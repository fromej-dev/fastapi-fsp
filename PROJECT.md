# FastAPI Filtering, Sorting and Pagination

## pypi package name
fastapi-fsp

## pypi package version
0.2.1

## pypi package description
Package to implement filtering, sorting and pagination in FastAPI endpoints
using SQLModel

Endpoint Depends class that parses query parameters for filtering,
sorting and pagination. It performs all necessary checks.
Filtering is with query params: field, operator, value (support multiple)
Sorting is with query params: sort, order.
Pagination is with query params: page, per_page.

a request with query params:
http://localhost:8000/items?field=name&operator=eq&value=Deadpond&sort=name&order=asc&page=1&per_page=10

A response with data:

data: list of objects
meta: pagination info, filters, sort, etc.
links: pagination links

Example response:
```
{
  "data": [
    {
      "id": 1,
      "name": "Deadpond",
      "secret_name": "Dive Wilson",
      "age": 28
    },
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
      "sort": "name",
      "order": "asc"
    } 
  },
  "links": {
    "self": "http://127.0.0.1:8000/heroes/?field=age&operator=gt&value=20&page=1&limit=2",
    "first": "http://127.0.0.1:8000/heroes/?field=age&operator=gt&value=20&page=1&limit=2",
    "next": "http://127.0.0.1:8000/heroes/?field=age&operator=gt&value=20&page=2&limit=2",
    "prev": null
  }
}
```


Example usage in endpoint:

class Item(SQLModel, table=True):
    id: int = Field(default=None, primary_key=True)
    name: str
    secret_name: str | None = None
    age: int | None = None

@app.get("/items/", response_model=FSPResponse[Item])
def read_items(
    fsp: Depends(FSPManager(Item)),
):
    query = Item.select()
    return fsp.make_response(query)

also support async endpoints:

@app.get("/items/", response_model=FSPResponse[Item])
async def read_items(
    fsp: Depends(FSPManager(Item)),
):
    query = Item.select()
    return await fsp.make_response(query)

## pypi package dependencies
use the following dependencies:
- uv as package manager


- black as code formatter
- isort as import formatter
- flake8 as linter
- pytest as test runner
- pytest-cov as test coverage runner
- pytest-asyncio as async test runner
- pytest-mock as mock runner
- FastAPI
- SQLModel
- pydantic


## pypi package keywords
fastapi, SQLModel, orm, filtering, sorting, pagination

## open source on github
Add a license file

## Documentations
Add a README.md file with documentation
Add mkdocs documentation with mkdocs material theme
Add an implementation example

## full test coverage
Implement unit tests using pytest

## workflow to deploy to run all tests and package and publish to pypi
Github Actions workflow file to deploy to run all tests and package and publish to pypi
