"""FastAPI-SQLModel-Pagination module"""

from typing import Annotated, Any, List, Optional, Type

from fastapi import Depends, HTTPException, Query, Request, status
from pydantic import ValidationError
from sqlalchemy import ColumnCollection, ColumnElement, Select
from sqlmodel import Session, SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_fsp.config import FSPConfig
from fastapi_fsp.filters import FilterEngine, _coerce_value, _is_string_column, _split_values
from fastapi_fsp.models import (
    Filter,
    FilterOperator,
    OrFilterGroup,
    PaginatedResponse,
    PaginationQuery,
    SortingOrder,
    SortingQuery,
)
from fastapi_fsp.pagination import PaginationEngine
from fastapi_fsp.sorting import SortEngine


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


def _parse_search(
    request: Request,
) -> Optional[List[OrFilterGroup]]:
    """
    Parse search parameters from query parameters.

    Supports: ?search=term&search_fields=name,email,city

    This creates an OR filter group that matches the search term against
    each specified field using case-insensitive CONTAINS (ILIKE %term%).

    Args:
        request: FastAPI Request object containing query parameters

    Returns:
        Optional[List[OrFilterGroup]]: List with one OR group, or None

    Raises:
        HTTPException: If search is provided without search_fields
    """
    query_params = request.query_params
    search = query_params.get("search")

    if not search:
        return None

    search_fields_raw = query_params.get("search_fields")
    if not search_fields_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'search_fields' is required when 'search' is provided. "
            "Specify comma-separated field names, e.g. search_fields=name,email",
        )

    fields = [f.strip() for f in search_fields_raw.split(",") if f.strip()]
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'search_fields' must contain at least one field name.",
        )

    filters = [
        Filter(field=field, operator=FilterOperator.CONTAINS, value=search) for field in fields
    ]
    return [OrFilterGroup(filters=filters)]


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

    Orchestrates FilterEngine, SortEngine, and PaginationEngine to handle
    query parameters and apply them to SQLModel queries.

    The FSP pipeline is split into focused engine classes:
    - FilterEngine: Strategy-pattern filter operator dispatch and application
    - SortEngine: Column resolution and sort direction
    - PaginationEngine: Pagination, counting, and response building
      (with optional PostgreSQL window function optimization)
    """

    def __init__(
        self,
        request: Request,
        filters: Annotated[Optional[List[Filter]], Depends(_parse_filters)],
        sorting: Annotated[Optional[SortingQuery], Depends(_parse_sort)],
        pagination: Annotated[PaginationQuery, Depends(_parse_pagination)],
        or_filters: Annotated[Optional[List[OrFilterGroup]], Depends(_parse_search)],
        strict_mode: bool = False,
        use_window_function: Optional[bool] = None,
    ):
        """
        Initialize FSPManager.

        Args:
            request: FastAPI Request object
            filters: Parsed AND filters
            sorting: Sorting configuration
            pagination: Pagination configuration
            or_filters: Parsed OR filter groups (from search params)
            strict_mode: If True, raise errors for unknown fields instead of silently skipping
            use_window_function: Force PostgreSQL window function optimization on/off.
                None = auto-detect (enabled for PostgreSQL, disabled for others).
        """
        self.request = request
        self.filters = filters
        self.or_filters = or_filters
        self.sorting = sorting
        self.pagination = pagination

        # Initialize engines
        self._filter_engine = FilterEngine(strict_mode=strict_mode)
        self._sort_engine = SortEngine(strict_mode=strict_mode)
        self._pagination_engine = PaginationEngine(
            pagination=pagination,
            request=request,
            use_window_function=use_window_function,
        )

    @property
    def strict_mode(self) -> bool:
        """Get strict mode setting."""
        return self._filter_engine.strict_mode

    @strict_mode.setter
    def strict_mode(self, value: bool) -> None:
        """Set strict mode on all engines."""
        self._filter_engine.strict_mode = value
        self._sort_engine.strict_mode = value

    @property
    def _type_cache(self) -> dict:
        """Backward-compatible access to filter engine type cache."""
        return self._filter_engine._type_cache

    def _get_column_type(self, column: ColumnElement[Any]) -> Optional[type]:
        """
        Get the Python type of a column with caching.

        Delegates to FilterEngine.get_column_type().

        Args:
            column: SQLAlchemy column element

        Returns:
            Optional[type]: Python type of the column or None
        """
        return self._filter_engine.get_column_type(column)

    @staticmethod
    def _get_entity_attribute(query: Select, field: str) -> Optional[ColumnElement[Any]]:
        """
        Try to get a column-like attribute from the query's entity.

        Delegates to FilterEngine.get_entity_attribute().

        Args:
            query: SQLAlchemy Select query
            field: Name of the field/attribute to get

        Returns:
            Optional[ColumnElement]: The SQL expression if available, None otherwise
        """
        return FilterEngine.get_entity_attribute(query, field)

    def paginate(self, query: Select, session: Session) -> Any:
        """
        Execute pagination on a query.

        Delegates to PaginationEngine.paginate().

        Args:
            query: SQLAlchemy Select query
            session: Database session

        Returns:
            Any: Query results
        """
        return self._pagination_engine.paginate(query, session)

    async def paginate_async(self, query: Select, session: AsyncSession) -> Any:
        """
        Execute pagination on a query asynchronously.

        Delegates to PaginationEngine.paginate_async().

        Args:
            query: SQLAlchemy Select query
            session: Async database session

        Returns:
            Any: Query results
        """
        return await self._pagination_engine.paginate_async(query, session)

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
        query = self._apply_or_filters(query, columns_map, self.or_filters)
        query = self._apply_sort(query, columns_map, self.sorting)

        data_page, total_items = self._pagination_engine.paginate_with_count(query, session)
        return self._pagination_engine.build_response(
            total_items=total_items,
            data_page=data_page,
            filters=self.filters,
            or_filters=self.or_filters,
            sorting=self.sorting,
        )

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
        query = self._apply_or_filters(query, columns_map, self.or_filters)
        query = self._apply_sort(query, columns_map, self.sorting)

        data_page, total_items = await self._pagination_engine.paginate_with_count_async(
            query, session
        )
        return self._pagination_engine.build_response(
            total_items=total_items,
            data_page=data_page,
            filters=self.filters,
            or_filters=self.or_filters,
            sorting=self.sorting,
        )

    @staticmethod
    def _coerce_value(column: ColumnElement[Any], raw: str, pytype: Optional[type] = None) -> Any:
        """
        Coerce raw string value to column's Python type.

        Delegates to filters._coerce_value().

        Args:
            column: SQLAlchemy column element
            raw: Raw string value
            pytype: Optional pre-fetched python type (for performance)

        Returns:
            Any: Coerced value
        """
        return _coerce_value(column, raw, pytype)

    @staticmethod
    def _split_values(raw: str) -> List[str]:
        """
        Split comma-separated values.

        Delegates to filters._split_values().

        Args:
            raw: Raw string of comma-separated values

        Returns:
            List[str]: List of stripped values
        """
        return _split_values(raw)

    @staticmethod
    def _is_string_column(col: ColumnElement[Any]) -> bool:
        """
        Check if a column has a string type in the database.

        Non-string columns (integer, float, datetime, etc.) need to be cast
        to text before ILIKE/LIKE pattern matching can be applied.

        Delegates to filters._is_string_column().

        Args:
            col: SQLAlchemy column element

        Returns:
            bool: True if the column is a string/text type
        """
        return _is_string_column(col)

    @staticmethod
    def _build_filter_condition(
        column: ColumnElement[Any], f: Filter, pytype: Optional[type] = None
    ) -> Optional[Any]:
        """
        Build a filter condition for a query using strategy pattern dispatch.

        Delegates to FilterEngine.build_filter_condition().

        Args:
            column: Column to apply filter to
            f: Filter to apply
            pytype: Optional pre-fetched python type (for performance)

        Returns:
            Optional[Any]: SQLAlchemy condition or None if invalid
        """
        return FilterEngine.build_filter_condition(column, f, pytype)

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
        return PaginationEngine._count_total_static(query, session)

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
        return await PaginationEngine._count_total_async_static(query, session)

    def _apply_filters(
        self,
        query: Select,
        columns_map: ColumnCollection[str, ColumnElement[Any]],
        filters: Optional[List[Filter]],
    ) -> Select:
        """
        Apply filters to a query.

        Delegates to FilterEngine.apply_filters().

        Args:
            query: Base SQLAlchemy Select query
            columns_map: Map of column names to column elements
            filters: List of filters to apply

        Returns:
            Select: Query with filters applied

        Raises:
            HTTPException: If strict_mode is True and unknown field is encountered
        """
        return self._filter_engine.apply_filters(query, columns_map, filters)

    def _apply_or_filters(
        self,
        query: Select,
        columns_map: ColumnCollection[str, ColumnElement[Any]],
        or_filters: Optional[List[OrFilterGroup]],
    ) -> Select:
        """
        Apply OR filter groups to a query.

        Delegates to FilterEngine.apply_or_filter_groups().

        Args:
            query: Base SQLAlchemy Select query
            columns_map: Map of column names to column elements
            or_filters: List of OR filter groups to apply

        Returns:
            Select: Query with OR filter groups applied

        Raises:
            HTTPException: If strict_mode is True and unknown field is encountered
        """
        return self._filter_engine.apply_or_filter_groups(query, columns_map, or_filters)

    def _apply_sort(
        self,
        query: Select,
        columns_map: ColumnCollection[str, ColumnElement[Any]],
        sorting: Optional[SortingQuery],
    ) -> Select:
        """
        Apply sorting to a query.

        Delegates to SortEngine.apply_sort().

        Args:
            query: Base SQLAlchemy Select query
            columns_map: Map of column names to column elements
            sorting: Sorting configuration

        Returns:
            Select: Query with sorting applied

        Raises:
            HTTPException: If strict_mode is True and unknown sort field is encountered
        """
        return self._sort_engine.apply_sort(query, columns_map, sorting)

    def apply_config(self, config: FSPConfig) -> "FSPManager":
        """
        Apply a configuration to this FSPManager instance.

        Args:
            config: FSPConfig instance with settings

        Returns:
            FSPManager: Self for chaining
        """
        self.strict_mode = config.strict_mode
        # Validate and constrain pagination values
        self.pagination.page = config.validate_page(self.pagination.page)
        self.pagination.per_page = config.validate_per_page(self.pagination.per_page)
        return self

    def from_model(
        self,
        model: Type[SQLModel],
        session: Session,
    ) -> PaginatedResponse[Any]:
        """
        Convenience method to query directly from a model.

        This simplifies the common pattern of selecting all from a model.

        Args:
            model: SQLModel class to query
            session: Database session

        Returns:
            PaginatedResponse: Complete paginated response

        Example:
            @app.get("/heroes/")
            def read_heroes(
                session: Session = Depends(get_session),
                fsp: FSPManager = Depends(FSPManager)
            ):
                return fsp.from_model(Hero, session)
        """
        query = select(model)
        return self.generate_response(query, session)

    async def from_model_async(
        self,
        model: Type[SQLModel],
        session: AsyncSession,
    ) -> PaginatedResponse[Any]:
        """
        Convenience method to query directly from a model (async version).

        This simplifies the common pattern of selecting all from a model.

        Args:
            model: SQLModel class to query
            session: Async database session

        Returns:
            PaginatedResponse: Complete paginated response

        Example:
            @app.get("/heroes/")
            async def read_heroes(
                session: AsyncSession = Depends(get_session),
                fsp: FSPManager = Depends(FSPManager)
            ):
                return await fsp.from_model_async(Hero, session)
        """
        query = select(model)
        return await self.generate_response_async(query, session)

    def with_filters(self, filters: Optional[List[Filter]]) -> "FSPManager":
        """
        Set or override filters.

        Args:
            filters: List of filters to apply

        Returns:
            FSPManager: Self for chaining
        """
        if filters:
            if self.filters:
                self.filters.extend(filters)
            else:
                self.filters = filters
        return self

    def with_or_filters(self, or_filters: Optional[List[OrFilterGroup]]) -> "FSPManager":
        """
        Set or append OR filter groups.

        Args:
            or_filters: List of OR filter groups to apply

        Returns:
            FSPManager: Self for chaining
        """
        if or_filters:
            if self.or_filters:
                self.or_filters.extend(or_filters)
            else:
                self.or_filters = or_filters
        return self

    def with_sorting(self, sorting: Optional[SortingQuery]) -> "FSPManager":
        """
        Set or override sorting.

        Args:
            sorting: Sorting configuration

        Returns:
            FSPManager: Self for chaining
        """
        if sorting:
            self.sorting = sorting
        return self
