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
    init_db()

    print(f"\n[task] {user_input}")

    # Route
    route_result = route(user_input)
    engine = route_result["engine"]
    task = route_result["task"]
    print(f"[router] engine={engine} task={task} method={route_result['method']} ({route_result['elapsed_ms']}ms)")

    # Select agent
    agent_key = engine if engine in AGENT_PROFILES else "general"
    if agent_key == "general":
        print("[dispatch] No specialized agent for 'general' — answering directly.")
        print("[note] Add a general-purpose agent profile or escalate to human.")
        return

    profile = AGENT_PROFILES[agent_key]
    session_id = route_result["session_id"]

    print(f"[dispatch] → {profile['name']}")

    result = run_agent(
        session_id=session_id,
        system_prompt=profile["system_prompt"],
        task=user_input,
        agent_name=profile["name"],
        tool_whitelist=profile["tool_whitelist"],
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
