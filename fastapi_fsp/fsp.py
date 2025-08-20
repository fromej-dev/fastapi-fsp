import math
from typing import Annotated, Any, List, Optional

from fastapi import Depends, HTTPException, Query, Request, status
from sqlalchemy import Select, func
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


def _parse_filters(
    fields: Optional[List[str]] = Query(None, alias="field"),
    operators: Optional[List[FilterOperator]] = Query(None, alias="operator"),
    values: Optional[List[str]] = Query(None, alias="value"),
) -> List[Filter] | None:
    if not fields:
        return None
    filters: List[Filter] = []
    if operators is None or values is None or not (len(fields) == len(operators) == len(values)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mismatched filter parameters.",
        )
    for field, operator, value in zip(fields, operators, values):
        filters.append(Filter(field=field, operator=operator, value=value))
    return filters


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

    def _apply_filters(self, query: Select) -> Select:
        # Helper: build a map of column name -> column object from the select statement
        try:
            columns_map = {
                col.key: col for col in query.selected_columns
            }  # SQLAlchemy 1.4+ ColumnCollection is iterable
        except Exception:
            columns_map = {}

        if not self.filters:
            return query

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

        def split_values(raw):
            if raw is None:
                return []
            if isinstance(raw, (list, tuple)):
                return list(raw)
            if isinstance(raw, str):
                return [item.strip() for item in raw.split(",")]
            return [raw]

        def ilike_supported(col):
            return hasattr(col, "ilike")

        for f in self.filters:
            if not f or not f.field:
                continue

            column = columns_map.get(f.field)
            if column is None:
                # Skip unknown fields silently
                continue

            op = str(f.operator).lower() if f.operator is not None else "eq"
            raw_value = f.value

            # Build conditions based on operator
            if op == "eq":
                query = query.where(column == coerce_value(column, raw_value))
            elif op == "ne":
                query = query.where(column != coerce_value(column, raw_value))
            elif op == "gt":
                query = query.where(column > coerce_value(column, raw_value))
            elif op == "gte":
                query = query.where(column >= coerce_value(column, raw_value))
            elif op == "lt":
                query = query.where(column < coerce_value(column, raw_value))
            elif op == "lte":
                query = query.where(column <= coerce_value(column, raw_value))
            elif op == "like":
                query = query.where(column.like(str(raw_value)))
            elif op == "not_like":
                query = query.where(not_(column.like(str(raw_value))))
            elif op == "ilike":
                pattern = str(raw_value)
                if ilike_supported(column):
                    query = query.where(column.ilike(pattern))
                else:
                    query = query.where(func.lower(column).like(pattern.lower()))
            elif op == "not_ilike":
                pattern = str(raw_value)
                if ilike_supported(column):
                    query = query.where(not_(column.ilike(pattern)))
                else:
                    query = query.where(not_(func.lower(column).like(pattern.lower())))
            elif op == "in":
                vals = [coerce_value(column, v) for v in split_values(raw_value)]
                query = query.where(column.in_(vals))
            elif op == "not_in":
                vals = [coerce_value(column, v) for v in split_values(raw_value)]
                query = query.where(not_(column.in_(vals)))
            elif op == "between":
                vals = split_values(raw_value)
                if len(vals) != 2:
                    # Ignore malformed between; alternatively raise 400
                    continue
                low = coerce_value(column, vals[0])
                high = coerce_value(column, vals[1])
                query = query.where(column.between(low, high))
            elif op == "is_null":
                query = query.where(column.is_(None))
            elif op == "is_not_null":
                query = query.where(column.is_not(None))
            elif op == "starts_with":
                pattern = f"{str(raw_value)}%"
                if ilike_supported(column):
                    query = query.where(column.ilike(pattern))
                else:
                    query = query.where(func.lower(column).like(pattern.lower()))
            elif op == "ends_with":
                pattern = f"%{str(raw_value)}"
                if ilike_supported(column):
                    query = query.where(column.ilike(pattern))
                else:
                    query = query.where(func.lower(column).like(pattern.lower()))
            elif op == "contains":
                pattern = f"%{str(raw_value)}%"
                if ilike_supported(column):
                    query = query.where(column.ilike(pattern))
                else:
                    query = query.where(func.lower(column).like(pattern.lower()))
            else:
                # Unknown operator: skip
                continue

        return query

    def _apply_sort(self, query: Select) -> Select:
        # Build a map of column name -> column object from the select statement
        try:
            columns_map = {col.key: col for col in query.selected_columns}
        except Exception:
            columns_map = {}

        if not self.sorting or not self.sorting.sort_by:
            return query

        column = columns_map.get(self.sorting.sort_by)
        if column is None:
            # Unknown sort column; skip sorting
            return query

        order = str(self.sorting.order).lower() if self.sorting.order else "asc"
        if order == "desc":
            return query.order_by(column.desc())
        else:
            return query.order_by(column.asc())

    def generate_response(self, query: Select, session: Session) -> PaginatedResponse[Any]:
        query = self._apply_filters(query)
        query = self._apply_sort(query)

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
        query = self._apply_filters(query)
        query = self._apply_sort(query)

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
