# Contributing to fastapi-fsp

Thanks for helping out. Bug reports, docs fixes, and pull requests are all welcome.
If you are looking for a place to start, check the issues labelled
[`good first issue`](https://github.com/fromej-dev/fastapi-fsp/labels/good%20first%20issue).

## Set up

The project uses [uv](https://docs.astral.sh/uv/) and supports Python 3.12+.

```bash
git clone https://github.com/fromej-dev/fastapi-fsp.git
cd fastapi-fsp
uv sync --dev
uv run pre-commit install   # optional: lint, format and test on each commit
```

## Before you open a pull request

Run the same checks CI runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

The PostgreSQL search backend tests (`tests/test_tsvector_pg.py`) are skipped unless
`DATABASE_URL` points to a PostgreSQL database:

```bash
docker run --rm -d -p 5432:5432 -e POSTGRES_USER=fsp_test -e POSTGRES_PASSWORD=fsp_test \
  -e POSTGRES_DB=fsp_test postgres:16
DATABASE_URL=postgresql://fsp_test:fsp_test@localhost:5432/fsp_test uv run pytest tests/test_tsvector_pg.py
```

Then:

- Add or update tests for the behaviour you changed.
- Add a line under **Unreleased** in [CHANGELOG.md](https://github.com/fromej-dev/fastapi-fsp/blob/master/CHANGELOG.md).
- Update the README if you changed or added a public API or query parameter. The docs site
  pulls its pages from the README, so there is one place to edit.

## Docs

Preview the docs site locally:

```bash
uv sync --group docs
uv run zensical serve
```

## Reporting bugs

Please include the fastapi-fsp, FastAPI, SQLModel/SQLAlchemy and database versions, the
request URL you sent, and what you expected to happen. A minimal model and endpoint that
reproduce the problem help most.

## Releases (maintainers)

1. Move the **Unreleased** entries in `CHANGELOG.md` under a new version heading.
2. Bump `version` in `pyproject.toml`.
3. Tag and push: `git tag v0.7.0 && git push origin v0.7.0`.

The release workflow checks that the tag matches `pyproject.toml`, runs the tests,
publishes to PyPI, and creates a GitHub Release with the changelog section as notes.
