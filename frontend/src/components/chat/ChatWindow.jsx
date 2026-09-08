// ============================================================
// src/components/chat/ChatWindow.jsx
// Streaming AI assistant — THE Phase 8 showcase feature.
//
// Three things happen on every send (revisit the sse.js lesson):
//   1. fetch POST /chat/stream with the JWT   (EventSource can't POST)
//   2. bytes arrive in arbitrary chunks         -> buffer + split "\n\n"
//   3. each `data: {kind, ...}` event drives ONE state update, and the
//      token stream visibly paints on screen, word by word.
//
// CONCEPT (event kinds -> state):
//   started    -> nothing visible (the stream opens)
//   token      -> append text to the current assistant message
//   answer     -> cache HIT: full answer + sources arrive as one block
//   sources    -> the citations arrive (after the last token)
//   done       -> mark the message complete
//   HITL 409   -> NOT an event — it's thrown by the fetch, carrying an
//                 action summary. The UI shows an approval card.
//
// CONCEPT (functional setState):
//   patchLast(fn) mutates ONLY the newest assistant message. Using the
//   setter's functional form (setMessages(prev => ...)) protects against
//   race conditions when the streamed tokens arrive asynchronously.
// ============================================================

import { useEffect, useRef, useState } from "react";
import { streamChat } from "../../lib/sse.js";
import { api } from "../../lib/api.js";
import { getRole } from "../../lib/auth.js";
import { Card, ErrorBanner } from "../shared/ui.jsx";

let msgId = 0;

export default function ChatWindow({ user }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [pending, setPending] = useState(null); // HITL approval card
  const bottomRef = useRef(null);

  // Auto-scroll to the newest content as tokens arrive.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Functional setter: mutate ONLY the most recent assistant message.
  const patchLast = (fn) =>
    setMessages((prev) => {
      const copy = [...prev];
      copy[copy.length - 1] = fn(copy[copy.length - 1]);
      return copy;
    });

  const send = async (e) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;

    setError(null);
    setPending(null);
    setInput("");
    // Optimistic append: user + empty assistant message we then fill.
    setMessages((m) => [
      ...m,
      { id: msgId++, role: "user", text },
      { id: msgId++, role: "assistant", text: "", sources: [], streaming: true },
    ]);
    setBusy(true);

    try {
      await streamChat(text, (evt) => {
        if (evt.kind === "token") {
          patchLast((m) => ({ ...m, text: m.text + evt.text }));
        } else if (evt.kind === "answer") {
          // Cache hit: the whole answer + citations in ONE event.
          patchLast((m) => ({ ...m, text: evt.answer, sources: evt.sources || [], streaming: false }));
        } else if (evt.kind === "sources") {
          patchLast((m) => ({ ...m, sources: evt.sources || [], streaming: false }));
        } else if (evt.kind === "done") {
          patchLast((m) => ({ ...m, streaming: false }));
        }
      });
    } catch (err) {
      if (err.status === 409) {
        // Dangerous action -> pause for human approval.
        patchLast((m) => ({ ...m, streaming: false }));
        setPending(err.hitl);
      } else {
        patchLast((m) => ({ ...m, text: m.text || "(stream failed)", streaming: false }));
        setError(err.message);
      }
    } finally {
      setBusy(false);
    }
  };

  // Approve / reject a HITL-paused action. Only admin/expert passes the
  // backend gate — end_users get 403 here, exactly as designed.
  const decide = async (approve) => {
    try {
      const r = await api.post("/chat/resume", {
        thread_id: pending.thread_id,
        approve,
      });
      patchLast((m) => ({ ...m, text: r.answer, sources: [], streaming: false }));
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(null);
    }
  };

  return (
    <Card title="AI Assistant">
      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      {/* ── Message thread ─────────────────────────────────────── */}
      <div className="space-y-4 max-h-[55vh] overflow-y-auto pr-1 mb-4">
        {messages.length === 0 && (
          <p className="text-sm text-muted text-center py-8">
            Ask a question about the uploaded manuals — answers stream in live
            with citations.
          </p>
        )}

        {messages.map((m) => (
          <div key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div
              className={`max-w-[85%] px-4 py-2.5 text-sm border whitespace-pre-wrap break-words min-w-0 ${
                m.role === "user"
                  ? "bg-ink text-paper border-ink"
                  : "bg-panel text-ink border-hairline"
              }`}
            >
              {m.text || (m.streaming ? "…" : "")}

              {/* Streamed answer -> show citations below it */}
              {m.role === "assistant" && m.sources?.length > 0 && (
                <div className="mt-3 border-t border-hairline pt-2 space-y-2">
                  {m.sources.map((s, i) => (
                    <div key={i} className="text-xs">
                      <p className="text-muted font-medium mb-0.5 wrap-anywhere">
                        Source: {s.source || "unknown"}
                        {s.page ? ` (p.${s.page})` : ""} — score{" "}
                        {s.rerank_score?.toFixed?.(3) ?? s.rerank_score}
                      </p>
                      <p className="text-muted italic bg-white border border-hairline p-2 wrap-anywhere">
                        “{s.text}”
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* ── HITL approval card ─────────────────────────────────── */}
      {pending && (
        <div className="mb-4 border border-hairline border-l-4 border-l-signal bg-panel p-4">
          <p className="text-sm font-medium text-signal mb-1">
            This action requires human approval
          </p>
          <p className="text-sm text-ink mb-3 wrap-anywhere">{pending.action}</p>
          <div className="flex gap-2">
            <button
              className="btn-primary !bg-signal !border-signal"
              disabled={user.role === "end_user"}
              title={user.role === "end_user" ? "Only admin/expert can approve" : ""}
              onClick={() => decide(true)}
            >
              Approve
            </button>
            <button
              className="btn-ghost border border-hairline"
              disabled={user.role === "end_user"}
              onClick={() => decide(false)}
            >
              Reject
            </button>
          </div>
          {user.role === "end_user" && (
            <p className="text-xs text-muted mt-2">
              An admin or expert must approve this request.
            </p>
          )}
        </div>
      )}

      {/* ── Composer ───────────────────────────────────────────── */}
      <form onSubmit={send} className="flex gap-2">
        <input
          className="input"
          placeholder="e.g. What does error 4012 mean?"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={busy}
        />
        <button type="submit" disabled={busy || !input.trim()} className="btn-primary">
          {busy ? "…" : "Send"}
        </button>
      </form>
      <p className="mt-2 text-xs text-muted">
        {getRole() === "end_user"
          ? "Admin/expert approval may be required for sensitive actions."
          : "You can approve or reject sensitive actions in this session."}
      </p>
    </Card>
  );
}