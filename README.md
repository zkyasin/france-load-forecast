# france-load-forecast

Forecasting and analysis of French electricity consumption from RTE open data.

The project is in development.

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
