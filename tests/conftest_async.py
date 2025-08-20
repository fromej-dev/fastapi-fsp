import asyncio
from typing import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.testclient import TestClient

from tests.main_async import app, get_session


@pytest.fixture(name="async_engine")
def async_engine_fixture(tmp_path) -> AsyncGenerator[AsyncEngine, None]:
    db_path = tmp_path / "test_async.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)

    async def _setup():
        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    asyncio.run(_setup())
    try:
        yield engine
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture(name="client_async")
def client_async_fixture(async_engine: AsyncEngine):
    async def _get_session() -> AsyncGenerator[AsyncSession, None]:
        async with AsyncSession(async_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = _get_session
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()
