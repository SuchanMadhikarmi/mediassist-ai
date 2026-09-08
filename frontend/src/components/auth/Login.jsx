// ============================================================
// src/components/auth/Login.jsx
// The student lesson here: CONTROLLED FORM + async submit.
//
// CONCEPT (controlled inputs):
//   input value comes from state, and typing only updates that state
//   (onChange -> setUsername). React owns the field, not the DOM.
//   This makes client-side validation trivial (we read state, not DOM).
//
// CONCEPT (async + loading):
//   submitting sets `busy=true` (disables button, shows spinner).
//   On success -> save tokens -> fetch the user profile -> lift it up
//   via onLogin. On failure -> show the backend's message in a banner.
// ============================================================

import { useState } from "react";
import { api } from "../../lib/api.js";
import { saveSession } from "../../lib/auth.js";
import { validate, validateUsername, validatePassword } from "../../lib/validation.js";
import AuthLayout from "./AuthLayout.jsx";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setServerError(null);

    // Client-side validation BEFORE any network call.
    const { errors, valid } = validate(
      { username, password },
      { username: validateUsername, password: validatePassword }
    );
    setErrors(errors);
    if (!valid) return;

    setBusy(true);
    try {
      const tokens = await api.post("/api/auth/login", { username, password });
      saveSession(tokens);
      // Login returns tokens but NOT the full profile → fetch the user.
      const me = await api.get("/api/auth/me");
      onLogin(me); // lift state up to App: user -> role routing
    } catch (err) {
      setServerError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Enter your credentials to continue"
      footer={
        <>
          No account?{" "}
          <a href="#/register" className="text-iodine-600 hover:underline">
            Register
          </a>
        </>
      }
    >
      {serverError && (
        <div className="mb-4 text-sm text-signal bg-white border border-hairline border-l-4 border-l-signal px-3 py-2 wrap-anywhere">
          {serverError}
        </div>
      )}

      <form onSubmit={submit} noValidate className="border border-hairline bg-panel p-6">
        {/* `noValidate` opts OUT of native browser bubbles — we show
            our own consistent validation messages instead. */}
        <div className="mb-4">
          <label className="field-label" htmlFor="username">Username</label>
          <input
            id="username"
            className="input"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
          {errors.username && <p className="text-xs text-signal mt-1">{errors.username}</p>}
        </div>

        <div className="mb-6">
          <label className="field-label" htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            className="input"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
          {errors.password && <p className="text-xs text-signal mt-1">{errors.password}</p>}
        </div>

        <button type="submit" disabled={busy} className="btn-primary w-full">
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </AuthLayout>
  );
}