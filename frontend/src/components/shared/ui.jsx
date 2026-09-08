// ============================================================
// src/components/shared/ui.jsx — tiny UI kit.
// Small reusable presentational components. Each is a pure function of
// its props: same props -> same UI, every time (the React contract).
// ============================================================

export function Card({ title, action, children, className = "" }) {
  return (
    <div className={`card ${className}`}>
      {(title || action) && (
        <div className="flex items-center justify-between mb-4 space-x-4">
          <h2 className="flex items-center gap-2.5 serif-title text-xl text-ink">
            {/* Iodine tick — the card's "reading point". */}
            {title && <span className="w-1.5 h-1.5 bg-iodine-600 shrink-0" />}
            {title}
          </h2>
          {action}
        </div>
      )}
      {children}
    </div>
  );
}

export function ErrorBanner({ message, onDismiss }) {
  if (!message) return null;
  return (
    <div className="mb-4 flex items-start justify-between gap-3 text-sm text-signal bg-white border border-hairline border-l-4 border-l-signal px-3 py-2 wrap-anywhere">
      <span>{message}</span>
      {onDismiss && (
        <button onClick={onDismiss} className="shrink-0 text-signal opacity-60 hover:opacity-100">
          ×
        </button>
      )}
    </div>
  );
}

export function Spinner({ label }) {
  return (
    <div className="flex items-center gap-2 text-muted text-sm py-4">
      <span className="inline-block w-4 h-4 border-2 border-hairline border-t-iodine-600 animate-spin" />
      {label || "Loading…"}
    </div>
  );
}

export function EmptyState({ text }) {
  return (
    <div className="py-8 text-center">
      <p className="text-sm text-muted">{text}</p>
      <div className="mt-3 inline-block w-10 border-t border-hairline border-t-2" />
    </div>
  );
}

// Pagination: standard "page x of y" bar. The parent owns the data
// (query params); this only reports the page the user asked for.
export function Pagination({ page, pages, total, onChange }) {
  if (pages <= 1) return null;
  return (
    <div className="flex items-center justify-between mt-5 pt-3 border-t border-hairline text-sm text-muted">
      <span>
        Page {page} of {pages} ({total} total)
      </span>
      <div className="flex gap-1">
        <button
          className="btn-ghost disabled:opacity-40"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          Prev
        </button>
        <button
          className="btn-ghost disabled:opacity-40"
          disabled={page >= pages}
          onClick={() => onChange(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}

// Generic horizontal bar built from CSS width — a "chart" library is
// overkill until datasets get complex. One LabelCount -> one bar.
export function Bar({ label, count, max, color = "bg-iodine-600" }) {
  const width = max > 0 ? Math.round((count / max) * 100) : 0;
  return (
    <div className="mb-3">
      <div className="flex justify-between text-sm mb-1">
        <span className="capitalize text-ink">{label}</span>
        <span className="text-muted font-medium">{count}</span>
      </div>
      <div className="h-2.5 bg-hairline/40 overflow-hidden">
        <div
          className={`h-full ${color} transition-all duration-500`}
          style={{ width: `${width}%` }}
        />
      </div>
    </div>
  );
}

// Confidence as a colored tick + percentage.
export function Confidence({ value }) {
  if (value === null || value === undefined) return <span className="text-muted">—</span>;
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? "bg-green-600" : pct >= 50 ? "bg-iodine-600" : "bg-signal";
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`w-2 h-2 ${color}`} />
      {pct}%
    </span>
  );
}