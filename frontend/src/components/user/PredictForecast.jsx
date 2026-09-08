// ============================================================
// src/components/user/PredictForecast.jsx
// The ML input form (16 Bank-Marketing features -> POST /api/predict).
//
// CONCEPT (validation parity):
//   The backend validates ranges + categories in Pydantic. We mirror
//   THE SAME RULES here for instant feedback. Two validators, same
//   contract — the backend is the security gate, the frontend is the
//   UX gate (defense in depth).
//
// CONCEPT (declarative form, zero state-dance):
//   Every field has a fixed spec (label, type, options, validator),
//   and the render loops over that spec once. Adding a field = one line.
// ============================================================

import { useState, useEffect, useRef } from "react";
import { api } from "../../lib/api.js";
import { Card, ErrorBanner, Spinner } from "../shared/ui.jsx";

// ── Field spec: mirrors schemas/prediction.py exactly ─────────────
const RANGES = {
  age: { ge: 18, le: 100 },
  balance: {},
  day: { ge: 1, le: 31 },
  duration: { ge: 0 },
  campaign: { ge: 1 },
  pdays: { ge: -1 },
  previous: { ge: 0 },
};

const OPTIONS = {
  job: ["admin.", "blue-collar", "entrepreneur", "housemaid", "management",
    "retired", "self-employed", "services", "student", "technician",
    "unemployed", "unknown"],
  marital: ["divorced", "married", "single"],
  education: ["primary", "secondary", "tertiary", "unknown"],
  default: ["no", "yes"],
  housing: ["no", "yes"],
  loan: ["no", "yes"],
  contact: ["cellular", "telephone", "unknown"],
  month: ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
  poutcome: ["failure", "other", "success", "unknown"],
};

const NUMERIC = [
  ["age", "Age"], ["balance", "Balance (EUR)"], ["day", "Contact day"],
  ["duration", "Last contact duration (s)"], ["campaign", "Campaign contacts"],
  ["pdays", "Days since last contact"], ["previous", "Previous contacts"],
];

const SELECTS = [
  ["job", "Job"], ["marital", "Marital status"], ["education", "Education"],
  ["default", "Credit in default?"], ["housing", "Housing loan?"],
  ["loan", "Personal loan?"], ["contact", "Contact type"], ["month", "Month"],
  ["poutcome", "Previous outcome"],
];

const DEFAULTS = {
  age: "40", balance: "1200",
  job: "admin.", marital: "married", education: "secondary",
  default: "no", housing: "yes", loan: "no",
  contact: "cellular", day: "15", month: "may", duration: "120",
  campaign: "1", pdays: "-1", previous: "0", poutcome: "unknown",
};

function validateNumeric(field, value) {
  const range = RANGES[field];
  const n = Number(value);
  if (value === "" || Number.isNaN(n)) return "Required number.";
  if (range.ge !== undefined && n < range.ge) return `Minimum ${range.ge}.`;
  if (range.le !== undefined && n > range.le) return `Maximum ${range.le}.`;
  return "";
}

// ── GlideBar: the "smooth probability" visual ──────────────────
// Receives prob_no + prob_yes (0..1). Renders two segments whose widths
// are ALWAYS transitioned via CSS (duration-500 ease-out), and drives the
// displayed widths from state so every change animates:
//   1. FIRST MOUNT: drawn at 0, then a double rAF kicks the width to the
//      real target → the bar visibly "loads in" instead of popping.
//   2. EVERY UPDATE: the element stays mounted (never remounts), so React
//      only changes the inline style → CSS transitions glide  old→new.
// This is the reusable "animated bar" pattern for any live-metric card.
function GlideBar({ no, yes }) {
  const [disp, setDisp] = useState({ no: 0, yes: 0 });
  const mounted = useRef(false);

  useEffect(() => {
    if (!mounted.current) {
      mounted.current = true;
      // First frame: force the browser to PAINT at 0 so the subsequent
      // transition has a real "from" state to animate from.
      const raf = requestAnimationFrame(() =>
        requestAnimationFrame(() => setDisp({ no, yes }))
      );
      return () => cancelAnimationFrame(raf);
    }
    // Subsequent updates glide from the previous displayed width.
    setDisp({ no, yes });
  }, [no, yes]);

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between text-xs text-muted mb-1">
        <span>No — {(disp.no * 100).toFixed(1)}%</span>
        <span>Yes — {(disp.yes * 100).toFixed(1)}%</span>
      </div>
      <div className="flex h-2.5 w-full overflow-hidden border border-hairline relative">
        <div
          className="bg-muted transition-all duration-500 ease-out"
          style={{ width: `${disp.no * 100}%` }}
        />
        <div
          className="bg-iodine transition-all duration-500 ease-out"
          style={{ width: `${disp.yes * 100}%` }}
        />
      </div>
      <p className="text-[11px] text-muted mt-1">
        The model picks the side above 50% — tweak a field and watch the bar
        glide rather than flip.
      </p>
    </div>
  );
}

export default function PredictForecast() {
  const [form, setForm] = useState(DEFAULTS);
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const set = (field) => (e) => setForm({ ...form, [field]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError(null);

    // NOTE: we deliberately do NOT setResult(null) here. Clearing the
    // result would UNMOUNT the <Card> — killing the transition. To make
    // the bar "glide" between predictions, the element must stay mounted
    // and only its width style must change; CSS transitions then animate
    // from the previous width to the new one. (React Diff-alg: same Card,
    // same class, only style differs → balanced update, no remount.)
    const errs = {};
    NUMERIC.forEach(([field]) => {
      const msg = validateNumeric(field, form[field]);
      if (msg) errs[field] = msg;
    });
    setErrors(errs);
    if (Object.keys(errs).length) return;

    setBusy(true);
    try {
      setResult(await api.post("/api/predict", form));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid lg:grid-cols-2 gap-6 items-start">
      <Card title="Bank marketing prediction">
        <p className="text-sm text-muted mb-4">
          Enter a customer profile to predict whether they'll subscribe to a
          term deposit. This calls the real trained XGBoost model.
        </p>

        <ErrorBanner message={error} onDismiss={() => setError(null)} />

        <form onSubmit={submit} noValidate>
          <div className="grid grid-cols-2 gap-3">
            {NUMERIC.map(([field, label]) => (
              <div key={field} className="mb-2">
                <label className="field-label" htmlFor={field}>{label}</label>
                <input
                  id={field}
                  type="number"
                  step="any"
                  className="input"
                  value={form[field]}
                  onChange={set(field)}
                />
                {errors[field] && (
                  <p className="text-xs text-signal mt-1">{errors[field]}</p>
                )}
              </div>
            ))}

            {SELECTS.map(([field, label]) => (
              <div key={field} className="mb-2">
                <label className="field-label" htmlFor={field}>{label}</label>
                <select id={field} className="input" value={form[field]} onChange={set(field)}>
                  {OPTIONS[field].map((opt) => (
                    <option key={opt} value={opt}>{opt}</option>
                  ))}
                </select>
              </div>
            ))}
          </div>

          <button type="submit" disabled={busy} className="btn-primary w-full mt-4">
            {busy ? "Running model…" : "Predict"}
          </button>
        </form>
      </Card>

      <div className="space-y-4">
        {busy && <Card><Spinner label="Loading model + predicting…" /></Card>}

        {result && (
          <Card title="Result">
            <div className="flex items-center justify-between gap-3 mb-3">
              <span
                className={`text-sm font-semibold border px-4 py-1.5 ${
                  result.prediction === "yes"
                    ? "bg-green-50 border-green-600 text-green-700"
                    : "bg-white border-signal text-signal"
                }`}
              >
                {result.prediction === "yes" ? "Will subscribe" : "Won't subscribe"}
              </span>
              <span className="text-sm text-muted">
                Confidence: <strong className="text-ink">{(result.confidence * 100).toFixed(1)}%</strong>
              </span>
            </div>

            {/* Probability bars — the honest view of the same verdict.
                The label (argmax) can snap when you tweak a field near the
                50% boundary; these two bars always move smoothly, so the
                model never looks random. P(no) + P(yes) = 1. */}
            <GlideBar no={result.prob_no} yes={result.prob_yes} />

            <dl className="text-sm text-muted grid grid-cols-2 gap-y-1">
              <dt>Model</dt><dd className="font-medium text-ink">{result.model_name}</dd>
              <dt>Version</dt><dd className="font-medium text-ink">{result.model_version}</dd>
              <dt>Inference time</dt><dd className="font-medium text-ink">{result.inference_time_ms} ms</dd>
              <dt>Logged as</dt><dd className="font-medium text-ink">#{result.prediction_id.slice(0, 8)}</dd>
            </dl>
            <p className="mt-4 text-xs text-muted">
              Disclaimer: ML prediction for demonstration only — not medical or
              financial advice.
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}