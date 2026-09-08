# ============================================================
# backend/eval/run_eval.py
# Runs the GOLDEN SET against the LIVE stack (Phase 9 — the "CD"
# half of CI/CD: the quality report you read before trusting the AI).
#
# WHY A LIVE-STACK EVAL (the concept we are teaching):
#   - pytest (backend/tests/) proves PURE LOGIC is correct, headless.
#   - This runner proves the FULL PIPELINE behaves end-to-end: real
#     Ollama answers, real RAG retrieval from Qdrant, real HITL pause
#     and resume, real semantic cache. It drives the *same* HTTP API the
#     frontend uses — so it tests exactly what a user experiences.
#
# HOW IT WORKS:
#   1. Logs in as admin (JWT) — the suite cheats; CI would use a token.
#   2. Plays each golden case (data/eval_golden.json) in order against
#      POST /chat (+ /chat/resume for the HITL cases).
#   3. Scores each response against the case's `expect` criteria.
#   4. Grades the flagship RAG case with an LLM-as-judge (best effort).
#   5. Prints a report and writes data/eval_report.json.
#
# EXIT CODE: 0 if every HARD case passed and the judge threshold was met
# (when a judge score exists); 1 otherwise. Soft cases never fail the run.
#
# Usage (from backend/, stack running):
#   .venv/bin/python -m eval.run_eval
# Flags: --base-url, --username, --password, --threshold, --no-judge
# ============================================================

import argparse
import asyncio
import json
import time
import urllib.parse
from pathlib import Path

import httpx

from eval.judge import grade_answer

HERE = Path(__file__).resolve().parent
GOLDEN_PATH = HERE.parent / "data" / "eval_golden.json"
REPORT_PATH = HERE.parent / "data" / "eval_report.json"

FALLBACK_SIGNAL = "could not find relevant information"


def _is_fallback(answer: str) -> bool:
    return FALLBACK_SIGNAL in (answer or "").lower()


def _load_golden() -> list[dict]:
    return json.loads(GOLDEN_PATH.read_text())


async def login(base: str, username: str, password: str) -> str:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{base}/api/auth/login", json={"username": username, "password": password})
        r.raise_for_status()
        return r.json()["access_token"]


async def post_chat(client: httpx.AsyncClient, base: str, headers: dict, question: str) -> tuple[int, dict]:
    r = await client.post(f"{base}/chat", json={"message": question}, headers=headers)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {"raw": r.text}


async def post_resume(client: httpx.AsyncClient, base: str, headers: dict, thread_id: str, approve: bool) -> tuple[int, dict]:
    r = await client.post(
        f"{base}/chat/resume",
        json={"thread_id": thread_id, "approve": approve},
        headers=headers,
    )
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {"raw": r.text}


# ─────────────────────────────────────────────────────────────
# Scoring: each golden case becomes one evaluation record
# ─────────────────────────────────────────────────────────────
def _score_case(case: dict, status_code: int, data: dict) -> tuple[str, list[str]]:
    """Return (status, reasons). status ∈ PASS | WARN | FAIL.

    Hard cases: any unmet criterion → FAIL.
    Soft cases: unmet criteria → WARN (recorded, never fails the run).
    """
    expect = case.get("expect", {})
    kind = case.get("kind")
    hard = not case.get("soft", False)
    problems: list[str] = []
    notes: list[str] = []

    answer = data.get("answer", "")

    for criterion in ("not_fallback", "answers_anything"):
        if expect.get(criterion):
            if _is_fallback(answer):
                problems.append("expected a real answer, got the fallback")

    if expect.get("fallback_phrase"):
        phrase = expect["fallback_phrase"]
        if phrase not in answer:
            problems.append(f"expected fallback phrase {phrase!r}")
    if expect.get("not_cached"):
        if data.get("cached"):
            problems.append("expected a fresh (uncached) answer")

    if expect.get("cached"):
        if not data.get("cached"):
            problems.append("expected cache hit (cached=true)")

    if expect.get("answer_contains"):
        for needle in expect["answer_contains"]:
            lower = f"{answer} {' '.join(s.get('text', '') for s in data.get('sources', []))}".lower()
            if needle.lower() not in lower:
                problems.append(f"answer/sources missing {needle!r}")

    if expect.get("sources_required") and not data.get("sources"):
        problems.append("expected citations (sources)")

    # The ERP-tool case: note whether the tool actually fired vs fell back.
    if kind == "tool":
        fired = ("ORD-" in answer) and not _is_fallback(answer)
        notes.append("tool path exercised" if fired else "tool path NOT exercised (fell to fallback)")
        if expect.get("tool") and not fired:
            problems.append("expected the ERP tool path, got a fallback answer")

    if problems:
        status = "WARN" if not hard else "FAIL"
    else:
        status = "PASS"
    return status, problems + notes


# ─────────────────────────────────────────────────────────────
# Main run
# ─────────────────────────────────────────────────────────────
async def main() -> int:
    parser = argparse.ArgumentParser(description="Run the MediAssist golden-set eval against the live stack.")
    parser.add_argument("--base-url", default="http://localhost:8000", help="FastAPI base URL")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    parser.add_argument("--threshold", type=float, default=1.0, help="min PASS fraction of HARD cases to exit 0")
    parser.add_argument("--no-judge", action="store_true", help="skip the LLM-as-judge quality pass")
    args = parser.parse_args()

    golden = _load_golden()
    print(f"eval: {len(golden)} golden cases  →  {args.base_url}")
    print("-" * 74)

    try:
        token = await login(args.base_url, args.username, args.password)
    except Exception as e:
        print(f"❌ eval ABORTED — could not authenticate: {e}")
        print("   Is uvicorn running on the base URL? (Phase 9 evals need the LIVE stack.)")
        return 1

    headers = {"Authorization": f"Bearer {token}"}
    records: list[dict] = []

    async with httpx.AsyncClient(timeout=120) as client:
        for case in golden:
            case_id = case["id"]
            started = time.perf_counter()
            status, reasons = "FAIL", ["unhandled"]
            answer_snippet, sources_n = "", 0

            try:
                if case.get("kind") == "hitl":
                    sc, data = await post_chat(client, args.base_url, headers, case["question"])
                    # The gate MUST pause with a 409 so the frontend can ask a human.
                    needs_approval = (sc == 409 and data.get("detail", {}).get("status") == "needs_approval")
                    problems = []
                    if case["expect"].get("needs_approval") and not needs_approval:
                        problems.append(f"expected HTTP 409 needs_approval, got {sc}")

                    if needs_approval:
                        thread_id = data["detail"]["thread_id"]
                        resume = case["expect"].get("then", "reject")
                        rsc, rdata = await post_resume(
                            client, args.base_url, headers, thread_id, approve=(resume == "approve")
                        )
                        expect_status = case["expect"].get("resume_status")
                        if rsc != 200 or rdata.get("status") != expect_status:
                            problems.append(f"resume expected status={expect_status} (200 body), got {rsc}/{rdata.get('status')}")
                        if resume == "reject":
                            answer = rdata.get("answer", "")
                            if "not approved" not in answer and "not approve" not in answer:
                                problems.append("rejected path should contain a refusal message")
                            answer_snippet = answer[:110]
                        else:
                            answer_snippet = f"{rdata.get('status')} (graph resumed)"
                        sources_n = 0
                    else:
                        answer_snippet = str(data)[:110]

                    status = "PASS" if not problems else "FAIL"
                    reasons = problems
                else:
                    sc, data = await post_chat(client, args.base_url, headers, case["question"])
                    if sc != 200:
                        status, reasons = "FAIL", [f"HTTP {sc}: {str(data)[:140]}"]
                        answer_snippet = str(data)[:110]
                    else:
                        status, reasons = _score_case(case, sc, data)
                        answer = data.get("answer", "")
                        answer_snippet = answer[:110].replace("\n", " ")
                        sources_n = len(data.get("sources", []))

                        if not args.no_judge and case.get("kind") == "rag" and status != "FAIL":
                            judge = await grade_answer(
                                case["question"], answer, case["expect"].get("answer_contains")
                            )
                            if judge.get("skipped"):
                                reasons.append(f'judge skipped ({judge.get("reason")})')
                            elif judge["score"] < 3.5:
                                status = "FAIL"
                                reasons.append(
                                    f'judge score {judge["score"]}/5 not grounded={not judge["grounded"]}: {judge.get("reason")}'
                                )
                            else:
                                reasons.append(f'judge {judge["score"]}/5 grounded={judge["grounded"]}')
            except httpx.ConnectError as e:
                status, reasons = "FAIL", [f"connect error to {args.base_url}: {e}"]
            except httpx.TimeoutException:
                status, reasons = "FAIL", ["timeout (LLM cold-load or stack busy)"]
            except httpx.HTTPStatusError as e:
                status, reasons = "FAIL", [f"HTTPStatusError {e.response.status_code}"]

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            records.append(
                {
                    "id": case_id, "kind": case.get("kind"), "status": status,
                    "ms": elapsed_ms, "sources": sources_n,
                    "answer": answer_snippet, "reasons": reasons,
                    "soft": bool(case.get("soft")),
                }
            )

            icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}[status]
            tag = " (soft)" if case.get("soft") else ""
            print(f"{icon} [{status:4s}] {case_id:<22}{tag:8s} {elapsed_ms:>6}ms  src={sources_n}")
            for r in reasons:
                print(f"         · {r}")
            print(f"         → {answer_snippet}")

    print("-" * 74)

    hard = [r for r in records if not r["soft"]]
    soft = [r for r in records if r["soft"]]
    hard_passed = [r for r in hard if r["status"] == "PASS"]
    pass_frac = len(hard_passed) / max(len(hard), 1)
    ok = pass_frac >= args.threshold and any(r["status"] == "FAIL" for r in hard) is False

    for r in soft:
        if r["status"] != "PASS":
            print(f"⚠ soft case {r['id']}: {'; '.join(r['reasons']) or 'no reasons logged'}")

    print(f"\nRESULT: {len(hard_passed)}/{len(hard)} hard cases passed "
          f"({pass_frac:.0%}; threshold {args.threshold:.0%})" + 
          (f" + {len([r for r in soft if r['status']=='PASS'])} soft passed" if soft else ""))
    print(f"report → {REPORT_PATH.relative_to(HERE.parent)}")

    REPORT_PATH.write_text(json.dumps(records, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))