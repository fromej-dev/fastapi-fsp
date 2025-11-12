import math
from typing import Annotated, Any, List, Optional

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
       ?filters[0][field]=age&filters[0][operator]=gte&filters[0][value]=18&filters[1][field]=name&filters[1][operator]=ilike&filters[1][value]=joy
    2. Simple format:
       ?field=age&operator=gte&value=18&field=name&operator=ilike&value=joy
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
):
    if not sort_by:
        return None
    return SortingQuery(sort_by=sort_by, order=order)


def _parse_pagination(
    page: Optional[int] = Query(1, ge=1, description="Page number"),
    per_page: Optional[int] = Query(10, ge=1, le=100, description="Items per page"),
) -> PaginationQuery:
    return PaginationQuery(page=page, per_page=per_page)


class FSPManager:
    def __init__(
        self,
        request: Request,
        filters: Annotated[List[Filter], Depends(_parse_filters)],
        sorting: Annotated[SortingQuery, Depends(_parse_sort)],
        pagination: Annotated[PaginationQuery, Depends(_parse_pagination)],
    ):
        self.request = request
        self.filters = filters
        self.sorting = sorting
        self.pagination = pagination

    def paginate(self, query: Select, session: Session) -> Any:
        return session.exec(
            query.offset((self.pagination.page - 1) * self.pagination.per_page).limit(
                self.pagination.per_page
            )
        ).all()

    async def paginate_async(self, query: Select, session: AsyncSession) -> Any:
        result = await session.exec(
            query.offset((self.pagination.page - 1) * self.pagination.per_page).limit(
                self.pagination.per_page
            )
        )
        return result.all()

    def _count_total(self, query: Select, session: Session) -> int:
        # Count the total rows of the given query (with filters/sort applied) ignoring pagination
        count_query = select(func.count()).select_from(query.subquery())
        return session.exec(count_query).one()

    async def _count_total_async(self, query: Select, session: AsyncSession) -> int:
        count_query = select(func.count()).select_from(query.subquery())
        result = await session.exec(count_query)
        return result.one()

    def _apply_filters(
        self,
        query: Select,
        columns_map: ColumnCollection[str, ColumnElement[Any]],
    ) -> Select:
        for f in self.filters:
            # filter of `self.filters` has been validated in the `_parse_filters`
            column = columns_map.get(f.field)
            # Skip unknown fields silently
            if column is not None:
                query = FSPManager._apply_filter(query, column, f)

        return query

    def _apply_sort(
        self,
        query: Select,
        columns_map: ColumnCollection[str, ColumnElement[Any]],
    ) -> Select:
        column = columns_map.get(self.sorting.sort_by)
        # Unknown sort column; skip sorting
        if column is not None:
            query = query.order_by(
                column.desc() if self.sorting.order == SortingOrder.DESC else column.asc()
            )
        return query

    def generate_response(self, query: Select, session: Session) -> PaginatedResponse[Any]:
        columns_map = query.selected_columns
        if self.filters:
            query = self._apply_filters(query, columns_map)
        if self.sorting:
            query = self._apply_sort(query, columns_map)

        total_items = self._count_total(query, session)
        per_page = self.pagination.per_page
        current_page = self.pagination.page
        total_pages = max(1, math.ceil(total_items / per_page)) if total_items is not None else 1

        data_page = self.paginate(query, session)

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

    async def generate_response_async(
        self, query: Select, session: AsyncSession
    ) -> PaginatedResponse[Any]:
        columns_map = query.selected_columns
        if self.filters:
            query = self._apply_filters(query, columns_map)
        if self.sorting and self.sorting.sort_by:
            query = self._apply_sort(query, columns_map)

        total_items = await self._count_total_async(query, session)
        per_page = self.pagination.per_page
        current_page = self.pagination.page
        total_pages = max(1, math.ceil(total_items / per_page)) if total_items is not None else 1

        data_page = await self.paginate_async(query, session)

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
    def coerce_value(column, raw):
        # Try to coerce raw (str or other) to the column's python type for proper comparisons
        try:
            pytype = getattr(column.type, "python_type", None)
        except Exception:
            pytype = None
        if pytype is None or raw is None:
            return raw
        if isinstance(raw, pytype):
            return raw
        # Handle booleans represented as strings
        if pytype is bool and isinstance(raw, str):
            val = raw.strip().lower()
            if val in {"true", "1", "t", "yes", "y"}:
                return True
            if val in {"false", "0", "f", "no", "n"}:
                return False
        # Generic cast with fallback
        try:
            return pytype(raw)
        except Exception:
            return raw

    @staticmethod
    def split_values(raw):
        if raw is None:
            return []
        if isinstance(raw, (list, tuple)):
            return list(raw)
        if isinstance(raw, str):
            return [item.strip() for item in raw.split(",")]
        return [raw]

    @staticmethod
    def ilike_supported(col):
        return hasattr(col, "ilike")

    @staticmethod
    def _apply_filter(query: Select, column: ColumnElement[Any], f: Filter):
        op = str(f.operator).lower() if f.operator is not None else "eq"
        raw_value = f.value

        # Build conditions based on operator
        if op == "eq":
            query = query.where(column == FSPManager.coerce_value(column, raw_value))
        elif op == "ne":
            query = query.where(column != FSPManager.coerce_value(column, raw_value))
        elif op == "gt":
            query = query.where(column > FSPManager.coerce_value(column, raw_value))
        elif op == "gte":
            query = query.where(column >= FSPManager.coerce_value(column, raw_value))
        elif op == "lt":
            query = query.where(column < FSPManager.coerce_value(column, raw_value))
        elif op == "lte":
            query = query.where(column <= FSPManager.coerce_value(column, raw_value))
        elif op == "like":
            query = query.where(column.like(str(raw_value)))
        elif op == "not_like":
            query = query.where(not_(column.like(str(raw_value))))
        elif op == "ilike":
            pattern = str(raw_value)
            if FSPManager.ilike_supported(column):
                query = query.where(column.ilike(pattern))
            else:
                query = query.where(func.lower(column).like(pattern.lower()))
        elif op == "not_ilike":
            pattern = str(raw_value)
            if FSPManager.ilike_supported(column):
                query = query.where(not_(column.ilike(pattern)))
            else:
                query = query.where(not_(func.lower(column).like(pattern.lower())))
        elif op == "in":
            vals = [FSPManager.coerce_value(column, v) for v in FSPManager.split_values(raw_value)]
            query = query.where(column.in_(vals))
        elif op == "not_in":
            vals = [FSPManager.coerce_value(column, v) for v in FSPManager.split_values(raw_value)]
            query = query.where(not_(column.in_(vals)))
        elif op == "between":
            vals = FSPManager.split_values(raw_value)
            if len(vals) == 2:
                # Ignore malformed between; alternatively raise 400
                low = FSPManager.coerce_value(column, vals[0])
                high = FSPManager.coerce_value(column, vals[1])
                query = query.where(column.between(low, high))
        elif op == "is_null":
            query = query.where(column.is_(None))
        elif op == "is_not_null":
            query = query.where(column.is_not(None))
        elif op == "starts_with":
            pattern = f"{str(raw_value)}%"
            if FSPManager.ilike_supported(column):
                query = query.where(column.ilike(pattern))
            else:
                query = query.where(func.lower(column).like(pattern.lower()))
        elif op == "ends_with":
            pattern = f"%{str(raw_value)}"
            if FSPManager.ilike_supported(column):
                query = query.where(column.ilike(pattern))
            else:
                query = query.where(func.lower(column).like(pattern.lower()))
        elif op == "contains":
            pattern = f"%{str(raw_value)}%"
            if FSPManager.ilike_supported(column):
                query = query.where(column.ilike(pattern))
            else:
                query = query.where(func.lower(column).like(pattern.lower()))
        else:
            # Unknown operator: skip
            pass
        return query
