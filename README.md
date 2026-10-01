# BUS3F-TUI — 100% Offline, Air-Gapped Local Multi-Agent Coding Harness

An off-the-grid, privacy-first local multi-agent harness and interactive curses TUI (`bus3f-tui`) for software engineering and game development workflows: automated code edits, AST-level API reviews, bug fixes, architecture explanations, and Godot 3.5 to Unity 2018.2 migrations.

---

## Core Pillars

1. **Zero Telemetry & External APIs**: 100% local inference against GGUF models via `llama-server`. No telemetry, analytics, tracking, or cloud dependencies.
2. **Multi-Agent Execution**: Sequential and concurrent ReAct teams (`/mode parallel|sequential` and `/team`) with strict GBNF grammar-constrained routing (`router.gbnf`).
3. **Process-Isolated Sandbox**: Native C Tree-sitter semantic lexers and custom grammar plugins run in a separate child process via `multiprocessing.Pipe` with a 500ms watchdog timeout and crash recovery.
4. **Full Local Persistence**: Checkpoints, execution traces, sessions, and project memory stored strictly on-disk via SQLite (`~/agent_team/traces.db`) and markdown (`MEMORY.md`).
5. **Zero-Configuration Auto-Detection**: Automatically detects active projects and engines (Godot 3.5 or Unity 2018.2) directly from the current working directory (`Path.cwd()`).

---

## Architecture & Directory Layout

```
├── cli.py                 # Interactive curses TUI application (bus3f-tui)
├── main.py                # Headless command-line task runner
├── setup.sh               # Universal installer (Arch, Debian/Ubuntu, Fedora)
├── AGENTS.md              # Strict engine invariants & coding standards
├── README.md              # Project documentation & reference manual
├── harness/
│   ├── router.py          # Deterministic regex pre-filter + GBNF LLM fallback
│   ├── loop.py            # Bounded ReAct loop (MAX_STEPS, checkpoints, tools)
│   └── db.py              # SQLite session & trace persistence (traces.db)
├── agents/
│   └── profiles.py        # Profiles (godot, unity, asset, build, general)
├── tools/
│   └── gamedev_tools.py   # Path-safe tools, dry-run writes, API validators
├── grammars/
│   └── router.gbnf        # GBNF grammar enforcing strict JSON router output
└── scripts/
    └── launch_server.sh   # llama-server launcher with CUDA, nproc threading & multi-slot
```

---

## Quickstart

### 1. Installation
The installer auto-detects distribution package managers (Arch `pacman`, Debian/Ubuntu `apt`, Fedora `dnf`), configures a PEP 668-safe venv, compiles `llama.cpp` (with CUDA offload if `nvcc` is present), and installs the global `bus3f-tui` command into `~/.local/bin`:

```bash
bash setup.sh
source ~/.bashrc
```

### 2. Start Local LLM Server
Launches `llama-server` with dynamic core detection (`nproc`), KV cache optimization (`q8_0`), and multi-slot execution (`-np 2`):

```bash
bash scripts/launch_server.sh &
```

*Optional Environment Overrides:*
- `LLAMA_THREADS`: Force CPU thread count (default: auto-detected via `nproc`).
- `LLAMA_PORT`: Server port (default: `8080`).
- `LLM_URL`: Custom OpenAI-compatible endpoint (default: `http://localhost:8080/v1/chat/completions`).

### 3. Launch Interactive TUI
Navigate to any project directory and launch:

```bash
cd /path/to/your/project
bus3f-tui
```
*Prompt dynamically auto-detects the engine:*  
`[my_project · godot · sequential · s-624b28aa · ponytail] >`

### 4. Headless Single-Task Execution (`main.py`)
Run tasks directly without entering interactive mode:

```bash
python3 main.py "review scripts/Player.gd"
python3 main.py "scaffold a 2D kinematic player controller in GDScript"
```

---

## Key Features

### 1. Interactive Curses TUI (`cli.py`)
- **Multi-line Navigation**: Built on `prompt_toolkit` with arrow navigation, history scrolling, and newline insertion via `Alt+Enter` or `Ctrl+J`.
- **Live Tab Completion**: Dynamic command auto-completion popup for `/`-commands, session IDs, installed models, and scanner targets.
- **Syntax Highlighting**: Pygments token coloring (Monokai theme) for C# and GDScript buffers.

### 2. Isolated Tree-sitter Semantic Lexing
- **AST Semantic Coloring**: Native C AST node extraction coloring variables, parameters, types, methods, keywords, strings, and comments.
- **Incremental AST Diff Re-parsing**: Sub-millisecond re-parsing on multi-thousand line files via prefix/suffix byte diffing and `tree.edit()`.
- **Debounced Asynchronous Worker**: Keystrokes debounced (40ms) and offloaded to a background thread to prevent UI frame drops.
- **Crash & Loop Isolation**: Grammars execute in a child process via `multiprocessing.Pipe` with watchdog timeout and auto-restart on segmentation faults.

### 3. Multi-Turn Session Subsystem
- **SQLite Persistence**: Sessions, traces, and checkpoints stored in `~/agent_team/traces.db`.
- **Session Management**: Full lifecycle support with `/sessions`, `/new [name]`, `/resume <id>`, `/branch [name]`, and `/delete <id>`.
- **Turn Context Continuity**: Conversation history is preserved across turns and reloaded on resumption.

### 4. Parallel & Sequential Multi-Agent Execution
- **Execution Mode Toggle**: Switch between `/mode parallel` and `/mode sequential`.
- **Concurrent Execution**: Run multi-agent teams simultaneously (`/team [agents] <task>`) via `ThreadPoolExecutor` and multi-slot inference (`-np 2`).

### 5. Local Model & Plugin Management
- **Local GGUF Models**: Manage models in `~/models` with `/models` and `/model switch <name>`.
- **HuggingFace Scraping**: Search HuggingFace directly from the CLI via `/search-model <query>` and download with automatic quantization selection.
- **Custom Agents & Plugins**: Create new specialist agents interactively (`/new-agent`) or load git plugins (`plugin install <url>`).

### 6. Engine Invariant Enforcement & Migration
- **Godot 3.5 GDScript**: Enforces 4-wide tabs, `export var`, `onready var`, `yield()`, `connect()`, `KinematicBody2D`, and pre-Godot-4 APIs.
- **Unity 2018.2 C#**: Enforces Allman brace style, `[SerializeField] private`, classic `Input`, coroutines, and Unity 2018.2 API constraints.
- **Static API Scanners**: Zero-token instant rule checks via `scan`, `scan godot`, or `scan unity`.
- **Migration Wizard**: Automated step-by-step conversion of Godot scripts to Unity C# with `migrate`.

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
