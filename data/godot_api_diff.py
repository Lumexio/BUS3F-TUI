# ~/agent_team/data/godot_api_diff.py
"""
Godot 3.5 vs 4.x API differences relevant to the validator.
Each entry: {"gd4_pattern": str, "gd35_replacement": str, "notes": str}
"""

GODOT_API_DIFF = [
    {
        "category": "annotations",
        "gd4_pattern": "@export",
        "gd35_replacement": "export var",
        "notes": "Annotations with @ prefix are Godot 4 only. In 3.5 use keyword syntax."
    },
    {
        "category": "annotations",
        "gd4_pattern": "@onready",
        "gd35_replacement": "onready var",
        "notes": "Same — keyword syntax in 3.5."
    },
    {
        "category": "annotations",
        "gd4_pattern": "@tool",
        "gd35_replacement": "tool",
        "notes": "Placed at top of file as a standalone keyword in 3.5, not @tool annotation."
    },
    {
        "category": "coroutines",
        "gd4_pattern": "await signal",
        "gd35_replacement": "yield(signal_object, \"completed\")",
        "notes": "yield() takes the signal source object and signal name as string."
    },
    {
        "category": "signals",
        "gd4_pattern": "signal_name.connect(callable)",
        "gd35_replacement": "connect(\"signal_name\", target, \"_method_name\")",
        "notes": "In 3.5, connect() is a method on the node, not on the signal object."
    },
    {
        "category": "classes",
        "gd4_pattern": "class_name MyClass",
        "gd35_replacement": "const MyClass = preload(\"res://my_class.gd\")",
        "notes": "class_name is not supported in 3.5. Use preload for type references."
    },
    {
        "category": "type_hints",
        "gd4_pattern": "func foo() -> ReturnType:",
        "gd35_replacement": "func foo():",
        "notes": "Return type hints are not supported in GDScript 1 (Godot 3.5)."
    },
    {
        "category": "type_hints",
        "gd4_pattern": "func foo(x: int):",
        "gd35_replacement": "func foo(x):",
        "notes": "Parameter type hints are not supported in GDScript 1."
    },
    {
        "category": "time",
        "gd4_pattern": "Time.get_ticks_msec()",
        "gd35_replacement": "OS.get_ticks_msec()",
        "notes": "The Time singleton does not exist in 3.5. Use OS for time functions."
    },
    {
        "category": "random",
        "gd4_pattern": "randf_range(a, b)",
        "gd35_replacement": "rand_range(a, b)",
        "notes": "Function renamed in 4.x."
    },
    {
        "category": "random",
        "gd4_pattern": "randi_range(0, n)",
        "gd35_replacement": "randi() % n",
        "notes": "randi_range() does not exist in 3.5. Use modulo arithmetic."
    },
    {
        "category": "physics",
        "gd4_pattern": "CharacterBody2D",
        "gd35_replacement": "KinematicBody2D",
        "notes": "CharacterBody2D is Godot 4. In 3.5 use KinematicBody2D."
    },
    {
        "category": "physics",
        "gd4_pattern": "move_and_slide() with no args",
        "gd35_replacement": "move_and_slide(velocity, Vector2.UP)",
        "notes": "In 3.5, velocity is passed as first argument; in 4.x it's a property."
    },
    {
        "category": "types",
        "gd4_pattern": "Vector2i",
        "gd35_replacement": "Vector2 (cast to int as needed)",
        "notes": "Integer vector types added in Godot 4. Use Vector2 with int casting in 3.5."
    },
    {
        "category": "nodes",
        "gd4_pattern": "Node3D",
        "gd35_replacement": "Spatial",
        "notes": "Node3D was renamed from Spatial in Godot 4."
    },
    {
        "category": "nodes",
        "gd4_pattern": "Camera3D",
        "gd35_replacement": "Camera",
        "notes": "Camera3D renamed from Camera in Godot 4."
    },
]
