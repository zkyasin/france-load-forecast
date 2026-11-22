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
| `gaps.json` | Gaps of the last 12 months to the forecast and to the year before, term by term |
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
if a number has no source. [`evals/questions.toml`](evals/questions.toml) holds frozen questions
and their expected answers.

A note reaches the page through a pull request: its reading is reviewed, then the page shows the
latest note from its next deployment. Before writing a note, `flf note` checks every figure of its
reading against the values of the note, with its unit and, when written, its sign. The tests run
the same check on the committed notes, so that an edit by hand cannot add a figure the note does
not give.

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
