# Agent Team — Workspace Guidelines & Architecture

## Overview
This repository implements **BUS3F-TUI**: a 100% offline, air-gapped local multi-agent coding harness and interactive curses TUI (`cli.py`, installed globally as `bus3f-tui`) along with a headless task runner (`main.py`).

It runs entirely against a local `llama-server` (OpenAI-compatible HTTP endpoint at `http://localhost:8080/v1/chat/completions` or configured via `LLM_URL`) powering local GGUF models with zero telemetry, zero analytics, and zero external network calls.

---

## Core Pillars & Invariants

1. **Air-Gapped & Offline**: Zero telemetry or cloud dependencies. All inferences, embeddings, and completions execute locally.
2. **Multi-Agent Orchestration**: Dual execution modes (`/mode parallel|sequential`) supporting single-agent routing and multi-agent teams (`/team [agents] <task>`) with GBNF grammar-constrained outputs (`grammars/router.gbnf`).
3. **Process-Isolated Sandbox**: Native C grammars and Tree-sitter AST lexers execute in an isolated child process via `multiprocessing.Pipe` with a 500ms watchdog timeout and automatic restart on crashes (`SIGSEGV`) or runaway loops.
4. **Full Local Persistence**: Checkpoints, execution traces, multi-turn chat sessions, and project context persist locally to SQLite (`~/agent_team/traces.db`) and markdown (`MEMORY.md`).
5. **CWD Auto-Detection**: Dynamic project root and engine auto-detection from the working directory (`Path.cwd()`) without requiring hardcoded configuration paths.

---

## Architecture & Directory Layout

- `cli.py` (`bus3f-tui`): Interactive curses TUI built on `prompt_toolkit`:
  - Multi-line editing (`Alt+Enter` / `Ctrl+J`) and live arrow history navigation.
  - Live tab-completion popup for `/`-commands, session IDs, and models.
  - Process-isolated Tree-sitter semantic lexing and Monokai syntax highlighting.
  - Session lifecycle management (`/sessions`, `/new`, `/resume`, `/branch`, `/delete`).
  - Concurrent multi-agent execution (`/team`) and mode toggles (`/mode`).
  - GGUF model manager (`/models`, `/model switch`, `/new-model`, `/search-model`).
  - Custom agent wizard (`/new-agent`) and tool plugin manager (`plugin install`).
  - Project memory scraper (`init`, `remember`, `memory`).
- `main.py`: Headless command-line task runner supporting absolute, relative, and quoted filepaths.
- `setup.sh`: Universal package installer auto-detecting Arch Linux (`pacman` + PEP 668), Debian/Ubuntu (`apt`), and Fedora (`dnf`). Compiles `llama.cpp` and creates `~/.local/bin/bus3f-tui`.
- `harness/`:
  - `router.py`: Dual-stage task classification (deterministic regex pre-filter + absolute-resolved GBNF grammar-constrained LLM fallback).
  - `loop.py`: Bounded ReAct loop (`MAX_STEPS = 8`, `TIME_BUDGET_SEC = 600`), checkpointing, tool dispatching, sliding context window, and human approval gating.
  - `db.py`: SQLite session, trace, and checkpoint persistence at `~/agent_team/traces.db`.
- `agents/`:
  - `profiles.py`: Universal agent profiles (`coder`, `reviewer`, `debugger`, `general`), system prompts, tool whitelists, and dynamic custom agent loader (`~/agent_team/custom_agents/*.json`).
- `tools/`:
  - `gamedev_tools.py`: Path-safe file operations (`read_file`, `write_file_dry`), directory listing (`list_dir`), and log greppers (`grep_file`, `read_log`, `grep_error`).
- `grammars/`:
  - `router.gbnf`: Strict JSON grammar enforcing role and task classification.
- `scripts/`:
  - `launch_server.sh`: Bash launcher for `llama-server` with dynamic core detection, CUDA offload, and multi-slot inference (`-np 2`).

---

## Strict Engine Invariants

### 1. Godot 3.5 (GDScript)
- **Indentation**: Tabs only (4-wide tabs). Never spaces.
- **Variables**: `export var` and `onready var`. Never `@export` or `@onready`.
- **Coroutines**: `yield(signal, "timeout")`. Never `await`.
- **Signals**: `connect("signal_name", self, "_method")`. Never `signal.connect()`.
- **Typing**: No parameter or return type hints (`func foo(bar):` not `func foo(bar: int) -> void:`).
- **Classes**: No `class_name` keyword. Use `const MyClass = preload("res://...")`.
- **Physics**: `KinematicBody2D`, `move_and_slide(velocity, Vector2.UP)` (velocity passed as argument).
- **APIs**: `OS.get_ticks_msec()` (not `Time`), `rand_range()` (not `randf_range()`).

### 2. Unity 2018.2 (C#)
- **Input System**: Classic `Input.GetAxis()`, `Input.GetKey()`. Never `UnityEngine.InputSystem`.
- **Formatting**: Allman brace style (opening braces on a new line). PascalCase methods, camelCase fields.
- **Serialization**: `[SerializeField] private` for Inspector-visible fields.
- **Async/Await**: Not supported; use `IEnumerator` coroutines.
- **Serialization**: `JsonUtility.FromJson<T>()`. Never `System.Text.Json`.
- **2D Collisions**: Parameters required: `void OnCollisionEnter2D(Collision2D other)`.
- **Object Resolution**: `FindObjectsOfType<T>()` (not `FindObjectsByType`).

---

## Safety & Tool Conventions

1. **Dry-Run & Approval**: Any file-modifying tools (`write_file_dry`) must default to `commit=False` and require explicit user approval before disk writes.
2. **Path Containment**: All file operations must pass through `_safe_path()`, strictly constrained to `$HOME`, `/tmp`, `/mnt/` (WSL mounts), `/media/`, and `/run/media/` (Linux removable media mounts).
3. **Database Consistency**: SQLite traces must always write to and query `~/agent_team/traces.db`.
4. **Offline Integrity**: Code changes must never introduce external cloud SDKs, unauthorized network calls, or phone-home telemetry.
