"""Tests for FSPConfig configuration class."""

import pytest
from fastapi_fsp.config import FSPConfig, FSPPresets


class TestFSPConfig:
    """Tests for FSPConfig class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = FSPConfig()

        assert config.max_per_page == 100
        assert config.default_per_page == 10
        assert config.default_page == 1
        assert config.min_per_page == 1
        assert config.strict_mode is False
        assert config.allow_deep_pagination is True
        assert config.max_page is None

    def test_custom_config(self):
        """Test custom configuration values."""
        config = FSPConfig(
            max_per_page=50,
            default_per_page=20,
            strict_mode=True,
            max_page=100,
        )

        assert config.max_per_page == 50
        assert config.default_per_page == 20
        assert config.strict_mode is True
        assert config.max_page == 100

    def test_invalid_max_per_page(self):
        """Test that max_per_page must be >= 1."""
        with pytest.raises(ValueError, match="max_per_page must be >= 1"):
            FSPConfig(max_per_page=0)

    def test_invalid_default_per_page(self):
        """Test that default_per_page must be >= 1."""
        with pytest.raises(ValueError, match="default_per_page must be >= 1"):
            FSPConfig(default_per_page=0)

    def test_default_exceeds_max(self):
        """Test that default_per_page cannot exceed max_per_page."""
        with pytest.raises(ValueError, match="default_per_page cannot exceed max_per_page"):
            FSPConfig(max_per_page=10, default_per_page=20)

    def test_invalid_min_per_page(self):
        """Test that min_per_page must be >= 1."""
        with pytest.raises(ValueError, match="min_per_page must be >= 1"):
            FSPConfig(min_per_page=0)

    def test_min_exceeds_max(self):
        """Test that min_per_page cannot exceed max_per_page."""
        with pytest.raises(ValueError, match="min_per_page cannot exceed max_per_page"):
            FSPConfig(max_per_page=10, min_per_page=20)

    def test_invalid_default_page(self):
        """Test that default_page must be >= 1."""
        with pytest.raises(ValueError, match="default_page must be >= 1"):
            FSPConfig(default_page=0)

    def test_invalid_max_page(self):
        """Test that max_page must be >= 1 or None."""
        with pytest.raises(ValueError, match="max_page must be >= 1 or None"):
            FSPConfig(max_page=0)

    def test_validate_page_normal(self):
        """Test page validation with normal value."""
        config = FSPConfig()
        assert config.validate_page(5) == 5

    def test_validate_page_less_than_one(self):
        """Test page validation returns default for values < 1."""
        config = FSPConfig(default_page=1)
        assert config.validate_page(0) == 1
        assert config.validate_page(-5) == 1

    def test_validate_page_with_max_page_deep_pagination_allowed(self):
        """Test page validation with max_page when deep pagination is allowed."""
        config = FSPConfig(max_page=50, allow_deep_pagination=True)
        # Should allow any page when deep pagination is allowed
        assert config.validate_page(100) == 100

    def test_validate_page_with_max_page_deep_pagination_not_allowed(self):
        """Test page validation with max_page when deep pagination is not allowed."""
        config = FSPConfig(max_page=50, allow_deep_pagination=False)
        with pytest.raises(ValueError, match="Page 100 exceeds maximum allowed page 50"):
            config.validate_page(100)

    def test_validate_per_page_normal(self):
        """Test per_page validation with normal value."""
        config = FSPConfig(min_per_page=5, max_per_page=100)
        assert config.validate_per_page(20) == 20

    def test_validate_per_page_below_min(self):
        """Test per_page validation returns min for values below minimum."""
        config = FSPConfig(min_per_page=5, max_per_page=100)
        assert config.validate_per_page(2) == 5

    def test_validate_per_page_above_max(self):
        """Test per_page validation returns max for values above maximum."""
        config = FSPConfig(min_per_page=5, max_per_page=100)
        assert config.validate_per_page(200) == 100


class TestFSPPresets:
    """Tests for FSPPresets class."""

    def test_default_preset(self):
        """Test default preset."""
        config = FSPPresets.default()
        assert config.max_per_page == 100
        assert config.default_per_page == 10
        assert config.strict_mode is False

    def test_strict_preset(self):
        """Test strict preset."""
        config = FSPPresets.strict()
        assert config.strict_mode is True

    def test_limited_pagination_preset(self):
        """Test limited pagination preset."""
        config = FSPPresets.limited_pagination(max_page=50, max_per_page=25)
        assert config.max_page == 50
        assert config.max_per_page == 25
        assert config.allow_deep_pagination is False

    def test_limited_pagination_preset_defaults(self):
        """Test limited pagination preset with default values."""
        config = FSPPresets.limited_pagination()
        assert config.max_page == 100
        assert config.max_per_page == 50

    def test_high_volume_preset(self):
        """Test high volume preset."""
        config = FSPPresets.high_volume(max_per_page=1000, default_per_page=200)
        assert config.max_per_page == 1000
        assert config.default_per_page == 200

    def test_high_volume_preset_defaults(self):
        """Test high volume preset with default values."""
        config = FSPPresets.high_volume()
        assert config.max_per_page == 500
        assert config.default_per_page == 100
