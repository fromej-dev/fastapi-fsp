"""Tests for PaginationEngine with window function optimization."""

from typing import Optional
from unittest.mock import Mock

import pytest
from fastapi_fsp.models import PaginationQuery
from fastapi_fsp.pagination import PaginationEngine, _detect_postgresql
from sqlmodel import Field, Session, SQLModel, create_engine, select


class PaginationTestModel(SQLModel, table=True):
    """Test model for pagination engine tests."""

    __tablename__ = "pagination_test_model"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(default="")
    age: Optional[int] = Field(default=None)


@pytest.fixture(scope="module")
def engine():
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def seeded_session(engine):
    """Session with test data."""
    with Session(engine) as session:
        # Clean existing data
        existing = session.exec(select(PaginationTestModel)).all()
        for item in existing:
            session.delete(item)
        session.commit()

        items = [PaginationTestModel(name=f"Item{i}", age=20 + i) for i in range(15)]
        session.add_all(items)
        session.commit()
        yield session


@pytest.fixture
def mock_request():
    request = Mock()
    request.url = Mock()
    request.url.include_query_params = Mock(return_value="http://example.com?page=1&per_page=10")
    return request


class TestDetectPostgresql:
    """Tests for PostgreSQL dialect detection."""

    def test_sqlite_not_postgresql(self, session):
        assert _detect_postgresql(session) is False

    def test_mock_postgresql(self):
        mock_session = Mock()
        mock_session.bind = Mock()
        mock_session.bind.dialect = Mock()
        mock_session.bind.dialect.name = "postgresql"
        assert _detect_postgresql(mock_session) is True

    def test_mock_mysql(self):
        mock_session = Mock()
        mock_session.bind = Mock()
        mock_session.bind.dialect = Mock()
        mock_session.bind.dialect.name = "mysql"
        assert _detect_postgresql(mock_session) is False

    def test_no_bind_returns_false(self):
        mock_session = Mock(spec=[])
        assert _detect_postgresql(mock_session) is False

    def test_async_session_postgresql(self):
        mock_session = Mock(spec=[])
        mock_session.sync_session = Mock()
        mock_session.sync_session.bind = Mock()
        mock_session.sync_session.bind.dialect = Mock()
        mock_session.sync_session.bind.dialect.name = "postgresql"
        assert _detect_postgresql(mock_session) is True


class TestPaginationEngineBasic:
    """Tests for basic pagination operations."""

    def test_paginate_first_page(self, seeded_session, mock_request):
        pagination = PaginationQuery(page=1, per_page=5)
        pe = PaginationEngine(pagination=pagination, request=mock_request)

        query = select(PaginationTestModel)
        results = pe.paginate(query, seeded_session)
        assert len(results) == 5

    def test_paginate_second_page(self, seeded_session, mock_request):
        pagination = PaginationQuery(page=2, per_page=5)
        pe = PaginationEngine(pagination=pagination, request=mock_request)

        query = select(PaginationTestModel)
        results = pe.paginate(query, seeded_session)
        assert len(results) == 5

    def test_paginate_last_page_partial(self, seeded_session, mock_request):
        pagination = PaginationQuery(page=3, per_page=5)
        pe = PaginationEngine(pagination=pagination, request=mock_request)

        query = select(PaginationTestModel)
        results = pe.paginate(query, seeded_session)
        assert len(results) == 5  # 15 items, page 3 of 5 = 5 items

    def test_count_total(self, seeded_session, mock_request):
        pagination = PaginationQuery(page=1, per_page=5)
        pe = PaginationEngine(pagination=pagination, request=mock_request)

        query = select(PaginationTestModel)
        total = pe.count_total(query, seeded_session)
        assert total == 15


class TestPaginateWithCount:
    """Tests for combined paginate + count."""

    def test_paginate_with_count_sqlite(self, seeded_session, mock_request):
        """SQLite should use separate queries (no window function)."""
        pagination = PaginationQuery(page=1, per_page=5)
        pe = PaginationEngine(pagination=pagination, request=mock_request)

        query = select(PaginationTestModel)
        data, total = pe.paginate_with_count(query, seeded_session)
        assert len(data) == 5
        assert total == 15

    def test_explicit_disable_window_function(self, seeded_session, mock_request):
        """Explicitly disabling window function should use separate queries."""
        pagination = PaginationQuery(page=1, per_page=5)
        pe = PaginationEngine(
            pagination=pagination,
            request=mock_request,
            use_window_function=False,
        )

        query = select(PaginationTestModel)
        data, total = pe.paginate_with_count(query, seeded_session)
        assert len(data) == 5
        assert total == 15

    def test_auto_detect_sqlite(self, seeded_session, mock_request):
        """Auto-detect should disable window function for SQLite."""
        pagination = PaginationQuery(page=1, per_page=5)
        pe = PaginationEngine(pagination=pagination, request=mock_request)

        assert pe._should_use_window_function(seeded_session) is False

    def test_explicit_override(self, mock_request):
        """Explicit True overrides auto-detect."""
        pagination = PaginationQuery(page=1, per_page=5)
        pe = PaginationEngine(
            pagination=pagination,
            request=mock_request,
            use_window_function=True,
        )

        mock_session = Mock()
        assert pe._should_use_window_function(mock_session) is True


class TestBuildResponse:
    """Tests for response building."""

    def test_build_response_basic(self, mock_request):
        pagination = PaginationQuery(page=1, per_page=10)
        pe = PaginationEngine(pagination=pagination, request=mock_request)

        response = pe.build_response(total_items=25, data_page=["a", "b", "c"])
        assert response.data == ["a", "b", "c"]
        assert response.meta.pagination.total_items == 25
        assert response.meta.pagination.per_page == 10
        assert response.meta.pagination.current_page == 1
        assert response.meta.pagination.total_pages == 3

    def test_build_response_with_filters_and_sorting(self, mock_request):
        from fastapi_fsp.models import Filter, FilterOperator, SortingOrder, SortingQuery

        pagination = PaginationQuery(page=1, per_page=10)
        pe = PaginationEngine(pagination=pagination, request=mock_request)

        filters = [Filter(field="age", operator=FilterOperator.GTE, value="18")]
        sorting = SortingQuery(sort_by="name", order=SortingOrder.ASC)

        response = pe.build_response(
            total_items=5,
            data_page=[],
            filters=filters,
            sorting=sorting,
        )
        assert response.meta.filters == filters
        assert response.meta.sort == sorting

    def test_build_response_empty(self, mock_request):
        pagination = PaginationQuery(page=1, per_page=10)
        pe = PaginationEngine(pagination=pagination, request=mock_request)

        response = pe.build_response(total_items=0, data_page=[])
        assert response.data == []
        assert response.meta.pagination.total_items == 0
        assert response.meta.pagination.total_pages == 1

    def test_build_response_links(self, mock_request):
        pagination = PaginationQuery(page=2, per_page=10)
        pe = PaginationEngine(pagination=pagination, request=mock_request)

        response = pe.build_response(total_items=30, data_page=[])
        assert response.links.self is not None
        assert response.links.first is not None
        assert response.links.last is not None
        assert response.links.next is not None
        assert response.links.prev is not None


class TestStaticCountMethods:
    """Tests for static count methods (backward compatibility)."""

    def test_count_total_static(self, seeded_session):
        query = select(PaginationTestModel)
        total = PaginationEngine._count_total_static(query, seeded_session)
        assert total == 15
