import { useEffect, useMemo, useState } from "react";
import { flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { buildQuery, fetchJson } from "./api.js";

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

const columns = [
  {
    id: "last_name",
    header: "Name",
    accessorFn: (row) => `${row.first_name} ${row.last_name}`,
  },
  { accessorKey: "email", header: "Email", enableSorting: false },
  { accessorKey: "department", header: "Department" },
  { accessorKey: "title", header: "Title" },
  { accessorKey: "city", header: "City" },
  {
    accessorKey: "salary",
    header: "Salary",
    cell: (info) => currency.format(info.getValue()),
    meta: { align: "right" },
  },
  { accessorKey: "hired_on", header: "Hired" },
];

function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export default function App() {
  const [pagination, setPagination] = useState({ pageIndex: 0, pageSize: 10 });
  const [sorting, setSorting] = useState([{ id: "last_name", desc: false }]);
  const [searchInput, setSearchInput] = useState("");
  const [department, setDepartment] = useState("");
  const [minSalary, setMinSalary] = useState("");
  const [departments, setDepartments] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  const search = useDebounced(searchInput);
  const debouncedMinSalary = useDebounced(minSalary);

  // Any filter change starts again from the first page.
  useEffect(() => {
    setPagination((p) => ({ ...p, pageIndex: 0 }));
  }, [search, department, debouncedMinSalary]);

  const query = useMemo(
    () =>
      buildQuery({ pagination, sorting, search, department, minSalary: debouncedMinSalary }),
    [pagination, sorting, search, department, debouncedMinSalary],
  );

  useEffect(() => {
    const controller = new AbortController();
    fetchJson("/api/departments", controller.signal)
      .then(setDepartments)
      .catch(() => {});
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    fetchJson(`/api/employees?${query}`, controller.signal)
      .then((body) => {
        setResult(body);
        setError(null);
      })
      .catch((err) => {
        if (err.name !== "AbortError") setError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [query]);

  const meta = result?.meta.pagination;

  const table = useReactTable({
    data: result?.data ?? [],
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    manualSorting: true,
    enableMultiSort: false,
    pageCount: meta?.total_pages ?? -1,
    state: { pagination, sorting },
    onPaginationChange: setPagination,
    onSortingChange: (updater) => {
      setSorting(updater);
      setPagination((p) => ({ ...p, pageIndex: 0 }));
    },
  });

  const firstItem = meta && meta.total_items > 0 ? pagination.pageIndex * pagination.pageSize + 1 : 0;
  const lastItem = firstItem > 0 ? firstItem + result.data.length - 1 : 0;

  return (
    <main>
      <header>
        <h1>Employees</h1>
        <p>
          A <a href="https://tanstack.com/table">TanStack Table</a> whose search, filters, sorting
          and paging all run on the server through one{" "}
          <a href="https://github.com/fromej-dev/fastapi-fsp">fastapi-fsp</a> endpoint.
        </p>
      </header>

      <section className="toolbar">
        <input
          type="search"
          placeholder="Search name, email, title, city…"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          aria-label="Search"
        />
        <select
          value={department}
          onChange={(e) => setDepartment(e.target.value)}
          aria-label="Department"
        >
          <option value="">All departments</option>
          {departments.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
        <input
          type="number"
          min="0"
          step="10000"
          placeholder="Min salary"
          value={minSalary}
          onChange={(e) => setMinSalary(e.target.value)}
          aria-label="Minimum salary"
        />
      </section>

      <div className={`table-wrap${loading ? " loading" : ""}`}>
        <table>
          <thead>
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => {
                  const sorted = header.column.getIsSorted();
                  const canSort = header.column.getCanSort();
                  return (
                    <th
                      key={header.id}
                      className={header.column.columnDef.meta?.align}
                      aria-sort={sorted ? (sorted === "desc" ? "descending" : "ascending") : undefined}
                    >
                      {canSort ? (
                        <button onClick={header.column.getToggleSortingHandler()}>
                          {flexRender(header.column.columnDef.header, header.getContext())}
                          <span className="sort">{{ asc: "▲", desc: "▼" }[sorted] ?? "↕"}</span>
                        </button>
                      ) : (
                        flexRender(header.column.columnDef.header, header.getContext())
                      )}
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.original.id}>
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className={cell.column.columnDef.meta?.align}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {result && result.data.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="empty">
                  No employees match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {error && <p className="error">{error}</p>}

      <footer className="pager">
        <span>{meta ? `${firstItem}–${lastItem} of ${meta.total_items}` : "Loading…"}</span>
        <select
          value={pagination.pageSize}
          onChange={(e) => setPagination({ pageIndex: 0, pageSize: Number(e.target.value) })}
          aria-label="Rows per page"
        >
          {[10, 25, 50, 100].map((size) => (
            <option key={size} value={size}>
              {size} / page
            </option>
          ))}
        </select>
        <div className="buttons">
          <button onClick={() => table.firstPage()} disabled={!table.getCanPreviousPage()}>
            «
          </button>
          <button onClick={() => table.previousPage()} disabled={!table.getCanPreviousPage()}>
            ‹
          </button>
          <span>
            Page {pagination.pageIndex + 1} of {meta?.total_pages ?? "…"}
          </span>
          <button onClick={() => table.nextPage()} disabled={!table.getCanNextPage()}>
            ›
          </button>
          <button onClick={() => table.lastPage()} disabled={!table.getCanNextPage()}>
            »
          </button>
        </div>
      </footer>

      <p className="request">
        <span>Request</span>
        <code>GET /api/employees?{decodeURIComponent(query.replaceAll("+", " "))}</code>
      </p>
    </main>
  );
}
