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

from enum import StrEnum

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


class ClaimOutcome(StrEnum):
    """What became of a side effect's idempotency claim.

    A boolean could not express the case that matters most: a task that is
    *terminal* but whose effect may have partly landed. Callers poll while the
    outcome is ``PENDING`` and stop otherwise -- ``STUCK`` ends the loop and
    asks for a human rather than guessing in either direction.
    """

    NOT_APPLICABLE = "not_applicable"
    """The capability is not side-effecting; there was never a claim."""
    COMPLETED = "completed"
    RELEASED = "released"
    """Definitively did not take effect. A retry is legitimate."""
    PENDING = "pending"
    """Still running. Keep polling."""
    STUCK = "stuck"
    """Terminal, effect uncertain. The claim stays held until a human resolves it."""

    @property
    def resolved(self) -> bool:
        """True when polling can stop."""
        return self is not ClaimOutcome.PENDING


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
    claim: ClaimOutcome = ClaimOutcome.NOT_APPLICABLE
    """What became of the idempotency claim. ``PENDING`` means the caller
    should poll :meth:`CapabilityRouter.settle`; ``STUCK`` means the effect is
    uncertain and the claim is held for a human."""

    @property
    def settled(self) -> bool:
        """True when no further polling is needed."""
        return self.claim.resolved


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
        self._claims_by_handle: dict[str, str] = {}
        """handle id -> idempotency key, for the claims *this router* issued.

        The router is what took the claim, so it is the authority on whether a
        handle has one. Depending on the adapter to echo the key made the two
        cases indistinguishable -- a read-only task and a side-effecting task
        whose adapter simply did not echo -- and the second one silently
        stranded the claim.
        """

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

        # 0. A mismatched task is a caller bug, not a policy question. Checking
        #    it first keeps the trail clean: otherwise an allow is written and
        #    then nothing follows it.
        task = self._task_for(request, task)

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

        if key is not None:
            self._claims_by_handle[handle.id] = key
        state = self._state_of(backend, handle)
        outcome = self._settle_claim(key, state, handle)
        # ``state is None`` means status() raised: we do not know what happened,
        # and recording that as a plain result would assert a certainty the code
        # has explicitly refused to have.
        uncertain = state is None or state is TaskState.INTERRUPTED
        failed = uncertain or state in {TaskState.FAILED, TaskState.CANCELLED}
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
                    "claim": outcome.value,
                    "effect_uncertain": uncertain,
                },
            )
        )

        return Invocation(
            decision=decision,
            handle=handle,
            backend_id=backend.id,
            event_id=event.event.id,
            idempotency_key=key,
            claim=outcome,
        )

    def settle(
        self,
        backend: AgentBackend,
        handle: TaskHandle,
        idempotency_key: str | None = None,
    ) -> ClaimOutcome:
        """Resolve an in-flight claim for an asynchronous task.

        A queued effect that later fails must not stay recorded as done, or the
        legitimate retry is suppressed and the message is never sent. Callers
        poll this until it returns True.

        The key is resolved from the router's own record of the claim it
        issued, falling back to an explicit argument or one the adapter echoed
        on the handle. Disagreement between any two is refused rather than
        guessed, since settling one action off another's status would mark a
        send DONE that never happened.
        """
        known = self._claims_by_handle.get(handle.id)
        echoed = handle.idempotency_key
        for label, candidate in (("router record", known), ("handle", echoed)):
            if idempotency_key is not None and candidate is not None and idempotency_key != candidate:
                # A transposed pair would settle one action off another's
                # status, marking a send DONE that never happened.
                raise ValueError(
                    f"idempotency key {idempotency_key[:12]}… disagrees with the {label} for "
                    f"handle {handle.id} ({candidate[:12]}…); refusing to settle the wrong claim"
                )
        key = known or idempotency_key or echoed
        if key is None:
            # Either read-only, or a handle this router never issued. Nothing to
            # settle is a valid answer, so a generic poll loop does not crash on
            # the first non-side-effecting handle.
            return ClaimOutcome.NOT_APPLICABLE
        outcome = self._settle_claim(key, self._state_of(backend, handle), handle)
        if outcome in {ClaimOutcome.COMPLETED, ClaimOutcome.RELEASED}:
            self._claims_by_handle.pop(handle.id, None)
        return outcome

    def stuck_claims(self) -> list[str]:
        """Idempotency keys held but unresolved -- work in flight, or stuck.

        Either way they block the retry, so they must be visible rather than
        silently permanent.
        """
        return self._idempotency.in_flight()

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

    def _settle_claim(
        self, key: str | None, state: TaskState | None, handle: TaskHandle | None = None
    ) -> ClaimOutcome:
        """Complete or release a claim, covering every terminal state."""
        if key is None:
            return ClaimOutcome.NOT_APPLICABLE
        if state is TaskState.SUCCEEDED:
            # Keep the result reference: DONE means "return what happened
            # before", which is impossible without it.
            self._idempotency.complete(key, handle.id if handle else None)
            return ClaimOutcome.COMPLETED
        if state in {TaskState.FAILED, TaskState.CANCELLED}:
            self._release(key)
            return ClaimOutcome.RELEASED
        if state is TaskState.INTERRUPTED:
            # Terminal, but the effect may have partly landed. Hold the claim
            # and surface it rather than guessing in either direction.
            return ClaimOutcome.STUCK
        return ClaimOutcome.PENDING

    def _release(self, key: str | None) -> None:
        if key is not None:
            self._idempotency.release(key)
