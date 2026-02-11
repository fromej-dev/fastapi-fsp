"""Tests for optimizations in FSPManager."""

from datetime import datetime

import pytest
from fastapi_fsp.fsp import FSPManager
from fastapi_fsp.models import Filter, FilterOperator
from sqlmodel import Field, Session, SQLModel, create_engine, select


class HeroOptimization(SQLModel, table=True):
    """HeroOptimization model for testing optimizations."""

    __tablename__ = "hero_optimization"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    age: int | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    active: bool = Field(default=True)


@pytest.fixture(name="session")
def session_fixture():
    """Create a test database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        yield session


def test_coerce_value_datetime_iso8601():
    """Test optimized datetime parsing for ISO 8601 format."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine):
        query = select(HeroOptimization)
        columns = query.selected_columns
        created_at_col = columns["created_at"]

        # Test ISO 8601 format (fast path)
        iso_date = "2024-01-15T10:30:00"
        result = FSPManager._coerce_value(created_at_col, iso_date)
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

        # Test ISO 8601 with microseconds
        iso_date_micro = "2024-01-15T10:30:00.123456"
        result = FSPManager._coerce_value(created_at_col, iso_date_micro)
        assert isinstance(result, datetime)
        assert result.microsecond == 123456


def test_coerce_value_datetime_other_formats():
    """Test datetime parsing for non-ISO formats (fallback)."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine):
        query = select(HeroOptimization)
        columns = query.selected_columns
        created_at_col = columns["created_at"]

        # Test other date formats that dateutil can parse
        test_dates = [
            "Jan 15, 2024",
            "2024-01-15",
            "15/01/2024",
        ]

        for date_str in test_dates:
            result = FSPManager._coerce_value(created_at_col, date_str)
            assert isinstance(result, datetime)
            assert result.year == 2024
            assert result.month == 1
            assert result.day == 15


def test_coerce_value_with_pytype_cache():
    """Test that coerce_value works with cached pytype."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine):
        query = select(HeroOptimization)
        columns = query.selected_columns
        age_col = columns["age"]

        # Get the pytype once
        pytype = int

        # Coerce with cached pytype
        result = FSPManager._coerce_value(age_col, "42", pytype)
        assert result == 42
        assert isinstance(result, int)

        # Test with different values using cached pytype
        result = FSPManager._coerce_value(age_col, "100", pytype)
        assert result == 100


def test_column_type_caching():
    """Test that column types are cached in FSPManager."""
    from unittest.mock import Mock

    from fastapi_fsp.models import PaginationQuery

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine):
        query = select(HeroOptimization)
        columns = query.selected_columns
        age_col = columns["age"]

        # Create FSPManager instance
        request = Mock()
        request.url = "http://example.com/items"
        pagination = PaginationQuery(page=1, per_page=20)
        fsp = FSPManager(request=request, filters=None, sorting=None, pagination=pagination)

        # Get column type (should cache it)
        pytype1 = fsp._get_column_type(age_col)
        assert pytype1 is int

        # Get column type again (should use cache)
        pytype2 = fsp._get_column_type(age_col)
        assert pytype2 is int
        assert pytype1 is pytype2

        # Verify cache has the entry
        col_id = id(age_col)
        assert col_id in fsp._type_cache
        assert fsp._type_cache[col_id] is int


def test_build_filter_condition():
    """Test that _build_filter_condition creates correct conditions."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine):
        query = select(HeroOptimization)
        columns = query.selected_columns
        age_col = columns["age"]
        name_col = columns["name"]
        columns["active"]

        # Test EQ condition
        condition = FSPManager._build_filter_condition(
            age_col, Filter(field="age", operator=FilterOperator.EQ, value="30")
        )
        assert condition is not None

        # Test GT condition
        condition = FSPManager._build_filter_condition(
            age_col, Filter(field="age", operator=FilterOperator.GT, value="25")
        )
        assert condition is not None

        # Test ILIKE condition
        condition = FSPManager._build_filter_condition(
            name_col, Filter(field="name", operator=FilterOperator.ILIKE, value="%hero%")
        )
        assert condition is not None

        # Test IS_NULL condition
        condition = FSPManager._build_filter_condition(
            age_col, Filter(field="age", operator=FilterOperator.IS_NULL, value="")
        )
        assert condition is not None

        # Test BETWEEN with valid values
        condition = FSPManager._build_filter_condition(
            age_col, Filter(field="age", operator=FilterOperator.BETWEEN, value="20,40")
        )
        assert condition is not None

        # Test BETWEEN with invalid values (should return None)
        condition = FSPManager._build_filter_condition(
            age_col, Filter(field="age", operator=FilterOperator.BETWEEN, value="20")
        )
        assert condition is None


def test_batch_filter_application():
    """Test that multiple filters are applied in batch."""
    from unittest.mock import Mock

    from fastapi_fsp.models import PaginationQuery

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # Add test data
        heroes = [
            HeroOptimization(name="HeroOptimization1", age=25, active=True),
            HeroOptimization(name="HeroOptimization2", age=35, active=True),
            HeroOptimization(name="HeroOptimization3", age=45, active=False),
        ]
        session.add_all(heroes)
        session.commit()

        query = select(HeroOptimization)
        columns = query.selected_columns

        # Create FSPManager with multiple filters
        request = Mock()
        request.url = "http://example.com/items"
        pagination = PaginationQuery(page=1, per_page=20)

        filters = [
            Filter(field="age", operator=FilterOperator.GTE, value="30"),
            Filter(field="active", operator=FilterOperator.EQ, value="true"),
        ]

        fsp = FSPManager(request=request, filters=filters, sorting=None, pagination=pagination)

        # Apply filters
        filtered_query = fsp._apply_filters(query, columns, filters)

        # Execute query
        results = session.exec(filtered_query).all()

        # Should only return HeroOptimization2 (age >= 30 and active=True)
        assert len(results) == 1
        assert results[0].name == "HeroOptimization2"
        assert results[0].age == 35
        assert results[0].active is True


def test_coerce_value_boolean_variations():
    """Test boolean coercion with various string representations."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine):
        query = select(HeroOptimization)
        columns = query.selected_columns
        active_col = columns["active"]

        # Test various true values
        true_values = ["true", "True", "TRUE", "1", "yes", "Yes", "y", "Y", "t", "T"]
        for val in true_values:
            result = FSPManager._coerce_value(active_col, val)
            assert result is True, f"Failed for value: {val}"

        # Test various false values
        false_values = ["false", "False", "FALSE", "0", "no", "No", "n", "N", "f", "F"]
        for val in false_values:
            result = FSPManager._coerce_value(active_col, val)
            assert result is False, f"Failed for value: {val}"


def test_coerce_value_integer_with_float_string():
    """Test integer coercion handles float strings like '1.0'."""
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine):
        query = select(HeroOptimization)
        columns = query.selected_columns
        age_col = columns["age"]

        # Test float string to int
        result = FSPManager._coerce_value(age_col, "42.0")
        assert result == 42
        assert isinstance(result, int)

        # Test normal int string
        result = FSPManager._coerce_value(age_col, "42")
        assert result == 42
        assert isinstance(result, int)


def test_split_values_with_whitespace():
    """Test that split_values handles whitespace correctly."""
    # Test with spaces
    result = FSPManager._split_values("a, b, c")
    assert result == ["a", "b", "c"]

    # Test without spaces
    result = FSPManager._split_values("a,b,c")
    assert result == ["a", "b", "c"]

    # Test with extra spaces
    result = FSPManager._split_values("a  ,  b  ,  c")
    assert result == ["a", "b", "c"]


def test_filter_condition_with_cached_type():
    """Test that filter conditions use cached types."""
    from unittest.mock import Mock

    from fastapi_fsp.models import PaginationQuery

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    with Session(engine):
        query = select(HeroOptimization)
        columns = query.selected_columns
        age_col = columns["age"]

        # Create FSPManager instance
        request = Mock()
        request.url = "http://example.com/items"
        pagination = PaginationQuery(page=1, per_page=20)
        fsp = FSPManager(request=request, filters=None, sorting=None, pagination=pagination)

        # Get and cache the type
        pytype = fsp._get_column_type(age_col)

        # Build filter condition with cached type
        condition = FSPManager._build_filter_condition(
            age_col, Filter(field="age", operator=FilterOperator.EQ, value="30"), pytype
        )
        assert condition is not None
