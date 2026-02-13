# fastapi-fsp

Filter, Sort, and Paginate (FSP) utilities for FastAPI + SQLModel.

fastapi-fsp helps you build standardized list endpoints that support:
- Filtering on arbitrary fields with rich operators (eq, ne, lt, lte, gt, gte, in, between, like/ilike, null checks, contains/starts_with/ends_with)
- OR filters for searching across multiple columns with a single search term
- Sorting by field (asc/desc)
- Pagination with page/per_page and convenient HATEOAS links

It is framework-friendly: you declare it as a FastAPI dependency and feed it a SQLModel/SQLAlchemy Select query and a Session.

## Installation

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

## Quick start

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

## Query parameters

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

## Filtering on Computed Fields

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

## OR Filters (Multi-Column Search)

OR filters let you search across multiple columns with a single search term — ideal for powering a table search input in your frontend.

### Query Parameters

Use `search` and `search_fields` to search across columns with OR logic:

```
GET /heroes/?search=john&search_fields=name,secret_name,email
```

This generates: `WHERE name ILIKE '%john%' OR secret_name ILIKE '%john%' OR email ILIKE '%john%'`

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

## FilterBuilder API

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

## Common Filter Presets

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

## Configuration

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

### Strict Mode

When `strict_mode=True`, FSPManager raises HTTP 400 errors for unknown filter/sort fields:

```python
# With strict_mode=True, this raises HTTP 400:
# GET /heroes/?field=unknown_field&operator=eq&value=test
# Error: "Unknown field 'unknown_field'. Available fields: age, id, name, secret_name"
```

## Convenience Methods

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

## Response model

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

## Development

This project uses uv as the package manager.

- Create env and sync deps:
```
uv venv
. .venv/bin/activate
uv sync --dev
```

- Run lint and format checks:
```
uv run ruff check .
uv run ruff format --check .
```

- Run tests:
```
uv run pytest -q
```

- Build the package:
```
uv build
```

## CI/CD and Releases

GitHub Actions workflows are included:
- CI (lint + tests) runs on pushes and PRs.
- Release: pushing a tag matching `v*.*.*` runs tests, builds, and publishes to PyPI using `PYPI_API_TOKEN` secret.

To release:
1. Update the version in `pyproject.toml`.
2. Push a tag, e.g. `git tag v0.1.1 && git push origin v0.1.1`.
3. Ensure the repository has `PYPI_API_TOKEN` secret set (an API token from PyPI).

## License

MIT License. See LICENSE.
