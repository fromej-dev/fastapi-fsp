"""Common filter presets for frequently used query patterns."""

from datetime import datetime, timedelta
from typing import List

from fastapi_fsp.models import Filter, FilterOperator


class CommonFilters:
    """
    Pre-defined filter presets for common query patterns.

    These presets help reduce boilerplate for frequently used filter combinations.

    Example usage:
        from fastapi_fsp.presets import CommonFilters

        # Get active (non-deleted) records
        filters = CommonFilters.active()

        # Get records from last 7 days
        filters = CommonFilters.recent(days=7)

        # Combine presets
        filters = CommonFilters.active() + CommonFilters.recent(days=30)
    """

    @staticmethod
    def active(deleted_field: str = "deleted") -> List[Filter]:
        """
        Filter for active (non-deleted) records.

        Args:
            deleted_field: Name of the boolean deleted field (default: "deleted")

        Returns:
            List[Filter]: Filters for non-deleted records
        """
        return [Filter(field=deleted_field, operator=FilterOperator.EQ, value="false")]

    @staticmethod
    def deleted(deleted_field: str = "deleted") -> List[Filter]:
        """
        Filter for deleted records only.

        Args:
            deleted_field: Name of the boolean deleted field (default: "deleted")

        Returns:
            List[Filter]: Filters for deleted records
        """
        return [Filter(field=deleted_field, operator=FilterOperator.EQ, value="true")]

    @staticmethod
    def recent(
        date_field: str = "created_at",
        days: int = 30,
        reference_time: datetime = None,
    ) -> List[Filter]:
        """
        Filter for records created in the last N days.

        Args:
            date_field: Name of the datetime field (default: "created_at")
            days: Number of days to look back (default: 30)
            reference_time: Reference time for calculation (default: now)

        Returns:
            List[Filter]: Filters for recent records
        """
        if reference_time is None:
            reference_time = datetime.now()
        cutoff = (reference_time - timedelta(days=days)).isoformat()
        return [Filter(field=date_field, operator=FilterOperator.GTE, value=cutoff)]

    @staticmethod
    def older_than(
        date_field: str = "created_at",
        days: int = 30,
        reference_time: datetime = None,
    ) -> List[Filter]:
        """
        Filter for records created more than N days ago.

        Args:
            date_field: Name of the datetime field (default: "created_at")
            days: Number of days threshold (default: 30)
            reference_time: Reference time for calculation (default: now)

        Returns:
            List[Filter]: Filters for older records
        """
        if reference_time is None:
            reference_time = datetime.now()
        cutoff = (reference_time - timedelta(days=days)).isoformat()
        return [Filter(field=date_field, operator=FilterOperator.LT, value=cutoff)]

    @staticmethod
    def date_range(
        date_field: str = "created_at",
        start: datetime = None,
        end: datetime = None,
    ) -> List[Filter]:
        """
        Filter for records within a date range.

        Args:
            date_field: Name of the datetime field (default: "created_at")
            start: Start of date range (inclusive)
            end: End of date range (inclusive)

        Returns:
            List[Filter]: Filters for date range

        Raises:
            ValueError: If neither start nor end is provided
        """
        if start is None and end is None:
            raise ValueError("At least one of start or end must be provided")

        filters = []
        if start is not None:
            filters.append(
                Filter(field=date_field, operator=FilterOperator.GTE, value=start.isoformat())
            )
        if end is not None:
            filters.append(
                Filter(field=date_field, operator=FilterOperator.LTE, value=end.isoformat())
            )
        return filters

    @staticmethod
    def today(date_field: str = "created_at", reference_time: datetime = None) -> List[Filter]:
        """
        Filter for records created today.

        Args:
            date_field: Name of the datetime field (default: "created_at")
            reference_time: Reference time for calculation (default: now)

        Returns:
            List[Filter]: Filters for today's records
        """
        if reference_time is None:
            reference_time = datetime.now()
        start_of_day = reference_time.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = reference_time.replace(hour=23, minute=59, second=59, microsecond=999999)
        return [
            Filter(
                field=date_field,
                operator=FilterOperator.BETWEEN,
                value=f"{start_of_day.isoformat()},{end_of_day.isoformat()}",
            )
        ]

    @staticmethod
    def not_null(field: str) -> List[Filter]:
        """
        Filter for records where field is not null.

        Args:
            field: Name of the field to check

        Returns:
            List[Filter]: Filter for non-null values
        """
        return [Filter(field=field, operator=FilterOperator.IS_NOT_NULL, value="")]

    @staticmethod
    def is_null(field: str) -> List[Filter]:
        """
        Filter for records where field is null.

        Args:
            field: Name of the field to check

        Returns:
            List[Filter]: Filter for null values
        """
        return [Filter(field=field, operator=FilterOperator.IS_NULL, value="")]

    @staticmethod
    def enabled(enabled_field: str = "enabled") -> List[Filter]:
        """
        Filter for enabled records.

        Args:
            enabled_field: Name of the boolean enabled field (default: "enabled")

        Returns:
            List[Filter]: Filters for enabled records
        """
        return [Filter(field=enabled_field, operator=FilterOperator.EQ, value="true")]

    @staticmethod
    def disabled(enabled_field: str = "enabled") -> List[Filter]:
        """
        Filter for disabled records.

        Args:
            enabled_field: Name of the boolean enabled field (default: "enabled")

        Returns:
            List[Filter]: Filters for disabled records
        """
        return [Filter(field=enabled_field, operator=FilterOperator.EQ, value="false")]

    @staticmethod
    def search(
        field: str,
        term: str,
        match_type: str = "contains",
    ) -> List[Filter]:
        """
        Create a search filter for text matching.

        Args:
            field: Name of the field to search
            term: Search term
            match_type: Type of match - "contains", "starts_with", "ends_with" (default: "contains")

        Returns:
            List[Filter]: Search filter

        Raises:
            ValueError: If match_type is invalid
        """
        operator_map = {
            "contains": FilterOperator.CONTAINS,
            "starts_with": FilterOperator.STARTS_WITH,
            "ends_with": FilterOperator.ENDS_WITH,
        }
        operator = operator_map.get(match_type)
        if operator is None:
            valid_types = "contains, starts_with, ends_with"
            raise ValueError(f"Invalid match_type: {match_type}. Use: {valid_types}")
        return [Filter(field=field, operator=operator, value=term)]

    @staticmethod
    def in_values(field: str, values: List) -> List[Filter]:
        """
        Filter for records where field is in a list of values.

        Args:
            field: Name of the field to filter
            values: List of values to match

        Returns:
            List[Filter]: IN filter
        """
        str_values = ",".join(str(v) for v in values)
        return [Filter(field=field, operator=FilterOperator.IN, value=str_values)]

    @staticmethod
    def not_in_values(field: str, values: List) -> List[Filter]:
        """
        Filter for records where field is not in a list of values.

        Args:
            field: Name of the field to filter
            values: List of values to exclude

        Returns:
            List[Filter]: NOT IN filter
        """
        str_values = ",".join(str(v) for v in values)
        return [Filter(field=field, operator=FilterOperator.NOT_IN, value=str_values)]
