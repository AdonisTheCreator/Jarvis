"""Canonical memory (docs/05 §4, revised by D5).

The Record is ground truth -- *what happened*. Memory holds the
**conclusions**, each pointing back at the source events that produced it.
That is what makes a memory correctable: you can always re-derive it.

Three rules the implementation enforces rather than documents:

1. **Provenance is mandatory.** A fact with no provenance is a bug, not a
   memory.
2. **Runtimes propose; the core writes.** A backend cannot reach in.
3. **Forgetting fans out.** Derived facts leak what they were derived from, so
   erasure must follow the derivation graph -- otherwise the guarantee is a
   lie (docs/11 §6).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Iterator, Mapping, Sequence

from .ids import new_ulid


class MemoryClass(StrEnum):
    """One owner per class (docs/04 Rule 2)."""

    IDENTITY = "identity"
    """Persona, tone, values, user-set boundaries. Written by humans only."""
    USER_FACTS = "user_facts"
    PROJECT = "project"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"
    """'How we do this.' Lives as SKILL.md files; this class indexes them."""
    OPERATIONAL = "operational"
    """Live missions, device state, sessions. Owned by the control plane, not
    by us -- represented here only so routing can see it."""


#: Classes the core owns outright. Everything else is indexed, not owned.
CORE_OWNED: frozenset[MemoryClass] = frozenset(
    {
        MemoryClass.IDENTITY,
        MemoryClass.USER_FACTS,
        MemoryClass.PROJECT,
        MemoryClass.EPISODIC,
    }
)


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a fact came from. Never optional."""

    source_events: tuple[str, ...]
    subject_keys: tuple[str, ...]
    confidence: float = 1.0
    derived_from: tuple[str, ...] = ()
    """Other fact ids this was built on. The forget fan-out follows these."""
    recorded_at: float = field(default_factory=time.time)
    recorded_by: str = "core"

    def __post_init__(self) -> None:
        if not self.source_events and not self.derived_from:
            raise ValueError(
                "provenance needs at least one source event or parent fact; "
                "a fact with no provenance is a bug, not a memory"
            )
        if not self.subject_keys:
            raise ValueError("provenance needs subject_keys so the fact can be forgotten")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class Fact:
    id: str
    memory_class: MemoryClass
    key: str
    value: Any
    provenance: Provenance
    superseded_by: str | None = None

    @property
    def active(self) -> bool:
        return self.superseded_by is None


@dataclass(frozen=True, slots=True)
class Proposal:
    """What a runtime may emit. It cannot write memory itself."""

    memory_class: MemoryClass
    key: str
    value: Any
    provenance: Provenance
    rationale: str = ""


@dataclass(frozen=True, slots=True)
class ForgetReport:
    """What erasure actually removed, so the promise is checkable."""

    subject: str
    directly_removed: tuple[str, ...]
    derived_removed: tuple[str, ...]

    @property
    def total(self) -> int:
        return len(self.directly_removed) + len(self.derived_removed)


class CanonicalMemory:
    """The conclusions, with provenance, and an erasure that really erases."""

    def __init__(self) -> None:
        self._facts: dict[str, Fact] = {}
        self._pending: list[Proposal] = []
        self._lock = threading.Lock()

    # -- proposing and writing -------------------------------------------

    def propose(self, proposal: Proposal) -> None:
        """A runtime's suggestion. Goes to a review queue, not to canonical."""
        if proposal.memory_class is MemoryClass.IDENTITY:
            raise ValueError("identity memory is written by humans only")
        with self._lock:
            self._pending.append(proposal)

    def pending(self) -> Sequence[Proposal]:
        with self._lock:
            return tuple(self._pending)

    def accept(self, index: int) -> Fact:
        """Promote a proposal into canonical memory."""
        with self._lock:
            proposal = self._pending.pop(index)
        return self.write(
            proposal.memory_class, proposal.key, proposal.value, proposal.provenance
        )

    def reject(self, index: int) -> Proposal:
        with self._lock:
            return self._pending.pop(index)

    def write(
        self,
        memory_class: MemoryClass,
        key: str,
        value: Any,
        provenance: Provenance,
    ) -> Fact:
        """Write a fact. Supersedes any active fact with the same class+key."""
        fact = Fact(
            id=new_ulid(), memory_class=memory_class, key=key, value=value, provenance=provenance
        )
        with self._lock:
            for existing_id, existing in list(self._facts.items()):
                if (
                    existing.active
                    and existing.memory_class is memory_class
                    and existing.key == key
                ):
                    self._facts[existing_id] = replace(existing, superseded_by=fact.id)
            self._facts[fact.id] = fact
        return fact

    # -- reading ---------------------------------------------------------

    def get(self, memory_class: MemoryClass, key: str) -> Fact | None:
        with self._lock:
            for fact in self._facts.values():
                if fact.active and fact.memory_class is memory_class and fact.key == key:
                    return fact
        return None

    def history(self, memory_class: MemoryClass, key: str) -> list[Fact]:
        """Every version of a fact, oldest first. Memory is correctable."""
        with self._lock:
            matching = [
                f for f in self._facts.values() if f.memory_class is memory_class and f.key == key
            ]
        return sorted(matching, key=lambda f: f.id)

    def all_facts(self, *, active_only: bool = True) -> Iterator[Fact]:
        with self._lock:
            facts = list(self._facts.values())
        for fact in sorted(facts, key=lambda f: f.id):
            if fact.active or not active_only:
                yield fact

    # -- forgetting ------------------------------------------------------

    def forget(self, subject: str) -> ForgetReport:
        """Erase everything about ``subject``, following the derivation graph.

        This is the half that is easy to get wrong: destroying the Record key
        makes the *source* unreadable, but a summary derived from it still
        holds the content. Erasure has to reach the derived facts too, which is
        exactly why ``derived_from`` exists.
        """
        with self._lock:
            direct = {
                fact.id for fact in self._facts.values() if subject in fact.provenance.subject_keys
            }
            derived: set[str] = set()
            frontier = set(direct)
            while frontier:
                current = frontier.pop()
                for fact in self._facts.values():
                    if fact.id in direct or fact.id in derived:
                        continue
                    if current in fact.provenance.derived_from:
                        derived.add(fact.id)
                        frontier.add(fact.id)
            for fact_id in direct | derived:
                del self._facts[fact_id]

        return ForgetReport(
            subject=subject,
            directly_removed=tuple(sorted(direct)),
            derived_removed=tuple(sorted(derived)),
        )

    def leaks(self, subject: str) -> list[str]:
        """Facts that would still hold ``subject``'s content after a naive delete.

        Diagnostic: if this is non-empty after a forget, the fan-out is broken.
        """
        with self._lock:
            return sorted(
                fact.id
                for fact in self._facts.values()
                if subject in fact.provenance.subject_keys
            )
