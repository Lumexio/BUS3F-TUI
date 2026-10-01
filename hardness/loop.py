# ~/agent_team/harness/loop.py
"""Bounded ReAct loop with MAX_STEPS, time budget, and tool dispatch."""

from __future__ import annotations
import time
import uuid
import json
import requests
from typing import Any, Callable

from harness.db import (
    init_db, log_trace, save_checkpoint, load_checkpoint,
    create_session, close_session
)
from tools.gamedev_tools import (
    read_gd, write_gd_dry, check_godot35_apis,
    read_cs, write_cs_dry, check_unity2018_apis,
    read_scene, read_log, grep_error, read_file, list_dir
)

LLM_URL = "http://localhost:8080/v1/chat/completions"
MAX_STEPS = 8
TIME_BUDGET_SEC = 120
APPROVAL_REQUIRED_TOOLS = {"write_gd_dry", "write_cs_dry"}

TOOL_REGISTRY: dict[str, Callable] = {
    "read_gd": read_gd,
    "write_gd_dry": write_gd_dry,
    "check_godot35_apis": check_godot35_apis,
    "read_cs": read_cs,
    "write_cs_dry": write_cs_dry,
    "check_unity2018_apis": check_unity2018_apis,
    "read_scene": read_scene,
    "read_log": read_log,
    "grep_error": grep_error,
    "read_file": read_file,
    "list_dir": list_dir,
}


def call_llm(messages: list[dict], model: str = "qwen", temperature: float = 0.1,
             grammar_path: str | None = None) -> dict[str, Any]:
    """Call llama-server OpenAI-compatible endpoint."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 1024,
    }
    if grammar_path:
        try:
            with open(grammar_path) as f:
                payload["grammar"] = f.read()
        except FileNotFoundError:
            pass  # Grammar file missing — degrade gracefully

    t0 = time.monotonic()
    resp = requests.post(LLM_URL, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    elapsed = int((time.monotonic() - t0) * 1000)

    content = data["choices"][0]["message"]["content"]
    usage = data.get("usage", {})
    return {
        "content": content,
        "tokens_in": usage.get("prompt_tokens", 0),
        "tokens_out": usage.get("completion_tokens", 0),
        "elapsed_ms": elapsed,
    }


def parse_react_step(text: str) -> dict[str, Any]:
    """
    Parse a ReAct-format response.
    Expected format:
        Thought: <reasoning>
        Action: <tool_name>
        Args: <json dict>
    Or for final answer:
        Thought: <reasoning>
        Final Answer: <text>
    """
    result: dict[str, Any] = {"thought": "", "action": None, "args": {}, "final_answer": None}

    for line in text.splitlines():
        if line.startswith("Thought:"):
            result["thought"] = line[len("Thought:"):].strip()
        elif line.startswith("Final Answer:"):
            result["final_answer"] = line[len("Final Answer:"):].strip()
        elif line.startswith("Action:"):
            result["action"] = line[len("Action:"):].strip()
        elif line.startswith("Args:"):
            try:
                result["args"] = json.loads(line[len("Args:"):].strip())
            except json.JSONDecodeError:
                result["args"] = {}
    return result


def request_human_approval(tool_name: str, args: dict, dry_result: dict) -> bool:
    """Blocking human approval gate for write operations."""
    print("\n" + "=" * 60)
    print(f"[APPROVAL REQUIRED] Tool: {tool_name}")
    print(f"Path: {args.get('path', '?')}")
    if "fixed_content" in dry_result:
        print("\n--- Proposed content (first 30 lines) ---")
        lines = dry_result["fixed_content"].splitlines()[:30]
        print("\n".join(lines))
        if len(dry_result["fixed_content"].splitlines()) > 30:
            print(f"... ({len(dry_result['fixed_content'].splitlines())} total lines)")
    print("=" * 60)
    response = input("Approve write? [y/N]: ").strip().lower()
    return response == "y"


def run_agent(
    session_id: str,
    system_prompt: str,
    task: str,
    agent_name: str,
    tool_whitelist: list[str],
    grammar_path: str | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    """
    Run a bounded ReAct loop for one agent.
    Returns {"ok": bool, "result": str, "steps": int, "session_id": str}
    """
    init_db()

    # Build initial message history
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Task: {task}\n\nRespond in ReAct format:\nThought: <your reasoning>\nAction: <tool_name> OR\nFinal Answer: <answer>\nArgs: <json args if using a tool>"},
    ]

    # Resume from checkpoint if requested
    start_step = 0
    if resume:
        checkpoint = load_checkpoint(session_id)
        if checkpoint:
            start_step = checkpoint["step"]
            messages = checkpoint["state"].get("messages", messages)
            print(f"[harness] Resuming from step {start_step}")

    deadline = time.monotonic() + TIME_BUDGET_SEC
    step = start_step

    try:
        while step < MAX_STEPS:
            if time.monotonic() > deadline:
                log_trace(session_id, step, agent_name, "timeout")
                close_session(session_id, "timeout")
                return {"ok": False, "result": "Time budget exceeded", "steps": step, "session_id": session_id}

            # Call LLM
            llm_result = call_llm(messages, grammar_path=grammar_path)
            content = llm_result["content"]

            log_trace(
                session_id, step, agent_name, "llm_call",
                model_out=content,
                tokens_in=llm_result["tokens_in"],
                tokens_out=llm_result["tokens_out"],
                elapsed_ms=llm_result["elapsed_ms"],
            )

            # Parse ReAct step
            parsed = parse_react_step(content)

            # Final answer — done
            if parsed["final_answer"]:
                log_trace(session_id, step, agent_name, "final_answer", model_out=parsed["final_answer"])
                close_session(session_id)
                return {
                    "ok": True,
                    "result": parsed["final_answer"],
                    "steps": step + 1,
                    "session_id": session_id,
                }

            # Tool call
            tool_name = parsed["action"]
            tool_args = parsed["args"]

            if not tool_name:
                # No action parsed — treat as final answer
                close_session(session_id)
                return {"ok": True, "result": content, "steps": step + 1, "session_id": session_id}

            # Enforce tool whitelist
            if tool_name not in tool_whitelist:
                tool_result = {"ok": False, "error": f"Tool '{tool_name}' not in whitelist for this agent"}
            elif tool_name not in TOOL_REGISTRY:
                tool_result = {"ok": False, "error": f"Tool '{tool_name}' not found in registry"}
            else:
                # Human approval gate for write tools
                if tool_name in APPROVAL_REQUIRED_TOOLS:
                    # Run dry-run first
                    tool_fn = TOOL_REGISTRY[tool_name]
                    dry_result = tool_fn(**tool_args, commit=False)
                    approved = request_human_approval(tool_name, tool_args, dry_result)
                    if approved:
                        tool_result = tool_fn(**tool_args, commit=True)
                    else:
                        tool_result = {"ok": False, "error": "User rejected write operation", "dry_run": dry_result}
                else:
                    tool_fn = TOOL_REGISTRY[tool_name]
                    t0 = time.monotonic()
                    tool_result = tool_fn(**tool_args)
                    elapsed = int((time.monotonic() - t0) * 1000)
                    log_trace(
                        session_id, step, agent_name, "tool_call",
                        tool_name=tool_name,
                        tool_args=tool_args,
                        tool_result=tool_result,
                        elapsed_ms=elapsed,
                    )

            # Append observation to message history
            messages.append({"role": "assistant", "content": content})
            messages.append({
                "role": "user",
                "content": f"Observation: {json.dumps(tool_result)}\n\nContinue. If you have enough information, give a Final Answer."
            })

            # Save checkpoint
            save_checkpoint(session_id, step, {"messages": messages})
            step += 1

        # Exceeded MAX_STEPS
        log_trace(session_id, step, agent_name, "max_steps_exceeded")
        close_session(session_id, "exceeded")
        return {
            "ok": False,
            "result": f"Exceeded {MAX_STEPS} steps without final answer",
            "steps": step,
            "session_id": session_id,
        }

    except requests.RequestException as e:
        log_trace(session_id, step, agent_name, "llm_error", model_out=str(e))
        close_session(session_id, "error")
        return {"ok": False, "result": f"LLM connection error: {e}", "steps": step, "session_id": session_id}
