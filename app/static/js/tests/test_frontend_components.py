"""Unit tests for frontend ES6 module graph, state bus, API transport, and safe component lifecycle."""

from pathlib import Path
import re
import pytest

JS_DIR = Path(__file__).resolve().parent.parent


def test_module_import_graph_resolution():
    """Verify that every ES6 relative import across all JS files resolves to an existing file."""
    import_pattern = re.compile(r"""(?:import|export)\s+(?:[\w\s{},*]+)\s+from\s+['"]([^'"]+)['"]""")
    broken_imports = []
    total_imports_verified = 0

    for js_file in JS_DIR.rglob("*.js"):
        if "tests" in js_file.parts:
            continue

        content = js_file.read_text(encoding="utf-8")
        matches = import_pattern.findall(content)

        for imp_path in matches:
            if imp_path.startswith("./") or imp_path.startswith("../"):
                # Resolve relative path
                resolved = (js_file.parent / imp_path).resolve()
                if not resolved.exists() or not resolved.is_file():
                    broken_imports.append(f"{js_file.name} -> {imp_path} (not found at {resolved})")
                else:
                    total_imports_verified += 1

    assert not broken_imports, "Broken module imports detected:\n" + "\n".join(broken_imports)
    assert total_imports_verified > 0, "Expected at least 1 verified ES6 module import"


def test_state_module_exports_and_event_bus():
    """Verify state.js exports reactive state object and pub-sub listener methods."""
    state_file = JS_DIR / "modules" / "state.js"
    assert state_file.exists() and state_file.is_file()

    content = state_file.read_text(encoding="utf-8")
    assert re.search(r"export\s+const\s+state\s*=", content), "state.js must export a state object"
    assert re.search(r"export\s+function\s+on\s*\(", content), "state.js must export an on() subscription function"
    assert re.search(r"export\s+function\s+emit\s*\(", content), "state.js must export an emit() dispatch function"


def test_api_transport_client_contracts():
    """Verify api.js defines all required REST client endpoints and SSE streaming functions."""
    api_file = JS_DIR / "modules" / "api.js"
    assert api_file.exists() and api_file.is_file()

    content = api_file.read_text(encoding="utf-8")
    required_endpoints = [
        "fetchStatus",
        "fetchDocuments",
        "deleteDocument",
        "loadSamples",
        "resetDatabase",
        "runEvaluation",
        "streamQuery",
        "streamIngest",
    ]

    missing_endpoints = []
    for ep in required_endpoints:
        if not re.search(rf"export\s+(?:async\s+)?function\s+{ep}\s*\(", content):
            missing_endpoints.append(ep)

    assert not missing_endpoints, f"Missing API endpoints in api.js: {missing_endpoints}"

    # Verify SSE streaming parser handles data lines and boundary delimiters
    assert "split(\"\\n\\n\")" in content or 'split("\\n\\n")' in content or 'split(`\\n\\n`)' in content, (
        "api.js SSE parser must split on standard \\n\\n stream event boundaries"
    )
    assert "data: " in content, "api.js SSE parser must handle 'data: ' payload prefix"


def test_component_lifecycle_initializers():
    """Verify all UI components export standard initialization and updater hooks."""
    components = {
        "chat.js": ["initChat"],
        "ingestion.js": ["initIngestion"],
        "evaluation.js": ["initEvaluation"],
        "modal.js": ["initModal"],
        "inspector.js": ["resetQAStepper", "updateQAStep", "resetIngestStepper", "updateIngestStep", "updateDiagnosticMetrics"],
    }

    missing_hooks = []
    for filename, hooks in components.items():
        comp_path = JS_DIR / "components" / filename
        assert comp_path.exists(), f"Component file not found: {filename}"

        content = comp_path.read_text(encoding="utf-8")
        for hook in hooks:
            if not re.search(rf"export\s+function\s+{hook}\s*\(", content):
                missing_hooks.append(f"{filename} missing {hook}()")

    assert not missing_hooks, "Missing component lifecycle initializers:\n" + "\n".join(missing_hooks)


def test_app_bootstrap_entrypoint():
    """Verify app.js imports and initializes all components and sets up tab routing."""
    app_file = JS_DIR / "app.js"
    assert app_file.exists() and app_file.is_file()

    content = app_file.read_text(encoding="utf-8")
    assert "initModal" in content
    assert "initChat" in content
    assert "initIngestion" in content
    assert "initEvaluation" in content
    assert "initTabNavigation" in content
    assert "DOMContentLoaded" in content
