"""Tests for FSPManager.depends(), field allowlists and the configurable denylist."""

import warnings
from typing import Annotated, Optional
from unittest.mock import Mock

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from fastapi_fsp import DEFAULT_DENIED_FIELDS, FSPConfig, FSPManager, PaginatedResponse
from fastapi_fsp.models import Filter, FilterOperator, PaginationQuery, SortingOrder, SortingQuery
from sqlalchemy import StaticPool, create_engine
from sqlmodel import Field, Session, SQLModel, select


class Account(SQLModel, table=True):
    __tablename__ = "config_dep_account"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str
    api_key: str
    password: str = "x"


class AccountPublic(SQLModel):
    id: int
    name: str
    email: str


@pytest.fixture(name="engine")
def engine_fixture():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine, tables=[Account.__table__])
    with Session(engine) as session:
        for i in range(30):
            session.add(Account(name=f"user{i:02d}", email=f"u{i}@example.com", api_key=f"key{i}"))
        session.commit()
    yield engine
    engine.dispose()


def make_client(engine, config: Optional[FSPConfig] = None, legacy: bool = False) -> TestClient:
    app = FastAPI()

    def get_session():
        with Session(engine) as session:
            yield session

    if legacy:

        @app.get("/accounts", response_model=PaginatedResponse)
        def legacy_accounts(
            session: Annotated[Session, Depends(get_session)],
            fsp: Annotated[FSPManager, Depends(FSPManager)],
        ):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                fsp.apply_config(config)
            return fsp.generate_response(select(Account), session)

    else:
        dep = FSPManager.depends(config) if config is not None else FSPManager

        @app.get("/accounts", response_model=PaginatedResponse)
        def accounts(
            session: Annotated[Session, Depends(get_session)],
            fsp: Annotated[FSPManager, Depends(dep)],
        ):
            return fsp.generate_response(select(Account), session)

    return TestClient(app)


def per_page_schema(client: TestClient) -> dict:
    params = client.app.openapi()["paths"]["/accounts"]["get"]["parameters"]
    return {p["name"]: p for p in params}


# --- #21: config wired into parsing ---


class TestDependsPagination:
    def test_defaults_come_from_config(self, engine):
        client = make_client(engine, FSPConfig(default_per_page=25, max_per_page=500))
        body = client.get("/accounts").json()
        assert body["meta"]["pagination"]["per_page"] == 25
        assert len(body["data"]) == 25

    def test_max_per_page_above_100_is_accepted(self, engine):
        client = make_client(engine, FSPConfig(max_per_page=500))
        r = client.get("/accounts?per_page=300")
        assert r.status_code == 200
        assert r.json()["meta"]["pagination"]["per_page"] == 300

    def test_per_page_above_max_is_rejected(self, engine):
        client = make_client(engine, FSPConfig(max_per_page=20))
        assert client.get("/accounts?per_page=21").status_code == 422

    def test_per_page_below_min_is_rejected(self, engine):
        client = make_client(engine, FSPConfig(min_per_page=5))
        assert client.get("/accounts?per_page=4").status_code == 422

    def test_default_page(self, engine):
        client = make_client(engine, FSPConfig(default_page=2, default_per_page=10))
        assert client.get("/accounts").json()["meta"]["pagination"]["current_page"] == 2

    def test_max_page_enforced_without_deep_pagination(self, engine):
        config = FSPConfig(max_page=3, allow_deep_pagination=False)
        client = make_client(engine, config)
        assert client.get("/accounts?page=3").status_code == 200
        assert client.get("/accounts?page=4").status_code == 422

    def test_max_page_ignored_with_deep_pagination(self, engine):
        client = make_client(engine, FSPConfig(max_page=1))
        assert client.get("/accounts?page=2").status_code == 200

    def test_openapi_reflects_config(self, engine):
        client = make_client(
            engine, FSPConfig(max_per_page=500, default_per_page=25, min_per_page=2)
        )
        params = per_page_schema(client)
        schema = params["per_page"]["schema"]
        assert schema["maximum"] == 500
        assert schema["minimum"] == 2
        assert schema["default"] == 25

    def test_openapi_has_no_internal_params(self, engine):
        params = per_page_schema(make_client(engine, FSPConfig()))
        assert "strict_mode" not in params
        assert "use_window_function" not in params

    def test_plain_depends_keeps_defaults(self, engine):
        client = make_client(engine)
        params = per_page_schema(client)
        assert params["per_page"]["schema"]["maximum"] == 100
        assert params["per_page"]["schema"]["default"] == 10
        assert client.get("/accounts?per_page=101").status_code == 422


class TestDependsSettings:
    def _build(self, config: FSPConfig, query: str = "") -> FSPManager:
        app = FastAPI()
        captured = {}

        @app.get("/x")
        def endpoint(fsp: Annotated[FSPManager, Depends(FSPManager.depends(config))]):
            captured["fsp"] = fsp
            return {}

        TestClient(app).get(f"/x{query}")
        return captured["fsp"]

    def test_strict_mode_from_config(self):
        assert self._build(FSPConfig(strict_mode=True)).strict_mode is True
        assert self._build(FSPConfig()).strict_mode is False

    def test_search_backend_from_config(self):
        from fastapi_fsp import SearchBackend

        fsp = self._build(FSPConfig(search_backend=SearchBackend.TRIGRAM))
        assert fsp._filter_engine.search_backend == "trigram"

    def test_max_search_tokens_from_config(self):
        fsp = self._build(FSPConfig(max_search_tokens=2), "?search=a+b+c+d&search_fields=name")
        assert len(fsp.or_filters) == 2

    def test_use_window_function_from_config(self):
        fsp = self._build(FSPConfig(use_window_function=False))
        assert fsp._pagination_engine.use_window_function is False

    def test_strict_mode_rejects_unknown_field(self, engine):
        client = make_client(engine, FSPConfig(strict_mode=True))
        assert client.get("/accounts?sort_by=nope").status_code == 400

    def test_depends_without_config(self, engine):
        app = FastAPI()

        @app.get("/x")
        def endpoint(fsp: Annotated[FSPManager, Depends(FSPManager.depends())]):
            return {"per_page": fsp.pagination.per_page}

        assert TestClient(app).get("/x").json() == {"per_page": 10}


class TestApplyConfigDeprecated:
    def _manager(self, **kwargs) -> FSPManager:
        request = Mock()
        request.query_params = {}
        return FSPManager(
            request=request,
            filters=kwargs.get("filters"),
            sorting=kwargs.get("sorting"),
            pagination=PaginationQuery(page=1, per_page=kwargs.get("per_page", 10)),
            or_filters=None,
        )

    def test_warns(self):
        with pytest.warns(DeprecationWarning, match="FSPManager.depends"):
            self._manager().apply_config(FSPConfig())

    def test_still_clamps_per_page(self):
        fsp = self._manager(per_page=80)
        with pytest.warns(DeprecationWarning):
            fsp.apply_config(FSPConfig(max_per_page=50))
        assert fsp.pagination.per_page == 50

    def test_enforces_allowlist(self):
        fsp = self._manager(sorting=SortingQuery(sort_by="email", order=SortingOrder.ASC))
        with pytest.warns(DeprecationWarning), pytest.raises(HTTPException) as exc:
            fsp.apply_config(FSPConfig(sortable_fields={"name"}))
        assert exc.value.status_code == 400

    def test_enforces_allowlist_over_http(self, engine):
        client = make_client(engine, FSPConfig(filterable_fields={"name"}), legacy=True)
        assert client.get("/accounts?field=email&operator=eq&value=x").status_code == 400
        assert client.get("/accounts?field=name&operator=eq&value=x").status_code == 200


# --- #20: allowlists and denylist ---


ALLOWLIST_CONFIG = FSPConfig(
    filterable_fields={"name", "email"},
    sortable_fields={"name"},
    searchable_fields={"name"},
)


class TestAllowlists:
    @pytest.mark.parametrize(
        "query",
        [
            "field=name&operator=eq&value=user01",
            "filters[0][field]=email&filters[0][operator]=contains&filters[0][value]=u1",
            "sort_by=name&order=desc",
            "search=user&search_fields=name",
            "search=user&search_fields=name&search_mode=phrase",
        ],
    )
    def test_allowed(self, engine, query):
        assert make_client(engine, ALLOWLIST_CONFIG).get(f"/accounts?{query}").status_code == 200

    @pytest.mark.parametrize(
        "query,word",
        [
            ("field=api_key&operator=starts_with&value=key", "Filtering by 'api_key'"),
            ("field=name&operator=eq&value=a&field=id&operator=eq&value=1", "Filtering by 'id'"),
            (
                "filters[0][field]=api_key&filters[0][operator]=eq&filters[0][value]=k",
                "Filtering by 'api_key'",
            ),
            ("sort_by=email", "Sorting by 'email'"),
            ("search=x&search_fields=name,email", "Searching by 'email'"),
            ("search=x&search_fields=api_key&search_mode=phrase", "Searching by 'api_key'"),
        ],
    )
    def test_disallowed(self, engine, query, word):
        r = make_client(engine, ALLOWLIST_CONFIG).get(f"/accounts?{query}")
        assert r.status_code == 400
        assert word in r.json()["detail"]
        assert "not allowed" in r.json()["detail"]

    def test_allowlist_overrides_denylist(self, engine):
        client = make_client(engine, FSPConfig(filterable_fields={"password"}))
        assert client.get("/accounts?field=password&operator=eq&value=x").status_code == 200
        # Sorting has no allowlist, so the denylist still applies to it.
        assert client.get("/accounts?sort_by=password").status_code == 400

    def test_empty_allowlist_blocks_everything(self, engine):
        client = make_client(engine, FSPConfig(sortable_fields=()))
        assert client.get("/accounts?sort_by=name").status_code == 400
        assert client.get("/accounts").status_code == 200

    def test_server_side_filters_are_not_checked(self, engine):
        app = FastAPI()

        def get_session():
            with Session(engine) as session:
                yield session

        dep = FSPManager.depends(FSPConfig(filterable_fields=()))

        @app.get("/accounts")
        def accounts(
            session: Annotated[Session, Depends(get_session)],
            fsp: Annotated[FSPManager, Depends(dep)],
        ):
            fsp.with_filters([Filter(field="api_key", operator=FilterOperator.EQ, value="key3")])
            return fsp.generate_response(select(Account), session)

        body = TestClient(app).get("/accounts").json()
        assert [row["name"] for row in body["data"]] == ["user03"]


class TestAllowedFieldsViaDepends:
    """The allowed_fields umbrella (from #41) also works through FSPManager.depends()."""

    def test_umbrella_list(self, engine):
        client = make_client(engine, FSPConfig(allowed_fields={"id", "name"}))
        assert client.get("/accounts?sort_by=name").status_code == 200
        r = client.get("/accounts?field=api_key&operator=starts_with&value=k")
        assert r.status_code == 400
        assert r.json()["detail"] == (
            "Filtering by 'api_key' is not allowed. Allowed fields: id, name"
        )

    def test_model_class(self, engine):
        client = make_client(engine, FSPConfig(allowed_fields=AccountPublic))
        assert client.get("/accounts?search=user&search_fields=name,email").status_code == 200
        assert client.get("/accounts?sort_by=api_key").status_code == 400

    def test_per_kind_override(self, engine):
        config = FSPConfig(allowed_fields={"id", "name"}, sortable_fields={"id"})
        client = make_client(engine, config)
        assert client.get("/accounts?sort_by=name").status_code == 400
        assert client.get("/accounts?field=name&operator=eq&value=x").status_code == 200


class TestDenylist:
    def test_default_denylist(self, engine):
        client = make_client(engine, FSPConfig())
        assert client.get("/accounts?sort_by=password").status_code == 400
        assert client.get("/accounts?sort_by=api_key").status_code == 200

    def test_custom_denylist(self, engine):
        config = FSPConfig(denied_fields=DEFAULT_DENIED_FIELDS | {"api_key"})
        client = make_client(engine, config)
        assert client.get("/accounts?sort_by=api_key").status_code == 400
        assert client.get("/accounts?field=api_key&operator=eq&value=k").status_code == 400
        assert client.get("/accounts?search=k&search_fields=api_key").status_code == 400
        assert client.get("/accounts?sort_by=password").status_code == 400

    def test_empty_denylist(self, engine):
        client = make_client(engine, FSPConfig(denied_fields=()))
        assert client.get("/accounts?sort_by=password").status_code == 200

    def test_models_no_longer_validate_fields(self):
        assert Filter(field="password", operator=FilterOperator.EQ, value="x").field == "password"
        assert SortingQuery(sort_by="secret", order=SortingOrder.ASC).sort_by == "secret"


class TestFieldConfigValidation:
    @pytest.mark.parametrize(
        "name", ["filterable_fields", "sortable_fields", "searchable_fields", "denied_fields"]
    )
    def test_bare_string_rejected(self, name):
        with pytest.raises(ValueError, match="not a single string"):
            FSPConfig(**{name: "name"})

    def test_denied_fields_rejects_model_class(self):
        with pytest.raises(ValueError, match="denied_fields"):
            FSPConfig(denied_fields=AccountPublic)

    def test_normalized_to_frozenset(self):
        config = FSPConfig(filterable_fields=["a", "b"], denied_fields=["x"])
        assert config.filterable_fields == frozenset({"a", "b"})
        assert config.denied_fields == frozenset({"x"})
        assert config.sortable_fields is None

    def test_allows_methods(self):
        config = FSPConfig(sortable_fields={"name"})
        assert config.allows_sort("name")
        assert not config.allows_sort("email")
        assert config.allows_filter("email")
        assert not config.allows_filter("password")
        assert not config.allows_search("secret")
