# ~/agent_team/harness/router.py
"""
Router agent with deterministic pre-filters before model call.
Pre-filters handle the obvious cases without burning tokens.
"""

from __future__ import annotations
import re
import json
import uuid
import time
from typing import Any

from pathlib import Path
from harness.loop import call_llm
from harness.db import init_db, log_trace, create_session

GRAMMAR_PATH = str(Path(__file__).parent.parent / "grammars" / "router.gbnf")

SYSTEM_PROMPT_ROUTER = """
You are a software development task router. Your ONLY job is to classify the user's request and output a single JSON object. You do not write code, explain concepts, or answer questions.

Output format (strict — no other text):
{"engine": "<ENGINE>", "task": "<TASK>"}

ENGINE must be exactly one of: coder, reviewer, debugger, general
TASK must be exactly one of: edit, review, explain, debug, scaffold

Classification rules:
- engine=coder    : code edits, writing features, refactoring, fixing bugs, creating new scripts
- engine=reviewer : code audits, reviews, checking compliance, style, or syntax
- engine=debugger : errors, crash logs, stack traces, failure diagnosis
- engine=general  : general questions, explanations, architecture, or ambiguous queries
- task=edit       : fix, change, update, rewrite, refactor, modify, implement
- task=review     : check, review, audit, validate, inspect, lint
- task=explain    : explain, how does, what is, describe, walk me through
- task=debug      : not working, broken, error, crash, fails, why is
- task=scaffold   : create, generate, new, scaffold, write from scratch
Output ONLY the JSON. No markdown. No explanation.
"""

# Pre-filter patterns (deterministic, no model call needed)
BUILD_KEYWORDS = re.compile(
    r'\b(build error|compile error|error log|linker|missing reference|parse error|traceback|panic|syntaxerror|typeerror)\b',
    re.IGNORECASE
)

EDIT_KEYWORDS = re.compile(r'\b(fix|change|rewrite|refactor|modify|correct|repair)\b|\bupdate\b(?!\s*\()', re.IGNORECASE)
DEBUG_KEYWORDS = re.compile(
    r'\b(not working|broken|error|crash|fail|bug|why is|doesn\'t work|failing test|segfault)\b',
    re.IGNORECASE
)
SCAFFOLD_KEYWORDS = re.compile(r'\b(create|generate|new|scaffold|make me|write from scratch|template)\b', re.IGNORECASE)
REVIEW_KEYWORDS = re.compile(r'\b(check|review|audit|validate|inspect|look at|analyze)\b', re.IGNORECASE)
EXPLAIN_KEYWORDS = re.compile(r'\b(explain|how does|what is|describe|walk me through|what\'s)\b', re.IGNORECASE)


def _prefilter_route(text: str) -> dict[str, str] | None:
    """
    Deterministic pre-filter. Returns route dict if confident, None to fall through to model.
    Tradeoff: pre-filters are fast and token-free but can't handle ambiguous phrasings.
    Default: return None (use model) when uncertain.
    """
    engine = None
    if BUILD_KEYWORDS.search(text):
        engine = "debugger"
    else:
        from agents.profiles import AGENT_PROFILES
        for key, prof in AGENT_PROFILES.items():
            if prof.get("keywords"):
                pattern = r'\b(' + '|'.join(re.escape(k) for k in prof['keywords']) + r')\b'
                if re.search(pattern, text, re.IGNORECASE):
                    engine = key
                    break

    task = None
    if SCAFFOLD_KEYWORDS.search(text):
        task = "scaffold"
    elif DEBUG_KEYWORDS.search(text):
        task = "debug"
    elif EDIT_KEYWORDS.search(text):
        task = "edit"
    elif REVIEW_KEYWORDS.search(text):
        task = "review"
    elif EXPLAIN_KEYWORDS.search(text):
        task = "explain"

    if not engine and task:
        if task in ("edit", "scaffold"):
            engine = "coder"
        elif task == "review":
            engine = "reviewer"
        elif task == "debug":
            engine = "debugger"
        elif task == "explain":
            engine = "general"

    if engine and task:
        return {"engine": engine, "task": task}
    return None  # Fall through to model


def route(user_input: str, session_id: str | None = None) -> dict[str, Any]:
    """
    Route a user input to an engine+task. Returns routing dict with metadata.
    """
    init_db()
    session_id = session_id or f"s-{uuid.uuid4().hex[:8]}"
    create_session(session_id, user_input)

    t0 = time.monotonic()

    # Try pre-filter first
    prefilter_result = _prefilter_route(user_input)
    if prefilter_result:
        elapsed = int((time.monotonic() - t0) * 1000)
        log_trace(session_id, 0, "router", "prefilter_route",
                  tool_result=prefilter_result, elapsed_ms=elapsed)
        return {
            "session_id": session_id,
            "engine": prefilter_result["engine"],
            "task": prefilter_result["task"],
            "method": "prefilter",
            "elapsed_ms": elapsed,
        }

    # Fall through to model
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_ROUTER},
        {"role": "user", "content": user_input},
    ]
    try:
        llm_result = call_llm(messages, temperature=0.0, grammar_path=GRAMMAR_PATH)
        elapsed = int((time.monotonic() - t0) * 1000)
        route_json = json.loads(llm_result["content"])
        engine = route_json.get("engine", "general")
        task = route_json.get("task", "explain")
        method = "model"
        content_out = llm_result.get("content", "")
        tokens_in = llm_result.get("tokens_in", 0)
        tokens_out = llm_result.get("tokens_out", 0)
    except Exception as e:
        elapsed = int((time.monotonic() - t0) * 1000)
        engine = "general"
        task = "explain"
        method = "fallback"
        content_out = str(e)
        tokens_in = 0
        tokens_out = 0

    log_trace(
        session_id, 0, "router", f"{method}_route",
        model_out=content_out,
        tool_result={"engine": engine, "task": task},
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        elapsed_ms=elapsed,
    )

    return {
        "session_id": session_id,
        "engine": engine,
        "task": task,
        "method": method,
        "elapsed_ms": elapsed,
    }
