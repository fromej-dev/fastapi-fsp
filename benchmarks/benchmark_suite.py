"""Comprehensive benchmark suite for fastapi-fsp package."""

import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Field, Session, SQLModel, create_engine, select

from fastapi_fsp.fsp import FSPManager
from fastapi_fsp.models import PaginatedResponse


class HeroBase(SQLModel):
    """Base hero model for benchmarking."""

    name: str = Field(index=True)
    secret_name: str
    age: Optional[int] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    deleted: bool = Field(default=False)
    email: str = Field(default="", index=True)
    city: str = Field(default="")


class Hero(HeroBase, table=True):
    """Hero model with table definition."""

    id: Optional[int] = Field(default=None, primary_key=True)


class HeroPublic(HeroBase):
    """Public hero model for API responses."""

    id: int


class BenchmarkResult:
    """Container for benchmark results."""

    def __init__(self, name: str):
        self.name = name
        self.timings: List[float] = []
        self.avg_time: float = 0.0
        self.min_time: float = 0.0
        self.max_time: float = 0.0
        self.p50_time: float = 0.0
        self.p95_time: float = 0.0
        self.p99_time: float = 0.0
        self.iterations: int = 0

    def add_timing(self, duration: float):
        """Add a timing measurement."""
        self.timings.append(duration)

    def calculate_stats(self):
        """Calculate statistics from timings."""
        if not self.timings:
            return
        self.timings.sort()
        self.iterations = len(self.timings)
        self.avg_time = sum(self.timings) / self.iterations
        self.min_time = self.timings[0]
        self.max_time = self.timings[-1]
        self.p50_time = self.timings[int(self.iterations * 0.5)]
        self.p95_time = self.timings[int(self.iterations * 0.95)]
        self.p99_time = self.timings[int(self.iterations * 0.99)]

    def __str__(self) -> str:
        """String representation of benchmark results."""
        return (
            f"{self.name}:\n"
            f"  Iterations: {self.iterations}\n"
            f"  Avg: {self.avg_time*1000:.2f}ms\n"
            f"  Min: {self.min_time*1000:.2f}ms\n"
            f"  Max: {self.max_time*1000:.2f}ms\n"
            f"  P50: {self.p50_time*1000:.2f}ms\n"
            f"  P95: {self.p95_time*1000:.2f}ms\n"
            f"  P99: {self.p99_time*1000:.2f}ms"
        )


class BenchmarkSuite:
    """Main benchmark suite for fastapi-fsp."""

    def __init__(self, num_records: int = 1000, iterations: int = 100):
        """
        Initialize benchmark suite.

        Args:
            num_records: Number of records to generate for testing
            iterations: Number of iterations per benchmark
        """
        self.num_records = num_records
        self.iterations = iterations
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        self.app = FastAPI()
        self.client = None
        self.results: Dict[str, BenchmarkResult] = {}

    def setup(self):
        """Set up test database and app."""
        SQLModel.metadata.create_all(self.engine)
        self._populate_database()
        self._setup_app()
        self.client = TestClient(self.app)

    def _populate_database(self):
        """Populate database with test data."""
        cities = ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"]
        base_time = datetime.now()

        with Session(self.engine) as session:
            heroes = []
            for i in range(self.num_records):
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

    def _setup_app(self):
        """Set up FastAPI app with endpoints."""

        def get_session():
            with Session(self.engine) as session:
                yield session

        @self.app.get("/heroes/", response_model=PaginatedResponse[HeroPublic])
        def read_heroes(
            *, session: Session = FastAPI.Depends(get_session), fsp: FSPManager = FastAPI.Depends(FSPManager)
        ):
            query = select(Hero)
            return fsp.generate_response(query, session)

    def _run_benchmark(
        self, name: str, request_func: Callable[[], Any]
    ) -> BenchmarkResult:
        """
        Run a single benchmark.

        Args:
            name: Name of the benchmark
            request_func: Function that makes the request

        Returns:
            BenchmarkResult: Results of the benchmark
        """
        result = BenchmarkResult(name)

        # Warmup
        for _ in range(10):
            request_func()

        # Actual benchmark
        for _ in range(self.iterations):
            start = time.perf_counter()
            request_func()
            end = time.perf_counter()
            result.add_timing(end - start)

        result.calculate_stats()
        self.results[name] = result
        return result

    def benchmark_basic_pagination(self):
        """Benchmark basic pagination without filters or sorting."""

        def request():
            return self.client.get("/heroes/?page=1&per_page=20")

        return self._run_benchmark("Basic Pagination (20 items)", request)

    def benchmark_large_page(self):
        """Benchmark large page size."""

        def request():
            return self.client.get("/heroes/?page=1&per_page=100")

        return self._run_benchmark("Large Page (100 items)", request)

    def benchmark_deep_pagination(self):
        """Benchmark pagination at a deeper page."""

        def request():
            return self.client.get(f"/heroes/?page=25&per_page=20")

        return self._run_benchmark("Deep Pagination (page 25)", request)

    def benchmark_single_filter_eq(self):
        """Benchmark single equality filter."""

        def request():
            return self.client.get("/heroes/?field=age&operator=eq&value=30")

        return self._run_benchmark("Single Filter (EQ)", request)

    def benchmark_single_filter_range(self):
        """Benchmark single range filter."""

        def request():
            return self.client.get("/heroes/?field=age&operator=gte&value=30")

        return self._run_benchmark("Single Filter (GTE)", request)

    def benchmark_single_filter_like(self):
        """Benchmark LIKE filter."""

        def request():
            return self.client.get("/heroes/?field=name&operator=ilike&value=%Hero_1%")

        return self._run_benchmark("Single Filter (ILIKE pattern)", request)

    def benchmark_multiple_filters(self):
        """Benchmark multiple filters."""

        def request():
            return self.client.get(
                "/heroes/?field=age&operator=gte&value=30"
                "&field=deleted&operator=eq&value=false"
                "&field=city&operator=eq&value=Chicago"
            )

        return self._run_benchmark("Multiple Filters (3 conditions)", request)

    def benchmark_indexed_filters(self):
        """Benchmark indexed filter format."""

        def request():
            return self.client.get(
                "/heroes/?filters[0][field]=age&filters[0][operator]=gte&filters[0][value]=30"
                "&filters[1][field]=deleted&filters[1][operator]=eq&filters[1][value]=false"
            )

        return self._run_benchmark("Indexed Filters (2 conditions)", request)

    def benchmark_filter_in_operator(self):
        """Benchmark IN operator with multiple values."""

        def request():
            return self.client.get(
                "/heroes/?field=city&operator=in&value=Chicago,Houston,Phoenix"
            )

        return self._run_benchmark("Filter IN (3 values)", request)

    def benchmark_filter_between(self):
        """Benchmark BETWEEN operator."""

        def request():
            return self.client.get("/heroes/?field=age&operator=between&value=25,45")

        return self._run_benchmark("Filter BETWEEN", request)

    def benchmark_simple_sort(self):
        """Benchmark simple sorting."""

        def request():
            return self.client.get("/heroes/?sort_by=age&order=asc")

        return self._run_benchmark("Simple Sort (ASC)", request)

    def benchmark_sort_desc(self):
        """Benchmark descending sort."""

        def request():
            return self.client.get("/heroes/?sort_by=created_at&order=desc")

        return self._run_benchmark("Sort (DESC)", request)

    def benchmark_filter_and_sort(self):
        """Benchmark filtering and sorting combined."""

        def request():
            return self.client.get(
                "/heroes/?field=age&operator=gte&value=30&sort_by=name&order=asc"
            )

        return self._run_benchmark("Filter + Sort", request)

    def benchmark_complex_query(self):
        """Benchmark complex query with multiple filters, sort, and pagination."""

        def request():
            return self.client.get(
                "/heroes/?field=age&operator=gte&value=25"
                "&field=age&operator=lte&value=60"
                "&field=deleted&operator=eq&value=false"
                "&sort_by=age&order=desc"
                "&page=2&per_page=25"
            )

        return self._run_benchmark("Complex Query (filters+sort+pagination)", request)

    def run_all_benchmarks(self) -> Dict[str, BenchmarkResult]:
        """Run all benchmarks and return results."""
        print(f"Running benchmarks with {self.num_records} records, {self.iterations} iterations each...")
        print("=" * 80)

        benchmarks = [
            self.benchmark_basic_pagination,
            self.benchmark_large_page,
            self.benchmark_deep_pagination,
            self.benchmark_single_filter_eq,
            self.benchmark_single_filter_range,
            self.benchmark_single_filter_like,
            self.benchmark_multiple_filters,
            self.benchmark_indexed_filters,
            self.benchmark_filter_in_operator,
            self.benchmark_filter_between,
            self.benchmark_simple_sort,
            self.benchmark_sort_desc,
            self.benchmark_filter_and_sort,
            self.benchmark_complex_query,
        ]

        for benchmark in benchmarks:
            result = benchmark()
            print(result)
            print("-" * 80)

        return self.results

    def print_summary(self):
        """Print summary of all benchmarks."""
        print("\n" + "=" * 80)
        print("BENCHMARK SUMMARY")
        print("=" * 80)

        sorted_results = sorted(self.results.values(), key=lambda r: r.avg_time)

        print("\nFastest to Slowest (by average time):")
        for i, result in enumerate(sorted_results, 1):
            print(f"{i}. {result.name}: {result.avg_time*1000:.2f}ms avg")


def main():
    """Run benchmark suite."""
    # Test with different dataset sizes
    for num_records in [100, 1000, 10000]:
        print(f"\n\n{'='*80}")
        print(f"TESTING WITH {num_records} RECORDS")
        print(f"{'='*80}\n")

        suite = BenchmarkSuite(num_records=num_records, iterations=50)
        suite.setup()
        suite.run_all_benchmarks()
        suite.print_summary()


if __name__ == "__main__":
    main()
