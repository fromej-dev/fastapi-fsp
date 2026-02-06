"""FilterBuilder API for creating filters with a fluent interface."""

from datetime import date, datetime
from typing import List, Optional, Union

from fastapi_fsp.models import Filter, FilterOperator


class FieldBuilder:
    """
    Builder for a single field's filter conditions.

    Provides a fluent interface for building filter conditions on a specific field.
    """

    def __init__(self, filter_builder: "FilterBuilder", field: str):
        """
        Initialize FieldBuilder.

        Args:
            filter_builder: Parent FilterBuilder instance
            field: Field name to build filters for
        """
        self._filter_builder = filter_builder
        self._field = field

    def _add_filter(self, operator: FilterOperator, value: str) -> "FilterBuilder":
        """Add a filter and return the parent builder."""
        self._filter_builder._filters.append(
            Filter(field=self._field, operator=operator, value=value)
        )
        return self._filter_builder

    @staticmethod
    def _to_str(value: Union[str, int, float, bool, date, datetime]) -> str:
        """Convert a value to string representation."""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    def eq(self, value: Union[str, int, float, bool, date, datetime]) -> "FilterBuilder":
        """
        Equal to (=).

        Args:
            value: Value to compare against

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        return self._add_filter(FilterOperator.EQ, self._to_str(value))

    def ne(self, value: Union[str, int, float, bool, date, datetime]) -> "FilterBuilder":
        """
        Not equal to (!=).

        Args:
            value: Value to compare against

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        return self._add_filter(FilterOperator.NE, self._to_str(value))

    def gt(self, value: Union[str, int, float, date, datetime]) -> "FilterBuilder":
        """
        Greater than (>).

        Args:
            value: Value to compare against

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        return self._add_filter(FilterOperator.GT, self._to_str(value))

    def gte(self, value: Union[str, int, float, date, datetime]) -> "FilterBuilder":
        """
        Greater than or equal to (>=).

        Args:
            value: Value to compare against

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        return self._add_filter(FilterOperator.GTE, self._to_str(value))

    def lt(self, value: Union[str, int, float, date, datetime]) -> "FilterBuilder":
        """
        Less than (<).

        Args:
            value: Value to compare against

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        return self._add_filter(FilterOperator.LT, self._to_str(value))

    def lte(self, value: Union[str, int, float, date, datetime]) -> "FilterBuilder":
        """
        Less than or equal to (<=).

        Args:
            value: Value to compare against

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        return self._add_filter(FilterOperator.LTE, self._to_str(value))

    def like(self, pattern: str) -> "FilterBuilder":
        """
        Case-sensitive LIKE pattern match.

        Args:
            pattern: LIKE pattern (use % for wildcards)

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        return self._add_filter(FilterOperator.LIKE, pattern)

    def not_like(self, pattern: str) -> "FilterBuilder":
        """
        Case-sensitive NOT LIKE pattern match.

        Args:
            pattern: LIKE pattern (use % for wildcards)

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        return self._add_filter(FilterOperator.NOT_LIKE, pattern)

    def ilike(self, pattern: str) -> "FilterBuilder":
        """
        Case-insensitive LIKE pattern match.

        Args:
            pattern: LIKE pattern (use % for wildcards)

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        return self._add_filter(FilterOperator.ILIKE, pattern)

    def not_ilike(self, pattern: str) -> "FilterBuilder":
        """
        Case-insensitive NOT LIKE pattern match.

        Args:
            pattern: LIKE pattern (use % for wildcards)

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        return self._add_filter(FilterOperator.NOT_ILIKE, pattern)

    def in_(self, values: List[Union[str, int, float, bool, date, datetime]]) -> "FilterBuilder":
        """
        IN list of values.

        Args:
            values: List of values to match against

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        str_values = ",".join(self._to_str(v) for v in values)
        return self._add_filter(FilterOperator.IN, str_values)

    def not_in(self, values: List[Union[str, int, float, bool, date, datetime]]) -> "FilterBuilder":
        """
        NOT IN list of values.

        Args:
            values: List of values to exclude

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        str_values = ",".join(self._to_str(v) for v in values)
        return self._add_filter(FilterOperator.NOT_IN, str_values)

    def between(
        self,
        low: Union[str, int, float, date, datetime],
        high: Union[str, int, float, date, datetime],
    ) -> "FilterBuilder":
        """
        BETWEEN low AND high (inclusive).

        Args:
            low: Lower bound
            high: Upper bound

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        value = f"{self._to_str(low)},{self._to_str(high)}"
        return self._add_filter(FilterOperator.BETWEEN, value)

    def is_null(self) -> "FilterBuilder":
        """
        IS NULL check.

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        return self._add_filter(FilterOperator.IS_NULL, "")

    def is_not_null(self) -> "FilterBuilder":
        """
        IS NOT NULL check.

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        return self._add_filter(FilterOperator.IS_NOT_NULL, "")

    def starts_with(self, prefix: str) -> "FilterBuilder":
        """
        Starts with prefix (case-insensitive).

        Args:
            prefix: String prefix to match

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        return self._add_filter(FilterOperator.STARTS_WITH, prefix)

    def ends_with(self, suffix: str) -> "FilterBuilder":
        """
        Ends with suffix (case-insensitive).

        Args:
            suffix: String suffix to match

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        return self._add_filter(FilterOperator.ENDS_WITH, suffix)

    def contains(self, substring: str) -> "FilterBuilder":
        """
        Contains substring (case-insensitive).

        Args:
            substring: String to search for

        Returns:
            FilterBuilder: Parent builder for chaining
        """
        return self._add_filter(FilterOperator.CONTAINS, substring)


class FilterBuilder:
    """
    Fluent builder for creating filter lists.

    Example usage:
        filters = (
            FilterBuilder()
            .where("age").gte(30)
            .where("city").eq("Chicago")
            .where("deleted").eq(False)
            .build()
        )

    This creates a list of Filter objects that can be used with FSPManager.
    """

    def __init__(self):
        """Initialize an empty FilterBuilder."""
        self._filters: List[Filter] = []

    def where(self, field: str) -> FieldBuilder:
        """
        Start building a filter for a field.

        Args:
            field: Name of the field to filter on

        Returns:
            FieldBuilder: Builder for the field's filter condition
        """
        return FieldBuilder(self, field)

    def add_filter(self, field: str, operator: FilterOperator, value: str) -> "FilterBuilder":
        """
        Add a filter directly.

        Args:
            field: Field name
            operator: Filter operator
            value: Filter value as string

        Returns:
            FilterBuilder: Self for chaining
        """
        self._filters.append(Filter(field=field, operator=operator, value=value))
        return self

    def add_filters(self, filters: List[Filter]) -> "FilterBuilder":
        """
        Add multiple filters at once.

        Args:
            filters: List of Filter objects to add

        Returns:
            FilterBuilder: Self for chaining
        """
        self._filters.extend(filters)
        return self

    def build(self) -> Optional[List[Filter]]:
        """
        Build and return the list of filters.

        Returns:
            Optional[List[Filter]]: List of filters, or None if empty
        """
        return self._filters if self._filters else None

    def __len__(self) -> int:
        """Return the number of filters."""
        return len(self._filters)

    def __bool__(self) -> bool:
        """Return True if there are any filters."""
        return bool(self._filters)
