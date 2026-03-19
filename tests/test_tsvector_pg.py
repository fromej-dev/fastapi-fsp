"""Integration tests for tsvector search backend against real PostgreSQL.

These tests require a running PostgreSQL instance. They are skipped automatically
when DATABASE_URL is not set or PostgreSQL is not available.

Run locally:
    DATABASE_URL=postgresql://user:pass@localhost:5432/testdb pytest tests/test_tsvector_pg.py -v

CI provides PostgreSQL via a service container and sets DATABASE_URL automatically.
"""

import os
from typing import Optional

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from fastapi_fsp.config import FSPConfig
from fastapi_fsp.filters import FilterEngine
from fastapi_fsp.fsp import FSPManager
from fastapi_fsp.models import (
    Filter,
    FilterOperator,
    OrFilterGroup,
    PaginatedResponse,
    SearchBackend,
)
from sqlmodel import Field, Session, SQLModel, create_engine, select

DATABASE_URL = os.environ.get("DATABASE_URL", "")
# Default to psycopg3 (v3) for postgresql:// URLs
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

requires_pg = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="Requires DATABASE_URL pointing to PostgreSQL",
)


# --- Model ---


class PgAddress(SQLModel, table=True):
    __tablename__ = "pg_address"

    id: Optional[int] = Field(default=None, primary_key=True)
    city: str
    address: str
    house_nr: str
    house_nr_suffix: Optional[str] = Field(default=None)
    zip_code: str


# --- Helper ---


def _make_token_groups(tokens, fields):
    return [
        OrFilterGroup(
            filters=[Filter(field=f, operator=FilterOperator.CONTAINS, value=token) for f in fields]
        )
        for token in tokens
    ]


# --- Fixtures ---


@pytest.fixture(scope="module")
def pg_engine():
    if not DATABASE_URL.startswith("postgresql"):
        pytest.skip("No PostgreSQL DATABASE_URL")
    engine = create_engine(DATABASE_URL)
    SQLModel.metadata.create_all(engine)
    yield engine
    # Clean up table after module
    PgAddress.__table__.drop(engine, checkfirst=True)
    engine.dispose()


@pytest.fixture(scope="module")
def pg_seed(pg_engine):
    with Session(pg_engine) as session:
        # Clear any leftover data
        session.query(PgAddress).delete()
        session.add_all(
            [
                PgAddress(city="Vilvoorde", address="Medialaan", house_nr="32", zip_code="1800"),
                PgAddress(city="Vilvoorde", address="Kerkstraat", house_nr="5", zip_code="1800"),
                PgAddress(city="Brussel", address="Kerkstraat", house_nr="10", zip_code="1000"),
                PgAddress(city="Antwerpen", address="Medialaan", house_nr="1", zip_code="2000"),
                PgAddress(city="Gent", address="Hoogstraat", house_nr="2", zip_code="9000"),
                PgAddress(city="Leuven", address="Stationsstraat", house_nr="44", zip_code="3000"),
            ]
        )
        session.commit()


@pytest.fixture
def pg_session(pg_engine, pg_seed):
    with Session(pg_engine) as session:
        yield session


@pytest.fixture
def pg_client(pg_engine, pg_seed):
    app = FastAPI()

    def get_session():
        with Session(pg_engine) as session:
            yield session

    @app.get("/addresses/", response_model=PaginatedResponse)
    def read_addresses(
        *,
        session: Session = Depends(get_session),
        fsp: FSPManager = Depends(FSPManager),
    ):
        config = FSPConfig(search_backend=SearchBackend.TSVECTOR)
        fsp.apply_config(config)
        return fsp.generate_response(select(PgAddress), session)

    client = TestClient(app)
    yield client


# --- Unit-level tests: FilterEngine with real PG ---


@requires_pg
class TestTsvectorFilterEngine:
    """Test FilterEngine tsvector methods against real PostgreSQL."""

    def test_tsvector_single_token(self, pg_session):
        groups = _make_token_groups(["vilvoorde"], ["city", "address", "house_nr"])
        fe = FilterEngine()
        query = select(PgAddress)
        result = fe.apply_search_optimized(query, query.selected_columns, groups, "tsvector")
        rows = pg_session.exec(result).all()
        assert len(rows) == 2
        assert all(r.city == "Vilvoorde" for r in rows)

    def test_tsvector_two_tokens(self, pg_session):
        groups = _make_token_groups(["media", "vilvoorde"], ["city", "address", "house_nr"])
        fe = FilterEngine()
        query = select(PgAddress)
        result = fe.apply_search_optimized(query, query.selected_columns, groups, "tsvector")
        rows = pg_session.exec(result).all()
        assert len(rows) == 1
        assert rows[0].city == "Vilvoorde"
        assert rows[0].address == "Medialaan"

    def test_tsvector_three_tokens(self, pg_session):
        groups = _make_token_groups(["media", "32", "vilvoorde"], ["city", "address", "house_nr"])
        fe = FilterEngine()
        query = select(PgAddress)
        result = fe.apply_search_optimized(query, query.selected_columns, groups, "tsvector")
        rows = pg_session.exec(result).all()
        assert len(rows) == 1
        assert rows[0].house_nr == "32"

    def test_tsvector_prefix_matching(self, pg_session):
        """tsvector :* matches start-of-word: 'media' matches 'Medialaan'."""
        groups = _make_token_groups(["media"], ["address"])
        fe = FilterEngine()
        query = select(PgAddress)
        result = fe.apply_search_optimized(query, query.selected_columns, groups, "tsvector")
        rows = pg_session.exec(result).all()
        assert len(rows) == 2  # Vilvoorde + Antwerpen both have Medialaan
        for r in rows:
            assert r.address == "Medialaan"

    def test_tsvector_prefix_no_infix_match(self, pg_session):
        """tsvector prefix does NOT match mid-word: 'laan' should NOT match 'Medialaan'."""
        groups = _make_token_groups(["laan"], ["address"])
        fe = FilterEngine()
        query = select(PgAddress)
        result = fe.apply_search_optimized(query, query.selected_columns, groups, "tsvector")
        rows = pg_session.exec(result).all()
        assert len(rows) == 0

    def test_tsvector_case_insensitive(self, pg_session):
        groups = _make_token_groups(["VILVOORDE", "MEDIA"], ["city", "address"])
        fe = FilterEngine()
        query = select(PgAddress)
        result = fe.apply_search_optimized(query, query.selected_columns, groups, "tsvector")
        rows = pg_session.exec(result).all()
        assert len(rows) == 1
        assert rows[0].city == "Vilvoorde"

    def test_tsvector_no_match(self, pg_session):
        groups = _make_token_groups(["nonexistent"], ["city", "address"])
        fe = FilterEngine()
        query = select(PgAddress)
        result = fe.apply_search_optimized(query, query.selected_columns, groups, "tsvector")
        rows = pg_session.exec(result).all()
        assert len(rows) == 0

    def test_tsvector_numeric_token(self, pg_session):
        """Numbers work with 'simple' config (no stop-word removal)."""
        groups = _make_token_groups(["32"], ["house_nr"])
        fe = FilterEngine()
        query = select(PgAddress)
        result = fe.apply_search_optimized(query, query.selected_columns, groups, "tsvector")
        rows = pg_session.exec(result).all()
        assert len(rows) == 1
        assert rows[0].house_nr == "32"

    def test_tsvector_special_char_sanitized(self, pg_session):
        """Tokens with tsquery special chars are sanitized, query doesn't error."""
        groups = _make_token_groups(["vilvoorde&|!"], ["city"])
        fe = FilterEngine()
        query = select(PgAddress)
        result = fe.apply_search_optimized(query, query.selected_columns, groups, "tsvector")
        rows = pg_session.exec(result).all()
        assert len(rows) == 2  # sanitized to "vilvoorde"


# --- Full pipeline tests via HTTP client ---


@requires_pg
class TestTsvectorHttpIntegration:
    """Test tsvector search through the full FSPManager HTTP pipeline."""

    def test_search_two_tokens(self, pg_client):
        r = pg_client.get(
            "/addresses/?search=medialaan vilvoorde&search_fields=city,address,house_nr"
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["city"] == "Vilvoorde"
        assert data[0]["address"] == "Medialaan"

    def test_search_single_token(self, pg_client):
        r = pg_client.get("/addresses/?search=vilvoorde&search_fields=city,address,house_nr")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 2

    def test_search_prefix_matching(self, pg_client):
        """'media' prefix-matches 'Medialaan' via tsvector."""
        r = pg_client.get("/addresses/?search=media&search_fields=address")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 2
        assert all(d["address"] == "Medialaan" for d in data)

    def test_search_no_infix_match(self, pg_client):
        """'laan' does NOT match 'Medialaan' in tsvector (prefix-only)."""
        r = pg_client.get("/addresses/?search=laan&search_fields=address")
        assert r.status_code == 200
        assert len(r.json()["data"]) == 0

    def test_search_with_pagination(self, pg_client):
        r = pg_client.get("/addresses/?search=kerk&search_fields=address&page=1&per_page=1")
        assert r.status_code == 200
        js = r.json()
        assert len(js["data"]) == 1
        assert js["meta"]["pagination"]["total_items"] == 2

    def test_search_no_match(self, pg_client):
        r = pg_client.get("/addresses/?search=nonexistent&search_fields=city,address")
        assert r.status_code == 200
        assert len(r.json()["data"]) == 0

    def test_search_three_tokens_narrow(self, pg_client):
        r = pg_client.get(
            "/addresses/?search=media 32 vilvoorde&search_fields=city,address,house_nr"
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["house_nr"] == "32"

    def test_phrase_mode_bypasses_tsvector(self, pg_client):
        """Phrase mode (space in value) should fall back to ILIKE, not tsvector."""
        r = pg_client.get(
            "/addresses/?search=medialaan 32&search_fields=city,address,house_nr&search_mode=phrase"
        )
        assert r.status_code == 200
        data = r.json()["data"]
        # Phrase "medialaan 32" won't match any single column via ILIKE either
        assert len(data) == 0

    def test_meta_shows_or_filters(self, pg_client):
        r = pg_client.get("/addresses/?search=media vilvoorde&search_fields=city,address")
        assert r.status_code == 200
        meta = r.json()["meta"]
        assert meta["or_filters"] is not None
        assert len(meta["or_filters"]) == 2


# --- Trigram on real PG for comparison ---


@requires_pg
class TestTrigramPgIntegration:
    """Test trigram search on real PostgreSQL for substring match comparison."""

    def test_trigram_infix_match(self, pg_session):
        """Trigram preserves full substring: 'laan' matches 'Medialaan'."""
        groups = _make_token_groups(["laan"], ["address"])
        fe = FilterEngine()
        query = select(PgAddress)
        result = fe.apply_search_optimized(query, query.selected_columns, groups, "trigram")
        rows = pg_session.exec(result).all()
        assert len(rows) == 2  # Both Medialaan addresses
        assert all(r.address == "Medialaan" for r in rows)

    def test_trigram_vs_tsvector_infix_difference(self, pg_session):
        """Demonstrates the key tradeoff: trigram finds substrings, tsvector doesn't."""
        groups_laan = _make_token_groups(["laan"], ["address"])
        fe = FilterEngine()
        query = select(PgAddress)

        tsvector_result = fe.apply_search_optimized(
            query, query.selected_columns, groups_laan, "tsvector"
        )
        trigram_result = fe.apply_search_optimized(
            query, query.selected_columns, groups_laan, "trigram"
        )

        tsvector_rows = pg_session.exec(tsvector_result).all()
        trigram_rows = pg_session.exec(trigram_result).all()

        assert len(tsvector_rows) == 0  # Prefix-only, no infix
        assert len(trigram_rows) == 2  # Full substring match

    def test_trigram_two_tokens(self, pg_session):
        groups = _make_token_groups(["media", "vilvoorde"], ["city", "address"])
        fe = FilterEngine()
        query = select(PgAddress)
        result = fe.apply_search_optimized(query, query.selected_columns, groups, "trigram")
        rows = pg_session.exec(result).all()
        assert len(rows) == 1
        assert rows[0].city == "Vilvoorde"
        assert rows[0].address == "Medialaan"
