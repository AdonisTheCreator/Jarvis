"""The decision registry and the resolution path.

This is the single place the catalog in docs/20 becomes code, which is what
keeps its "rejected" list enforced: **a decision point that cannot name its
fallback cannot be registered.**
"""
from __future__ import annotations

import time
from typing import Any, Mapping, Sequence

from ..errors import PolicyDenied
from .types import (
    Decider, DecisionPoint, DecisionResult, DecisionSource, FallbackDecider,
    PromotedRule,
)


class DecisionRegistry:
    """Registered decision points plus the decider that answers them."""

    def __init__(self, decider: Decider | None = None) -> None:
        self._points: dict[str, DecisionPoint] = {}
        self._decider: Decider = decider or FallbackDecider()
        self._forced_rules: dict[str, PromotedRule] = {}

    # -- registration ----------------------------------------------------

    def register(self, point: DecisionPoint) -> DecisionPoint:
        if point.id in self._points:
            raise ValueError(f"decision point {point.id!r} already registered")
        self._points[point.id] = point
        return point

    def register_all(self, points: Sequence[DecisionPoint]) -> None:
        for point in points:
            self.register(point)

    def get(self, point_id: str) -> DecisionPoint | None:
        return self._points.get(point_id)

    def ids(self) -> Sequence[str]:
        return sorted(self._points)

    def set_decider(self, decider: Decider) -> None:
        self._decider = decider

    # -- the rule factory (docs/17 §2) -----------------------------------

    def promote_to_rule(
        self, point_id: str, chosen: str, *, actor: str, note: str = ""
    ) -> PromotedRule:
        """Freeze a decision as a deterministic rule.

        This is the mechanism behind "always use Fable 5.1 for coding tasks":
        once a human settles the judgment, the decision layer stops being
        asked. Call volume falls, determinism rises, cost falls.

        ``actor`` is required. This write outranks the decision layer
        permanently and answers with confidence 1.0, so an anonymous one is
        the least auditable and most powerful thing in the plane. The returned
        rule is what the caller appends to the Record as a POLICY_WRITE.
        """
        point = self._require(point_id)
        if chosen not in point.options:
            raise ValueError(f"{chosen!r} is not an option of {point_id!r}")
        rule = PromotedRule(
            point_id=point_id, chosen=chosen, actor=actor, note=note, at=time.time()
        )
        self._forced_rules[point_id] = rule
        return rule

    def clear_rule(self, point_id: str) -> PromotedRule | None:
        """Unsettle a judgment. Returns the rule that was lifted, for the
        Record -- removing a policy is a policy write too."""
        return self._forced_rules.pop(point_id, None)

    def rules(self) -> Mapping[str, PromotedRule]:
        """Every judgment that has been settled. Enumerable on demand (R3)."""
        return dict(self._forced_rules)

    # -- resolution ------------------------------------------------------

    def decide(self, point_id: str, state: Mapping[str, Any]) -> DecisionResult:
        point = self._require(point_id)

        # A promoted rule short-circuits everything, including the model.
        forced = self._forced_rules.get(point_id)
        if forced is not None:
            return DecisionResult(point.id, forced.chosen, 1.0, DecisionSource.RULE)

        if not self._decider.available():
            if point.safety_critical:
                # Fail closed for safety (D9 §7).
                raise PolicyDenied(
                    point.id, "decision layer unavailable and this point is safety-critical"
                )
            return DecisionResult(point.id, point.fallback, 0.0, DecisionSource.FALLBACK)

        started = time.perf_counter()
        try:
            chosen, confidence, distribution = self._decider.decide(point, state)
        except Exception:  # noqa: BLE001 -- a decider fault must not take the system down
            if point.safety_critical:
                raise PolicyDenied(point.id, "decision layer failed on a safety-critical point")
            return DecisionResult(point.id, point.fallback, 0.0, DecisionSource.FAULT)
        latency_ms = (time.perf_counter() - started) * 1000

        if chosen not in point.options:
            # A decider that answers outside the option set is broken, not
            # creative -- and more broken than one that is merely unsure, so it
            # escalates rather than falling back. Falling back handed it the
            # *milder* of the two treatments: on record.retention that is
            # "compress" where low confidence would have said "keep_full", so a
            # broken decider quietly destroyed detail the unsure one preserved.
            return DecisionResult(
                point.id, point.escalate_to, 0.0, DecisionSource.INVALID, latency_ms
            )

        if confidence < point.min_confidence:
            # Escalate to the MORE conservative option, never the cheaper one.
            return DecisionResult(
                point.id, point.escalate_to, confidence, DecisionSource.ESCALATED, latency_ms, distribution
            )

        return DecisionResult(
            point.id, chosen, confidence, DecisionSource.MODEL, latency_ms, distribution
        )

    def _require(self, point_id: str) -> DecisionPoint:
        point = self._points.get(point_id)
        if point is None:
            raise KeyError(f"unknown decision point {point_id!r}")
        return point
