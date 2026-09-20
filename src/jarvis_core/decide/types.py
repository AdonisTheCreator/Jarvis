"""Decision points: the catalog (docs/20) as code.

A decision point is a bounded choice over unstructured state, with a
**mandatory deterministic fallback**. The registry refuses to register one
without a fallback, which is how the catalog's discipline survives contact
with a deadline: if you cannot name what happens when the decision layer is
unavailable, you have not finished designing the decision.

Two invariants from D9:

* **Low confidence escalates to the *more conservative* option, never the
  cheaper one.** Each point names that option explicitly rather than trusting
  an ordering convention.
* **Fail open for speed, fail closed for safety.** Routing and retention
  degrade to a safe default; anything touching policy, quarantine or approval
  denies when the decider is unavailable.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Protocol, Sequence


class DecisionSource(StrEnum):
    MODEL = "model"
    FALLBACK = "fallback"
    ESCALATED = "escalated"
    RULE = "rule"
    """A point that has been *promoted to a rule* (docs/17 §2) -- the decision
    layer as a rule factory. A source of RULE means this judgment was settled
    by a human and is no longer asked."""


@dataclass(frozen=True, slots=True)
class DecisionPoint:
    """One registered bounded choice."""

    id: str
    options: tuple[str, ...]
    fallback: str
    escalate_to: str
    """The *more conservative* option, used when confidence is below
    ``min_confidence``. Named explicitly because 'more conservative' is
    domain-specific: for retention it is ``keep``, for a review loop it is
    ``full``."""
    min_confidence: float = 0.7
    safety_critical: bool = False
    """When True, an unavailable decider denies rather than falling back."""
    description: str = ""

    def __post_init__(self) -> None:
        if len(self.options) < 2:
            raise ValueError(f"decision point {self.id!r} needs at least two options")
        if len(set(self.options)) != len(self.options):
            raise ValueError(f"decision point {self.id!r} has duplicate options")
        if self.fallback not in self.options:
            raise ValueError(
                f"decision point {self.id!r}: fallback {self.fallback!r} is not one of {self.options}"
            )
        if self.escalate_to not in self.options:
            raise ValueError(
                f"decision point {self.id!r}: escalate_to {self.escalate_to!r} "
                f"is not one of {self.options}"
            )
        if not 0.0 < self.min_confidence <= 1.0:
            raise ValueError(f"decision point {self.id!r}: min_confidence must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class DecisionResult:
    """What was chosen, how sure, and by what."""

    point_id: str
    chosen: str
    confidence: float
    source: DecisionSource
    latency_ms: float = 0.0
    raw: Mapping[str, float] | None = None
    """Full probability distribution when the decider supplies one. Kept for
    calibration analysis (D9 §6)."""

    @property
    def is_confident(self) -> bool:
        return self.source is DecisionSource.MODEL


class Decider(Protocol):
    """Anything that can answer a decision point.

    Implementations: the hosted decision model, a local model, a recorded
    fixture for tests, and the fallback decider below.
    """

    def decide(
        self, point: DecisionPoint, state: Mapping[str, Any]
    ) -> tuple[str, float, Mapping[str, float] | None]:
        """Return ``(chosen_option, confidence, distribution_or_None)``."""
        ...

    def available(self) -> bool:
        """False when the decider cannot currently answer."""
        ...


class FallbackDecider:
    """The null decider: used when no decision layer is configured.

    ``available()`` is **False** on purpose. This object does not answer
    questions -- it represents the absence of anything that can. The registry
    then applies each point's own fallback (or denies, for safety-critical
    points), which is the documented behaviour when the decision layer is
    unreachable (D9 §7).

    The distinction matters: if this reported itself available, its answer
    would arrive with zero confidence and be *re-escalated* as though a model
    had been unsure, quietly turning "no decider" into "escalate everything".
    """

    def decide(
        self, point: DecisionPoint, state: Mapping[str, Any]
    ) -> tuple[str, float, Mapping[str, float] | None]:
        return point.fallback, 0.0, None

    def available(self) -> bool:
        return False


def options_of(values: Sequence[str]) -> tuple[str, ...]:
    """Small helper so catalog entries read cleanly."""
    return tuple(values)
