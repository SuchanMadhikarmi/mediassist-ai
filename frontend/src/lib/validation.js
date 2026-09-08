// ============================================================
// src/lib/validation.js — client-side validation helpers.
//
// CONCEPT: why validate in the browser AT ALL when the API re-checks?
//   1. UX: instant feedback, no round-trip to the server.
//   2. Cost: the backend only ever sees well-formed requests.
//   BUT this is UX, not security — the API is the real gate. The
//   frontend never trusts the backend, and vice versa. (Defense in
//   depth: both sides validate.)
//
// Every validator returns "" (OK) or a human-readable error string.
// ============================================================

export function validateUsername(value) {
  if (!value) return "Username is required.";
  if (value.length < 3 || value.length > 50)
    return "Username must be 3–50 characters.";
  return "";
}

export function validatePassword(value) {
  if (!value) return "Password is required.";
  if (value.length < 8) return "Password must be at least 8 characters.";
  if (value.length > 128) return "Password must be at most 128 characters.";
  return "";
}

// A very small, honest email check (the backend's EmailStr is stricter).
export function validateEmail(value) {
  if (!value) return "Email is required.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value))
    return "Enter a valid email address.";
  return "";
}

// Generic builder: run all validators, produce {field: error} map.
// Returns true when the whole form is valid.
export function validate(obj, validators) {
  const errors = {};
  for (const [field, value] of Object.entries(obj)) {
    const fn = validators[field];
    if (fn) errors[field] = fn(value);
  }
  return {
    errors,
    valid: Object.values(errors).every((e) => !e),
  };
}