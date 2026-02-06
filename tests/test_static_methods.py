"""Tests for FSPManager static methods."""

from datetime import datetime
from typing import Optional
from unittest.mock import Mock

import pytest
from fastapi_fsp.fsp import FSPManager
from fastapi_fsp.models import Filter, FilterOperator, PaginationQuery
from sqlmodel import Field, SQLModel, create_engine, select


class TestModel(SQLModel, table=True):
    """Test model for static method tests."""

    __tablename__ = "test_static_methods"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(default="")
    age: Optional[int] = Field(default=None)
    price: Optional[float] = Field(default=None)
    active: bool = Field(default=True)
    created_at: Optional[datetime] = Field(default=None)
    description: Optional[str] = Field(default=None)


@pytest.fixture(scope="module")
def engine():
    """Create test engine."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def columns(engine):
    """Get columns from test model."""
    query = select(TestModel)
    return query.selected_columns


class TestCoerceValue:
    """Tests for _coerce_value method."""

    def test_coerce_integer_from_string(self, columns):
        """Test coercing integer from string."""
        result = FSPManager._coerce_value(columns["age"], "42")
        assert result == 42
        assert isinstance(result, int)

    def test_coerce_integer_from_float_string(self, columns):
        """Test coercing integer from float-like string."""
        result = FSPManager._coerce_value(columns["age"], "42.0")
        assert result == 42
        assert isinstance(result, int)

    def test_coerce_integer_invalid(self, columns):
        """Test coercing invalid integer returns original."""
        result = FSPManager._coerce_value(columns["age"], "not_a_number")
        assert result == "not_a_number"

    def test_coerce_boolean_true_values(self, columns):
        """Test coercing various true values to boolean."""
        true_values = ["true", "True", "TRUE", "1", "t", "T", "yes", "Yes", "y", "Y"]
        for val in true_values:
            result = FSPManager._coerce_value(columns["active"], val)
            assert result is True, f"Expected True for '{val}'"

    def test_coerce_boolean_false_values(self, columns):
        """Test coercing various false values to boolean."""
        false_values = ["false", "False", "FALSE", "0", "f", "F", "no", "No", "n", "N"]
        for val in false_values:
            result = FSPManager._coerce_value(columns["active"], val)
            assert result is False, f"Expected False for '{val}'"

    def test_coerce_boolean_with_whitespace(self, columns):
        """Test coercing boolean with whitespace."""
        result = FSPManager._coerce_value(columns["active"], "  true  ")
        assert result is True

    def test_coerce_datetime_iso8601(self, columns):
        """Test coercing ISO 8601 datetime."""
        result = FSPManager._coerce_value(columns["created_at"], "2024-01-15T10:30:00")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 10
        assert result.minute == 30

    def test_coerce_datetime_date_only(self, columns):
        """Test coercing date-only string to datetime."""
        result = FSPManager._coerce_value(columns["created_at"], "2024-01-15")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_coerce_datetime_with_timezone(self, columns):
        """Test coercing datetime with timezone."""
        result = FSPManager._coerce_value(columns["created_at"], "2024-01-15T10:30:00+00:00")
        assert isinstance(result, datetime)

    def test_coerce_datetime_natural_language(self, columns):
        """Test coercing natural language datetime (via dateutil)."""
        result = FSPManager._coerce_value(columns["created_at"], "January 15, 2024")
        assert isinstance(result, datetime)
        assert result.month == 1
        assert result.day == 15

    def test_coerce_datetime_invalid(self, columns):
        """Test coercing invalid datetime returns original."""
        result = FSPManager._coerce_value(columns["created_at"], "not_a_date")
        assert result == "not_a_date"

    def test_coerce_string_passthrough(self, columns):
        """Test string values pass through unchanged."""
        result = FSPManager._coerce_value(columns["name"], "John Doe")
        assert result == "John Doe"

    def test_coerce_with_precomputed_pytype(self, columns):
        """Test coercing with pre-computed pytype for performance."""
        result = FSPManager._coerce_value(columns["age"], "42", pytype=int)
        assert result == 42

    def test_coerce_with_none_pytype(self, columns):
        """Test coercing when pytype is None returns original."""
        # Create a mock column with no python_type
        mock_column = Mock()
        mock_column.type = Mock()
        del mock_column.type.python_type  # Remove python_type attribute

        result = FSPManager._coerce_value(mock_column, "test_value", pytype=None)
        assert result == "test_value"


class TestSplitValues:
    """Tests for _split_values method."""

    def test_split_simple_values(self):
        """Test splitting simple comma-separated values."""
        result = FSPManager._split_values("a,b,c")
        assert result == ["a", "b", "c"]

    def test_split_with_spaces(self):
        """Test splitting values with surrounding spaces."""
        result = FSPManager._split_values("  a  ,  b  ,  c  ")
        assert result == ["a", "b", "c"]

    def test_split_single_value(self):
        """Test splitting single value."""
        result = FSPManager._split_values("single")
        assert result == ["single"]

    def test_split_empty_string(self):
        """Test splitting empty string."""
        result = FSPManager._split_values("")
        assert result == [""]

    def test_split_numeric_values(self):
        """Test splitting numeric string values."""
        result = FSPManager._split_values("1,2,3,4,5")
        assert result == ["1", "2", "3", "4", "5"]

    def test_split_mixed_values(self):
        """Test splitting mixed values."""
        result = FSPManager._split_values("active, pending, 42, true")
        assert result == ["active", "pending", "42", "true"]


class TestBuildFilterCondition:
    """Tests for _build_filter_condition method."""

    def test_eq_filter(self, columns):
        """Test EQ filter condition."""
        f = Filter(field="age", operator=FilterOperator.EQ, value="30")
        condition = FSPManager._build_filter_condition(columns["age"], f)
        assert condition is not None
        assert str(condition) == "test_static_methods.age = :age_1"

    def test_ne_filter(self, columns):
        """Test NE filter condition."""
        f = Filter(field="age", operator=FilterOperator.NE, value="30")
        condition = FSPManager._build_filter_condition(columns["age"], f)
        assert condition is not None
        assert "!=" in str(condition) or "<>" in str(condition)

    def test_gt_filter(self, columns):
        """Test GT filter condition."""
        f = Filter(field="age", operator=FilterOperator.GT, value="30")
        condition = FSPManager._build_filter_condition(columns["age"], f)
        assert condition is not None
        assert ">" in str(condition)

    def test_gte_filter(self, columns):
        """Test GTE filter condition."""
        f = Filter(field="age", operator=FilterOperator.GTE, value="30")
        condition = FSPManager._build_filter_condition(columns["age"], f)
        assert condition is not None
        assert ">=" in str(condition)

    def test_lt_filter(self, columns):
        """Test LT filter condition."""
        f = Filter(field="age", operator=FilterOperator.LT, value="30")
        condition = FSPManager._build_filter_condition(columns["age"], f)
        assert condition is not None
        assert "<" in str(condition)

    def test_lte_filter(self, columns):
        """Test LTE filter condition."""
        f = Filter(field="age", operator=FilterOperator.LTE, value="30")
        condition = FSPManager._build_filter_condition(columns["age"], f)
        assert condition is not None
        assert "<=" in str(condition)

    def test_like_filter(self, columns):
        """Test LIKE filter condition."""
        f = Filter(field="name", operator=FilterOperator.LIKE, value="%John%")
        condition = FSPManager._build_filter_condition(columns["name"], f)
        assert condition is not None
        assert "LIKE" in str(condition).upper()

    def test_not_like_filter(self, columns):
        """Test NOT LIKE filter condition."""
        f = Filter(field="name", operator=FilterOperator.NOT_LIKE, value="%spam%")
        condition = FSPManager._build_filter_condition(columns["name"], f)
        assert condition is not None
        assert "NOT" in str(condition).upper()

    def test_ilike_filter(self, columns):
        """Test ILIKE filter condition."""
        f = Filter(field="name", operator=FilterOperator.ILIKE, value="%john%")
        condition = FSPManager._build_filter_condition(columns["name"], f)
        assert condition is not None

    def test_not_ilike_filter(self, columns):
        """Test NOT ILIKE filter condition."""
        f = Filter(field="name", operator=FilterOperator.NOT_ILIKE, value="%test%")
        condition = FSPManager._build_filter_condition(columns["name"], f)
        assert condition is not None

    def test_in_filter(self, columns):
        """Test IN filter condition."""
        f = Filter(field="age", operator=FilterOperator.IN, value="25,30,35")
        condition = FSPManager._build_filter_condition(columns["age"], f)
        assert condition is not None
        assert "IN" in str(condition).upper()

    def test_not_in_filter(self, columns):
        """Test NOT IN filter condition."""
        f = Filter(field="age", operator=FilterOperator.NOT_IN, value="1,2,3")
        condition = FSPManager._build_filter_condition(columns["age"], f)
        assert condition is not None

    def test_between_filter(self, columns):
        """Test BETWEEN filter condition."""
        f = Filter(field="age", operator=FilterOperator.BETWEEN, value="20,40")
        condition = FSPManager._build_filter_condition(columns["age"], f)
        assert condition is not None
        assert "BETWEEN" in str(condition).upper()

    def test_between_filter_invalid(self, columns):
        """Test BETWEEN filter with invalid value returns None."""
        f = Filter(field="age", operator=FilterOperator.BETWEEN, value="20")  # Only one value
        condition = FSPManager._build_filter_condition(columns["age"], f)
        assert condition is None

    def test_is_null_filter(self, columns):
        """Test IS NULL filter condition."""
        f = Filter(field="description", operator=FilterOperator.IS_NULL, value="")
        condition = FSPManager._build_filter_condition(columns["description"], f)
        assert condition is not None
        assert "IS NULL" in str(condition).upper()

    def test_is_not_null_filter(self, columns):
        """Test IS NOT NULL filter condition."""
        f = Filter(field="description", operator=FilterOperator.IS_NOT_NULL, value="")
        condition = FSPManager._build_filter_condition(columns["description"], f)
        assert condition is not None
        assert "NOT NULL" in str(condition).upper() or "IS NOT" in str(condition).upper()

    def test_starts_with_filter(self, columns):
        """Test STARTS_WITH filter condition."""
        f = Filter(field="name", operator=FilterOperator.STARTS_WITH, value="John")
        condition = FSPManager._build_filter_condition(columns["name"], f)
        assert condition is not None

    def test_ends_with_filter(self, columns):
        """Test ENDS_WITH filter condition."""
        f = Filter(field="name", operator=FilterOperator.ENDS_WITH, value="son")
        condition = FSPManager._build_filter_condition(columns["name"], f)
        assert condition is not None

    def test_contains_filter(self, columns):
        """Test CONTAINS filter condition."""
        f = Filter(field="name", operator=FilterOperator.CONTAINS, value="oh")
        condition = FSPManager._build_filter_condition(columns["name"], f)
        assert condition is not None

    def test_with_precomputed_pytype(self, columns):
        """Test filter condition with pre-computed pytype."""
        f = Filter(field="age", operator=FilterOperator.EQ, value="30")
        condition = FSPManager._build_filter_condition(columns["age"], f, pytype=int)
        assert condition is not None


class TestIlikeSupported:
    """Tests for _ilike_supported method."""

    def test_ilike_supported_with_string_column(self, columns):
        """Test ilike supported returns True for string column."""
        result = FSPManager._ilike_supported(columns["name"])
        assert result is True

    def test_ilike_supported_with_integer_column(self, columns):
        """Test ilike supported for integer column."""
        # Integer columns may or may not support ilike depending on database
        result = FSPManager._ilike_supported(columns["age"])
        assert isinstance(result, bool)


class TestApplyFilters:
    """Tests for _apply_filters method."""

    @pytest.fixture
    def fsp_manager(self):
        """Create a mock FSPManager."""
        request = Mock()
        request.url = Mock()
        request.url.include_query_params = Mock(return_value="http://example.com")
        pagination = PaginationQuery(page=1, per_page=20)
        return FSPManager(request=request, filters=None, sorting=None, pagination=pagination)

    def test_apply_filters_empty(self, fsp_manager, columns):
        """Test apply_filters with no filters."""
        query = select(TestModel)
        result = fsp_manager._apply_filters(query, columns, None)
        # Query should be unchanged
        assert "WHERE" not in str(result)

    def test_apply_filters_single(self, fsp_manager, columns):
        """Test apply_filters with single filter."""
        query = select(TestModel)
        filters = [Filter(field="age", operator=FilterOperator.GTE, value="18")]
        result = fsp_manager._apply_filters(query, columns, filters)
        assert "WHERE" in str(result)

    def test_apply_filters_multiple(self, fsp_manager, columns):
        """Test apply_filters with multiple filters."""
        query = select(TestModel)
        filters = [
            Filter(field="age", operator=FilterOperator.GTE, value="18"),
            Filter(field="active", operator=FilterOperator.EQ, value="true"),
        ]
        result = fsp_manager._apply_filters(query, columns, filters)
        assert "WHERE" in str(result)
        assert "AND" in str(result)

    def test_apply_filters_unknown_field_non_strict(self, fsp_manager, columns):
        """Test apply_filters skips unknown fields in non-strict mode."""
        query = select(TestModel)
        filters = [Filter(field="unknown_field", operator=FilterOperator.EQ, value="test")]
        result = fsp_manager._apply_filters(query, columns, filters)
        # Should not add WHERE clause for unknown field
        assert "unknown_field" not in str(result)

    def test_apply_filters_unknown_field_strict(self, columns):
        """Test apply_filters raises error for unknown fields in strict mode."""
        from fastapi import HTTPException

        request = Mock()
        request.url = Mock()
        request.url.include_query_params = Mock(return_value="http://example.com")
        pagination = PaginationQuery(page=1, per_page=20)

        fsp = FSPManager(
            request=request, filters=None, sorting=None, pagination=pagination, strict_mode=True
        )

        query = select(TestModel)
        filters = [Filter(field="unknown_field", operator=FilterOperator.EQ, value="test")]

        with pytest.raises(HTTPException) as exc_info:
            fsp._apply_filters(query, columns, filters)

        assert exc_info.value.status_code == 400
        assert "Unknown field" in str(exc_info.value.detail)
