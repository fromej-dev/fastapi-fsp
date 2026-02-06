"""Sort engine for applying ordering to queries."""

from typing import Any, Optional

from fastapi import HTTPException, status
from sqlalchemy import ColumnCollection, ColumnElement, Select

from fastapi_fsp.filters import FilterEngine
from fastapi_fsp.models import SortingOrder, SortingQuery


class SortEngine:
    """
    Engine for applying sorting to SQL queries.

    Handles column resolution (including computed fields) and sort direction.
    """

    def __init__(self, strict_mode: bool = False):
        """
        Initialize SortEngine.

        Args:
            strict_mode: If True, raise errors for unknown sort fields
        """
        self.strict_mode = strict_mode

    def apply_sort(
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
        if not sorting or not sorting.sort_by:
            return query

        column = columns_map.get(sorting.sort_by)

        # Fall back to computed fields (hybrid_property, etc.)
        if column is None:
            column = FilterEngine.get_entity_attribute(query, sorting.sort_by)

        if column is None:
            if self.strict_mode:
                available = ", ".join(sorted(columns_map.keys()))
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Unknown sort field '{sorting.sort_by}'. Available fields: {available}"
                    ),
                )
            return query

        query = query.order_by(
            column.desc() if sorting.order == SortingOrder.DESC else column.asc()
        )
        return query
