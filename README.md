# BUS3F-TUI — 100% Offline, Air-Gapped Local Multi-Agent Coding Harness

An off-the-grid, privacy-first local multi-agent harness and interactive curses TUI (`bus3f-tui`) for software engineering: automated code creation and edits across any language or stack, on-the-fly multi-developer team synthesis, AST reviews, bug fixing, architecture explanations, and decoupled engine specializations.

---

## Core Pillars

1. **Zero Telemetry & External APIs**: 100% local inference against GGUF models via `llama-server`. No telemetry, analytics, tracking, or cloud dependencies.
2. **Dynamic Team Synthesis**: Given an open-ended project goal (e.g. full-stack SaaS with React frontend and FastAPI backend), the harness dynamically purposes a team of developer specialists (frontend, backend, QA, devops) on the fly, running in sequential pipeline or concurrent modes (`/mode parallel|sequential` and `/team`).
3. **Process-Isolated Sandbox**: Native C Tree-sitter semantic lexers and custom grammar plugins run in a separate child process via `multiprocessing.Pipe` with a 500ms watchdog timeout and crash recovery.
4. **Full Local Persistence**: Checkpoints, execution traces, sessions, and project memory stored strictly on-disk via SQLite (`~/agent_team/traces.db`) and markdown (`MEMORY.md`).
5. **Zero-Configuration Auto-Detection**: Automatically detects active projects and codebases directly from the current working directory (`Path.cwd()`).

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
│   └── profiles.py        # Universal profiles (coder, reviewer, debugger, general) & custom loader
├── tools/
│   └── gamedev_tools.py   # Path-safe file operations, dry-run writes, log greppers
├── grammars/
│   └── router.gbnf        # GBNF grammar enforcing strict JSON router output
└── scripts/
    └── launch_server.sh   # llama-server launcher with CUDA, core detection & multi-slot
```

---

## Quickstart

### 1. Installation
The installer auto-detects distribution package managers (Arch `pacman`, Debian/Ubuntu `apt`, Fedora `dnf`), configures a PEP 668-safe venv, compiles `llama.cpp` (with CUDA offload if `nvcc` is present), and installs the global `bus3f-tui` command into `~/.local/bin`:

```bash
bash setup.sh
source ~/.bashrc
```

### 2. Local LLM Server & Auto-Start
`setup.sh` and the `bus3f-tui` launcher automatically start and monitor `llama-server` in the background. You can also launch it manually with custom models:

```bash
bash scripts/launch_server.sh &
# Or specify a model directly:
bash scripts/launch_server.sh DeepSeek-Coder-V2-Lite-Instruct-Q4_K_M.gguf &
```

*Optional Environment Overrides:*
- `LLAMA_THREADS`: Force CPU thread count (default: auto-detected via CPU cores).
- `LLAMA_PORT`: Server port (default: `8080`).
- `LLM_URL`: Custom OpenAI-compatible endpoint (default: `http://localhost:8080/v1/chat/completions`).

### 3. Launch Interactive TUI
Navigate to any project directory and launch:

```bash
cd /path/to/your/project
bus3f-tui
```
*Prompt dynamically displays project context:*  
`[my_project · coder · sequential · s-624b28aa · ponytail] >`

### 4. Headless Single-Task Execution (`main.py`)
Run tasks directly without entering interactive mode:

```bash
python3 main.py "review src/auth.py for edge cases"
python3 main.py "scaffold a rate limiter middleware"
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

### 6. Universal Specialist Profiles & Dynamic Custom Agents
- **Universal Specialist Profiles**:
  - `coder`: Code implementation, file editing, and dry-run code changes.
  - `reviewer`: Read-only security auditing, bug reviews, and pattern inspection.
  - `debugger`: Log inspection, crash diagnosis, and error trace grepping.
  - `general`: Architecture planning, task breakdowns, and multi-stack orchestration.
- **Dynamic Custom Agents**: Create new specialist agents interactively via `/new-agent` or drop JSON definitions into `~/agent_team/custom_agents/*.json`.
- **Backward-Compatible Engine Aliases**: Legacy engine tags (`godot`, `unity`, `asset`, `build`) map transparently to universal profiles.

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
| `/team [agents] <task>` | Run multi-agent team task concurrently or sequentially |
| `/grammar [module\|reset]` | Set isolated Tree-sitter grammar plugin |
| `/models` | List installed GGUF models in `~/models` |
| `/model switch <name>` | Switch active model and hot-swap background server |
| `/new-model [url]` | Download and install a GGUF model |
| `/search-model <query>` | Search HuggingFace for GGUFs and install |
| `/agents` | List built-in and custom specialist agents |
| `/new-agent` | Interactive wizard to create a new agent |
| `plugins` | List loaded tool plugins and skills |
| `plugin install <url>` | Install plugin from local path or URL |
| `/ponytail` | Toggle lazy developer mode (minimal diffs, zero bloat) |
| `init` | Scrape active project into `MEMORY.md` |
| `project [path]` | View or set active project directory |
| `remember <note>` | Append a note to project `MEMORY.md` |
| `memory` | Display current project `MEMORY.md` |
| `status` | Check local `llama-server` connection status |
| `history` | Display recent session traces from SQLite |
| `clear` | Clear terminal screen and redraw banner |
| `quit` | Exit the CLI |
