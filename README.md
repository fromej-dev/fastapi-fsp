# fastapi-fsp

[![PyPI](https://img.shields.io/pypi/v/fastapi-fsp)](https://pypi.org/project/fastapi-fsp/)
[![Python versions](https://img.shields.io/pypi/pyversions/fastapi-fsp)](https://pypi.org/project/fastapi-fsp/)
[![CI](https://github.com/fromej-dev/fastapi-fsp/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/fromej-dev/fastapi-fsp/actions/workflows/ci.yml)
[![Coverage](https://codecov.io/gh/fromej-dev/fastapi-fsp/branch/master/graph/badge.svg)](https://codecov.io/gh/fromej-dev/fastapi-fsp)
[![License: MIT](https://img.shields.io/pypi/l/fastapi-fsp)](https://github.com/fromej-dev/fastapi-fsp/blob/master/LICENSE)
[![Docs](https://img.shields.io/badge/docs-zensical-blue)](https://fromej-dev.github.io/fastapi-fsp/)

**Filter, sort, paginate and search a FastAPI list endpoint with one dependency.**

<!-- --8<-- [start:intro] -->
Add `fsp: FSPManager = Depends(FSPManager)` to an endpoint, pass it a SQLModel or SQLAlchemy
`select()`, and the endpoint accepts filters, sorting, pagination and multi-column search
from the query string. No filter schema to declare per model.

```
GET /heroes/?search=spider+man&search_fields=name,secret_name&field=age&operator=gte&value=18&sort_by=name&page=2
```

```json
{
  "data": [{"id": 7, "name": "Spider-Man", "secret_name": "Peter Parker", "age": 18}],
  "meta": {"pagination": {"total_items": 11, "per_page": 10, "current_page": 2, "total_pages": 2}},
  "links": {"self": "...", "first": "...", "next": null, "prev": "...", "last": "..."}
}
```

It is built for the backend of a data table: the search box, column filters, sortable
headers and the pager all map to query parameters on one endpoint. See the
[React + TanStack Table example](https://github.com/fromej-dev/fastapi-fsp/tree/master/examples/react-table).

![A TanStack Table searching, filtering, sorting and paging through a fastapi-fsp endpoint](https://raw.githubusercontent.com/fromej-dev/fastapi-fsp/master/docs/assets/react-table-demo.gif)

## Why fastapi-fsp?

[fastapi-pagination](https://github.com/uriyyo/fastapi-pagination) and
[fastapi-filter](https://github.com/arthurio/fastapi-filter) are good libraries that each
cover part of this. fastapi-fsp covers all of it in one dependency, for SQL databases:

|                                                   | fastapi-fsp                                  | fastapi-pagination                       | fastapi-filter                       |
|---------------------------------------------------|----------------------------------------------|------------------------------------------|--------------------------------------|
| Pagination                                        | ✅ page / per_page, total count, HATEOAS links | ✅ page, limit-offset and cursor           | ➖ pair it with fastapi-pagination    |
| Filtering                                         | ✅ 18 operators on any column                  | ➖                                        | ✅ via a `Filter` class per model     |
| Sorting                                           | ✅                                            | ➖                                        | ✅                                    |
| Search one term across several columns (OR)       | ✅ `search` + `search_fields`, per-word matching | ➖                                     | ✅ over the fields you declare        |
| Indexed PostgreSQL search (`tsvector`, `pg_trgm`) | ✅                                            | ➖                                        | ➖                                    |
| Setup per endpoint                                | one `Depends(FSPManager)`                    | one `Depends` + `paginate()`             | a `Filter` class per model           |
| Backends                                          | SQLModel / SQLAlchemy, sync and async        | SQLAlchemy, SQLModel, MongoDB, and more  | SQLAlchemy, MongoEngine              |

Choose **fastapi-pagination** if you need cursor pagination or a non-SQL backend. Choose
**fastapi-filter** if you want every filter declared as a typed field that shows up in the
OpenAPI schema. Choose **fastapi-fsp** if you want one dependency that turns a `select()`
into a full list endpoint, with fast search on PostgreSQL. It also filters and sorts on
computed `hybrid_property` fields.

Full documentation: **[fromej-dev.github.io/fastapi-fsp](https://fromej-dev.github.io/fastapi-fsp/)**
<!-- --8<-- [end:intro] -->

## Installation
<!-- --8<-- [start:installation] -->

Using uv (recommended):

```
# create & activate virtual env with uv
uv venv
. .venv/bin/activate

# add runtime dependency
uv add fastapi-fsp
```

Using pip:

```
pip install fastapi-fsp
```
<!-- --8<-- [end:installation] -->

## Quick start
<!-- --8<-- [start:quickstart] -->

Below is a minimal example using FastAPI and SQLModel.

```python
from typing import Optional
from fastapi import Depends, FastAPI
from sqlmodel import Field, SQLModel, Session, create_engine, select

from fastapi_fsp.fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse

class HeroBase(SQLModel):
    name: str = Field(index=True)
    secret_name: str
    age: Optional[int] = Field(default=None, index=True)

class Hero(HeroBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

class HeroPublic(HeroBase):
    id: int

engine = create_engine("sqlite:///database.db", connect_args={"check_same_thread": False})
SQLModel.metadata.create_all(engine)

app = FastAPI()

def get_session():
    with Session(engine) as session:
        yield session

@app.get("/heroes/", response_model=PaginatedResponse[HeroPublic])
def read_heroes(*, session: Session = Depends(get_session), fsp: FSPManager = Depends(FSPManager)):
    query = select(Hero)
    return fsp.generate_response(query, session)
```

Run the app and query:

- Pagination: `GET /heroes/?page=1&per_page=10`
- Sorting: `GET /heroes/?sort_by=name&order=asc`
- Filtering: `GET /heroes/?field=age&operator=gte&value=21`

The response includes data, meta (pagination, filters, sorting), and links (self, first, next, prev, last).
<!-- --8<-- [end:quickstart] -->

## Query parameters
<!-- --8<-- [start:query-parameters] -->

Pagination:
- page: integer (>=1), default 1
- per_page: integer (1..100), default 10

Sorting:
- sort_by: the field name, e.g., `name`
- order: `asc` or `desc`

Filtering (two supported formats):

1) Simple (triplets repeated in the query string):
- field: the field/column name, e.g., `name`
- operator: one of
  - eq, ne
  - lt, lte, gt, gte
  - in, not_in (comma-separated values)
  - between (two comma-separated values)
  - like, not_like
  - ilike, not_ilike (if backend supports ILIKE)
  - is_null, is_not_null
  - contains, starts_with, ends_with (translated to LIKE patterns)
- value: raw string value (or list-like comma-separated depending on operator)

Examples (simple format):
- `?field=name&operator=eq&value=Deadpond`
- `?field=age&operator=between&value=18,30`
- `?field=name&operator=in&value=Deadpond,Rusty-Man`
- `?field=name&operator=contains&value=man`
- Chain multiple filters by repeating the triplet: `?field=age&operator=gte&value=18&field=name&operator=ilike&value=rust`

2) Indexed format (useful for clients that handle arrays of objects):
- Use keys like `filters[0][field]`, `filters[0][operator]`, `filters[0][value]`, then increment the index for additional filters (`filters[1][...]`, etc.).

Example (indexed format):
```
?filters[0][field]=age&filters[0][operator]=gte&filters[0][value]=18&filters[1][field]=name&filters[1][operator]=ilike&filters[1][value]=joy
```

Notes:
- Both formats are equivalent; the indexed format takes precedence if present.
- If any filter is incomplete (missing operator or value in the indexed form, or mismatched counts of simple triplets), the API responds with HTTP 400.
<!-- --8<-- [end:query-parameters] -->

## Filtering on Computed Fields
<!-- --8<-- [start:computed-fields] -->

You can filter (and sort) on SQLAlchemy `hybrid_property` fields that have a SQL expression defined. This enables filtering on calculated or derived values at the database level.

### Defining a Computed Field

```python
from typing import ClassVar, Optional
from sqlalchemy import func
from sqlalchemy.ext.hybrid import hybrid_property
from sqlmodel import Field, SQLModel

class HeroBase(SQLModel):
    name: str = Field(index=True)
    secret_name: str
    age: Optional[int] = Field(default=None)
    full_name: ClassVar[str]  # Required: declare as ClassVar for Pydantic

    @hybrid_property
    def full_name(self) -> str:
        """Python-level implementation (used on instances)."""
        return f"{self.name}-{self.secret_name}"

    @full_name.expression
    def full_name(cls):
        """SQL-level implementation (used in queries)."""
        return func.concat(cls.name, "-", cls.secret_name)

class Hero(HeroBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

class HeroPublic(HeroBase):
    id: int
    full_name: str  # Include in response model
```

### Querying Computed Fields

Once defined, you can filter and sort on the computed field like any regular field:

```
# Filter by computed field
GET /heroes/?field=full_name&operator=eq&value=Spider-Man
GET /heroes/?field=full_name&operator=ilike&value=%man
GET /heroes/?field=full_name&operator=contains&value=Spider

# Sort by computed field
GET /heroes/?sort_by=full_name&order=asc

# Combine with other filters
GET /heroes/?field=full_name&operator=starts_with&value=Spider&field=age&operator=gte&value=21
```

### Requirements

- The `hybrid_property` must have an `.expression` decorator that returns a valid SQL expression
- The field should be declared as `ClassVar[type]` in the SQLModel base class to work with Pydantic
- Only computed fields with SQL expressions are supported; Python-only properties cannot be filtered at the database level
<!-- --8<-- [end:computed-fields] -->

## OR Filters (Multi-Column Search)
<!-- --8<-- [start:or-filters] -->

OR filters let you search across multiple columns with a single search term — ideal for powering a table search input in your frontend.

### Query Parameters

Use `search` and `search_fields` to search across columns with OR logic:

```
GET /heroes/?search=john&search_fields=name,secret_name,email
```

This generates: `WHERE name ILIKE '%john%' OR secret_name ILIKE '%john%' OR email ILIKE '%john%'`

A search with several words is split into tokens by default (`search_mode=token`), and every
token has to match at least one field: `?search=john smith&search_fields=first_name,last_name`
finds "John Smith" even though no single column contains "john smith". Use
`search_mode=phrase` to match the whole string as one value.

Combine with regular AND filters:

```
GET /heroes/?search=john&search_fields=name,email&field=deleted&operator=eq&value=false
```

This generates: `WHERE (name ILIKE '%john%' OR email ILIKE '%john%') AND deleted = false`

### Programmatic API

Use `CommonFilters.multi_field_search()` for server-side search:

```python
from fastapi_fsp import CommonFilters

@app.get("/heroes/")
def read_heroes(session: Session = Depends(get_session), fsp: FSPManager = Depends(FSPManager)):
    or_groups = CommonFilters.multi_field_search(
        fields=["name", "secret_name"],
        term="john",
        match_type="contains",  # or "starts_with", "ends_with"
    )
    fsp.with_or_filters(or_groups)
    return fsp.generate_response(select(Hero), session)
```

Or build OR groups with the `FilterBuilder`:

```python
from fastapi_fsp import FilterBuilder

or_group = (
    FilterBuilder()
    .where("name").contains("john")
    .where("email").contains("john")
    .build_or_group()
)
fsp.with_or_filters([or_group])
```

Or create `OrFilterGroup` objects directly:

```python
from fastapi_fsp import OrFilterGroup, Filter, FilterOperator

group = OrFilterGroup(filters=[
    Filter(field="name", operator=FilterOperator.CONTAINS, value="john"),
    Filter(field="email", operator=FilterOperator.CONTAINS, value="john"),
])
fsp.with_or_filters([group])
```

### Response

When OR filters are active, they appear in the response meta:

```json
{
  "meta": {
    "or_filters": [
      {
        "filters": [
          {"field": "name", "operator": "contains", "value": "john"},
          {"field": "email", "operator": "contains", "value": "john"}
        ]
      }
    ]
  }
}
```
<!-- --8<-- [end:or-filters] -->

## FilterBuilder API
<!-- --8<-- [start:filter-builder] -->

For programmatic filter creation, use the fluent `FilterBuilder` API:

```python
from fastapi_fsp import FilterBuilder

# Instead of manually creating Filter objects:
# filters = [
#     Filter(field="age", operator=FilterOperator.GTE, value="30"),
#     Filter(field="city", operator=FilterOperator.EQ, value="Chicago"),
# ]

# Use the builder pattern:
filters = (
    FilterBuilder()
    .where("age").gte(30)
    .where("city").eq("Chicago")
    .where("active").eq(True)
    .where("tags").in_(["python", "fastapi"])
    .where("created_at").between("2024-01-01", "2024-12-31")
    .build()
)

# Use with FSPManager
@app.get("/heroes/")
def read_heroes(session: Session = Depends(get_session), fsp: FSPManager = Depends(FSPManager)):
    additional_filters = FilterBuilder().where("deleted").eq(False).build()
    fsp.with_filters(additional_filters)
    return fsp.generate_response(select(Hero), session)
```

### Available FilterBuilder Methods

| Method | Description |
|--------|-------------|
| `.eq(value)` | Equal to |
| `.ne(value)` | Not equal to |
| `.gt(value)` | Greater than |
| `.gte(value)` | Greater than or equal |
| `.lt(value)` | Less than |
| `.lte(value)` | Less than or equal |
| `.like(pattern)` | Case-sensitive LIKE |
| `.ilike(pattern)` | Case-insensitive LIKE |
| `.in_(values)` | IN list |
| `.not_in(values)` | NOT IN list |
| `.between(low, high)` | BETWEEN range |
| `.is_null()` | IS NULL |
| `.is_not_null()` | IS NOT NULL |
| `.starts_with(prefix)` | Starts with (case-insensitive) |
| `.ends_with(suffix)` | Ends with (case-insensitive) |
| `.contains(substring)` | Contains (case-insensitive) |
<!-- --8<-- [end:filter-builder] -->

## Common Filter Presets
<!-- --8<-- [start:presets] -->

For frequently used filter patterns, use `CommonFilters`:

```python
from fastapi_fsp import CommonFilters

# Active (non-deleted) records
filters = CommonFilters.active()  # deleted=false

# Recent records (last 7 days)
filters = CommonFilters.recent(days=7)

# Date range
filters = CommonFilters.date_range(start=datetime(2024, 1, 1), end=datetime(2024, 12, 31))

# Records created today
filters = CommonFilters.today()

# Null checks
filters = CommonFilters.not_null("email")
filters = CommonFilters.is_null("deleted_at")

# Search
filters = CommonFilters.search("name", "john", match_type="contains")

# Combine presets
filters = CommonFilters.active() + CommonFilters.recent(days=30)
```
<!-- --8<-- [end:presets] -->

## Configuration
<!-- --8<-- [start:configuration] -->

Customize FSPManager behavior with `FSPConfig`:

```python
from fastapi_fsp import FSPConfig, FSPPresets

# Custom configuration
config = FSPConfig(
    max_per_page=50,
    default_per_page=20,
    strict_mode=True,  # Raise errors for unknown fields
    max_page=100,
    allow_deep_pagination=False,
)

# Or use presets
config = FSPPresets.strict()  # strict_mode=True
config = FSPPresets.limited_pagination(max_page=50)  # Limit deep pagination
config = FSPPresets.high_volume(max_per_page=500)  # High-volume APIs

# Apply configuration
@app.get("/heroes/")
def read_heroes(session: Session = Depends(get_session), fsp: FSPManager = Depends(FSPManager)):
    fsp.apply_config(config)
    return fsp.generate_response(select(Hero), session)
```

### Search Backend Optimization

By default, tokenized search generates N tokens x M fields = N*M individual ILIKE conditions, each requiring a full table scan. For PostgreSQL, you can choose a faster search backend:

| Backend | SQL strategy | Substring match? | Indexable? |
|---------|-------------|------------------|------------|
| `ILIKE` (default) | N*M individual ILIKEs | Yes | No (full scan) |
| `TSVECTOR` | `to_tsvector @@ to_tsquery` | Prefix only | GIN index |
| `TRIGRAM` | concat + N ILIKEs | Yes | GIN + pg_trgm |

**Key tradeoff**: `TSVECTOR` is fastest (single expression) but only matches word prefixes — `"media"` matches `"Medialaan"` but `"laan"` does not. `TRIGRAM` preserves full substring semantics while reducing N*M to N operations.

```python
from fastapi_fsp import FSPConfig, SearchBackend

# Use tsvector for fast prefix-matching search (PostgreSQL only)
config = FSPConfig(search_backend=SearchBackend.TSVECTOR)

# Use trigram for full substring search with fewer operations (PostgreSQL only)
config = FSPConfig(search_backend=SearchBackend.TRIGRAM)

# Limit maximum search tokens (default: 10)
config = FSPConfig(
    search_backend=SearchBackend.TSVECTOR,
    max_search_tokens=5,
)

@app.get("/heroes/")
def read_heroes(
    session: Session = Depends(get_session),
    fsp: FSPManager = Depends(FSPManager),
):
    fsp.apply_config(config)
    return fsp.generate_response(select(Hero), session)
```

Non-search OR groups (mixed operators, phrase mode, custom `with_or_filters()`) automatically fall back to the standard ILIKE path regardless of the configured backend.

### Strict Mode

When `strict_mode=True`, FSPManager raises HTTP 400 errors for unknown filter/sort fields:

```python
# With strict_mode=True, this raises HTTP 400:
# GET /heroes/?field=unknown_field&operator=eq&value=test
# Error: "Unknown field 'unknown_field'. Available fields: age, id, name, secret_name"
```
<!-- --8<-- [end:configuration] -->

## Convenience Methods
<!-- --8<-- [start:convenience] -->

### from_model()

Simplify common queries with `from_model()`:

```python
@app.get("/heroes/")
def read_heroes(session: Session = Depends(get_session), fsp: FSPManager = Depends(FSPManager)):
    # Instead of:
    # query = select(Hero)
    # return fsp.generate_response(query, session)

    # Use:
    return fsp.from_model(Hero, session)

# Async version
@app.get("/heroes/")
async def read_heroes(session: AsyncSession = Depends(get_session), fsp: FSPManager = Depends(FSPManager)):
    return await fsp.from_model_async(Hero, session)
```

### Method Chaining

Chain configuration methods:

```python
@app.get("/heroes/")
def read_heroes(session: Session = Depends(get_session), fsp: FSPManager = Depends(FSPManager)):
    return (
        fsp
        .with_filters(CommonFilters.active())
        .apply_config(FSPPresets.strict())
        .generate_response(select(Hero), session)
    )
```
<!-- --8<-- [end:convenience] -->

## Response model
<!-- --8<-- [start:response] -->

```
{
  "data": [ ... ],
  "meta": {
    "pagination": {
      "total_items": 42,
      "per_page": 10,
      "current_page": 1,
      "total_pages": 5
    },
    "filters": [
      {"field": "name", "operator": "eq", "value": "Deadpond"}
    ],
    "or_filters": [
      {
        "filters": [
          {"field": "name", "operator": "contains", "value": "john"},
          {"field": "email", "operator": "contains", "value": "john"}
        ]
      }
    ],
    "sort": {"sort_by": "name", "order": "asc"}
  },
  "links": {
    "self": "/heroes/?page=1&per_page=10",
    "first": "/heroes/?page=1&per_page=10",
    "next": "/heroes/?page=2&per_page=10",
    "prev": null,
    "last": "/heroes/?page=5&per_page=10"
  }
}
```

`filters` and `or_filters` are `null` when not active.
<!-- --8<-- [end:response] -->

## Contributing

Issues and pull requests are welcome. [CONTRIBUTING.md](https://github.com/fromej-dev/fastapi-fsp/blob/master/CONTRIBUTING.md) covers the dev
setup, the checks CI runs, and how releases are made. Changes per version are in
[CHANGELOG.md](https://github.com/fromej-dev/fastapi-fsp/blob/master/CHANGELOG.md) and on the [Releases](https://github.com/fromej-dev/fastapi-fsp/releases) page.

## License

MIT License. See [LICENSE](https://github.com/fromej-dev/fastapi-fsp/blob/master/LICENSE).
