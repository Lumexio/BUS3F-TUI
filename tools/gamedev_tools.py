# ~/agent_team/tools/gamedev_tools.py
"""
Universal developer agent tools. All file operations are path-escape-safe.
All write operations are dry-run first — no file is modified without explicit commit=True.
All tools return dicts with at least {"ok": bool, "error": str|None}.
"""

from __future__ import annotations
import os
import re
import json
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

def _safe_path(raw: str, must_exist: bool = True) -> Path:
    """Resolve path, refuse traversal. Allows HOME, cwd/project, /tmp, and system mounts."""
    p = Path(raw).expanduser().resolve()
    allowed_roots = [
        Path.home().resolve(),
        Path.cwd().resolve(),
        Path("/tmp").resolve(),
    ]
    for mount in ("/mnt", "/media", "/run/media", "/Volumes"):
        mp = Path(mount)
        if mp.exists():
            allowed_roots.append(mp.resolve())

    def _is_contained(child: Path, parent: Path) -> bool:
        try:
            return child.is_relative_to(parent)
        except AttributeError:
            return str(child).startswith(str(parent))

    if not any(_is_contained(p, root) for root in allowed_roots):
        raise ValueError(f"Path escape rejected: {p}")
    if must_exist and not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    return p


def _normalize_code(content: str) -> str:
    """Normalize literal backslash-escapes from LLM JSON responses."""
    if not content:
        return content
    if "\\n" in content and (content.count("\\n") > content.count("\n")):
        content = content.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
        if '\\"' in content:
            content = content.replace('\\"', '"')
    return content


# ---------------------------------------------------------------------------
# Universal File Tools
# ---------------------------------------------------------------------------

def read_file(path: str) -> dict[str, Any]:
    """Generic file reader for code, configs, and assets."""
    try:
        p = _safe_path(path)
        content = p.read_text(encoding="utf-8", errors="replace")
        return {"ok": True, "path": str(p), "content": content, "error": None}
    except Exception as e:
        return {"ok": False, "content": None, "error": str(e)}


def list_dir(path: str, pattern: str = "*") -> dict[str, Any]:
    """List files in a directory matching a glob pattern."""
    try:
        p = _safe_path(path)
        if not p.is_dir():
            return {"ok": False, "error": f"Not a directory: {p}", "files": []}
        files = [str(f) for f in p.glob(pattern) if f.is_file()]
        return {"ok": True, "path": str(p), "files": sorted(files), "count": len(files), "error": None}
    except Exception as e:
        return {"ok": False, "files": [], "error": str(e)}


def write_file_dry(path: str = None, content: str = None, commit: bool = False) -> dict[str, Any]:
    """
    Write any source file safely with dry-run gating.
    If commit=False (default), returns preview without touching disk.
    If commit=True, writes to disk under path containment checks.
    """
    if not path:
        return {"ok": False, "error": "path is required for write_file_dry"}
    if content is None:
        return {"ok": False, "error": "content is required for write_file_dry"}
    content = _normalize_code(content)
    result: dict[str, Any] = {
        "ok": True,
        "path": path,
        "chars": len(content),
        "lines": len(content.splitlines()),
        "committed": commit,
        "preview": content[:300] + ("..." if len(content) > 300 else ""),
        "error": None,
    }
    if commit:
        try:
            p = _safe_path(path, must_exist=False)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
        except Exception as e:
            return {"ok": False, "committed": False, "error": str(e)}
    return result


def grep_file(path: str, pattern: str) -> dict[str, Any]:
    """Search for a regex pattern in a file, returning matching lines."""
    try:
        p = _safe_path(path)
        content = p.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        rx = re.compile(pattern, re.IGNORECASE)
        matches = []
        for i, line in enumerate(lines, 1):
            if rx.search(line):
                matches.append({"line": i, "text": line.strip()})
        return {
            "ok": True,
            "path": str(p),
            "match_count": len(matches),
            "matches": matches[:100],
            "error": None,
        }
    except Exception as e:
        return {"ok": False, "matches": [], "error": str(e)}


# ---------------------------------------------------------------------------
# Log & Error Inspection Tools
# ---------------------------------------------------------------------------

def read_log(path: str, max_lines: int = 500) -> dict[str, Any]:
    """Read a build or runtime log file, returning up to max_lines from the end."""
    try:
        p = _safe_path(path)
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
        tail = lines[-max_lines:] if len(lines) > max_lines else lines
        return {
            "ok": True,
            "path": str(p),
            "total_lines": len(lines),
            "returned_lines": len(tail),
            "content": "\n".join(tail),
            "error": None,
        }
    except Exception as e:
        return {"ok": False, "content": None, "error": str(e)}


def grep_error(path: str) -> dict[str, Any]:
    """Extract error and warning lines from any build or runtime log."""
    try:
        p = _safe_path(path)
        content = p.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()

        errors = []
        warnings = []

        error_patterns = [
            r'\berror\b', r'\bERROR\b', r'Error:', r'error CS', r'Parse Error',
            r'FAILED', r'failed', r'Exception', r'cannot', r'undeclared', r'Traceback',
        ]
        warning_patterns = [
            r'\bwarning\b', r'\bWARNING\b', r'Warning:', r'warning CS',
        ]

        for i, line in enumerate(lines, 1):
            if any(re.search(pat, line) for pat in error_patterns):
                errors.append({"line": i, "text": line.strip()})
            elif any(re.search(pat, line) for pat in warning_patterns):
                warnings.append({"line": i, "text": line.strip()})

        return {
            "ok": True,
            "path": str(p),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings[:50],
            "error": None,
        }
    except Exception as e:
        return {"ok": False, "errors": [], "warnings": [], "error": str(e)}
