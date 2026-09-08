// ============================================================
// src/components/layout/Layout.jsx — the app frame.
//
// CONCEPT (composition):
//   Layout is the SHELL — nav + content region. The active view is
//   passed in as `children` (React composition). Layout doesn't care
//   which view it hosts; it just renders it. This keeps every screen
//   visually consistent for free.
//
// The nav items are derived from the USER'S ROLE (a naive "show
// everything" menu would leak admin screens to end_users). The backend
// still enforces RBAC — this is just hiding what the user can't use.
// ============================================================

import { clearSession } from "../../lib/auth.js";

const NAV = {
  admin: [
    ["Dashboard", "#/dashboard"],
    ["Users", "#/users"],
    ["Predictions", "#/predictions"],
    ["Documents", "#/documents"],
    ["Audit Log", "#/audit"],
    ["AI Assistant", "#/chat"],
  ],
  expert: [
    ["Dashboard", "#/dashboard"],
    ["Predictions", "#/predictions"],
    ["Audit Log", "#/audit"],
    ["AI Assistant", "#/chat"],
  ],
  end_user: [
    ["Predict", "#/predict"],
    ["My Predictions", "#/predictions"],
    ["AI Assistant", "#/chat"],
  ],
};

// Page hero: every route gets an eyebrow + serif title + one-line
// subtitle so no screen looks "empty". Kept in ONE place (the shell).
const PAGE_META = (role) => ({
  dashboard: ["System", "Dashboard", "Live statistics across predictions, users, documents and models."],
  users: ["Administration", "User management", "Create accounts, control access and search the staff directory."],
  predictions:
    role === "end_user"
      ? ["History", "My predictions", "Every request you've scored with the trained model, with confidence."]
      : ["Review", "Predictions", "Every ML call, its input, verdict, confidence and review status."],
  documents: ["Knowledge base", "Documents & uploads", "Ingest clinical manuals as PDFs — PII-redacted before embedding."],
  audit: ["Accounts", "Audit trail", "The append-only log of every sensitive action in the system."],
  predict: ["Inference", "Predict", "Score a customer profile against the live XGBoost model."],
  chat: ["Assistant", "AI Assistant", "Ask about the uploaded manuals — streamed answers with cited sources."],
});

export default function Layout({ user, onLogout, children }) {
  const handleLogout = () => {
    clearSession();
    onLogout();
    window.location.hash = "#/login";
  };

  const active = (window.location.hash || "#/").replace(/^#\/?/, "") || "dashboard";
  const items = NAV[user.role] || [];
  const meta = (PAGE_META(user.role)[active] || PAGE_META(user.role).dashboard);
  const [eyebrow, title, sub] = meta;

  return (
    <div className="min-h-screen flex flex-col">
      {/* ── Top bar: ink, flat ─────────────────────────────────── */}
      <header className="bg-ink text-paper border-b border-ink">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <a href="#/dashboard" className="flex items-center gap-2.5">
            {/* Brand mark: a tiny "pressure tick" — plus glyph on iodine. */}
            <span className="w-6 h-6 bg-iodine-600 inline-flex items-center justify-center">
              <span className="text-paper text-xs font-semibold leading-none">+</span>
            </span>
            <span className="serif-title text-2xl text-paper leading-none">MediAssist AI</span>
          </a>
          <div className="flex items-center gap-4">
            <span className="text-xs text-iodine-100/80 border border-iodine-100/40 px-2.5 py-1">
              {user.role.replace("_", " ")}
            </span>
            <span className="hidden sm:inline text-sm text-paper/70">{user.username}</span>
            <button
              onClick={handleLogout}
              className="text-sm text-paper/80 hover:text-paper hover:bg-paper/10 px-2 py-1"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      {/* ── Nav: ruling line under the active item ─────────────── */}
      <nav className="bg-white border-b border-hairline">
        <div className="max-w-6xl mx-auto px-2 flex gap-1 overflow-x-auto">
          {items.map(([label, hash]) => {
            const key = hash.replace("#/", "");
            const isActive = active === key;
            return (
              <a
                key={key}
                href={hash}
                className={`px-3 py-2.5 text-sm whitespace-nowrap border-b-2 ${
                  isActive
                    ? "border-iodine-600 text-ink font-medium"
                    : "border-transparent text-muted hover:text-ink"
                }`}
              >
                {label}
              </a>
            );
          })}
        </div>
      </nav>

      {/* ── Active view ─────────────────────────────────────────── */}
      <main className="flex-1 w-full max-w-6xl mx-auto px-4 py-6">
        {/* Page hero — one rule at the top of every screen. */}
        <header className="page-header">
          <p className="page-eyebrow">{eyebrow}</p>
          <h1 className="page-title">{title}</h1>
          <p className="page-sub">{sub}</p>
        </header>
        {children}
      </main>

      {/* ── Footer: the stack, stated plainly ───────────────────── */}
      <footer className="border-t border-hairline">
        <div className="max-w-6xl mx-auto px-4 py-3 flex flex-col sm:flex-row items-center justify-between gap-1 text-xs text-muted">
          <span>MediAssist AI — university project</span>
          <span>FastAPI · React · PostgreSQL · Qdrant · Ollama</span>
        </div>
      </footer>
    </div>
  );
}