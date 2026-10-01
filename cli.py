from __future__ import annotations
import re
import sys
import os
import json
import time
import threading
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from harness.router import route
from harness.loop import run_agent
from harness.db import (
    init_db, list_sessions, get_session, create_session, delete_session, branch_session
)
from agents.profiles import AGENT_PROFILES
from tools.gamedev_tools import check_godot35_apis, check_unity2018_apis

try:
    import readline
except ImportError:
    pass

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.formatted_text import ANSI
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.styles import Style, merge_styles
    from prompt_toolkit.application.current import get_app
    HAS_PROMPT_TOOLKIT = True
except ImportError:
    HAS_PROMPT_TOOLKIT = False
    get_app = None

try:
    from prompt_toolkit.lexers import Lexer, PygmentsLexer
    from prompt_toolkit.styles.pygments import style_from_pygments_cls
    from pygments.styles import get_style_by_name
    from pygments.lexers.dotnet import CSharpLexer
    try:
        from pygments.lexers.gdscript import GDScriptLexer
    except ImportError:
        from pygments.lexers.python import PythonLexer as GDScriptLexer
    HAS_PYGMENTS = True
except ImportError:
    HAS_PYGMENTS = False

try:
    import tree_sitter
    from tree_sitter import Language, Parser
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

try:
    import termios
    import tty
    import select
    import _thread
except ImportError:
    termios = None
    tty = None
    select = None
    _thread = None

# ── Colors ────────────────────────────────────────────────────────────────────
class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    GREEN  = "\033[32m"
    YELLOW = "\033[33m"
    CYAN   = "\033[36m"
    RED    = "\033[31m"
    BLUE   = "\033[34m"
    PURPLE = "\033[35m"
    WHITE  = "\033[97m"

# ── Spinner ───────────────────────────────────────────────────────────────────
class Spinner:
    FRAMES = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]

    def __init__(self, label: str = ""):
        self.label = label
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def _spin(self):
        i = 0
        fd = sys.stdin.fileno() if (termios and hasattr(sys.stdin, "isatty") and sys.stdin.isatty()) else None
        old_attr = None
        if fd is not None:
            try:
                old_attr = termios.tcgetattr(fd)
                tty.setcbreak(fd)
            except Exception:
                old_attr = None
        try:
            while not self._stop.is_set():
                frame = self.FRAMES[i % len(self.FRAMES)]
                hint = f" {C.DIM}[ESC to cancel]{C.RESET}" if "[ESC" not in self.label else ""
                print(f"\r  {C.CYAN}{frame}{C.RESET}  {C.DIM}{self.label}{C.RESET}{hint}", end="", flush=True)
                if fd is not None and select and _thread:
                    r, _, _ = select.select([sys.stdin], [], [], 0.08)
                    if r:
                        ch = sys.stdin.read(1)
                        if ch == "\x1b":  # ESC
                            r2, _, _ = select.select([sys.stdin], [], [], 0.04)
                            if r2:
                                sys.stdin.read(2)  # skip arrow keys / ANSI escape sequences
                                continue
                            _thread.interrupt_main()
                            break
                        elif ch == "\x03":  # Ctrl+C
                            _thread.interrupt_main()
                            break
                else:
                    time.sleep(0.08)
                i += 1
        finally:
            if fd is not None and old_attr is not None:
                try:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_attr)
                except Exception:
                    pass

    def update(self, label: str):
        self.label = label

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()
        print("\r" + " " * 70 + "\r", end="", flush=True)

# ── Configuration & Active Project ───────────────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "config.json" if (Path(__file__).parent / "config.json").exists() else (Path.home() / "agent_team" / "config.json")

def load_config() -> dict:
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass

    proj = cfg.get("project")
    if not proj or not Path(proj).exists() or "NONNULL" in proj:
        cwd = Path.cwd()
        has_gd = (cwd / "project.godot").exists() or any(cwd.glob("*.gd"))
        has_cs = (cwd / "Assets").exists() or any(cwd.glob("*.cs"))
        cfg["project"] = str(cwd)
        cfg["engine"] = "godot" if has_gd else "unity" if has_cs else "general"

    cfg.setdefault("engine", "general")
    cfg.setdefault("exec_mode", "sequential")
    return cfg

def save_config(cfg: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

def set_project(raw: str):
    p = Path(raw).expanduser()
    if not p.is_absolute() or not p.exists():
        cfg = load_config()
        if cfg.get("project"):
            sibling = Path(cfg["project"]).parent / raw
            if sibling.exists():
                p = sibling
    p = p.resolve()
    if not p.exists():
        print(f"\n  {C.RED}Directory not found:{C.RESET} {p}\n")
        return
    has_gd = (p / "project.godot").exists() or next(p.rglob("*.gd"), None) is not None
    has_cs = (p / "Assets").exists() or next(p.rglob("*.cs"), None) is not None
    engine = "godot" if has_gd else "unity" if has_cs else "general"
    save_config({"project": str(p), "engine": engine})
    print(f"\n  {C.GREEN}✓{C.RESET} Active project: {C.BOLD}{p.name}{C.RESET}  {C.DIM}({engine}){C.RESET}")
    print(f"    {C.DIM}{p}{C.RESET}")
    if (p / "MEMORY.md").exists():
        print(f"    {C.DIM}Memory: MEMORY.md active{C.RESET}")
    print()

def append_memory(note: str):
    cfg = load_config()
    p = Path(cfg["project"]) if cfg.get("project") else None
    if not p or not p.exists():
        print(f"\n  {C.YELLOW}No active project set. Use: project <path>{C.RESET}\n")
        return
    mem_file = p / "MEMORY.md"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(mem_file, "a", encoding="utf-8") as f:
        f.write(f"\n- [{ts}] {note.strip()}\n")
    print(f"\n  {C.GREEN}✓{C.RESET} Saved note to {C.BOLD}{p.name}/MEMORY.md{C.RESET}\n")

def init_codebase():
    """Scrapes active project, detects conventions/files, and generates initial MEMORY.md."""
    cfg = load_config()
    p = Path(cfg["project"]) if cfg.get("project") else None
    if not p or not p.exists():
        print(f"\n  {C.YELLOW}No active project set. Use: project <path>{C.RESET}\n")
        return
    rule(f"init · {p.name}")
    engine = cfg.get("engine", "general")
    ext = "*.cs" if engine == "unity" else "*.gd" if engine == "godot" else "*.*"
    ignored = {".git", "Library", "obj", "bin", ".import", ".idea", "Build", "Temp"}
    files = [f for f in sorted(p.rglob(ext)) if not any(x in f.parts for x in ignored)]

    lines = [
        f"# Project Context — {p.name} ({engine.upper()})",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Total scripts: {len(files)}",
        "",
        "## Invariants & Architecture",
        f"- Target Engine: {engine.upper()}",
        "- Core conventions: see AGENTS.md",
        "",
        "## Core Scripts Inventory",
    ]
    for f in files[:40]:
        lines.append(f"- `{f.relative_to(p)}` ({f.stat().st_size:,} bytes)")
    if len(files) > 40:
        lines.append(f"- … and {len(files)-40} more scripts")

    mem_file = p / "MEMORY.md"
    mem_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n  {C.GREEN}✓{C.RESET} Scraped {len(files)} scripts → {C.BOLD}{p.name}/MEMORY.md{C.RESET}\n")

# ── Plugins & Skills ──────────────────────────────────────────────────────────
PLUGINS_DIR = Path.home() / "agent_team" / "plugins"

def find_skill_file(name: str) -> Path | None:
    """Find skill markdown file either as standalone .md or in a cloned plugin directory."""
    clean = name.lower().strip()
    candidates = [
        PLUGINS_DIR / f"{clean}.md",
        PLUGINS_DIR / clean / "SKILL.md",
        PLUGINS_DIR / clean / f"{clean}.md",
    ]
    for c in candidates:
        if c.exists():
            return c
    for c in PLUGINS_DIR.rglob("*.md"):
        if ".git" in c.parts:
            continue
        if c.stem.lower() == clean or c.parent.name.lower() == clean:
            return c
    return None

def load_plugins():
    """Load .py tool plugins and register them with the loop harness."""
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    import importlib.util
    import harness.loop as loop_mod

    for p in PLUGINS_DIR.rglob("*.py"):
        if ".git" in p.parts:
            continue
        try:
            name = f"plugin_{p.stem}"
            spec = importlib.util.spec_from_file_location(name, p)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                tools = getattr(mod, "TOOLS", {})
                if isinstance(tools, dict):
                    loop_mod.TOOL_REGISTRY.update(tools)
                    loop_mod.PLUGIN_TOOLS.update(tools.keys())
        except Exception as e:
            print(f"  {C.YELLOW}! Failed to load plugin {p.name}: {e}{C.RESET}")

def get_active_skills() -> list[str]:
    cfg = load_config()
    return cfg.get("active_skills", ["ponytail"])

def toggle_skill(name: str):
    name = name.lstrip("/").lower()
    cfg = load_config()
    active = set(cfg.get("active_skills", ["ponytail"]))
    if name in active:
        active.remove(name)
        status = f"{C.YELLOW}disabled{C.RESET}"
    else:
        active.add(name)
        status = f"{C.GREEN}enabled{C.RESET}"
    cfg["active_skills"] = list(active)
    save_config(cfg)
    print(f"\n  {C.BOLD}{name}{C.RESET} mode {status}\n")

def get_exec_mode() -> str:
    cfg = load_config()
    return cfg.get("exec_mode", "sequential")

def toggle_exec_mode(target: str = ""):
    cfg = load_config()
    current = cfg.get("exec_mode", "sequential")
    target = target.strip().lower()
    if target in ("parallel", "sequential"):
        mode = target
    elif not target:
        mode = "parallel" if current == "sequential" else "sequential"
    else:
        print(f"\n  {C.YELLOW}Invalid mode '{target}'. Use: /mode [parallel|sequential]{C.RESET}\n")
        return
    cfg["exec_mode"] = mode
    save_config(cfg)
    print(f"\n  {C.GREEN}✓{C.RESET} Multi-agent execution mode: {C.BOLD}{mode}{C.RESET}")
    if mode == "parallel":
        print(f"    {C.DIM}Agents run concurrently via ThreadPoolExecutor (-np 2+ on llama-server).{C.RESET}\n")
    else:
        print(f"    {C.DIM}Agents run sequentially in pipeline order.{C.RESET}\n")

# ── Chat Sessions ─────────────────────────────────────────────────────────────
def get_active_session() -> str:
    cfg = load_config()
    sid = cfg.get("active_session")
    if not sid:
        import uuid
        sid = f"s-{uuid.uuid4().hex[:8]}"
        cfg["active_session"] = sid
        save_config(cfg)
        create_session(sid, "main session", title="main")
    return sid

def list_sessions_cli():
    rule("chat sessions")
    sessions = list_sessions()
    if not sessions:
        print(f"  {C.DIM}No sessions found. Create one with: /new [name]{C.RESET}\n")
        return
    active_id = get_active_session()
    print(f"  {'#':<3} {'ID':<12} {'Turns':<8} {'Status':<10} {'Title / First prompt':<35}")
    print(f"  {'─'*3} {'─'*12} {'─'*8} {'─'*10} {'─'*35}")
    for i, s in enumerate(sessions, 1):
        sid = s["id"]
        is_active = (sid == active_id)
        tag = f" {C.GREEN}● active{C.RESET}" if is_active else ""
        parent = f" {C.CYAN}↳ branch of {s['parent_id']}{C.RESET}" if s.get("parent_id") else ""
        title = s.get("title") or s.get("task_input", "")[:35]
        status = s.get("status", "running")
        status_col = C.GREEN + status + C.RESET if status == "done" else C.DIM + status + C.RESET
        print(f"  {i:<3} {C.BOLD}{sid:<12}{C.RESET} {s.get('trace_count', 0):<8} {status_col:<10} {title[:35]}{tag}{parent}")
    print(f"\n  {C.DIM}Commands: /resume <id>, /new [name], /branch [name], /delete <id>{C.RESET}\n")

def resolve_session_target(target: str) -> dict | None:
    sessions = list_sessions()
    if not sessions:
        return None
    target = target.strip()
    if target.isdigit():
        idx = int(target) - 1
        if 0 <= idx < len(sessions):
            return sessions[idx]
    for s in sessions:
        if s["id"].lower() == target.lower() or s["id"].lower().startswith(target.lower()):
            return s
        if (s.get("title") or "").lower() == target.lower():
            return s
    return None

def new_session_cli(name: str = ""):
    import uuid
    sid = f"s-{uuid.uuid4().hex[:8]}"
    title = name.strip() or sid
    create_session(sid, "", title=title)
    cfg = load_config()
    cfg["active_session"] = sid
    save_config(cfg)
    print(f"\n  {C.GREEN}✓{C.RESET} Started new chat session: {C.BOLD}{title}{C.RESET} ({sid})\n")

def resume_session_cli(target: str = ""):
    if not target.strip():
        list_sessions_cli()
        return
    s = resolve_session_target(target)
    if not s:
        print(f"\n  {C.YELLOW}Session '{target}' not found.{C.RESET}")
        list_sessions_cli()
        return
    cfg = load_config()
    cfg["active_session"] = s["id"]
    save_config(cfg)
    title = s.get("title") or s["id"]
    print(f"\n  {C.GREEN}✓{C.RESET} Resumed session: {C.BOLD}{title}{C.RESET} ({s['id']})\n")

def delete_session_cli(target: str = ""):
    if not target.strip():
        print(f"\n  {C.YELLOW}Usage: /delete <id_or_number>{C.RESET}\n")
        return
    s = resolve_session_target(target)
    if not s:
        print(f"\n  {C.YELLOW}Session '{target}' not found.{C.RESET}\n")
        return
    sid = s["id"]
    delete_session(sid)
    print(f"\n  {C.GREEN}✓{C.RESET} Deleted session: {C.BOLD}{sid}{C.RESET}")
    cfg = load_config()
    if cfg.get("active_session") == sid:
        remaining = list_sessions()
        new_active = remaining[0]["id"] if remaining else ""
        if not new_active:
            import uuid
            new_active = f"s-{uuid.uuid4().hex[:8]}"
            create_session(new_active, "", title="main")
        cfg["active_session"] = new_active
        save_config(cfg)
        print(f"    Switched active session to: {C.BOLD}{new_active}{C.RESET}\n")
    else:
        print()

def branch_session_cli(raw_args: str = ""):
    import uuid
    current_active = get_active_session()
    parts = raw_args.strip().split(maxsplit=1)

    source_session = None
    new_title = None

    if len(parts) >= 2 and resolve_session_target(parts[0]):
        source_session = resolve_session_target(parts[0])
        new_title = parts[1].strip()
    elif len(parts) == 1 and resolve_session_target(parts[0]):
        source_session = resolve_session_target(parts[0])
        new_title = f"branch of {source_session.get('title') or source_session['id']}"
    elif len(parts) >= 1 and raw_args.strip():
        source_session = resolve_session_target(current_active)
        new_title = raw_args.strip()
    else:
        source_session = resolve_session_target(current_active)
        new_title = f"branch of {source_session.get('title') or current_active}" if source_session else "branch"

    if not source_session:
        print(f"\n  {C.YELLOW}Source session not found to branch from.{C.RESET}\n")
        return

    new_id = f"s-{uuid.uuid4().hex[:8]}"
    branch_session(source_session["id"], new_id, title=new_title)
    cfg = load_config()
    cfg["active_session"] = new_id
    save_config(cfg)
    print(f"\n  {C.GREEN}✓{C.RESET} Branched from {C.BOLD}{source_session['id']}{C.RESET} → {C.BOLD}{new_title}{C.RESET} ({new_id})")
    print(f"    {C.DIM}Active session switched to new branch.{C.RESET}\n")

def list_plugins():
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    rule("plugins & skills")
    py_files = [p for p in sorted(PLUGINS_DIR.rglob("*.py")) if ".git" not in p.parts]
    active = set(get_active_skills())

    skills = {}
    for p in sorted(PLUGINS_DIR.rglob("*.md")):
        if ".git" in p.parts:
            continue
        skill_id = p.parent.name if p.name.upper() == "SKILL.MD" else p.stem
        if skill_id not in skills:
            skills[skill_id] = p

    print(f"  Directory: {C.DIM}{PLUGINS_DIR}{C.RESET}\n")
    if not py_files and not skills:
        print(f"  {C.DIM}No plugins found. Install via: plugin install <github_url_or_path>{C.RESET}\n")
        return

    for sid in sorted(skills.keys()):
        is_on = sid in active
        badge = f"{C.GREEN}active{C.RESET}" if is_on else f"{C.DIM}inactive{C.RESET}"
        print(f"  {C.PURPLE}skill{C.RESET}  {sid:<18} {badge}  {C.DIM}(/{sid} to toggle){C.RESET}")

    for p in py_files:
        print(f"  {C.CYAN}tool{C.RESET}   {p.name}")
    print()

def install_plugin(target: str):
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    import subprocess
    import shutil
    from urllib.parse import urlparse

    target = target.strip()
    if not target:
        print(f"\n  {C.YELLOW}Usage: plugin install <github_url_or_path>{C.RESET}\n")
        return

    # GitHub shorthand like "DietrichGebert/ponytail"
    if re.match(r"^[\w-]+/[\w.-]+$", target):
        target = f"https://github.com/{target}"

    # Git repository URL
    if target.endswith(".git") or "github.com/" in target or "gitlab.com/" in target:
        repo_name = target.rstrip("/").split("/")[-1].replace(".git", "")
        dest = PLUGINS_DIR / repo_name
        if dest.exists():
            print(f"\n  Updating {C.BOLD}{repo_name}{C.RESET}…")
            subprocess.run(["git", "-C", str(dest), "pull"], check=False)
        else:
            with Spinner(f"cloning {repo_name}…"):
                res = subprocess.run(["git", "clone", "--depth", "1", target, str(dest)], capture_output=True, text=True)
            if res.returncode != 0:
                print(f"\n  {C.RED}✗ Git clone failed:{C.RESET} {res.stderr}\n")
                return
        print(f"\n  {C.GREEN}✓{C.RESET} Installed plugin {C.BOLD}{repo_name}{C.RESET} → {dest}\n")
        load_plugins()
        return

    # Direct URL
    if target.startswith(("http://", "https://")):
        import urllib.request
        name = Path(urlparse(target).path).name or "plugin.py"
        dest = PLUGINS_DIR / name
        try:
            with Spinner(f"downloading {name}…"):
                req = urllib.request.Request(target, headers={"User-Agent": "agent-team"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    dest.write_bytes(resp.read())
            print(f"\n  {C.GREEN}✓{C.RESET} Installed plugin {name} → {dest}\n")
        except Exception as e:
            print(f"\n  {C.RED}✗ Download failed:{C.RESET} {e}\n")
            return
    else:
        src = Path(target).expanduser().resolve()
        if not src.exists():
            print(f"\n  {C.RED}File not found:{C.RESET} {src}\n")
            return
        dest = PLUGINS_DIR / src.name
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            dest.write_bytes(src.read_bytes())
        print(f"\n  {C.GREEN}✓{C.RESET} Installed {src.name} → {dest}\n")
    load_plugins()

# ── Local Models ──────────────────────────────────────────────────────────────
MODELS_DIR = Path.home() / "models"

MODEL_PRESETS = {
    "1": ("qwen2.5-coder-7b-instruct-q4_k_m.gguf", "https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF/resolve/main/qwen2.5-coder-7b-instruct-q4_k_m.gguf", "Qwen2.5-Coder-7B (4.7 GB, recommended)"),
    "2": ("qwen2.5-coder-3b-instruct-q4_k_m.gguf", "https://huggingface.co/Qwen/Qwen2.5-Coder-3B-Instruct-GGUF/resolve/main/qwen2.5-coder-3b-instruct-q4_k_m.gguf", "Qwen2.5-Coder-3B (2.0 GB, lightweight)"),
    "3": ("DeepSeek-Coder-V2-Lite-Instruct-Q4_K_M.gguf", "https://huggingface.co/bartowski/DeepSeek-Coder-V2-Lite-Instruct-GGUF/resolve/main/DeepSeek-Coder-V2-Lite-Instruct-Q4_K_M.gguf", "DeepSeek-Coder-V2-Lite (8.9 GB, MoE)"),
}

MODEL_ALIASES = {
    "qwen": "1", "qwen7b": "1", "qwen-7b": "1", "qwen2.5": "1", "default": "1",
    "qwen3b": "2", "qwen-3b": "2", "light": "2", "small": "2",
    "deepseek": "3", "deepseek-lite": "3", "deepseek-coder": "3",
}

def list_models():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    rule("local models")
    files = sorted(MODELS_DIR.glob("*.gguf"))
    cfg = load_config()
    active = cfg.get("active_model", "")
    print(f"  Directory: {C.DIM}{MODELS_DIR}{C.RESET}\n")
    if not files:
        print(f"  {C.DIM}No GGUF models found. Add via: /new-model{C.RESET}\n")
        return
    for i, f in enumerate(files, 1):
        size_gb = f.stat().st_size / (1024**3)
        is_active = (f.name == active) or (not active and "7b" in f.name.lower())
        tag = f" {C.GREEN}● active{C.RESET}" if is_active else ""
        print(f"  [{i}] {C.CYAN}{f.name:<46}{C.RESET} {C.DIM}({size_gb:.1f} GB){C.RESET}{tag}")
    print(f"\n  {C.DIM}Switch model: model switch <number_or_name>{C.RESET}")
    print(f"  {C.DIM}Add model:    /new-model [alias_or_url]{C.RESET}\n")

def switch_model(target: str = ""):
    files = sorted(MODELS_DIR.glob("*.gguf"))
    if not files:
        print(f"\n  {C.YELLOW}No models found in {MODELS_DIR}. Add one via /new-model{C.RESET}\n")
        return
    cfg = load_config()
    target = target.strip().lower()
    selected = None
    if target.isdigit() and 1 <= int(target) <= len(files):
        selected = files[int(target) - 1]
    elif target in MODEL_ALIASES:
        preset_name = MODEL_PRESETS[MODEL_ALIASES[target]][0]
        selected = next((f for f in files if f.name.lower() == preset_name.lower()), None)
    elif target:
        selected = next((f for f in files if target in f.name.lower()), None)

    if not selected:
        print(f"\n  {C.YELLOW}Model '{target}' not found. Installed models:{C.RESET}")
        list_models()
        return

    cfg["active_model"] = selected.name
    save_config(cfg)
    print(f"\n  {C.GREEN}✓{C.RESET} Active model set to {C.BOLD}{selected.name}{C.RESET}")
    print(f"    {C.DIM}Restart llama-server to apply: bash ~/agent_team/scripts/launch_server.sh &{C.RESET}\n")

def add_model(target: str = "", custom_name: str = ""):
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    import subprocess
    target = target.strip()

    if target.lower() in MODEL_ALIASES:
        target = MODEL_ALIASES[target.lower()]

    if target in MODEL_PRESETS:
        default_name, target, _ = MODEL_PRESETS[target]
        if not custom_name:
            custom_name = default_name

    if not target:
        rule("new model setup")
        print("\n  Quick Presets:")
        for k, (_, _, desc) in MODEL_PRESETS.items():
            print(f"  {k}) {desc}")
        choice = input("\n  Select preset [1-3], alias (e.g. 'deepseek'), or enter GGUF URL/path: ").strip()
        if choice.lower() in MODEL_ALIASES:
            choice = MODEL_ALIASES[choice.lower()]
        if choice in MODEL_PRESETS:
            default_name, target, _ = MODEL_PRESETS[choice]
            if not custom_name:
                custom_name = default_name
        else:
            target = choice

    if not target:
        return

    if "http://" in target or "https://" in target:
        target = re.sub(r"\s+", "", target).replace("/blob/", "/resolve/")

    name = custom_name.strip() if custom_name.strip() else target.rstrip("/").split("/")[-1].split("?")[0]
    if not name.endswith(".gguf"):
        name += ".gguf"
    dest = MODELS_DIR / name

    if target.startswith(("http://", "https://")):
        print(f"\n  Downloading {name} to {dest}…")
        res = subprocess.run(["curl", "-L", "-C", "-", "--http1.1", "--retry", "5", "--retry-delay", "2", "--progress-bar", "-o", str(dest), target])
        if res.returncode == 0:
            print(f"\n  {C.GREEN}✓{C.RESET} Saved {name} to {MODELS_DIR}\n")
            cfg = load_config()
            cfg["active_model"] = name
            save_config(cfg)
        else:
            if dest.exists() and dest.stat().st_size == 0:
                dest.unlink()
            print(f"\n  {C.RED}✗ Download failed (code {res.returncode}){C.RESET}\n")
    else:
        src = Path(target).expanduser().resolve()
        if not src.exists():
            print(f"\n  {C.RED}File not found:{C.RESET} {src}\n")
            return
        import shutil
        shutil.copy2(src, dest)
        print(f"\n  {C.GREEN}✓{C.RESET} Copied {name} to {MODELS_DIR}\n")
        cfg = load_config()
        cfg["active_model"] = name
        save_config(cfg)

def search_and_install_model(query: str):
    """Query HuggingFace models API for GGUFs matching query and present interactive selection."""
    import urllib.request
    import urllib.parse
    clean_query = query.strip()
    rule(f"search models · {clean_query}")
    url = f"https://huggingface.co/api/models?search={urllib.parse.quote(clean_query)}&filter=gguf&sort=downloads&direction=-1&limit=5"
    try:
        with Spinner(f"searching HuggingFace for '{clean_query}'…"):
            req = urllib.request.Request(url, headers={"User-Agent": "agent-team"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"\n  {C.RED}✗ Search failed:{C.RESET} {e}\n")
        return

    if not data:
        print(f"\n  {C.YELLOW}No GGUF models found for '{clean_query}'.{C.RESET}\n")
        return

    print(f"\n  Matched GGUF models on HuggingFace:")
    candidates = []
    for i, item in enumerate(data, 1):
        repo_id = item.get("id", "")
        downloads = item.get("downloads", 0)
        likes = item.get("likes", 0)
        siblings = [s.get("rfilename", "") for s in item.get("siblings", []) if s.get("rfilename", "").endswith(".gguf")]
        best_file = next((s for s in siblings if "q4_k_m" in s.lower()), None)
        if not best_file:
            best_file = next((s for s in siblings if "q4" in s.lower()), None)
        if not best_file and siblings:
            best_file = siblings[0]

        file_label = f" ({best_file})" if best_file else ""
        print(f"  [{i}] {C.CYAN}{repo_id}{C.RESET}{C.DIM}{file_label} · ↓ {downloads:,} · ♥ {likes}{C.RESET}")
        candidates.append((repo_id, best_file))

    choice = input(f"\n  Select [1-{len(candidates)}] to download, or enter to cancel: ").strip()
    if not choice.isdigit() or not (1 <= int(choice) <= len(candidates)):
        print(f"  {C.DIM}Cancelled.{C.RESET}\n")
        return

    chosen_repo, chosen_file = candidates[int(choice) - 1]
    if not chosen_file:
        try:
            tree_url = f"https://huggingface.co/api/models/{chosen_repo}/tree/main"
            req = urllib.request.Request(tree_url, headers={"User-Agent": "agent-team"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                tree_data = json.loads(resp.read().decode("utf-8"))
            ggufs = [f["path"] for f in tree_data if f.get("path", "").endswith(".gguf")]
            chosen_file = next((s for s in ggufs if "q4_k_m" in s.lower()), None) or next((s for s in ggufs if "q4" in s.lower()), None) or (ggufs[0] if ggufs else None)
        except Exception:
            pass

    if not chosen_file:
        chosen_file = f"{chosen_repo.split('/')[-1]}.gguf"

    download_url = f"https://huggingface.co/{chosen_repo}/resolve/main/{chosen_file}"
    short_name = chosen_file.replace(".gguf", "")
    add_model(download_url, custom_name=short_name)

# ── Local Agent Registry ──────────────────────────────────────────────────────
CUSTOM_AGENTS_DIR = Path.home() / "agent_team" / "custom_agents"

def list_agents():
    from agents.profiles import AGENT_PROFILES, load_custom_agents
    load_custom_agents()
    rule("local agents")
    print(f"  {C.BOLD}{'Agent':<20} {'Role / Parent':<24} {'Tools'}{C.RESET}")
    print(f"  {C.DIM}{'─'*20} {'─'*24} {'─'*24}{C.RESET}")
    for k, p in AGENT_PROFILES.items():
        role = f"sub-agent → {p['parent']}" if p.get("parent") else ("custom" if p.get("custom") else "built-in")
        tools = ", ".join(p.get("tool_whitelist", [])[:3])
        if len(p.get("tool_whitelist", [])) > 3:
            tools += "…"
        print(f"  {C.CYAN}{p['name']:<20}{C.RESET} {C.DIM}{role:<24}{C.RESET} {tools}")
    print(f"\n  {C.DIM}Create new agent: /new-agent{C.RESET}\n")

def create_agent_wizard():
    rule("create new local agent")
    print(f"  {C.DIM}Define a new specialist agent or a sub-agent helper.{C.RESET}\n")
    name = input("  Agent name (e.g. 'shader-expert', 'audio-master'): ").strip()
    if not name:
        return
    key = re.sub(r"[^\w-]", "", name.lower().replace(" ", "-"))

    print("\n  Architecture role:")
    print("  1) Standalone specialist (routes directly based on keywords)")
    print("  2) Sub-agent helper to Unity (assists unity tasks)")
    print("  3) Sub-agent helper to Godot (assists godot tasks)")
    choice = input("  Choose role [1-3, default 1]: ").strip()
    parent = "unity" if choice == "2" else "godot" if choice == "3" else None

    purpose = input("\n  Agent purpose / focus: ").strip()
    keywords_raw = input("  Trigger keywords (comma-separated, e.g. 'shader,hlsl,material'): ").strip()
    keywords = [k.strip().lower() for k in keywords_raw.split(",") if k.strip()]

    import harness.loop as loop_mod
    all_tools = list(loop_mod.TOOL_REGISTRY.keys())
    print(f"\n  Available tools: {', '.join(all_tools)}")
    tools_raw = input("  Tools to grant (comma-separated, default: read_file,list_dir): ").strip()
    tools = [t.strip() for t in tools_raw.split(",") if t.strip() in all_tools] or ["read_file", "list_dir"]

    parent_note = f" You act as a specialized sub-agent assisting {parent}." if parent else ""
    system_prompt = f"""You are {name}, a specialist game development AI agent.{parent_note}
Purpose: {purpose}

Respond in ReAct format:
Thought: <reasoning>
Action: <tool_name>
Args: <json args>
OR
Final Answer: <your response>"""

    agent_data = {
        "name": name,
        "parent": parent,
        "purpose": purpose,
        "keywords": keywords,
        "tool_whitelist": tools,
        "system_prompt": system_prompt,
    }

    CUSTOM_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    out_file = CUSTOM_AGENTS_DIR / f"{key}.json"
    out_file.write_text(json.dumps(agent_data, indent=2), encoding="utf-8")

    from agents.profiles import load_custom_agents
    load_custom_agents()
    print(f"\n  {C.GREEN}✓{C.RESET} Agent {C.BOLD}{name}{C.RESET} created and active!")
    print(f"    Saved: {out_file}")
    if parent:
        print(f"    Role:  Sub-agent helper for {C.CYAN}{parent}{C.RESET}")
    else:
        print(f"    Role:  Standalone (keywords: {', '.join(keywords)})")
    print()

GODOT_SCRIPTS = Path("/mnt/c/Users/Piaczo/Documents/Projects/Personal/game-dev-main/slide-x/scripts")
UNITY_SCRIPTS = Path("/mnt/c/Users/Piaczo/Documents/Projects/Personal/game-dev-main/NONNULL/Assets")

# ── Command Autocompletion & Readline Suggestions ─────────────────────────────
COMMANDS_HELP: dict[str, str] = {
    "/help": "show built-in commands and usage",
    "help": "show built-in commands and usage",
    "/sessions": "list all chat sessions",
    "sessions": "list all chat sessions",
    "/new": "start clean chat session [/new <name>]",
    "/resume": "resume previous session [/resume <id>]",
    "/branch": "branch conversation from active session [/branch <name>]",
    "/delete": "delete session and history [/delete <id>]",
    "/mode": "switch multi-agent mode [/mode parallel|sequential]",
    "/team": "run multi-agent task [/team <agents> <task>]",
    "/models": "list installed GGUF models in ~/models",
    "/new-model": "download & install new GGUF model [/new-model <url>]",
    "/search-model": "search HuggingFace for GGUF models & install",
    "/agents": "list local specialist and custom sub-agents",
    "/new-agent": "create new local specialist agent",
    "/ponytail": "toggle ponytail mode (minimal diffs, zero bloat)",
    "/grammar": "set isolated Tree-sitter grammar plugin or 'reset' [/grammar <module>]",
    "init": "scrape active project and generate MEMORY.md",
    "project": "view or switch active project directory",
    "remember": "append note to active project MEMORY.md",
    "memory": "display active project MEMORY.md",
    "plugins": "list loaded tool plugins and skills",
    "plugin install": "install plugin from GitHub URL or local path",
    "scan": "scan project files for Godot 3.5 / Unity 2018.2 violations",
    "migrate": "convert slide-x GDScript files to NONNULL C#",
    "status": "check local llama-server connection status",
    "history": "view recent task history from traces.db",
    "clear": "clear the terminal screen",
    "quit": "exit the CLI",
}

def setup_readline():
    if "readline" not in sys.modules:
        return
    import readline

    # Set word delimiters so '/' stays with command name
    readline.set_completer_delims(" \t\n")
    readline.parse_and_bind("tab: complete")
    readline.parse_and_bind("set show-all-if-ambiguous on")
    readline.parse_and_bind("set completion-query-items 100")

    def completer(text: str, state: int):
        buf = readline.get_line_buffer()
        lbuf = buf.lstrip()
        parts = lbuf.split()

        # Argument completions
        if len(parts) >= 2 or (len(parts) == 1 and buf.endswith(" ")):
            cmd = parts[0].lower()
            if cmd in ("/mode", "mode"):
                cands = ["parallel", "sequential"]
            elif cmd in ("/grammar", "grammar"):
                cands = ["reset", "tree_sitter_c_sharp", "tree_sitter_gdscript"]
            elif cmd in ("/resume", "resume", "/delete", "delete", "/del", "del", "/branch", "branch"):
                cands = [s["id"] for s in list_sessions()]
            elif cmd in ("scan", "/scan"):
                cands = ["godot", "unity"]
            elif cmd in ("model", "/model") or (len(parts) >= 2 and parts[1] in ("switch", "use")):
                cands = [p.name for p in MODELS_DIR.glob("*.gguf")]
            else:
                cands = []
            arg_text = parts[-1] if not buf.endswith(" ") else ""
            matches = [c for c in cands if c.lower().startswith(arg_text.lower())]
            return matches[state] if state < len(matches) else None

        # Command completions
        matches = [c for c in COMMANDS_HELP.keys() if c.lower().startswith(text.lower())]
        return matches[state] if state < len(matches) else None

    def display_matches(substitution, matches, longest_match_length):
        print()
        print(f"  {C.DIM}Available suggestions:{C.RESET}")
        for m in sorted(matches):
            desc = COMMANDS_HELP.get(m, "")
            if desc:
                print(f"    {C.CYAN}{m:<18}{C.RESET} {C.DIM}{desc}{C.RESET}")
            else:
                print(f"    {C.CYAN}{m}{C.RESET}")
        print()
        if hasattr(readline, "redisplay"):
            readline.redisplay()

    readline.set_completer(completer)
    if hasattr(readline, "set_completion_display_matches_hook"):
        readline.set_completion_display_matches_hook(display_matches)

# ── Tree-sitter AST & Process Isolation IPC ────────────────────────────────────
def _extract_tree_sitter_spans(node, text_bytes: bytes, tokens: list):
    ntype = node.type
    if ntype == "variable_declarator":
        for ch in node.children:
            if ch.type == "identifier":
                tokens.append((ch.start_byte, ch.end_byte, "class:sem.variable"))
    elif ntype == "parameter":
        for ch in node.children:
            if ch.type == "identifier":
                tokens.append((ch.start_byte, ch.end_byte, "class:sem.parameter"))
    elif ntype in ("field_declaration", "property_declaration"):
        for ch in node.children:
            if ch.type == "variable_declarator":
                for vch in ch.children:
                    if vch.type == "identifier":
                        tokens.append((vch.start_byte, vch.end_byte, "class:sem.variable"))
            elif ch.type == "identifier":
                tokens.append((ch.start_byte, ch.end_byte, "class:sem.variable"))
    elif ntype == "method_declaration":
        for ch in node.children:
            if ch.type == "identifier":
                tokens.append((ch.start_byte, ch.end_byte, "class:sem.method"))
    elif ntype in ("type_identifier", "predefined_type"):
        tokens.append((node.start_byte, node.end_byte, "class:sem.type"))
    elif ntype == "invocation_expression":
        if node.children:
            ch = node.children[0]
            if ch.type == "identifier":
                tokens.append((ch.start_byte, ch.end_byte, "class:sem.method"))
            elif ch.type == "member_access_expression" and len(ch.children) >= 3:
                tokens.append((ch.children[2].start_byte, ch.children[2].end_byte, "class:sem.method"))
    elif "comment" in ntype:
        tokens.append((node.start_byte, node.end_byte, "class:sem.comment"))
    elif "string" in ntype:
        tokens.append((node.start_byte, node.end_byte, "class:sem.string"))
    elif ntype in ("number_literal", "integer_literal", "true", "false", "null"):
        tokens.append((node.start_byte, node.end_byte, "class:sem.number"))
    elif not node.children:
        txt = node.text.decode("utf-8", errors="ignore")
        if txt in ("public", "private", "protected", "class", "void", "static", "using", "new", "return", "if", "else", "for", "while", "func", "var", "extends", "yield"):
            tokens.append((node.start_byte, node.end_byte, "class:sem.keyword"))
    for child in node.children:
        _extract_tree_sitter_spans(child, text_bytes, tokens)

def _tree_sitter_ipc_worker(conn, grammar_plugin: str | None = None):
    """Isolated child process worker running Tree-sitter C parsing and AST traversal.
    Prevents SIGSEGV or memory corruption in untrusted C grammar plugins from crashing the CLI.
    """
    parser = None
    try:
        from tree_sitter import Language, Parser
        if grammar_plugin:
            import importlib
            mod = importlib.import_module(grammar_plugin)
            lang = Language(mod.language())
            parser = Parser(lang)
        else:
            try:
                import tree_sitter_c_sharp as tscsharp
                lang = Language(tscsharp.language())
                parser = Parser(lang)
            except Exception:
                try:
                    from tree_sitter_languages import get_parser
                    parser = get_parser("c_sharp")
                except Exception:
                    parser = None
    except Exception as e:
        try:
            conn.send(("error", str(e)))
        except Exception:
            pass
        return

    if not parser:
        try:
            conn.send(("error", "Failed to initialize Tree-sitter parser"))
        except Exception:
            pass
        return

    try:
        conn.send(("ready", None))
    except Exception:
        return

    prev_tree = None
    prev_bytes = b""

    while True:
        try:
            msg = conn.recv()
        except (EOFError, KeyboardInterrupt):
            break

        if not msg or msg[0] == "shutdown":
            break

        cmd, raw_bytes = msg[0], msg[1]
        if cmd == "parse":
            try:
                if prev_tree is not None and prev_bytes:
                    min_len = min(len(prev_bytes), len(raw_bytes))
                    i = 0
                    while i < min_len and prev_bytes[i] == raw_bytes[i]:
                        i += 1
                    start_byte = i

                    j = 0
                    while j < (min_len - start_byte) and prev_bytes[-(j + 1)] == raw_bytes[-(j + 1)]:
                        j += 1
                    old_end_byte = len(prev_bytes) - j
                    new_end_byte = len(raw_bytes) - j

                    def _point(b_data, off):
                        pre = b_data[:off]
                        r = pre.count(b"\n")
                        last_nl = pre.rfind(b"\n")
                        c = off if last_nl == -1 else off - (last_nl + 1)
                        return (r, c)

                    prev_tree.edit(
                        start_byte=start_byte,
                        old_end_byte=old_end_byte,
                        new_end_byte=new_end_byte,
                        start_point=_point(prev_bytes, start_byte),
                        old_end_point=_point(prev_bytes, old_end_byte),
                        new_end_point=_point(raw_bytes, new_end_byte),
                    )
                    tree = parser.parse(raw_bytes, prev_tree)
                else:
                    tree = parser.parse(raw_bytes)

                prev_tree = tree
                prev_bytes = raw_bytes

                tokens = []
                _extract_tree_sitter_spans(tree.root_node, raw_bytes, tokens)
                tokens.sort(key=lambda t: t[0])
                conn.send(("tokens", raw_bytes, tokens))
            except Exception as e:
                prev_tree = None
                prev_bytes = b""
                try:
                    conn.send(("error", str(e)))
                except Exception:
                    break

# ── Prompt Toolkit Curses Widget & Multi-line Support ─────────────────────────
if HAS_PROMPT_TOOLKIT:
    class PTKCompleter(Completer):
        def get_completions(self, document, complete_event):
            line = document.current_line_before_cursor
            lbuf = line.lstrip()
            word = document.get_word_before_cursor(WORD=True)
            parts = lbuf.split()

            if len(parts) >= 2 or (len(parts) == 1 and line.endswith(" ")):
                cmd = parts[0].lower()
                cands = []
                if cmd in ("/mode", "mode"):
                    cands = [("parallel", "Concurrent agent execution"), ("sequential", "Pipeline agent execution")]
                elif cmd in ("/grammar", "grammar"):
                    cands = [("reset", "Reset to default C# Tree-sitter"), ("tree_sitter_c_sharp", "C# parser"), ("tree_sitter_gdscript", "GDScript parser")]
                elif cmd in ("/resume", "resume", "/delete", "delete", "/del", "del", "/branch", "branch"):
                    cands = [(s["id"], s.get("title") or "Session") for s in list_sessions()]
                elif cmd in ("scan", "/scan"):
                    cands = [("godot", "Scan Godot 3.5 GDScript files"), ("unity", "Scan Unity 2018.2 C# files")]
                elif cmd in ("model", "/model") or (len(parts) >= 2 and parts[1] in ("switch", "use")):
                    cands = [(p.name, f"{p.stat().st_size / (1024**3):.1f} GB") for p in MODELS_DIR.glob("*.gguf")]

                arg_prefix = parts[-1] if not line.endswith(" ") else ""
                for val, meta in cands:
                    if val.lower().startswith(arg_prefix.lower()):
                        yield Completion(val, start_position=-len(arg_prefix), display_meta=meta)
            else:
                for c, desc in COMMANDS_HELP.items():
                    if c.lower().startswith(word.lower()):
                        yield Completion(c, start_position=-len(word), display_meta=desc)

    ptk_bindings = KeyBindings()

    @ptk_bindings.add("escape", "enter")
    def _(event):
        """Alt+Enter or Esc+Enter inserts newline for multi-line cursor navigation."""
        event.current_buffer.insert_text("\n")

    @ptk_bindings.add("c-j")
    def _(event):
        """Ctrl+J inserts newline."""
        event.current_buffer.insert_text("\n")

    if HAS_PYGMENTS:
        class GameDevInputLexer(Lexer):
            def __init__(self):
                self.cs = PygmentsLexer(CSharpLexer)
                self.gd = PygmentsLexer(GDScriptLexer)

            def lex_document(self, document):
                txt = document.text
                if txt.strip().startswith("/"):
                    return lambda lineno: []
                cfg = load_config()
                eng = cfg.get("engine", "unity")
                if eng == "unity" or any(k in txt for k in ("using ", "public ", "class ", "void ", "MonoBehaviour")):
                    return self.cs.lex_document(document)
                return self.gd.lex_document(document)

    class TreeSitterSemanticLexer(Lexer):
        """AST-level semantic variable, type, parameter and method coloring via isolated Tree-sitter worker process."""
        def __init__(self, debounce_sec: float = 0.04, grammar_plugin: str | None = None):
            self.pygments = GameDevInputLexer() if HAS_PYGMENTS else None
            self.grammar_plugin = grammar_plugin
            self.proc = None
            self.parent_conn = None
            self.tokens = []
            self.token_bytes = b""
            self.debounce_sec = debounce_sec
            self.pending_bytes = None
            self.lock = threading.Lock()
            self.cond = threading.Condition(self.lock)
            self._stopped = False

            if HAS_TREE_SITTER:
                self._start_proc()

            if self.proc and self.proc.is_alive():
                self._thread = threading.Thread(target=self._worker, daemon=True)
                self._thread.start()

        def _start_proc(self) -> bool:
            try:
                import multiprocessing as mp
                self.parent_conn, child_conn = mp.Pipe()
                self.proc = mp.Process(
                    target=_tree_sitter_ipc_worker,
                    args=(child_conn, self.grammar_plugin),
                    daemon=True
                )
                self.proc.start()
                child_conn.close()
                if self.parent_conn.poll(timeout=1.5):
                    status, _ = self.parent_conn.recv()
                    if status == "ready":
                        return True
                return False
            except Exception:
                self.proc = None
                self.parent_conn = None
                return False

        def _worker(self):
            while not self._stopped:
                with self.cond:
                    while self.pending_bytes is None and not self._stopped:
                        self.cond.wait()
                    if self._stopped:
                        break
                    target_bytes = self.pending_bytes

                time.sleep(self.debounce_sec)

                with self.cond:
                    if self.pending_bytes != target_bytes:
                        continue
                    self.pending_bytes = None

                # Check process health; restart if untrusted third-party grammar segfaulted
                if not self.proc or not self.proc.is_alive() or not self.parent_conn:
                    if not self._start_proc():
                        continue

                try:
                    self.parent_conn.send(("parse", target_bytes))
                    # Timeout guard: protect against hung untrusted third-party C parser loops
                    if self.parent_conn.poll(timeout=0.5):
                        msg = self.parent_conn.recv()
                        if msg[0] == "tokens":
                            _, b_data, toks = msg
                            with self.lock:
                                self.tokens = toks
                                self.token_bytes = b_data
                        elif msg[0] == "error":
                            with self.lock:
                                self.tokens = []
                    else:
                        # Third-party plugin timed out or froze in C
                        try:
                            self.proc.terminate()
                        except Exception:
                            pass
                        self.proc = None
                        continue
                except Exception:
                    # Broken pipe or crash in child process
                    try:
                        if self.proc:
                            self.proc.terminate()
                    except Exception:
                        pass
                    self.proc = None
                    continue

                if HAS_PROMPT_TOOLKIT and get_app is not None:
                    try:
                        app = get_app()
                        if app and getattr(app, "is_running", False):
                            app.invalidate()
                    except Exception:
                        pass

        def lex_document(self, document):
            txt = document.text
            if txt.strip().startswith("/") or not self.proc:
                return self.pygments.lex_document(document) if self.pygments else lambda lineno: []

            raw_bytes = txt.encode("utf-8")

            with self.lock:
                is_match = (raw_bytes == self.token_bytes)
                toks = list(self.tokens)

            if not is_match:
                with self.cond:
                    self.pending_bytes = raw_bytes
                    self.cond.notify()

            lines = document.lines
            line_offsets = []
            offset = 0
            for l in lines:
                line_offsets.append(offset)
                offset += len(l.encode("utf-8")) + 1

            def get_line(lineno):
                if lineno >= len(lines):
                    return []
                l_text = lines[lineno]
                l_start = line_offsets[lineno]
                l_end = l_start + len(l_text.encode("utf-8"))

                line_toks = [t for t in toks if t[1] > l_start and t[0] < l_end]
                if not line_toks:
                    return [("", l_text)]

                frags = []
                curr = l_start
                for t_start, t_end, style in line_toks:
                    s = min(max(t_start, l_start), l_end)
                    e = min(max(t_end, l_start), l_end)
                    if s >= e:
                        continue
                    if s > curr:
                        prefix = raw_bytes[curr:s].decode("utf-8", errors="ignore")
                        if prefix:
                            frags.append(("", prefix))
                    chunk = raw_bytes[s:e].decode("utf-8", errors="ignore")
                    if chunk:
                        frags.append((style, chunk))
                    curr = e
                if curr < l_end:
                    suffix = raw_bytes[curr:l_end].decode("utf-8", errors="ignore")
                    if suffix:
                        frags.append(("", suffix))
                return frags

            return get_line

def get_prompt_session():
    if not HAS_PROMPT_TOOLKIT:
        return None
    history_file = Path.home() / "agent_team" / ".cli_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    custom_style = Style.from_dict({
        "completion-menu.completion": "bg:#1e1e1e #00d7d7",
        "completion-menu.completion.current": "bg:#005f87 #ffffff bold",
        "completion-menu.meta.completion": "bg:#1e1e1e #888888",
        "completion-menu.meta.completion.current": "bg:#005f87 #eeeeee",
        "scrollbar.background": "bg:#1e1e1e",
        "scrollbar.button": "bg:#444444",
        "sem.variable": "#9cdcfe bold",
        "sem.parameter": "#9cdcfe italic",
        "sem.method": "#dcdcaa bold",
        "sem.type": "#4ec9b0 bold",
        "sem.keyword": "#c586c0 bold",
        "sem.string": "#ce9178",
        "sem.number": "#b5cea8",
        "sem.comment": "#6a9955 italic",
    })

    lexer = None
    if HAS_TREE_SITTER:
        cfg = load_config()
        plugin = cfg.get("grammar_plugin", None)
        lexer = TreeSitterSemanticLexer(grammar_plugin=plugin)
    elif HAS_PYGMENTS:
        lexer = GameDevInputLexer()

    if HAS_PYGMENTS:
        try:
            pyg_style = style_from_pygments_cls(get_style_by_name("monokai"))
            combined_style = merge_styles([pyg_style, custom_style])
        except Exception:
            combined_style = custom_style
    else:
        combined_style = custom_style

    return PromptSession(
        completer=PTKCompleter(),
        complete_while_typing=True,
        key_bindings=ptk_bindings,
        history=FileHistory(str(history_file)),
        style=combined_style,
        lexer=lexer,
    )


# ── UI primitives ─────────────────────────────────────────────────────────────
def banner():
    print(f"""
{C.BOLD}  bus3f-tui{C.RESET}  {C.DIM}100% offline · air-gapped · multi-agent coding harness{C.RESET}
  {C.DIM}──────────────────────────────────────────────────────────{C.RESET}
  {C.DIM}Type '/' and press [Tab] for command suggestions{C.RESET}""")

def rule(label: str = ""):
    width = 44
    if label:
        pad = width - len(label) - 2
        print(f"\n  {C.DIM}── {label} {'─' * max(pad,2)}{C.RESET}")
    else:
        print(f"  {C.DIM}{'─' * width}{C.RESET}")

def print_thought(text: str):
    """Print model reasoning in dim italic style with clean wrapping."""
    import textwrap
    wrapped = textwrap.fill(text.strip(), width=76, initial_indent="  ✦ ", subsequent_indent="    ")
    print(f"\n{C.DIM}{wrapped}{C.RESET}")

def print_action(tool: str, args: dict):
    """Print tool call with clean, compact formatting."""
    formatted = []
    for k, v in args.items():
        if k in ("content", "code") or (isinstance(v, str) and "\n" in v):
            val_str = f"<{len(str(v)):,} chars>"
        elif k in ("path", "file_path", "filepath") and isinstance(v, str):
            p = Path(v)
            val_str = f"…/{p.parent.name}/{p.name}" if len(p.parts) > 2 else p.name
        else:
            val_str = str(v).replace("\n", " ")[:50]
        formatted.append(f"{k}: {val_str}")
    arg_str = "  ".join(formatted)
    print(f"\n  {C.BLUE}⟳{C.RESET} {C.BOLD}{tool}{C.RESET}  {C.DIM}{arg_str}{C.RESET}")

def print_result_ok(text: str):
    print(f"  {C.GREEN}✓{C.RESET}  {C.DIM}{text[:80]}{C.RESET}")

def print_result_err(text: str):
    print(f"  {C.RED}✗{C.RESET}  {C.DIM}{text[:80]}{C.RESET}")

def print_final(agent: str, text: str, steps: int, elapsed: float):
    rule()
    print(f"\n  {C.GREEN}{C.BOLD}●{C.RESET}  {C.BOLD}{agent}{C.RESET}  {C.DIM}{steps} step{'s' if steps!=1 else ''} · {elapsed:.1f}s{C.RESET}\n")
    # Word-wrap the final answer at 72 chars
    for para in text.split("\n"):
        if not para.strip():
            print()
            continue
        words = para.split()
        line = "  "
        for word in words:
            if len(line) + len(word) + 1 > 74:
                print(line)
                line = "  " + word
            else:
                line += (" " if line != "  " else "") + word
        if line.strip():
            print(line)
    print()

def print_fail(reason: str, steps: int):
    rule()
    print(f"\n  {C.RED}{C.BOLD}✗  Failed{C.RESET}  {C.DIM}{steps} steps — {reason}{C.RESET}\n")

def check_server() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen("http://localhost:8080/health", timeout=2) as resp:
            return json.loads(resp.read().decode("utf-8")).get("status") == "ok"
    except Exception:
        return False

# ── Scan command ──────────────────────────────────────────────────────────────
def run_scan(engine: str = ""):
    cfg = load_config()
    active_root = Path(cfg["project"]) if cfg.get("project") else None
    active_engine = cfg.get("engine", "general")

    if not engine:
        engine = active_engine if active_engine in ("godot", "unity") else "unity"

    if engine == "godot":
        root = active_root if (active_root and active_engine == "godot") else GODOT_SCRIPTS
        files = list(root.rglob("*.gd")) if root.exists() else []
        checker = check_godot35_apis
        label = f"Godot 3.5 ({root.name})"
    else:
        root = active_root if (active_root and active_engine == "unity") else (UNITY_SCRIPTS / "Scripts" if (UNITY_SCRIPTS / "Scripts").exists() else UNITY_SCRIPTS)
        files = list(root.rglob("*.cs")) if root.exists() else []
        checker = check_unity2018_apis
        label = f"Unity 2018.2 ({root.name})"

    if not files:
        print(f"\n  {C.YELLOW}No files found in {root}.{C.RESET}\n")
        return

    rule(f"scan · {label}")
    total = 0
    dirty = []

    for f in sorted(files):
        try:
            result = checker(f.read_text(encoding="utf-8", errors="replace"))
            if result["passed"]:
                print(f"  {C.GREEN}✓{C.RESET}  {f.name}")
            else:
                c = result["violation_count"]
                total += c
                dirty.append((f, result["violations"]))
                print(f"  {C.RED}✗{C.RESET}  {f.name}  {C.DIM}{c} violation{'s' if c!=1 else ''}{C.RESET}")
        except Exception as e:
            print(f"  {C.YELLOW}?{C.RESET}  {f.name}  {C.DIM}{e}{C.RESET}")

    rule()
    if total == 0:
        print(f"\n  {C.GREEN}{C.BOLD}All {len(files)} files clean.{C.RESET}\n")
    else:
        print(f"\n  {C.RED}{C.BOLD}{total} violation(s) in {len(dirty)} file(s){C.RESET}\n")
        for f, violations in dirty:
            print(f"  {C.YELLOW}{f.name}{C.RESET}")
            for v in violations[:4]:
                print(f"    {C.DIM}L{v['line']:4d}  {v['violation']}{C.RESET}")
            if len(violations) > 4:
                print(f"    {C.DIM}… +{len(violations)-4} more{C.RESET}")
        print()



def run_migration():
    """Guided migration from slide-x (Godot) to NONNULL (Unity)."""
    rule("migration · Godot → Unity")

    gd_files = sorted(GODOT_SCRIPTS.rglob("*.gd"))
    cs_out = UNITY_SCRIPTS / "Scripts"

    print(f"\n  {C.BOLD}Found {len(gd_files)} GDScript files to migrate{C.RESET}\n")
    for f in gd_files:
        print(f"  {C.DIM}{f.relative_to(GODOT_SCRIPTS)}{C.RESET}")

    print(f"\n  {C.YELLOW}This will generate Unity C# equivalents for each file.{C.RESET}")
    print(f"  Output → {cs_out}\n")
    confirm = input(f"  Proceed file by file? [y/N] ").strip().lower()
    if confirm != "y":
        print(f"  {C.DIM}Cancelled.{C.RESET}\n")
        return

    for gd_file in gd_files:
        name = gd_file.stem
        content = gd_file.read_text(encoding="utf-8", errors="replace")

        rule(f"{gd_file.name}")
        print()

        task = (
            f"You are converting a Godot 3.5 GDScript file to Unity 2018.2 C#.\n"
            f"Source: {gd_file.name}\n\n"

            f"CONVERSION RULES:\n"
            f"1. extends KinematicBody2D → MonoBehaviour on a GameObject with Rigidbody2D\n"
            f"2. extends Spatial → MonoBehaviour (3D, use Transform)\n"
            f"3. extends Node → MonoBehaviour\n"
            f"4. _ready() → void Start()\n"
            f"5. _process(delta) → void Update()\n"
            f"6. _physics_process(delta) → void FixedUpdate()\n"
            f"7. _input(event) → void Update() with Input.GetKey / Input.GetAxis\n"
            f"8. export var → [SerializeField] private with matching type\n"
            f"9. onready var → private field, assigned in Start() via GetComponent<T>()\n"
            f"10. yield(signal) → StartCoroutine() with IEnumerator\n"
            f"11. emit_signal() → C# event invoke or UnityEvent.Invoke()\n"
            f"12. connect(signal, self, method) → C# event subscription in Start()\n"
            f"13. get_node('X') / $X → GetComponentInChildren<T>() or serialized field\n"
            f"14. move_and_slide(vel) → rigidbody.velocity = vel (2D) or CharacterController.Move()\n"
            f"15. Input.is_action_pressed('ui_right') → Input.GetAxis('Horizontal') > 0\n"
            f"16. rand_range(a,b) → Random.Range(a,b)\n"
            f"17. OS.get_ticks_msec() → Time.time * 1000\n"
            f"18. Tween → use Coroutine with Mathf.Lerp\n"
            f"19. AnimationPlayer.play() → GetComponent<Animator>().Play()\n"
            f"20. preload('res://x.gd') → [SerializeField] prefab reference\n\n"

            f"OUTPUT FORMAT:\n"
            f"- One complete .cs file\n"
            f"- Allman brace style (braces on new line)\n"
            f"- [SerializeField] private for all inspector fields\n"
            f"- PascalCase methods, camelCase fields\n"
            f"- No async/await — use Coroutines\n"
            f"- Old Input system only\n"
            f"- Add a comment on any line where manual Unity editor setup is required: // TODO: wire in Inspector\n"
            f"- Add a comment where scene hierarchy must be built manually: // TODO: create GameObject hierarchy\n"
            f"- Add a comment where an Animator state machine is needed: // TODO: create Animator controller\n\n"

            f"IMPORTANT: Do not skip logic. Convert everything in the source file.\n"
            f"If something has no direct Unity equivalent, implement the closest "
            f"approximation and mark it // MANUAL REVIEW\n\n"

            f"--- SOURCE ---\n{content[:3000]}\n--- END SOURCE ---\n\n"
            f"Output the complete C# file. Nothing before or after it."
        )

        profile = AGENT_PROFILES["unity"]
        route_result = route(f"scaffold unity cs from {gd_file.name}")

        with Spinner(f"converting {gd_file.name}…"):
            result = run_agent(
                session_id=route_result["session_id"],
                system_prompt=profile["system_prompt"],
                task=task,
                agent_name=profile["name"],
                tool_whitelist=profile["tool_whitelist"],
                grammar_path=None,
            )

        if result["ok"]:
            out_path = cs_out / f"{name}.cs"
            print(f"  {C.GREEN}✓{C.RESET}  Generated {name}.cs")
            print(f"\n  {C.DIM}--- preview (first 10 lines) ---{C.RESET}")
            for line in result["result"].splitlines()[:10]:
                print(f"  {line}")
            print(f"  {C.DIM}...\n{C.RESET}")

            save = input(f"  Save to {out_path.name}? [y/N] ").strip().lower()
            if save == "y":
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(result["result"], encoding="utf-8")
                print(f"  {C.GREEN}Saved → {out_path}{C.RESET}\n")
            else:
                print(f"  {C.DIM}Skipped.{C.RESET}\n")
        else:
            print(f"  {C.RED}✗{C.RESET}  Failed: {result['result'][:80]}\n")
            skip = input("  Skip and continue? [Y/n] ").strip().lower()
            if skip == "n":
                break


def _build_inventory(engine: str) -> str:
    """Build a compact file inventory to inject into the prompt."""
    cfg = load_config()
    active_root = Path(cfg["project"]) if cfg.get("project") else None
    active_engine = cfg.get("engine", "general")

    if engine in ("godot", "general"):
        root = active_root if (active_root and active_engine == "godot") else GODOT_SCRIPTS
        ext = "*.gd"
        label = f"{root.name} (Godot 3.5)"
    elif engine == "unity":
        root = active_root if (active_root and active_engine == "unity") else (UNITY_SCRIPTS / "Scripts" if (UNITY_SCRIPTS / "Scripts").exists() else UNITY_SCRIPTS)
        ext = "*.cs"
        label = f"{root.name} (Unity 2018.2)"
    else:
        return ""

    if not root.exists():
        return ""

    files = list(root.rglob(ext))[:30]
    if not files:
        return ""

    lines = [f"Project inventory — {label}:"]
    for f in sorted(files):
        try:
            size = f.stat().st_size
            lines.append(f"  {f.relative_to(root)}  ({size:,} bytes)")
        except Exception:
            lines.append(f"  {f.relative_to(root)}")

    return "\n".join(lines)


LAST_CHAT_STATE = {"reply": ""}

def quick_reply(text: str) -> str | None:
    """Fast deterministic response for greetings, small talk, and meta-questions (0ms, 0 tokens)."""
    global LAST_CHAT_STATE
    clean = re.sub(r"[^\w\s]", "", text.strip().lower())
    if not clean:
        return None
    words = clean.split()
    actions = {"fix", "create", "scaffold", "make", "write", "check", "review", "audit", "explain", "debug", "test", "run", "convert", "code", "script"}
    if any(w in actions for w in words) or any(ext in text.lower() for ext in (".gd", ".cs", ".tscn", ".unity", ".py", ".json", ".log")):
        LAST_CHAT_STATE["reply"] = ""
        return None

    # Knock-knock joke dialogue state machine
    if clean in ("knock knock", "knock knock joke"):
        LAST_CHAT_STATE["reply"] = "Who's there?"
        return "Who's there?"

    if LAST_CHAT_STATE.get("reply") == "Who's there?":
        reply = f"{text.strip()} who?"
        LAST_CHAT_STATE["reply"] = reply
        return reply

    if LAST_CHAT_STATE.get("reply", "").endswith(" who?"):
        LAST_CHAT_STATE["reply"] = ""
        return "😄 Good one! What can I help you build or fix in your project?"

    LAST_CHAT_STATE["reply"] = ""

    # Common short replies / affirmations
    SHORT_CHAT = {
        "ok": "Got it. What would you like to work on next?",
        "okay": "Sounds good. What's next?",
        "cool": "Indeed! Let me know if you need code changes or an audit.",
        "sure": "Ready when you are. Tell me what to inspect or generate.",
        "yes": "Great! Give me the command or file to work with.",
        "no": "Understood. Let me know whenever you're ready.",
        "haha": "😄 Let me know what you'd like to work on next!",
        "hahaha": "😄 Let me know what you'd like to work on next!",
        "lol": "😄 What can I do for you today?",
    }
    if clean in SHORT_CHAT:
        return SHORT_CHAT[clean]

    if clean in ("can i ask you something", "can i ask a question", "can i ask you a question", "can i ask something"):
        return "Of course! What are you working on?"
    if clean in ("who are you", "what are you"):
        return "I am your local game-dev agent for Godot 3.5 and Unity 2018.2."
    if clean in ("what can you do", "help me"):
        return "I can scan APIs, explain architecture, scaffold scripts, fix bugs, and migrate Godot to Unity. Type 'help' for commands."
    if clean in ("thank you", "thanks", "thx"):
        return "You're welcome! Let me know what you need next."
    if (len(words) <= 3 and words[0] in ("hi", "hello", "hey", "hola", "yo", "sup", "howdy", "greetings")) or clean in ("good morning", "good afternoon", "good evening", "whats up", "what is up", "how are you"):
        cfg = load_config()
        p_name = Path(cfg.get("project", "")).name or "no project"
        eng = cfg.get("engine", "general")
        return f"Hello! Ready to assist with {p_name} ({eng}).\n     {C.DIM}Try: scan, explain <file>, fix <issue>, scaffold <name>, /init, /models{C.RESET}"

    return None

def run_team(raw_args: str):
    """Run multi-agent task either sequentially or concurrently via ThreadPoolExecutor."""
    import concurrent.futures
    from agents.profiles import load_custom_agents
    load_custom_agents()

    cfg = load_config()
    mode = cfg.get("exec_mode", "sequential")
    active_engine = cfg.get("engine", "unity")

    parts = raw_args.strip().split(maxsplit=1)
    if not parts or not parts[0]:
        print(f"\n  {C.YELLOW}Usage: /team [agent1,agent2,...] <task>{C.RESET}\n")
        return

    cand_agents = [a.strip() for a in parts[0].split(",") if a.strip()]
    if cand_agents and all(a in AGENT_PROFILES for a in cand_agents) and len(parts) > 1:
        target_agents = cand_agents
        task_prompt = parts[1]
    else:
        target_agents = [active_engine, "build"] if active_engine in AGENT_PROFILES else ["general", "build"]
        task_prompt = raw_args.strip()

    rule(f"team ({mode}) · {','.join(target_agents)}")
    print(f"  {C.DIM}Task: {task_prompt}{C.RESET}\n")

    active_sid = get_active_session()
    def execute_agent(agent_key: str, prompt_text: str):
        profile = AGENT_PROFILES[agent_key]
        active_tools = [t for t in profile["tool_whitelist"] if not t.startswith("write_")]
        sid = active_sid if mode != "parallel" else f"{active_sid}-{agent_key}"
        return run_agent(
            session_id=sid,
            system_prompt=profile["system_prompt"],
            task=prompt_text,
            agent_name=profile["name"],
            tool_whitelist=active_tools,
        )

    if mode == "parallel":
        print(f"  {C.CYAN}⚡ Running {len(target_agents)} agents in parallel (ThreadPoolExecutor)...{C.RESET}\n")
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(target_agents)) as ex:
            futures = {ex.submit(execute_agent, k, task_prompt): k for k in target_agents}
            for f in concurrent.futures.as_completed(futures):
                k = futures[f]
                prof = AGENT_PROFILES[k]
                try:
                    res = f.result()
                    rule(f"{prof['name']} (done)")
                    ans = res.get("result") or res.get("final_answer") or res.get("error") or "No response"
                    print(f"\n{ans}\n")
                except Exception as e:
                    print(f"\n  {C.RED}✗ {prof['name']} error: {e}{C.RESET}\n")
    else:
        print(f"  {C.CYAN}→ Running {len(target_agents)} agents sequentially (Pipeline)...{C.RESET}\n")
        context = ""
        for k in target_agents:
            prof = AGENT_PROFILES[k]
            prompt = f"{task_prompt}\n\n[Findings from prior team member]:\n{context}" if context else task_prompt
            rule(prof["name"])
            try:
                res = execute_agent(k, prompt)
                ans = res.get("result") or res.get("final_answer") or res.get("error") or "No response"
                print(f"\n{ans}\n")
                context += f"\n[{prof['name']}]: {ans[:500]}\n"
            except Exception as e:
                print(f"\n  {C.RED}✗ {prof['name']} error: {e}{C.RESET}\n")

# ── Core task runner ──────────────────────────────────────────────────────────
def run_task(user_input: str):
    if user_input.lower().startswith(("team ", "/team ")):
        run_team(user_input.split(maxsplit=1)[1] if " " in user_input else "")
        return

    reply = quick_reply(user_input)
    if reply:
        print(f"\n  {C.GREEN}●{C.RESET}  {reply}\n")
        return

    # Natural language model install/search detection
    # e.g. "Can you install deepseek", "install model qwen", "search model llama"
    model_match = re.search(
        r'(?:can you\s+)?(?:install|download|get|search|find|lookup)\s+(?:a\s+)?(?:new\s+)?model\s+(?:named\s+|called\s+)?["\']?([^"\']+)["\']?|'
        r'(?:can you\s+)?(?:install|download|search|find)\s+["\']?([\w\-./]+)["\']?\s+model|'
        r'(?:can you\s+)?install\s+["\']?([\w\-./]+)["\']?\s*$',
        user_input,
        re.IGNORECASE
    )
    if model_match:
        query = (model_match.group(1) or model_match.group(2) or model_match.group(3) or "").strip()
        if query and not any(ext in query.lower() for ext in (".gd", ".cs", ".tscn", ".unity", ".py")):
            search_and_install_model(query)
            return

    t_start = time.monotonic()
    cfg = load_config()
    active_root = Path(cfg["project"]) if cfg.get("project") else None
    active_engine = cfg.get("engine", "general")

    # Match filenames or paths in user input
    cand_match = re.search(
        r'["\']([^"\']+\.(?:gd|cs|tscn|unity|log|txt))["\']|(?:^|\s)([\w.\-/\\]+\.(?:gd|cs|tscn|unity|log|txt))\b',
        user_input,
    )
    file_path = None
    file_content = None

    if cand_match:
        raw = (cand_match.group(1) or cand_match.group(2)).strip()
        cand = Path(raw)
        if cand.is_absolute() and cand.exists():
            file_path = str(cand)
        elif active_root and (active_root / raw).exists():
            file_path = str((active_root / raw).resolve())
        elif active_root and active_root.exists():
            found = list(active_root.rglob(cand.name))
            if found:
                file_path = str(found[0].resolve())
        if not file_path:
            for root in [GODOT_SCRIPTS, UNITY_SCRIPTS, UNITY_SCRIPTS / "Scripts"]:
                cand_p = root / raw.lstrip("/")
                if cand_p.exists():
                    file_path = str(cand_p.resolve())
                    break
        if file_path and Path(file_path).exists():
            try:
                file_content = Path(file_path).read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                print(f"\n  {C.YELLOW}Could not load {file_path}: {e}{C.RESET}\n")
        elif active_root and not cand.is_absolute():
            default_dir = (
                (active_root / "Assets" / "Scripts")
                if (active_root / "Assets" / "Scripts").exists()
                else (active_root / "scripts" if (active_root / "scripts").exists() else active_root)
            )
            file_path = str((default_dir / cand.name).resolve())

    active_sid = get_active_session()

    # Route
    with Spinner("routing…"):
        route_result = route(user_input, session_id=active_sid)

    engine = route_result["engine"]
    task   = route_result["task"]
    method = route_result["method"]

    # Fallback to file extension or active project engine
    if file_path:
        if file_path.endswith(".cs") and engine != "unity":
            engine = "unity"
        elif file_path.endswith(".gd") and engine != "godot":
            engine = "godot"
    if engine == "general" and active_engine in ("unity", "godot") and (file_path or task in ("edit", "scaffold", "debug")):
        engine = active_engine

    print(f"\n  {C.DIM}engine:{engine}  task:{task}  via:{method}{C.RESET}")

    if file_content:
        print(f"  {C.DIM}file: {Path(file_path).name} ({len(file_content):,} chars){C.RESET}")
    elif file_path and task == "scaffold":
        print(f"  {C.DIM}target: {Path(file_path).name}{C.RESET}")

    # Fast path: direct validator for review
    if task == "review" and file_content and file_path:
        if engine == "godot" and file_path.endswith(".gd"):
            _show_validation(check_godot35_apis(file_content), file_path, "Godot 3.5")
            return
        elif engine == "unity" and file_path.endswith(".cs"):
            _show_validation(check_unity2018_apis(file_content), file_path, "Unity 2018.2")
            return

    agent_key = engine if engine in AGENT_PROFILES else None
    if not agent_key:
        print(f"\n  {C.YELLOW}No specialized agent for '{engine}'. Be more specific about Godot or Unity.{C.RESET}\n")
        return

    if not check_server():
        print(f"\n  {C.RED}llama-server not running.{C.RESET}  Start: {C.DIM}bash ~/agent_team/scripts/launch_server.sh &{C.RESET}\n")
        return

    profile = AGENT_PROFILES[agent_key]

    # Memory context
    mem_context = ""
    if active_root and (active_root / "MEMORY.md").exists():
        try:
            mem_text = (active_root / "MEMORY.md").read_text(encoding="utf-8").strip()
            if mem_text:
                mem_context = f"\n\n--- PROJECT MEMORY ({active_root.name}) ---\n{mem_text[:2000]}\n--- END MEMORY ---"
        except Exception:
            pass

    # Build enriched prompt
    if task == "scaffold":
        file_content = None
    if file_content and len(file_content) < 6000:
        enriched = (
            f"{user_input}{mem_context}\n\n--- EXISTING FILE: {file_path} ---\n{file_content}\n--- END EXISTING FILE ---\n\n"
            f"Existing file content is provided above. "
            f"Write the complete updated code and call write_cs_dry or write_gd_dry with 'path' and 'content'."
        )
    elif file_content:
        enriched = (
            f"{user_input}{mem_context}\n\nFile at {file_path} ({len(file_content)} chars) — "
            f"use read_gd/read_cs to load it."
        )
    elif task == "scaffold" and not file_content:
        inventory = _build_inventory(engine)
        inv_str = f"\n\n{inventory}" if inventory else ""
        target_hint = f"\nTarget file: {file_path}" if file_path else ""
        enriched = f"{user_input}{mem_context}{inv_str}{target_hint}"
    elif task == "explain" and not file_content and any(k in user_input.lower() for k in ("project", "inventory", "files", "architecture", "overview", "structure")):
        inventory = _build_inventory(engine)
        inv_str = f"\n\n{inventory}" if inventory else ""
        enriched = f"{user_input}{mem_context}{inv_str}"
    else:
        enriched = f"{user_input}{mem_context}"

    rule(profile["name"])
    print()

    # Monkey-patch the loop to show live steps
    import harness.loop as loop_mod
    orig_call = loop_mod.call_llm
    orig_tool = loop_mod.TOOL_REGISTRY.copy()
    step_counter = [0]

    def live_call_llm(messages, **kwargs):
        with Spinner(f"step {step_counter[0]+1} · thinking…"):
            result = orig_call(messages, **kwargs)
        # Parse and display the thought
        from harness.loop import parse_react_step
        parsed = parse_react_step(result["content"])
        if parsed["thought"]:
            print_thought(parsed["thought"][:120])
        if parsed["action"] and parsed["action"].lower() not in ("none","null"):
            print_action(parsed["action"], parsed["args"])
        elif parsed["final_answer"]:
            pass  # shown after
        step_counter[0] += 1
        return result

    # Wrap tools to show results
    def make_live_tool(name, fn):
        def wrapped(**kwargs):
            try:
                r = fn(**kwargs)
            except Exception as e:
                print_result_err(f"{name} → {e}")
                return {"ok": False, "error": str(e)}
            if r is None:
                print_result_err(f"{name} → returned None")
                return {"ok": False, "error": "tool returned None"}
            if r.get("ok"):
                lines_n = len(r.get("fixed_content", r.get("content", "") or "").splitlines())
                summary = (
                    f"saved to disk ({lines_n} lines)" if r.get("written")
                    else f"preview generated ({lines_n} lines)" if ("fixed_content" in r or "content" in r) and not r.get("violations")
                    else f"{r.get('line_count','?')} lines loaded" if "line_count" in r
                    else "clean (0 violations)" if "passed" in r and r.get("passed")
                    else f"{r.get('violation_count','?')} violations" if "violation_count" in r
                    else f"{r.get('error_count','?')} errors" if "error_count" in r
                    else "ok"
                )
                print_result_ok(f"{name} → {summary}")
            else:
                print_result_err(f"{name} → {r.get('error','failed')}")
            return r
        return wrapped

    loop_mod.call_llm = live_call_llm
    for name, fn in orig_tool.items():
        loop_mod.TOOL_REGISTRY[name] = make_live_tool(name, fn)

    # Collect active skills prompt injections
    skills_context = ""
    for skill in get_active_skills():
        skill_file = find_skill_file(skill)
        if skill_file and skill_file.exists():
            try:
                skills_context += f"\n\n--- SKILL ({skill.upper()}) ---\n{skill_file.read_text(encoding='utf-8').strip()}\n--- END SKILL ---"
            except Exception:
                pass

    active_system_prompt = profile["system_prompt"] + skills_context
    active_tools = [t for t in profile["tool_whitelist"] if not t.startswith("write_")] if task in ("explain", "review") else profile["tool_whitelist"]

    try:
        result = run_agent(
            session_id=route_result["session_id"],
            system_prompt=active_system_prompt,
            task=enriched,
            agent_name=profile["name"],
            tool_whitelist=active_tools,
            grammar_path=profile.get("grammar_path"),
        )
    except KeyboardInterrupt:
        print(f"\n\n  {C.YELLOW}● Cancelled.{C.RESET}\n")
        return
    finally:
        # Restore originals
        loop_mod.call_llm = orig_call
        loop_mod.TOOL_REGISTRY.clear()
        loop_mod.TOOL_REGISTRY.update(orig_tool)

    elapsed = time.monotonic() - t_start

    if result["ok"]:
        print_final(profile["name"], result["result"], result["steps"], elapsed)
    elif "Cancelled" in result.get("result", ""):
        print(f"\n  {C.YELLOW}● Cancelled.{C.RESET}  {C.DIM}{result['steps']} step{'s' if result['steps']!=1 else ''} completed{C.RESET}\n")
    else:
        print_fail(result["result"], result["steps"])

def _show_validation(result: dict, file_path: str, label: str):
    name = Path(file_path).name
    rule(f"validate · {label}")
    if result["passed"]:
        print(f"\n  {C.GREEN}✓  {name}{C.RESET}  clean\n")
    else:
        c = result["violation_count"]
        print(f"\n  {C.RED}✗  {name}{C.RESET}  {C.BOLD}{c} violation{'s' if c!=1 else ''}{C.RESET}\n")
        for v in result["violations"]:
            print(f"  {C.DIM}L{v['line']:<6}{C.RESET}{C.YELLOW}{v['violation']}{C.RESET}")
            print(f"          {C.DIM}{v['text']}{C.RESET}")
        print()

# ── History ───────────────────────────────────────────────────────────────────
def show_history():
    import sqlite3
    db = Path.home() / "agent_team" / "traces.db"
    if not db.exists():
        print(f"\n  {C.DIM}No history yet.{C.RESET}\n")
        return
    conn = sqlite3.connect(str(db))
    rows = conn.execute("""
        SELECT s.task_input, s.status, s.created_at, COUNT(t.id) as steps
        FROM sessions s LEFT JOIN traces t ON t.session_id = s.id
        GROUP BY s.id ORDER BY s.created_at DESC LIMIT 15
    """).fetchall()
    conn.close()
    rule("history")
    for task, status, ts, steps in rows:
        dt = datetime.fromtimestamp(ts).strftime("%H:%M")
        icon = C.GREEN+"✓" if status=="done" else C.YELLOW+"~"
        print(f"  {icon}{C.RESET}  {C.DIM}{dt}{C.RESET}  {task[:64]}")
    print()

# ── Help ──────────────────────────────────────────────────────────────────────
def show_help():
    print(f"""
  {C.BOLD}Built-in commands{C.RESET}
  {C.CYAN}init{C.RESET}                 scrape active project and generate MEMORY.md
  {C.CYAN}project [path]{C.RESET}   show or switch active project directory
  {C.CYAN}remember <note>{C.RESET}  append note or rule to active project MEMORY.md
  {C.CYAN}memory{C.RESET}           view active project MEMORY.md
  {C.CYAN}/models{C.RESET}              list installed GGUF models in ~/models
  {C.CYAN}/new-model [url]{C.RESET}   install new GGUF model (preset menu or URL)
  {C.CYAN}/search-model <q>{C.RESET}   search HuggingFace for GGUF models & install
  {C.CYAN}/agents{C.RESET}              list local specialist and sub-agents
  {C.CYAN}/new-agent{C.RESET}           create new local specialist or sub-agent
  {C.CYAN}plugins{C.RESET}              list loaded tool plugins and skills
  {C.CYAN}plugin install <url>{C.RESET} install plugin from GitHub URL or local path
  {C.CYAN}/ponytail{C.RESET}            toggle ponytail mode (minimal diffs, zero bloat)
  {C.CYAN}/mode [mode]{C.RESET}         switch multi-agent mode (parallel or sequential)
  {C.CYAN}/team [agents] <task>{C.RESET} run multi-agent task concurrently or sequentially
  {C.CYAN}scan [engine]{C.RESET}        scan files for Godot 3.5 / Unity 2018.2 violations
  {C.CYAN}migrate{C.RESET}              convert slide-x GDScript files to NONNULL C#
  {C.CYAN}/sessions{C.RESET}            list chat sessions
  {C.CYAN}/new [name]{C.RESET}          start clean chat session
  {C.CYAN}/resume <id>{C.RESET}         resume previous session
  {C.CYAN}/branch [name]{C.RESET}       branch conversation from active session
  {C.CYAN}/delete <id>{C.RESET}         delete chat session and history
  {C.CYAN}status{C.RESET}               check llama-server
  {C.CYAN}history{C.RESET}              recent sessions
  {C.CYAN}clear{C.RESET}                clear screen
  {C.CYAN}help{C.RESET}                 this message
  {C.CYAN}quit{C.RESET}                 exit

  {C.BOLD}Natural tasks{C.RESET}
  Can you install deepseek — search HuggingFace and pick a GGUF to install
  rewrite PlayerController.cs — convert from melee brawler to third-person shooter
  scaffold GunController.cs — attaches gun to hand bone
  review scripts/player.gd for Godot 3.5 issues
  fix enemy AI not chasing player
  explain FlockManager.gd
""")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) > 1:
        args = sys.argv[1:]
        if args[0] == "plugin" and len(args) > 2 and args[1] in ("install", "add"):
            install_plugin(args[2])
            return
        elif args[0] in ("plugins", "plugin"):
            list_plugins()
            return
        elif args[0] in ("init", "/init"):
            init_codebase()
            return
        elif args[0] in ("agents", "/agents"):
            list_agents()
            return
        elif args[0] in ("new-agent", "/new-agent"):
            create_agent_wizard()
            return
        elif args[0] in ("models", "/models") and len(args) == 1:
            list_models()
            return
        elif args[0] in ("search-model", "/search-model", "find-model", "/find-model"):
            search_and_install_model(args[1] if len(args) > 1 else "")
            return
        elif args[0] in ("models", "model", "new-model", "/new-model"):
            if len(args) > 1 and args[1] in ("switch", "use", "set"):
                switch_model(args[2] if len(args) > 2 else "")
            elif len(args) > 2 and args[1] in ("add", "install", "new"):
                url = args[3] if len(args) > 3 else args[2]
                name = args[2] if len(args) > 3 else ""
                add_model(url, custom_name=name)
            else:
                add_model(args[1] if len(args) > 1 else "")
            return
        elif args[0] in ("sessions", "/sessions", "session", "/session") and len(args) == 1:
            list_sessions_cli()
            return
        elif args[0] in ("new", "/new") or (args[0] in ("session", "/session") and len(args) > 1 and args[1] in ("new", "create")):
            name = args[2] if len(args) > 2 else (args[1] if len(args) > 1 and args[0] in ("new", "/new") else "")
            new_session_cli(name)
            return
        elif args[0] in ("resume", "/resume") or (args[0] in ("session", "/session") and len(args) > 1 and args[1] in ("resume", "switch")):
            target = args[2] if len(args) > 2 else (args[1] if len(args) > 1 else "")
            resume_session_cli(target)
            return
        elif args[0] in ("branch", "/branch") or (args[0] in ("session", "/session") and len(args) > 1 and args[1] == "branch"):
            raw = " ".join(args[2:]) if len(args) > 2 else (args[1] if len(args) > 1 and args[0] in ("branch", "/branch") else "")
            branch_session_cli(raw)
            return
        elif args[0] in ("delete", "/delete", "del", "/del") or (args[0] in ("session", "/session") and len(args) > 1 and args[1] in ("del", "delete")):
            target = args[2] if len(args) > 2 else (args[1] if len(args) > 1 else "")
            delete_session_cli(target)
            return
        # Direct CLI: bus3f-tui "model_name" "https://...gguf" or bus3f-tui "https://...gguf"
        elif any(".gguf" in a or a.startswith("http") for a in args):
            url = next(a for a in args if a.startswith("http") or ".gguf" in a)
            other = [a for a in args if a != url]
            name = other[0] if other else ""
            add_model(url, custom_name=name)
            return

    init_db()
    load_plugins()
    ptk_session = get_prompt_session()
    if not ptk_session:
        setup_readline()
    banner()

    if check_server():
        print(f"  {C.GREEN}●{C.RESET}  llama-server  {C.DIM}:8080{C.RESET}\n")
    else:
        print(f"  {C.YELLOW}●{C.RESET}  llama-server  {C.DIM}not running{C.RESET}\n")

    while True:
        try:
            cfg = load_config()
            proj_path = Path(cfg["project"]) if cfg.get("project") else Path.cwd()
            proj_name = "local" if proj_path in (Path.home(), Path("/")) else proj_path.name
            eng = cfg.get("engine", "general")
            exec_mode = cfg.get("exec_mode", "sequential")
            active_sid = get_active_session()
            skills = get_active_skills()
            skill_tag = f" · {','.join(skills)}" if skills else ""
            prompt_str = f"{C.DIM}[{proj_name} · {eng} · {exec_mode} · {active_sid}{skill_tag}]{C.RESET} {C.CYAN}{C.BOLD}>{C.RESET} "
            if ptk_session:
                user_input = ptk_session.prompt(ANSI(prompt_str)).strip()
            else:
                user_input = input(prompt_str).strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {C.DIM}bye{C.RESET}\n")
            break

        if not user_input:
            continue

        try:
            cmd = user_input.lower()
            if cmd in ("quit", "exit", "q"):
                print(f"\n  {C.DIM}bye{C.RESET}\n")
                break
            elif cmd in ("help", "/help", "/", "/?"):
                show_help()
            elif cmd in ("/sessions", "sessions", "/session", "session"):
                list_sessions_cli()
            elif cmd.startswith(("/session new ", "session new ", "/new ", "new session ")):
                name = user_input.split(maxsplit=2)[-1]
                new_session_cli(name)
            elif cmd in ("/new", "new"):
                new_session_cli("")
            elif cmd.startswith(("/session resume ", "session resume ", "/resume ", "resume ")):
                target = user_input.split()[-1]
                resume_session_cli(target)
            elif cmd in ("/resume", "resume"):
                resume_session_cli("")
            elif cmd.startswith(("/session branch ", "session branch ", "/branch ", "branch ")):
                raw = user_input.split(maxsplit=2)[2] if cmd.startswith(("session branch ", "/session branch ")) else user_input.split(maxsplit=1)[1]
                branch_session_cli(raw)
            elif cmd in ("/branch", "branch"):
                branch_session_cli("")
            elif cmd.startswith(("/session delete ", "session delete ", "/session del ", "session del ", "/delete ", "delete ", "/del ", "del ")):
                target = user_input.split()[-1]
                delete_session_cli(target)
            elif cmd in ("/mode", "mode", "/parallel", "parallel", "/sequential", "sequential") or cmd.startswith(("/mode ", "mode ")):
                parts = user_input.split()
                target = parts[1] if len(parts) > 1 else ("parallel" if "parallel" in cmd else "sequential" if "sequential" in cmd else "")
                toggle_exec_mode(target)
            elif cmd.startswith(("/team ", "team ")):
                raw_args = user_input.split(maxsplit=1)[1]
                run_team(raw_args)
            elif cmd in ("init", "/init"):
                init_codebase()
            elif cmd in ("/agents", "agents"):
                list_agents()
            elif cmd in ("/new-agent", "new-agent", "agent new", "agent add"):
                create_agent_wizard()
            elif cmd in ("/models", "models"):
                list_models()
            elif cmd.startswith(("model switch ", "/model switch ", "model use ", "/model use ")):
                target = user_input.split()[-1]
                switch_model(target)
            elif cmd.startswith(("/search-model ", "search-model ", "/find-model ", "find-model ")):
                query = user_input.split(maxsplit=1)[1]
                search_and_install_model(query)
            elif cmd in ("/new-model", "new-model") or cmd.startswith(("/new-model ", "new-model ", "model add ")):
                raw_args = user_input.split()[1:]
                if raw_args and raw_args[0] == "add":
                    raw_args = raw_args[1:]
                if len(raw_args) >= 2:
                    url = next((a for a in raw_args if a.startswith("http") or ".gguf" in a), raw_args[-1])
                    name = next((a for a in raw_args if a != url), "")
                    add_model(url, custom_name=name)
                elif len(raw_args) == 1:
                    add_model(raw_args[0])
                else:
                    add_model()
            elif cmd in ("/ponytail", "ponytail"):
                toggle_skill("ponytail")
            elif cmd.startswith(("/grammar ", "grammar ")):
                target = user_input.split(maxsplit=1)[1].strip()
                cfg = load_config()
                if target in ("reset", "default", "none"):
                    cfg.pop("grammar_plugin", None)
                    print(f"\n  {C.GREEN}✓{C.RESET} Reset grammar to default C# Tree-sitter (process-isolated)\n")
                else:
                    cfg["grammar_plugin"] = target
                    print(f"\n  {C.GREEN}✓{C.RESET} Active Tree-sitter grammar plugin: {C.BOLD}{target}{C.RESET} (isolated process sandbox)\n")
                save_config(cfg)
            elif cmd in ("plugins", "plugin list"):
                list_plugins()
            elif cmd.startswith("plugin install ") or cmd.startswith("plugin add "):
                parts = user_input.split(maxsplit=2)
                if len(parts) > 2:
                    install_plugin(parts[2])
                else:
                    print(f"\n  {C.YELLOW}Usage: plugin install <github_url_or_path>{C.RESET}\n")
            elif cmd.startswith("skill "):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    toggle_skill(parts[1].strip())
            elif cmd == "project" or cmd.startswith("project "):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    set_project(parts[1].strip())
                else:
                    cfg = load_config()
                    p = cfg.get("project", "none")
                    eng = cfg.get("engine", "none")
                    print(f"\n  Active project: {C.BOLD}{p}{C.RESET}  {C.DIM}({eng}){C.RESET}\n")
            elif cmd.startswith("remember ") or cmd.startswith("memo "):
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    append_memory(parts[1].strip())
            elif cmd == "memory":
                cfg = load_config()
                p = Path(cfg["project"]) if cfg.get("project") else None
                mem_file = p / "MEMORY.md" if p else None
                if mem_file and mem_file.exists():
                    print(f"\n{C.DIM}── {p.name}/MEMORY.md ────────────────────{C.RESET}\n" + mem_file.read_text(encoding="utf-8") + f"\n{C.DIM}──────────────────────────────────────────{C.RESET}\n")
                else:
                    print(f"\n  {C.DIM}No MEMORY.md found for current project.{C.RESET}\n")
            elif cmd == "status":
                ok = check_server()
                print(f"\n  {'✓' if ok else '✗'}  llama-server {'running' if ok else 'not running'}\n")
            elif cmd == "clear":
                os.system("clear")
                banner()
            elif cmd == "history":
                show_history()
            elif cmd == "scan":
                run_scan()
            elif cmd == "scan godot":
                run_scan("godot")
            elif cmd == "scan unity":
                run_scan("unity")
            elif cmd == "migrate":
                run_migration()
            else:
                run_task(user_input)
        except KeyboardInterrupt:
            print(f"\n  {C.YELLOW}● Cancelled.{C.RESET}\n")
            continue

if __name__ == "__main__":
    main()
