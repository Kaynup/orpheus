"""Automated security & DOM XSS prevention tests for frontend JavaScript modules.

This suite enforces static AST / DOM rules to prevent Cross-Site Scripting (XSS)
by disallowing unsafe sinks (innerHTML, document.write, eval) across the ES6
JavaScript component architecture.
"""

import re
from pathlib import Path

JS_DIR = Path(__file__).resolve().parent.parent

# Sinks that are strictly prohibited to prevent XSS
UNSAFE_SINKS = [
    r"\.innerHTML\s*=",
    r"document\.write\(",
    r"eval\(",
]

# DOM APIs that are strictly prohibited in favor of textContent / DOM methods
UNSAFE_APIS = [
    r"\.insertAdjacentHTML",
    r"outerHTML\s*=",
]


def test_no_unsafe_sinks():
    """Verify that no unsafe DOM sinks (innerHTML, eval, document.write) are used."""
    violations = []
    
    for js_file in JS_DIR.rglob("*.js"):
        if js_file.is_dir() or js_file.name.startswith("test_"):
            continue
            
        content = js_file.read_text(encoding="utf-8")
        
        for sink in UNSAFE_SINKS:
            if re.search(sink, content):
                violations.append(f"Found unsafe sink '{sink}' in {js_file.name}")
                
    assert not violations, "Unsafe sinks detected:\n" + "\n".join(violations)


def test_no_unsafe_dom_apis():
    """Verify that no unsafe DOM injection APIs are used."""
    violations = []
    
    for js_file in JS_DIR.rglob("*.js"):
        if js_file.is_dir() or js_file.name.startswith("test_"):
            continue
            
        content = js_file.read_text(encoding="utf-8")
        
        for api in UNSAFE_APIS:
            if re.search(api, content):
                violations.append(f"Found unsafe DOM API '{api}' in {js_file.name}")
                
    assert not violations, "Unsafe DOM APIs detected:\n" + "\n".join(violations)


def test_enforces_strict_text_content():
    """Ensure that dynamically injected text strictly uses textContent."""
    # This is a heuristic test. If the codebase parses markdown or complex HTML, 
    # it must use a sanitized DOM building approach (e.g., document.createElement 
    # or a safe markdown library) instead of innerHTML.
    
    # We verify that textContent is used somewhere in chat.js as a positive assertion
    # that the developer is using safe text rendering for responses.
    chat_js = JS_DIR / "components" / "chat.js"
    
    if chat_js.exists():
        content = chat_js.read_text(encoding="utf-8")
        assert ".textContent" in content, (
            "chat.js must use .textContent for safe rendering of user/bot text."
        )
