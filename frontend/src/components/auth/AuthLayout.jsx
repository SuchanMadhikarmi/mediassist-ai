// ============================================================
// src/components/auth/AuthLayout.jsx — shared sign-in / register frame.
//
// WHY: both auth screens had a bare centered form on paper — "too
// minimal". Splitting the screen fixes that in one shared place:
//   LEFT  (lg+): ink "instrument plate" — brand, what the system does,
//                 and the demo credentials (a live demo needs a hint
//                 card, otherwise the viva audience is stuck).
//   RIGHT (all) : the actual form, horizontally centered on paper.
//
// CONCEPT (composition): the caller passes the card body as children;
// the layout owns the frame, title, error banner + footer CTA. Login
// and Register never duplicate this chrome again.
// ============================================================

const FEATURES = [
  ["RAG document query", "Ask questions about clinical manuals — answers come back with cited sources."],
  ["ML subscription prediction", "A trained XGBoost model scores customer profiles with calibrated confidence."],
  ["Role-based access", "Admin, expert and end-user views are enforced end to end."],
];

const CREDENTIALS = [
  ["admin", "admin123"],
  ["expert1", "expert123"],
  ["nurse1", "nurse123"],
];

export default function AuthLayout({ title, subtitle, children, footer }) {
  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      {/* ── Left: ink instrument plate (hidden on small screens) ── */}
      <aside className="hidden lg:flex flex-col bg-ink text-paper border-r border-hairline">
        <div className="p-10 flex flex-col justify-between min-h-full flex-1">
          <div>
            <p className="text-[11px] tracking-[0.18em] uppercase text-iodine-300 mb-3">
              Clinical support system
            </p>
            <p className="serif-title text-5xl text-paper leading-[1.05]">
              MediAssist AI
            </p>
            <div className="w-12 h-1 bg-iodine-600 mt-6 mb-8" />

            <ul className="space-y-6">
              {FEATURES.map(([t, d]) => (
                <li key={t} className="flex gap-3">
                  <span className="mt-1.5 w-2 h-2 bg-iodine-500 shrink-0" />
                  <div>
                    <p className="text-sm font-medium text-paper">{t}</p>
                    <p className="text-sm text-paper/60">{d}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          {/* Demo credentials — a demo app must be explorable. */}
          <div className="border border-paper/20 p-4">
            <p className="text-[11px] uppercase tracking-[0.18em] text-iodine-300 mb-2">
              Demo accounts
            </p>
            <div className="flex gap-4 text-xs text-paper/70">
              {CREDENTIALS.map(([u, p]) => (
                <span key={u} className="whitespace-nowrap">
                  <span className="text-paper font-medium">{u}</span>
                  <span className="text-paper/40"> / </span>
                  {p}
                </span>
              ))}
            </div>
          </div>
        </div>
      </aside>

      {/* ── Right: paper form region ─────────────────────────────── */}
      <main className="flex flex-col justify-center">
        <div className="ruler" />
        <div className="max-w-sm mx-auto w-full px-6 py-10">
          <p className="serif-title text-3xl text-ink mb-1">{title}</p>
          <p className="text-sm text-muted mb-6">{subtitle}</p>
          {children}
          {footer && <div className="mt-4 text-sm text-center text-muted">{footer}</div>}
        </div>
      </main>
    </div>
  );
}