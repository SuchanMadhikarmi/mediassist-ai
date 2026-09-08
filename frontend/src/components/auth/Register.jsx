// ============================================================
// src/components/auth/Register.jsx
// Client-side validation for a 4-field form + auto-login on success.
// The register response RETURNS tokens, so the user is logged in the
// moment they sign up — no second step (backend forces role=end_user).
// ============================================================

import { useState } from "react";
import { api } from "../../lib/api.js";
import { saveSession } from "../../lib/auth.js";
import {
  validate,
  validateUsername,
  validateEmail,
  validatePassword,
} from "../../lib/validation.js";
import AuthLayout from "./AuthLayout.jsx";

export default function Register({ onLogin }) {
  const [form, setForm] = useState({ username: "", email: "", password: "", confirm: "" });
  const [errors, setErrors] = useState({});
  const [serverError, setServerError] = useState(null);
  const [busy, setBusy] = useState(false);

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setServerError(null);

    const { errors, valid } = validate(
      form,
      {
        username: validateUsername,
        email: validateEmail,
        password: validatePassword,
        confirm: (v) => (v !== form.password ? "Passwords do not match." : ""),
      }
    );
    setErrors(errors);
    if (!valid) return;

    setBusy(true);
    try {
      const tokens = await api.post("/api/auth/register", {
        username: form.username,
        email: form.email,
        password: form.password,
      });
      saveSession(tokens);
      const me = await api.get("/api/auth/me");
      onLogin(me);
    } catch (err) {
      setServerError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const field = (name, label, type = "text") => (
    <div className="mb-4">
      <label className="field-label" htmlFor={name}>{label}</label>
      <input
        id={name}
        type={type}
        className="input"
        value={form[name]}
        onChange={set(name)}
        autoComplete={name === "confirm" ? "new-password" : "off"}
      />
      {errors[name] && <p className="text-xs text-signal mt-1">{errors[name]}</p>}
    </div>
  );

  return (
    <AuthLayout
      title="Create your account"
      subtitle="Registration always creates a standard user."
      footer={
        <>
          Already have an account?{" "}
          <a href="#/login" className="text-iodine-600 hover:underline">
            Sign in
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
        {field("username", "Username")}
        {field("email", "Email", "email")}
        {field("password", "Password (min 8 chars)", "password")}
        {field("confirm", "Confirm password", "password")}

        <button type="submit" disabled={busy} className="btn-primary w-full">
          {busy ? "Creating…" : "Register"}
        </button>
      </form>
    </AuthLayout>
  );
}