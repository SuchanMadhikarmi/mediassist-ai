// ============================================================
// src/components/prediction/PredictionsTable.jsx
// Shared list for BOTH end_users (own rows) and staff (all rows).
//
// CONCEPT (the effect/data-fetch pattern):
//   `useEffect` runs the fetch whenever its DEPENDENCIES [page, search]
//   change. First mount -> fetch page 1. Prev/Next -> setPage -> effect
//   re-runs -> fetch. Typing a search -> debounce-free, refetch on the
//   submitted term. Data lives in `rows` state; render reads it.
//
// CONCEPT (Search) — classic query-parameter pattern:
//   The search is NOT applied locally — it's sent as ?search=, and the
//   SERVER filters (consistent with everything else, works at scale).
// ============================================================

import { useCallback, useEffect, useState, Fragment } from "react";
import { api } from "../../lib/api.js";
import { Card, ErrorBanner, EmptyState, Pagination, Spinner, Confidence } from "../shared/ui.jsx";

const PER_PAGE = 8;

export default function PredictionsTable({ canReview }) {
  const [rows, setRows] = useState(null);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [submittedSearch, setSubmittedSearch] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState(null); // row id showing input_data
  const [review, setReview] = useState({});       // row id -> {output, approve}
  const [actionError, setActionError] = useState(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const qs = new URLSearchParams({ page, per_page: PER_PAGE });
      if (submittedSearch) qs.set("search", submittedSearch);
      const data = await api.get(`/api/predictions?${qs.toString()}`);
      setRows(data.items);
      setPages(data.pages);
      setTotal(data.total);
      if (page > data.pages) setPage(1); // page empties after a delete
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }, [page, submittedSearch]);

  useEffect(() => { load(); }, [load]);

  const submitSearch = (e) => {
    e.preventDefault();
    setPage(1);
    setSubmittedSearch(search.trim());
  };

  const doReview = async (id) => {
    const entry = review[id];
    if (!entry?.output) return;
    try {
      await api.put(`/api/predictions/${id}/review`, {
        reviewed_output: entry.output,
        is_approved: entry.approve !== false,
      });
      setActionError(null);
      load();
    } catch (err) {
      setActionError(err.message);
    }
  };

  const doDelete = async (id) => {
    if (!window.confirm("Delete this prediction record?")) return;
    try {
      await api.delete(`/api/predictions/${id}`);
      setActionError(null);
      load();
    } catch (err) {
      setActionError(err.message);
    }
  };

  return (
    <Card
      title={canReview ? "All predictions (review)" : "My predictions"}
      action={
        <form onSubmit={submitSearch} className="flex gap-2">
          <input
            className="input !w-44"
            placeholder="Filter by yes / no"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button className="btn-primary !py-2" type="submit">Search</button>
        </form>
      }
    >
      <ErrorBanner message={actionError} onDismiss={() => setActionError(null)} />
      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      {busy && !rows ? (
        <Spinner />
      ) : !rows || rows.length === 0 ? (
        <EmptyState text="No prediction records yet." />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="thead">
                <th>Created</th>
                <th>Output</th>
                <th>Confidence</th>
                <th>Model</th>
                <th>Time</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody className="tbody">
              {rows.map((p) => (
                <Fragment key={p.id}>
                  <tr className="border-b border-hairline">
                    <td className="py-2 pr-3 text-muted whitespace-nowrap">
                      {new Date(p.created_at).toLocaleString()}
                    </td>
                    <td className="py-2 pr-3">
                      <span
                        className={`px-2.5 py-0.5 font-medium border whitespace-nowrap ${
                          p.predicted_output === "yes"
                            ? "bg-green-50 border-green-600 text-green-700"
                            : p.predicted_output === "no"
                              ? "bg-white border-signal text-signal"
                              : "bg-white border-hairline text-muted"
                        }`}
                      >
                        {p.predicted_output}
                      </span>
                    </td>
                    <td className="py-2 pr-3 whitespace-nowrap"><Confidence value={p.confidence} /></td>
                    <td className="py-2 pr-3 text-muted whitespace-nowrap">{p.model_version}</td>
                    <td className="py-2 pr-3 text-muted whitespace-nowrap">{p.inference_time_ms} ms</td>
                    <td className="py-2">
                      <button
                        className="btn-ghost"
                        onClick={() => setExpanded(expanded === p.id ? null : p.id)}
                      >
                        {expanded === p.id ? "Hide" : "Input"}
                      </button>
                      {canReview && (
                        <>
                          <button className="btn-ghost" onClick={() => doDelete(p.id)}>
                            Delete
                          </button>
                        </>
                      )}
                    </td>
                  </tr>
                  {expanded === p.id && (
                    <tr className="bg-paper">
                      <td colSpan={6} className="py-3">
                        <pre className="text-xs text-muted overflow-x-auto">
                          {JSON.stringify(p.input_data, null, 2)}
                        </pre>
                        {canReview && (
                          <div className="mt-3 flex flex-wrap items-end gap-2">
                            <input
                              className="input !w-40"
                              placeholder="Override output (yes/no)"
                              value={review[p.id]?.output || ""}
                              onChange={(e) =>
                                setReview({ ...review, [p.id]: { ...review[p.id], output: e.target.value } })
                              }
                            />
                            <label className="flex items-center gap-1.5 text-sm text-muted">
                              <input
                                type="checkbox"
                                defaultChecked
                                onChange={(e) =>
                                  setReview({ ...review, [p.id]: { ...review[p.id], approve: e.target.checked } })
                                }
                              />
                              Mark approved
                            </label>
                            <button className="btn-primary !py-2" onClick={() => doReview(p.id)}>
                              Save review
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Pagination page={page} pages={pages} total={total} onChange={setPage} />
    </Card>
  );
}