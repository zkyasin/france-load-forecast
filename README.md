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
