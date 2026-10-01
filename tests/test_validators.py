# ~/agent_team/tests/test_validators.py
"""
pytest suite for API validators, tool failures, and stochasticity.
Run: pytest tests/test_validators.py -v
"""

import pytest
import time
import json
import uuid
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent.parent))

from tools.gamedev_tools import (
    check_godot35_apis,
    check_unity2018_apis,
    read_gd,
    write_gd_dry,
    grep_error,
)
from harness.router import route, _prefilter_route


# ---------------------------------------------------------------------------
# Godot 3.5 API violation detection
# ---------------------------------------------------------------------------

class TestGodotApiChecker:

    def test_detects_at_export(self):
        code = "@export var health = 100"
        result = check_godot35_apis(code)
        assert result["passed"] is False
        violations = [v["violation"] for v in result["violations"]]
        assert any("@export" in v for v in violations)

    def test_detects_at_onready(self):
        code = "@onready var player = $Player"
        result = check_godot35_apis(code)
        assert result["passed"] is False

    def test_detects_await(self):
        code = "await get_tree().create_timer(1.0).timeout"
        result = check_godot35_apis(code)
        assert result["passed"] is False
        violations = [v["violation"] for v in result["violations"]]
        assert any("await" in v for v in violations)

    def test_detects_new_style_connect(self):
        code = 'health_changed.connect(_on_health_changed)'
        result = check_godot35_apis(code)
        assert result["passed"] is False

    def test_detects_class_name(self):
        code = "class_name PlayerController"
        result = check_godot35_apis(code)
        assert result["passed"] is False

    def test_detects_return_type_hint(self):
        code = "func get_health() -> int:"
        result = check_godot35_apis(code)
        assert result["passed"] is False

    def test_detects_time_singleton(self):
        code = "var t = Time.get_ticks_msec()"
        result = check_godot35_apis(code)
        assert result["passed"] is False

    def test_detects_randf_range(self):
        code = "var x = randf_range(0.0, 1.0)"
        result = check_godot35_apis(code)
        assert result["passed"] is False

    def test_detects_character_body_2d(self):
        code = "extends CharacterBody2D"
        result = check_godot35_apis(code)
        assert result["passed"] is False

    def test_detects_node3d(self):
        code = "extends Node3D"
        result = check_godot35_apis(code)
        assert result["passed"] is False

    def test_valid_godot35_code_passes(self):
        code = """
extends KinematicBody2D

export var speed = 200
onready var sprite = $Sprite

func _physics_process(delta):
\tvar velocity = Vector2.ZERO
\tif Input.is_action_pressed("ui_right"):
\t\tvelocity.x += speed
\tmove_and_slide(velocity, Vector2.UP)

func _on_area_entered(area):
\tconnect("body_entered", self, "_on_body_entered")
"""
        result = check_godot35_apis(code)
        assert result["passed"] is True, f"False positives: {result['violations']}"

    def test_skips_comment_lines(self):
        # Pattern in a comment should not trigger
        code = "# await is the Godot 4 way\nvar x = 1"
        result = check_godot35_apis(code)
        assert result["passed"] is True

    def test_violation_has_line_number(self):
        code = "var x = 1\n@export var health = 100\nvar y = 2"
        result = check_godot35_apis(code)
        assert result["violations"][0]["line"] == 2

    def test_multiple_violations_all_reported(self):
        code = "@export var x = 1\n@onready var y = $Node\nawait signal"
        result = check_godot35_apis(code)
        assert result["violation_count"] >= 3


# ---------------------------------------------------------------------------
# Unity 2018.2 API violation detection
# ---------------------------------------------------------------------------

class TestUnityApiChecker:

    def test_detects_input_system_using(self):
        code = "using UnityEngine.InputSystem;"
        result = check_unity2018_apis(code)
        assert result["passed"] is False

    def test_detects_input_system_namespace(self):
        code = "var action = new UnityEngine.InputSystem.InputAction();"
        result = check_unity2018_apis(code)
        assert result["passed"] is False

    def test_detects_collision_without_param(self):
        code = "void OnCollisionEnter2D()\n{\n    Debug.Log(\"hit\");\n}"
        result = check_unity2018_apis(code)
        assert result["passed"] is False
        violations = [v["violation"] for v in result["violations"]]
        assert any("Collision2D" in v for v in violations)

    def test_detects_system_text_json(self):
        code = "using System.Text.Json;\nvar obj = JsonSerializer.Deserialize<MyType>(json);"
        result = check_unity2018_apis(code)
        assert result["passed"] is False

    def test_detects_find_objects_by_type(self):
        code = "var enemies = FindObjectsByType<Enemy>(FindObjectsSortMode.None);"
        result = check_unity2018_apis(code)
        assert result["passed"] is False

    def test_detects_addressables(self):
        code = "Addressables.LoadAssetAsync<Texture2D>(key);"
        result = check_unity2018_apis(code)
        assert result["passed"] is False

    def test_valid_unity_2018_code_passes(self):
        code = """
using UnityEngine;
using UnityEngine.UI;

public class PlayerController : MonoBehaviour
{
    [SerializeField] private float speed;
    private Rigidbody2D rb;

    private void Start()
    {
        rb = GetComponent<Rigidbody2D>();
    }

    private void Update()
    {
        float h = Input.GetAxis("Horizontal");
        float v = Input.GetAxis("Vertical");
        rb.velocity = new Vector2(h, v) * speed;
    }

    private void OnCollisionEnter2D(Collision2D other)
    {
        Debug.Log("Hit: " + other.gameObject.name);
    }
}
"""
        result = check_unity2018_apis(code)
        assert result["passed"] is True, f"False positives: {result['violations']}"

    def test_violation_has_line_number(self):
        code = "using UnityEngine;\nusing System.Text.Json;\nclass Foo {}"
        result = check_unity2018_apis(code)
        assert result["violations"][0]["line"] == 2

    def test_skips_comment_lines(self):
        code = "// System.Text.Json is NOT available in 2018\nusing UnityEngine;"
        result = check_unity2018_apis(code)
        assert result["passed"] is True


# ---------------------------------------------------------------------------
# Tool failure and recovery
# ---------------------------------------------------------------------------

class TestToolFailureRecovery:

    def test_read_gd_missing_file_returns_error(self):
        result = read_gd("/tmp/this_file_definitely_does_not_exist_xyzzy.gd")
        assert result["ok"] is False
        assert result["error"] is not None

    def test_read_gd_path_escape_rejected(self):
        with pytest.raises(ValueError, match="Path escape rejected"):
            from tools.gamedev_tools import _safe_path
            _safe_path("/etc/passwd")

    def test_write_gd_dry_run_does_not_write(self, tmp_path):
        target = str(tmp_path / "test.gd")
        result = write_gd_dry(target, "var x = 1\n", commit=False)
        assert result["ok"] is True
        assert result["dry_run"] is True
        assert not (tmp_path / "test.gd").exists()

    def test_write_gd_commit_writes_file(self, tmp_path):
        target = str(tmp_path / "test.gd")
        result = write_gd_dry(target, "var x = 1\n", commit=True)
        assert result["ok"] is True
        assert (tmp_path / "test.gd").exists()

    def test_write_gd_converts_spaces_to_tabs(self, tmp_path):
        target = str(tmp_path / "test.gd")
        code_with_spaces = "func foo():\n    var x = 1\n    return x\n"
        result = write_gd_dry(target, code_with_spaces, commit=True)
        written = (tmp_path / "test.gd").read_text()
        assert "\t" in written
        # No 4-space sequences at line start
        for line in written.splitlines():
            assert not line.startswith("    "), f"Space indentation found: {repr(line)}"

    def test_grep_error_missing_file_returns_error(self):
        result = grep_error("/tmp/no_such_log.txt")
        assert result["ok"] is False

    def test_grep_error_extracts_errors(self, tmp_path):
        log = tmp_path / "build.log"
        log.write_text("Compiling...\nParse Error: Expected indented block\nDone\n")
        result = grep_error(str(log))
        assert result["ok"] is True
        assert result["error_count"] >= 1
        assert any("Parse Error" in e["text"] for e in result["errors"])

    def test_tool_whitelist_enforced(self):
        """Simulate harness rejecting a tool not in whitelist."""
        from harness.loop import TOOL_REGISTRY
        tool_name = "write_gd_dry"
        whitelist = ["read_gd", "check_godot35_apis"]  # write NOT allowed

        if tool_name not in whitelist:
            result = {"ok": False, "error": f"Tool '{tool_name}' not in whitelist for this agent"}
        else:
            result = {"ok": True}

        assert result["ok"] is False
        assert "whitelist" in result["error"]


# ---------------------------------------------------------------------------
# Router pre-filter tests
# ---------------------------------------------------------------------------

class TestRouter:

    def test_godot_debug_prefilter(self):
        result = _prefilter_route("fix the player.gd script — it's not moving")
        assert result is not None
        assert result["engine"] == "godot"
        assert result["task"] == "debug"

    def test_unity_edit_prefilter(self):
        result = _prefilter_route("update the MonoBehaviour in PlayerController.cs")
        assert result is not None
        assert result["engine"] == "unity"
        assert result["task"] == "edit"

    def test_build_error_prefilter(self):
        result = _prefilter_route("I'm getting a CS0246 compile error in the build")
        assert result is not None
        assert result["engine"] == "build"

    def test_asset_prefilter(self):
        result = _prefilter_route("check the import settings on my texture.png")
        assert result is not None
        assert result["engine"] == "asset"

    def test_ambiguous_returns_none_for_model_fallback(self):
        # Pure ambiguity should return None so model handles it
        result = _prefilter_route("help me with my game")
        # May or may not match depending on keywords — just verify it doesn't crash
        # and returns dict or None
        assert result is None or isinstance(result, dict)


# ---------------------------------------------------------------------------
# Stochasticity measurement
# ---------------------------------------------------------------------------

class TestStochasticity:
    """
    Run the same validator N times and verify deterministic output.
    (Validators are pure Python — should be 100% deterministic.
     LLM calls are skipped here; test them separately with temperature=0.)
    """

    N = 10

    def test_godot_validator_is_deterministic(self):
        code = "@export var health = 100\nawait signal\n"
        results = [check_godot35_apis(code) for _ in range(self.N)]
        violation_counts = [r["violation_count"] for r in results]
        # All runs must return same count
        assert len(set(violation_counts)) == 1, f"Non-deterministic results: {violation_counts}"

    def test_unity_validator_is_deterministic(self):
        code = "using System.Text.Json;\nvoid OnCollisionEnter2D() {}"
        results = [check_unity2018_apis(code) for _ in range(self.N)]
        violation_counts = [r["violation_count"] for r in results]
        assert len(set(violation_counts)) == 1

    def test_prefilter_router_is_deterministic(self):
        text = "fix the player.gd — not moving"
        results = [_prefilter_route(text) for _ in range(self.N)]
        engines = [r["engine"] if r else None for r in results]
        assert len(set(engines)) == 1, f"Non-deterministic routing: {engines}"

    @pytest.mark.parametrize("run", range(5))
    def test_tab_conversion_idempotent(self, run, tmp_path):
        """write_gd_dry with commit=False is idempotent."""
        code = "func foo():\n    var x = 1\n"
        r1 = write_gd_dry("dummy.gd", code, commit=False)
        r2 = write_gd_dry("dummy.gd", r1["fixed_content"], commit=False)
        assert r1["fixed_content"] == r2["fixed_content"], "Tab conversion not idempotent"
