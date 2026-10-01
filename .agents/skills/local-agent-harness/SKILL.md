---
name: local-agent-harness
description: >-
  Run, test, maintain, and extend the local game-dev multi-agent team harness
  (cli.py, main.py, llama-server, profiles, and safety tools).
---

# Local Agent Harness Runbook

Use this skill when running, troubleshooting, testing, or extending the local multi-agent harness in `agent_team`.

## 1. Starting the llama-server

The local agents depend on `llama-server` listening on port 8080:

```bash
# Launch server with default 7B Qwen2.5-Coder model
bash ~/agent_team/scripts/launch_server.sh &

# Or launch with small 3B fallback model
bash ~/agent_team/scripts/launch_server.sh --small &

# Check server health
curl -s http://localhost:8080/health
```

## 2. Using the CLI (`cli.py`)

Run the interactive terminal interface:
```bash
python3 cli.py
```

Built-in commands within `cli.py`:
- `status`: Check if `llama-server` is reachable on `:8080`.
- `scan godot`: Scans GDScript files for Godot 4 incompatibilities.
- `scan unity`: Scans C# files for Unity 2019+ incompatibilities.
- `migrate`: Runs the file-by-file Godot 3.5 to Unity 2018.2 migration wizard.
- `history`: Shows the last 15 executed sessions from `traces.db`.

## 3. Direct Task Execution (`main.py`)

Run ad-hoc tasks directly:
```bash
python3 main.py "review scripts/player.gd for Godot 3.5 issues"
python3 main.py "explain how FlockManager.gd works"
python3 main.py "fix the enemy AI in scripts/entities/Enemy.gd"
```

## 4. Traces and Checkpoints

All sessions, tool calls, token usage, and ReAct steps are persisted to:
- SQLite Database: `~/agent_team/traces.db`
- Inspecting recent traces:
  ```bash
  sqlite3 ~/agent_team/traces.db "SELECT agent, action, tool_name, elapsed_ms FROM traces ORDER BY id DESC LIMIT 20;"
  ```

## 5. Adding New Agents or Tools

1. **New Tools**: Implement in `tools/gamedev_tools.py` using `_safe_path()` and register in `TOOL_REGISTRY` in `harness/loop.py`.
2. **New Agent Profile**: Add configuration to `AGENT_PROFILES` in `agents/profiles.py` specifying `name`, `system_prompt`, and `tool_whitelist`.
3. **Router Update**: If adding an engine or task type, update `SYSTEM_PROMPT_ROUTER` in `harness/router.py` and the grammar in `grammars/router.gbnf`.
