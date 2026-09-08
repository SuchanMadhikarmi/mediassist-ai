# ============================================================
# backend/eval/judge.py
# LLM-AS-A-JUDGE for the Phase 9 eval suite.
#
# CONCEPT (the umbrella idea of this whole phase):
# We already grade LLM output WITH an LLM inside the CRAG graph — three
# times: grade_sufficiency, grade_faithfulness, and the generate loop.
# Eval simply reuses that pattern AT THE TEST level: give a judge model
# (question, candidate answer, reference hints) and ask it to score.
#
# WHY AUTO-JUDGE INSTEAD OF KEYWORD CHECKS ONLY:
# The golden set's hard pass/fail criteria are keyword/source checks —
# deterministic and cheap. But "is this a GOOD, grounded answer?" cannot
# be keyword-checked. The judge adds a quality signal (1-5) that catches
# drift the deterministic checks can't (e.g. a confident-sounding wrong
# answer that still contains the right keywords).
#
# RESILIENCE: the judge is BEST-EFFORT. If Ollama is down or slow, we
# SKIP grading and mark the case judge="skipped" — a missing quality
# score must never block an otherwise-correct pipeline result.
# ============================================================

import json
import re

import httpx

from config import settings

_JUDGE_PROMPT = """\
You are a strict answer-quality judge for a clinical support chatbot.
Score the assistant's answer to the user's question.

QUESTION:
{question}

ASSISTANT ANSWER:
{answer}

REFERENCE HINTS (facts the answer may be expected to mention):
{reference_hints}

Judge on three axes:
 1. Correctness — is the answer factually aligned with the reference?
 2. Groundedness — does the answer stay within what could be known from
    the company materials, without inventing specifics?
 3. Helpfulness — does it directly answer the question?

Reply with ONLY a JSON object of the form:
{{"score": 1, "grounded": true, "reason": "one concise sentence"}}
where score is an integer 1 (terrible) to 5 (excellent).
"""


async def grade_answer(
    question: str,
    answer: str,
    reference_hints: list[str] | None = None,
    model: str | None = None,
    ollama_host: str | None = None,
    timeout: float = 150.0,
) -> dict:
    """Ask a judge LLM to score the answer.

    Returns:
        On success:      {"score": 1-5, "grounded": bool, "reason": str}
        On LLM failure:  {"score": None, "skipped": True, "reason": ...}
        On BUSY engine:  {"score": None, "skipped": True, "reason": "Ollama busy..."}
    """
    if not answer.strip():
        return {"score": None, "skipped": True, "reason": "empty answer"}

    payload = {
        "model": model or settings.primary_model,   # qwen: fast enough to judge
        "messages": [
            {
                "role": "system",
                "content": _JUDGE_PROMPT.format(
                    question=question,
                    answer=answer,
                    reference_hints="; ".join(reference_hints or []) or "(none provided)",
                ),
            }
        ],
        "stream": False,
        "options": {"temperature": 0.0},  # judges must be consistent, not creative
    }

    base = ollama_host or settings.ollama_host
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{base}/api/chat", json=payload)
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
    except httpx.HTTPStatusError as e:
        return {"score": None, "skipped": True, "reason": f"Ollama HTTP {e.response.status_code}"}
    except httpx.ConnectError:
        return {"score": None, "skipped": True, "reason": "Ollama unreachable"}
    except (httpx.TimeoutException, KeyError) as e:
        msg = str(e) or e.__class__.__name__
        return {"score": None, "skipped": True, "reason": f"judge call failed: {msg}"}

    # The model may wrap JSON in ``` code fences — strip them, then parse.
    try:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return {"score": None, "skipped": True, "reason": "no JSON in judge reply"}
        parsed = json.loads(match.group(0))
        return {
            "score": int(parsed["score"]),
            "grounded": bool(parsed.get("grounded", False)),
            "reason": str(parsed.get("reason", "")),
        }
    except (ValueError, KeyError, TypeError) as e:
        return {"score": None, "skipped": True, "reason": f"bad judge reply: {e}"}