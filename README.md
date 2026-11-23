# france-load-forecast

Forecasting and analysis of French electricity consumption from RTE open data.

The project is in development.

## Data

All inputs are public datasets published by RTE on [ODRÉ](https://odre.opendatasoft.com) under the
[Licence Ouverte 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence/).

| Dataset | Content |
|---|---|
| `eco2mix-national-cons-def` | National consumption every 30 minutes since 2012, consolidated then definitive |
| `eco2mix-national-tr` | National consumption every 15 minutes, in real time, after the last consolidated day |
| `consommation-quotidienne-brute` | Consolidated consumption every 30 minutes, a month ahead of éCO2mix, to measure the revision of real-time data |
| `pic-journalier-consommation-brute` | Daily peak, national temperature and reference temperature |
| `conso_brute_corrigee_client_direct` | Monthly gross and corrected consumption, used for validation |

```sh
uv run flf ingest
```

downloads the exports to `data/raw/<dataset>/<date>.csv`, loads them into `data/warehouse.duckdb`
and runs the data checks. The command exits with status 1 if a check fails.

```sh
uv run flf fit
uv run flf correct
uv run flf backtest
uv run flf forecast
uv run flf decompose
```

fit the daily load model, compare the climate-corrected consumption with RTE's, score forecasts
made from past months, forecast monthly energy over the current month and the next 11 with a band
calibrated on those past errors, and split the energy gaps of the last 12 months into climate,
calendar, structural and residual terms.
[docs/methodology.md](docs/methodology.md) describes the model and its results.

```sh
uv run flf publish
```

writes the weekly bundle to `data/bundle/`, one JSON file per subject, from the warehouse and the
results of `flf backtest`. Every file carries the publication date and the model id (`model_id` in
[`config/model.toml`](config/model.toml)).

| File | Content |
|---|---|
| `meta.json` | Last consolidated day, last day with a temperature, last measured day, revision of real-time load |
| `forecast.json` | Monthly P10, P50 and P90 from the current month, energy measured so far, total P50 over 12 months |
| `gaps.json` | Gaps of the last 12 months to the forecast and to the year before, term by term, with the temperatures they compare |
| `history.json` | Energy of each whole month, annual gross and corrected energy against RTE's |
| `accuracy.json` | Backtest errors by horizon and coverage of the P10-P90 band |
| `model.json` | Estimation window and response to temperature of the forecasting model |
| `scenarios.json` | Energy of each year from 2027 to 2031 by BP2025 trajectory and winter, month by month |

## Publication

The [Publish](.github/workflows/publish.yml) workflow runs every Monday at 06:00 UTC, after each
merge on `main`, and on demand. It runs `ingest`, `backtest` and `publish`, which refuses to write
a bundle that breaks its schema ([`bundle.py`](src/france_load_forecast/bundle.py)): a band out
of order, an implausible energy, terms that do not add up to their gap. `flf snapshot` then saves
the real-time load, which RTE overwrites once it is consolidated.

[`scripts/archive.sh`](scripts/archive.sh) commits the result to the `data` branch:

- `latest/`: the last bundle, read by the page;
- `archive/<date>/`: each published bundle with its real-time snapshot, so that a forecast can be
  judged once its months are over.

The workflow then builds the page and deploys it to GitHub Pages, whose source must be set to
GitHub Actions once, in the Pages settings of the repository.

## Page

The page, in French, is at <https://zkyasin.github.io/france-load-forecast/>. It shows:

- the forecast of the next twelve months with its band, and the forecast of any past
  publication against the months measured since;
- the accuracy of past forecasts;
- the gaps of the last twelve months, against the year before or against the forecast, split
  into weather, calendar and other effects;
- the note of the month, written by the agent;
- in the bottom-right corner, a "tête de chat" pylon that opens a panel of questions to the
  agent: suggestions drawn from the latest data, what the agent reads as it reads it, answers
  with their source, a chart of the month they read and the sections of the page that show
  them, follow-up questions that may build on the answer before, and the questions left once
  few are. It appears once the question API is deployed and its address is set as the
  repository variable `API_URL`;
- the load added by one degree less, by temperature;
- the energy of each year since 2014, measured and corrected for the weather;
- the BP2025 scenarios to 2031, for a trajectory and a winter chosen by the reader;
- the method and the sources.

[`web/`](web) is a static site built with [Vite](https://vite.dev), TypeScript and
[Observable Plot](https://observablehq.com/plot/). It reads the bundles of the `data` branch,
which `npm run data` copies into `web/public/data/`. It requires Node.js 26:

```sh
cd web
npm ci --ignore-scripts
npm run data
npm run dev
```

## Agent

The agent answers questions in French and writes the monthly note from the bundle. Its tools are
read-only and return the figures it may quote: the forecast, the gaps of a month, annual energies,
the response to temperature, the accuracy of past forecasts, the scenarios, and dated facts from
[`config/facts.toml`](config/facts.toml). A verifier checks that every number of a text comes
from a tool result or is a year named in the question, and that the text holds no link. The model
gets one more try, and a text that still fails, or stays empty, is not shown.

The model is set in [`config/agent.toml`](config/agent.toml). Locally, it is Ministral 3 14B on
[Ollama](https://ollama.com):

```sh
brew install ollama
brew services start ollama
ollama pull ministral-3:14b
```

```sh
uv run flf ask "Pourquoi la consommation de février 2026 a-t-elle été plus basse que prévu ?"
uv run flf note 2026-09
```

`ask` prints the tool calls and the answer. `note` writes `notes/2026-09.md`: the energy of the
month and its gaps term by term, then a reading written by the agent, which may only read the gaps
of the month. It also writes `notes/2026-09.json` for the page. Both commands exit with status 1
if a number has no source. [`evals/`](evals) holds 40 frozen questions with their expected
answers, and `flf eval` scores the answers of a model on them, without a judge: the
[results](evals/results.md) compare the local model with the hosted ones.

A note reaches the page through a pull request: its reading is reviewed, then the page shows the
latest note from its next deployment. Before writing a note, `flf note` checks every figure of its
reading against the values of the note, with its unit and, when written, its sign. The tests run
the same check on the committed notes, so that an edit by hand cannot add a figure the note does
not give.

## Question API

[`api.py`](src/france_load_forecast/api.py) serves the agent to the page. `POST /ask` takes
`{"question": "..."}` and returns the answer, the tools the agent called with their arguments, the
date of the data and the questions the visitor has left, or the agent's refusal when a number of
the answer has no source. An answer that read no data is replaced by a sentence saying that the
question is out of scope. A question may come with `previous`, the question and the answer just
before it, which the agent reads as context but never as a source of numbers. `POST /ask/stream`
gives the same reply as server-sent events, after a `step` event for each tool the agent calls. The API reads the last bundle
from the page and reads it again every hour. The limits of [`config/api.toml`](config/api.toml)
are 60 questions a day in all, and 5 an hour and 20 a day per visitor. They are kept in memory,
so they start again when Cloud Run stops the idle instance; the free plan of Groq bounds the
rest.

To run it locally with the Ollama model:

```sh
FLF_MODELS=ollama:ministral-3:14b uv run uvicorn france_load_forecast.api:build --factory
```

Online, it runs on Cloud Run in Paris (europe-west9), with Groq's free plan: gpt-oss-120b, then
gpt-oss-20b. Beyond its limits, Groq answers with an error instead of a bill. The image holds only
the agent and its dependencies. The [Deploy](.github/workflows/deploy.yml) workflow builds the
image and deploys it after each merge that changes the agent. To set it up once:

1. Create a Google Cloud project with two budgets: a spend cap of 2 € a month on Cloud Run,
   which pauses the service when reached, and an alert at 1 € on all the services of the
   project.
2. Create a Groq API key.
3. Run `scripts/cloud-setup.sh <project id>`. It asks for the key, and leaves Cloud Run's
   request logs out of storage, as the spend cap does not cover logging. Then set the variables
   it prints on the repository.
4. Run the Deploy workflow, then set the repository variable `API_URL` to the address of the
   service.

## Development

Requires [uv](https://docs.astral.sh/uv/). It installs Python 3.12 and the locked dependencies.

```sh
uv sync
uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
uv run pytest
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow.

## License

The code is released under the MIT license.
