"""The Policy Engine (docs/05 §5).

The single place that answers "may this happen?". Three properties make it
worth having rather than trusting the model:

* **Deterministic.** Same request, same answer, every time. A decision model
  may inform routing; it never authorizes (docs/14 §5 -- *Jev decides, the
  Policy Engine authorizes; a calibrated probability is not an approval*).
* **Fail closed.** Unknown capability, unreadable kill switch, missing
  approval -- all deny.
* **Explainable.** Every outcome carries a reason string that the audit
  projection can replay without re-running anything.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from ..capability import Capability, CapabilityRegistry
from ..errors import ApprovalInvalid, ApprovalRequired, PolicyDenied
from ..ids import new_ulid
from ..killswitch import KillSwitch, NullKillSwitch
from .approval import ApprovalLedger, ApprovalToken
from ..autonomy import AutonomyClass
from .protocols import AuthLevel, ProtocolRegistry


class Outcome(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class Request:
    """One attempt to use a capability."""

    capability: str
    target: str
    params: Mapping[str, Any] = field(default_factory=dict)
    actor: str = "agent"
    session: str = "default"
    protocol: str | None = None
    approval: ApprovalToken | None = None
    auth_level: AuthLevel = AuthLevel.SESSION
    quarantined: bool = False
    """Set for any agent that has ingested untrusted content (docs/05 §5.5).
    Such an agent may emit a typed Proposal and nothing else."""


@dataclass(frozen=True, slots=True)
class Decision:
    """The engine's answer, and why."""

    outcome: Outcome
    reason: str
    capability: str
    autonomy: AutonomyClass | None = None
    approval_request_id: str | None = None

    @property
    def allowed(self) -> bool:
        return self.outcome is Outcome.ALLOW


class PolicyEngine:
    def __init__(
        self,
        registry: CapabilityRegistry,
        approvals: ApprovalLedger,
        protocols: ProtocolRegistry,
        kill_switch: KillSwitch | None = None,
    ) -> None:
        self._registry = registry
        self._approvals = approvals
        self._protocols = protocols
        self._kill = kill_switch or NullKillSwitch()

    # -- the decision ----------------------------------------------------

    def evaluate(self, request: Request, *, now: float | None = None) -> Decision:
        """Decide without side effects, except spending a presented approval."""
        capability = self._registry.get(request.capability)

        # 1. Kill switch. Observation by a human still works -- you must be able
        #    to see what is happening while everything is halted -- but nothing
        #    else does, and no agent-initiated call does.
        if self._kill.is_engaged():
            # The documented actor form is prefixed ("user:harrison"), so an
            # exact match would deny the very person trying to diagnose a halt.
            actor_kind = request.actor.split(":", 1)[0].strip().lower()
            observing = (
                capability is not None
                and capability.autonomy == AutonomyClass.A0_OBSERVE
                and actor_kind == "user"
            )
            if not observing:
                return self._deny(
                    request, f"kill switch engaged: {self._kill.reason() or 'halted'}", capability
                )

        # 2. Unknown capability. Fail closed: an unregistered name is not a
        #    permission question, it is a bug or an attack.
        if capability is None:
            return self._deny(request, "unknown capability", None)

        # 3. Quarantine. An agent that read untrusted content may emit a
        #    Proposal and nothing else -- not scoped recall, none.
        if request.quarantined:
            return self._deny(
                request,
                "actor is quarantined (untrusted ingest); may only emit a Proposal",
                capability,
            )

        # 4. A4 is blocked with no override path. Checked before 'enabled' so
        #    enabling an A4 capability cannot accidentally open it.
        if capability.autonomy.is_blocked:
            return self._deny(request, "A4 capabilities are blocked with no override", capability)

        if not capability.enabled:
            return self._deny(request, "capability is not enabled", capability)

        # 5. A3 must run as a declared Protocol (R8).
        if capability.autonomy.needs_protocol:
            protocol_denial = self._check_protocol(request, capability, now=now)
            if protocol_denial is not None:
                return protocol_denial

        # 6. A2 and above need a scoped, single-use approval.
        if capability.autonomy.needs_approval:
            if request.approval is None:
                request_id = new_ulid()
                return Decision(
                    outcome=Outcome.REQUIRE_APPROVAL,
                    reason=f"{capability.autonomy.label} requires explicit approval",
                    capability=request.capability,
                    autonomy=capability.autonomy,
                    approval_request_id=request_id,
                )
            try:
                self._approvals.redeem(
                    request.approval,
                    request.capability,
                    request.target,
                    request.params,
                    now=now,
                )
            except ApprovalInvalid as exc:
                return self._deny(request, str(exc), capability)

        return Decision(
            outcome=Outcome.ALLOW,
            reason=f"{capability.autonomy.label} permitted",
            capability=request.capability,
            autonomy=capability.autonomy,
        )

    def authorize(self, request: Request, *, now: float | None = None) -> Decision:
        """Like :meth:`evaluate`, but raises instead of returning a refusal.

        For call sites that should not be able to forget to check.
        """
        decision = self.evaluate(request, now=now)
        if decision.outcome is Outcome.DENY:
            raise PolicyDenied(
                request.capability,
                decision.reason,
                decision.autonomy.label if decision.autonomy else None,
            )
        if decision.outcome is Outcome.REQUIRE_APPROVAL:
            raise ApprovalRequired(request.capability, decision.approval_request_id or "")
        return decision

    # -- internals -------------------------------------------------------

    def _check_protocol(
        self, request: Request, capability: Capability, *, now: float | None
    ) -> Decision | None:
        if request.protocol is None:
            return self._deny(
                request,
                "A3 capabilities may only run inside a declared Protocol "
                "(an agent may invoke one, never compose one)",
                capability,
            )
        protocol = self._protocols.get(request.protocol)
        if protocol is None:
            return self._deny(request, f"unknown protocol {request.protocol!r}", capability)
        if not self._protocols.covers(
            request.protocol, request.capability, request.params, request.target
        ):
            return self._deny(
                request,
                f"protocol {request.protocol!r} does not authorize {request.capability!r} "
                "on this target with these parameters",
                capability,
            )
        if protocol.expires_at is not None:
            import time

            if (now if now is not None else time.time()) >= protocol.expires_at:
                return self._deny(request, f"protocol {request.protocol!r} expired", capability)
        if _auth_rank(request.auth_level) < _auth_rank(protocol.auth_required):
            return self._deny(
                request,
                f"protocol {request.protocol!r} needs {protocol.auth_required.value} auth, "
                f"got {request.auth_level.value}",
                capability,
            )
        return None

    def _deny(self, request: Request, reason: str, capability: Capability | None) -> Decision:
        return Decision(
            outcome=Outcome.DENY,
            reason=reason,
            capability=request.capability,
            autonomy=capability.autonomy if capability else None,
        )


_AUTH_ORDER: dict[AuthLevel, int] = {
    AuthLevel.NONE: 0,
    AuthLevel.SESSION: 1,
    AuthLevel.VOICE_MATCH: 2,
    AuthLevel.STRONG: 3,
}


def _auth_rank(level: AuthLevel) -> int:
    return _AUTH_ORDER[level]
