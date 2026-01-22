"""Tests for strict mode in FSPManager."""

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import StaticPool
from sqlmodel import Field, Session, SQLModel, create_engine, select

from fastapi_fsp.fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse


class HeroStrict(SQLModel, table=True):
    """Hero model for testing strict mode."""

    __tablename__ = "hero_strict"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    secret_name: str
    age: int | None = Field(default=None, index=True)


class HeroStrictPublic(SQLModel):
    """Public hero model for strict mode tests."""

    id: int
    name: str
    secret_name: str
    age: int | None


@pytest.fixture(name="session", scope="function")
def session_fixture():
    """Create a test database session."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # Add test data
        heroes = [
            HeroStrict(name="Deadpond", secret_name="Dive Wilson", age=30),
            HeroStrict(name="Spider-Boy", secret_name="Pedro Parqueador", age=25),
            HeroStrict(name="Rusty-Man", secret_name="Tommy Sharp", age=48),
        ]
        session.add_all(heroes)
        session.commit()
        yield session
    engine.dispose()


def test_strict_mode_unknown_filter_field(session):
    """Test that strict mode raises error for unknown filter field."""
    app = FastAPI()

    def get_session():
        yield session

    @app.get("/heroes/", response_model=PaginatedResponse[HeroStrictPublic])
    def read_heroes(
        *,
        session: Session = Depends(get_session),
        fsp: FSPManager = Depends(FSPManager),
    ):
        # Enable strict mode by passing it to the dependency
        fsp.strict_mode = True
        query = select(HeroStrict)
        return fsp.generate_response(query, session)

    client = TestClient(app)

    # Unknown field should raise 400 error in strict mode
    response = client.get("/heroes/?field=unknown_field&operator=eq&value=test")
    assert response.status_code == 400
    assert "unknown_field" in response.json()["detail"].lower()
    assert "available fields" in response.json()["detail"].lower()


def test_strict_mode_unknown_sort_field(session):
    """Test that strict mode raises error for unknown sort field."""
    app = FastAPI()

    def get_session():
        yield session

    @app.get("/heroes/", response_model=PaginatedResponse[HeroStrictPublic])
    def read_heroes(
        *,
        session: Session = Depends(get_session),
        fsp: FSPManager = Depends(FSPManager),
    ):
        fsp.strict_mode = True
        query = select(HeroStrict)
        return fsp.generate_response(query, session)

    client = TestClient(app)

    # Unknown sort field should raise 400 error in strict mode
    response = client.get("/heroes/?sort_by=unknown_field&order=asc")
    assert response.status_code == 400
    assert "unknown_field" in response.json()["detail"].lower()
    assert "available fields" in response.json()["detail"].lower()


def test_non_strict_mode_unknown_filter_field(session):
    """Test that non-strict mode silently ignores unknown filter field."""
    app = FastAPI()

    def get_session():
        yield session

    @app.get("/heroes/", response_model=PaginatedResponse[HeroStrictPublic])
    def read_heroes(
        *,
        session: Session = Depends(get_session),
        fsp: FSPManager = Depends(FSPManager),
    ):
        # Non-strict mode is default
        query = select(HeroStrict)
        return fsp.generate_response(query, session)

    client = TestClient(app)

    # Unknown field should be silently ignored in non-strict mode
    response = client.get("/heroes/?field=unknown_field&operator=eq&value=test")
    assert response.status_code == 200
    # Should return all heroes since filter is ignored
    assert len(response.json()["data"]) == 3


def test_non_strict_mode_unknown_sort_field(session):
    """Test that non-strict mode silently ignores unknown sort field."""
    app = FastAPI()

    def get_session():
        yield session

    @app.get("/heroes/", response_model=PaginatedResponse[HeroStrictPublic])
    def read_heroes(
        *,
        session: Session = Depends(get_session),
        fsp: FSPManager = Depends(FSPManager),
    ):
        query = select(HeroStrict)
        return fsp.generate_response(query, session)

    client = TestClient(app)

    # Unknown sort field should be silently ignored in non-strict mode
    response = client.get("/heroes/?sort_by=unknown_field&order=asc")
    assert response.status_code == 200
    assert len(response.json()["data"]) == 3


def test_strict_mode_valid_filter_field(session):
    """Test that strict mode works correctly with valid filter field."""
    app = FastAPI()

    def get_session():
        yield session

    @app.get("/heroes/", response_model=PaginatedResponse[HeroStrictPublic])
    def read_heroes(
        *,
        session: Session = Depends(get_session),
        fsp: FSPManager = Depends(FSPManager),
    ):
        fsp.strict_mode = True
        query = select(HeroStrict)
        return fsp.generate_response(query, session)

    client = TestClient(app)

    # Valid field should work in strict mode
    response = client.get("/heroes/?field=age&operator=gte&value=30")
    assert response.status_code == 200
    data = response.json()["data"]
    # Should return heroes with age >= 30
    assert len(data) == 2
    assert all(hero["age"] >= 30 for hero in data)


def test_strict_mode_valid_sort_field(session):
    """Test that strict mode works correctly with valid sort field."""
    app = FastAPI()

    def get_session():
        yield session

    @app.get("/heroes/", response_model=PaginatedResponse[HeroStrictPublic])
    def read_heroes(
        *,
        session: Session = Depends(get_session),
        fsp: FSPManager = Depends(FSPManager),
    ):
        fsp.strict_mode = True
        query = select(HeroStrict)
        return fsp.generate_response(query, session)

    client = TestClient(app)

    # Valid sort field should work in strict mode
    response = client.get("/heroes/?sort_by=age&order=asc")
    assert response.status_code == 200
    data = response.json()["data"]
    ages = [hero["age"] for hero in data]
    assert ages == sorted(ages)


def test_strict_mode_multiple_filters_with_one_invalid(session):
    """Test strict mode with multiple filters where one is invalid."""
    app = FastAPI()

    def get_session():
        yield session

    @app.get("/heroes/", response_model=PaginatedResponse[HeroStrictPublic])
    def read_heroes(
        *,
        session: Session = Depends(get_session),
        fsp: FSPManager = Depends(FSPManager),
    ):
        fsp.strict_mode = True
        query = select(HeroStrict)
        return fsp.generate_response(query, session)

    client = TestClient(app)

    # First filter valid, second filter invalid
    response = client.get(
        "/heroes/?field=age&operator=gte&value=30&field=invalid&operator=eq&value=test"
    )
    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()
