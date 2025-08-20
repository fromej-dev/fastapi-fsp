from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import Depends, FastAPI
from fastapi_fsp.fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from tests.main import Hero, HeroPublic

sqlite_file_name = "database.db"
sqlite_url = f"sqlite+aiosqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread": False}
engine = create_async_engine(sqlite_url, echo=True, connect_args=connect_args)


async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async_session = AsyncSession(engine, expire_on_commit=False)
    try:
        yield async_session
    finally:
        await async_session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code to run on startup
    print("Creating database and tables...")
    await create_db_and_tables()
    yield
    # Code to run on shutdown (if any)
    print("Application shutdown.")


app = FastAPI(lifespan=lifespan)


@app.get("/heroes_async/", response_model=PaginatedResponse[HeroPublic])
async def read_heroes_async(
    *, session: AsyncSession = Depends(get_session), fsp: FSPManager = Depends(FSPManager)
):
    heroes = select(Hero)
    return await fsp.generate_response_async(heroes, session)
