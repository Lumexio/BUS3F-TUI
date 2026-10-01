"""
Strips Godot 4 parameter type hints from .gd files for Godot 3.5 compatibility.
Handles: func foo(x: float, y: int = 0): -> func foo(x, y = 0):
Dry-run by default. Pass --commit to write changes.
"""
import re
import sys
import shutil
from pathlib import Path

SCRIPTS_DIR = Path("/mnt/c/Users/Piaczo/Documents/Projects/Personal/game-dev-main/slide-x/scripts")
COMMIT = "--commit" in sys.argv

def strip_param_hints(line: str) -> str:
    """Strip type hints from function parameters on a single line."""
    # Match func definition lines only
    if not re.match(r'\s*(static\s+)?func\s+', line):
        return line

    def strip_param(m: re.Match) -> str:
        params_str = m.group(1)
        # Process each parameter
        result_params = []
        # Split by comma but respect nested brackets
        params = _split_params(params_str)
        for param in params:
            param = param.strip()
            if not param:
                continue
            # Strip type hint: name: Type = default -> name = default
            # Pattern: identifier: TypeName (= default)?
            p = re.sub(r'^(\w+)\s*:\s*[\w\[\], ]+(\s*=\s*.+)?$',
                       lambda mm: mm.group(1) + (mm.group(2) if mm.group(2) else ''),
                       param)
            result_params.append(p)
        return '(' + ', '.join(result_params) + ')'

    # Replace the parameter list in the func signature
    result = re.sub(r'\(([^)]*)\)', strip_param, line, count=1)
    return result

def _split_params(params_str: str) -> list:
    """Split parameter string by comma, ignoring nested brackets."""
    params = []
    depth = 0
    current = ""
    for ch in params_str:
        if ch in "([":
            depth += 1
            current += ch
        elif ch in ")]":
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            params.append(current)
            current = ""
        else:
            current += ch
    if current.strip():
        params.append(current)
    return params

total_fixed = 0
fixed_files = []

for gd_file in SCRIPTS_DIR.rglob("*.gd"):
    original_lines = gd_file.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    fixed_lines = []
    file_changes = 0

    for line in original_lines:
        fixed = strip_param_hints(line)
        if fixed != line:
            file_changes += 1
        fixed_lines.append(fixed)

    if file_changes > 0:
        total_fixed += file_changes
        fixed_files.append(str(gd_file))
        print(f"{'[WRITE]' if COMMIT else '[DRY]  '} {gd_file.name} ({file_changes} params fixed)")
        if COMMIT:
            shutil.copy2(gd_file, gd_file.with_suffix(".gd.param.bak"))
            gd_file.write_text("".join(fixed_lines), encoding="utf-8")
    else:
        print(f"[CLEAN] {gd_file.name}")

print(f"\n{'Fixed' if COMMIT else 'Would fix'} {total_fixed} parameter hints across {len(fixed_files)} file(s).")
if not COMMIT:
    print("Run with --commit to apply changes (backups as .gd.param.bak)")
