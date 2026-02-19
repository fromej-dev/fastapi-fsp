"""Tests for FilterEngine with strategy pattern."""

from datetime import datetime
from enum import StrEnum
from typing import Optional
from unittest.mock import Mock

import pytest
from fastapi_fsp.filters import (
    FILTER_STRATEGIES,
    FilterEngine,
    _coerce_value,
    _is_string_column,
    _split_values,
)
from fastapi_fsp.models import Filter, FilterOperator
from sqlalchemy import Column as SAColumn
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel, create_engine, select


class StatusEnum(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class FilterTestModel(SQLModel, table=True):
    """Test model for filter engine tests."""

    __tablename__ = "filter_test_model"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(default="")
    age: Optional[int] = Field(default=None)
    active: bool = Field(default=True)
    created_at: Optional[datetime] = Field(default=None)
    description: Optional[str] = Field(default=None)
    status: Optional[str] = Field(
        default=None,
        sa_column=SAColumn(SAEnum(StatusEnum, name="statusenum"), nullable=True),
    )


@pytest.fixture(scope="module")
def engine():
    """Create test engine."""
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def columns(engine):
    """Get columns from test model."""
    query = select(FilterTestModel)
    return query.selected_columns


class TestStrategyRegistry:
    """Tests for the FILTER_STRATEGIES registry."""

    def test_all_operators_registered(self):
        """Every FilterOperator has a strategy registered."""
        for op in FilterOperator:
            assert op in FILTER_STRATEGIES, f"Missing strategy for {op}"

    def test_strategy_count_matches_operators(self):
        """Strategy count matches operator count."""
        assert len(FILTER_STRATEGIES) == len(FilterOperator)

    def test_strategies_are_callable(self):
        """All registered strategies are callable."""
        for op, strategy in FILTER_STRATEGIES.items():
            assert callable(strategy), f"Strategy for {op} is not callable"


class TestFilterEngineStrategyDispatch:
    """Tests for strategy-based filter condition building."""

    def test_eq_via_strategy(self, columns):
        """Test EQ operator dispatched through strategy."""
        f = Filter(field="age", operator=FilterOperator.EQ, value="30")
        condition = FilterEngine.build_filter_condition(columns["age"], f)
        assert condition is not None
        assert str(condition) == "filter_test_model.age = :age_1"

    def test_ne_via_strategy(self, columns):
        """Test NE operator."""
        f = Filter(field="age", operator=FilterOperator.NE, value="30")
        condition = FilterEngine.build_filter_condition(columns["age"], f)
        assert condition is not None
        assert "!=" in str(condition) or "<>" in str(condition)

    def test_gt_via_strategy(self, columns):
        f = Filter(field="age", operator=FilterOperator.GT, value="30")
        condition = FilterEngine.build_filter_condition(columns["age"], f)
        assert condition is not None
        assert ">" in str(condition)

    def test_gte_via_strategy(self, columns):
        f = Filter(field="age", operator=FilterOperator.GTE, value="30")
        condition = FilterEngine.build_filter_condition(columns["age"], f)
        assert ">=" in str(condition)

    def test_lt_via_strategy(self, columns):
        f = Filter(field="age", operator=FilterOperator.LT, value="30")
        condition = FilterEngine.build_filter_condition(columns["age"], f)
        assert "<" in str(condition)

    def test_lte_via_strategy(self, columns):
        f = Filter(field="age", operator=FilterOperator.LTE, value="30")
        condition = FilterEngine.build_filter_condition(columns["age"], f)
        assert "<=" in str(condition)

    def test_like_via_strategy(self, columns):
        f = Filter(field="name", operator=FilterOperator.LIKE, value="%John%")
        condition = FilterEngine.build_filter_condition(columns["name"], f)
        assert "LIKE" in str(condition).upper()

    def test_not_like_via_strategy(self, columns):
        f = Filter(field="name", operator=FilterOperator.NOT_LIKE, value="%spam%")
        condition = FilterEngine.build_filter_condition(columns["name"], f)
        assert "NOT" in str(condition).upper()

    def test_ilike_via_strategy(self, columns):
        f = Filter(field="name", operator=FilterOperator.ILIKE, value="%john%")
        condition = FilterEngine.build_filter_condition(columns["name"], f)
        assert condition is not None

    def test_not_ilike_via_strategy(self, columns):
        f = Filter(field="name", operator=FilterOperator.NOT_ILIKE, value="%test%")
        condition = FilterEngine.build_filter_condition(columns["name"], f)
        assert condition is not None

    def test_in_via_strategy(self, columns):
        f = Filter(field="age", operator=FilterOperator.IN, value="25,30,35")
        condition = FilterEngine.build_filter_condition(columns["age"], f)
        assert "IN" in str(condition).upper()

    def test_not_in_via_strategy(self, columns):
        f = Filter(field="age", operator=FilterOperator.NOT_IN, value="1,2,3")
        condition = FilterEngine.build_filter_condition(columns["age"], f)
        assert condition is not None

    def test_between_via_strategy(self, columns):
        f = Filter(field="age", operator=FilterOperator.BETWEEN, value="20,40")
        condition = FilterEngine.build_filter_condition(columns["age"], f)
        assert "BETWEEN" in str(condition).upper()

    def test_between_invalid_returns_none(self, columns):
        f = Filter(field="age", operator=FilterOperator.BETWEEN, value="20")
        condition = FilterEngine.build_filter_condition(columns["age"], f)
        assert condition is None

    def test_is_null_via_strategy(self, columns):
        f = Filter(field="description", operator=FilterOperator.IS_NULL, value="")
        condition = FilterEngine.build_filter_condition(columns["description"], f)
        assert "IS NULL" in str(condition).upper()

    def test_is_not_null_via_strategy(self, columns):
        f = Filter(field="description", operator=FilterOperator.IS_NOT_NULL, value="")
        condition = FilterEngine.build_filter_condition(columns["description"], f)
        assert "NOT NULL" in str(condition).upper() or "IS NOT" in str(condition).upper()

    def test_starts_with_via_strategy(self, columns):
        f = Filter(field="name", operator=FilterOperator.STARTS_WITH, value="John")
        condition = FilterEngine.build_filter_condition(columns["name"], f)
        assert condition is not None

    def test_ends_with_via_strategy(self, columns):
        f = Filter(field="name", operator=FilterOperator.ENDS_WITH, value="son")
        condition = FilterEngine.build_filter_condition(columns["name"], f)
        assert condition is not None

    def test_contains_via_strategy(self, columns):
        f = Filter(field="name", operator=FilterOperator.CONTAINS, value="oh")
        condition = FilterEngine.build_filter_condition(columns["name"], f)
        assert condition is not None

    def test_with_precomputed_pytype(self, columns):
        f = Filter(field="age", operator=FilterOperator.EQ, value="30")
        condition = FilterEngine.build_filter_condition(columns["age"], f, pytype=int)
        assert condition is not None

    def test_contains_on_integer_column_casts_to_text(self, columns):
        """CONTAINS on integer column should cast to text, not fail with ILIKE on int."""
        f = Filter(field="age", operator=FilterOperator.CONTAINS, value="3")
        condition = FilterEngine.build_filter_condition(columns["age"], f)
        assert condition is not None
        compiled = str(condition)
        assert "CAST" in compiled.upper() or "VARCHAR" in compiled.upper()

    def test_ilike_on_integer_column_casts_to_text(self, columns):
        """ILIKE on integer column should cast to text, not fail."""
        f = Filter(field="age", operator=FilterOperator.ILIKE, value="%3%")
        condition = FilterEngine.build_filter_condition(columns["age"], f)
        assert condition is not None
        compiled = str(condition)
        assert "CAST" in compiled.upper() or "VARCHAR" in compiled.upper()

    def test_starts_with_on_integer_column_casts_to_text(self, columns):
        """STARTS_WITH on integer column should cast to text."""
        f = Filter(field="age", operator=FilterOperator.STARTS_WITH, value="3")
        condition = FilterEngine.build_filter_condition(columns["age"], f)
        assert condition is not None
        compiled = str(condition)
        assert "CAST" in compiled.upper() or "VARCHAR" in compiled.upper()

    def test_ends_with_on_integer_column_casts_to_text(self, columns):
        """ENDS_WITH on integer column should cast to text."""
        f = Filter(field="age", operator=FilterOperator.ENDS_WITH, value="5")
        condition = FilterEngine.build_filter_condition(columns["age"], f)
        assert condition is not None
        compiled = str(condition)
        assert "CAST" in compiled.upper() or "VARCHAR" in compiled.upper()

    def test_like_on_integer_column_casts_to_text(self, columns):
        """LIKE on integer column should cast to text."""
        f = Filter(field="age", operator=FilterOperator.LIKE, value="%3%")
        condition = FilterEngine.build_filter_condition(columns["age"], f)
        assert condition is not None
        compiled = str(condition)
        assert "CAST" in compiled.upper() or "VARCHAR" in compiled.upper()

    def test_contains_on_string_column_no_cast(self, columns):
        """CONTAINS on string column should NOT cast - use column directly."""
        f = Filter(field="name", operator=FilterOperator.CONTAINS, value="oh")
        condition = FilterEngine.build_filter_condition(columns["name"], f)
        assert condition is not None
        compiled = str(condition)
        assert "CAST" not in compiled.upper()

    def test_contains_on_enum_column_casts_to_text(self, columns):
        """CONTAINS on enum column should cast to text to avoid PG operator error."""
        f = Filter(field="status", operator=FilterOperator.CONTAINS, value="act")
        condition = FilterEngine.build_filter_condition(columns["status"], f)
        assert condition is not None
        compiled = str(condition)
        assert "CAST" in compiled.upper() or "VARCHAR" in compiled.upper()

    def test_ilike_on_enum_column_casts_to_text(self, columns):
        """ILIKE on enum column should cast to text."""
        f = Filter(field="status", operator=FilterOperator.ILIKE, value="%active%")
        condition = FilterEngine.build_filter_condition(columns["status"], f)
        assert condition is not None
        compiled = str(condition)
        assert "CAST" in compiled.upper() or "VARCHAR" in compiled.upper()


class TestCustomStrategy:
    """Tests for registering custom filter strategies."""

    def test_register_custom_strategy(self, columns):
        """Test registering and using a custom strategy."""
        original = FILTER_STRATEGIES[FilterOperator.EQ]

        def custom_eq(column, raw, pytype):
            return column == raw  # No type coercion

        FilterEngine.register_strategy(FilterOperator.EQ, custom_eq)
        assert FILTER_STRATEGIES[FilterOperator.EQ] is custom_eq

        f = Filter(field="name", operator=FilterOperator.EQ, value="test")
        condition = FilterEngine.build_filter_condition(columns["name"], f)
        assert condition is not None

        # Restore original
        FILTER_STRATEGIES[FilterOperator.EQ] = original

    def test_register_preserves_other_strategies(self, columns):
        """Registering one strategy doesn't affect others."""
        original_eq = FILTER_STRATEGIES[FilterOperator.EQ]
        original_ne = FILTER_STRATEGIES[FilterOperator.NE]

        FilterEngine.register_strategy(FilterOperator.EQ, lambda c, r, p: c == r)
        assert FILTER_STRATEGIES[FilterOperator.NE] is original_ne

        # Restore
        FILTER_STRATEGIES[FilterOperator.EQ] = original_eq


class TestFilterEngineColumnTypeCaching:
    """Tests for FilterEngine column type caching."""

    def test_caches_column_type(self, columns):
        engine = FilterEngine()
        age_col = columns["age"]

        pytype1 = engine.get_column_type(age_col)
        assert pytype1 is int

        pytype2 = engine.get_column_type(age_col)
        assert pytype2 is int
        assert pytype1 is pytype2

        col_id = id(age_col)
        assert col_id in engine._type_cache

    def test_handles_missing_python_type(self):
        engine = FilterEngine()
        mock_col = Mock()
        mock_col.type = Mock(spec=[])  # No python_type attribute

        pytype = engine.get_column_type(mock_col)
        assert pytype is None


class TestFilterEngineApplyFilters:
    """Tests for FilterEngine.apply_filters()."""

    def test_apply_no_filters(self, columns):
        engine = FilterEngine()
        query = select(FilterTestModel)
        result = engine.apply_filters(query, columns, None)
        assert "WHERE" not in str(result)

    def test_apply_single_filter(self, columns):
        engine = FilterEngine()
        query = select(FilterTestModel)
        filters = [Filter(field="age", operator=FilterOperator.GTE, value="18")]
        result = engine.apply_filters(query, columns, filters)
        assert "WHERE" in str(result)

    def test_apply_multiple_filters(self, columns):
        engine = FilterEngine()
        query = select(FilterTestModel)
        filters = [
            Filter(field="age", operator=FilterOperator.GTE, value="18"),
            Filter(field="active", operator=FilterOperator.EQ, value="true"),
        ]
        result = engine.apply_filters(query, columns, filters)
        assert "WHERE" in str(result)
        assert "AND" in str(result)

    def test_strict_mode_unknown_field(self, columns):
        from fastapi import HTTPException

        engine = FilterEngine(strict_mode=True)
        query = select(FilterTestModel)
        filters = [Filter(field="unknown", operator=FilterOperator.EQ, value="test")]

        with pytest.raises(HTTPException) as exc_info:
            engine.apply_filters(query, columns, filters)
        assert exc_info.value.status_code == 400

    def test_non_strict_skips_unknown(self, columns):
        engine = FilterEngine(strict_mode=False)
        query = select(FilterTestModel)
        filters = [Filter(field="unknown", operator=FilterOperator.EQ, value="test")]
        result = engine.apply_filters(query, columns, filters)
        assert "unknown" not in str(result)


class TestModuleFunctions:
    """Tests for module-level helper functions."""

    def test_coerce_value_integer(self, columns):
        result = _coerce_value(columns["age"], "42")
        assert result == 42

    def test_coerce_value_boolean_true(self, columns):
        result = _coerce_value(columns["active"], "true")
        assert result is True

    def test_coerce_value_boolean_false(self, columns):
        result = _coerce_value(columns["active"], "false")
        assert result is False

    def test_coerce_value_datetime(self, columns):
        result = _coerce_value(columns["created_at"], "2024-01-15T10:30:00")
        assert isinstance(result, datetime)

    def test_split_values(self):
        assert _split_values("a,b,c") == ["a", "b", "c"]
        assert _split_values("  a  ,  b  ") == ["a", "b"]

    def test_is_string_column(self, columns):
        assert _is_string_column(columns["name"]) is True
        assert _is_string_column(columns["age"]) is False

    def test_is_string_column_enum_returns_false(self, columns):
        """Enum columns should not be treated as string for ILIKE purposes."""
        assert _is_string_column(columns["status"]) is False
