"""Filter engine with strategy pattern for operator handling."""

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from dateutil.parser import parse
from fastapi import HTTPException, status
from sqlalchemy import ColumnCollection, ColumnElement, Select, func
from sqlmodel import not_

from fastapi_fsp.models import Filter, FilterOperator

# Type alias for filter strategy functions
FilterStrategyFn = Callable[[ColumnElement[Any], str, Optional[type]], Optional[Any]]


def _coerce_value(column: ColumnElement[Any], raw: str, pytype: Optional[type] = None) -> Any:
    """
    Coerce raw string value to column's Python type.

    Args:
        column: SQLAlchemy column element
        raw: Raw string value
        pytype: Optional pre-fetched python type (for performance)

    Returns:
        Any: Coerced value
    """
    if pytype is None:
        try:
            pytype = getattr(column.type, "python_type", None)
        except Exception:
            pytype = None
    if pytype is None or isinstance(raw, pytype):
        return raw
    if pytype is bool:
        val = raw.strip().lower()
        if val in {"true", "1", "t", "yes", "y"}:
            return True
        if val in {"false", "0", "f", "no", "n"}:
            return False
    if pytype is int:
        try:
            return int(raw)
        except ValueError:
            try:
                return int(float(raw))
            except ValueError:
                return raw
    if pytype is datetime:
        try:
            return datetime.fromisoformat(raw)
        except (ValueError, AttributeError):
            try:
                return parse(raw)
            except ValueError:
                return raw
    try:
        return pytype(raw)
    except Exception:
        return raw


def _split_values(raw: str) -> List[str]:
    """
    Split comma-separated values.

    Args:
        raw: Raw string of comma-separated values

    Returns:
        List[str]: List of stripped values
    """
    return [item.strip() for item in raw.split(",")]


def _ilike_supported(col: ColumnElement[Any]) -> bool:
    """
    Check if ILIKE is supported for this column.

    Args:
        col: SQLAlchemy column element

    Returns:
        bool: True if ILIKE is supported
    """
    return hasattr(col, "ilike")


# --- Strategy functions for each filter operator ---


def _strategy_eq(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    return column == _coerce_value(column, raw, pytype)


def _strategy_ne(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    return column != _coerce_value(column, raw, pytype)


def _strategy_gt(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    return column > _coerce_value(column, raw, pytype)


def _strategy_gte(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    return column >= _coerce_value(column, raw, pytype)


def _strategy_lt(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    return column < _coerce_value(column, raw, pytype)


def _strategy_lte(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    return column <= _coerce_value(column, raw, pytype)


def _strategy_like(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    return column.like(raw)


def _strategy_not_like(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    return not_(column.like(raw))


def _strategy_ilike(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    if _ilike_supported(column):
        return column.ilike(raw)
    return func.lower(column).like(raw.lower())


def _strategy_not_ilike(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    if _ilike_supported(column):
        return not_(column.ilike(raw))
    return not_(func.lower(column).like(raw.lower()))


def _strategy_in(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    vals = [_coerce_value(column, v, pytype) for v in _split_values(raw)]
    return column.in_(vals)


def _strategy_not_in(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    vals = [_coerce_value(column, v, pytype) for v in _split_values(raw)]
    return not_(column.in_(vals))


def _strategy_between(
    column: ColumnElement[Any], raw: str, pytype: Optional[type]
) -> Optional[Any]:
    vals = _split_values(raw)
    if len(vals) == 2:
        low = _coerce_value(column, vals[0], pytype)
        high = _coerce_value(column, vals[1], pytype)
        return column.between(low, high)
    return None


def _strategy_is_null(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    return column.is_(None)


def _strategy_is_not_null(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    return column.is_not(None)


def _strategy_starts_with(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    pattern = f"{raw}%"
    if _ilike_supported(column):
        return column.ilike(pattern)
    return func.lower(column).like(pattern.lower())


def _strategy_ends_with(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    pattern = f"%{raw}"
    if _ilike_supported(column):
        return column.ilike(pattern)
    return func.lower(column).like(pattern.lower())


def _strategy_contains(column: ColumnElement[Any], raw: str, pytype: Optional[type]) -> Any:
    pattern = f"%{raw}%"
    if _ilike_supported(column):
        return column.ilike(pattern)
    return func.lower(column).like(pattern.lower())


# Strategy registry: maps FilterOperator -> handler function
FILTER_STRATEGIES: Dict[FilterOperator, FilterStrategyFn] = {
    FilterOperator.EQ: _strategy_eq,
    FilterOperator.NE: _strategy_ne,
    FilterOperator.GT: _strategy_gt,
    FilterOperator.GTE: _strategy_gte,
    FilterOperator.LT: _strategy_lt,
    FilterOperator.LTE: _strategy_lte,
    FilterOperator.LIKE: _strategy_like,
    FilterOperator.NOT_LIKE: _strategy_not_like,
    FilterOperator.ILIKE: _strategy_ilike,
    FilterOperator.NOT_ILIKE: _strategy_not_ilike,
    FilterOperator.IN: _strategy_in,
    FilterOperator.NOT_IN: _strategy_not_in,
    FilterOperator.BETWEEN: _strategy_between,
    FilterOperator.IS_NULL: _strategy_is_null,
    FilterOperator.IS_NOT_NULL: _strategy_is_not_null,
    FilterOperator.STARTS_WITH: _strategy_starts_with,
    FilterOperator.ENDS_WITH: _strategy_ends_with,
    FilterOperator.CONTAINS: _strategy_contains,
}


class FilterEngine:
    """
    Engine for building and applying SQL filter conditions.

    Uses the strategy pattern to dispatch filter operations by operator type,
    replacing monolithic if/elif chains with a registry of handler functions.

    Custom strategies can be registered to extend or override operators.
    """

    def __init__(self, strict_mode: bool = False):
        """
        Initialize FilterEngine.

        Args:
            strict_mode: If True, raise errors for unknown fields
        """
        self.strict_mode = strict_mode
        self._type_cache: dict[int, Optional[type]] = {}

    def get_column_type(self, column: ColumnElement[Any]) -> Optional[type]:
        """
        Get the Python type of a column with caching.

        Args:
            column: SQLAlchemy column element

        Returns:
            Optional[type]: Python type of the column or None
        """
        col_id = id(column)
        if col_id not in self._type_cache:
            try:
                self._type_cache[col_id] = getattr(column.type, "python_type", None)
            except (AttributeError, NotImplementedError):
                self._type_cache[col_id] = None
        return self._type_cache[col_id]

    @staticmethod
    def get_entity_attribute(query: Select, field: str) -> Optional[ColumnElement[Any]]:
        """
        Try to get a column-like attribute from the query's entity.

        This enables filtering/sorting on computed fields like hybrid_property
        that have SQL expressions defined.

        Args:
            query: SQLAlchemy Select query
            field: Name of the field/attribute to get

        Returns:
            Optional[ColumnElement]: The SQL expression if available, None otherwise
        """
        try:
            column_descriptions = query.column_descriptions
            if not column_descriptions:
                return None

            entity = column_descriptions[0].get("entity")
            if entity is None:
                return None

            attr = getattr(entity, field, None)
            if attr is None:
                return None

            if isinstance(attr, ColumnElement):
                return attr

            if hasattr(attr, "__clause_element__"):
                return attr.__clause_element__()

            return None
        except Exception:
            return None

    @staticmethod
    def build_filter_condition(
        column: ColumnElement[Any], f: Filter, pytype: Optional[type] = None
    ) -> Optional[Any]:
        """
        Build a filter condition using strategy pattern dispatch.

        Args:
            column: Column to apply filter to
            f: Filter to apply
            pytype: Optional pre-fetched python type (for performance)

        Returns:
            Optional[Any]: SQLAlchemy condition or None if invalid/unknown operator
        """
        strategy = FILTER_STRATEGIES.get(f.operator)
        if strategy is None:
            return None
        return strategy(column, f.value, pytype)

    def apply_filters(
        self,
        query: Select,
        columns_map: ColumnCollection[str, ColumnElement[Any]],
        filters: Optional[List[Filter]],
    ) -> Select:
        """
        Apply filters to a query.

        Args:
            query: Base SQLAlchemy Select query
            columns_map: Map of column names to column elements
            filters: List of filters to apply

        Returns:
            Select: Query with filters applied

        Raises:
            HTTPException: If strict_mode is True and unknown field is encountered
        """
        if not filters:
            return query

        conditions = []
        for f in filters:
            column = columns_map.get(f.field)

            if column is None:
                column = self.get_entity_attribute(query, f.field)

            if column is None:
                if self.strict_mode:
                    available = ", ".join(sorted(columns_map.keys()))
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Unknown field '{f.field}'. Available fields: {available}",
                    )
                continue

            pytype = self.get_column_type(column)
            condition = self.build_filter_condition(column, f, pytype)
            if condition is not None:
                conditions.append(condition)

        if conditions:
            query = query.where(*conditions)

        return query

    @staticmethod
    def register_strategy(operator: FilterOperator, strategy: FilterStrategyFn) -> None:
        """
        Register a custom filter strategy for an operator.

        This allows extending or overriding the built-in filter strategies.

        Args:
            operator: The FilterOperator to register for
            strategy: A callable with signature (column, raw_value, pytype) -> condition

        Example:
            def my_custom_eq(column, raw, pytype):
                return column == raw  # Skip type coercion

            FilterEngine.register_strategy(FilterOperator.EQ, my_custom_eq)
        """
        FILTER_STRATEGIES[operator] = strategy
