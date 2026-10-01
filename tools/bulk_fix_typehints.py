"""
Strips Godot 4 return type hints from .gd files to make them Godot 3.5 compatible.
Dry-run by default. Pass --commit to write changes.
Backs up each file before writing.
"""
import re
import sys
import shutil
from pathlib import Path

SCRIPTS_DIR = Path("/mnt/c/Users/Piaczo/Documents/Projects/Personal/game-dev-main/slide-x/scripts")
COMMIT = "--commit" in sys.argv

# Match: func name(params) -> ReturnType:
# Keeps everything except the -> ReturnType part
TYPE_HINT_RE = re.compile(r'(\bfunc\s+\w+\s*\([^)]*\))\s*->\s*[\w\[\], ]+\s*(:)', )

fixed_files = []

for gd_file in SCRIPTS_DIR.rglob("*.gd"):
    original = gd_file.read_text(encoding="utf-8", errors="replace")
    fixed = TYPE_HINT_RE.sub(r'\1\2', original)

    if fixed != original:
        diff_count = len(TYPE_HINT_RE.findall(original))
        print(f"{'[WRITE]' if COMMIT else '[DRY]  '} {gd_file.relative_to(SCRIPTS_DIR.parent.parent.parent.parent.parent.parent)} ({diff_count} hints removed)")
        if COMMIT:
            # Backup first
            backup = gd_file.with_suffix(".gd.bak")
            shutil.copy2(gd_file, backup)
            gd_file.write_text(fixed, encoding="utf-8")
        fixed_files.append(str(gd_file))
    else:
        print(f"[CLEAN] {gd_file.name}")

print(f"\n{'Would fix' if not COMMIT else 'Fixed'} {len(fixed_files)} file(s).")
if not COMMIT:
    print("Run with --commit to apply changes (backups created as .gd.bak)")
