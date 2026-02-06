"""Tests for CommonFilters presets."""

from datetime import datetime, timedelta

import pytest
from fastapi_fsp.models import FilterOperator
from fastapi_fsp.presets import CommonFilters


class TestCommonFilters:
    """Tests for CommonFilters class."""

    def test_active_default_field(self):
        """Test active filter with default field name."""
        filters = CommonFilters.active()

        assert len(filters) == 1
        assert filters[0].field == "deleted"
        assert filters[0].operator == FilterOperator.EQ
        assert filters[0].value == "false"

    def test_active_custom_field(self):
        """Test active filter with custom field name."""
        filters = CommonFilters.active(deleted_field="is_deleted")

        assert filters[0].field == "is_deleted"
        assert filters[0].value == "false"

    def test_deleted_default_field(self):
        """Test deleted filter with default field name."""
        filters = CommonFilters.deleted()

        assert len(filters) == 1
        assert filters[0].field == "deleted"
        assert filters[0].operator == FilterOperator.EQ
        assert filters[0].value == "true"

    def test_deleted_custom_field(self):
        """Test deleted filter with custom field name."""
        filters = CommonFilters.deleted(deleted_field="is_removed")

        assert filters[0].field == "is_removed"

    def test_recent_default(self):
        """Test recent filter with default values."""
        reference = datetime(2024, 6, 15, 12, 0, 0)
        filters = CommonFilters.recent(reference_time=reference)

        assert len(filters) == 1
        assert filters[0].field == "created_at"
        assert filters[0].operator == FilterOperator.GTE
        # Should be 30 days before reference time
        expected = (reference - timedelta(days=30)).isoformat()
        assert filters[0].value == expected

    def test_recent_custom_days(self):
        """Test recent filter with custom days."""
        reference = datetime(2024, 6, 15, 12, 0, 0)
        filters = CommonFilters.recent(days=7, reference_time=reference)

        expected = (reference - timedelta(days=7)).isoformat()
        assert filters[0].value == expected

    def test_recent_custom_field(self):
        """Test recent filter with custom field name."""
        now = datetime.now()
        filters = CommonFilters.recent(date_field="updated_at", days=7, reference_time=now)

        assert filters[0].field == "updated_at"

    def test_older_than_default(self):
        """Test older_than filter with default values."""
        reference = datetime(2024, 6, 15, 12, 0, 0)
        filters = CommonFilters.older_than(reference_time=reference)

        assert len(filters) == 1
        assert filters[0].field == "created_at"
        assert filters[0].operator == FilterOperator.LT
        expected = (reference - timedelta(days=30)).isoformat()
        assert filters[0].value == expected

    def test_older_than_custom(self):
        """Test older_than filter with custom values."""
        reference = datetime(2024, 6, 15, 12, 0, 0)
        filters = CommonFilters.older_than(
            date_field="modified_at", days=90, reference_time=reference
        )

        assert filters[0].field == "modified_at"
        expected = (reference - timedelta(days=90)).isoformat()
        assert filters[0].value == expected

    def test_date_range_both_bounds(self):
        """Test date_range with both start and end."""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 12, 31)
        filters = CommonFilters.date_range(start=start, end=end)

        assert len(filters) == 2
        assert filters[0].operator == FilterOperator.GTE
        assert filters[0].value == start.isoformat()
        assert filters[1].operator == FilterOperator.LTE
        assert filters[1].value == end.isoformat()

    def test_date_range_start_only(self):
        """Test date_range with only start."""
        start = datetime(2024, 1, 1)
        filters = CommonFilters.date_range(start=start)

        assert len(filters) == 1
        assert filters[0].operator == FilterOperator.GTE

    def test_date_range_end_only(self):
        """Test date_range with only end."""
        end = datetime(2024, 12, 31)
        filters = CommonFilters.date_range(end=end)

        assert len(filters) == 1
        assert filters[0].operator == FilterOperator.LTE

    def test_date_range_no_bounds_raises(self):
        """Test date_range raises error if no bounds provided."""
        with pytest.raises(ValueError, match="At least one of start or end must be provided"):
            CommonFilters.date_range()

    def test_date_range_custom_field(self):
        """Test date_range with custom field name."""
        start = datetime(2024, 1, 1)
        filters = CommonFilters.date_range(date_field="event_date", start=start)

        assert filters[0].field == "event_date"

    def test_today(self):
        """Test today filter."""
        reference = datetime(2024, 6, 15, 14, 30, 0)
        filters = CommonFilters.today(reference_time=reference)

        assert len(filters) == 1
        assert filters[0].field == "created_at"
        assert filters[0].operator == FilterOperator.BETWEEN
        # Should contain start of day and end of day
        assert "2024-06-15T00:00:00" in filters[0].value
        assert "2024-06-15T23:59:59" in filters[0].value

    def test_today_custom_field(self):
        """Test today filter with custom field."""
        filters = CommonFilters.today(date_field="logged_at", reference_time=datetime.now())

        assert filters[0].field == "logged_at"

    def test_not_null(self):
        """Test not_null filter."""
        filters = CommonFilters.not_null("email")

        assert len(filters) == 1
        assert filters[0].field == "email"
        assert filters[0].operator == FilterOperator.IS_NOT_NULL

    def test_is_null(self):
        """Test is_null filter."""
        filters = CommonFilters.is_null("deleted_at")

        assert len(filters) == 1
        assert filters[0].field == "deleted_at"
        assert filters[0].operator == FilterOperator.IS_NULL

    def test_enabled_default(self):
        """Test enabled filter with default field."""
        filters = CommonFilters.enabled()

        assert len(filters) == 1
        assert filters[0].field == "enabled"
        assert filters[0].operator == FilterOperator.EQ
        assert filters[0].value == "true"

    def test_enabled_custom_field(self):
        """Test enabled filter with custom field."""
        filters = CommonFilters.enabled(enabled_field="is_active")

        assert filters[0].field == "is_active"

    def test_disabled_default(self):
        """Test disabled filter with default field."""
        filters = CommonFilters.disabled()

        assert len(filters) == 1
        assert filters[0].field == "enabled"
        assert filters[0].value == "false"

    def test_disabled_custom_field(self):
        """Test disabled filter with custom field."""
        filters = CommonFilters.disabled(enabled_field="is_active")

        assert filters[0].field == "is_active"

    def test_search_contains(self):
        """Test search filter with contains."""
        filters = CommonFilters.search("name", "john", match_type="contains")

        assert len(filters) == 1
        assert filters[0].field == "name"
        assert filters[0].operator == FilterOperator.CONTAINS
        assert filters[0].value == "john"

    def test_search_starts_with(self):
        """Test search filter with starts_with."""
        filters = CommonFilters.search("name", "john", match_type="starts_with")

        assert filters[0].operator == FilterOperator.STARTS_WITH

    def test_search_ends_with(self):
        """Test search filter with ends_with."""
        filters = CommonFilters.search("email", "@example.com", match_type="ends_with")

        assert filters[0].operator == FilterOperator.ENDS_WITH

    def test_search_default_match_type(self):
        """Test search filter defaults to contains."""
        filters = CommonFilters.search("description", "important")

        assert filters[0].operator == FilterOperator.CONTAINS

    def test_search_invalid_match_type(self):
        """Test search raises error for invalid match_type."""
        with pytest.raises(ValueError, match="Invalid match_type"):
            CommonFilters.search("name", "test", match_type="invalid")

    def test_in_values(self):
        """Test in_values filter."""
        filters = CommonFilters.in_values("status", ["active", "pending", "review"])

        assert len(filters) == 1
        assert filters[0].field == "status"
        assert filters[0].operator == FilterOperator.IN
        assert filters[0].value == "active,pending,review"

    def test_in_values_integers(self):
        """Test in_values filter with integers."""
        filters = CommonFilters.in_values("id", [1, 2, 3, 4, 5])

        assert filters[0].value == "1,2,3,4,5"

    def test_not_in_values(self):
        """Test not_in_values filter."""
        filters = CommonFilters.not_in_values("category", ["spam", "deleted"])

        assert len(filters) == 1
        assert filters[0].field == "category"
        assert filters[0].operator == FilterOperator.NOT_IN
        assert filters[0].value == "spam,deleted"

    def test_combining_filters(self):
        """Test combining multiple filter presets."""
        now = datetime.now()
        filters = CommonFilters.active() + CommonFilters.recent(days=7, reference_time=now)

        assert len(filters) == 2
        assert filters[0].field == "deleted"
        assert filters[1].field == "created_at"

    def test_combining_multiple_presets(self):
        """Test combining many presets."""
        filters = CommonFilters.active() + CommonFilters.enabled() + CommonFilters.not_null("email")

        assert len(filters) == 3
