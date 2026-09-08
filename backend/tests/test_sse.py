# ============================================================
# backend/tests/test_sse.py
# Deterministic tests for the SSE wire format (Phase 7, Step 2).
#
# WHY: the frontend's ChatWindow depends on the exact `data: {...}\n\n`
# framing we emit. A silent format change (extra blank line, missing
# blank line, non-JSON payload) would break live token streaming with NO
# Python-side error. These tests lock the contract.
# ============================================================

import json

from llmops.streaming import sse_frame


class TestSseFrame:
    def test_emits_data_prefix_and_trailing_blank_line(self):
        frame = sse_frame({"kind": "started"})
        assert frame.startswith("data: ")
        assert frame.endswith("\n\n")  # blank line = end of event (client parser requirement)

    def test_embeds_valid_json(self):
        payload = {"kind": "done", "cached": True}
        frame = sse_frame(payload)
        # The JSON payload is the part after "data: " and before "\n\n"
        data_part = frame[len("data: "):].rstrip("\n")
        assert json.loads(data_part) == payload

    def test_token_frames_round_trip(self):
        # A realistic token frame used by /chat/stream
        frame = sse_frame({"kind": "token", "content": "hello"})
        data_part = frame[len("data: "):].rstrip("\n")
        assert json.loads(data_part)["content"] == "hello"

    def test_client_parser_compat_four_frame_burst(self):
        # Emulate what streamChat() sees: 4 events back-to-back, each
        # separated by the required blank line.
        raw = "".join(
            sse_frame(k) for k in [{"kind": "started"}, {"kind": "token", "content": "a"},
                                   {"kind": "done"}, {"kind": "error", "detail": "x"}]
        )
        events = [ln for ln in raw.split("\n") if ln.startswith("data: ")]
        assert len(events) == 4
        assert json.loads(events[0][len("data: "):])["kind"] == "started"
        assert json.loads(events[-1][len("data: "):])["kind"] == "error"