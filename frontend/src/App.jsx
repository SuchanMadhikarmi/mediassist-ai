// ============================================================
// src/App.jsx — the app's "brain".
//
// CONCEPT (lift state up):
//   `user` (who is logged in) is needed by MANY components — the nav,
//   every view, the router. So it lives HERE (the top), and is passed
//   DOWN as props. This is "lifting state up": siblings can't share
//   state, so the common ancestor holds it.
//
// CONCEPT (effect = side effects live outside render):
//   Two effects:
//    1. on mount — if we have a saved token, ask /api/auth/me who we are
//       (restores the session across browser refreshes).
//    2. hash routing — listen for changes to `location.hash` and swap
//       the visible view. Simple & dependency-free (no react-router).
//
// CONCEPT (controlled component):
//   `route` is state + HTML drives it via <a href="#/x">. One-direction
//   flow: hash change -> state update -> re-render.
// ============================================================

import { useEffect, useState } from "react";
import { api } from "./lib/api.js";
import { isLoggedIn, clearSession } from "./lib/auth.js";

import Layout from "./components/layout/Layout.jsx";
import Login from "./components/auth/Login.jsx";
import Register from "./components/auth/Register.jsx";
import AdminDashboard from "./components/admin/AdminDashboard.jsx";
import PredictForecast from "./components/user/PredictForecast.jsx";
import PredictionsTable from "./components/prediction/PredictionsTable.jsx";
import UsersPane from "./components/admin/UsersPane.jsx";
import DocsPane from "./components/admin/DocsPane.jsx";
import AuditPane from "./components/admin/AuditPane.jsx";
import ChatWindow from "./components/chat/ChatWindow.jsx";

// Role -> { route: component }. This single map IS the RBAC routing:
// a route a role doesn't own simply doesn't exist for them.
const VIEWS = {
  admin: {
    dashboard: AdminDashboard,
    users: UsersPane,
    predictions: (p) => <PredictionsTable user={p.user} canReview />,
    documents: DocsPane,
    audit: AuditPane,
    chat: ChatWindow,
  },
  expert: {
    dashboard: AdminDashboard,
    predictions: (p) => <PredictionsTable user={p.user} canReview />,
    audit: AuditPane,
    chat: ChatWindow,
  },
  end_user: {
    predict: PredictForecast,
    predictions: (p) => <PredictionsTable user={p.user} canReview={false} />,
    chat: ChatWindow,
  },
};

const DEFAULT_ROUTE = { admin: "dashboard", expert: "dashboard", end_user: "predict" };

function currentHash() {
  return (window.location.hash || "#/").replace(/^#\/?/, "") || "login";
}

export default function App() {
  const [user, setUser] = useState(null);
  const [booted, setBooted] = useState(false); // false while restoring session
  const [route, setRoute] = useState(currentHash());

  // ── Restore session from a saved token on load ─────────────────
  useEffect(() => {
    if (!isLoggedIn()) {
      setBooted(true);
      return;
    }
    api
      .get("/api/auth/me")
      .then(setUser)
      .catch(() => {
        clearSession();
        setUser(null);
      })
      .finally(() => setBooted(true));
  }, []);

  // ── Hash router ────────────────────────────────────────────────
  useEffect(() => {
    const onHash = () => setRoute(currentHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // ── After login, drop the stale "#/login" hash ────────────────
  // Login/Register never touch the URL (they only call onLogin -> setUser),
  // so the hash would stay "#/login" even though the dashboard is shown.
  // Jump to the role's default route so the hero meta + nav highlight match.
  useEffect(() => {
    if (!user) return;
    const table = VIEWS[user.role];
    if (!table?.[currentHash()]) {
      window.location.hash = `#/${DEFAULT_ROUTE[user.role] || "chat"}`;
    }
  }, [user]);

  if (!booted) return <div className="p-8 text-center text-slate-500">Loading…</div>;

  // ── Not logged in → auth screens ───────────────────────────────
  if (!user) {
    return route === "register" ? (
      <Register onLogin={setUser} />
    ) : (
      <Login onLogin={setUser} />
    );
  }

  // ── Logged in → role-based routing ─────────────────────────────
  const table = VIEWS[user.role];
  const goDefault = DEFAULT_ROUTE[user.role] || "chat";
  const View = table?.[route] ? table[route] : table[goDefault];

  return (
    <Layout user={user} onLogout={() => setUser(null)}>
      <View user={user} />
    </Layout>
  );
}