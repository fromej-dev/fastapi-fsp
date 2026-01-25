"""Configuration classes for fastapi-fsp."""

from dataclasses import dataclass, field
from typing import Optional


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

    Example:
        # Create a strict configuration
        config = FSPConfig(
            strict_mode=True,
            max_per_page=50,
            default_per_page=20
        )

        # Use with FSPManager
        def get_fsp_config():
            return FSPConfig(strict_mode=True)

        @app.get("/items/")
        def read_items(
            fsp: FSPManager = Depends(FSPManager),
            config: FSPConfig = Depends(get_fsp_config)
        ):
            fsp.apply_config(config)
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
