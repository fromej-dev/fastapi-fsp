import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.testclient import TestClient

from tests.main_async import Hero

pytest_plugins = ("tests.conftest_async",)


async def _seed(async_engine: AsyncEngine):
    async with AsyncSession(async_engine, expire_on_commit=False) as session:
        session.add_all(
            [
                Hero(name="Deadpond", secret_name="Dive Wilson", age=None),
                Hero(name="Rusty-Man", secret_name="Tommy Sharp", age=48),
                Hero(name="ALPHA", secret_name="Alpha Secret", age=10),
                Hero(name="beta", secret_name="Beta Secret", age=20),
            ]
        )
        await session.commit()


def test_async_full_operator_coverage(async_engine: AsyncEngine, client_async: TestClient):
    asyncio.run(_seed(async_engine))

    client = client_async

    # Basic pagination
    r = client.get("/heroes_async/?page=1&per_page=2")
    assert r.status_code == 200
    js = r.json()
    assert len(js["data"]) == 2
    assert js["meta"]["pagination"]["total_items"] == 4
    assert js["links"]["self"].endswith("page=1&per_page=2")

    # eq / ne
    assert (
        client.get("/heroes_async/?field=name&operator=eq&value=Deadpond").json()["data"][0]["name"]
        == "Deadpond"
    )
    names_ne = [
        h["name"]
        for h in client.get("/heroes_async/?field=name&operator=ne&value=Deadpond").json()["data"]
    ]
    assert "Deadpond" not in names_ne

    # gt / gte / lt / lte on age
    assert set(
        [
            h["name"]
            for h in client.get("/heroes_async/?field=age&operator=gt&value=15").json()["data"]
        ]
    ) == {"beta", "Rusty-Man"}
    assert set(
        [
            h["name"]
            for h in client.get("/heroes_async/?field=age&operator=gte&value=20").json()["data"]
        ]
    ) == {"Rusty-Man", "beta"}
    assert [
        h["name"]
        for h in client.get("/heroes_async/?field=age&operator=lt&value=15").json()["data"]
    ] == ["ALPHA"]
    assert set(
        [
            h["name"]
            for h in client.get("/heroes_async/?field=age&operator=lte&value=20").json()["data"]
        ]
    ) == {"ALPHA", "beta"}

    # like / not_like (case-sensitive) on name
    assert [
        h["name"]
        for h in client.get("/heroes_async/?field=name&operator=like&value=A%").json()["data"]
    ] == ["ALPHA"]
    not_like_a = [
        h["name"]
        for h in client.get("/heroes_async/?field=name&operator=not_like&value=A%").json()["data"]
    ]
    assert "ALPHA" not in not_like_a

    # ilike / not_ilike (case-insensitive)
    assert set(
        [
            h["name"]
            for h in client.get("/heroes_async/?field=name&operator=ilike&value=a%").json()["data"]
        ]
    ) == {"ALPHA"}
    not_ilike_beta = [
        h["name"]
        for h in client.get("/heroes_async/?field=name&operator=not_ilike&value=%eta").json()[
            "data"
        ]
    ]
    assert "beta" not in not_ilike_beta

    # in / not_in
    in_names = client.get("/heroes_async/?field=name&operator=in&value=Deadpond,ALPHA").json()[
        "data"
    ]
    assert set([h["name"] for h in in_names]) == {"Deadpond", "ALPHA"}
    not_in_names = client.get(
        "/heroes_async/?field=name&operator=not_in&value=Deadpond,ALPHA"
    ).json()["data"]
    assert "Deadpond" not in [h["name"] for h in not_in_names]
    assert "ALPHA" not in [h["name"] for h in not_in_names]

    # between
    between_ages = [
        h["name"]
        for h in client.get("/heroes_async/?field=age&operator=between&value=15,48").json()["data"]
    ]
    assert set(between_ages) == {"beta", "Rusty-Man"}

    # is_null / is_not_null
    assert [
        h["name"]
        for h in client.get("/heroes_async/?field=age&operator=is_null&value=").json()["data"]
    ] == ["Deadpond"]
    assert set(
        [
            h["name"]
            for h in client.get("/heroes_async/?field=age&operator=is_not_null&value=").json()[
                "data"
            ]
        ]
    ) == {"ALPHA", "beta", "Rusty-Man"}

    # starts_with / ends_with / contains (case-insensitive behavior via ilike fallback)
    assert set(
        [
            h["name"]
            for h in client.get("/heroes_async/?field=name&operator=starts_with&value=a").json()[
                "data"
            ]
        ]
    ) == {"ALPHA"}
    assert set(
        [
            h["name"]
            for h in client.get("/heroes_async/?field=name&operator=ends_with&value=a").json()[
                "data"
            ]
        ]
    ) == {"ALPHA", "beta"}
    assert set(
        [
            h["name"]
            for h in client.get("/heroes_async/?field=name&operator=contains&value=us").json()[
                "data"
            ]
        ]
    ) == {"Rusty-Man"}

    # sort invalid column ignored
    js = client.get("/heroes_async/?sort_by=unknown&order=asc").json()
    assert js["meta"]["sort"] is not None  # request reflected

    # malformed between should not filter out anything
    names = [
        h["name"]
        for h in client.get("/heroes_async/?field=age&operator=between&value=10").json()["data"]
    ]
    assert set(names) == {"Deadpond", "Rusty-Man", "ALPHA", "beta"}

    # unknown field filter ignored
    names = [
        h["name"]
        for h in client.get("/heroes_async/?field=unknown&operator=eq&value=x").json()["data"]
    ]
    assert set(names) == {"Deadpond", "Rusty-Man", "ALPHA", "beta"}

    # pagination validation errors (422) and mismatched filter params (400)
    assert client.get("/heroes_async/?page=0").status_code == 422
    assert client.get("/heroes_async/?per_page=101").status_code == 422
    # mismatched: missing value
    resp = client.get("/heroes_async/?field=name&operator=eq")
    assert resp.status_code == 400
