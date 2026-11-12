"""Tests for per-route field allowlists (FSPConfig.allowed_fields and friends)."""

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from fastapi_fsp import FSPConfig, FSPManager
from fastapi_fsp.models import Filter, FilterOperator, OrFilterGroup, PaginatedResponse
from pydantic import computed_field
from sqlalchemy import StaticPool
from sqlmodel import Field, Session, SQLModel, create_engine, select


class Account(SQLModel, table=True):
    """Model with a column the API must never expose."""

    __tablename__ = "account_allowed_fields"

    id: int | None = Field(default=None, primary_key=True)
    email: str
    hashed_password: str
    is_admin: bool = False


class AccountPublic(SQLModel):
    """Response model: hides hashed_password and is_admin."""

    id: int
    email: str

    @computed_field
    @property
    def domain(self) -> str:
        return self.email.split("@")[-1]


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
SQLModel.metadata.create_all(engine, tables=[Account.__table__])


def get_session():
    with Session(engine) as session:
        yield session


app = FastAPI()


def _endpoint(config: FSPConfig | None):
    def read_accounts(
        session: Annotated[Session, Depends(get_session)],
        fsp: Annotated[FSPManager, Depends(FSPManager)],
    ):
        if config is not None:
            fsp.apply_config(config)
        # Server-side filter on a column outside the allowlist must keep working.
        fsp.with_filters([Filter(field="is_admin", operator=FilterOperator.EQ, value="false")])
        return fsp.generate_response(select(Account), session)

    return read_accounts


app.get("/open", response_model=PaginatedResponse[AccountPublic])(_endpoint(None))
app.get("/model", response_model=PaginatedResponse[AccountPublic])(
    _endpoint(FSPConfig(allowed_fields=AccountPublic))
)
app.get("/names", response_model=PaginatedResponse[AccountPublic])(
    _endpoint(FSPConfig(allowed_fields={"id", "email"}))
)
app.get("/per-kind", response_model=PaginatedResponse[AccountPublic])(
    _endpoint(
        FSPConfig(
            allowed_fields={"id", "email"},
            sortable_fields={"id"},
            searchable_fields={"email"},
        )
    )
)


@pytest.fixture(scope="module", autouse=True)
def seed():
    with Session(engine) as session:
        session.add_all(
            [
                Account(email="a@example.com", hashed_password="$2b$12$aaa"),
                Account(email="b@example.org", hashed_password="$argon2id$bbb"),
            ]
        )
        session.commit()
    yield
    with Session(engine) as session:
        for account in session.exec(select(Account)).all():
            session.delete(account)
        session.commit()


@pytest.fixture
def client():
    return TestClient(app)


LEAKY_QUERIES = [
    "field=hashed_password&operator=starts_with&value=$2b",
    "filters[0][field]=hashed_password&filters[0][operator]=starts_with&filters[0][value]=$2b",
    "field=email&operator=contains&value=a&field=hashed_password&operator=starts_with&value=$",
    "sort_by=hashed_password&order=desc",
    "search=argon&search_fields=hashed_password",
    "search=argon&search_fields=email,hashed_password&search_mode=phrase",
    "field=is_admin&operator=eq&value=true",
]


@pytest.mark.parametrize("query", LEAKY_QUERIES)
def test_default_behaviour_unchanged(client: TestClient, query: str):
    """Without an allowlist every model column stays reachable (backwards compatible)."""
    r = client.get(f"/open?{query}")
    assert r.status_code == 200


@pytest.mark.parametrize("path", ["/model", "/names", "/per-kind"])
@pytest.mark.parametrize("query", LEAKY_QUERIES)
def test_keys_outside_allowlist_return_400(client: TestClient, path: str, query: str):
    r = client.get(f"{path}?{query}")
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "is not allowed" in detail
    assert "Allowed fields:" in detail


def test_error_names_field_and_allowed_fields(client: TestClient):
    r = client.get("/names?sort_by=hashed_password")
    assert r.status_code == 400
    assert r.json()["detail"] == (
        "Sorting by 'hashed_password' is not allowed. Allowed fields: email, id"
    )


@pytest.mark.parametrize(
    "query, expected_emails",
    [
        ("field=email&operator=starts_with&value=a", ["a@example.com"]),
        ("sort_by=id&order=desc", ["b@example.org", "a@example.com"]),
        ("sort_by=email&order=desc", ["b@example.org", "a@example.com"]),
        ("search=example.org&search_fields=email", ["b@example.org"]),
        ("search=example.org&search_fields=email&search_mode=phrase", ["b@example.org"]),
    ],
)
def test_allowed_keys_still_work(client: TestClient, query: str, expected_emails: list[str]):
    r = client.get(f"/model?{query}")
    assert r.status_code == 200
    assert [d["email"] for d in r.json()["data"]] == expected_emails


def test_model_allowlist_includes_computed_fields():
    config = FSPConfig(allowed_fields=AccountPublic)
    assert config.allowed_fields == frozenset({"id", "email", "domain"})


@pytest.mark.parametrize(
    "query",
    [
        "sort_by=email",  # sortable_fields overrides allowed_fields
        "search=a&search_fields=id",  # searchable_fields overrides allowed_fields
    ],
)
def test_per_kind_lists_override_allowed_fields(client: TestClient, query: str):
    r = client.get(f"/per-kind?{query}")
    assert r.status_code == 400


def test_per_kind_lists_fall_back_to_allowed_fields(client: TestClient):
    r = client.get("/per-kind?field=email&operator=eq&value=a@example.com&sort_by=id")
    assert r.status_code == 200
    assert r.json()["meta"]["pagination"]["total_items"] == 1


def test_code_added_or_filters_and_sorting_are_not_checked():
    """Only keys that came from the request are checked against the allowlist."""
    probe = FastAPI()

    @probe.get("/accounts")
    def read_accounts(
        session: Annotated[Session, Depends(get_session)],
        fsp: Annotated[FSPManager, Depends(FSPManager)],
    ):
        fsp.apply_config(FSPConfig(allowed_fields=AccountPublic))
        fsp.with_or_filters(
            [
                OrFilterGroup(
                    filters=[Filter(field="is_admin", operator=FilterOperator.EQ, value="false")]
                )
            ]
        )
        return fsp.generate_response(select(Account), session)

    r = TestClient(probe).get("/accounts")
    assert r.status_code == 200
    assert r.json()["meta"]["pagination"]["total_items"] == 2


def test_apply_config_after_with_filters_does_not_check_code_filters():
    probe = FastAPI()

    @probe.get("/accounts")
    def read_accounts(
        session: Annotated[Session, Depends(get_session)],
        fsp: Annotated[FSPManager, Depends(FSPManager)],
    ):
        fsp.with_filters([Filter(field="is_admin", operator=FilterOperator.EQ, value="false")])
        fsp.apply_config(FSPConfig(allowed_fields={"id", "email"}))
        return fsp.generate_response(select(Account), session)

    client = TestClient(probe)
    assert client.get("/accounts").status_code == 200
    assert client.get("/accounts?field=is_admin&operator=eq&value=true").status_code == 400


@pytest.mark.parametrize(
    "kwargs",
    [
        {"allowed_fields": "email"},
        {"sortable_fields": "email"},
        {"filterable_fields": [1]},
    ],
)
def test_invalid_allowlist_values_raise(kwargs):
    with pytest.raises(ValueError):
        FSPConfig(**kwargs)


def test_empty_allowlist_refuses_everything():
    probe = FastAPI()

    @probe.get("/accounts")
    def read_accounts(
        session: Annotated[Session, Depends(get_session)],
        fsp: Annotated[FSPManager, Depends(FSPManager)],
    ):
        fsp.apply_config(FSPConfig(allowed_fields=set()))
        return fsp.generate_response(select(Account), session)

    r = TestClient(probe).get("/accounts?sort_by=id")
    assert r.status_code == 400
    assert r.json()["detail"] == "Sorting by 'id' is not allowed. Allowed fields: (none)"
    assert TestClient(probe).get("/accounts").status_code == 200
