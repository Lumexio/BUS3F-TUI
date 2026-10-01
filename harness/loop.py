# ~/agent_team/harness/loop.py
"""Bounded ReAct loop with MAX_STEPS, time budget, and tool dispatch."""

from __future__ import annotations
import os
import re
import time
import uuid
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Callable

from harness.db import (
    init_db, log_trace, save_checkpoint, load_checkpoint,
    create_session, close_session
)
from tools.gamedev_tools import (
    read_file, write_file_dry, grep_file, list_dir, read_log, grep_error
)

LLM_URL = os.environ.get("LLM_URL", "http://localhost:8080/v1/chat/completions")
MAX_STEPS = 8
TIME_BUDGET_SEC = 600
APPROVAL_REQUIRED_TOOLS = {"write_file_dry"}
PLUGIN_TOOLS: set[str] = set()

TOOL_REGISTRY: dict[str, Callable] = {
    "read_file": read_file,
    "write_file_dry": write_file_dry,
    "grep_file": grep_file,
    "list_dir": list_dir,
    "read_log": read_log,
    "grep_error": grep_error,
}


def call_llm(messages: list[dict], model: str = "qwen", temperature: float = 0.1,
             grammar_path: str | None = None) -> dict[str, Any]:
    """Call llama-server OpenAI-compatible endpoint."""
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": -1,  # -1 = dynamic tokens (generates until completion/EOS)
    }
    if grammar_path:
        gp = Path(grammar_path)
        if not gp.is_absolute():
            gp = Path(__file__).parent.parent / grammar_path
        try:
            payload["grammar"] = gp.read_text(encoding="utf-8")
        except FileNotFoundError:
            pass  # Grammar file missing — degrade gracefully

    t0 = time.monotonic()
    req = urllib.request.Request(
        LLM_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
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
    result: dict[str, Any] = {"thought": "", "action": None, "args": {}, "final_answer": None}

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        th_match = re.match(r'^(?:\*\*)?Thought(?:\*\*)?\s*:\s*(.*)', stripped, re.IGNORECASE)
        fa_match = re.match(r'^(?:\*\*)?Final Answer(?:\*\*)?\s*:\s*(.*)', stripped, re.IGNORECASE)
        ac_match = re.match(r'^(?:\*\*)?Action(?:\*\*)?\s*:\s*(.*)', stripped, re.IGNORECASE)
        ar_match = re.match(r'^(?:\*\*)?Args(?:\*\*)?\s*:\s*(.*)', stripped, re.IGNORECASE)

        if th_match:
            raw = th_match.group(1).strip()
            j = i + 1
            while j < len(lines):
                s = lines[j].strip()
                if re.match(r'^(?:\*\*)?(Action|Args|Final Answer)(?:\*\*)?\s*:', s, re.IGNORECASE):
                    break
                raw += "\n" + lines[j]
                j += 1
            result["thought"] = raw.strip()
            i = j - 1
        elif fa_match:
            raw = fa_match.group(1).strip()
            j = i + 1
            while j < len(lines):
                s = lines[j].strip()
                if re.match(r'^(?:\*\*)?(Thought|Action|Args)(?:\*\*)?\s*:', s, re.IGNORECASE):
                    break
                raw += "\n" + lines[j]
                j += 1
            result["final_answer"] = raw.strip()
            i = j - 1
        elif ac_match:
            result["action"] = ac_match.group(1).strip()
        elif ar_match:
            # Collect everything from Args: onward into one string
            raw = ar_match.group(1).strip()
            # Gather continuation lines until next section header
            j = i + 1
            while j < len(lines):
                next_line = lines[j]
                s = next_line.strip()
                if re.match(r'^(?:\*\*)?(Thought|Action|Final Answer)(?:\*\*)?\s*:', s, re.IGNORECASE):
                    break
                raw += "\n" + next_line
                j += 1
            i = j - 1

            # Try to parse as JSON with strict=False (allows unescaped control chars / newlines)
            try:
                parsed_args = json.loads(raw, strict=False)
            except json.JSONDecodeError:
                parsed_args = {}
                try:
                    start = raw.find("{")
                    end = raw.rfind("}")
                    if start != -1 and end > start:
                        parsed_args = json.loads(raw[start:end+1], strict=False)
                except (json.JSONDecodeError, TypeError):
                    parsed_args = {}

            # Ensure parsed_args is a dict
            if not isinstance(parsed_args, dict):
                parsed_args = {}

            # Normalize alternate key names the model might use
            KEY_ALIASES = {
                "file_path": "path",
                "filepath": "path",
                "filename": "path",
                "file": "path",
                "code": "content",
                "source": "content",
                "text": "content",
                "script": "content",
                "new_content": "content",
                "file_content": "content",
                "updated_code": "content",
                "new_code": "content",
            }
            normalized = {}
            for k, v in parsed_args.items():
                normalized[KEY_ALIASES.get(k, k)] = v
            result["args"] = normalized
        i += 1

    # Fallback: if tool expects content and none found in args, grab code from text
    if result["action"] in ("write_cs_dry", "write_gd_dry", "check_unity2018_apis", "check_godot35_apis"):
        if not result["args"].get("content"):
            code_block = re.search(r'```(?:\w+)?\s*\n(.*?)\n```', text, re.DOTALL)
            if code_block:
                result["args"]["content"] = code_block.group(1).strip()
            elif "using UnityEngine" in text:
                start = text.find("using UnityEngine")
                end = text.find("Final Answer:", start)
                result["args"]["content"] = text[start:end if end != -1 else len(text)].strip()
            elif "extends " in text:
                start = text.find("extends ")
                end = text.find("Final Answer:", start)
                result["args"]["content"] = text[start:end if end != -1 else len(text)].strip()

    # Treat literal "None" or "Final Answer" as no action
    if result["action"] and result["action"].lower() in (
        "none", "null", "n/a", "-", "final answer", "finalanswer"
    ):
        result["action"] = None
    return result


def request_human_approval(tool_name: str, args: dict, dry_result: dict) -> bool:
    """Styled human approval gate for write operations."""
    path = args.get("path", "?")
    content_to_show = dry_result.get("fixed_content") or dry_result.get("content") or ""
    line_count = len(content_to_show.splitlines())

    print(f"\n  \033[33m\033[1m⚠ Approval Required\033[0m  \033[2m{tool_name}\033[0m")
    print(f"  \033[1mTarget:\033[0m {path} \033[2m({line_count} lines)\033[0m")
    if content_to_show:
        print(f"  \033[2m── Preview (first 25 lines) ──────────────\033[0m")
        for line in content_to_show.splitlines()[:25]:
            print(f"  \033[2m│\033[0m {line}")
        if line_count > 25:
            print(f"  \033[2m│ … +{line_count - 25} more lines\033[0m")
        print(f"  \033[2m──────────────────────────────────────────\033[0m")

    try:
        response = input(f"  \033[33mCommit to disk?\033[0m [y/N]: ").strip().lower()
        return response == "y"
    except (EOFError, KeyboardInterrupt):
        return False


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

    # Build message history (resume existing session history or start fresh)
    checkpoint = load_checkpoint(session_id)
    if checkpoint and "messages" in checkpoint.get("state", {}):
        prior = checkpoint["state"]["messages"]
        # Drop any poisoned assistant stubs that were truncated in prior sessions
        cleaned = []
        for m in prior:
            if m.get("role") == "assistant" and m.get("content", "").strip().endswith(":") and len(m.get("content", "").strip()) < 80:
                continue
            cleaned.append(m)
        if len(cleaned) > 6:
            cleaned = [cleaned[0]] + cleaned[-4:]
        messages = cleaned + [
            {"role": "user", "content": f"Task: {task}\n\nRespond in ReAct format:\nThought: <reasoning>\nFinal Answer: <complete code and response>\nOR\nAction: <tool_name>\nArgs: {{\"path\": \"<path>\", \"content\": \"<code>\"}}"}
        ]
        start_step = 0
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Task: {task}\n\nRespond in ReAct format:\nThought: <reasoning>\nFinal Answer: <complete code and response>\nOR\nAction: <tool_name>\nArgs: {{\"path\": \"<path>\", \"content\": \"<code>\"}}"},
        ]
        start_step = 0

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

            # Final answer — done (only if no action requested)
            if parsed["final_answer"] and not parsed["action"]:
                messages.append({"role": "assistant", "content": parsed["final_answer"]})
                save_checkpoint(session_id, step + 1, {"messages": messages})
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
                ans = parsed["final_answer"] or re.sub(r'^(?:Thought:)?\s*', '', content).strip()
                messages.append({"role": "assistant", "content": ans})
                save_checkpoint(session_id, step + 1, {"messages": messages})
                log_trace(session_id, step, agent_name, "final_answer", model_out=ans)
                close_session(session_id)
                return {"ok": True, "result": ans, "steps": step + 1, "session_id": session_id}

            # If path/content missing from tool call, infer path from task
            if not tool_args.get("path") and not tool_args.get("content"):
                pm = re.search(r'(/[\w./\-\\ ]+\.(?:[\w]+))', task)
                if pm:
                    tool_args["path"] = pm.group(1).strip()
            elif tool_name in ("write_file_dry", "read_file", "grep_file") and not tool_args.get("path"):
                pm = re.search(r'(/[\w./\-\\ ]+\.(?:[\w]+))', task)
                if pm:
                    tool_args["path"] = pm.group(1).strip()

            # Enforce tool whitelist (built-in whitelist or loaded plugin tools)
            if tool_name not in tool_whitelist and tool_name not in PLUGIN_TOOLS:
                tool_result = {"ok": False, "error": f"Tool '{tool_name}' not in whitelist for this agent"}
            elif tool_name not in TOOL_REGISTRY:
                tool_result = {"ok": False, "error": f"Tool '{tool_name}' not found in registry"}
            else:
                try:
                    # Human approval gate for write tools
                    if tool_name in APPROVAL_REQUIRED_TOOLS:
                        tool_fn = TOOL_REGISTRY[tool_name]
                        dry_result = tool_fn(**tool_args, commit=False)
                        if not dry_result.get("ok"):
                            tool_result = dry_result
                        else:
                            t_pause = time.monotonic()
                            approved = request_human_approval(tool_name, tool_args, dry_result)
                            # Do not penalize agent for human reading/approval time
                            deadline += (time.monotonic() - t_pause)
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
                except Exception as e:
                    tool_result = {"ok": False, "error": str(e)}

            # If tool committed file to disk or succeeded with a final answer, conclude cleanly
            if tool_result.get("written") or (tool_result.get("ok") and parsed.get("final_answer")):
                summary = parsed.get("final_answer") or f"Successfully updated and saved {tool_args.get('path', 'file')}."
                messages.append({"role": "assistant", "content": summary})
                save_checkpoint(session_id, step + 1, {"messages": messages})
                log_trace(session_id, step, agent_name, "final_answer", model_out=summary)
                close_session(session_id)
                return {
                    "ok": True,
                    "result": summary,
                    "steps": step + 1,
                    "session_id": session_id,
                }

            # Append observation to message history with sliding window protection
            messages.append({"role": "assistant", "content": content})
            if tool_result.get("ok") is False:
                obs = f"Observation: ERROR — {tool_result.get('error', 'unknown error')}. Fix your action and try again, or give a Final Answer if you cannot proceed."
            else:
                raw_obs = json.dumps(tool_result)
                if len(raw_obs) > 2500:
                    raw_obs = raw_obs[:2300] + f"... [truncated {len(raw_obs) - 2300} chars]"
                obs = f"Observation: {raw_obs}"

            messages.append({
                "role": "user",
                "content": f"{obs}\n\nContinue. Use Action/Args or give a Final Answer."
            })

            # Compact message history if context window is getting full (keep system prompt, initial task, and recent steps)
            if len(messages) > 10:
                messages = [messages[0], messages[1]] + messages[-6:]

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

    except KeyboardInterrupt:
        log_trace(session_id, step, agent_name, "cancelled")
        close_session(session_id, "cancelled")
        return {"ok": False, "result": "Cancelled by user.", "steps": step, "session_id": session_id}
    except (urllib.error.URLError, TimeoutError, OSError, Exception) as e:
        log_trace(session_id, step, agent_name, "llm_error", model_out=str(e))
        close_session(session_id, "error")
        return {"ok": False, "result": f"LLM connection error: {e}", "steps": step, "session_id": session_id}
