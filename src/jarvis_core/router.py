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
from .idempotency import ClaimToken, IdempotencyLedger, derive_key
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
    """What became of a side effect's idempotency claim, as of dispatch.

    Deliberately small. An earlier version modelled a full asynchronous
    settlement protocol -- handle bindings, a polling loop, five states -- for
    backends that do not exist yet, against a ledger that is not durable yet.
    Every review round found a new hole in it. The core stays small on purpose
    (docs/04 Rule 3), so the router now reports what it knows and hands the
    caller a token to resolve the rest.
    """

    NOT_APPLICABLE = "not_applicable"
    """The capability is not side-effecting; there was never a claim."""
    COMPLETED = "completed"
    RELEASED = "released"
    """Definitively did not take effect. A retry is legitimate."""
    HELD = "held"
    """The outcome is not yet known, so the claim is held and the action stays
    blocked. The caller owns the token and resolves it when it finds out."""

    @property
    def resolved(self) -> bool:
        return self is not ClaimOutcome.HELD


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
    claim_token: ClaimToken | None = None
    """Held by the caller. Required to resolve a ``HELD`` claim later, and what
    stops a late resolution from an abandoned attempt settling a newer one."""
    claim: ClaimOutcome = ClaimOutcome.NOT_APPLICABLE

    @property
    def idempotency_key(self) -> str | None:
        return self.claim_token.key if self.claim_token else None

    @property
    def settled(self) -> bool:
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

        # 0. A mismatched task is a caller bug, not a policy question -- but the
        #    attempt is still recorded as a refusal. Raising silently would let
        #    any caller suppress the audit trail of its own probing by attaching
        #    a mismatched task.
        try:
            task = self._task_for(request, task)
        except TaskMismatch as exc:
            self._record_decision(
                request,
                Decision(
                    outcome=Outcome.DENY,
                    reason=f"task does not match the request: {exc}",
                    capability=request.capability,
                ),
                actor,
            )
            raise

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
        token = self._claim_if_side_effecting(capability, request)
        key = token.key if token else None

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
            if token is not None:
                self._idempotency.release(token)
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
                        # Only a side effect can be uncertain. A read that
                        # raised simply did not happen.
                        "effect_uncertain": token is not None,
                        "dispatch_failed": True,
                        "status_unreadable": False,
                        "claim": (
                            ClaimOutcome.HELD if token else ClaimOutcome.NOT_APPLICABLE
                        ).value,
                    },
                )
            )
            if token is not None:
                # The claim is held here too -- and this is the most common way
                # an action gets stranded, so it must be enumerable by kind
                # like every other held claim.
                self._record_claim_held(
                    request, task, event.event.id, token, None, dispatch_failed=True
                )
            raise

        state = self._state_of(backend, handle)
        outcome = self._resolve_at_dispatch(token, state, handle)
        # One event, one meaning. Overloading TOOL_ERROR to also mean "needs
        # attention" is what kept making healthy queued work look like a
        # failure, so a held claim now gets its own kind (CLAIM_HELD) and this
        # event only describes how the *task* is going.
        #
        #   state       | kind        | effect_uncertain (claim only)
        #   ------------|-------------|------------------------------
        #   SUCCEEDED   | TOOL_RESULT | no
        #   PENDING     | TOOL_RESULT | yes  + CLAIM_HELD
        #   RUNNING     | TOOL_RESULT | yes  + CLAIM_HELD
        #   FAILED      | TOOL_ERROR  | no   (promises the effect did not land)
        #   CANCELLED   | TOOL_ERROR  | yes  + CLAIM_HELD
        #   INTERRUPTED | TOOL_ERROR  | yes  + CLAIM_HELD
        #   None        | TOOL_ERROR  | yes  + CLAIM_HELD   (status unreadable)
        status_unreadable = state is None
        went_wrong = status_unreadable or state in {
            TaskState.FAILED, TaskState.CANCELLED, TaskState.INTERRUPTED
        }
        uncertain = outcome is ClaimOutcome.HELD
        self._record.append(
            make_event(
                # A backend that reports failure immediately must not be
                # recorded as a result, or the trail cannot tell it from success.
                EventKind.TOOL_ERROR if went_wrong else EventKind.TOOL_RESULT,
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
                    "dispatch_failed": False,  # execute() returned a handle
                    "status_unreadable": status_unreadable,
                },
            )
        )

        if uncertain:
            self._record_claim_held(
                request, task, event.event.id, token, state, handle_id=handle.id
            )

        return Invocation(
            decision=decision,
            handle=handle,
            backend_id=backend.id,
            event_id=event.event.id,
            claim_token=token,
            claim=outcome,
        )

    def resolve(
        self,
        token: ClaimToken,
        outcome: ClaimOutcome,
        result_ref: str | None = None,
        *,
        session: str = "operator",
        subject_keys: tuple[str, ...] = ("system",),
        caused_by: str | None = None,
    ) -> bool:
        """Resolve a ``HELD`` claim once the caller knows what happened.

        The token carries the attempt's generation, so a late resolution from
        an abandoned attempt cannot settle a newer one that shares the key.
        Returns False when the token has been superseded.

        Pass ``session``, ``subject_keys`` and ``caused_by`` from the original
        :class:`Invocation`, so the resolution lands in the same session's
        audit trail as the ``claim.held`` it closes. Left at their defaults the
        held notice still reads as stranded in that session's trail, which is
        the thing this event exists to prevent.

        Use ``RELEASED`` only when the side effect provably did not happen: a
        wrongly released claim sends the message twice, while a claim left held
        merely needs a human.
        """
        if outcome is ClaimOutcome.COMPLETED:
            applied = self._idempotency.complete(token, result_ref)
        elif outcome is ClaimOutcome.RELEASED:
            applied = self._idempotency.release(token)
        else:
            raise ValueError(f"cannot resolve a claim as {outcome.value!r}")

        if not applied:
            return False

        # Close out the claim.held notice. The ledger is already mutated, so a
        # failure here leaves a settled claim with no closing event that no
        # retry can write -- both resolve() and force_release() would be
        # refused by the state and generation checks. Surface it rather than
        # swallow it, exactly as force_release does.
        try:
            self._record.append(
                make_event(
                    EventKind.CLAIM_RESOLVED,
                    actor=Actor.SYSTEM,
                    session=session,
                    subject_keys=subject_keys,
                    parent=[caused_by] if caused_by else (),
                    meta={
                        "idempotency_key": token.key,
                        "generation": token.generation,
                        "outcome": outcome.value,
                        "result_ref": result_ref,
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001 -- surface, never swallow
            raise JarvisCoreError(
                f"claim {token.key} was resolved as {outcome.value} but the closing "
                "event could not be recorded; reconcile manually"
            ) from exc
        return True

    def force_release(
        self,
        key: str,
        *,
        operator: str = "system",  # same prefixed form as Request.actor
        reason: str = "",
        session: str = "operator",
        caused_by: str | None = None,
    ) -> bool:
        """Free a claim whose token was lost -- an operator escape hatch.

        A token normally dies with the exception that stranded its claim, and
        a ``HELD`` claim outlives the process that holds its token. Without a
        key-based path those keys appear in :meth:`outstanding_claims` with no
        way to act on them, and the action is suppressed forever.

        **This bypasses the generation guard**, so it can free a live claim as
        well as a dead one. Use it only after establishing that the side effect
        did not happen: a wrongly released claim sends the message twice. It is
        recorded as a permanent ``claim.override`` event for exactly that
        reason -- it is the one operation that can deliberately cause a
        duplicate effect, so it must never be invisible.

        ``operator`` takes the same prefixed form as :attr:`Request.actor`
        (``"user:harrison"``, ``"watcher:claim-gc"``), so an automated caller
        is not recorded as a person authorizing a duplicate effect.

        Pass ``session`` and ``caused_by`` (the stranded invoke's event id) so
        the override lands in the affected session's audit trail and in the
        causal walk from the invocation it unblocks. Without them the only
        link is the key in meta.
        """
        claim = self._idempotency.peek(key)
        if claim is None:
            return False
        # The release is authoritative, so it happens first and only a release
        # that actually occurred is recorded -- otherwise the trail claims an
        # override that never happened. The residual risk is the reverse: if
        # the append fails, a freed claim goes unrecorded. That is re-raised
        # with the key so it can be reconciled, and a Record that cannot accept
        # a write is a system-wide failure anyway, since every invoke writes.
        released = self._idempotency.release(claim.token)
        if not released:
            return False
        try:
            self._record.append(
                make_event(
                    EventKind.CLAIM_OVERRIDE,
                    actor=_actor_of(operator),
                    actor_id=operator,
                    session=session,
                    subject_keys=("system",),
                    parent=[caused_by] if caused_by else (),
                    meta={
                        "idempotency_key": key,
                        "generation": claim.generation,
                        "reason": reason,
                        "note": "a released claim permits the action to run again",
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001 -- surface, never swallow
            raise JarvisCoreError(
                f"claim {key} was released but the override could not be recorded; "
                "reconcile manually"
            ) from exc
        return True

    def outstanding_claims(self) -> list[str]:
        """Idempotency keys held but unresolved.

        Named honestly: this is *everything* in flight, which includes healthy
        work still running as well as genuinely stuck claims. Calling it
        "stuck" would invite an operator to release a live claim, and the
        action would then run twice.
        """
        return self._idempotency.in_flight()

    # -- internals -------------------------------------------------------

    def _record_claim_held(
        self,
        request: Request,
        task: Task,
        caused_by: str,
        token: ClaimToken | None,
        state: TaskState | None,
        *,
        dispatch_failed: bool = False,
        handle_id: str | None = None,
    ) -> None:
        """Note that a side effect's fate is undetermined.

        Its own kind rather than an overloaded ``tool.error``: a queued task is
        not a failure, but every retry of the action is blocked until someone
        resolves it, so it has to be visible in the audit trail.
        """
        self._record.append(
            make_event(
                EventKind.CLAIM_HELD,
                actor=Actor.SYSTEM,
                session=request.session,
                subject_keys=task.subject_keys or ("system",),
                parent=[caused_by],
                meta={
                    "capability": request.capability,
                    "idempotency_key": token.key if token else None,
                    # "never dispatched" and "dispatched, status endpoint down"
                    # both read as unknown state, but need opposite recovery
                    # before an operator force-releases either.
                    "state": state.value if state else "unknown",
                    "dispatch_failed": dispatch_failed,
                    "handle": handle_id,
                    "note": "every retry of this action is blocked until resolved",
                },
            )
        )

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
    ) -> ClaimToken | None:
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
        return claim.token

    @staticmethod
    def _state_of(backend: AgentBackend, handle: TaskHandle) -> TaskState | None:
        try:
            return backend.status(handle).state
        except Exception:
            return None  # unknown: never guess about a side effect

    def _resolve_at_dispatch(
        self, token: ClaimToken | None, state: TaskState | None, handle: TaskHandle | None
    ) -> ClaimOutcome:
        """Resolve what is knowable at dispatch; hold the rest.

        Anything other than a clear success or a clear non-effect leaves the
        claim held -- pending work, an interrupted effect that may have partly
        landed, or a status call that raised. Guessing in either direction is
        how a message gets sent twice or never.
        """
        if token is None:
            return ClaimOutcome.NOT_APPLICABLE
        if state is TaskState.SUCCEEDED:
            # Keep the result reference: DONE means "return what happened
            # before", which is impossible without it.
            self._idempotency.complete(token, handle.id if handle else None)
            return ClaimOutcome.COMPLETED
        if state is not None and state.guarantees_no_effect:
            # Only FAILED promises the effect did not happen. A cancelled send
            # the provider already accepted would otherwise free the claim and
            # the retry would send twice.
            self._idempotency.release(token)
            return ClaimOutcome.RELEASED
        return ClaimOutcome.HELD


