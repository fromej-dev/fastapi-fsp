"""Tests for SearchBackend optimization (tsvector, trigram, ILIKE fallback)."""

from typing import Optional
from unittest.mock import Mock

import pytest
from fastapi_fsp.config import FSPConfig
from fastapi_fsp.filters import (
    FilterEngine,
    _is_search_optimizable,
    _sanitize_tsquery_token,
)
from fastapi_fsp.fsp import FSPManager
from fastapi_fsp.models import (
    Filter,
    FilterOperator,
    OrFilterGroup,
    PaginationQuery,
    SearchBackend,
)
from sqlalchemy import StaticPool
from sqlalchemy.dialects import postgresql
from sqlmodel import Field, Session, SQLModel, create_engine, select

# --- Test model ---


class Item(SQLModel, table=True):
    __tablename__ = "search_backend_item"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    city: str
    house_nr: str
    zip_code: str


# --- Helpers ---


def _make_token_groups(tokens, fields):
    """Create tokenized search OR groups."""
    return [
        OrFilterGroup(
            filters=[Filter(field=f, operator=FilterOperator.CONTAINS, value=token) for f in fields]
        )
        for token in tokens
    ]


def _compile_pg(query):
    """Compile a query to PostgreSQL SQL string for inspection."""
    compiled = query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    return str(compiled)


# --- Pattern detection tests ---


class TestIsSearchOptimizable:
    def test_true_for_token_groups(self):
        groups = _make_token_groups(["media", "32"], ["name", "city", "house_nr"])
        assert _is_search_optimizable(groups) is True

    def test_true_single_token(self):
        groups = _make_token_groups(["media"], ["name", "city"])
        assert _is_search_optimizable(groups) is True

    def test_false_empty(self):
        assert _is_search_optimizable([]) is False

    def test_false_mixed_operators(self):
        groups = [
            OrFilterGroup(
                filters=[
                    Filter(field="name", operator=FilterOperator.CONTAINS, value="test"),
                    Filter(field="city", operator=FilterOperator.EQ, value="test"),
                ]
            )
        ]
        assert _is_search_optimizable(groups) is False

    def test_false_space_in_value(self):
        groups = [
            OrFilterGroup(
                filters=[
                    Filter(field="name", operator=FilterOperator.CONTAINS, value="hello world"),
                    Filter(field="city", operator=FilterOperator.CONTAINS, value="hello world"),
                ]
            )
        ]
        assert _is_search_optimizable(groups) is False

    def test_false_different_values_in_group(self):
        groups = [
            OrFilterGroup(
                filters=[
                    Filter(field="name", operator=FilterOperator.CONTAINS, value="alpha"),
                    Filter(field="city", operator=FilterOperator.CONTAINS, value="beta"),
                ]
            )
        ]
        assert _is_search_optimizable(groups) is False

    def test_false_different_field_sets(self):
        groups = [
            OrFilterGroup(
                filters=[
                    Filter(field="name", operator=FilterOperator.CONTAINS, value="a"),
                    Filter(field="city", operator=FilterOperator.CONTAINS, value="a"),
                ]
            ),
            OrFilterGroup(
                filters=[
                    Filter(field="name", operator=FilterOperator.CONTAINS, value="b"),
                    Filter(field="zip_code", operator=FilterOperator.CONTAINS, value="b"),
                ]
            ),
        ]
        assert _is_search_optimizable(groups) is False

    def test_false_single_filter_per_group_still_optimizable(self):
        # Single field is still optimizable
        groups = _make_token_groups(["test"], ["name"])
        assert _is_search_optimizable(groups) is True

    def test_false_empty_filters_in_group(self):
        groups = [OrFilterGroup(filters=[])]
        assert _is_search_optimizable(groups) is False


# --- Sanitization tests ---


class TestSanitizeTsqueryToken:
    def test_strips_special_chars(self):
        assert _sanitize_tsquery_token("hello&world") == "helloworld"
        assert _sanitize_tsquery_token("test|or") == "testor"
        assert _sanitize_tsquery_token("!not") == "not"
        assert _sanitize_tsquery_token("(parens)") == "parens"
        assert _sanitize_tsquery_token("colon:star*") == "colonstar"
        assert _sanitize_tsquery_token("quote'test") == "quotetest"
        assert _sanitize_tsquery_token("back\\slash") == "backslash"

    def test_normal_token_unchanged(self):
        assert _sanitize_tsquery_token("medialaan") == "medialaan"
        assert _sanitize_tsquery_token("32") == "32"

    def test_empty_after_strip(self):
        assert _sanitize_tsquery_token("&|!") == ""


# --- SQL generation tests (tsvector) ---


class TestTsvectorSqlGeneration:
    def setup_method(self):
        self.engine_fe = FilterEngine()
        self.query = select(Item)
        self.columns = self.query.selected_columns

    def test_generates_correct_sql(self):
        groups = _make_token_groups(["media", "32"], ["name", "city", "house_nr"])
        result = self.engine_fe.apply_search_optimized(self.query, self.columns, groups, "tsvector")
        sql = _compile_pg(result)
        assert "to_tsvector" in sql
        assert "to_tsquery" in sql
        assert "@@" in sql

    def test_prefix_matching(self):
        groups = _make_token_groups(["media", "32"], ["name", "city"])
        result = self.engine_fe.apply_search_optimized(self.query, self.columns, groups, "tsvector")
        sql = _compile_pg(result)
        assert "media:*" in sql
        assert "32:*" in sql
        assert "&" in sql

    def test_sanitizes_special_chars(self):
        groups = _make_token_groups(["test&inject", "normal"], ["name", "city"])
        result = self.engine_fe.apply_search_optimized(self.query, self.columns, groups, "tsvector")
        sql = _compile_pg(result)
        assert "testinject:*" in sql
        assert "normal:*" in sql
        # No raw & from injection
        assert "test&inject" not in sql

    def test_single_token(self):
        groups = _make_token_groups(["media"], ["name", "city"])
        result = self.engine_fe.apply_search_optimized(self.query, self.columns, groups, "tsvector")
        sql = _compile_pg(result)
        assert "media:*" in sql
        # No & conjunction for single token
        assert "& " not in sql

    def test_uses_simple_config(self):
        groups = _make_token_groups(["test"], ["name"])
        result = self.engine_fe.apply_search_optimized(self.query, self.columns, groups, "tsvector")
        sql = _compile_pg(result)
        assert "simple" in sql.lower()


# --- SQL generation tests (trigram) ---


class TestTrigramSqlGeneration:
    def setup_method(self):
        self.engine_fe = FilterEngine()
        self.query = select(Item)
        self.columns = self.query.selected_columns

    def test_generates_correct_sql(self):
        groups = _make_token_groups(["media"], ["name", "city"])
        result = self.engine_fe.apply_search_optimized(self.query, self.columns, groups, "trigram")
        sql = _compile_pg(result).lower()
        assert "ilike" in sql or "like" in sql

    def test_three_tokens_generate_three_conditions(self):
        groups = _make_token_groups(["a", "b", "c"], ["name", "city"])
        result = self.engine_fe.apply_search_optimized(self.query, self.columns, groups, "trigram")
        sql = _compile_pg(result).lower()
        # Three ILIKE conditions (one per token)
        assert sql.count("like") == 3


# --- Config integration tests ---


class TestConfigIntegration:
    def test_default_backend_is_ilike(self):
        config = FSPConfig()
        assert config.search_backend == SearchBackend.ILIKE

    def test_config_propagates_to_filter_engine(self):
        request = Mock()
        request.url = Mock()
        request.url.include_query_params = Mock(return_value="http://example.com")
        request.query_params = {}
        pagination = PaginationQuery(page=1, per_page=20)

        fsp = FSPManager(
            request=request,
            filters=None,
            sorting=None,
            pagination=pagination,
            or_filters=None,
        )

        config = FSPConfig(search_backend=SearchBackend.TSVECTOR)
        fsp.apply_config(config)

        assert fsp._filter_engine.search_backend == "tsvector"

    def test_trigram_config_propagates(self):
        request = Mock()
        request.url = Mock()
        request.url.include_query_params = Mock(return_value="http://example.com")
        request.query_params = {}
        pagination = PaginationQuery(page=1, per_page=20)

        fsp = FSPManager(
            request=request,
            filters=None,
            sorting=None,
            pagination=pagination,
            or_filters=None,
        )

        config = FSPConfig(search_backend=SearchBackend.TRIGRAM)
        fsp.apply_config(config)

        assert fsp._filter_engine.search_backend == "trigram"

    def test_max_search_tokens_truncates(self):
        request = Mock()
        request.url = Mock()
        request.url.include_query_params = Mock(return_value="http://example.com")
        request.query_params = {}
        pagination = PaginationQuery(page=1, per_page=20)

        groups = _make_token_groups([f"token{i}" for i in range(15)], ["name", "city"])
        fsp = FSPManager(
            request=request,
            filters=None,
            sorting=None,
            pagination=pagination,
            or_filters=groups,
        )

        config = FSPConfig(max_search_tokens=10)
        fsp.apply_config(config)

        assert len(fsp.or_filters) == 10

    def test_max_search_tokens_validation(self):
        with pytest.raises(ValueError, match="max_search_tokens must be >= 1"):
            FSPConfig(max_search_tokens=0)

    def test_max_search_tokens_no_truncation_when_within_limit(self):
        request = Mock()
        request.url = Mock()
        request.url.include_query_params = Mock(return_value="http://example.com")
        request.query_params = {}
        pagination = PaginationQuery(page=1, per_page=20)

        groups = _make_token_groups(["a", "b", "c"], ["name"])
        fsp = FSPManager(
            request=request,
            filters=None,
            sorting=None,
            pagination=pagination,
            or_filters=groups,
        )

        config = FSPConfig(max_search_tokens=10)
        fsp.apply_config(config)

        assert len(fsp.or_filters) == 3


# --- Trigram integration tests (SQLite-compatible) ---


class TestTrigramIntegration:
    @pytest.fixture(autouse=True)
    def setup_db(self):
        self.db_engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        SQLModel.metadata.create_all(self.db_engine)
        with Session(self.db_engine) as session:
            session.add_all(
                [
                    Item(name="Medialaan", city="Vilvoorde", house_nr="32", zip_code="1800"),
                    Item(name="Kerkstraat", city="Vilvoorde", house_nr="5", zip_code="1800"),
                    Item(name="Kerkstraat", city="Brussel", house_nr="10", zip_code="1000"),
                    Item(name="Medialaan", city="Antwerpen", house_nr="1", zip_code="2000"),
                ]
            )
            session.commit()
        yield

    def _query_trigram(self, tokens, fields):
        """Execute a trigram search and return results."""
        groups = _make_token_groups(tokens, fields)
        fe = FilterEngine()
        query = select(Item)
        columns = query.selected_columns
        result_query = fe.apply_search_optimized(query, columns, groups, "trigram")
        with Session(self.db_engine) as session:
            return session.exec(result_query).all()

    def _query_ilike(self, tokens, fields):
        """Execute standard ILIKE search and return results."""
        groups = _make_token_groups(tokens, fields)
        fe = FilterEngine()
        query = select(Item)
        columns = query.selected_columns
        result_query = fe.apply_or_filter_groups(query, columns, groups)
        with Session(self.db_engine) as session:
            return session.exec(result_query).all()

    def test_trigram_search_same_results_as_ilike(self):
        tokens = ["media", "vilvoorde"]
        fields = ["name", "city", "house_nr"]
        trigram_results = self._query_trigram(tokens, fields)
        ilike_results = self._query_ilike(tokens, fields)
        assert len(trigram_results) == len(ilike_results)
        assert {r.id for r in trigram_results} == {r.id for r in ilike_results}

    def test_trigram_token_search(self):
        results = self._query_trigram(["media", "32"], ["name", "city", "house_nr"])
        assert len(results) == 1
        assert results[0].name == "Medialaan"
        assert results[0].house_nr == "32"

    def test_trigram_case_insensitive(self):
        results = self._query_trigram(["MEDIA", "VILVOORDE"], ["name", "city"])
        assert len(results) == 1
        assert results[0].city == "Vilvoorde"

    def test_trigram_single_token(self):
        results = self._query_trigram(["vilvoorde"], ["name", "city"])
        assert len(results) == 2

    def test_trigram_no_match(self):
        results = self._query_trigram(["nonexistent"], ["name", "city"])
        assert len(results) == 0


# --- Fallback tests ---


class TestFallback:
    def setup_method(self):
        self.engine_fe = FilterEngine()
        self.query = select(Item)
        self.columns = self.query.selected_columns

    def test_non_search_or_groups_use_standard_path(self):
        """Arbitrary or_filters with mixed operators bypass optimization."""
        groups = [
            OrFilterGroup(
                filters=[
                    Filter(field="name", operator=FilterOperator.EQ, value="test"),
                    Filter(field="city", operator=FilterOperator.CONTAINS, value="test"),
                ]
            )
        ]
        # Should not raise, falls back to standard path
        result = self.engine_fe.apply_search_optimized(self.query, self.columns, groups, "tsvector")
        sql = _compile_pg(result)
        # Standard path uses individual conditions, no tsvector
        assert "to_tsvector" not in sql

    def test_phrase_mode_bypasses_optimization(self):
        """Phrase with spaces in value is not optimizable."""
        groups = [
            OrFilterGroup(
                filters=[
                    Filter(
                        field="name",
                        operator=FilterOperator.CONTAINS,
                        value="hello world",
                    ),
                    Filter(
                        field="city",
                        operator=FilterOperator.CONTAINS,
                        value="hello world",
                    ),
                ]
            )
        ]
        result = self.engine_fe.apply_search_optimized(self.query, self.columns, groups, "tsvector")
        sql = _compile_pg(result)
        assert "to_tsvector" not in sql

    def test_empty_groups_returns_query_unchanged(self):
        result = self.engine_fe.apply_search_optimized(self.query, self.columns, [], "tsvector")
        assert _compile_pg(result) == _compile_pg(self.query)

    def test_none_groups_returns_query_unchanged(self):
        result = self.engine_fe.apply_search_optimized(self.query, self.columns, None, "tsvector")
        assert _compile_pg(result) == _compile_pg(self.query)


# --- SearchBackend enum tests ---


class TestSearchBackendEnum:
    def test_values(self):
        assert SearchBackend.ILIKE == "ilike"
        assert SearchBackend.TSVECTOR == "tsvector"
        assert SearchBackend.TRIGRAM == "trigram"

    def test_is_str_enum(self):
        assert isinstance(SearchBackend.ILIKE, str)
