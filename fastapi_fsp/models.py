"""FastAPI-SQLModel-Pagination models"""

from enum import StrEnum
from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel


class FilterOperator(StrEnum):
    """Filter operators"""

    EQ = "eq"  # equals (=)
    NE = "ne"  # not equals (!=)
    GT = "gt"  # greater than (>)
    GTE = "gte"  # greater than or equal (>=)
    LT = "lt"  # less than (<)
    LTE = "lte"  # less than or equal (<=)

    LIKE = "like"  # case-sensitive LIKE
    NOT_LIKE = "not_like"  # NOT LIKE
    ILIKE = "ilike"  # case-insensitive LIKE (if supported by backend)
    NOT_ILIKE = "not_ilike"  # NOT ILIKE

    IN = "in"  # IN (...)
    NOT_IN = "not_in"  # NOT IN (...)

    BETWEEN = "between"  # BETWEEN x AND y

    IS_NULL = "is_null"  # IS NULL
    IS_NOT_NULL = "is_not_null"  # IS NOT NULL

    STARTS_WITH = "starts_with"  # value%
    ENDS_WITH = "ends_with"  # %value
    CONTAINS = "contains"  # %value%


class SortingOrder(StrEnum):
    """Sorting orders"""

    ASC = "asc"  # ascending order
    DESC = "desc"  # descending order


T = TypeVar("T")


class Filter(BaseModel):
    """Filter model"""

    field: str
    operator: FilterOperator
    value: str


class PaginationQuery(BaseModel):
    """Pagination query model"""

    page: int
    per_page: int


class SortingQuery(BaseModel):
    """Sorting query model"""

    sort_by: str
    order: SortingOrder


class Pagination(BaseModel):
    """Pagination model"""

    total_items: Optional[int] = None
    per_page: int
    current_page: int
    total_pages: Optional[int] = None


class Meta(BaseModel):
    """Meta model"""

    pagination: Pagination
    filters: Optional[List[Filter]] = None
    sort: Optional[SortingQuery] = None


class Links(BaseModel):
    """Links model"""

    self: str
    first: str
    next: Optional[str] = None
    prev: Optional[str] = None
    last: Optional[str] = None


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response model"""

    data: List[T]
    meta: Meta
    links: Links
