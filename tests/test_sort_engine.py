"""Tests for SortEngine."""

from typing import Optional

import pytest
from fastapi import HTTPException
from fastapi_fsp.models import SortingOrder, SortingQuery
from fastapi_fsp.sorting import SortEngine
from sqlmodel import Field, SQLModel, create_engine, select


class SortTestModel(SQLModel, table=True):
    """Test model for sort engine tests."""

    __tablename__ = "sort_test_model"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(default="")
    age: Optional[int] = Field(default=None)


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def columns(engine):
    return select(SortTestModel).selected_columns


class TestSortEngine:
    """Tests for SortEngine.apply_sort()."""

    def test_no_sorting(self, columns):
        se = SortEngine()
        query = select(SortTestModel)
        result = se.apply_sort(query, columns, None)
        assert "ORDER BY" not in str(result)

    def test_sort_asc(self, columns):
        se = SortEngine()
        query = select(SortTestModel)
        sorting = SortingQuery(sort_by="age", order=SortingOrder.ASC)
        result = se.apply_sort(query, columns, sorting)
        compiled = str(result)
        assert "ORDER BY" in compiled
        assert "ASC" in compiled

    def test_sort_desc(self, columns):
        se = SortEngine()
        query = select(SortTestModel)
        sorting = SortingQuery(sort_by="age", order=SortingOrder.DESC)
        result = se.apply_sort(query, columns, sorting)
        compiled = str(result)
        assert "ORDER BY" in compiled
        assert "DESC" in compiled

    def test_unknown_field_non_strict(self, columns):
        se = SortEngine(strict_mode=False)
        query = select(SortTestModel)
        sorting = SortingQuery(sort_by="nonexistent", order=SortingOrder.ASC)
        result = se.apply_sort(query, columns, sorting)
        assert "ORDER BY" not in str(result)

    def test_unknown_field_strict(self, columns):
        se = SortEngine(strict_mode=True)
        query = select(SortTestModel)
        sorting = SortingQuery(sort_by="nonexistent", order=SortingOrder.ASC)

        with pytest.raises(HTTPException) as exc_info:
            se.apply_sort(query, columns, sorting)
        assert exc_info.value.status_code == 400
        assert "nonexistent" in str(exc_info.value.detail).lower()

    def test_empty_sort_by(self, columns):
        se = SortEngine()
        query = select(SortTestModel)
        sorting = SortingQuery(sort_by="", order=SortingOrder.ASC)
        result = se.apply_sort(query, columns, sorting)
        assert "ORDER BY" not in str(result)
