# Agent Team — Workspace Guidelines & Architecture

## Overview
This repository implements a local multi-agent harness powering an interactive CLI AI experience (`cli.py`) and task runner (`main.py`) for game development workflows: code edits, API reviews, bug fixes, architecture explanations, and Godot-to-Unity migrations.

It connects to a local `llama-server` (OpenAI-compatible endpoint at `http://localhost:8080/v1/chat/completions`) typically running `Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf`.

---

## Architecture & Directory Layout

- `cli.py`: Interactive user CLI with live execution styling, spinner, history, fast API scanner, and migration wizard.
- `main.py`: Headless and direct invocation entry point with query file-path extraction and direct validator bypass for review tasks.
- `harness/`:
  - `router.py`: Dual-stage task classification (fast deterministic regex pre-filter + GBNF-constrained LLM fallback).
  - `loop.py`: Bounded ReAct loop (`MAX_STEPS = 8`, `TIME_BUDGET_SEC = 120`), checkpointing, tool dispatching, and human approval gating.
  - `db.py`: SQLite session, trace, and checkpoint persistence at `~/agent_team/traces.db`.
- `agents/`:
  - `profiles.py`: Agent profile definitions (`godot`, `unity`, `asset`, `build`, `general`), system prompts, and tool whitelists.
- `tools/`:
  - `gamedev_tools.py`: Path-safe file operations, dry-run write tools, AST/regex API validators, scene parsers (`.tscn`, `.unity`), and build log greppers.
- `grammars/`:
  - `router.gbnf`: Grammar enforcing strict JSON output for router classification.
- `scripts/`:
  - `launch_server.sh`: Bash launcher for `llama-server` with CUDA offload and KV cache optimization.

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

1. **Dry-Run & Approval**: Any file-modifying tools (`write_gd_dry`, `write_cs_dry`) must default to `commit=False` and require explicit user approval before disk writes.
2. **Path Containment**: All file operations must pass through `_safe_path()`, strictly constrained to `$HOME`, `/tmp`, and `/mnt/` (WSL Windows filesystem mounts).
3. **Database Consistency**: SQLite traces must always write to and query `~/agent_team/traces.db`.
