// ============================================================
// src/components/admin/UsersPane.jsx — admin user management.
// CRUD on users: list (search + paginate), create, deactivate.
// The ONLY screen with full user control — the nav hides it from all
// non-admin roles, and the backend's require_admin enforces it anyway.
// ============================================================

import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api.js";
import { Card, ErrorBanner, EmptyState, Pagination, Spinner } from "../shared/ui.jsx";

const PER_PAGE = 8;

export default function UsersPane() {
  const [rows, setRows] = useState(null);
  const [page, setPage] = useState(1);
  const [pages, setPages] = useState(0);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [error, setError] = useState(null);

  // Create-user form state (client-side validated).
  const [form, setForm] = useState({ username: "", email: "", password: "", role: "end_user" });
  const [formErrors, setFormErrors] = useState({});
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const qs = new URLSearchParams({ page, per_page: PER_PAGE });
      if (submitted) qs.set("search", submitted);
      const data = await api.get(`/api/users?${qs.toString()}`);
      setRows(data.items);
      setPages(data.pages);
      setTotal(data.total);
    } catch (err) {
      setError(err.message);
    }
  }, [page, submitted]);

  useEffect(() => { load(); }, [load]);

  const submitSearch = (e) => {
    e.preventDefault();
    setPage(1);
    setSubmitted(search.trim());
  };

  const setField = (f) => (e) => setForm({ ...form, [f]: e.target.value });

  const createUser = async (e) => {
    e.preventDefault();
    const errs = {};
    if (form.username.length < 3) errs.username = "Min 3 characters.";
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errs.email = "Invalid email.";
    if (form.password.length < 8) errs.password = "Min 8 characters.";
    setFormErrors(errs);
    if (Object.keys(errs).length) return;

    setCreating(true);
    try {
      await api.post("/api/users", form);
      setForm({ username: "", email: "", password: "", role: "end_user" });
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  const toggleActive = async (u) => {
    try {
      await api.put(`/api/users/${u.id}`, { is_active: !u.is_active });
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="grid lg:grid-cols-3 gap-6 items-start">
      <Card title="Users" className="lg:col-span-2">
        <form onSubmit={submitSearch} className="flex gap-2 mb-4">
          <input
            className="input"
            placeholder="Search username, email or role"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button className="btn-primary !py-2" type="submit">Search</button>
        </form>

        <ErrorBanner message={error} onDismiss={() => setError(null)} />

        {!rows ? (
          <Spinner />
        ) : rows.length === 0 ? (
          <EmptyState text="No users match." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="thead">
                  <th>Username</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody className="tbody">
                {rows.map((u) => (
                  <tr key={u.id} className="border-b border-hairline">
                    <td className="py-2 pr-3 font-medium text-ink">{u.username}</td>
                    <td className="py-2 pr-3 text-muted wrap-anywhere">{u.email}</td>
                    <td className="py-2 pr-3">
                      <span className="text-xs border border-iodine-600 bg-iodine-50 text-iodine-700 px-2 py-0.5">
                        {u.role.replace("_", " ")}
                      </span>
                    </td>
                    <td className="py-2 pr-3">
                      <span className={`text-xs ${u.is_active ? "text-green-700" : "text-muted"}`}>
                        {u.is_active ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td className="py-2">
                      <button
                        className="btn-ghost"
                        onClick={() => toggleActive(u)}
                        disabled={u.username === "admin"}
                      >
                        {u.is_active ? "Deactivate" : "Activate"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <Pagination page={page} pages={pages} total={total} onChange={setPage} />
      </Card>

      <Card title="Create user">
        <form onSubmit={createUser} noValidate>
          <div className="mb-3">
            <label className="field-label">Username</label>
            <input className="input" value={form.username} onChange={setField("username")} />
            {formErrors.username && (
              <p className="text-xs text-signal mt-1">{formErrors.username}</p>
            )}
          </div>
          <div className="mb-3">
            <label className="field-label">Email</label>
            <input className="input" type="email" value={form.email} onChange={setField("email")} />
            {formErrors.email && (
              <p className="text-xs text-signal mt-1">{formErrors.email}</p>
            )}
          </div>
          <div className="mb-3">
            <label className="field-label">Password</label>
            <input
              className="input"
              type="password"
              value={form.password}
              onChange={setField("password")}
            />
            {formErrors.password && (
              <p className="text-xs text-signal mt-1">{formErrors.password}</p>
            )}
          </div>
          <div className="mb-4">
            <label className="field-label">Role</label>
            <select className="input" value={form.role} onChange={setField("role")}>
              <option value="end_user">end_user</option>
              <option value="expert">expert</option>
              <option value="admin">admin</option>
            </select>
          </div>
          <button type="submit" disabled={creating} className="btn-primary w-full">
            {creating ? "Creating…" : "Create user"}
          </button>
        </form>
      </Card>
    </div>
  );
}