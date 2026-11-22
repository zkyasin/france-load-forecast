"""The public question API: the agent answers from the last published bundle.

POST /ask takes a question in French and returns the answer, or the refusal of the agent when a
number of the answer has no source. The bundle is read from the page, where each publication
deploys it. Limits per visitor and per day keep the use of the model and of Cloud Run small.

Run it with `uvicorn france_load_forecast.api:build --factory`.
"""

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

import groq
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel

from france_load_forecast import bundle as schema
from france_load_forecast.agent import agent, tools

# Errors of a model that another model may not have: a rate limit, an outage, a malformed call.
UNAVAILABLE = (groq.APIError, httpx.HTTPError)

DAY = 86_400
HOUR = 3_600

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
    and the last day."""

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
            asked = self.asked.setdefault(visitor, deque())
            while asked and asked[0] <= now - DAY:
                asked.popleft()
            last_hour = sum(1 for moment in asked if moment > now - HOUR)
            if self.today >= self.settings.questions_per_day:
                return "Le nombre de questions du jour est atteint. Réessayez demain."
            if (
                len(asked) >= self.settings.questions_per_visitor_per_day
                or last_hour >= self.settings.questions_per_visitor_per_hour
            ):
                return "Vous avez posé beaucoup de questions. Réessayez plus tard."
            asked.append(now)
            self.today += 1
            return None


def visitor(request: Request) -> str:
    """The address of the visitor. Cloud Run appends it to X-Forwarded-For, after any value the
    visitor sent, so the last one is the one to trust."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else ""


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["POST"],
        allow_headers=["Content-Type"],
    )
    limits = Limits(settings, clock)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/ask")
    def ask(body: Question, request: Request) -> Reply:
        question = body.question.strip()
        if not question or len(question) > config.max_question_chars:
            raise HTTPException(
                422, f"Posez une question de 1 à {config.max_question_chars} caractères."
            )
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
            try:
                answer = agent.ask(question, current, facts, models[name], config)
            except UNAVAILABLE as error:
                # The question stays out of the logs.
                log.warning("%s did not answer: %s", name, type(error).__name__)
                continue
            return Reply(
                answer=agent.plain(answer.text) if answer.verified else agent.REFUSAL,
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
