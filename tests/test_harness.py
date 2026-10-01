# ~/agent_team/tests/test_harness.py
"""
Smoke test suite for bus3f-tui universal coding harness.
Run with: python3 tests/test_harness.py
"""

from __future__ import annotations
import sys
import os
import tempfile
from pathlib import Path

# Add project root to sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

def test_tools():
    from tools.gamedev_tools import (
        _safe_path, _normalize_code, read_file, write_file_dry,
        list_dir, grep_file, read_log, grep_error
    )

    # 1. Path safety
    assert _safe_path("/tmp", must_exist=False) == Path("/tmp").resolve()
    try:
        _safe_path("/etc/shadow", must_exist=False)
        assert False, "Should have rejected path outside allowed roots"
    except ValueError:
        pass

    # 2. Code normalization
    raw = r"def foo():\n\treturn 42"
    assert _normalize_code(raw) == "def foo():\n\treturn 42"

    # 3. Dry-run write vs committed write
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = str(Path(tmpdir) / "test.py")
        content = "print('hello world')\n"

        # Dry-run: commit=False
        dry = write_file_dry(test_file, content, commit=False)
        assert dry["ok"] is True
        assert dry["committed"] is False
        assert not Path(test_file).exists()

        # Real commit: commit=True
        committed = write_file_dry(test_file, content, commit=True)
        assert committed["ok"] is True
        assert committed["committed"] is True
        assert Path(test_file).exists()

        # Read back
        read = read_file(test_file)
        assert read["ok"] is True
        assert read["content"] == content

        # Grep
        found = grep_file(test_file, r"hello")
        assert found["ok"] is True
        assert found["match_count"] == 1
        assert "hello world" in found["matches"][0]["text"]

        # List dir
        listed = list_dir(tmpdir, "*.py")
        assert listed["ok"] is True
        assert len(listed["files"]) == 1

        # Log tools
        log_file = str(Path(tmpdir) / "build.log")
        Path(log_file).write_text("info: compiling\nerror: undefined symbol foo\nwarning: unused var x\n", encoding="utf-8")
        tail = read_log(log_file, max_lines=2)
        assert tail["ok"] is True
        assert tail["returned_lines"] == 2

        errs = grep_error(log_file)
        assert errs["ok"] is True
        assert errs["error_count"] == 1
        assert errs["warning_count"] == 1
        assert "undefined symbol" in errs["errors"][0]["text"]

    print("  ✓ tools/gamedev_tools pass")


def test_profiles():
    from agents.profiles import AGENT_PROFILES, load_custom_agents

    assert "coder" in AGENT_PROFILES
    assert "reviewer" in AGENT_PROFILES
    assert "debugger" in AGENT_PROFILES
    assert "general" in AGENT_PROFILES

    # Check backwards compatibility aliases
    assert AGENT_PROFILES["godot"]["name"] == AGENT_PROFILES["coder"]["name"]
    assert AGENT_PROFILES["unity"]["name"] == AGENT_PROFILES["coder"]["name"]

    custom = load_custom_agents()
    assert isinstance(custom, dict)
    print("  ✓ agents/profiles pass")


def test_router():
    from harness.router import _prefilter_route, route

    # Test deterministic fast-path pre-filters
    r1 = _prefilter_route("fix the null pointer exception")
    assert r1 is not None and r1["task"] == "edit" and r1["engine"] == "coder"

    r2 = _prefilter_route("review the auth module for security bugs")
    assert r2 is not None and r2["task"] == "review" and r2["engine"] == "reviewer"

    r3 = _prefilter_route("why is the server failing to start with crash")
    assert r3 is not None and r3["task"] == "debug" and r3["engine"] == "debugger"

    r4 = _prefilter_route("explain how the database pooling works")
    assert r4 is not None and r4["task"] == "explain" and r4["engine"] == "general"

    # Test graceful fallback when llama-server is unreachable
    r5 = route("you good at your job?")
    assert r5["engine"] == "general" and r5["method"] in ("model", "fallback")

    print("  ✓ harness/router pre-filters and offline resilience pass")


def test_db():
    import uuid
    from harness.db import (
        init_db, create_session, get_session, branch_session,
        delete_session, list_sessions
    )

    init_db()
    sid = f"test-{uuid.uuid4().hex[:8]}"
    create_session(sid, "test task", title="Test Session")

    sess = get_session(sid)
    assert sess is not None
    assert sess["id"] == sid
    assert sess["title"] == "Test Session"

    bid = f"test-{uuid.uuid4().hex[:8]}"
    branched = branch_session(sid, bid, title="Branch Session")
    assert branched is True
    b_sess = get_session(bid)
    assert b_sess is not None
    assert b_sess["parent_id"] == sid

    assert delete_session(sid) is True
    assert delete_session(bid) is True
    assert get_session(sid) is None
    print("  ✓ harness/db SQLite operations pass")


def test_loop():
    from harness.loop import parse_react_step, TOOL_REGISTRY, APPROVAL_REQUIRED_TOOLS

    # Universal tools registration check
    assert "read_file" in TOOL_REGISTRY
    assert "write_file_dry" in TOOL_REGISTRY
    assert "grep_file" in TOOL_REGISTRY
    assert "list_dir" in TOOL_REGISTRY
    assert APPROVAL_REQUIRED_TOOLS == {"write_file_dry"}

    # ReAct step parser checks
    text1 = """Thought: Need to read the file first
Action: read_file
Args: {"path": "src/main.py"}"""
    p1 = parse_react_step(text1)
    assert p1["thought"] == "Need to read the file first"
    assert p1["action"] == "read_file"
    assert p1["args"] == {"path": "src/main.py"}
    assert p1["final_answer"] is None

    text2 = """Thought: Everything looks good.
Final Answer: All tests are passing cleanly."""
    p2 = parse_react_step(text2)
    assert p2["action"] is None
    assert p2["final_answer"] == "All tests are passing cleanly."

    text3 = """Thought: Here is the code
Final Answer: Here is the code:
```python
def binary_search(arr, target):
    return 0
```"""
    p3 = parse_react_step(text3)
    assert p3["action"] is None
    assert "def binary_search" in p3["final_answer"]

    print("  ✓ harness/loop ReAct step parsing pass")


def test_cli():
    from cli import quick_reply, check_models_available, highlight_code

    assert isinstance(check_models_available(), bool)
    assert highlight_code("def foo():\n    return 42", "python") is not None
    assert quick_reply("hello") is not None
    assert quick_reply("thanks") == "You're welcome! Let me know what you need next."
    assert quick_reply("ok") == "Got it. What would you like to work on next?"

    # Coding requests should bypass quick_reply and fall through to agents
    assert quick_reply("fix bug in auth.py") is None
    assert quick_reply("review src/controller.py") is None

    print("  ✓ cli quick_reply, model check, and syntax highlighter pass")


if __name__ == "__main__":
    print("\nRunning bus3f-tui test suite...")
    test_tools()
    test_profiles()
    test_router()
    test_db()
    test_loop()
    test_cli()
    print("\nAll checks passed cleanly! System is 100% operational.\n")
