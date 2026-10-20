# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/). Until 1.0, minor versions may contain
breaking changes; they are called out under **Changed**.

## [Unreleased]

### Added
- Date and time filters accept ISO 8601 strings, so `?field=created_at&operator=gte&value=2026-01-01T00:00:00` works directly ([#18](https://github.com/fromej-dev/fastapi-fsp/pull/18), thanks @Harold2017).
- Filtering and sorting on sensitive column names (`password`, `password_hash`, `secret`) is rejected with HTTP 400 ([#18](https://github.com/fromej-dev/fastapi-fsp/pull/18), thanks @Harold2017).
- `py.typed` marker, so type checkers use the package's inline type hints.
- Documentation site (built with Zensical), `CONTRIBUTING.md`, and this changelog.
- A React + TanStack Table example in `examples/react-table`.

## [0.6.0] - 2026-03-19

### Added
- `SearchBackend` option on `FSPConfig` with PostgreSQL `TSVECTOR` (GIN-indexable, prefix match) and `TRIGRAM` (substring match with fewer `ILIKE` conditions) backends ([#16](https://github.com/fromej-dev/fastapi-fsp/pull/16)).
- `max_search_tokens` setting to cap how many tokens a search term is split into.

### Fixed
- Cast non-text columns correctly when building the `tsvector` expression ([#17](https://github.com/fromej-dev/fastapi-fsp/pull/17)).

## [0.5.2] - 2026-02-19

### Fixed
- Enum columns are cast correctly when used as search fields.

## [0.5.1] - 2026-02-19

### Fixed
- Non-string columns are cast to text when used as search fields.

## [0.5.0] - 2026-02-19

### Added
- OR filters for multi-column search: `?search=john&search_fields=name,email` ([#15](https://github.com/fromej-dev/fastapi-fsp/pull/15)).
- `OrFilterGroup`, `FilterBuilder.build_or_group()`, `CommonFilters.multi_field_search()` and `FSPManager.with_or_filters()`.
- `or_filters` in the response `meta`.

## [0.4.2] - 2026-02-11

### Fixed
- Count queries on subqueries now keep the selected columns ([#14](https://github.com/fromej-dev/fastapi-fsp/pull/14)).

## [0.4.1] - 2026-02-09

### Fixed
- Rows returned by window-function pagination are converted to dicts before validation ([#13](https://github.com/fromej-dev/fastapi-fsp/pull/13)).

## [0.4.0] - 2026-02-06

### Changed
- `FSPManager` internals split into `FilterEngine`, `SortEngine` and `PaginationEngine`, with a strategy registry (`FILTER_STRATEGIES`) for filter operators ([#11](https://github.com/fromej-dev/fastapi-fsp/pull/11)).

### Added
- On PostgreSQL, pagination fetches the page and the total count in one query using a window function.

## [0.3.0] - 2026-02-06

### Added
- Filtering and sorting on SQLAlchemy `hybrid_property` fields that define a SQL expression ([#9](https://github.com/fromej-dev/fastapi-fsp/pull/9)).
- `FilterBuilder` fluent API, `FSPConfig` / `FSPPresets`, and `CommonFilters` presets.
- `from_model()`, `from_model_async()`, `with_filters()`, `with_sorting()` and `apply_config()` convenience methods.
- Benchmark CI workflow.

## [0.2.3] - 2026-02-06

- Published to PyPI; no separate changes are recorded in the repository history.

## [0.2.2] - 2026-01-23

### Added
- Strict mode: unknown filter or sort fields return HTTP 400 with the list of available fields ([#8](https://github.com/fromej-dev/fastapi-fsp/pull/8)).

### Changed
- Faster datetime parsing, cached column types and batched filter conditions.

## [0.2.1] - 2026-01-04

### Fixed
- Value coercion for typed columns ([#6](https://github.com/fromej-dev/fastapi-fsp/pull/6), thanks @Harold2017).

## [0.1.3] - 2025-11-10

### Added
- Support for Python 3.13 and 3.14.

## [0.1.2] - 2025-11-10

### Added
- Indexed filter format: `filters[0][field]=...&filters[0][operator]=...&filters[0][value]=...` ([#2](https://github.com/fromej-dev/fastapi-fsp/pull/2), thanks @Harold2017).

## [0.1.1] - 2025-08-20

### Added
- Async support (`AsyncSession`, `generate_response_async`).

## [0.1.0] - 2025-08-19

- First release: filtering, sorting and pagination as a FastAPI dependency.

[Unreleased]: https://github.com/fromej-dev/fastapi-fsp/commits/master
[0.6.0]: https://pypi.org/project/fastapi-fsp/0.6.0/
[0.5.2]: https://pypi.org/project/fastapi-fsp/0.5.2/
[0.5.1]: https://pypi.org/project/fastapi-fsp/0.5.1/
[0.5.0]: https://pypi.org/project/fastapi-fsp/0.5.0/
[0.4.2]: https://pypi.org/project/fastapi-fsp/0.4.2/
[0.4.1]: https://pypi.org/project/fastapi-fsp/0.4.1/
[0.4.0]: https://pypi.org/project/fastapi-fsp/0.4.0/
[0.3.0]: https://pypi.org/project/fastapi-fsp/0.3.0/
[0.2.3]: https://pypi.org/project/fastapi-fsp/0.2.3/
[0.2.2]: https://pypi.org/project/fastapi-fsp/0.2.2/
[0.2.1]: https://pypi.org/project/fastapi-fsp/0.2.1/
[0.1.3]: https://pypi.org/project/fastapi-fsp/0.1.3/
[0.1.2]: https://pypi.org/project/fastapi-fsp/0.1.2/
[0.1.1]: https://pypi.org/project/fastapi-fsp/0.1.1/
[0.1.0]: https://pypi.org/project/fastapi-fsp/0.1.0/
