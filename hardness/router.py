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

from harness.loop import call_llm
from harness.db import init_db, log_trace, create_session

GRAMMAR_PATH = "grammars/router.gbnf"

SYSTEM_PROMPT_ROUTER = """
You are a game-development task router. Your ONLY job is to classify the user's request and output a single JSON object. You do not write code, explain concepts, or answer questions.

Output format (strict — no other text):
{"engine": "<ENGINE>", "task": "<TASK>"}

ENGINE must be exactly one of: godot, unity, asset, build, general
TASK must be exactly one of: edit, review, explain, debug, scaffold

Classification rules:
- engine=godot : mentions GDScript, .gd files, .tscn, Godot, nodes, signals, export var
- engine=unity : mentions C#, .cs files, .unity, Unity, MonoBehaviour, GameObject, Inspector
- engine=asset : mentions textures, sprites, import settings, atlas, compression, mipmaps
- engine=build : mentions build errors, compile errors, log files, linker errors, missing references
- engine=general : none of the above, or ambiguous
- task=edit    : fix, change, update, rewrite, refactor, modify
- task=review  : check, review, audit, validate, look at, inspect
- task=explain : explain, how does, what is, describe, walk me through
- task=debug   : not working, broken, error, crash, fails, why is
- task=scaffold: create, generate, new, scaffold, make me a, write from scratch
Output ONLY the JSON. No markdown. No explanation.
"""

# Pre-filter patterns (deterministic, no model call needed)
GODOT_KEYWORDS = re.compile(
    r'\b(gdscript|\.gd\b|\.tscn\b|godot|kinematicbody|export var|onready|yield\(|get_node)',
    re.IGNORECASE
)
UNITY_KEYWORDS = re.compile(
    r'\b(monobehaviour|gameobject|\.cs\b|\.unity\b|unity|inspector|serializedfield|start\(\)|update\(\))',
    re.IGNORECASE
)
ASSET_KEYWORDS = re.compile(
    r'\b(texture|sprite|import setting|atlas|compression|mipmap|\.png\b|\.jpg\b|\.wav\b|\.meta\b|\.import\b)',
    re.IGNORECASE
)
BUILD_KEYWORDS = re.compile(
    r'\b(build error|compile error|error log|linker|missing reference|parse error|cs\d{4})',
    re.IGNORECASE
)

EDIT_KEYWORDS = re.compile(r'\b(fix|change|update|rewrite|refactor|modify|correct|repair)\b', re.IGNORECASE)
DEBUG_KEYWORDS = re.compile(r'\b(not working|broken|error|crash|fail|bug|why is|doesn\'t work)\b', re.IGNORECASE)
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
    if GODOT_KEYWORDS.search(text):
        engine = "godot"
    elif UNITY_KEYWORDS.search(text):
        engine = "unity"
    elif ASSET_KEYWORDS.search(text):
        engine = "asset"
    elif BUILD_KEYWORDS.search(text):
        engine = "build"

    task = None
    if DEBUG_KEYWORDS.search(text):
        task = "debug"
    elif EDIT_KEYWORDS.search(text):
        task = "edit"
    elif REVIEW_KEYWORDS.search(text):
        task = "review"
    elif EXPLAIN_KEYWORDS.search(text):
        task = "explain"
    elif SCAFFOLD_KEYWORDS.search(text):
        task = "scaffold"

    if engine and task:
        return {"engine": engine, "task": task}
    return None  # Fall through to model


def route(user_input: str) -> dict[str, Any]:
    """
    Route a user input to an engine+task. Returns routing dict with metadata.
    """
    init_db()
    session_id = str(uuid.uuid4())
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
    llm_result = call_llm(messages, temperature=0.0, grammar_path=GRAMMAR_PATH)
    elapsed = int((time.monotonic() - t0) * 1000)

    try:
        route_json = json.loads(llm_result["content"])
        engine = route_json.get("engine", "general")
        task = route_json.get("task", "explain")
    except json.JSONDecodeError:
        engine = "general"
        task = "explain"

    log_trace(
        session_id, 0, "router", "model_route",
        model_out=llm_result["content"],
        tool_result={"engine": engine, "task": task},
        tokens_in=llm_result["tokens_in"],
        tokens_out=llm_result["tokens_out"],
        elapsed_ms=elapsed,
    )

    return {
        "session_id": session_id,
        "engine": engine,
        "task": task,
        "method": "model",
        "elapsed_ms": elapsed,
    }
