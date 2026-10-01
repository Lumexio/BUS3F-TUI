# Agent Team — Workspace Guidelines & Architecture

## Overview
This repository implements **BUS3F-TUI**: a 100% offline, air-gapped universal multi-agent coding harness and interactive curses TUI (`cli.py`, installed globally as `bus3f-tui`) along with a headless task runner (`main.py`).

It runs entirely against a local `llama-server` (OpenAI-compatible HTTP endpoint at `http://localhost:8080/v1/chat/completions` or configured via `LLM_URL`) powering local GGUF models with zero telemetry, zero analytics, and zero external network calls.

---

## Core Pillars & Invariants

1. **Air-Gapped & Offline**: Zero telemetry or cloud dependencies. All inferences, embeddings, and completions execute locally.
2. **Multi-Agent Orchestration**: Dual execution modes (`/mode parallel|sequential`) supporting single-agent routing and dynamic multi-agent teams (`/team [agents] <task>`) with GBNF grammar-constrained outputs (`grammars/router.gbnf`).
3. **Process-Isolated Sandbox**: Native C grammars and Tree-sitter AST lexers execute in an isolated child process via `multiprocessing.Pipe` with a 500ms watchdog timeout and automatic restart on crashes (`SIGSEGV`) or runaway loops.
4. **Dynamic Tokens & Infinite Turns**: LLM requests use native dynamic generation (`max_tokens: -1`) with a 16k context window (`-c 16384 -np 2` -> 8,192 tokens/slot). A rolling sliding window (`[anchor] + last 4 turns`) prevents context saturation across endless sessions.
5. **Full Local Persistence**: Checkpoints, execution traces, multi-turn chat sessions, and project context persist locally to SQLite (`~/agent_team/traces.db`) and markdown (`MEMORY.md`).
6. **CWD Auto-Detection**: Dynamic project root auto-detection from working directory (`Path.cwd()`) without requiring hardcoded configuration paths.

---

## Architecture & Directory Layout

- `cli.py` (`bus3f-tui`): Interactive curses TUI built on `prompt_toolkit`:
  - Multi-line editing (`Alt+Enter` / `Ctrl+J`) and live arrow history navigation.
  - Live tab-completion popup for `/`-commands, session IDs, and models.
  - Process-isolated Tree-sitter semantic lexing and Monokai code block syntax highlighting.
  - Out-of-the-box model enforcement: auto-prompts `/new-model` if `~/models` is empty.
  - Live server context upgrade: auto-detects and upgrades `llama-server` context (<4096 → 8192).
  - Session lifecycle management (`/sessions`, `/new`, `/resume`, `/branch`, `/delete`).
  - Concurrent multi-agent execution (`/team`) and mode toggles (`/mode`).
  - Model manager (`/models`, `/model switch`, `/new-model`, `/search-model`, `/restart`).
  - Custom agent wizard (`/new-agent`) and tool plugin manager (`plugins`, `plugin install`).
  - Project memory scraper (`init`, `remember`, `memory`).
- `main.py`: Headless command-line task runner supporting absolute, relative, and quoted filepaths.
- `setup.sh`: Universal package installer auto-detecting Arch Linux (`pacman` + PEP 668), Debian/Ubuntu (`apt`), and Fedora (`dnf`). Compiles `llama.cpp` and creates `~/.local/bin/bus3f-tui` and Windows launcher.
- `harness/`:
  - `router.py`: Dual-stage task classification (deterministic regex pre-filter + absolute-resolved GBNF grammar-constrained LLM fallback).
  - `loop.py`: Bounded ReAct loop (`MAX_STEPS = 8`, `TIME_BUDGET_SEC = 600`), dynamic token generation (`max_tokens: -1`), multiline parsing, checkpointing, tool dispatching, sliding context window, and human approval gating.
  - `db.py`: SQLite session, trace, and checkpoint persistence at `~/agent_team/traces.db`.
- `agents/`:
  - `profiles.py`: Universal agent profiles (`code-specialist`, `code-reviewer`, `build-doctor`, `general-agent`), system prompts, tool whitelists, and dynamic custom agent loader (`~/agent_team/custom_agents/*.json`).
- `tools/`:
  - `gamedev_tools.py`: Path-safe file operations (`read_file`, `write_file_dry`), directory listing (`list_dir`), and log greppers (`grep_file`, `read_log`, `grep_error`).
- `grammars/`:
  - `router.gbnf`: Strict JSON grammar enforcing role and task classification.
- `scripts/`:
  - `launch_server.sh`: Bash launcher for `llama-server` with dynamic core detection, CUDA offload (`-ngl 99`), 16k context (`-c 16384`), and multi-slot inference (`-np 2`).

---

## Agent Profiles

| Profile | Role Name | Primary Focus | Default Tools |
|---|---|---|---|
| `coder` | `code-specialist` | Multi-language code implementation & refactoring | `read_file`, `write_file_dry`, `list_dir`, `grep_file` |
| `reviewer` | `code-reviewer` | Static analysis, bug auditing, security & performance | `read_file`, `list_dir`, `grep_file` |
| `debugger` | `build-doctor` | Root-cause crash/error diagnosis & minimal fixes | `read_file`, `read_log`, `grep_error`, `grep_file`, `write_file_dry` |
| `general` | `general-agent` | Architectural planning, technical Q&A, conversational | `read_file`, `list_dir`, `grep_file`, `write_file_dry` |
| *custom* | User-defined | Configured via `/new-agent` (`~/agent_team/custom_agents/*.json`) | Configurable |

---

## Interactive TUI Commands (`bus3f-tui`)

| Command | Action |
|---|---|
| `/help`, `help` | Show command reference and usage |
| `/sessions` | List saved chat sessions from SQLite |
| `/new [name]` | Create and switch to a fresh chat session |
| `/resume [id]` | Resume an existing conversation session |
| `/branch [name]` | Branch current session history into a new session |
| `/delete [id]` | Delete session history and checkpoints |
| `/mode [parallel\|sequential]` | Toggle multi-agent execution strategy |
| `/team <agents> <task>` | Run multi-agent collaboration on a task |
| `/models` | List installed GGUF models in `~/models` |
| `/select-model [name\|num]` | Interactively select or switch active GGUF model |
| `/model switch <name\|num>` | Hot-swap active model in `llama-server` |
| `/new-model [alias_or_url]` | Download and install GGUF model |
| `/search-model [query]` | Search HuggingFace for GGUF models & install |
| `/restart` | Hot-restart `llama-server` service |
| `/agents` | List active agent profiles and custom agents |
| `/new-agent` | Interactive wizard to define a custom specialist |
| `/ponytail` | Toggle Ponytail mode (simplest diff, minimal code) |
| `/grammar <module\|reset>` | Switch isolated Tree-sitter grammar plugin |
| `project [path]` | View or change active target project root |
| `init` | Scrape project scripts and generate `MEMORY.md` |
| `remember <note>` | Append note to active project `MEMORY.md` |
| `memory` | Display contents of `MEMORY.md` |
| `plugins`, `plugin install` | Manage tool plugins and skill modules |
| `status` | Check local `llama-server` health & connectivity |
| `history` | View execution trace history from `traces.db` |
| `clear`, `quit` | Clear screen / exit TUI |

---

## Universal Coding Invariants

1. **Language & Framework Agnostic**: Clean, idiomatic implementation conforming to the target codebase's existing conventions, style, and type system (Python, Rust, TypeScript, Go, C#, C/C++, Bash, etc.).
2. **YAGNI & Zero Bloat**: Minimal code required to solve the task. Standard library and native language features before external dependencies.
3. **No Speculative Abstractions**: No unrequested interfaces, premature factories, or unused boilerplate scaffolding "for later".
4. **Complete Working Implementations**: Output fully functional code with all edge cases and error bounds handled. Never truncate, stub, or leave placeholder comments.

---

## Safety & Tool Conventions

1. **Dry-Run & Approval**: Any file-modifying tools (`write_file_dry`) must default to `commit=False` and require explicit user approval before disk writes.
2. **Path Containment**: All file operations must pass through `_safe_path()`, strictly constrained to `$HOME`, `/tmp`, `/mnt/` (WSL mounts), `/media/`, and `/run/media/` (Linux removable media mounts).
3. **Database Consistency**: SQLite traces must always write to and query `~/agent_team/traces.db`.
4. **Offline Integrity**: Code changes must never introduce external cloud SDKs, unauthorized network calls, or phone-home telemetry.
