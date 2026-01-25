# FastAPI Filtering, Sorting and Pagination

## pypi package name
fastapi-fsp

## pypi package version
0.3.0

## pypi package description
Filter, Sort, and Paginate (FSP) utilities for FastAPI + SQLModel.

A FastAPI dependency that parses query parameters for filtering, sorting, and pagination. Includes:

- **Filtering**: Rich operators (eq, ne, lt, lte, gt, gte, in, between, like/ilike, null checks, contains/starts_with/ends_with)
- **Sorting**: By field (asc/desc)
- **Pagination**: With page/per_page and HATEOAS links
- **FilterBuilder**: Fluent API for building filters programmatically
- **FSPConfig**: Centralized configuration with validation
- **CommonFilters**: Pre-built filter presets for common patterns
- **Strict Mode**: Helpful error messages for unknown fields

### Example Request
```
GET /items?field=name&operator=eq&value=Deadpond&sort=name&order=asc&page=1&per_page=10
```

### Example Response
```json
{
  "data": [
    {
      "id": 1,
      "name": "Deadpond",
      "secret_name": "Dive Wilson",
      "age": 28
    }
  ],
  "meta": {
    "pagination": {
      "total_items": 1,
      "per_page": 10,
      "current_page": 1,
      "total_pages": 1
    },
    "filters": [
      {
        "field": "name",
        "operator": "eq",
        "value": "Deadpond"
      }
    ],
    "sort": {
      "sort_by": "name",
      "order": "asc"
    }
  },
  "links": {
    "self": "/items/?page=1&per_page=10",
    "first": "/items/?page=1&per_page=10",
    "next": null,
    "prev": null,
    "last": "/items/?page=1&per_page=10"
  }
}
```

## Basic Usage

```python
from fastapi import Depends, FastAPI
from sqlmodel import Session, select

from fastapi_fsp import FSPManager, PaginatedResponse

@app.get("/items/", response_model=PaginatedResponse[Item])
def read_items(
    session: Session = Depends(get_session),
    fsp: FSPManager = Depends(FSPManager)
):
    query = select(Item)
    return fsp.generate_response(query, session)
```

## FilterBuilder API (v0.3.0)

```python
from fastapi_fsp import FilterBuilder

filters = (
    FilterBuilder()
    .where("age").gte(30)
    .where("city").eq("Chicago")
    .where("active").eq(True)
    .build()
)
```

## CommonFilters Presets (v0.3.0)

```python
from fastapi_fsp import CommonFilters

# Active records
filters = CommonFilters.active()

# Recent records
filters = CommonFilters.recent(days=7)

# Combine presets
filters = CommonFilters.active() + CommonFilters.recent(days=30)
```

## FSPConfig (v0.3.0)

```python
from fastapi_fsp import FSPConfig, FSPPresets

config = FSPConfig(
    max_per_page=50,
    strict_mode=True,
)

# Or use presets
config = FSPPresets.strict()
config = FSPPresets.high_volume(max_per_page=500)
```

## Convenience Methods (v0.3.0)

```python
# Simple model query
return fsp.from_model(Item, session)

# Method chaining
return (
    fsp
    .with_filters(CommonFilters.active())
    .apply_config(FSPPresets.strict())
    .generate_response(select(Item), session)
)
```

## Async Support

```python
@app.get("/items/", response_model=PaginatedResponse[Item])
async def read_items(
    session: AsyncSession = Depends(get_session),
    fsp: FSPManager = Depends(FSPManager)
):
    return await fsp.from_model_async(Item, session)
```

## pypi package dependencies
- uv as package manager
- ruff as linter/formatter
- pytest as test runner
- pytest-cov for coverage
- pytest-asyncio for async tests
- FastAPI
- SQLModel
- pydantic
- python-dateutil

## pypi package keywords
fastapi, SQLModel, orm, filtering, sorting, pagination, api, rest

## Open Source
MIT License

## Documentation
- README.md with comprehensive documentation
- OPTIMIZATION_ANALYSIS.md with performance analysis
- RECOMMENDATIONS.md with implementation status

## Test Coverage
- 162 tests
- 93% coverage
- Unit tests for all components
- Integration tests for full pipeline
- Benchmark CI workflow

## CI/CD
- GitHub Actions for CI (lint + tests)
- GitHub Actions for benchmarks
- Release workflow for PyPI publishing
