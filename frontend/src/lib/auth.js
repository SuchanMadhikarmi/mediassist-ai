// ============================================================
// src/lib/auth.js — session management (the token's home).
//
// CONCEPT: where should the JWT live?
//   localStorage  : survives browser restarts, readable by JS (needed!).
//   sessionStorage: cleared when the tab closes.
// We use localStorage so a refresh doesn't log the user out. The
// trade-off (XSS could read it) is accepted here because the whole app
// ships via one trusted origin; production may tighten this further
// (httpOnly cookies via SameSite).
//
// All access goes through these helpers — components never touch the
// raw localStorage key, so we could swap the storage mechanism later
// without touching UI code.
// ============================================================

const ACCESS_KEY = "medassist_access";
const REFRESH_KEY = "medassist_refresh";
const ROLE_KEY = "medassist_role";

export function saveSession({ access_token, refresh_token, role }) {
  localStorage.setItem(ACCESS_KEY, access_token);
  localStorage.setItem(REFRESH_KEY, refresh_token);
  localStorage.setItem(ROLE_KEY, role);
}

export function getToken() {
  return localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_KEY);
}

export function getRole() {
  return localStorage.getItem(ROLE_KEY);
}

export function isLoggedIn() {
  return Boolean(getToken());
}

export function clearSession() {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(ROLE_KEY);
}