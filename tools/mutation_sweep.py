#!/usr/bin/env python3
"""Break every guard in the core and see whether a test notices (D20).

A guard that has never been observed to fail is documentation, and the test
covering it is a second piece of documentation agreeing with the first. This
walks `src/jarvis_core/`, applies one mutation at a time, and reports the ones
the suite did not catch.

    python3 tools/mutation_sweep.py            # everything
    python3 tools/mutation_sweep.py record/    # one subtree

A *survivor* is a branch no test asserts. Not every survivor is a bug --
equivalent mutants exist, and a default argument nothing varies is noise --
but each one is a claim the suite is not checking, and the last sweep turned
six of them into real defects.

Two things it cannot tell you, so read the survivors rather than the count:
it scores *branches*, not whether the *right* test failed; and it says nothing
about the guards you never wrote.
"""
from __future__ import annotations

import ast
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "src" / "jarvis_core"

#: Each swap turns a guard into its opposite, which is what a missing test
#: cannot distinguish from the original.
CMP_SWAP = {
    ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
    ast.Lt: ast.LtE, ast.LtE: ast.Lt,      # boundaries: off-by-one on a threshold
    ast.Gt: ast.GtE, ast.GtE: ast.Gt,
    ast.Is: ast.IsNot, ast.IsNot: ast.Is,
    ast.In: ast.NotIn, ast.NotIn: ast.In,
}


def _decorator_flags(tree: ast.AST) -> set[int]:
    """Booleans inside a decorator call, e.g. ``@dataclass(frozen=True)``.

    Flipping one is a real change, but asserting that every dataclass is
    frozen is not what this sweep is for, and 40-odd of them drown the
    findings that matter. Skipped, and said out loud rather than filtered
    silently from the output.
    """
    skip: set[int] = set()
    nodes = list(ast.walk(tree))
    index = {id(node): i for i, node in enumerate(nodes)}
    for node in nodes:
        for decorator in getattr(node, "decorator_list", []):
            for inner in ast.walk(decorator):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, bool):
                    skip.add(index[id(inner)])
    return skip


def sites(tree: ast.AST) -> list[tuple[int, str, int]]:
    """Every mutable point, as (ordinal, kind, operator index).

    The ordinal is a position in a fixed pre-order walk, so the same number
    selects the same node in a freshly parsed copy of the file.
    """
    found: list[tuple[int, str, int]] = []
    skip = _decorator_flags(tree)
    for ordinal, node in enumerate(ast.walk(tree)):
        if ordinal in skip:
            continue
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                if type(op) in CMP_SWAP:
                    found.append((ordinal, "cmp", i))
        elif isinstance(node, ast.Constant) and node.value in (True, False) \
                and isinstance(node.value, bool):
            found.append((ordinal, "bool", 0))
        elif isinstance(node, ast.BoolOp):
            found.append((ordinal, "boolop", 0))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            found.append((ordinal, "not", 0))
    return found


def mutate(tree: ast.AST, ordinal: int, kind: str, index: int) -> tuple[str, int, str]:
    """Apply one mutation in place. Returns (source, line, description)."""
    node = list(ast.walk(tree))[ordinal]
    if kind == "cmp":
        was = type(node.ops[index]).__name__
        node.ops[index] = CMP_SWAP[type(node.ops[index])]()
        label = f"{was} -> {type(node.ops[index]).__name__}"
    elif kind == "bool":
        label = f"{node.value} -> {not node.value}"
        node.value = not node.value
    elif kind == "boolop":
        was = type(node.op).__name__
        node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        label = f"{was} -> {type(node.op).__name__}"
    else:                                   # drop a `not`
        label = "not removed"
        line = node.lineno

        class Drop(ast.NodeTransformer):
            """A UnaryOp is replaced by its operand, which its parent has to
            do -- so this is a transform rather than an in-place edit."""

            def visit_UnaryOp(self, candidate):
                self.generic_visit(candidate)
                return candidate.operand if candidate is node else candidate

        tree = Drop().visit(tree)
        ast.fix_missing_locations(tree)
        return ast.unparse(tree), line, label
    ast.fix_missing_locations(tree)
    return ast.unparse(tree), getattr(node, "lineno", 0), label


def suite_passes(fast: bool = True) -> bool:
    cmd = [sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"]
    if fast:
        cmd.append("-x")     # a killed mutant usually dies on the first test
    try:
        return subprocess.run(
            cmd, cwd=ROOT, capture_output=True, timeout=120, text=True
        ).returncode == 0
    except subprocess.TimeoutExpired:
        return False         # a hang is a kill: something noticed


def main(argv: list[str]) -> int:
    prefix = argv[1] if len(argv) > 1 else ""
    targets = [p for p in sorted(CORE.rglob("*.py"))
               if str(p.relative_to(CORE)).startswith(prefix)]
    survivors, total, started = [], 0, time.time()

    for path in targets:
        original = path.read_text()
        try:
            for ordinal, kind, index in sites(ast.parse(original)):
                try:
                    source, line, label = mutate(ast.parse(original), ordinal, kind, index)
                except Exception:
                    continue
                path.write_text(source)
                total += 1
                if suite_passes():
                    where = f"{path.relative_to(ROOT)}:{line}"
                    survivors.append((where, label, original.splitlines()[line - 1].strip()))
                    print(f"SURVIVED  {where}  {label}", flush=True)
                path.write_text(original)
        finally:
            path.write_text(original)     # never leave a mutant behind

    print(f"\n{total} mutants, {len(survivors)} survived, {time.time() - started:.0f}s")
    for where, label, source in survivors:
        print(f"  {where}  [{label}]  {source[:88]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
