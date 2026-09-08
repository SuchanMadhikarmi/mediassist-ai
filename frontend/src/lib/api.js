// ============================================================
// src/lib/api.js — the SINGLE door to the backend.
//
// Why one wrapper for every request?
//   1. JWT: every call needs `Authorization: Bearer <token>`. Put it
//      here once, not in 15 components.
//   2. Errors: HTTP error -> thrown Error with the backend's `detail`
//      message, so every component handles errors identically.
//   3. 401: an expired/absent token means "re-login". Centralizing the
//      redirect here means no component ever forgets to handle it.
// This is the "API client" pattern from every production frontend.
// ============================================================

import { getToken, clearSession } from "./auth.js";

async function request(path, { method = "GET", body, isForm = false } = {}) {
  const headers = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body && !isForm) headers["Content-Type"] = "application/json";

  const res = await fetch(path, {
    method,
    headers,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });

  // 401 = token missing/invalid/expired -> always a fresh login.
  if (res.status === 401) {
    clearSession();
    window.location.hash = "#/login";
    throw new Error("Session expired — please log in again.");
  }

  // No body (e.g. 204 on delete) -> nothing to parse.
  if (res.status === 204) return null;

  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null; // non-JSON body — leave as null
  }

  if (!res.ok) {
    // FastAPI puts the human-readable reason in `detail`.
    const message =
      data?.detail && typeof data.detail === "string"
        ? data.detail
        : data?.detail?.message || `Request failed (${res.status})`;
    const err = new Error(message);
    err.status = res.status;
    err.detail = data?.detail;
    throw err;
  }
  return data;
}

export const api = {
  get: (path) => request(path),
  post: (path, body) => request(path, { method: "POST", body }),
  put: (path, body) => request(path, { method: "PUT", body }),
  delete: (path) => request(path, { method: "DELETE" }),

  // Multipart upload — fetch sets the multipart boundary itself when we
  // pass a FormData object (Content-Type header must NOT be set manually).
  upload: (path, formData) =>
    request(path, { method: "POST", body: formData, isForm: true }),
};