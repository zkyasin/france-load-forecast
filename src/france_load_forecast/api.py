"""The public question API: the agent answers from the last published bundle.

POST /ask takes a question in French and returns the answer, or the refusal of the agent when a
number of the answer has no source. The bundle is read from the page, where each publication
deploys it. Limits per visitor and per day keep the use of the model and of Cloud Run small. They
are kept in memory, so they start again when Cloud Run stops or replaces the instance.

Run it with `uvicorn france_load_forecast.api:build --factory`.
"""

import ipaddress
import logging
import os
import time
import tomllib
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from france_load_forecast import bundle as schema
from france_load_forecast.agent import agent, tools

DAY = 86_400
HOUR = 3_600
# Far above a question of 300 characters, even with every character escaped.
MAX_BODY_BYTES = 4_096

# Said instead of an answer that read no data: a question in scope always calls a tool, so the
# text could only come from the model, as when a question asks it to change its rules.
OUT_OF_SCOPE = (
    "Cette question sort du périmètre de l'outil, qui répond sur la consommation d'électricité en "
    "France à partir des données publiées."
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    bundle_url: str
    bundle_ttl_seconds: float
    models: list[str]
    allowed_origins: list[str]
    questions_per_day: int
    questions_per_visitor_per_hour: int
    questions_per_visitor_per_day: int


def load_settings(path: Path) -> Settings:
    with path.open("rb") as file:
        settings = Settings(**tomllib.load(file))
    models = os.environ.get("FLF_MODELS")
    return replace(settings, models=models.split(",")) if models else settings


def fetch_bundle(url: str) -> tools.Bundle:
    """The files of the bundle published at `url`."""
    with httpx.Client(timeout=10) as client:
        return {
            name: client.get(f"{url}{name}.json").raise_for_status().json() for name in schema.FILES
        }


class BundleSource:
    """The last bundle, read again once it is older than `ttl` seconds. A bundle that cannot be
    read, or breaks its schema, leaves the previous one in use until the next try."""

    def __init__(
        self,
        fetch: Callable[[], tools.Bundle],
        ttl: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.fetch, self.ttl, self.clock = fetch, ttl, clock
        self.bundle: tools.Bundle | None = None
        self.read_at = 0.0
        self.lock = Lock()

    def get(self) -> tools.Bundle:
        with self.lock:
            if self.bundle is None or self.clock() - self.read_at > self.ttl:
                try:
                    fresh = self.fetch()
                    problems = schema.check(fresh)
                    if problems:
                        raise ValueError("; ".join(problems))
                    self.bundle = fresh
                except (httpx.HTTPError, ValueError):
                    if self.bundle is None:
                        raise
                self.read_at = self.clock()
            return self.bundle


class Limits:
    """Questions accepted in all during the current UTC day, and per visitor over the last hour
    and the last day. Only visitors whose questions were accepted are kept."""

    def __init__(self, settings: Settings, clock: Callable[[], float] = time.time) -> None:
        self.settings, self.clock = settings, clock
        self.asked: dict[str, deque[float]] = {}
        self.day, self.today = "", 0
        self.lock = Lock()

    def refuse(self, visitor: str) -> str | None:
        """Why a question of `visitor` is refused now, or None once it is counted."""
        now = self.clock()
        day = time.strftime("%Y-%m-%d", time.gmtime(now))
        with self.lock:
            if day != self.day:
                self.day, self.today = day, 0
            asked = self.asked.get(visitor, deque())
            while asked and asked[0] <= now - DAY:
                asked.popleft()
            if not asked:
                self.asked.pop(visitor, None)
            last_hour = sum(1 for moment in asked if moment > now - HOUR)
            if self.today >= self.settings.questions_per_day:
                return "Le nombre de questions du jour est atteint. Réessayez demain."
            if (
                len(asked) >= self.settings.questions_per_visitor_per_day
                or last_hour >= self.settings.questions_per_visitor_per_hour
            ):
                return "Vous avez posé beaucoup de questions. Réessayez plus tard."
            asked.append(now)
            self.asked[visitor] = asked
            self.today += 1
            return None


def visitor(request: Request) -> str:
    """Who asks. Cloud Run appends the address of the visitor to X-Forwarded-For, after any value
    the visitor sent, so the last one is the one to trust. An IPv6 visitor holds a whole /64, so
    it is counted by its /64."""
    forwarded = request.headers.get("x-forwarded-for", "")
    address = forwarded.split(",")[-1].strip() if forwarded else ""
    if not address and request.client:
        address = request.client.host
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return address
    if parsed.version == 6:
        return str(ipaddress.ip_network(f"{parsed}/64", strict=False))
    return address


class BodyLimit:
    """Refuses a request whose body grows past `limit` bytes, counted as it arrives, before the
    app reads it whole."""

    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app, self.limit = app, limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        received = 0

        async def counted() -> Message:
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.limit:
                raise HTTPException(413, "La question est trop longue.")
            return message

        await self.app(scope, counted, send)


class Question(BaseModel):
    question: str


class Reply(BaseModel):
    answer: str
    verified: bool
    # The tools the agent called, in order.
    tools: list[str]
    # Date of the bundle the answer comes from.
    published: str


def create_app(
    settings: Settings,
    config: agent.AgentConfig,
    facts: dict[str, dict[str, Any]],
    source: BundleSource,
    models: dict[str, BaseChatModel],
    clock: Callable[[], float] = time.time,
) -> FastAPI:
    app = FastAPI(title="france-load-forecast", docs_url=None, redoc_url=None, openapi_url=None)
    # Added last, the CORS middleware wraps the other one, so that its refusals carry CORS too.
    app.add_middleware(BodyLimit, limit=MAX_BODY_BYTES)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["POST"],
        allow_headers=["Content-Type"],
    )
    limits = Limits(settings, clock)
    malformed = f"Posez une question de 1 à {config.max_question_chars} caractères."

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, error: RequestValidationError) -> JSONResponse:
        # FastAPI's own reply would send the request back.
        return JSONResponse({"detail": malformed}, status_code=422)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/ask")
    def ask(body: Question, request: Request) -> Reply:
        question = body.question.strip()
        try:
            question.encode("utf-8")
        except UnicodeEncodeError:
            question = ""
        if not question or len(question) > config.max_question_chars:
            raise HTTPException(422, malformed)
        refused = limits.refuse(visitor(request))
        if refused:
            raise HTTPException(429, refused)
        try:
            current = source.get()
        except (httpx.HTTPError, ValueError) as error:
            raise HTTPException(
                503, "Les données ne sont pas disponibles pour le moment."
            ) from error
        for name in settings.models:
            # Whatever stops a model, a rate limit, a timeout or a malformed call, the next one
            # may answer. The question stays out of the logs.
            try:
                answer = agent.ask(question, current, facts, models[name], config)
            except Exception as error:
                log.warning("%s did not answer: %s", name, type(error).__name__)
                continue
            if not answer.tool_calls:
                text = OUT_OF_SCOPE
            elif answer.verified:
                text = agent.plain(answer.text)
            else:
                text = agent.REFUSAL
            return Reply(
                answer=text,
                verified=answer.verified,
                tools=[call["name"] for call in answer.tool_calls],
                published=current["meta"]["published"],
            )
        raise HTTPException(503, "Le modèle ne répond pas pour le moment. Réessayez plus tard.")

    return app


def build(config_dir: Path = Path("config")) -> FastAPI:
    """The app with the files of `config_dir`, and the models named in config/api.toml."""
    settings = load_settings(config_dir / "api.toml")
    config = agent.load_config(config_dir / "agent.toml")
    models = {name: agent.chat_model(replace(config, model=name)) for name in settings.models}
    source = BundleSource(lambda: fetch_bundle(settings.bundle_url), settings.bundle_ttl_seconds)
    return create_app(settings, config, tools.load_facts(config_dir / "facts.toml"), source, models)
