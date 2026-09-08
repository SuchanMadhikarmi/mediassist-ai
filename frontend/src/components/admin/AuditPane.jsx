// ============================================================
// src/components/admin/AuditPane.jsx — append-only audit trail.
// Read-only viewer (the API has no audit-write endpoint — by design).
// Pattern: filtered (by action), paginated table. Mirrors every other
// list view — one UI pattern for the whole CRUD suite.
// ============================================================

import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api.js";
import { Card, ErrorBanner, EmptyState, Pagination, Spinner } from "../shared/ui.jsx";

const PER_PAGE = 12;

export default function AuditPane() {
  const [rows, setRows] = useState(null);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [total, setTotal] = useState(0);
  const [action, setAction] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const qs = new URLSearchParams({ page, per_page: PER_PAGE });
      if (submitted) qs.set("action", submitted);
      const data = await api.get(`/api/audit?${qs.toString()}`);
      setRows(data.items);
      setPages(data.pages);
      setTotal(data.total);
    } catch (err) {
      setError(err.message);
    }
  }, [page, submitted]);

  useEffect(() => { load(); }, [load]);

  const submitFilter = (e) => {
    e.preventDefault();
    setPage(1);
    setSubmitted(action.trim());
  };

  return (
    <Card
      title="Audit trail"
      action={
        <form onSubmit={submitFilter} className="flex gap-2">
          <input
            className="input !w-44"
            placeholder="Filter by action"
            value={action}
            onChange={(e) => setAction(e.target.value)}
          />
          <button className="btn-primary !py-2" type="submit">Filter</button>
        </form>
      }
    >
      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      {!rows ? (
        <Spinner />
      ) : rows.length === 0 ? (
        <EmptyState text="No audit entries match." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="thead">
                <th>When</th>
                <th>User</th>
                <th>Action</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody className="tbody">
              {rows.map((a) => (
                <tr key={a.id} className="border-b border-hairline">
                  <td className="py-2 pr-3 text-muted whitespace-nowrap">
                    {new Date(a.created_at).toLocaleString()}
                  </td>
                  <td className="py-2 pr-3">{a.user_id ? a.user_id.slice(0, 8) : "—"}</td>
                  <td className="py-2 pr-3">
                    <span className="text-xs border border-hairline bg-white px-2 py-0.5 font-medium whitespace-nowrap">
                      {a.action}
                    </span>
                  </td>
                  <td className="py-2 text-muted max-w-md">
                    {a.details ? (
                      <pre className="text-xs overflow-x-auto">{JSON.stringify(a.details)}</pre>
                    ) : (
                      "—"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Pagination page={page} pages={pages} total={total} onChange={setPage} />
    </Card>
  );
}