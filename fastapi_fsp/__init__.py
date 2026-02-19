"""fastapi-fsp: Filter, Sort, and Paginate utilities for FastAPI + SQLModel."""

from . import models as models  # noqa: F401
from .builder import FieldBuilder, FilterBuilder  # noqa: F401
from .config import FSPConfig, FSPPresets  # noqa: F401
from .filters import FILTER_STRATEGIES, FilterEngine  # noqa: F401
from .fsp import FSPManager  # noqa: F401
from .models import (  # noqa: F401
    Filter,
    FilterOperator,
    Links,
    Meta,
    OrFilterGroup,
    PaginatedResponse,
    Pagination,
    PaginationQuery,
    SortingOrder,
    SortingQuery,
)
from .pagination import PaginationEngine  # noqa: F401
from .presets import CommonFilters  # noqa: F401
from .sorting import SortEngine  # noqa: F401

__all__ = [
    # Main class
    "FSPManager",
    # Engines
    "FilterEngine",
    "SortEngine",
    "PaginationEngine",
    # Strategy registry
    "FILTER_STRATEGIES",
    # Builder
    "FilterBuilder",
    "FieldBuilder",
    # Configuration
    "FSPConfig",
    "FSPPresets",
    # Presets
    "CommonFilters",
    # Models
    "Filter",
    "FilterOperator",
    "OrFilterGroup",
    "SortingOrder",
    "SortingQuery",
    "PaginationQuery",
    "Pagination",
    "Meta",
    "Links",
    "PaginatedResponse",
    # Module
    "models",
]
