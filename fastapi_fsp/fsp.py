"""FastAPI-SQLModel-Pagination module"""

from datetime import datetime
from math import ceil
from typing import Annotated, Any, List, Optional

from dateutil.parser import parse
from fastapi import Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy import ColumnCollection, ColumnElement, Select, func
from sqlmodel import Session, not_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_fsp.models import (
    Filter,
    FilterOperator,
    Links,
    Meta,
    PaginatedResponse,
    Pagination,
    PaginationQuery,
    SortingOrder,
    SortingQuery,
)


def _parse_one_filter_at(i: int, field: str, operator: str, value: str) -> Filter:
    """
    Parse a single filter with comprehensive validation.

    Args:
        i: Index of the filter
        field: Field name to filter on
        operator: Filter operator
        value: Filter value

    Returns:
        Filter: Parsed filter object

    Raises:
        HTTPException: If filter parameters are invalid
    """
    try:
        filter_ = Filter(field=field, operator=FilterOperator(operator), value=value)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid filter at index {i}: {str(e)}",
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid operator '{operator}' at index {i}.",
        ) from e
    return filter_


def _parse_array_of_filters(
    fields: List[str], operators: List[str], values: List[str]
) -> List[Filter]:
    """
    Parse filters from array format parameters.

    Args:
        fields: List of field names
        operators: List of operators
        values: List of values

    Returns:
        List[Filter]: List of parsed filters

    Raises:
        HTTPException: If parameters are mismatched or invalid
    """
    # Validate that we have matching lengths
    if not (len(fields) == len(operators) == len(values)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mismatched filter parameters in array format.",
        )
    return [
        _parse_one_filter_at(i, field, operator, value)
        for i, (field, operator, value) in enumerate(zip(fields, operators, values))
    ]


def _parse_filters(
    request: Request,
) -> Optional[List[Filter]]:
    """
    Parse filters from query parameters supporting two formats:
    1. Indexed format:
       ?filters[0][field]=age&filters[0][operator]=gte&filters[0][value]=18
       &filters[1][field]=name&filters[1][operator]=ilike&filters[1][value]=joy
    2. Simple format:
       ?field=age&operator=gte&value=18&field=name&operator=ilike&value=joy

    Args:
        request: FastAPI Request object containing query parameters

    Returns:
        Optional[List[Filter]]: List of parsed filters or None if no filters
    """
    query_params = request.query_params
    filters = []

    # Try indexed format first: filters[0][field], filters[0][operator], etc.
    i = 0
    while True:
        field_key = f"filters[{i}][field]"
        operator_key = f"filters[{i}][operator]"
        value_key = f"filters[{i}][value]"

        field = query_params.get(field_key)
        operator = query_params.get(operator_key)
        value = query_params.get(value_key)

        # If we don't have a field at this index, break the loop
        if field is None:
            break

        # Validate that we have all required parts
        if operator is None or value is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Incomplete filter at index {i}. Missing operator or value.",
            )

        filters.append(_parse_one_filter_at(i, field, operator, value))
        i += 1

    # If we found indexed filters, return them
    if filters:
        return filters

    # Fall back to simple format: field, operator, value
    filters = _parse_array_of_filters(
        query_params.getlist("field"),
        query_params.getlist("operator"),
        query_params.getlist("value"),
    )
    if filters:
        return filters

    # No filters found
    return None


def _parse_sort(
    sort_by: Optional[str] = Query(None, alias="sort_by"),
    order: Optional[SortingOrder] = Query(SortingOrder.ASC, alias="order"),
) -> Optional[SortingQuery]:
    """
    Parse sorting parameters from query parameters.

    Args:
        sort_by: Field to sort by
        order: Sorting order (ASC or DESC)

    Returns:
        Optional[SortingQuery]: Parsed sorting query or None if no sorting
    """
    if not sort_by:
        return None
    return SortingQuery(sort_by=sort_by, order=order)


def _parse_pagination(
    page: Optional[int] = Query(1, ge=1, description="Page number"),
    per_page: Optional[int] = Query(10, ge=1, le=100, description="Items per page"),
) -> PaginationQuery:
    """
    Parse pagination parameters from query parameters.

    Args:
        page: Page number (>= 1)
        per_page: Number of items per page (1-100)

    Returns:
        PaginationQuery: Parsed pagination query
    """
    return PaginationQuery(page=page, per_page=per_page)


class FSPManager:
    """
    FastAPI Filtering, Sorting, and Pagination Manager.

    Handles parsing query parameters and applying them to SQLModel queries.
    """

    def __init__(
        self,
        request: Request,
        filters: Annotated[Optional[List[Filter]], Depends(_parse_filters)],
        sorting: Annotated[Optional[SortingQuery], Depends(_parse_sort)],
        pagination: Annotated[PaginationQuery, Depends(_parse_pagination)],
        strict_mode: bool = False,
    ):
        """
        Initialize FSPManager.

        Args:
            request: FastAPI Request object
            filters: Parsed filters
            sorting: Sorting configuration
            pagination: Pagination configuration
            strict_mode: If True, raise errors for unknown fields instead of silently skipping
        """
        self.request = request
        self.filters = filters
        self.sorting = sorting
        self.pagination = pagination
        self.strict_mode = strict_mode
        self._type_cache: dict[int, Optional[type]] = {}

    def _get_column_type(self, column: ColumnElement[Any]) -> Optional[type]:
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
            except Exception:
                self._type_cache[col_id] = None
        return self._type_cache[col_id]

    def paginate(self, query: Select, session: Session) -> Any:
        """
        Execute pagination on a query.

        Args:
            query: SQLAlchemy Select query
            session: Database session

        Returns:
            Any: Query results
        """
        return session.exec(
            query.offset((self.pagination.page - 1) * self.pagination.per_page).limit(
                self.pagination.per_page
            )
        ).all()

    async def paginate_async(self, query: Select, session: AsyncSession) -> Any:
        """
        Execute pagination on a query asynchronously.

        Args:
            query: SQLAlchemy Select query
            session: Async database session

        Returns:
            Any: Query results
        """
        result = await session.exec(
            query.offset((self.pagination.page - 1) * self.pagination.per_page).limit(
                self.pagination.per_page
            )
        )
        return result.all()

    def generate_response(self, query: Select, session: Session) -> PaginatedResponse[Any]:
        """
        Generate a complete paginated response.

        Args:
            query: Base SQLAlchemy Select query
            session: Database session

        Returns:
            PaginatedResponse: Complete paginated response
        """
        columns_map = query.selected_columns
        query = self._apply_filters(query, columns_map, self.filters)
        query = self._apply_sort(query, columns_map, self.sorting)

        total_items = self._count_total(query, session)
        data_page = self.paginate(query, session)
        return self._generate_response(total_items=total_items, data_page=data_page)

    async def generate_response_async(
        self, query: Select, session: AsyncSession
    ) -> PaginatedResponse[Any]:
        """
        Generate a complete paginated response asynchronously.

        Args:
            query: Base SQLAlchemy Select query
            session: Async database session

        Returns:
            PaginatedResponse: Complete paginated response
        """
        columns_map = query.selected_columns
        query = self._apply_filters(query, columns_map, self.filters)
        query = self._apply_sort(query, columns_map, self.sorting)

        total_items = await self._count_total_async(query, session)
        data_page = await self.paginate_async(query, session)
        return self._generate_response(total_items=total_items, data_page=data_page)

    def _generate_response(self, total_items: int, data_page: Any) -> PaginatedResponse[Any]:
        """
        Generate the final paginated response object.

        Args:
            total_items: Total number of items matching filters
            data_page: Current page of data

        Returns:
            PaginatedResponse: Final response object
        """
        per_page = self.pagination.per_page
        current_page = self.pagination.page
        total_pages = max(1, ceil(total_items / per_page)) if total_items is not None else 1

        # Build links based on current URL, replacing/adding page and per_page parameters
        url = self.request.url
        first_url = str(url.include_query_params(page=1, per_page=per_page))
        last_url = str(url.include_query_params(page=total_pages, per_page=per_page))
        next_url = (
            str(url.include_query_params(page=current_page + 1, per_page=per_page))
            if current_page < total_pages
            else None
        )
        prev_url = (
            str(url.include_query_params(page=current_page - 1, per_page=per_page))
            if current_page > 1
            else None
        )
        self_url = str(url.include_query_params(page=current_page, per_page=per_page))

        return PaginatedResponse(
            data=data_page,
            meta=Meta(
                pagination=Pagination(
                    total_items=total_items,
                    per_page=per_page,
                    current_page=current_page,
                    total_pages=total_pages,
                ),
                filters=self.filters,
                sort=self.sorting,
            ),
            links=Links(
                self=self_url,
                first=first_url,
                last=last_url,
                next=next_url,
                prev=prev_url,
            ),
        )

    @staticmethod
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
        # Try to coerce raw (str) to the column's python type for proper comparisons
        if pytype is None:
            try:
                pytype = getattr(column.type, "python_type", None)
            except Exception:
                pytype = None
        if pytype is None or isinstance(raw, pytype):
            return raw
        # Handle booleans represented as strings
        if pytype is bool:
            val = raw.strip().lower()
            if val in {"true", "1", "t", "yes", "y"}:
                return True
            if val in {"false", "0", "f", "no", "n"}:
                return False
        # Handle integers represented as strings
        if pytype is int:
            try:
                return int(raw)
            except ValueError:
                # Handle common cases like "1.0"
                try:
                    return int(float(raw))
                except ValueError:
                    return raw
        # Handle dates represented as strings - optimized with fast path for ISO 8601
        if pytype is datetime:
            try:
                # Fast path for ISO 8601 format (most common)
                return datetime.fromisoformat(raw)
            except (ValueError, AttributeError):
                # Fallback to flexible dateutil parser for other formats
                try:
                    return parse(raw)
                except ValueError:
                    return raw
        # Generic cast with fallback
        try:
            return pytype(raw)
        except Exception:
            return raw

    @staticmethod
    def _split_values(raw: str) -> List[str]:
        """
        Split comma-separated values.

        Args:
            raw: Raw string of comma-separated values

        Returns:
            List[str]: List of stripped values
        """
        return [item.strip() for item in raw.split(",")]

    @staticmethod
    def _ilike_supported(col: ColumnElement[Any]) -> bool:
        """
        Check if ILIKE is supported for this column.

        Args:
            col: SQLAlchemy column element

        Returns:
            bool: True if ILIKE is supported
        """
        return hasattr(col, "ilike")

    @staticmethod
    def _build_filter_condition(
        column: ColumnElement[Any], f: Filter, pytype: Optional[type] = None
    ) -> Optional[Any]:
        """
        Build a filter condition for a query.

        Args:
            column: Column to apply filter to
            f: Filter to apply
            pytype: Optional pre-fetched python type (for performance)

        Returns:
            Optional[Any]: SQLAlchemy condition or None if invalid
        """
        op = f.operator  # type: FilterOperator
        raw_value = f.value  # type: str

        # Build conditions based on operator
        if op == FilterOperator.EQ:
            return column == FSPManager._coerce_value(column, raw_value, pytype)
        elif op == FilterOperator.NE:
            return column != FSPManager._coerce_value(column, raw_value, pytype)
        elif op == FilterOperator.GT:
            return column > FSPManager._coerce_value(column, raw_value, pytype)
        elif op == FilterOperator.GTE:
            return column >= FSPManager._coerce_value(column, raw_value, pytype)
        elif op == FilterOperator.LT:
            return column < FSPManager._coerce_value(column, raw_value, pytype)
        elif op == FilterOperator.LTE:
            return column <= FSPManager._coerce_value(column, raw_value, pytype)
        elif op == FilterOperator.LIKE:
            return column.like(raw_value)
        elif op == FilterOperator.NOT_LIKE:
            return not_(column.like(raw_value))
        elif op == FilterOperator.ILIKE:
            pattern = raw_value
            if FSPManager._ilike_supported(column):
                return column.ilike(pattern)
            else:
                return func.lower(column).like(pattern.lower())
        elif op == FilterOperator.NOT_ILIKE:
            pattern = raw_value
            if FSPManager._ilike_supported(column):
                return not_(column.ilike(pattern))
            else:
                return not_(func.lower(column).like(pattern.lower()))
        elif op == FilterOperator.IN:
            vals = [
                FSPManager._coerce_value(column, v, pytype)
                for v in FSPManager._split_values(raw_value)
            ]
            return column.in_(vals)
        elif op == FilterOperator.NOT_IN:
            vals = [
                FSPManager._coerce_value(column, v, pytype)
                for v in FSPManager._split_values(raw_value)
            ]
            return not_(column.in_(vals))
        elif op == FilterOperator.BETWEEN:
            vals = FSPManager._split_values(raw_value)
            if len(vals) == 2:
                low = FSPManager._coerce_value(column, vals[0], pytype)
                high = FSPManager._coerce_value(column, vals[1], pytype)
                return column.between(low, high)
            # Ignore malformed between
            return None
        elif op == FilterOperator.IS_NULL:
            return column.is_(None)
        elif op == FilterOperator.IS_NOT_NULL:
            return column.is_not(None)
        elif op == FilterOperator.STARTS_WITH:
            pattern = f"{raw_value}%"
            if FSPManager._ilike_supported(column):
                return column.ilike(pattern)
            else:
                return func.lower(column).like(pattern.lower())
        elif op == FilterOperator.ENDS_WITH:
            pattern = f"%{raw_value}"
            if FSPManager._ilike_supported(column):
                return column.ilike(pattern)
            else:
                return func.lower(column).like(pattern.lower())
        elif op == FilterOperator.CONTAINS:
            pattern = f"%{raw_value}%"
            if FSPManager._ilike_supported(column):
                return column.ilike(pattern)
            else:
                return func.lower(column).like(pattern.lower())
        # Unknown operator
        return None

    @staticmethod
    def _count_total(query: Select, session: Session) -> int:
        """
        Count total items matching the query.

        Args:
            query: SQLAlchemy Select query with filters applied
            session: Database session

        Returns:
            int: Total count of items
        """
        # Count the total rows of the given query (with filters/sort applied) ignoring pagination
        count_query = select(func.count()).select_from(query.subquery())
        return session.exec(count_query).one()

    @staticmethod
    async def _count_total_async(query: Select, session: AsyncSession) -> int:
        """
        Count total items matching the query asynchronously.

        Args:
            query: SQLAlchemy Select query with filters applied
            session: Async database session

        Returns:
            int: Total count of items
        """
        count_query = select(func.count()).select_from(query.subquery())
        result = await session.exec(count_query)
        return result.one()

    def _apply_filters(
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
            # filter of `filters` has been validated in the `_parse_filters`
            column = columns_map.get(f.field)
            if column is None:
                if self.strict_mode:
                    available = ", ".join(sorted(columns_map.keys()))
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Unknown field '{f.field}'. Available fields: {available}",
                    )
                # Skip unknown fields silently in non-strict mode
                continue

            # Get column type from cache for better performance
            pytype = self._get_column_type(column)
            condition = FSPManager._build_filter_condition(column, f, pytype)
            if condition is not None:
                conditions.append(condition)

        # Apply all conditions in a single where() call for better SQL generation
        if conditions:
            query = query.where(*conditions)

        return query

    def _apply_sort(
        self,
        query: Select,
        columns_map: ColumnCollection[str, ColumnElement[Any]],
        sorting: Optional[SortingQuery],
    ) -> Select:
        """
        Apply sorting to a query.

        Args:
            query: Base SQLAlchemy Select query
            columns_map: Map of column names to column elements
            sorting: Sorting configuration

        Returns:
            Select: Query with sorting applied

        Raises:
            HTTPException: If strict_mode is True and unknown sort field is encountered
        """
        if sorting and sorting.sort_by:
            column = columns_map.get(sorting.sort_by)
            if column is None:
                try:
                    column = getattr(query.column_descriptions[0]["entity"], sorting.sort_by, None)
                except Exception:
                    pass

            if column is None:
                if self.strict_mode:
                    available = ", ".join(sorted(columns_map.keys()))
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            f"Unknown sort field '{sorting.sort_by}'. Available fields: {available}"
                        ),
                    )
                # Unknown sort column; skip sorting in non-strict mode
                return query

            query = query.order_by(
                column.desc() if sorting.order == SortingOrder.DESC else column.asc()
            )
        return query
