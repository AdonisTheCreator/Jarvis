"""Architectural invariants, asserted rather than documented.

docs/05 §1: *no module in the core may import a vendor type.* That is the
property that makes a control plane swappable, and it decays silently unless
something checks it.
"""
import ast
import pathlib

import pytest

CORE = pathlib.Path(__file__).resolve().parents[1] / "src" / "jarvis_core"

#: Anything that ties the core to a specific vendor, runtime or control plane.
FORBIDDEN_PREFIXES = {
    "anthropic", "openai", "google", "genai", "xai", "grok", "mistralai",
    "cohere", "ollama", "langchain", "langgraph", "letta", "llama_index",
    "openclaw", "hermes", "traycer", "crewai", "autogen", "boto3",
}

#: The core's only permitted third-party dependency. It is crypto, which is the
#: last thing that should be hand-rolled.
ALLOWED_THIRD_PARTY = {"cryptography"}

STDLIB_OK = {
    "abc", "dataclasses", "enum", "typing", "json", "os", "time", "hashlib",
    "hmac", "threading", "math", "re", "pathlib", "__future__", "collections",
    "itertools", "functools", "contextlib", "secrets", "base64", "uuid",
    "logging", "types", "datetime",
}


def core_modules() -> list[pathlib.Path]:
    return sorted(CORE.rglob("*.py"))


def top_level_imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def test_core_has_modules_to_check():
    assert len(core_modules()) >= 10


@pytest.mark.parametrize("path", core_modules(), ids=lambda p: p.name)
def test_no_vendor_imports_in_the_core(path: pathlib.Path):
    offenders = top_level_imports(path) & FORBIDDEN_PREFIXES
    assert not offenders, (
        f"{path.relative_to(CORE)} imports {sorted(offenders)}. Vendors live behind "
        "adapters; a vendor type in the core is how a swappable control plane "
        "stops being swappable (docs/05 §1)."
    )


@pytest.mark.parametrize("path", core_modules(), ids=lambda p: p.name)
def test_third_party_dependencies_stay_at_one(path: pathlib.Path):
    third_party = top_level_imports(path) - STDLIB_OK - {"jarvis_core"}
    unexpected = third_party - ALLOWED_THIRD_PARTY
    assert not unexpected, (
        f"{path.relative_to(CORE)} pulls in {sorted(unexpected)}. The core stays "
        "small and boring on purpose (docs/04 Rule 3)."
    )


def test_no_vendor_names_appear_in_core_identifiers():
    """Catches `class OpenClawAdapter` living in the core by mistake."""
    for path in core_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                lowered = node.name.lower()
                hits = [v for v in FORBIDDEN_PREFIXES if v in lowered]
                assert not hits, f"{path.name}: {node.name} names a vendor {hits}"
