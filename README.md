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
uv run flf forecast
uv run flf backtest
```

fit the daily load model, compare the climate-corrected consumption with RTE's, forecast
monthly energy over the next 12 months, and score forecasts made from past months.
[docs/methodology.md](docs/methodology.md) describes the model and its results.

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
