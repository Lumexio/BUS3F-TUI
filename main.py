# ~/agent_team/main.py
"""
Entry point for the game-dev agent team.
Usage: python main.py "your task here"
       python main.py  (interactive mode)
"""

from __future__ import annotations
import sys
import uuid
from harness.router import route
from harness.loop import run_agent
from harness.db import init_db, create_session
from agents.profiles import AGENT_PROFILES

def run_task(user_input: str) -> None:
    import re as _re
    from pathlib import Path as _Path

    init_db()
    print(f"\n[task] {user_input}")

    clean = _re.sub(r"[^\w\s]", "", user_input.strip().lower())
    words = clean.split()
    if len(words) <= 3 and words and words[0] in ("hi", "hello", "hey", "hola", "yo", "sup", "howdy", "greetings"):
        print("[dispatch] Greeting received. Ready for coding tasks.")
        return

    if user_input.lower().startswith(("team ", "/team ")):
        from cli import run_team
        run_team(user_input.split(maxsplit=1)[1] if " " in user_input else "")
        return

    route_result = route(user_input)
    engine = route_result["engine"]
    task = route_result["task"]
    print(f"[router] engine={engine} task={task} method={route_result['method']} ({route_result['elapsed_ms']}ms)")

    profile = AGENT_PROFILES.get(engine, AGENT_PROFILES["general"])
    session_id = route_result["session_id"]
    print(f"[dispatch] → {profile['name']}")

    # Extract file path from input (supports absolute, relative, and quoted paths)
    file_match = _re.search(
        r'["\']([^"\']+\.(?:py|ts|js|rs|go|cs|gd|cpp|c|h|json|yaml|yml|toml|md|tscn|unity|log|txt))["\']|'
        r'(?:^|\s)([\w.\-/\\]+\.(?:py|ts|js|rs|go|cs|gd|cpp|c|h|json|yaml|yml|toml|md|tscn|unity|log|txt))\b',
        user_input
    )
    raw_path = (file_match.group(1) or file_match.group(2)).strip() if file_match else None
    file_path = str(_Path(raw_path).resolve()) if raw_path and _Path(raw_path).exists() else raw_path
    file_content = None

    if file_path:
        try:
            file_content = _Path(file_path).read_text(encoding="utf-8", errors="replace")
            print(f"[pre-load] Loaded {file_path} ({len(file_content)} chars)")
        except Exception as e:
            print(f"[pre-load] Could not load file: {e}")

    # For non-review tasks — pre-load file into prompt if small enough
    if task == "scaffold":
        file_content = None
    enriched_input = user_input
    if file_content and len(file_content) < 6000:
        enriched_input = (
            f"{user_input}\n\n"
            f"--- EXISTING FILE CONTENTS: {file_path} ---\n"
            f"{file_content}\n"
            f"--- END FILE ---\n\n"
            f"The existing file content is provided above. "
            f"Write the complete updated code and call write_file_dry with 'path' and 'content'."
        )
    elif file_content:
        # File too large for prompt — tell agent to use the tool
        enriched_input = (
            f"{user_input}\n\n"
            f"The file at {file_path} is {len(file_content)} chars. "
            f"Use read_file to load it, then edit or validate."
        )

    tools = [t for t in profile["tool_whitelist"] if not t.startswith("write_")] if task in ("explain", "review") else profile["tool_whitelist"]

    result = run_agent(
        session_id=session_id,
        system_prompt=profile["system_prompt"],
        task=enriched_input,
        agent_name=profile["name"],
        tool_whitelist=tools,
        grammar_path=profile.get("grammar_path"),
    )

    print(f"\n[result] ok={result['ok']} steps={result['steps']}")
    print(f"\n{result['result']}")


def main() -> None:
    if len(sys.argv) > 1:
        run_task(" ".join(sys.argv[1:]))
    else:
        print("Game-Dev Agent Team — Interactive Mode")
        print("Type 'quit' to exit.\n")
        while True:
            try:
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if user_input.lower() in ("quit", "exit", "q"):
                break
            if user_input:
                run_task(user_input)


if __name__ == "__main__":
    main()
