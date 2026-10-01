# ~/agent_team/agents/profiles.py
"""Universal developer agent profiles and dynamic custom agent loader."""

from __future__ import annotations
import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from harness.router import SYSTEM_PROMPT_ROUTER  # noqa: F401

SYSTEM_PROMPT_CODER = """
You are an expert autonomous software engineer and pair programmer.
You write clean, idiomatic, robust code in any programming language (Python, C#, Rust, TypeScript, JavaScript, Go, C/C++, GDScript, Bash, etc.).

When editing or creating files:
1. If file content is provided in prompt, do not re-read it.
2. Write complete, working code and call write_file_dry with "path" and "content".
3. Maintain existing style, types, and conventions. Never introduce unneeded dependencies.
4. If a target file path is specified, use write_file_dry to save it. If NO target file path is specified (e.g. asking for a snippet, algorithm, or explanation), provide the complete, working code implementation directly in your Final Answer using markdown code blocks.

Respond in ReAct format:
Thought: <reasoning>
Action: <tool_name>
Args: {"path": "<path>", "content": "<code>"}
OR
Thought: <reasoning>
Final Answer: <complete code and explanation>
"""

SYSTEM_PROMPT_REVIEWER = """
You are an expert code reviewer and static analysis specialist.
Your job is to audit code for bugs, edge cases, security issues, performance pitfalls, and over-engineering.
Use read_file to inspect code. Provide concise, high-signal findings with exact line references and concrete fixes.

Respond in ReAct format:
Thought: <reasoning>
Action: read_file
Args: {"path": "<path>"}
OR
Final Answer: <review findings>
"""

SYSTEM_PROMPT_DEBUGGER = """
You are a root-cause debugging specialist.
You investigate errors, crash logs, stack traces, and failing tests.
Identify the exact defect, explain the failure mechanism, and propose the minimal fix.
Use grep_file, read_file, or read_log to inspect relevant files.

Respond in ReAct format:
Thought: <reasoning>
Action: <tool_name>
Args: <json args>
OR
Final Answer: <diagnosis and fix>
"""

SYSTEM_PROMPT_GENERAL = """You are an expert autonomous software engineer and architectural advisor.
You answer technical questions, explain codebases, analyze architectures, and plan multi-step implementations.

CRITICAL RULES:
1. If the user's request is a question, greeting, conversational comment, or ambiguous, respond immediately with Final Answer. Do NOT call tools.
2. Only call tools (read_file, list_dir, grep_file) when you actually need to inspect project files to answer the user's specific request.
3. Keep answers clear, minimal, and actionable.

Respond in ReAct format:
Thought: <reasoning>
Action: <tool_name>
Args: <json args>
OR
Final Answer: <your response>"""

AGENT_PROFILES: dict[str, dict] = {
    "coder": {
        "name": "code-specialist",
        "system_prompt": SYSTEM_PROMPT_CODER,
        "tool_whitelist": ["read_file", "write_file_dry", "list_dir", "grep_file"],
        "grammar_path": None,
    },
    "reviewer": {
        "name": "code-reviewer",
        "system_prompt": SYSTEM_PROMPT_REVIEWER,
        "tool_whitelist": ["read_file", "list_dir", "grep_file"],
        "grammar_path": None,
    },
    "debugger": {
        "name": "build-doctor",
        "system_prompt": SYSTEM_PROMPT_DEBUGGER,
        "tool_whitelist": ["read_file", "read_log", "grep_error", "grep_file", "write_file_dry"],
        "grammar_path": None,
    },
    "general": {
        "name": "general-agent",
        "system_prompt": SYSTEM_PROMPT_GENERAL,
        "tool_whitelist": ["read_file", "list_dir", "grep_file", "write_file_dry"],
        "grammar_path": None,
    },
}

# Legacy engine alias compatibility mappings
AGENT_PROFILES["godot"] = AGENT_PROFILES["coder"]
AGENT_PROFILES["unity"] = AGENT_PROFILES["coder"]
AGENT_PROFILES["asset"] = AGENT_PROFILES["coder"]
AGENT_PROFILES["build"] = AGENT_PROFILES["debugger"]

CUSTOM_AGENTS_DIR = Path.home() / "agent_team" / "custom_agents"


def load_custom_agents() -> dict[str, dict]:
    """Load user-defined local agents from ~/agent_team/custom_agents/*.json or local custom_agents/."""
    dirs = [
        CUSTOM_AGENTS_DIR,
        Path(__file__).parent.parent / "custom_agents",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        for p in d.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                key = p.stem.lower()
                AGENT_PROFILES[key] = {
                    "name": data.get("name", key),
                    "system_prompt": data.get("system_prompt", f"You are {key} specialist."),
                    "tool_whitelist": data.get("tool_whitelist", ["read_file", "write_file_dry", "list_dir", "grep_file"]),
                    "parent": data.get("parent", None),
                    "keywords": data.get("keywords", []),
                    "grammar_path": data.get("grammar_path", None),
                    "custom": True,
                }
            except Exception:
                pass
    return AGENT_PROFILES


load_custom_agents()
