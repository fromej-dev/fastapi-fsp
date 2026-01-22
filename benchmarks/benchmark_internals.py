"""Benchmark internal operations of fastapi-fsp to identify bottlenecks."""

import time
from datetime import datetime, timedelta
from typing import Optional
from unittest.mock import Mock

from fastapi_fsp.fsp import FSPManager
from fastapi_fsp.models import Filter, FilterOperator, PaginationQuery, SortingQuery
from sqlmodel import Field, Session, SQLModel, create_engine, select


class Hero(SQLModel, table=True):
    """Hero model for benchmarking."""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    secret_name: str
    age: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    deleted: bool = Field(default=False)
    email: str = Field(default="", index=True)
    city: str = Field(default="")


def time_function(func, iterations: int = 1000):
    """Time a function execution."""
    # Warmup
    for _ in range(10):
        func()

    # Benchmark
    timings = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        timings.append(end - start)

    timings.sort()
    avg = sum(timings) / len(timings)
    p50 = timings[int(len(timings) * 0.5)]
    p95 = timings[int(len(timings) * 0.95)]
    return {"avg": avg * 1000, "p50": p50 * 1000, "p95": p95 * 1000}


def setup_database(num_records: int = 1000):
    """Set up in-memory database with test data."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    cities = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"]
    base_time = datetime.now()

    with Session(engine) as session:
        heroes = []
        for i in range(num_records):
            hero = Hero(
                name=f"Hero_{i}",
                secret_name=f"Secret_{i}",
                age=20 + (i % 60),
                created_at=base_time - timedelta(days=i % 365),
                deleted=i % 10 == 0,
                email=f"hero_{i}@example.com",
                city=cities[i % len(cities)],
            )
            heroes.append(hero)
        session.add_all(heroes)
        session.commit()

    return engine


def benchmark_coerce_value():
    """Benchmark _coerce_value method."""
    print("\n=== Benchmark: _coerce_value ===")

    engine = setup_database(10)
    with Session(engine):
        query = select(Hero)
        columns = query.selected_columns

        # Get sample columns
        age_col = columns["age"]
        name_col = columns["name"]
        deleted_col = columns["deleted"]
        created_at_col = columns["created_at"]

        # Test different type coercions
        tests = {
            "Integer coercion": lambda: FSPManager._coerce_value(age_col, "42"),
            "Boolean coercion (true)": lambda: FSPManager._coerce_value(
                deleted_col, "true"
            ),
            "Boolean coercion (false)": lambda: FSPManager._coerce_value(
                deleted_col, "false"
            ),
            "Datetime coercion": lambda: FSPManager._coerce_value(
                created_at_col, "2024-01-01"
            ),
            "String passthrough": lambda: FSPManager._coerce_value(name_col, "Hero_1"),
        }

        for name, func in tests.items():
            result = time_function(func, iterations=10000)
            print(
                f"  {name:30s} - Avg: {result['avg']:6.3f}ms, "
                f"P50: {result['p50']:6.3f}ms, P95: {result['p95']:6.3f}ms"
            )


def benchmark_split_values():
    """Benchmark _split_values method."""
    print("\n=== Benchmark: _split_values ===")

    tests = {
        "Split 3 values": lambda: FSPManager._split_values("val1,val2,val3"),
        "Split 10 values": lambda: FSPManager._split_values(
            ",".join([f"val{i}" for i in range(10)])
        ),
        "Split with spaces": lambda: FSPManager._split_values("val1, val2, val3"),
    }

    for name, func in tests.items():
        result = time_function(func, iterations=10000)
        print(
            f"  {name:30s} - Avg: {result['avg']:6.3f}ms, "
            f"P50: {result['p50']:6.3f}ms, P95: {result['p95']:6.3f}ms"
        )


def benchmark_apply_filter():
    """Benchmark _build_filter_condition method."""
    print("\n=== Benchmark: _build_filter_condition ===")

    engine = setup_database(100)
    with Session(engine):
        base_query = select(Hero)
        columns = base_query.selected_columns
        age_col = columns["age"]
        name_col = columns["name"]

        tests = {
            "EQ filter": lambda: FSPManager._build_filter_condition(
                age_col, Filter(field="age", operator=FilterOperator.EQ, value="30")
            ),
            "GT filter": lambda: FSPManager._build_filter_condition(
                age_col, Filter(field="age", operator=FilterOperator.GT, value="30")
            ),
            "ILIKE filter": lambda: FSPManager._build_filter_condition(
                name_col,
                Filter(field="name", operator=FilterOperator.ILIKE, value="%Hero%"),
            ),
            "IN filter (3 values)": lambda: FSPManager._build_filter_condition(
                age_col,
                Filter(field="age", operator=FilterOperator.IN, value="25,30,35"),
            ),
            "BETWEEN filter": lambda: FSPManager._build_filter_condition(
                age_col,
                Filter(field="age", operator=FilterOperator.BETWEEN, value="25,45"),
            ),
        }

        for name, func in tests.items():
            result = time_function(func, iterations=1000)
            print(
                f"  {name:30s} - Avg: {result['avg']:6.3f}ms, "
                f"P50: {result['p50']:6.3f}ms, P95: {result['p95']:6.3f}ms"
            )


def benchmark_apply_filters():
    """Benchmark _apply_filters method with multiple filters."""
    print("\n=== Benchmark: _apply_filters ===")

    engine = setup_database(100)
    with Session(engine):
        base_query = select(Hero)
        columns = base_query.selected_columns

        # Create mock request for FSPManager
        request = Mock()
        request.url = Mock()
        request.url.include_query_params = Mock(return_value="http://example.com")
        pagination = PaginationQuery(page=1, per_page=20)

        filters_1 = [Filter(field="age", operator=FilterOperator.GTE, value="30")]
        filters_3 = [
            Filter(field="age", operator=FilterOperator.GTE, value="30"),
            Filter(field="deleted", operator=FilterOperator.EQ, value="false"),
            Filter(field="city", operator=FilterOperator.EQ, value="Chicago"),
        ]
        filters_5 = filters_3 + [
            Filter(field="name", operator=FilterOperator.ILIKE, value="%Hero%"),
            Filter(field="age", operator=FilterOperator.LTE, value="60"),
        ]

        # Create FSPManager instances
        fsp_1 = FSPManager(request=request, filters=filters_1, sorting=None, pagination=pagination)
        fsp_3 = FSPManager(request=request, filters=filters_3, sorting=None, pagination=pagination)
        fsp_5 = FSPManager(request=request, filters=filters_5, sorting=None, pagination=pagination)
        fsp_none = FSPManager(request=request, filters=None, sorting=None, pagination=pagination)

        tests = {
            "1 filter": lambda: fsp_1._apply_filters(base_query, columns, filters_1),
            "3 filters": lambda: fsp_3._apply_filters(base_query, columns, filters_3),
            "5 filters": lambda: fsp_5._apply_filters(base_query, columns, filters_5),
            "No filters": lambda: fsp_none._apply_filters(base_query, columns, None),
        }

        for name, func in tests.items():
            result = time_function(func, iterations=1000)
            print(
                f"  {name:30s} - Avg: {result['avg']:6.3f}ms, "
                f"P50: {result['p50']:6.3f}ms, P95: {result['p95']:6.3f}ms"
            )


def benchmark_apply_sort():
    """Benchmark _apply_sort method."""
    print("\n=== Benchmark: _apply_sort ===")

    engine = setup_database(100)
    with Session(engine):
        base_query = select(Hero)
        columns = base_query.selected_columns

        # Create mock request for FSPManager
        request = Mock()
        request.url = Mock()
        request.url.include_query_params = Mock(return_value="http://example.com")
        pagination = PaginationQuery(page=1, per_page=20)

        from fastapi_fsp.models import SortingOrder

        sort_age_asc = SortingQuery(sort_by="age", order=SortingOrder.ASC)
        sort_name_desc = SortingQuery(sort_by="name", order=SortingOrder.DESC)

        # Create FSPManager instances
        fsp_asc = FSPManager(
            request=request, filters=None, sorting=sort_age_asc, pagination=pagination
        )
        fsp_desc = FSPManager(
            request=request, filters=None, sorting=sort_name_desc, pagination=pagination
        )
        fsp_none = FSPManager(request=request, filters=None, sorting=None, pagination=pagination)

        tests = {
            "Sort by age ASC": lambda: fsp_asc._apply_sort(base_query, columns, sort_age_asc),
            "Sort by name DESC": lambda: fsp_desc._apply_sort(
                base_query, columns, sort_name_desc
            ),
            "No sorting": lambda: fsp_none._apply_sort(base_query, columns, None),
        }

        for name, func in tests.items():
            result = time_function(func, iterations=1000)
            print(
                f"  {name:30s} - Avg: {result['avg']:6.3f}ms, "
                f"P50: {result['p50']:6.3f}ms, P95: {result['p95']:6.3f}ms"
            )


def benchmark_count_total():
    """Benchmark _count_total method."""
    print("\n=== Benchmark: _count_total ===")

    for num_records in [100, 1000, 10000]:
        print(f"\n  Dataset: {num_records} records")
        engine = setup_database(num_records)

        with Session(engine) as session:
            base_query = select(Hero)

            # Count with no filters
            def count_all():
                return FSPManager._count_total(base_query, session)

            # Count with filter
            filtered_query = base_query.where(Hero.age >= 30)

            def count_filtered():
                return FSPManager._count_total(filtered_query, session)

            tests = {
                "Count all records": count_all,
                "Count filtered records": count_filtered,
            }

            for name, func in tests.items():
                result = time_function(func, iterations=100)
                print(
                    f"    {name:30s} - Avg: {result['avg']:6.3f}ms, "
                    f"P50: {result['p50']:6.3f}ms, P95: {result['p95']:6.3f}ms"
                )


def benchmark_pagination():
    """Benchmark pagination method."""
    print("\n=== Benchmark: paginate ===")

    for num_records in [100, 1000, 10000]:
        print(f"\n  Dataset: {num_records} records")
        engine = setup_database(num_records)

        with Session(engine) as session:
            base_query = select(Hero)

            # Create mock request and FSPManager
            request = Mock()
            request.url = Mock()
            request.url.include_query_params = Mock(return_value="http://example.com")

            pagination = PaginationQuery(page=1, per_page=20)
            fsp = FSPManager(request=request, filters=None, sorting=None, pagination=pagination)

            def paginate_first_page():
                return fsp.paginate(base_query, session)

            # Deep pagination
            pagination_deep = PaginationQuery(page=25, per_page=20)
            fsp_deep = FSPManager(
                request=request, filters=None, sorting=None, pagination=pagination_deep
            )

            def paginate_deep():
                return fsp_deep.paginate(base_query, session)

            tests = {
                "Page 1 (20 items)": paginate_first_page,
                "Page 25 (20 items)": paginate_deep,
            }

            for name, func in tests.items():
                result = time_function(func, iterations=100)
                print(
                    f"    {name:30s} - Avg: {result['avg']:6.3f}ms, "
                    f"P50: {result['p50']:6.3f}ms, P95: {result['p95']:6.3f}ms"
                )


def benchmark_generate_response():
    """Benchmark full generate_response method."""
    print("\n=== Benchmark: generate_response (full pipeline) ===")

    for num_records in [100, 1000, 10000]:
        print(f"\n  Dataset: {num_records} records")
        engine = setup_database(num_records)

        with Session(engine) as session:
            base_query = select(Hero)

            # Create mock request
            request = Mock()
            request.url = Mock()
            request.url.include_query_params = Mock(return_value="http://example.com")

            # Simple pagination
            pagination = PaginationQuery(page=1, per_page=20)
            fsp_simple = FSPManager(
                request=request, filters=None, sorting=None, pagination=pagination
            )

            def simple_response():
                return fsp_simple.generate_response(base_query, session)

            # With filters and sorting
            filters = [
                Filter(field="age", operator=FilterOperator.GTE, value="30"),
                Filter(field="deleted", operator=FilterOperator.EQ, value="false"),
            ]
            sorting = SortingQuery(sort_by="age", order="asc")
            fsp_complex = FSPManager(
                request=request, filters=filters, sorting=sorting, pagination=pagination
            )

            def complex_response():
                return fsp_complex.generate_response(base_query, session)

            tests = {
                "Simple (no filters/sort)": simple_response,
                "Complex (filters + sort)": complex_response,
            }

            for name, func in tests.items():
                result = time_function(func, iterations=50)
                print(
                    f"    {name:30s} - Avg: {result['avg']:6.3f}ms, "
                    f"P50: {result['p50']:6.3f}ms, P95: {result['p95']:6.3f}ms"
                )


def main():
    """Run all internal benchmarks."""
    print("=" * 80)
    print("FASTAPI-FSP INTERNAL BENCHMARKS")
    print("=" * 80)

    benchmark_coerce_value()
    benchmark_split_values()
    benchmark_apply_filter()
    benchmark_apply_filters()
    benchmark_apply_sort()
    benchmark_count_total()
    benchmark_pagination()
    benchmark_generate_response()

    print("\n" + "=" * 80)
    print("BENCHMARKS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
