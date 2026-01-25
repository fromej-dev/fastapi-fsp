"""Tests for FilterBuilder fluent API."""

from datetime import date, datetime

from fastapi_fsp.builder import FilterBuilder
from fastapi_fsp.models import Filter, FilterOperator


class TestFilterBuilder:
    """Tests for FilterBuilder class."""

    def test_empty_builder(self):
        """Test empty builder returns None."""
        builder = FilterBuilder()
        assert builder.build() is None
        assert len(builder) == 0
        assert not builder

    def test_single_eq_filter(self):
        """Test building a single EQ filter."""
        filters = FilterBuilder().where("age").eq(30).build()

        assert filters is not None
        assert len(filters) == 1
        assert filters[0].field == "age"
        assert filters[0].operator == FilterOperator.EQ
        assert filters[0].value == "30"

    def test_single_ne_filter(self):
        """Test building a single NE filter."""
        filters = FilterBuilder().where("status").ne("inactive").build()

        assert filters is not None
        assert len(filters) == 1
        assert filters[0].operator == FilterOperator.NE
        assert filters[0].value == "inactive"

    def test_comparison_operators(self):
        """Test GT, GTE, LT, LTE operators."""
        filters = (
            FilterBuilder()
            .where("age")
            .gt(18)
            .where("score")
            .gte(90)
            .where("price")
            .lt(100)
            .where("quantity")
            .lte(50)
            .build()
        )

        assert len(filters) == 4
        assert filters[0].operator == FilterOperator.GT
        assert filters[0].value == "18"
        assert filters[1].operator == FilterOperator.GTE
        assert filters[1].value == "90"
        assert filters[2].operator == FilterOperator.LT
        assert filters[2].value == "100"
        assert filters[3].operator == FilterOperator.LTE
        assert filters[3].value == "50"

    def test_like_operators(self):
        """Test LIKE pattern operators."""
        filters = (
            FilterBuilder()
            .where("name")
            .like("%John%")
            .where("email")
            .not_like("%spam%")
            .where("title")
            .ilike("%manager%")
            .where("desc")
            .not_ilike("%test%")
            .build()
        )

        assert len(filters) == 4
        assert filters[0].operator == FilterOperator.LIKE
        assert filters[1].operator == FilterOperator.NOT_LIKE
        assert filters[2].operator == FilterOperator.ILIKE
        assert filters[3].operator == FilterOperator.NOT_ILIKE

    def test_in_operator(self):
        """Test IN operator with list of values."""
        filters = FilterBuilder().where("status").in_(["active", "pending", "review"]).build()

        assert len(filters) == 1
        assert filters[0].operator == FilterOperator.IN
        assert filters[0].value == "active,pending,review"

    def test_not_in_operator(self):
        """Test NOT IN operator."""
        filters = FilterBuilder().where("id").not_in([1, 2, 3]).build()

        assert len(filters) == 1
        assert filters[0].operator == FilterOperator.NOT_IN
        assert filters[0].value == "1,2,3"

    def test_between_operator(self):
        """Test BETWEEN operator."""
        filters = FilterBuilder().where("price").between(10, 100).build()

        assert len(filters) == 1
        assert filters[0].operator == FilterOperator.BETWEEN
        assert filters[0].value == "10,100"

    def test_null_operators(self):
        """Test IS NULL and IS NOT NULL operators."""
        filters = (
            FilterBuilder().where("deleted_at").is_null().where("created_at").is_not_null().build()
        )

        assert len(filters) == 2
        assert filters[0].operator == FilterOperator.IS_NULL
        assert filters[1].operator == FilterOperator.IS_NOT_NULL

    def test_text_match_operators(self):
        """Test starts_with, ends_with, contains operators."""
        filters = (
            FilterBuilder()
            .where("name")
            .starts_with("John")
            .where("email")
            .ends_with("@example.com")
            .where("description")
            .contains("important")
            .build()
        )

        assert len(filters) == 3
        assert filters[0].operator == FilterOperator.STARTS_WITH
        assert filters[0].value == "John"
        assert filters[1].operator == FilterOperator.ENDS_WITH
        assert filters[1].value == "@example.com"
        assert filters[2].operator == FilterOperator.CONTAINS
        assert filters[2].value == "important"

    def test_boolean_conversion(self):
        """Test boolean value conversion."""
        filters = FilterBuilder().where("active").eq(True).where("deleted").eq(False).build()

        assert filters[0].value == "true"
        assert filters[1].value == "false"

    def test_datetime_conversion(self):
        """Test datetime value conversion."""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        filters = FilterBuilder().where("created_at").gte(dt).build()

        assert filters[0].value == "2024-01-15T10:30:00"

    def test_date_conversion(self):
        """Test date value conversion."""
        d = date(2024, 1, 15)
        filters = FilterBuilder().where("birth_date").eq(d).build()

        assert filters[0].value == "2024-01-15"

    def test_float_conversion(self):
        """Test float value conversion."""
        filters = FilterBuilder().where("price").gte(99.99).build()

        assert filters[0].value == "99.99"

    def test_chaining_multiple_fields(self):
        """Test chaining filters on multiple fields."""
        filters = (
            FilterBuilder()
            .where("age")
            .gte(18)
            .where("city")
            .eq("New York")
            .where("active")
            .eq(True)
            .where("score")
            .between(80, 100)
            .build()
        )

        assert len(filters) == 4
        assert filters[0].field == "age"
        assert filters[1].field == "city"
        assert filters[2].field == "active"
        assert filters[3].field == "score"

    def test_add_filter_direct(self):
        """Test adding filter directly."""
        builder = FilterBuilder()
        builder.add_filter("age", FilterOperator.GTE, "21")
        filters = builder.build()

        assert len(filters) == 1
        assert filters[0].field == "age"
        assert filters[0].operator == FilterOperator.GTE
        assert filters[0].value == "21"

    def test_add_filters_bulk(self):
        """Test adding multiple filters at once."""
        existing_filters = [
            Filter(field="age", operator=FilterOperator.GTE, value="18"),
            Filter(field="city", operator=FilterOperator.EQ, value="NYC"),
        ]
        filters = FilterBuilder().add_filters(existing_filters).where("active").eq(True).build()

        assert len(filters) == 3

    def test_builder_len(self):
        """Test __len__ method."""
        builder = FilterBuilder().where("a").eq(1).where("b").eq(2)
        assert len(builder) == 2

    def test_builder_bool(self):
        """Test __bool__ method."""
        empty_builder = FilterBuilder()
        assert not empty_builder

        filled_builder = FilterBuilder().where("a").eq(1)
        assert filled_builder

    def test_in_with_integers(self):
        """Test IN with integer list."""
        filters = FilterBuilder().where("id").in_([1, 2, 3, 4, 5]).build()
        assert filters[0].value == "1,2,3,4,5"

    def test_in_with_booleans(self):
        """Test IN with boolean list."""
        filters = FilterBuilder().where("flag").in_([True, False]).build()
        assert filters[0].value == "true,false"

    def test_between_with_dates(self):
        """Test BETWEEN with date values."""
        start = date(2024, 1, 1)
        end = date(2024, 12, 31)
        filters = FilterBuilder().where("date").between(start, end).build()

        assert filters[0].value == "2024-01-01,2024-12-31"

    def test_between_with_datetimes(self):
        """Test BETWEEN with datetime values."""
        start = datetime(2024, 1, 1, 0, 0, 0)
        end = datetime(2024, 12, 31, 23, 59, 59)
        filters = FilterBuilder().where("timestamp").between(start, end).build()

        assert "2024-01-01T00:00:00" in filters[0].value
        assert "2024-12-31T23:59:59" in filters[0].value
