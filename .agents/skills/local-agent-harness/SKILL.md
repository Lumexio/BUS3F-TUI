---
name: local-agent-harness
description: >-
  Run, test, maintain, and extend the local game-dev multi-agent team harness
  (cli.py, main.py, llama-server, profiles, isolated sandbox, and safety tools).
---

# Local Agent Harness Runbook

Use this skill when running, troubleshooting, testing, or extending the local multi-agent harness in `agent_team`.

## 1. Starting the llama-server

The local agents depend on `llama-server` listening on port 8080:

```bash
# Launch server with dynamic nproc threading, KV cache optimization, and multi-slot execution (-np 2)
bash ~/agent_team/scripts/launch_server.sh &

# Or launch with small 3B fallback model
bash ~/agent_team/scripts/launch_server.sh --small &

# Check server health
curl -s http://localhost:8080/health
```

*Environment Overrides:*
- `LLAMA_THREADS`: Force CPU threads (default: auto-detected via `nproc`).
- `LLAMA_PORT`: Server port (default: `8080`).
- `LLM_URL`: Custom endpoint (default: `http://localhost:8080/v1/chat/completions`).

## 2. Using the Interactive Curses TUI (`bus3f-tui` / `cli.py`)

Run the interactive terminal interface:
```bash
bus3f-tui
# Or from source:
python3 cli.py
```

### Core Commands
- **Sessions**: `/sessions` (list), `/new [name]`, `/resume <id>`, `/branch [name]`, `/delete <id>`.
- **Multi-Agent**: `/mode [parallel|sequential]`, `/team [agents] <task>`.
- **Grammar & Lexer**: `/grammar [module|reset]` (isolated C child process).
- **Model Management**: `/models`, `/model switch <name>`, `/new-model [url]`, `/search-model <query>`.
- **Agents & Plugins**: `/agents`, `/new-agent`, `plugin install <url_or_path>`, `plugins`.
- **Project Context**: `init` (scrape `MEMORY.md`), `project [path]`, `remember <note>`, `memory`.
- **Engine Scanners**: `scan` (auto-detect), `scan godot`, `scan unity`, `migrate`.

## 3. Headless Task Execution (`main.py`)

Run tasks directly without entering interactive mode:
```bash
python3 main.py "review scripts/Player.gd"
python3 main.py "scaffold a 2D kinematic player controller in GDScript"
python3 main.py "explain how FlockManager.gd works"
```

## 4. Architecture & Sandboxing Invariants

1. **Air-Gapped Invariant**: No telemetry or external network calls.
2. **Process-Isolated Sandbox**: Tree-sitter AST lexing runs in an isolated worker process via `multiprocessing.Pipe` with a 500ms watchdog timeout and automatic restart on crash (`SIGSEGV`).
3. **Path Safety**: File operations must pass through `_safe_path()`, strictly constrained to `$HOME`, `/tmp`, `/mnt/`, `/media/`, and `/run/media/`.
4. **Dry-Run Writes**: Modifying tools (`write_gd_dry`, `write_cs_dry`) default to `commit=False` and require user confirmation.
5. **Persistence**: Traces and checkpoints persist to `~/agent_team/traces.db`.

## 5. Adding New Agents or Tools

1. **New Tools**: Implement in `tools/gamedev_tools.py` using `_safe_path()`, dry-run approval, and register in `TOOL_REGISTRY` in `harness/loop.py`.
2. **New Agent Profile**: Add configuration to `AGENT_PROFILES` in `agents/profiles.py` specifying `name`, `system_prompt`, and `tool_whitelist`, or use `/new-agent`.
3. **Router Update**: Update `SYSTEM_PROMPT_ROUTER` in `harness/router.py` and grammar in `grammars/router.gbnf`.
