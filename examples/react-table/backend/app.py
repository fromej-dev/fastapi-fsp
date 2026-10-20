"""Backend for the React + TanStack Table example.

One endpoint, GET /api/employees, handles the table's search box, column filters,
sortable headers and pager through fastapi-fsp query parameters.

Run with: uv run --with uvicorn uvicorn app:app --reload
"""

import random
from datetime import date, timedelta
from typing import Optional

from fastapi import Depends, FastAPI
from fastapi_fsp import FSPConfig, FSPManager, PaginatedResponse
from sqlalchemy.pool import StaticPool
from sqlmodel import Field, Session, SQLModel, create_engine, select


class EmployeeBase(SQLModel):
    first_name: str = Field(index=True)
    last_name: str = Field(index=True)
    email: str
    department: str = Field(index=True)
    title: str
    city: str
    salary: int
    hired_on: date


class Employee(EmployeeBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)


class EmployeePublic(EmployeeBase):
    id: int


# In-memory SQLite, shared across threads, reseeded on every start.
engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

FIRST_NAMES = [
    "Ada", "Alan", "Grace", "Linus", "Margaret", "Dennis", "Barbara", "Ken", "Radia", "Guido",
    "Frances", "Donald", "Hedy", "Tim", "Katherine", "Edsger", "Sophie", "John", "Anita", "Bjarne",
]  # fmt: skip
LAST_NAMES = [
    "Lovelace", "Turing", "Hopper", "Torvalds", "Hamilton", "Ritchie", "Liskov", "Thompson",
    "Perlman", "van Rossum", "Allen", "Knuth", "Lamarr", "Berners-Lee", "Johnson", "Dijkstra",
    "Wilson", "McCarthy", "Borg", "Stroustrup",
]  # fmt: skip
ROLES = {
    "Engineering": ["Software Engineer", "Staff Engineer", "Engineering Manager", "SRE"],
    "Design": ["Product Designer", "UX Researcher", "Design Lead"],
    "Sales": ["Account Executive", "Sales Engineer", "Sales Manager"],
    "Support": ["Support Specialist", "Support Lead"],
    "Finance": ["Financial Analyst", "Controller"],
}
CITIES = ["Amsterdam", "Berlin", "Lisbon", "London", "New York", "Toronto", "Utrecht", "Tokyo"]


def seed(session: Session, count: int = 500) -> None:
    rng = random.Random(42)
    for _ in range(count):
        first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
        department = rng.choice(list(ROLES))
        session.add(
            Employee(
                first_name=first,
                last_name=last,
                email=f"{first}.{last}".lower().replace(" ", "") + "@example.com",
                department=department,
                title=rng.choice(ROLES[department]),
                city=rng.choice(CITIES),
                salary=rng.randrange(40_000, 160_000, 1_000),
                hired_on=date(2015, 1, 1) + timedelta(days=rng.randrange(0, 3900)),
            )
        )
    session.commit()


SQLModel.metadata.create_all(engine)
with Session(engine) as _session:
    seed(_session)

app = FastAPI(title="fastapi-fsp React table example")

# Reject unknown filter or sort fields with a 400 instead of ignoring them.
config = FSPConfig(strict_mode=True, max_per_page=100)


def get_session():
    with Session(engine) as session:
        yield session


@app.get("/api/employees", response_model=PaginatedResponse[EmployeePublic])
def list_employees(
    session: Session = Depends(get_session),
    fsp: FSPManager = Depends(FSPManager),
):
    return fsp.apply_config(config).generate_response(select(Employee), session)


@app.get("/api/departments", response_model=list[str])
def list_departments(session: Session = Depends(get_session)):
    """Options for the department filter dropdown."""
    return session.exec(select(Employee.department).distinct().order_by(Employee.department)).all()
