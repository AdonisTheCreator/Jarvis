"""Protocols: pre-declared, named, high-consequence macros (R8, docs/05 §5.3).

The design pattern taken from the fictional JARVIS. Every dangerous capability
he has is a *named, pre-authorized* sequence -- House Party, Clean Slate, Barn
Door -- designed and reviewed in calm conditions, then invoked by a single
authenticated utterance under pressure. He never improvises something
dangerous.

That inverts the usual agent-safety question. Not "how do we make the agent's
judgment safe enough to take dangerous actions?" but **"how do we make
dangerous actions not require in-the-moment judgment at all?"**

Consequently: an agent may *invoke* a Protocol. An agent may never *compose* a
new A3 sequence at runtime.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Sequence

from ..autonomy import AutonomyClass


class AuthLevel(StrEnum):
    NONE = "none"
    SESSION = "session"
    VOICE_MATCH = "voice_match"
    STRONG = "strong"  # second factor, or physical presence


class ConfirmMode(StrEnum):
    NONE = "none"
    PHRASE = "phrase"
    EXPLICIT = "explicit"


@dataclass(frozen=True, slots=True)
class ProtocolStep:
    """One capability invocation with its target and parameters fixed."""

    capability: str
    params: Mapping[str, Any] = field(default_factory=dict)
    target: str | None = None
    """The thing acted on. ``None`` places no constraint; anything else binds,
    because ``target`` reaches the backend untouched and a Protocol that named
    the front door must not authorize the garage."""


@dataclass(frozen=True, slots=True)
class Protocol:
    """A reviewed, named sequence. Immutable once declared."""

    name: str
    steps: tuple[ProtocolStep, ...]
    blast_radius: str
    declared_by: str
    reviewed_on: str
    auth_required: AuthLevel = AuthLevel.SESSION
    confirm: ConfirmMode = ConfirmMode.NONE
    undo: str | None = None
    expires_at: float | None = None

    def validate(self, classes: Mapping[str, AutonomyClass]) -> None:
        """Check the declaration is coherent against the capability registry.

        Run at declaration time, in calm conditions -- which is the only time
        anyone will read the error message properly.
        """
        if not self.steps:
            raise ValueError(f"protocol {self.name!r} has no steps")
        if not self.blast_radius.strip():
            raise ValueError(
                f"protocol {self.name!r} must state its blast radius in writing"
            )

        unknown = [s.capability for s in self.steps if s.capability not in classes]
        if unknown:
            raise ValueError(f"protocol {self.name!r} names unknown capabilities: {unknown}")

        highest = max(classes[s.capability] for s in self.steps)
        if highest.is_blocked:
            raise ValueError(
                f"protocol {self.name!r} contains an A4 step; A4 has no override path"
            )
        if highest == AutonomyClass.A3_CONSEQUENTIAL:
            if self.confirm != ConfirmMode.EXPLICIT:
                raise ValueError(
                    f"protocol {self.name!r} reaches A3 and must use confirm=explicit"
                )
            if self.auth_required not in (AuthLevel.VOICE_MATCH, AuthLevel.STRONG):
                raise ValueError(
                    f"protocol {self.name!r} reaches A3 and needs voice_match or strong auth"
                )
        if self.undo is None and self.confirm == ConfirmMode.NONE:
            # No undo and no confirmation is the combination that cannot be
            # recovered from. One of the two must be present.
            raise ValueError(
                f"protocol {self.name!r} declares no undo, so it must require confirmation"
            )

    @property
    def highest_class(self) -> str:
        return self.name  # placeholder for registry-aware reporting


class ProtocolRegistry:
    """Declared Protocols. Registration validates; invocation only looks up."""

    def __init__(self, capability_classes: Mapping[str, AutonomyClass]) -> None:
        self._classes = capability_classes
        self._protocols: dict[str, Protocol] = {}

    def declare(self, protocol: Protocol) -> None:
        protocol.validate(self._classes)
        if protocol.name in self._protocols:
            raise ValueError(f"protocol {protocol.name!r} already declared; protocols are immutable")
        self._protocols[protocol.name] = protocol

    def get(self, name: str) -> Protocol | None:
        return self._protocols.get(name)

    def names(self) -> Sequence[str]:
        return sorted(self._protocols)

    def covers(
        self,
        name: str,
        capability: str,
        params: Mapping[str, Any] | None = None,
        target: str | None = None,
    ) -> bool:
        """Does Protocol ``name`` authorize this exact call?

        The declared parameters **bind**. A Protocol is a sequence reviewed in
        calm conditions with its blast radius written down; if it named the
        garage door, it does not authorize the front door. Checking the
        capability alone would make the fixed parameter set decorative and
        quietly reintroduce the in-the-moment judgment Protocols exist to
        remove (R8).

        A step that declares no parameters or no target places no constraint on
        that dimension. A step that *does* declare parameters requires them to
        match exactly -- subset matching would let undeclared extras through.
        """
        protocol = self._protocols.get(name)
        if protocol is None:
            return False
        supplied = dict(params or {})
        for step in protocol.steps:
            if step.capability != capability:
                continue
            if step.target is not None and step.target != target:
                continue
            # Exact, not a subset: undeclared extras pass unchecked otherwise,
            # which is the same fail-open shape as an unbound target. A step
            # that declares no params still constrains none.
            if not step.params or supplied == dict(step.params):
                return True
        return False
