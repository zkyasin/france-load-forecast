# The question API (src/france_load_forecast/api.py). Only the dependency group "api" goes in:
# the agent needs LangChain and the standard library, not the forecasting stack.
FROM python:3.12.16-slim AS build
COPY --from=astral/uv:0.11.33 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --only-group api

FROM python:3.12.16-slim
WORKDIR /app
COPY --from=build /app/.venv .venv
COPY src/france_load_forecast/__init__.py src/france_load_forecast/api.py \
    src/france_load_forecast/bundle.py src/france_load_forecast/
COPY src/france_load_forecast/agent/*.py src/france_load_forecast/agent/
COPY config/agent.toml config/api.toml config/facts.toml config/

ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app/src
RUN useradd --no-create-home api
USER api
# Cloud Run gives the port to listen on in PORT.
CMD exec uvicorn france_load_forecast.api:build --factory --host 0.0.0.0 --port "${PORT:-8080}"
