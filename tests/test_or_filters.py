"""Tests for OR filter groups and search query parameter support."""

import pytest
from fastapi.testclient import TestClient
from fastapi_fsp.builder import FilterBuilder
from fastapi_fsp.models import Filter, FilterOperator, OrFilterGroup
from fastapi_fsp.presets import CommonFilters
from sqlmodel import Session

from tests.main import Hero


def seed(session: Session):
    session.add_all(
        [
            Hero(name="Deadpond", secret_name="Dive Wilson", age=28),
            Hero(name="Rusty-Man", secret_name="Tommy Sharp", age=48),
            Hero(name="ALPHA", secret_name="Alpha Secret", age=10),
            Hero(name="beta", secret_name="Beta Secret", age=20),
        ]
    )
    session.commit()


# --- Query parameter tests (search + search_fields) ---


class TestSearchQueryParams:
    """Tests for ?search=term&search_fields=col1,col2 query parameters."""

    def test_search_single_field(self, session: Session, client: TestClient):
        """Search across a single field."""
        seed(session)
        r = client.get("/heroes/?search=dead&search_fields=name")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["name"] == "Deadpond"

    def test_search_multiple_fields(self, session: Session, client: TestClient):
        """Search across multiple fields with OR logic."""
        seed(session)
        # "sharp" matches secret_name="Tommy Sharp" for Rusty-Man
        r = client.get("/heroes/?search=sharp&search_fields=name,secret_name")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["name"] == "Rusty-Man"

    def test_search_matches_any_field(self, session: Session, client: TestClient):
        """Search term matching different fields returns all matching rows."""
        seed(session)
        # "alpha" matches name="ALPHA" and also secret_name="Alpha Secret"
        # Both point to same record, but it should appear once
        r = client.get("/heroes/?search=alpha&search_fields=name,secret_name")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["name"] == "ALPHA"

    def test_search_case_insensitive(self, session: Session, client: TestClient):
        """Search is case-insensitive (uses CONTAINS/ILIKE)."""
        seed(session)
        r = client.get("/heroes/?search=RUSTY&search_fields=name")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["name"] == "Rusty-Man"

    def test_search_no_match(self, session: Session, client: TestClient):
        """Search with no matching results returns empty data."""
        seed(session)
        r = client.get("/heroes/?search=nonexistent&search_fields=name,secret_name")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 0

    def test_search_with_and_filters(self, session: Session, client: TestClient):
        """Search combined with regular AND filters."""
        seed(session)
        # Search for "secret" in secret_name, but also filter age > 15
        r = client.get(
            "/heroes/?search=secret&search_fields=secret_name"
            "&field=age&operator=gt&value=15"
        )
        assert r.status_code == 200
        data = r.json()["data"]
        names = {h["name"] for h in data}
        # "Alpha Secret" (age=10) excluded by age > 15
        # "Beta Secret" (age=20) included
        assert names == {"beta"}

    def test_search_with_pagination(self, session: Session, client: TestClient):
        """Search results are properly paginated."""
        seed(session)
        r = client.get("/heroes/?search=secret&search_fields=secret_name&page=1&per_page=1")
        assert r.status_code == 200
        js = r.json()
        assert len(js["data"]) == 1
        assert js["meta"]["pagination"]["total_items"] == 2

    def test_search_with_sorting(self, session: Session, client: TestClient):
        """Search results can be sorted."""
        seed(session)
        r = client.get(
            "/heroes/?search=secret&search_fields=secret_name&sort_by=name&order=asc"
        )
        assert r.status_code == 200
        data = r.json()["data"]
        names = [h["name"] for h in data]
        assert names == ["ALPHA", "beta"]

    def test_search_without_search_fields_returns_400(
        self, session: Session, client: TestClient
    ):
        """Search without search_fields returns 400."""
        seed(session)
        r = client.get("/heroes/?search=test")
        assert r.status_code == 400
        assert "search_fields" in r.json()["detail"]

    def test_empty_search_fields_returns_400(self, session: Session, client: TestClient):
        """Empty search_fields returns 400."""
        seed(session)
        r = client.get("/heroes/?search=test&search_fields=")
        assert r.status_code == 400

    def test_no_search_param_returns_all(self, session: Session, client: TestClient):
        """Without search param, all records are returned (no OR filtering)."""
        seed(session)
        r = client.get("/heroes/")
        assert r.status_code == 200
        assert len(r.json()["data"]) == 4

    def test_search_meta_includes_or_filters(self, session: Session, client: TestClient):
        """Response meta includes or_filters information."""
        seed(session)
        r = client.get("/heroes/?search=dead&search_fields=name,secret_name")
        assert r.status_code == 200
        meta = r.json()["meta"]
        assert meta["or_filters"] is not None
        assert len(meta["or_filters"]) == 1
        group = meta["or_filters"][0]
        assert len(group["filters"]) == 2
        fields = {f["field"] for f in group["filters"]}
        assert fields == {"name", "secret_name"}
        for f in group["filters"]:
            assert f["operator"] == "contains"
            assert f["value"] == "dead"

    def test_search_across_name_and_secret_name(
        self, session: Session, client: TestClient
    ):
        """Search matches across different columns for different rows."""
        seed(session)
        # "dive" matches secret_name of Deadpond ("Dive Wilson")
        # "beta" matches name of beta
        # Searching for "d" should match: Deadpond (name), Dive Wilson (secret_name)
        r = client.get("/heroes/?search=pond&search_fields=name,secret_name")
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["name"] == "Deadpond"

    def test_search_multiple_results(self, session: Session, client: TestClient):
        """Search matching multiple rows."""
        seed(session)
        # "man" appears in "Rusty-Man" (name) — only 1 match
        # Let's use a term that matches in different fields for different rows
        # "a" appears in: Deadpond (name has 'a'), ALPHA (name), Alpha Secret, Beta Secret
        r = client.get("/heroes/?search=a&search_fields=name,secret_name")
        assert r.status_code == 200
        data = r.json()["data"]
        # Deadpond: name contains 'a' -> no. "Deadpond" has 'a' -> yes!
        # Rusty-Man: name "Rusty-Man" has 'a' -> yes, secret_name "Tommy Sharp" has 'a' -> yes
        # ALPHA: name contains 'a' -> yes
        # beta: name "beta" has 'a' -> yes, secret_name "Beta Secret" -> yes
        assert len(data) == 4


# --- OrFilterGroup model tests ---


class TestOrFilterGroupModel:
    """Tests for OrFilterGroup model."""

    def test_create_or_filter_group(self):
        """Create an OrFilterGroup with filters."""
        group = OrFilterGroup(
            filters=[
                Filter(field="name", operator=FilterOperator.CONTAINS, value="john"),
                Filter(field="email", operator=FilterOperator.CONTAINS, value="john"),
            ]
        )
        assert len(group.filters) == 2
        assert group.filters[0].field == "name"
        assert group.filters[1].field == "email"

    def test_or_filter_group_serialization(self):
        """OrFilterGroup serializes to dict correctly."""
        group = OrFilterGroup(
            filters=[
                Filter(field="name", operator=FilterOperator.CONTAINS, value="test"),
            ]
        )
        d = group.model_dump()
        assert "filters" in d
        assert len(d["filters"]) == 1
        assert d["filters"][0]["field"] == "name"

    def test_empty_or_filter_group(self):
        """OrFilterGroup with empty filters is valid."""
        group = OrFilterGroup(filters=[])
        assert len(group.filters) == 0


# --- FilterBuilder.build_or_group() tests ---


class TestFilterBuilderOrGroup:
    """Tests for FilterBuilder.build_or_group()."""

    def test_build_or_group_basic(self):
        """Build an OR group from filter builder."""
        group = (
            FilterBuilder()
            .where("name").contains("john")
            .where("email").contains("john")
            .build_or_group()
        )
        assert group is not None
        assert len(group.filters) == 2
        assert group.filters[0].field == "name"
        assert group.filters[0].operator == FilterOperator.CONTAINS
        assert group.filters[1].field == "email"

    def test_build_or_group_empty(self):
        """Empty builder returns None for OR group."""
        group = FilterBuilder().build_or_group()
        assert group is None

    def test_build_or_group_single_filter(self):
        """Single filter OR group."""
        group = FilterBuilder().where("name").ilike("%test%").build_or_group()
        assert group is not None
        assert len(group.filters) == 1

    def test_build_or_group_mixed_operators(self):
        """OR group with mixed operators."""
        group = (
            FilterBuilder()
            .where("name").contains("test")
            .where("age").eq(25)
            .where("city").starts_with("new")
            .build_or_group()
        )
        assert group is not None
        assert len(group.filters) == 3
        assert group.filters[0].operator == FilterOperator.CONTAINS
        assert group.filters[1].operator == FilterOperator.EQ
        assert group.filters[2].operator == FilterOperator.STARTS_WITH

    def test_build_vs_build_or_group(self):
        """build() and build_or_group() use same filters differently."""
        builder = (
            FilterBuilder()
            .where("name").contains("test")
            .where("email").contains("test")
        )
        # build() returns List[Filter] for AND logic
        and_filters = builder.build()
        assert and_filters is not None
        assert isinstance(and_filters, list)
        assert len(and_filters) == 2

        # build_or_group() returns OrFilterGroup for OR logic
        or_group = builder.build_or_group()
        assert or_group is not None
        assert isinstance(or_group, OrFilterGroup)
        assert len(or_group.filters) == 2


# --- CommonFilters.multi_field_search() tests ---


class TestMultiFieldSearch:
    """Tests for CommonFilters.multi_field_search()."""

    def test_basic_multi_field_search(self):
        """Basic multi-field search creates OR group."""
        groups = CommonFilters.multi_field_search(
            fields=["name", "email"], term="john"
        )
        assert len(groups) == 1
        group = groups[0]
        assert isinstance(group, OrFilterGroup)
        assert len(group.filters) == 2
        assert group.filters[0].field == "name"
        assert group.filters[0].operator == FilterOperator.CONTAINS
        assert group.filters[0].value == "john"
        assert group.filters[1].field == "email"

    def test_multi_field_search_starts_with(self):
        """Multi-field search with starts_with match type."""
        groups = CommonFilters.multi_field_search(
            fields=["name"], term="jo", match_type="starts_with"
        )
        assert groups[0].filters[0].operator == FilterOperator.STARTS_WITH

    def test_multi_field_search_ends_with(self):
        """Multi-field search with ends_with match type."""
        groups = CommonFilters.multi_field_search(
            fields=["name"], term="hn", match_type="ends_with"
        )
        assert groups[0].filters[0].operator == FilterOperator.ENDS_WITH

    def test_multi_field_search_invalid_match_type(self):
        """Invalid match_type raises ValueError."""
        with pytest.raises(ValueError, match="Invalid match_type"):
            CommonFilters.multi_field_search(
                fields=["name"], term="test", match_type="invalid"
            )

    def test_multi_field_search_empty_fields(self):
        """Empty fields list raises ValueError."""
        with pytest.raises(ValueError, match="At least one field"):
            CommonFilters.multi_field_search(fields=[], term="test")

    def test_multi_field_search_many_fields(self):
        """Multi-field search with many fields."""
        fields = ["name", "email", "city", "phone", "address"]
        groups = CommonFilters.multi_field_search(fields=fields, term="test")
        assert len(groups[0].filters) == 5
        for i, f in enumerate(groups[0].filters):
            assert f.field == fields[i]
            assert f.value == "test"
