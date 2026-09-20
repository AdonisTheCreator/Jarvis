"""Capability descriptors and the registry (docs/05 §6, docs/17 §4).

Routing is by **capability and policy**, never by product name. A capability
has one owner, a declared autonomy class, a reversibility story, and a set of
providers that may change without the capability changing meaning.

The registry is also the *structured action space* the decision layer chooses
from -- which is not a side benefit. On the published benchmark, a decision
model scored 49/49 with clean, well-named tools and 25/49 without them
(docs/14 §2). The registry pays for itself twice.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Iterable, Mapping, Sequence

from .autonomy import AutonomyClass


class PrivacyClass(StrEnum):
    """What kind of data crosses this capability. Drives `route.pin` (D14)."""

    PUBLIC = "public"
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    LOCAL_ONLY = "local_only"
    """Must never leave the machine. A pinned-local task that silently burst
    to cloud would breach charter commitment 7, so this is enforced at the
    network layer, not by asking a model."""


class ModelPosition(StrEnum):
    """Where a model sits in a task (docs/17 §4).

    Four positions because they have genuinely different economics and risk:
    a model welcome at the top of a task can be unwelcome in fan-out, because
    subagents multiply.
    """

    PRIMARY = "primary"
    SUBAGENT = "subagent"
    CRITIC = "critic"
    BACKGROUND = "background"


@dataclass(frozen=True, slots=True)
class PositionPolicy:
    """Rules for one model position."""

    default: str
    deny: frozenset[str] = frozenset()
    require_different_provider_than_builder: bool = False

    def permits(self, model: str) -> bool:
        return model not in self.deny


@dataclass(slots=True)
class ModelCabinet:
    """Position-scoped model rules, authored by voice (D17).

    ``manual_override`` encodes the rule from docs/17 §5: an exclusion binds
    *automatic selection*; a deliberate human pin always wins, bounded only by
    autonomy class. The user is not a thing the router protects itself from.
    """

    positions: dict[ModelPosition, PositionPolicy] = field(default_factory=dict)
    manual_override: bool = True

    def policy_for(self, position: ModelPosition) -> PositionPolicy | None:
        return self.positions.get(position)

    def permits(self, position: ModelPosition, model: str, *, manual: bool = False) -> bool:
        if manual and self.manual_override:
            return True
        policy = self.positions.get(position)
        return True if policy is None else policy.permits(model)

    def conflicts(self, providers: Mapping[str, str]) -> list[str]:
        """Find rules that would leave a position with no legal model.

        ``providers`` maps model id -> provider id. Surfaced at policy-write
        time (docs/17 §4), never as a silent same-provider critic fallback at
        2am.
        """
        problems: list[str] = []
        all_models = set(providers)
        for position, policy in self.positions.items():
            remaining = all_models - set(policy.deny)
            if not remaining:
                problems.append(f"{position.value}: every known model is denied")
                continue
            if policy.require_different_provider_than_builder:
                # If only one provider survives the denials, a cross-provider
                # critic becomes impossible whenever that provider builds.
                survivors = {providers[m] for m in remaining}
                if len(survivors) < 2:
                    problems.append(
                        f"{position.value}: requires a different provider than the builder, "
                        f"but only provider {sorted(survivors)} survives the deny list"
                    )
        return problems


@dataclass(frozen=True, slots=True)
class Capability:
    """One thing Jarvis can do, and the terms on which it may do it."""

    name: str
    autonomy: AutonomyClass
    providers: tuple[str, ...] = ()
    privacy: PrivacyClass = PrivacyClass.PERSONAL
    reversible: bool = True
    undo: str | None = None
    enabled: bool = False
    """Off until explicitly enabled. A1 is 'automatic once enabled', and the
    default must be the safe half of that sentence."""
    idempotency_key_fields: tuple[str, ...] = ()
    """Parameter names whose values derive the idempotency key. Empty means
    the call is not side-effecting."""
    outputs: tuple[str, ...] = ()
    fallback: tuple[str, ...] = ()
    cabinet: ModelCabinet | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if self.autonomy >= AutonomyClass.A2_EXTERNAL and not self.reversible and not self.undo:
            # Not fatal -- some things genuinely cannot be undone -- but it must
            # be stated rather than implied, because it drives the approval tier.
            object.__setattr__(self, "undo", None)

    @property
    def side_effecting(self) -> bool:
        return bool(self.idempotency_key_fields)


class CapabilityRegistry:
    """The document of record for what exists and who owns it."""

    def __init__(self, capabilities: Iterable[Capability] = ()) -> None:
        self._by_name: dict[str, Capability] = {}
        for capability in capabilities:
            self.register(capability)

    def register(self, capability: Capability) -> None:
        if capability.name in self._by_name:
            raise ValueError(f"capability {capability.name!r} is already registered")
        self._by_name[capability.name] = capability

    def get(self, name: str) -> Capability | None:
        return self._by_name.get(name)

    def require(self, name: str) -> Capability:
        capability = self._by_name.get(name)
        if capability is None:
            raise KeyError(f"unknown capability {name!r}")
        return capability

    def names(self) -> Sequence[str]:
        return sorted(self._by_name)

    def classes(self) -> Mapping[str, AutonomyClass]:
        """Capability -> autonomy class, for Protocol validation."""
        return {name: cap.autonomy for name, cap in self._by_name.items()}

    def enable(self, name: str, enabled: bool = True) -> Capability:
        """Flip a capability's enabled flag, returning the updated descriptor.

        ``dataclasses.replace`` rather than ``**__dict__``: ``Capability`` is
        slotted, so it has no instance dict to splat.
        """
        updated = replace(self.require(name), enabled=enabled)
        self._by_name[name] = updated
        return updated
