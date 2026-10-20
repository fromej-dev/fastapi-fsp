// Turns the table state into fastapi-fsp query parameters.
// See https://fromej-dev.github.io/fastapi-fsp/query-parameters/

const SEARCH_FIELDS = ["first_name", "last_name", "email", "title", "city"];

export function buildQuery({ pagination, sorting, search, department, minSalary }) {
  const params = new URLSearchParams();

  // Pagination: TanStack pages are 0-based, fastapi-fsp pages are 1-based.
  params.set("page", String(pagination.pageIndex + 1));
  params.set("per_page", String(pagination.pageSize));

  // Sorting: one column at a time.
  if (sorting.length > 0) {
    params.set("sort_by", sorting[0].id);
    params.set("order", sorting[0].desc ? "desc" : "asc");
  }

  // Search box: every word must match at least one of the search fields.
  if (search.trim()) {
    params.set("search", search.trim());
    params.set("search_fields", SEARCH_FIELDS.join(","));
  }

  // Column filters: repeat the field/operator/value triplet for each one.
  const filters = [];
  if (department) filters.push(["department", "eq", department]);
  if (minSalary) filters.push(["salary", "gte", minSalary]);
  for (const [field, operator, value] of filters) {
    params.append("field", field);
    params.append("operator", operator);
    params.append("value", value);
  }

  return params.toString();
}

export async function fetchJson(url, signal) {
  const response = await fetch(url, { signal });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail ?? response.statusText);
  return body;
}
