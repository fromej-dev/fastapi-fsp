"""Tests for filtering on computed fields (hybrid_property, etc.)."""

from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.main import Hero


class TestComputedFieldFiltering:
    """Test suite for filtering on computed fields like hybrid_property."""

    def test_filter_hybrid_property_eq(self, session: Session, client: TestClient):
        """Test filtering hybrid_property with equality operator."""
        hero_1 = Hero(name="Spider", secret_name="Man")
        hero_2 = Hero(name="Bat", secret_name="Man")
        session.add(hero_1)
        session.add(hero_2)
        session.commit()

        # Filter by full_name (hybrid_property) with exact match
        response = client.get("/heroes/?field=full_name&operator=eq&value=Spider-Man")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["full_name"] == "Spider-Man"
        assert data[0]["name"] == "Spider"

    def test_filter_hybrid_property_ilike(self, session: Session, client: TestClient):
        """Test filtering hybrid_property with ILIKE operator."""
        hero_1 = Hero(name="Spider", secret_name="Man")
        hero_2 = Hero(name="Bat", secret_name="Girl")
        hero_3 = Hero(name="Iron", secret_name="Man")
        session.add_all([hero_1, hero_2, hero_3])
        session.commit()

        # Filter by full_name with ILIKE pattern (case-insensitive)
        response = client.get("/heroes/?field=full_name&operator=ilike&value=%man")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 2
        full_names = {d["full_name"] for d in data}
        assert full_names == {"Spider-Man", "Iron-Man"}

    def test_filter_hybrid_property_contains(self, session: Session, client: TestClient):
        """Test filtering hybrid_property with contains operator."""
        hero_1 = Hero(name="Spider", secret_name="Man")
        hero_2 = Hero(name="Bat", secret_name="Woman")
        session.add_all([hero_1, hero_2])
        session.commit()

        # Filter by full_name containing "ider"
        response = client.get("/heroes/?field=full_name&operator=contains&value=ider")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["full_name"] == "Spider-Man"

    def test_filter_hybrid_property_starts_with(self, session: Session, client: TestClient):
        """Test filtering hybrid_property with starts_with operator."""
        hero_1 = Hero(name="Spider", secret_name="Man")
        hero_2 = Hero(name="Bat", secret_name="Man")
        session.add_all([hero_1, hero_2])
        session.commit()

        # Filter by full_name starting with "Bat"
        response = client.get("/heroes/?field=full_name&operator=starts_with&value=Bat")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["full_name"] == "Bat-Man"

    def test_filter_hybrid_property_ends_with(self, session: Session, client: TestClient):
        """Test filtering hybrid_property with ends_with operator."""
        hero_1 = Hero(name="Spider", secret_name="Man")
        hero_2 = Hero(name="Bat", secret_name="Woman")
        session.add_all([hero_1, hero_2])
        session.commit()

        # Filter by full_name ending with "Woman"
        response = client.get("/heroes/?field=full_name&operator=ends_with&value=Woman")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["full_name"] == "Bat-Woman"

    def test_filter_hybrid_property_ne(self, session: Session, client: TestClient):
        """Test filtering hybrid_property with not-equals operator."""
        hero_1 = Hero(name="Spider", secret_name="Man")
        hero_2 = Hero(name="Bat", secret_name="Man")
        session.add_all([hero_1, hero_2])
        session.commit()

        # Filter by full_name not equal to "Spider-Man"
        response = client.get("/heroes/?field=full_name&operator=ne&value=Spider-Man")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["full_name"] == "Bat-Man"

    def test_filter_hybrid_property_in(self, session: Session, client: TestClient):
        """Test filtering hybrid_property with IN operator."""
        hero_1 = Hero(name="Spider", secret_name="Man")
        hero_2 = Hero(name="Bat", secret_name="Man")
        hero_3 = Hero(name="Iron", secret_name="Man")
        session.add_all([hero_1, hero_2, hero_3])
        session.commit()

        # Filter by full_name in a list
        response = client.get("/heroes/?field=full_name&operator=in&value=Spider-Man,Iron-Man")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 2
        full_names = {d["full_name"] for d in data}
        assert full_names == {"Spider-Man", "Iron-Man"}

    def test_filter_hybrid_property_not_in(self, session: Session, client: TestClient):
        """Test filtering hybrid_property with NOT IN operator."""
        hero_1 = Hero(name="Spider", secret_name="Man")
        hero_2 = Hero(name="Bat", secret_name="Man")
        hero_3 = Hero(name="Iron", secret_name="Man")
        session.add_all([hero_1, hero_2, hero_3])
        session.commit()

        # Filter by full_name not in a list
        response = client.get("/heroes/?field=full_name&operator=not_in&value=Spider-Man,Iron-Man")
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["full_name"] == "Bat-Man"

    def test_filter_hybrid_property_combined_with_regular_field(
        self, session: Session, client: TestClient
    ):
        """Test filtering with both hybrid_property and regular fields."""
        hero_1 = Hero(name="Spider", secret_name="Man", age=25)
        hero_2 = Hero(name="Bat", secret_name="Man", age=35)
        hero_3 = Hero(name="Spider", secret_name="Woman", age=28)
        session.add_all([hero_1, hero_2, hero_3])
        session.commit()

        # Filter by hybrid_property AND regular field
        response = client.get(
            "/heroes/?field=full_name&operator=starts_with&value=Spider"
            "&field=age&operator=lt&value=30"
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 2
        full_names = {d["full_name"] for d in data}
        assert full_names == {"Spider-Man", "Spider-Woman"}

    def test_filter_hybrid_property_with_sort_and_pagination(
        self, session: Session, client: TestClient
    ):
        """Test filtering hybrid_property combined with sorting and pagination."""
        heroes = [
            Hero(name="A", secret_name="Hero"),
            Hero(name="B", secret_name="Hero"),
            Hero(name="C", secret_name="Hero"),
            Hero(name="D", secret_name="Villain"),
        ]
        session.add_all(heroes)
        session.commit()

        # Filter + sort + paginate
        response = client.get(
            "/heroes/?field=full_name&operator=ends_with&value=Hero"
            "&sort_by=full_name&order=desc"
            "&page=1&per_page=2"
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 2
        assert data["data"][0]["full_name"] == "C-Hero"
        assert data["data"][1]["full_name"] == "B-Hero"
        assert data["meta"]["pagination"]["total_items"] == 3

    def test_filter_hybrid_property_indexed_format(self, session: Session, client: TestClient):
        """Test filtering hybrid_property with indexed filter format."""
        hero_1 = Hero(name="Spider", secret_name="Man", age=25)
        hero_2 = Hero(name="Bat", secret_name="Man", age=35)
        session.add_all([hero_1, hero_2])
        session.commit()

        # Use indexed filter format
        response = client.get(
            "/heroes/?"
            "filters[0][field]=full_name&filters[0][operator]=eq&filters[0][value]=Spider-Man"
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["full_name"] == "Spider-Man"

    def test_filter_unknown_field_non_strict_mode(self, session: Session, client: TestClient):
        """Test that unknown fields are silently skipped in non-strict mode."""
        hero_1 = Hero(name="Spider", secret_name="Man")
        session.add(hero_1)
        session.commit()

        # Filter by non-existent field - should be silently skipped
        response = client.get("/heroes/?field=nonexistent_field&operator=eq&value=test")
        assert response.status_code == 200
        data = response.json()["data"]
        # All heroes should be returned since filter is skipped
        assert len(data) == 1

    def test_meta_includes_computed_field_filters(self, session: Session, client: TestClient):
        """Test that response meta includes the computed field filter info."""
        hero_1 = Hero(name="Spider", secret_name="Man")
        session.add(hero_1)
        session.commit()

        response = client.get("/heroes/?field=full_name&operator=eq&value=Spider-Man")
        assert response.status_code == 200
        meta = response.json()["meta"]
        assert meta["filters"] is not None
        assert len(meta["filters"]) == 1
        assert meta["filters"][0]["field"] == "full_name"
        assert meta["filters"][0]["operator"] == "eq"
        assert meta["filters"][0]["value"] == "Spider-Man"
