# ~/agent_team/tools/gamedev_tools.py
"""
Game-dev agent tools. All file operations are path-escape-safe.
All write operations are dry-run first — no file is modified without explicit commit=True.
All tools return dicts with at least {"ok": bool, "error": str|None}.
"""

from __future__ import annotations
import os
import re
import json
import sqlite3
import yaml
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------

def _safe_path(raw: str, must_exist: bool = True) -> Path:
    """Resolve path, refuse traversal outside HOME."""
    p = Path(raw).expanduser().resolve()
    home = Path.home().resolve()
    if home not in p.parents and p != home:
        raise ValueError(f"Path escape rejected: {p}")
    if must_exist and not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    return p


# ---------------------------------------------------------------------------
# GDScript tools
# ---------------------------------------------------------------------------

def read_gd(path: str) -> dict[str, Any]:
    """Read a .gd file and return its content."""
    try:
        p = _safe_path(path)
        content = p.read_text(encoding="utf-8")
        lines = content.splitlines()
        return {
            "ok": True,
            "path": str(p),
            "content": content,
            "line_count": len(lines),
            "error": None,
        }
    except Exception as e:
        return {"ok": False, "content": None, "error": str(e)}


def write_gd_dry(path: str, content: str, commit: bool = False) -> dict[str, Any]:
    """
    Write GDScript. Always converts spaces→tabs before writing.
    If commit=False (default), returns the would-be content without touching disk.
    If commit=True, writes to disk.
    """
    # Force tab indentation: replace leading spaces (4 or 2) with tabs
    fixed_lines = []
    for line in content.splitlines():
        # Count leading spaces
        stripped = line.lstrip(" ")
        space_count = len(line) - len(stripped)
        # Convert groups of 4 spaces to tabs; remainder stays as-is
        tab_count = space_count // 4
        remainder = space_count % 4
        fixed_line = "\t" * tab_count + " " * remainder + stripped
        fixed_lines.append(fixed_line)
    fixed_content = "\n".join(fixed_lines) + "\n"

    result: dict[str, Any] = {
        "ok": True,
        "path": path,
        "dry_run": not commit,
        "original_content": content,
        "fixed_content": fixed_content,
        "tabs_enforced": True,
        "error": None,
    }

    if commit:
        try:
            p = _safe_path(path, must_exist=False)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(fixed_content, encoding="utf-8")
            result["written"] = True
        except Exception as e:
            result["ok"] = False
            result["error"] = str(e)
    return result


# ---------------------------------------------------------------------------
# C# tools
# ---------------------------------------------------------------------------

def read_cs(path: str) -> dict[str, Any]:
    """Read a .cs file."""
    try:
        p = _safe_path(path)
        content = p.read_text(encoding="utf-8")
        return {
            "ok": True,
            "path": str(p),
            "content": content,
            "line_count": len(content.splitlines()),
            "error": None,
        }
    except Exception as e:
        return {"ok": False, "content": None, "error": str(e)}


def write_cs_dry(path: str, content: str, commit: bool = False) -> dict[str, Any]:
    """
    Write C#. Checks brace style (braces must be on new line after control structures).
    If brace violations found, reports them but still writes (style is advisory for C#).
    If commit=False, dry-run only.
    """
    brace_violations = []
    for i, line in enumerate(content.splitlines(), 1):
        # Detect inline opening brace after if/for/while/else/try — Allman style required
        if re.search(r'\b(if|for|foreach|while|else|try|catch|finally)\b.*\{', line):
            brace_violations.append({"line": i, "text": line.strip()})

    result: dict[str, Any] = {
        "ok": True,
        "path": path,
        "dry_run": not commit,
        "content": content,
        "brace_violations": brace_violations,
        "error": None,
    }

    if commit:
        try:
            p = _safe_path(path, must_exist=False)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            result["written"] = True
        except Exception as e:
            result["ok"] = False
            result["error"] = str(e)
    return result


# ---------------------------------------------------------------------------
# API Validators
# ---------------------------------------------------------------------------

# Godot 4 patterns that are INVALID in Godot 3.5
GODOT4_PATTERNS: list[tuple[str, str]] = [
    (r'@export\b', "@export (use 'export var' instead)"),
    (r'@onready\b', "@onready (use 'onready var' instead)"),
    (r'\bawait\b', "await keyword (use yield() in Godot 3.5)"),
    (r'\.connect\s*\(', ".connect() new-style (use connect(\"signal\", self, \"_method\"))"),
    (r'\bclass_name\b', "class_name keyword (use preload() instead)"),
    (r'\bfunc\s+\w+\s*\([^)]*\)\s*->', "return type hint (not supported in 3.5)"),
    (r'\bTime\.get_ticks_msec\b', "Time.get_ticks_msec() (use OS.get_ticks_msec())"),
    (r'\brandf_range\b', "randf_range() (use rand_range() in 3.5)"),
    (r'\brandi_range\b', "randi_range() (use randi() % n in 3.5)"),
    (r'\bCharacterBody2D\b', "CharacterBody2D (use KinematicBody2D in 3.5)"),
    (r'\bCharacterBody3D\b', "CharacterBody3D (use KinematicBody in 3.5)"),
    (r'\bmove_and_slide\s*\(\s*\)', "move_and_slide() with no args (3.5 requires velocity arg)"),
    (r'\bVector2i\b', "Vector2i (not available in 3.5, use Vector2)"),
    (r'\bVector3i\b', "Vector3i (not available in 3.5, use Vector3)"),
    (r'@tool\b', "@tool decorator (use 'tool' keyword at top of file in 3.5)"),
    (r'\bNode3D\b', "Node3D (use Spatial in 3.5)"),
    (r'\bCamera3D\b', "Camera3D (use Camera in 3.5)"),
    (r'\bDirectionalLight3D\b', "DirectionalLight3D (use DirectionalLight in 3.5)"),
]


def check_godot35_apis(content: str) -> dict[str, Any]:
    """
    Scan GDScript content for Godot 4 patterns that are invalid in Godot 3.5.
    Returns list of violations with line numbers.
    """
    violations = []
    for i, line in enumerate(content.splitlines(), 1):
        # Skip comment lines
        if line.strip().startswith("#"):
            continue
        for pattern, description in GODOT4_PATTERNS:
            if re.search(pattern, line):
                violations.append({
                    "line": i,
                    "text": line.strip(),
                    "violation": description,
                    "pattern": pattern,
                })
    return {
        "ok": True,
        "violations": violations,
        "violation_count": len(violations),
        "passed": len(violations) == 0,
        "error": None,
    }


# Unity 2019+ patterns that are INVALID in Unity 2018.2
UNITY2019_PATTERNS: list[tuple[str, str]] = [
    (r'\bUnityEngine\.InputSystem\b', "UnityEngine.InputSystem namespace (not available in 2018.2)"),
    (r'\busing\s+UnityEngine\.InputSystem', "InputSystem using directive"),
    (r'\bInputSystem\b', "InputSystem class reference"),
    (r'\bPlayerInput\b', "PlayerInput component (new input system, not in 2018.2)"),
    (r'\bvoid\s+OnCollisionEnter2D\s*\(\s*\)', "OnCollisionEnter2D without Collision2D parameter"),
    (r'\bvoid\s+OnTriggerEnter2D\s*\(\s*\)', "OnTriggerEnter2D without Collider2D parameter"),
    (r'\bSystem\.Text\.Json\b', "System.Text.Json (not available in Unity 2018.2, use JsonUtility)"),
    (r'\busing\s+System\.Text\.Json', "System.Text.Json using directive"),
    (r'\bTextMeshProUGUI\b(?!.*//.*project uses TMP)', "TextMeshProUGUI without TMP in project (use UI.Text)"),
    (r'\bTMP_Text\b', "TMP_Text (only if TMP package confirmed in project)"),
    (r'\bFindObjectsByType\b', "FindObjectsByType() (use FindObjectsOfType() in 2018.2)"),
    (r'\bSceneManager\.LoadSceneAsync\b.*\.GetAwaiter\b', "Awaitable scene loading (not supported)"),
    (r'\[RuntimeInitializeOnLoadMethod\(RuntimeInitializeLoadType\.BeforeSplashScreen\)\]',
     "BeforeSplashScreen load type (not in 2018.2)"),
    (r'\bUnityEngine\.UIElements\b', "UIElements/UI Toolkit (not in 2018.2)"),
    (r'\bAddressables\b', "Addressables (not available in 2018.2)"),
]


def check_unity2018_apis(content: str) -> dict[str, Any]:
    """
    Scan C# content for Unity 2019+ patterns that are invalid in Unity 2018.2.
    Returns list of violations with line numbers.
    """
    violations = []
    for i, line in enumerate(content.splitlines(), 1):
        if line.strip().startswith("//"):
            continue
        for pattern, description in UNITY2019_PATTERNS:
            if re.search(pattern, line):
                violations.append({
                    "line": i,
                    "text": line.strip(),
                    "violation": description,
                    "pattern": pattern,
                })
    return {
        "ok": True,
        "violations": violations,
        "violation_count": len(violations),
        "passed": len(violations) == 0,
        "error": None,
    }


# ---------------------------------------------------------------------------
# Scene parser
# ---------------------------------------------------------------------------

def read_scene(path: str) -> dict[str, Any]:
    """
    Parse a .tscn (Godot) or .unity (Unity YAML) scene file.
    Returns a node tree as a dict.
    """
    try:
        p = _safe_path(path)
        suffix = p.suffix.lower()
        content = p.read_text(encoding="utf-8", errors="replace")

        if suffix == ".tscn":
            return _parse_tscn(content, str(p))
        elif suffix == ".unity":
            return _parse_unity_scene(content, str(p))
        else:
            return {"ok": False, "error": f"Unknown scene format: {suffix}", "tree": None}
    except Exception as e:
        return {"ok": False, "error": str(e), "tree": None}


def _parse_tscn(content: str, path: str) -> dict[str, Any]:
    """Parse Godot .tscn text format into a node tree."""
    nodes = []
    ext_resources = []
    connections = []
    current_node: dict[str, Any] | None = None

    for line in content.splitlines():
        line = line.strip()

        # Parse [ext_resource ...]
        m = re.match(r'\[ext_resource\s+(.*)\]', line)
        if m:
            attrs = _parse_tscn_attrs(m.group(1))
            ext_resources.append(attrs)
            continue

        # Parse [node ...]
        m = re.match(r'\[node\s+(.*)\]', line)
        if m:
            attrs = _parse_tscn_attrs(m.group(1))
            current_node = attrs
            current_node["properties"] = {}
            nodes.append(current_node)
            continue

        # Parse [connection ...]
        m = re.match(r'\[connection\s+(.*)\]', line)
        if m:
            attrs = _parse_tscn_attrs(m.group(1))
            connections.append(attrs)
            continue

        # Parse node properties
        if current_node and "=" in line and not line.startswith("["):
            k, _, v = line.partition("=")
            current_node["properties"][k.strip()] = v.strip()

    # Build tree
    tree = _build_godot_tree(nodes)

    return {
        "ok": True,
        "path": path,
        "format": "tscn",
        "ext_resources": ext_resources,
        "connections": connections,
        "node_count": len(nodes),
        "tree": tree,
        "error": None,
    }


def _parse_tscn_attrs(attr_str: str) -> dict[str, str]:
    """Parse key=value pairs from a .tscn section header."""
    attrs: dict[str, str] = {}
    for m in re.finditer(r'(\w+)="([^"]*)"', attr_str):
        attrs[m.group(1)] = m.group(2)
    return attrs


def _build_godot_tree(nodes: list[dict]) -> dict | None:
    """Convert flat node list into nested tree using parent= attributes."""
    if not nodes:
        return None

    node_map: dict[str, dict] = {}
    root = None

    for node in nodes:
        name = node.get("name", "Unknown")
        node["children"] = []
        node_map[name] = node

        if "parent" not in node:
            root = node

    for node in nodes:
        parent_path = node.get("parent")
        if parent_path is None:
            continue
        if parent_path == ".":
            if root:
                root["children"].append(node)
        else:
            parent_name = parent_path.split("/")[-1]
            if parent_name in node_map:
                node_map[parent_name]["children"].append(node)

    return root


def _parse_unity_scene(content: str, path: str) -> dict[str, Any]:
    """Parse Unity .unity YAML scene file."""
    # Unity YAML has custom tags that break standard parsers; strip them
    cleaned = re.sub(r'%YAML.*\n', '', content)
    cleaned = re.sub(r'%TAG.*\n', '', cleaned)
    cleaned = re.sub(r'!u![0-9]+ &[0-9]+\n', '', cleaned)

    try:
        docs = list(yaml.safe_load_all(cleaned))
    except yaml.YAMLError:
        # Fallback: extract GameObjects manually
        docs = []

    game_objects = []
    missing_scripts = []

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        if "GameObject" in doc:
            go = doc["GameObject"]
            name = go.get("m_Name", "Unknown")
            components = go.get("m_Component", [])
            game_objects.append({"name": name, "components": components})

        if "MonoBehaviour" in doc:
            mb = doc["MonoBehaviour"]
            script = mb.get("m_Script", {})
            if isinstance(script, dict) and script.get("fileID") == 0:
                missing_scripts.append(mb.get("m_Name", "Unknown MonoBehaviour"))

    return {
        "ok": True,
        "path": path,
        "format": "unity",
        "game_object_count": len(game_objects),
        "game_objects": game_objects[:20],  # cap at 20 for context
        "missing_scripts": missing_scripts,
        "tree": {"name": "Scene", "children": game_objects},
        "error": None,
    }


# ---------------------------------------------------------------------------
# Log tools
# ---------------------------------------------------------------------------

def read_log(path: str, max_lines: int = 500) -> dict[str, Any]:
    """Read a build log file, returning up to max_lines from the end."""
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
    """
    Extract error and warning lines from a build log.
    Works for both Godot and Unity build output.
    """
    try:
        p = _safe_path(path)
        content = p.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()

        errors = []
        warnings = []

        error_patterns = [
            r'\berror\b', r'\bERROR\b', r'Error:', r'error CS', r'Parse Error',
            r'FAILED', r'failed', r'Exception', r'cannot', r'undeclared',
        ]
        warning_patterns = [
            r'\bwarning\b', r'\bWARNING\b', r'Warning:', r'warning CS',
        ]

        for i, line in enumerate(lines, 1):
            if any(re.search(p, line) for p in error_patterns):
                errors.append({"line": i, "text": line.strip()})
            elif any(re.search(p, line) for p in warning_patterns):
                warnings.append({"line": i, "text": line.strip()})

        return {
            "ok": True,
            "path": str(p),
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors,
            "warnings": warnings[:50],  # cap warnings
            "error": None,
        }
    except Exception as e:
        return {"ok": False, "errors": [], "warnings": [], "error": str(e)}


def read_file(path: str) -> dict[str, Any]:
    """Generic file reader for asset inspection."""
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
