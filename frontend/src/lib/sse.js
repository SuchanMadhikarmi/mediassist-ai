// ============================================================
// src/lib/sse.js — consume POST-based Server-Sent Events.
//
// WHY NOT EventSource? The browser's EventSource() helper only supports
// GET. Our /chat/stream endpoint REQUIRES POST (it carries a JSON body
// + JWT). So we stream with fetch + ReadableStream and parse the SSE
// framing ourselves. This is also what you must do for any POST-stream
// (OpenAI-compatible APIs, etc.) — a broadly reusable pattern.
//
// The wire format (from backend llmops.streaming.sse_frame):
//     data: {"kind":"token","text":"Hello"}\n\n
//     data: {"kind":"sources","sources":[...]}\n\n
//     data: {"kind":"done"}\n\n
// Each event is `data: <json>` followed by a blank line. We buffer raw
// bytes, split on the blank line, and dispatch each parsed JSON payload
// to the onEvent callback.
//
// THE LESSON (async streaming in the browser):
// `res.body` is a ReadableStream of BYTES, arriving in arbitrary chunk
// sizes (a token can arrive split across two chunks, or several tokens
// in one chunk). So we must keep a `buffer` string across reads and
// extract complete events. TextDecoder handles multi-byte UTF-8 that
// also got split across chunks.
// ============================================================

import { getToken, clearSession } from "./auth.js";

async function readBodyAsJson(res) {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

export async function streamChat(message, onEvent) {
  const res = await fetch("/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify({ message }),
  });

  // HITL refusal arrives as a normal JSON body BEFORE the stream opens —
  // the backend raises 409 before sending headers. Carry the approval
  // payload on the error so the UI can render "needs approval".
  if (res.status === 409) {
    const data = await readBodyAsJson(res);
    const err = new Error(data?.detail?.message || "This action needs approval.");
    err.status = 409;
    err.hitl = data?.detail; // {status, thread_id, action}
    throw err;
  }
  if (res.status === 401) {
    clearSession();
    window.location.hash = "#/login";
    throw new Error("Session expired — please log in again.");
  }
  if (!res.ok) {
    const data = await readBodyAsJson(res);
    throw new Error(
      (typeof data?.detail === "string" && data.detail) || `Stream failed (${res.status})`
    );
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    // Decode this chunk of bytes (stream:true = don't force-finalize
    // partial multi-byte sequences yet).
    buffer += decoder.decode(value, { stream: true });

    // Extract every COMPLETE event from the buffer. \n\n is the event
    // delimiter the backend writes. Leftover partial bytes stay in the
    // buffer for the next chunk.
    let sep;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const line = raw.trim();
      if (!line.startsWith("data:")) continue;

      // "data: {json}" -> parse everything after the prefix.
      const payload = JSON.parse(line.slice(5).trim());
      onEvent(payload);
    }
  }

  // The stream ended with no final event as a "done" sentinel
  // (backend closes cleanly) — caller decides what to do on close.
}