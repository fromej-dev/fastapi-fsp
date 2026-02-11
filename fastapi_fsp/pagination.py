"""Pagination engine with optional PostgreSQL window function optimization."""

from collections import namedtuple
from math import ceil
from typing import Any, Optional, Tuple

from fastapi import Request
from sqlalchemy import Select, func, over
from sqlmodel import Session, select
from sqlmodel.ext.asyncio.session import AsyncSession

from fastapi_fsp.models import (
    Links,
    Meta,
    PaginatedResponse,
    Pagination,
    PaginationQuery,
)


def _detect_postgresql(session: Any) -> bool:
    """
    Detect if the session is connected to a PostgreSQL database.

    Args:
        session: Database session (sync or async)

    Returns:
        bool: True if the database dialect is PostgreSQL
    """
    try:
        bind = getattr(session, "bind", None)
        if bind is not None:
            return bind.dialect.name == "postgresql"
        # For async sessions, try to get the bind from the sync session
        sync_session = getattr(session, "sync_session", None)
        if sync_session is not None:
            bind = getattr(sync_session, "bind", None)
            if bind is not None:
                return bind.dialect.name == "postgresql"
    except Exception:
        pass
    return False


class PaginationEngine:
    """
    Engine for paginating queries and building paginated responses.

    Supports an optional PostgreSQL window function optimization that combines
    the data query and count query into a single database round-trip using
    ``COUNT(*) OVER()`` instead of issuing a separate count subquery.

    The optimization is auto-detected based on the database dialect, or
    can be explicitly enabled/disabled.
    """

    def __init__(
        self,
        pagination: PaginationQuery,
        request: Request,
        use_window_function: Optional[bool] = None,
    ):
        """
        Initialize PaginationEngine.

        Args:
            pagination: Pagination parameters (page, per_page)
            request: FastAPI Request object (for building HATEOAS links)
            use_window_function: Force window function usage on/off.
                None = auto-detect based on database dialect (enabled for PostgreSQL).
        """
        self.pagination = pagination
        self.request = request
        self.use_window_function = use_window_function

    def _should_use_window_function(self, session: Any) -> bool:
        """Determine whether to use window function optimization."""
        if self.use_window_function is not None:
            return self.use_window_function
        return _detect_postgresql(session)

    # --- Sync methods ---

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

    def count_total(self, query: Select, session: Session) -> int:
        """
        Count total items matching the query.

        Args:
            query: SQLAlchemy Select query with filters applied
            session: Database session

        Returns:
            int: Total count of items
        """
        return self._count_total_static(query, session)

    @staticmethod
    def _count_total_static(query: Select, session: Session) -> int:
        """Static count method for backward compatibility with FSPManager."""
        count_query = select(func.count()).select_from(query.subquery())
        return session.exec(count_query).one()

    def paginate_with_count(self, query: Select, session: Session) -> Tuple[Any, int]:
        """
        Paginate and count in a single or dual query depending on the database.

        When using PostgreSQL with window function optimization enabled, this
        executes a single query with ``COUNT(*) OVER()`` to get both the page
        data and total count. Otherwise, falls back to separate count + paginate.

        Args:
            query: SQLAlchemy Select query (with filters/sort already applied)
            session: Database session

        Returns:
            Tuple[Any, int]: (page_data, total_count)
        """
        if self._should_use_window_function(session):
            return self._paginate_with_window(query, session)

        total = self.count_total(query, session)
        data = self.paginate(query, session)
        return data, total

    def _paginate_with_window(self, query: Select, session: Session) -> Tuple[Any, int]:
        """
        Use PostgreSQL window function to get data + count in one query.

        Generates SQL like:
            SELECT *, COUNT(*) OVER() AS _total_count
            FROM (...) sub
            LIMIT :per_page OFFSET :offset

        Args:
            query: SQLAlchemy Select query
            session: Database session

        Returns:
            Tuple[Any, int]: (page_data, total_count)
        """
        total_count_col = over(func.count()).label("_total_count")
        subq = query.subquery()
        window_query = (
            select(subq, total_count_col)
            .offset((self.pagination.page - 1) * self.pagination.per_page)
            .limit(self.pagination.per_page)
        )

        rows = session.execute(window_query).all()
        if not rows:
            return [], 0

        total = rows[0]._total_count
        # Strip the _total_count column from each row
        if len(rows[0]) == 2:
            data = [row[0] for row in rows]
        else:
            col_names = [k for k in rows[0]._mapping.keys() if k != "_total_count"]
            Row = namedtuple("Row", col_names)
            data = [Row(*(row._mapping[k] for k in col_names)) for row in rows]
        return data, total

    # --- Async methods ---

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

    async def count_total_async(self, query: Select, session: AsyncSession) -> int:
        """
        Count total items matching the query asynchronously.

        Args:
            query: SQLAlchemy Select query with filters applied
            session: Async database session

        Returns:
            int: Total count of items
        """
        return await self._count_total_async_static(query, session)

    @staticmethod
    async def _count_total_async_static(query: Select, session: AsyncSession) -> int:
        """Static async count method for backward compatibility with FSPManager."""
        count_query = select(func.count()).select_from(query.subquery())
        result = await session.exec(count_query)
        return result.one()

    async def paginate_with_count_async(
        self, query: Select, session: AsyncSession
    ) -> Tuple[Any, int]:
        """
        Async version of paginate_with_count.

        Args:
            query: SQLAlchemy Select query
            session: Async database session

        Returns:
            Tuple[Any, int]: (page_data, total_count)
        """
        if self._should_use_window_function(session):
            return await self._paginate_with_window_async(query, session)

        total = await self.count_total_async(query, session)
        data = await self.paginate_async(query, session)
        return data, total

    async def _paginate_with_window_async(
        self, query: Select, session: AsyncSession
    ) -> Tuple[Any, int]:
        """
        Async version of window function pagination.

        Args:
            query: SQLAlchemy Select query
            session: Async database session

        Returns:
            Tuple[Any, int]: (page_data, total_count)
        """
        total_count_col = over(func.count()).label("_total_count")
        subq = query.subquery()
        window_query = (
            select(subq, total_count_col)
            .offset((self.pagination.page - 1) * self.pagination.per_page)
            .limit(self.pagination.per_page)
        )

        result = await session.execute(window_query)
        rows = result.all()
        if not rows:
            return [], 0

        total = rows[0]._total_count
        if len(rows[0]) == 2:
            data = [row[0] for row in rows]
        else:
            col_names = [k for k in rows[0]._mapping.keys() if k != "_total_count"]
            Row = namedtuple("Row", col_names)
            data = [Row(*(row._mapping[k] for k in col_names)) for row in rows]
        return data, total

    # --- Response building ---

    def build_response(
        self,
        total_items: int,
        data_page: Any,
        filters: Any = None,
        sorting: Any = None,
    ) -> PaginatedResponse[Any]:
        """
        Build the final paginated response with HATEOAS links.

        Args:
            total_items: Total number of items matching filters
            data_page: Current page of data
            filters: Active filters (for meta)
            sorting: Active sorting (for meta)

        Returns:
            PaginatedResponse: Final response object
        """
        per_page = self.pagination.per_page
        current_page = self.pagination.page
        total_pages = max(1, ceil(total_items / per_page)) if total_items is not None else 1

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
                filters=filters,
                sort=sorting,
            ),
            links=Links(
                self=self_url,
                first=first_url,
                last=last_url,
                next=next_url,
                prev=prev_url,
            ),
        )
