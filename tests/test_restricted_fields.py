import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "query",
    [
        "field=password&operator=eq&value=x",
        "filters[0][field]=secret&filters[0][operator]=eq&filters[0][value]=x",
        "sort_by=password_hash&order=asc",
        "search=x&search_fields=name,password",
        "search=x&search_fields=name,secret&search_mode=phrase",
    ],
)
def test_restricted_fields_return_400(client: TestClient, query: str):
    r = client.get(f"/heroes/?{query}")
    assert r.status_code == 400
    assert "not allowed" in r.json()["detail"]
