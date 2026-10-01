# ~/agent_team/data/unity_api_diff.py
"""
Unity 2018.2 vs 2019+ API differences relevant to the validator.
"""

UNITY_API_DIFF = [
    {
        "category": "input",
        "new_pattern": "UnityEngine.InputSystem",
        "legacy_replacement": "Input.GetAxis(), Input.GetButton(), Input.GetKey()",
        "notes": "New Input System is a package added in 2019. In 2018.2, use the legacy Input class only."
    },
    {
        "category": "input",
        "new_pattern": "PlayerInput component",
        "legacy_replacement": "Manual Input.GetAxis() polling in Update()",
        "notes": "PlayerInput is a new Input System component, unavailable in 2018.2."
    },
    {
        "category": "physics",
        "new_pattern": "void OnCollisionEnter2D()",
        "legacy_replacement": "void OnCollisionEnter2D(Collision2D other)",
        "notes": "Unity 2018.2 requires the Collision2D parameter. Parameterless overload is 2019+."
    },
    {
        "category": "json",
        "new_pattern": "System.Text.Json",
        "legacy_replacement": "JsonUtility.FromJson<T>() / JsonUtility.ToJson()",
        "notes": "System.Text.Json is a .NET Core API. Unity 2018.2 uses .NET Framework subset — use JsonUtility."
    },
    {
        "category": "ui",
        "new_pattern": "UnityEngine.UIElements (UI Toolkit)",
        "legacy_replacement": "UnityEngine.UI (uGUI)",
        "notes": "UI Toolkit was introduced in 2021. In 2018.2, use the uGUI Canvas/Text/Button system."
    },
    {
        "category": "addressables",
        "new_pattern": "Addressables.LoadAssetAsync<T>()",
        "legacy_replacement": "Resources.Load<T>() or AssetBundle.LoadAsset<T>()",
        "notes": "Addressables package not available in 2018.2 without manual install. Prefer Resources for small projects."
    },
    {
        "category": "scene_management",
        "new_pattern": "FindObjectsByType<T>()",
        "legacy_replacement": "FindObjectsOfType<T>()",
        "notes": "FindObjectsByType was added in Unity 2023. Use FindObjectsOfType in 2018.2."
    },
    {
        "category": "async",
        "new_pattern": "async/await in MonoBehaviour",
        "legacy_replacement": "IEnumerator coroutines with StartCoroutine()",
        "notes": "async/await technically compiles but is unreliable in Unity 2018.2 — exception handling is broken. Use coroutines."
    },
    {
        "category": "rendering",
        "new_pattern": "UniversalRenderPipeline (URP) / HDRP",
        "legacy_replacement": "Standard Shader / Built-in Render Pipeline",
        "notes": "URP and HDRP are Unity 2019+ packages. 2018.2 uses the built-in render pipeline."
    },
]
