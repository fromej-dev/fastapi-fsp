"""Tests for tokenized multi-column search (search_mode=token|phrase)."""

from typing import Optional

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from fastapi_fsp.fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse
from fastapi_fsp.presets import CommonFilters
from sqlalchemy import StaticPool, create_engine
from sqlmodel import Field, Session, SQLModel, select

from tests.main import Hero

# --- Address model and dedicated app ---


class Address(SQLModel, table=True):
    __tablename__ = "address"

    id: Optional[int] = Field(default=None, primary_key=True)
    city: str
    address: str
    house_nr: str
    house_nr_suffix: Optional[str] = Field(default=None)
    box: Optional[str] = Field(default=None)
    zip_code: str


def get_address_session():
    raise RuntimeError("Should be overridden in tests")


address_app = FastAPI()


@address_app.get("/addresses/", response_model=PaginatedResponse)
def read_addresses(
    *,
    session: Session = Depends(get_address_session),
    fsp: FSPManager = Depends(FSPManager),
):
    return fsp.generate_response(select(Address), session)


# --- Fixtures ---


@pytest.fixture(name="address_engine")
def address_engine_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with engine.connect():
        yield engine
    engine.dispose()


@pytest.fixture(name="address_session")
def address_session_fixture(address_engine):
    with Session(address_engine) as session:
        yield session


@pytest.fixture(name="address_client")
def address_client_fixture(address_session):
    def override():
        return address_session

    address_app.dependency_overrides[get_address_session] = override
    client = TestClient(address_app)
    yield client
    address_app.dependency_overrides.clear()


@pytest.fixture(name="seed_addresses")
def seed_addresses_fixture(address_session):
    addresses = [
        Address(
            city="Vilvoorde",
            address="Medialaan",
            house_nr="32",
            zip_code="1800",
        ),
        Address(
            city="Vilvoorde",
            address="Kerkstraat",
            house_nr="5",
            zip_code="1800",
        ),
        Address(
            city="Brussel",
            address="Kerkstraat",
            house_nr="10",
            zip_code="1000",
        ),
        Address(
            city="Antwerpen",
            address="Medialaan",
            house_nr="1",
            zip_code="2000",
        ),
        Address(
            city="Gent",
            address="Hoogstraat",
            house_nr="2",
            house_nr_suffix="A",
            zip_code="9000",
        ),
        Address(
            city="Leuven",
            address="Stationsstraat",
            house_nr="44",
            zip_code="3000",
        ),
    ]
    address_session.add_all(addresses)
    address_session.commit()
    return addresses


@pytest.fixture(name="seed_large_dataset")
def seed_large_dataset_fixture(address_session):
    cities = ["Vilvoorde", "Brussel", "Antwerpen", "Gent", "Leuven", "Mechelen"]
    streets = ["Medialaan", "Kerkstraat", "Stationsstraat", "Hoogstraat", "Dorpstraat"]
    zips = {
        "Vilvoorde": "1800",
        "Brussel": "1000",
        "Antwerpen": "2000",
        "Gent": "9000",
        "Leuven": "3000",
        "Mechelen": "2800",
    }
    batch = []
    for city in cities:
        for street in streets:
            for nr in range(1, 36):
                batch.append(
                    Address(
                        city=city,
                        address=street,
                        house_nr=str(nr),
                        zip_code=zips[city],
                    )
                )
    address_session.add_all(batch)
    address_session.commit()
    return len(batch)  # 6 * 5 * 35 = 1050


# --- Helper to seed heroes ---


def seed_heroes(session: Session):
    session.add_all(
        [
            Hero(name="Deadpond", secret_name="Dive Wilson", age=28),
            Hero(name="Rusty-Man", secret_name="Tommy Sharp", age=48),
            Hero(name="ALPHA", secret_name="Alpha Secret", age=10),
            Hero(name="beta", secret_name="Beta Secret", age=20),
        ]
    )
    session.commit()


# --- Test classes ---


class TestTokenSearchIntegration:
    """Core tokenized search with Address model."""

    def test_token_search_address_and_city(self, address_client, seed_addresses):
        r = address_client.get(
            "/addresses/?search=medialaan vilvoorde&search_fields=city,address,house_nr"
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["city"] == "Vilvoorde"
        assert data[0]["address"] == "Medialaan"

    def test_token_search_address_and_house_nr(self, address_client, seed_addresses):
        r = address_client.get(
            "/addresses/?search=kerkstraat 5&search_fields=city,address,house_nr"
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["address"] == "Kerkstraat"
        assert data[0]["house_nr"] == "5"

    def test_token_search_partial_match(self, address_client, seed_addresses):
        r = address_client.get("/addresses/?search=media 32&search_fields=city,address,house_nr")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["address"] == "Medialaan"
        assert data[0]["house_nr"] == "32"

    def test_token_search_no_match(self, address_client, seed_addresses):
        r = address_client.get("/addresses/?search=kerkstraat brussel&search_fields=city,address")
        assert r.status_code == 200
        data = r.json()["data"]
        # Brussel + Kerkstraat exists as a combo
        assert len(data) == 1
        assert data[0]["city"] == "Brussel"
        assert data[0]["address"] == "Kerkstraat"

    def test_token_search_no_match_wrong_combo(self, address_client, seed_addresses):
        r = address_client.get("/addresses/?search=hoogstraat vilvoorde&search_fields=city,address")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 0

    def test_token_search_single_token(self, address_client, seed_addresses):
        r = address_client.get("/addresses/?search=vilvoorde&search_fields=city,address,house_nr")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 2  # Two addresses in Vilvoorde

    def test_phrase_mode_full_string(self, address_client, seed_addresses):
        r = address_client.get(
            "/addresses/?search=medialaan 32&search_fields=city,address,house_nr&search_mode=phrase"
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 0  # No single column contains "medialaan 32"

    def test_token_search_case_insensitive(self, address_client, seed_addresses):
        r = address_client.get(
            "/addresses/?search=VILVOORDE medialaan&search_fields=city,address,house_nr"
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["city"] == "Vilvoorde"
        assert data[0]["address"] == "Medialaan"


class TestTokenSearchWithHeroModel:
    """Tokenized search using the existing Hero model from conftest."""

    def test_token_search_name_and_secret(self, session, client):
        seed_heroes(session)
        r = client.get("/heroes/?search=dead wilson&search_fields=name,secret_name")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["name"] == "Deadpond"

    def test_token_search_default_is_token(self, session, client):
        seed_heroes(session)
        # No search_mode param — should use token mode
        r = client.get("/heroes/?search=dead wilson&search_fields=name,secret_name")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1  # token mode finds Deadpond

    def test_explicit_phrase_mode(self, session, client):
        seed_heroes(session)
        r = client.get(
            "/heroes/?search=dead wilson&search_fields=name,secret_name&search_mode=phrase"
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 0  # phrase "dead wilson" not in any single column

    def test_token_search_with_and_filters(self, session, client):
        seed_heroes(session)
        r = client.get(
            "/heroes/?search=secret&search_fields=secret_name&field=age&operator=gt&value=15"
        )
        assert r.status_code == 200
        data = r.json()["data"]
        names = {h["name"] for h in data}
        assert names == {"beta"}

    def test_token_search_with_pagination(self, session, client):
        seed_heroes(session)
        r = client.get("/heroes/?search=secret&search_fields=secret_name&page=1&per_page=1")
        assert r.status_code == 200
        js = r.json()
        assert len(js["data"]) == 1
        assert js["meta"]["pagination"]["total_items"] == 2

    def test_token_search_with_sorting(self, session, client):
        seed_heroes(session)
        r = client.get("/heroes/?search=secret&search_fields=secret_name&sort_by=name&order=asc")
        assert r.status_code == 200
        names = [h["name"] for h in r.json()["data"]]
        assert names == ["ALPHA", "beta"]

    def test_token_search_meta_shows_multiple_groups(self, session, client):
        seed_heroes(session)
        r = client.get("/heroes/?search=dead wilson&search_fields=name,secret_name")
        assert r.status_code == 200
        meta = r.json()["meta"]
        or_filters = meta["or_filters"]
        assert len(or_filters) == 2  # 2 tokens -> 2 groups
        # First group: "dead" across name,secret_name
        assert or_filters[0]["filters"][0]["value"] == "dead"
        assert or_filters[1]["filters"][0]["value"] == "wilson"


class TestTokenSearchEdgeCases:
    """Edge cases for search_mode parameter."""

    def test_invalid_search_mode_returns_400(self, session, client):
        seed_heroes(session)
        r = client.get("/heroes/?search=test&search_fields=name&search_mode=invalid")
        assert r.status_code == 400
        assert "Invalid search_mode" in r.json()["detail"]

    def test_whitespace_only_search_returns_all(self, session, client):
        seed_heroes(session)
        r = client.get("/heroes/?search=   &search_fields=name&search_mode=token")
        assert r.status_code == 200
        assert len(r.json()["data"]) == 4

    def test_search_mode_without_search_ignored(self, session, client):
        seed_heroes(session)
        r = client.get("/heroes/?search_mode=token")
        assert r.status_code == 200
        assert len(r.json()["data"]) == 4

    def test_single_word_token_mode_equals_phrase_mode(self, session, client):
        seed_heroes(session)
        r_token = client.get("/heroes/?search=dead&search_fields=name&search_mode=token")
        r_phrase = client.get("/heroes/?search=dead&search_fields=name&search_mode=phrase")
        assert r_token.status_code == 200
        assert r_phrase.status_code == 200
        assert len(r_token.json()["data"]) == len(r_phrase.json()["data"])


class TestTokenSearchLargeDataset:
    """Baseline tests with 1000+ rows."""

    def test_large_dataset_token_search_returns_correct_count(
        self, address_client, seed_large_dataset
    ):
        r = address_client.get(
            "/addresses/?search=medialaan vilvoorde"
            "&search_fields=city,address,house_nr&per_page=100"
        )
        assert r.status_code == 200
        total = r.json()["meta"]["pagination"]["total_items"]
        # Vilvoorde + Medialaan = 35 addresses
        assert total == 35

    def test_large_dataset_token_search_with_pagination(self, address_client, seed_large_dataset):
        r = address_client.get(
            "/addresses/?search=medialaan vilvoorde&search_fields=city,address,house_nr"
            "&page=1&per_page=10"
        )
        assert r.status_code == 200
        js = r.json()
        assert len(js["data"]) == 10
        assert js["meta"]["pagination"]["total_items"] == 35

    def test_large_dataset_three_token_search(self, address_client, seed_large_dataset):
        r = address_client.get(
            "/addresses/?search=medialaan 1 vilvoorde&search_fields=city,address,house_nr"
            "&per_page=100"
        )
        assert r.status_code == 200
        data = r.json()["data"]
        # "1" matches house_nr containing "1": 1, 10-19, 21, 31
        # Combined with Vilvoorde + Medialaan
        for row in data:
            assert row["city"] == "Vilvoorde"
            assert row["address"] == "Medialaan"
            assert "1" in row["house_nr"]

    def test_large_dataset_broad_vs_narrow_search(self, address_client, seed_large_dataset):
        r_broad = address_client.get(
            "/addresses/?search=vilvoorde&search_fields=city,address,house_nr&per_page=100"
        )
        r_narrow = address_client.get(
            "/addresses/?search=vilvoorde medialaan"
            "&search_fields=city,address,house_nr&per_page=100"
        )
        assert r_broad.status_code == 200
        assert r_narrow.status_code == 200
        broad_total = r_broad.json()["meta"]["pagination"]["total_items"]
        narrow_total = r_narrow.json()["meta"]["pagination"]["total_items"]
        assert broad_total > narrow_total

    def test_large_dataset_token_search_with_sorting(self, address_client, seed_large_dataset):
        r = address_client.get(
            "/addresses/?search=medialaan vilvoorde&search_fields=city,address,house_nr"
            "&sort_by=house_nr&order=asc&per_page=100"
        )
        assert r.status_code == 200
        data = r.json()["data"]
        house_nrs = [d["house_nr"] for d in data]
        assert house_nrs == sorted(house_nrs)


class TestMultiFieldSearchTokenize:
    """Tests for CommonFilters.multi_field_search() tokenize parameter."""

    def test_multi_field_search_tokenize_true(self):
        groups = CommonFilters.multi_field_search(
            fields=["name", "email"], term="john doe", tokenize=True
        )
        assert len(groups) == 2
        assert groups[0].filters[0].value == "john"
        assert groups[0].filters[1].value == "john"
        assert groups[1].filters[0].value == "doe"
        assert groups[1].filters[1].value == "doe"

    def test_multi_field_search_tokenize_false_default(self):
        groups = CommonFilters.multi_field_search(fields=["name", "email"], term="john doe")
        assert len(groups) == 1
        assert groups[0].filters[0].value == "john doe"

    def test_multi_field_search_tokenize_single_word(self):
        groups = CommonFilters.multi_field_search(fields=["name"], term="john", tokenize=True)
        assert len(groups) == 1
        assert groups[0].filters[0].value == "john"

    def test_multi_field_search_tokenize_with_starts_with(self):
        groups = CommonFilters.multi_field_search(
            fields=["name", "city"],
            term="jo br",
            match_type="starts_with",
            tokenize=True,
        )
        assert len(groups) == 2
        for group in groups:
            for f in group.filters:
                assert f.operator.value == "starts_with"
