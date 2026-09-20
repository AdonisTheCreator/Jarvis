"""The Capability Router (docs/05 §6).

Routes by **capability and policy**, never by product name, and scores rather
than branching. Three properties of the hot path matter:

* **No model call.** Scoring is a registry lookup plus arithmetic. A model call
  here is where latency stacking begins.
* **Policy first.** Nothing reaches a backend before the Policy Engine has
  said yes.
* **Exactly once.** Side-effecting capabilities claim an idempotency key before
  execution and release it only when the effect provably did not happen.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .backend import AgentBackend, Estimate, Task, TaskHandle
from .capability import Capability, CapabilityRegistry
from .errors import JarvisCoreError
from .idempotency import IdempotencyLedger, derive_key
from .policy.engine import Decision, PolicyEngine, Request
from .record import Actor, EventKind, RecordStore, make_event


class NoBackendAvailable(JarvisCoreError):
    """No healthy backend serves this capability."""


class DuplicateSuppressed(JarvisCoreError):
    """This exact side effect already happened or is in flight."""

    def __init__(self, key: str, state: str) -> None:
        self.key, self.state = key, state
        super().__init__(f"idempotency key {key[:12]}… is {state}; not repeating")


@dataclass(frozen=True, slots=True)
class Candidate:
    backend: AgentBackend
    estimate: Estimate
    score: float


@dataclass(frozen=True, slots=True)
class Invocation:
    """The result of a routed call, and the trail it left."""

    decision: Decision
    handle: TaskHandle | None
    backend_id: str | None
    event_id: str
    idempotency_key: str | None = None


class CapabilityRouter:
    """Ties the registry, policy, backends, idempotency and the Record together."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        policy: PolicyEngine,
        record: RecordStore,
        idempotency: IdempotencyLedger | None = None,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._record = record
        self._idempotency = idempotency or IdempotencyLedger()
        self._backends: list[AgentBackend] = []

    def register_backend(self, backend: AgentBackend) -> None:
        self._backends.append(backend)

    # -- routing ---------------------------------------------------------

    def candidates(self, task: Task) -> list[Candidate]:
        """Score every healthy backend that serves the capability.

        Deliberately arithmetic: capability match, health, measured confidence,
        then latency and cost as tie-breakers.
        """
        out: list[Candidate] = []
        for backend in self._backends:
            if task.capability not in backend.capabilities:
                continue
            if not backend.health().healthy:
                continue
            estimate = backend.estimate(task)
            score = estimate.confidence / (
                1.0 + estimate.latency_ms / 1000.0 + estimate.cost_usd * 10.0
            )
            out.append(Candidate(backend=backend, estimate=estimate, score=score))
        return sorted(out, key=lambda c: c.score, reverse=True)

    def choose(self, task: Task) -> AgentBackend:
        candidates = self.candidates(task)
        if not candidates:
            raise NoBackendAvailable(f"no healthy backend serves {task.capability!r}")
        return candidates[0].backend

    # -- the full path ---------------------------------------------------

    def invoke(self, request: Request, task: Task | None = None) -> Invocation:
        """Authorize, claim, execute, record. In that order, always."""
        capability = self._registry.require(request.capability)
        decision = self._policy.authorize(request)  # raises on deny / approval needed

        task = task or Task(
            capability=request.capability,
            target=request.target,
            params=request.params,
            session=request.session,
            subject_keys=("system",),
        )

        key = self._claim_if_side_effecting(capability, request)

        backend = self.choose(task)
        event = self._record.append(
            make_event(
                EventKind.CAPABILITY_INVOKE,
                actor=Actor.AGENT if request.actor == "agent" else Actor.USER,
                actor_id=request.actor,
                session=request.session,
                subject_keys=task.subject_keys or ("system",),
                meta={
                    "capability": request.capability,
                    "target": request.target,
                    "backend": backend.id,
                    "policy": decision.reason,
                    "idempotency_key": key,
                    "reversible": capability.reversible,
                },
            )
        )

        try:
            handle = backend.execute(task, idempotency_key=key)
        except Exception as exc:
            # The effect may or may not have landed. Leave the claim in flight:
            # a stuck claim needs a human, a wrongly released one sends twice.
            # Record the failure, though -- an audit trail that only shows
            # attempts cannot distinguish "did nothing" from "half did it".
            self._record.append(
                make_event(
                    EventKind.ERROR,
                    actor=Actor.SYSTEM,
                    session=request.session,
                    subject_keys=task.subject_keys or ("system",),
                    parent=[event.event.id],
                    meta={
                        "capability": request.capability,
                        "backend": backend.id,
                        "error": type(exc).__name__,
                        "idempotency_key": key,
                        "effect_uncertain": True,
                    },
                )
            )
            raise

        if key is not None:
            self._idempotency.complete(key, handle.id)

        self._record.append(
            make_event(
                EventKind.TOOL_RESULT,
                actor=Actor.SYSTEM,
                session=request.session,
                subject_keys=task.subject_keys or ("system",),
                parent=[event.event.id],
                meta={
                    "capability": request.capability,
                    "backend": backend.id,
                    "handle": handle.id,
                },
            )
        )

        return Invocation(
            decision=decision,
            handle=handle,
            backend_id=backend.id,
            event_id=event.event.id,
            idempotency_key=key,
        )

    def _claim_if_side_effecting(
        self, capability: Capability, request: Request
    ) -> str | None:
        if not capability.side_effecting:
            return None
        key = derive_key(
            capability.name,
            request.target,
            request.params,
            capability.idempotency_key_fields,
        )
        claim = self._idempotency.claim(key)
        if not claim.should_execute:
            raise DuplicateSuppressed(key, claim.state.value)
        return key
