# Contributing

## Workflow

- One branch per change, prefixed by its type: `feat/`, `fix/`, `docs/`, `test/`, `ci/`, `chore/`.
- Small commits whose messages follow [Conventional Commits](https://www.conventionalcommits.org/).
  The `commit-msg` hook and the CI check them.
- One pull request per branch. The CI must pass before review.
- `main` changes only through reviewed pull requests, merged with a merge commit.

## Checks

The CI runs the same commands as below:

```sh
uv run ruff check
uv run ruff format --check
uv run mypy
uv run pytest
```
