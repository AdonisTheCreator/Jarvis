"""The Capability Router (docs/05 §6).

Routes by **capability and policy**, never by product name, and scores rather
than branching. Four properties of the path matter:

* **No model call on the hot path.** Scoring is a registry lookup plus
  arithmetic. A model call here is where latency stacking begins.
* **Policy first, and always recorded.** Nothing reaches a backend before the
  Policy Engine has said yes -- and a *refusal* is written to the Record too. A
  trail that only shows what happened cannot show what was attempted, which is
  exactly what you want to see after a quarantined agent probes every
  capability it can name.
* **Exactly once.** Side-effecting capabilities claim an idempotency key, and
  the claim is released only when the effect provably did not happen.
* **The authorized action is the executed action.** The task cannot disagree
  with the request it was authorized under.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from .backend import AgentBackend, Estimate, Task, TaskHandle, TaskState
from .capability import Capability, CapabilityRegistry
from .errors import ApprovalRequired, JarvisCoreError, PolicyDenied
from .idempotency import IdempotencyLedger, derive_key
from .policy.engine import Decision, Outcome, PolicyEngine, Request
from .record import Actor, EventKind, RecordStore, make_event


class NoBackendAvailable(JarvisCoreError):
    """No healthy backend serves this capability."""


class DuplicateSuppressed(JarvisCoreError):
    """This exact side effect already happened or is in flight."""

    def __init__(self, key: str, state: str) -> None:
        self.key, self.state = key, state
        super().__init__(f"idempotency key {key[:12]}… is {state}; not repeating")


class TaskMismatch(JarvisCoreError):
    """A task was handed in that does not match the authorized request.

    Guards the hole where an authorized read could carry a write past policy:
    policy and the idempotency key derive from the *request*, while execution
    would use the *task*.
    """


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
    settled: bool = False
    """False when the backend returned a non-terminal state. The idempotency
    claim stays in flight until :meth:`CapabilityRouter.settle` resolves it."""


def _actor_of(actor: str) -> Actor:
    """Map a request actor string onto the Record's coarse actor enum.

    Getting this wrong attributes unattended background work to the human,
    which is the one mistake an audit trail must never make.
    """
    head = actor.split(":", 1)[0].strip().lower()
    return {
        "user": Actor.USER,
        "agent": Actor.AGENT,
        "watcher": Actor.WATCHER,
        "subconscious": Actor.SUBCONSCIOUS,
        "system": Actor.SYSTEM,
    }.get(head, Actor.SYSTEM)


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

        Deliberately arithmetic: measured confidence first, then latency and
        cost as tie-breakers.
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
        """Authorize, choose, claim, execute, record.

        Order is load-bearing. The backend is chosen *before* the idempotency
        claim, so a routing failure cannot strand a claim and permanently
        block the retry that would have succeeded.
        """
        actor = _actor_of(request.actor)

        # 1. Policy decides -- including on unknown capabilities, which it fails
        #    closed on. Looking the capability up first would turn a documented
        #    refusal into a raw KeyError.
        decision = self._policy.evaluate(request)
        self._record_decision(request, decision, actor)

        if decision.outcome is Outcome.DENY:
            raise PolicyDenied(
                request.capability,
                decision.reason,
                decision.autonomy.label if decision.autonomy else None,
            )
        if decision.outcome is Outcome.REQUIRE_APPROVAL:
            raise ApprovalRequired(request.capability, decision.approval_request_id or "")

        capability = self._registry.require(request.capability)
        task = self._task_for(request, task)

        # 2. Choose before claiming.
        backend = self.choose(task)

        # 3. Claim. From here a failure must either complete or release.
        key = self._claim_if_side_effecting(capability, request)

        try:
            event = self._record.append(
                make_event(
                    EventKind.CAPABILITY_INVOKE,
                    actor=actor,
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
        except Exception:
            # Nothing has executed, so the claim is definitively free.
            self._release(key)
            raise

        try:
            handle = backend.execute(task, idempotency_key=key)
        except Exception as exc:
            # The effect may or may not have landed. Leave the claim in flight:
            # a stuck claim needs a human, a wrongly released one sends twice.
            self._record.append(
                make_event(
                    EventKind.TOOL_ERROR,
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

        state = self._state_of(backend, handle)
        settled = self._settle_claim(key, state)
        failed = state in {TaskState.FAILED, TaskState.CANCELLED, TaskState.INTERRUPTED}
        self._record.append(
            make_event(
                # A backend that reports failure immediately must not be
                # recorded as a result, or the trail cannot tell it from success.
                EventKind.TOOL_ERROR if failed else EventKind.TOOL_RESULT,
                actor=Actor.SYSTEM,
                session=request.session,
                subject_keys=task.subject_keys or ("system",),
                parent=[event.event.id],
                meta={
                    "capability": request.capability,
                    "backend": backend.id,
                    "handle": handle.id,
                    "state": state.value if state else "unknown",
                    "settled": settled,
                    "effect_uncertain": state is TaskState.INTERRUPTED,
                },
            )
        )

        return Invocation(
            decision=decision,
            handle=handle,
            backend_id=backend.id,
            event_id=event.event.id,
            idempotency_key=key,
            settled=settled,
        )

    def settle(
        self,
        backend: AgentBackend,
        handle: TaskHandle,
        idempotency_key: str | None = None,
    ) -> bool:
        """Resolve an in-flight claim for an asynchronous task.

        A queued effect that later fails must not stay recorded as done, or the
        legitimate retry is suppressed and the message is never sent. Callers
        poll this until it returns True.

        The key must be supplied (from :attr:`Invocation.idempotency_key`) or
        echoed by the adapter on the handle. The ``AgentBackend`` contract does
        not *require* adapters to echo it, so relying on the handle alone would
        silently return "resolved" while leaving the claim in flight forever.
        """
        key = idempotency_key or handle.idempotency_key
        if key is None:
            raise ValueError(
                "settle() needs the idempotency key -- pass Invocation.idempotency_key; "
                "the backend contract does not require adapters to echo it on the handle"
            )
        return self._settle_claim(key, self._state_of(backend, handle))

    # -- internals -------------------------------------------------------

    def _task_for(self, request: Request, task: Task | None) -> Task:
        """Derive the task from the request, or validate a supplied one.

        Policy and the idempotency key both derive from the *request*. If the
        task were allowed to name a different capability or target, an
        authorized read could carry an unauthorized write to a backend.
        """
        if task is None:
            return Task(
                capability=request.capability,
                target=request.target,
                params=request.params,
                session=request.session,
                subject_keys=("system",),
            )
        if task.capability != request.capability or task.target != request.target:
            raise TaskMismatch(
                f"task {task.capability!r}->{task.target!r} does not match authorized "
                f"request {request.capability!r}->{request.target!r}"
            )
        if dict(task.params) != dict(request.params):
            # The approval token is fingerprinted over request.params. Letting
            # the task carry different ones would execute an action the human
            # never saw -- the precise hole this guard exists to close.
            raise TaskMismatch(
                f"task params for {request.capability!r} differ from the authorized request; "
                "the approval was bound to the request's parameters"
            )
        return replace(task, session=request.session)

    def _record_decision(self, request: Request, decision: Decision, actor: Actor) -> None:
        """Write every policy outcome, including refusals."""
        # A refusal by the engine is a POLICY_DECISION. APPROVAL_DENY is
        # reserved for a denial a *human* actually made -- conflating the two
        # would make "the kill switch stopped it" look like "you said no".
        kind = (
            EventKind.APPROVAL_REQUEST
            if decision.outcome is Outcome.REQUIRE_APPROVAL
            else EventKind.POLICY_DECISION
        )
        self._record.append(
            make_event(
                kind,
                actor=actor,
                actor_id=request.actor,
                session=request.session,
                subject_keys=("system",),
                meta={
                    "capability": request.capability,
                    "target": request.target,
                    "outcome": decision.outcome.value,
                    "reason": decision.reason,
                    "autonomy": decision.autonomy.label if decision.autonomy else None,
                    "quarantined": request.quarantined,
                    "approval_request_id": decision.approval_request_id,
                },
            )
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

    @staticmethod
    def _state_of(backend: AgentBackend, handle: TaskHandle) -> TaskState | None:
        try:
            return backend.status(handle).state
        except Exception:
            return None  # unknown: never guess about a side effect

    def _settle_claim(self, key: str | None, state: TaskState | None) -> bool:
        """Complete or release a claim. Returns True when polling can stop.

        Covers every terminal state, including ``INTERRUPTED`` -- omitting it
        would leave a documented "poll until True" loop running forever.
        """
        if key is None:
            return True
        if state is TaskState.SUCCEEDED:
            self._idempotency.complete(key)
            return True
        if state in {TaskState.FAILED, TaskState.CANCELLED}:
            # Definitively did not take effect -- a retry is legitimate.
            self._release(key)
            return True
        if state is TaskState.INTERRUPTED:
            # Terminal, but the effect may have partly landed. Stop polling and
            # leave the claim in flight: a stuck claim needs a human, and that
            # is the correct outcome here rather than a guess either way.
            return True
        return False  # pending, running, awaiting approval, or unknown

    def _release(self, key: str | None) -> None:
        if key is not None:
            self._idempotency.release(key)
