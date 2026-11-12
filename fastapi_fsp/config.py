"""Configuration classes for fastapi-fsp."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import FrozenSet, Optional, Union

from pydantic import BaseModel

from fastapi_fsp.models import SearchBackend

#: Field names that clients cannot filter, sort or search on when that
#: operation has no allowlist.
DEFAULT_DENIED_FIELDS: FrozenSet[str] = frozenset({"password", "password_hash", "secret"})

FieldAllowlist = Union[Iterable[str], type[BaseModel]]
"""Field names, or a pydantic/SQLModel class whose fields and computed fields are allowed."""


def _to_field_set(name: str, value: Optional[FieldAllowlist]) -> Optional[FrozenSet[str]]:
    """Normalize an allowlist option to a frozenset of field names."""
    if value is None:
        return None
    if isinstance(value, type) and issubclass(value, BaseModel):
        return frozenset(value.model_fields) | frozenset(value.model_computed_fields)
    if isinstance(value, str):
        raise ValueError(f"{name} must be a collection of field names, not a single string")
    fields = frozenset(value)
    if not all(isinstance(f, str) for f in fields):
        raise ValueError(f"{name} must contain only field names (str)")
    return fields


@dataclass
class FSPConfig:
    """
    Configuration for FSP behavior.

    This class centralizes all configuration options for the FSPManager,
    making it easier to customize behavior across your application.

    Attributes:
        max_per_page: Maximum allowed items per page (default: 100)
        default_per_page: Default items per page when not specified (default: 10)
        default_page: Default page number when not specified (default: 1)
        strict_mode: If True, raise errors for unknown fields (default: False)
        allow_deep_pagination: If True, allow pagination to any page (default: True)
        max_page: Maximum allowed page number, None for unlimited (default: None)
        min_per_page: Minimum allowed items per page (default: 1)
        allowed_fields: Field names clients may filter, search and sort on, or a
            pydantic/SQLModel class whose fields and computed fields are allowed.
            None (default) allows every column of the queried model.
        filterable_fields: Overrides allowed_fields for filters
        sortable_fields: Overrides allowed_fields for sort_by
        searchable_fields: Overrides allowed_fields for search_fields
        denied_fields: Field names refused for an operation that has no allowlist
            (default: ``DEFAULT_DENIED_FIELDS``: password, password_hash, secret)
        use_window_function: Force the PostgreSQL window-function count on or off.
            None (default) auto-detects.

    Example:
        config = FSPConfig(
            max_per_page=500,
            default_per_page=25,
            allowed_fields=ItemPublic,
        )
        fsp_dep = FSPManager.depends(config)

        @app.get("/items/")
        def read_items(fsp: Annotated[FSPManager, Depends(fsp_dep)]):
            ...
    """

    # Pagination settings
    max_per_page: int = 100
    default_per_page: int = 10
    default_page: int = 1
    min_per_page: int = 1

    # Validation settings
    strict_mode: bool = False

    # Deep pagination settings
    allow_deep_pagination: bool = True
    max_page: Optional[int] = None

    # Search backend settings
    search_backend: SearchBackend = SearchBackend.ILIKE
    max_search_tokens: int = 10

    # Field allowlists (None = no restriction)
    allowed_fields: Optional[FieldAllowlist] = None
    filterable_fields: Optional[FieldAllowlist] = None
    sortable_fields: Optional[FieldAllowlist] = None
    searchable_fields: Optional[FieldAllowlist] = None
    denied_fields: Iterable[str] = DEFAULT_DENIED_FIELDS

    # Query execution settings
    use_window_function: Optional[bool] = None

    # Reserved for future features
    _extra: dict = field(default_factory=dict)

    def __post_init__(self):
        """Validate configuration values."""
        if self.max_per_page < 1:
            raise ValueError("max_per_page must be >= 1")
        if self.default_per_page < 1:
            raise ValueError("default_per_page must be >= 1")
        if self.default_per_page > self.max_per_page:
            raise ValueError("default_per_page cannot exceed max_per_page")
        if self.min_per_page < 1:
            raise ValueError("min_per_page must be >= 1")
        if self.min_per_page > self.max_per_page:
            raise ValueError("min_per_page cannot exceed max_per_page")
        if self.default_page < 1:
            raise ValueError("default_page must be >= 1")
        if self.max_page is not None and self.max_page < 1:
            raise ValueError("max_page must be >= 1 or None")
        if self.max_search_tokens < 1:
            raise ValueError("max_search_tokens must be >= 1")
        for name in ("allowed_fields", "filterable_fields", "sortable_fields", "searchable_fields"):
            setattr(self, name, _to_field_set(name, getattr(self, name)))
        if isinstance(self.denied_fields, type):
            raise ValueError("denied_fields must be a collection of field names")
        self.denied_fields = _to_field_set("denied_fields", self.denied_fields)

    @property
    def effective_filterable_fields(self) -> Optional[FrozenSet[str]]:
        """Fields allowed in filters, or None for no restriction."""
        return self.filterable_fields if self.filterable_fields is not None else self.allowed_fields

    @property
    def effective_sortable_fields(self) -> Optional[FrozenSet[str]]:
        """Fields allowed in sort_by, or None for no restriction."""
        return self.sortable_fields if self.sortable_fields is not None else self.allowed_fields

    @property
    def effective_searchable_fields(self) -> Optional[FrozenSet[str]]:
        """Fields allowed in search_fields, or None for no restriction."""
        return self.searchable_fields if self.searchable_fields is not None else self.allowed_fields

    def allows_filter(self, field_name: str) -> bool:
        """Return True if clients may filter on ``field_name``."""
        return self._allows(field_name, self.effective_filterable_fields)

    def allows_sort(self, field_name: str) -> bool:
        """Return True if clients may sort on ``field_name``."""
        return self._allows(field_name, self.effective_sortable_fields)

    def allows_search(self, field_name: str) -> bool:
        """Return True if clients may search on ``field_name``."""
        return self._allows(field_name, self.effective_searchable_fields)

    def _allows(self, field_name: str, allowlist: Optional[FrozenSet[str]]) -> bool:
        if allowlist is not None:
            return field_name in allowlist
        return field_name not in self.denied_fields

    def validate_page(self, page: int) -> int:
        """
        Validate and constrain a page number.

        Args:
            page: Requested page number

        Returns:
            int: Valid page number

        Raises:
            ValueError: If page exceeds max_page and allow_deep_pagination is False
        """
        if page < 1:
            return self.default_page

        if not self.allow_deep_pagination and self.max_page is not None:
            if page > self.max_page:
                raise ValueError(f"Page {page} exceeds maximum allowed page {self.max_page}")

        return page

    def validate_per_page(self, per_page: int) -> int:
        """
        Validate and constrain items per page.

        Args:
            per_page: Requested items per page

        Returns:
            int: Valid per_page value, constrained to min/max bounds
        """
        if per_page < self.min_per_page:
            return self.min_per_page
        if per_page > self.max_per_page:
            return self.max_per_page
        return per_page


# Pre-defined configurations for common use cases
class FSPPresets:
    """Pre-defined FSPConfig presets for common use cases."""

    @staticmethod
    def default() -> FSPConfig:
        """Default configuration with sensible defaults."""
        return FSPConfig()

    @staticmethod
    def strict() -> FSPConfig:
        """Strict mode configuration - raises errors for unknown fields."""
        return FSPConfig(strict_mode=True)

    @staticmethod
    def limited_pagination(max_page: int = 100, max_per_page: int = 50) -> FSPConfig:
        """
        Configuration that limits deep pagination.

        Args:
            max_page: Maximum allowed page number
            max_per_page: Maximum items per page
        """
        return FSPConfig(
            max_page=max_page,
            max_per_page=max_per_page,
            allow_deep_pagination=False,
        )

    @staticmethod
    def high_volume(max_per_page: int = 500, default_per_page: int = 100) -> FSPConfig:
        """
        Configuration for high-volume APIs.

        Args:
            max_per_page: Maximum items per page
            default_per_page: Default items per page
        """
        return FSPConfig(
            max_per_page=max_per_page,
            default_per_page=default_per_page,
        )
