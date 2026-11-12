"""Configuration classes for fastapi-fsp."""

from dataclasses import dataclass, field
from typing import Collection, FrozenSet, Optional

from fastapi_fsp.models import SearchBackend

#: Field names that cannot be filtered, sorted or searched on unless an
#: allowlist for that operation explicitly includes them.
DEFAULT_DENIED_FIELDS: FrozenSet[str] = frozenset({"password", "password_hash", "secret"})


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
        search_backend: Backend used for ``search`` queries (default: ILIKE)
        max_search_tokens: Maximum number of search tokens; extra tokens are dropped
        filterable_fields: Fields clients may filter on. ``None`` allows any field
            that is not in ``denied_fields``.
        sortable_fields: Fields clients may sort on. ``None`` allows any field
            that is not in ``denied_fields``.
        searchable_fields: Fields clients may list in ``search_fields``. ``None``
            allows any field that is not in ``denied_fields``.
        denied_fields: Fields that are rejected for an operation that has no
            allowlist (default: ``password``, ``password_hash``, ``secret``)
        use_window_function: Force the PostgreSQL window-function count on or off.
            ``None`` auto-detects (default: None)

    Example:
        config = FSPConfig(
            max_per_page=500,
            default_per_page=25,
            filterable_fields={"name", "age"},
            sortable_fields={"name", "age", "created_at"},
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

    # Field access settings
    filterable_fields: Optional[Collection[str]] = None
    sortable_fields: Optional[Collection[str]] = None
    searchable_fields: Optional[Collection[str]] = None
    denied_fields: Collection[str] = DEFAULT_DENIED_FIELDS

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
        for name in ("filterable_fields", "sortable_fields", "searchable_fields"):
            value = getattr(self, name)
            if value is not None:
                setattr(self, name, _to_field_set(name, value))
        self.denied_fields = _to_field_set("denied_fields", self.denied_fields)

    def allows_filter(self, field_name: str) -> bool:
        """Return True if clients may filter on ``field_name``."""
        return self._allows(field_name, self.filterable_fields)

    def allows_sort(self, field_name: str) -> bool:
        """Return True if clients may sort on ``field_name``."""
        return self._allows(field_name, self.sortable_fields)

    def allows_search(self, field_name: str) -> bool:
        """Return True if clients may search on ``field_name``."""
        return self._allows(field_name, self.searchable_fields)

    def _allows(self, field_name: str, allowlist: Optional[Collection[str]]) -> bool:
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


def _to_field_set(name: str, value: Collection[str]) -> FrozenSet[str]:
    """Normalize a collection of field names, rejecting a bare string."""
    if isinstance(value, str):
        raise ValueError(f"{name} must be a collection of field names, not a string")
    return frozenset(value)


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
