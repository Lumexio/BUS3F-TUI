# Agent Team — Local Game-Dev AI Agent Team & Interactive TUI

A fully local multi-agent harness and interactive CLI AI experience for game development workflows: automated code edits, AST-level API reviews, bug fixing, architecture explanations, and Godot 3.5 to Unity 2018.2 migrations.

Powered by a local `llama-server` (OpenAI-compatible HTTP endpoint at `http://localhost:8080/v1/chat/completions`) running GGUF models (e.g. `Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf`).

---

## Key Features

### 1. Interactive Curses TUI (`cli.py`)
- **Multi-line Navigation**: Built on `prompt_toolkit` with full curses arrow navigation, history scrolling, and newline insertion via `Alt+Enter` or `Ctrl+J`.
- **Live Tab Completion**: Dynamic command auto-completion popup for `/`-commands, session IDs, installed models, and scanner targets.
- **Live Syntax Highlighting**: Pygments-powered token coloring (Monokai theme) for C# and GDScript input buffers.

### 2. Isolated Tree-sitter Semantic Lexing
- **AST Semantic Highlighting**: C-level AST node extraction coloring variables, parameters, types, methods, keywords, strings, and comments.
- **Incremental AST Diff Re-parsing**: Sub-millisecond re-parsing on multi-thousand-line input blocks using common prefix/suffix byte diffing and `tree.edit()`.
- **Debounced Asynchronous Worker**: Keystrokes debounced (40ms) and offloaded from the UI loop to a background thread to prevent UI frame drops.
- **Process Sandbox & Crash Isolation**: Native C grammars run in an isolated child process via `multiprocessing.Pipe`. Includes a 500ms watchdog timeout and auto-restart on segmentation faults (`SIGSEGV`) or runaway loops. Configure custom grammars with `/grammar <module>`.

### 3. Multi-Turn Session Subsystem
- **SQLite Persistence**: All sessions, execution traces, and ReAct checkpoints stored in `~/agent_team/traces.db`.
- **Session Management**: Full lifecycle support with `/sessions` (list), `/new <name>` (create), `/resume <id>` (resume), `/branch <name>` (branch), and `/delete <id>` (delete).
- **Turn Context Continuity**: Conversation history is preserved across turns and loaded upon session resumption.

### 4. Parallel & Sequential Multi-Agent Execution
- **Execution Mode Toggle**: Switch between `/mode parallel` and `/mode sequential`.
- **Concurrent Execution**: Run multi-agent teams simultaneously (`/team <agents> <task>`) via `ThreadPoolExecutor` and multi-slot inference (`-np 2` in `scripts/launch_server.sh`).

### 5. Local Model & Plugin Management
- **Local GGUF Models**: Manage models in `~/models` with `/models` and `/model switch <name>`.
- **HuggingFace Scraping**: Search HuggingFace directly from the CLI via `/search-model <query>` and download with automatic quantization selection.
- **Custom Agents & Plugins**: Create new specialist agents interactively (`/new-agent`) or load git plugins (`plugin install <url>`).

### 6. Engine Invariant Enforcement & Migration
- **Godot 3.5 GDScript**: Enforces 4-wide tabs, `export var`, `onready var`, `yield()`, `connect()`, `KinematicBody2D`, and pre-Godot-4 APIs.
- **Unity 2018.2 C#**: Enforces Allman brace style, `[SerializeField] private`, classic `Input`, coroutines, and Unity 2018.2 API constraints.
- **Static API Scanners**: Zero-token instant rule checks via `scan godot` or `scan unity`.
- **Migration Wizard**: Automated step-by-step conversion of Godot scripts to Unity C# with `migrate`.

---

## Directory Layout

```
├── cli.py                 # Interactive TUI terminal application
├── main.py                # Headless command-line task runner
├── setup.sh               # Environment setup & venv installer
├── AGENTS.md              # Strict workspace engine invariants & rules
├── README.md              # Project documentation & feature guide
├── harness/
│   ├── router.py          # Deterministic regex pre-filter + LLM fallback
│   ├── loop.py            # Bounded ReAct loop (MAX_STEPS, checkpoints, tools)
│   └── db.py              # SQLite session & trace persistence (traces.db)
├── agents/
│   └── profiles.py        # Profiles (godot, unity, asset, build, general)
├── tools/
│   └── gamedev_tools.py   # Path-safe tools, dry-run writes, API validators
├── grammars/
│   └── router.gbnf        # GBNF grammar enforcing strict JSON router output
└── scripts/
    └── launch_server.sh   # llama-server launcher with CUDA & multi-slot (-np 2)
```

---

## Quickstart

### 1. Setup & Installation
```bash
bash setup.sh
```

### 2. Launch Local LLM Server
```bash
bash scripts/launch_server.sh &
```

### 3. Start the Interactive CLI
```bash
python3 cli.py
# Or use the global command created by setup.sh:
bus3f-tui
```

---

## Command Reference

| Command | Description |
| :--- | :--- |
| `/help` or `help` | Show built-in commands and usage |
| `/sessions` | List all chat sessions and history turns |
| `/new [name]` | Start a new clean chat session |
| `/resume <id>` | Resume a previous chat session |
| `/branch [name]` | Branch conversation from the active session |
| `/delete <id>` | Delete a session and its trace history |
| `/mode [parallel\|sequential]` | Toggle concurrent vs pipeline agent execution |
| `/team [agents] <task>` | Run multi-agent team task |
| `/grammar [module\|reset]` | Set isolated Tree-sitter grammar plugin |
| `/models` | List installed GGUF models in `~/models` |
| `/new-model [url]` | Download and install a GGUF model |
| `/search-model <query>` | Search HuggingFace for GGUFs and install |
| `/agents` | List built-in and custom specialist agents |
| `/new-agent` | Interactive wizard to create a new agent |
| `/ponytail` | Toggle lazy developer mode (minimal diffs, zero bloat) |
| `init` | Scrape active project into `MEMORY.md` |
| `project [path]` | View or set active project directory |
| `remember <note>` | Append a note to project `MEMORY.md` |
| `memory` | Display current project `MEMORY.md` |
| `scan [godot\|unity]` | Scan scripts for version violations |
| `migrate` | Run Godot-to-Unity migration wizard |
| `status` | Check local `llama-server` connection status |
| `history` | Display recent session traces from SQLite |
| `clear` | Clear terminal screen and redraw banner |
| `quit` | Exit the CLI |
