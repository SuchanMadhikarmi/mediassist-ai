// ============================================================
// src/components/admin/AdminDashboard.jsx
// The staff dashboard — ONE fetch consumes the entire /api/stats
// payload built in Phase 7.5 (aggregates computed in Postgres, not in
// the browser). Every section is a pure function of that data; the
// frontend does zero aggregation and only renders.
//
// CONCEPT (chart-from-CSS): a "bar chart" is just divs whose width is
// scaled against the max value. No chart library needed at this scale.
// ============================================================

import { useEffect, useState } from "react";
import { api } from "../../lib/api.js";
import { Card, Spinner, ErrorBanner, Bar } from "../shared/ui.jsx";

function TotalsCard({ label, value }) {
  return (
    <div className="border border-hairline bg-panel p-4 min-w-0">
      <p className="serif-title text-3xl text-ink leading-none">{value}</p>
      <p className="text-sm font-medium text-muted mt-2 truncate" title={label}>{label}</p>
      <p className="text-xs text-muted/70 truncate">in database</p>
    </div>
  );
}

export default function AdminDashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .get("/api/stats")
      .then(setData)
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <ErrorBanner message={error} onDismiss={() => setError(null)} />;
  if (!data) return <Spinner label="Loading system statistics…" />;

  const t = data.totals;
  const q = data.quality;

  return (
    <div className="space-y-6">
      {/* ── Top cards: totals ──────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <TotalsCard label="Predictions" value={t.predictions} />
        <TotalsCard label="Users" value={t.users} />
        <TotalsCard label="Documents" value={t.documents} />
        <TotalsCard label="ERP orders" value={t.erp_orders} />
        <TotalsCard label="Model versions" value={t.model_versions} />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* ── GROUP BY outcomes (the bars) ─────────────────────── */}
        <Card title="Predictions by output">
          <BarRow items={data.predictions_by_output} />
        </Card>

        <Card title="Predictions by model">
          <BarRow items={data.predictions_by_model} />
        </Card>

        <Card title="Users by role">
          <BarRow items={data.users_by_role} />
        </Card>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* ── Quality gauges ───────────────────────────────────── */}
        <Card title="Model quality">
          <dl className="text-sm space-y-2">
            <Metric label="Avg confidence" value={q.avg_confidence != null ? `${(q.avg_confidence * 100).toFixed(1)}%` : "—"} />
            <Metric label="Avg inference time" value={q.avg_inference_time_ms != null ? `${q.avg_inference_time_ms.toFixed(1)} ms` : "—"} />
            <Metric label="Positive rate" value={q.positive_rate != null ? `${(q.positive_rate * 100).toFixed(1)}%` : "—"} />
          </dl>
        </Card>

        {/* ── 7-day trend ──────────────────────────────────────── */}
        <Card title="Predictions — last 7 days">
          <BarRow items={data.predictions_last_7_days} />
        </Card>

        {/* ── Recent activity feed ─────────────────────────────── */}
        <Card title="Recent activity">
          {data.recent_activity.length === 0 ? (
            <p className="text-sm text-muted">No activity yet.</p>
          ) : (
            <ul className="text-sm space-y-2.5">
              {data.recent_activity.map((a, i) => (
                <li key={i} className="flex items-baseline gap-2 min-w-0">
                  <span className="text-xs text-muted/70 whitespace-nowrap shrink-0">
                    {new Date(a.created_at).toLocaleString()}
                  </span>
                  <span className="font-medium truncate min-w-0">{a.action}</span>
                  <span className="text-muted truncate min-w-0">by {a.username || "—"}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      {/* ── Model registry cards ──────────────────────────────── */}
      <Card title="Model registry">
        <div className="grid md:grid-cols-2 gap-4">
          {data.model_registry.map((m) => (
            <div key={m.version} className="border border-hairline p-4">
              <div className="flex items-center justify-between mb-1">
                <h3 className="font-medium text-ink">{m.model_name}</h3>
                <span
                  className={`text-xs px-2.5 py-0.5 border ${
                    m.is_active
                      ? "bg-green-50 border-green-600 text-green-700"
                      : "bg-white border-hairline text-muted"
                  }`}
                >
                  {m.is_active ? "Active" : "Inactive"}
                </span>
              </div>
              <p className="text-xs text-muted mb-3">{m.version}</p>
              {m.metrics && (
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                  {Object.entries(m.metrics)
                    .filter(([k]) => k !== "confusion_matrix")
                    .map(([k, v]) => (
                      <div key={k} className="flex justify-between gap-2 min-w-0">
                        <span className="text-muted truncate">{k}</span>
                        <span className="font-medium shrink-0">
                          {typeof v === "number" ? v.toFixed(4) : v}
                        </span>
                      </div>
                    ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

// Bars for a GROUP BY list — bar width proportional to the max value.
function BarRow({ items }) {
  const max = Math.max(1, ...items.map((i) => i.count));
  if (items.length === 0)
    return <p className="text-sm text-muted">No data yet.</p>;
  return (
    <div>
      {items.map((i) => (
        <Bar key={i.label} label={i.label} count={i.count} max={max} />
      ))}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="flex justify-between border-b border-hairline pb-1.5">
      <dt className="text-muted">{label}</dt>
      <dd className="font-medium text-ink">{value}</dd>
    </div>
  );
}