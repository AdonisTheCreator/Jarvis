"""The Capability Router: authorize, claim, execute, record -- in that order."""
import pytest

from jarvis_core.autonomy import AutonomyClass as A
from jarvis_core.backend import (
    AgentBackend, Estimate, HealthStatus, Task, TaskHandle, TaskState, TaskStatus,
)
from jarvis_core.capability import Capability, CapabilityRegistry
from jarvis_core.errors import ApprovalRequired, PolicyDenied
from jarvis_core.ids import new_ulid
from jarvis_core.policy import PolicyEngine, Request
from jarvis_core.record import Actor, EventKind, RecordStore
from jarvis_core.router import (
    CapabilityRouter, ClaimOutcome, DuplicateSuppressed, NoBackendAvailable, TaskMismatch,
)


class FakeBackend(AgentBackend):
    def __init__(self, backend_id, capabilities, *, healthy=True,
                 cost=0.0, latency=100.0, confidence=0.9):
        self._id, self._caps, self._healthy = backend_id, tuple(capabilities), healthy
        self._estimate = Estimate(cost_usd=cost, latency_ms=latency, confidence=confidence)
        self.executions: list[tuple[Task, str | None]] = []

    @property
    def id(self): return self._id

    @property
    def capabilities(self): return self._caps

    def health(self): return HealthStatus(healthy=self._healthy)

    def estimate(self, task): return self._estimate

    def execute(self, task, idempotency_key=None):
        self.executions.append((task, idempotency_key))
        return TaskHandle(id=new_ulid(), backend_id=self._id, idempotency_key=idempotency_key)

    def status(self, handle):
        return TaskStatus(handle=handle, state=TaskState.SUCCEEDED)


class TestRouting:
    def test_picks_the_highest_scoring_healthy_backend(self, registry, engine, store):
        router = CapabilityRouter(registry, engine, store)
        slow = FakeBackend("slow", ["ci.read_status"], latency=5000.0, confidence=0.9)
        fast = FakeBackend("fast", ["ci.read_status"], latency=50.0, confidence=0.9)
        router.register_backend(slow)
        router.register_backend(fast)
        assert router.choose(Task("ci.read_status", "repo")).id == "fast"

    def test_confidence_outweighs_raw_speed(self, registry, engine, store):
        router = CapabilityRouter(registry, engine, store)
        router.register_backend(FakeBackend("quick_wrong", ["ci.read_status"],
                                            latency=10.0, confidence=0.2))
        router.register_backend(FakeBackend("solid", ["ci.read_status"],
                                            latency=200.0, confidence=0.95))
        assert router.choose(Task("ci.read_status", "repo")).id == "solid"

    def test_unhealthy_backends_are_skipped(self, registry, engine, store):
        router = CapabilityRouter(registry, engine, store)
        router.register_backend(FakeBackend("down", ["ci.read_status"], healthy=False))
        with pytest.raises(NoBackendAvailable):
            router.choose(Task("ci.read_status", "repo"))

    def test_routing_does_not_call_a_model(self, router):
        """estimate() runs on every decision; a model call here stacks latency."""
        import time

        started = time.perf_counter()
        for _ in range(1000):
            router.candidates(Task("ci.read_status", "repo"))
        assert (time.perf_counter() - started) < 0.5


class TestInvokePath:
    def test_policy_runs_before_any_backend_is_touched(self, registry, engine, store):
        router = CapabilityRouter(registry, engine, store)
        backend = FakeBackend("primary", ["vehicle.drive"])
        router.register_backend(backend)
        with pytest.raises(PolicyDenied):
            router.invoke(Request("vehicle.drive", "car"))
        assert backend.executions == []

    def test_approval_gate_blocks_execution(self, router):
        with pytest.raises(ApprovalRequired):
            router.invoke(Request("message.send", "sam", {"to": "sam", "body": "hi"}))

    def test_successful_invoke_is_recorded_with_its_authority(self, router, store: RecordStore):
        result = router.invoke(Request("ci.rerun_job", "job-1", {"job_id": "job-1"}))
        assert result.handle is not None and result.backend_id == "primary"
        events = [s.event for s in store.scan(kinds=[EventKind.CAPABILITY_INVOKE])]
        assert len(events) == 1
        meta = events[0].meta
        assert meta["capability"] == "ci.rerun_job"
        assert meta["backend"] == "primary"
        assert "permitted" in meta["policy"]

    def test_side_effecting_calls_are_exactly_once(self, router):
        request = Request("ci.rerun_job", "job-1", {"job_id": "job-1"})
        first = router.invoke(request)
        assert first.idempotency_key is not None
        with pytest.raises(DuplicateSuppressed):
            router.invoke(request)

    def test_suppression_carries_the_earlier_result(self, router):
        """The other half of exactly-once: return what happened before, rather
        than only reporting that the repeat was stopped."""
        request = Request("ci.rerun_job", "j", {"job_id": "j"})
        first = router.invoke(request)
        with pytest.raises(DuplicateSuppressed) as caught:
            router.invoke(request)
        assert caught.value.result_ref == first.handle.id
        assert caught.value.state == "done"

    def test_a_different_action_is_not_suppressed(self, router):
        router.invoke(Request("ci.rerun_job", "job-1", {"job_id": "job-1"}))
        second = router.invoke(Request("ci.rerun_job", "job-2", {"job_id": "job-2"}))
        assert second.handle is not None

    def test_read_only_calls_take_no_idempotency_key(self, router):
        assert router.invoke(Request("ci.read_status", "repo")).idempotency_key is None

    def test_the_record_verifies_after_a_run(self, router, store: RecordStore):
        router.invoke(Request("ci.read_status", "repo"))
        router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        # Three events per call now: the policy decision, the invoke, the result.
        assert store.verify() == 6

    def test_outcomes_are_recorded_not_just_attempts(self, router, store: RecordStore):
        result = router.invoke(Request("ci.read_status", "repo"))
        results = [s.event for s in store.scan(kinds=[EventKind.TOOL_RESULT])]
        assert len(results) == 1
        assert results[0].parent == (result.event_id,)

    def test_a_failed_execution_is_recorded_as_uncertain(self, registry, engine, store):
        class Exploding(FakeBackend):
            def execute(self, task, idempotency_key=None):
                raise RuntimeError("backend fell over")

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Exploding("flaky", ["ci.rerun_job"]))
        with pytest.raises(RuntimeError):
            router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))

        errors = [s.event for s in store.scan(kinds=[EventKind.TOOL_ERROR])]
        assert len(errors) == 1
        assert errors[0].meta["effect_uncertain"] is True
        # decision + invoke + tool.error + claim.held
        assert store.verify() == 4

    def test_a_failed_call_leaves_the_claim_in_flight(self, registry, engine, store):
        """A stuck claim needs a human; a wrongly released one sends twice."""
        class Exploding(FakeBackend):
            def execute(self, task, idempotency_key=None):
                raise RuntimeError("boom")

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Exploding("flaky", ["ci.rerun_job"]))
        request = Request("ci.rerun_job", "j", {"job_id": "j"})
        with pytest.raises(RuntimeError):
            router.invoke(request)
        with pytest.raises(DuplicateSuppressed):
            router.invoke(request)


class TestReviewFindings:
    """Regression coverage for the seven findings from the Phase 0 review."""

    def test_a_routing_failure_does_not_strand_the_claim(self, registry, engine, store):
        """Claim after choose: otherwise a retry is blocked forever once the
        backend recovers."""
        router = CapabilityRouter(registry, engine, store)
        request = Request("ci.rerun_job", "j", {"job_id": "j"})
        with pytest.raises(NoBackendAvailable):
            router.invoke(request)
        router.register_backend(FakeBackend("late", ["ci.rerun_job"]))
        assert router.invoke(request).handle is not None

    def test_a_task_cannot_disagree_with_the_request_it_was_authorized_under(self, router):
        """Otherwise an authorized read carries an unauthorized write."""
        with pytest.raises(TaskMismatch):
            router.invoke(
                Request("ci.read_status", "repo"),
                Task("ci.rerun_job", "prod-deploy", {"job_id": "prod-deploy"}),
            )
        with pytest.raises(TaskMismatch):
            router.invoke(Request("ci.read_status", "repo"), Task("ci.read_status", "other"))

    def test_refusals_leave_a_trail(self, router, store: RecordStore):
        """A quarantined agent probing every capability must be visible."""
        for capability in ("ci.read_status", "ci.rerun_job", "message.send"):
            with pytest.raises(PolicyDenied):
                router.invoke(Request(capability, "t", quarantined=True))
        decisions = [s.event for s in store.scan(kinds=[EventKind.POLICY_DECISION])]
        assert len(decisions) == 3
        assert all(e.meta["quarantined"] is True for e in decisions)

    def test_machine_refusals_are_not_recorded_as_human_denials(self, router, store):
        """'The kill switch stopped it' must not read as 'you said no'."""
        with pytest.raises(PolicyDenied):
            router.invoke(Request("vehicle.drive", "car"))
        assert [s.event for s in store.scan(kinds=[EventKind.APPROVAL_DENY])] == []
        decisions = [s.event for s in store.scan(kinds=[EventKind.POLICY_DECISION])]
        assert decisions[-1].meta["outcome"] == "deny"

    def test_an_approval_gate_is_recorded_as_a_correlatable_request(self, router, store):
        """The recorded event must carry the id the user actually acts on."""
        with pytest.raises(ApprovalRequired) as caught:
            router.invoke(Request("message.send", "sam", {"to": "sam", "body": "hi"}))
        requests = [s.event for s in store.scan(kinds=[EventKind.APPROVAL_REQUEST])]
        assert len(requests) == 1 and requests[0].is_permanent
        assert requests[0].meta["approval_request_id"] == caught.value.request_id

    def test_unknown_capability_raises_the_documented_refusal_type(self, router):
        """Not a raw KeyError -- callers catch PolicyDenied."""
        with pytest.raises(PolicyDenied, match="unknown capability"):
            router.invoke(Request("nope.invent", "t"))

    def test_a_failure_is_visible_in_the_audit_trail(self, registry, engine, store):
        """An invoke with no sign of what became of it is a broken trail."""
        from jarvis_core.record.projections import AuditProjection

        class Exploding(FakeBackend):
            def execute(self, task, idempotency_key=None):
                raise RuntimeError("boom")

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Exploding("flaky", ["ci.rerun_job"]))
        with pytest.raises(RuntimeError):
            router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        kinds = [e.kind for e in AuditProjection(store).trail()]
        assert EventKind.TOOL_ERROR in kinds


class TestClaimLifecycle:
    """Exactly-once, and what happens when the outcome is not yet knowable.

    The router resolves what it can see at dispatch and hands the caller a
    token for the rest. An earlier version modelled a full asynchronous
    settlement protocol for backends that do not exist yet; it was removed
    (docs/09 D19) rather than patched further.
    """

    def test_task_params_cannot_differ_from_the_authorized_request(self, router):
        """The approval is fingerprinted over request.params; a task carrying
        different ones would execute an action the human never saw."""
        with pytest.raises(TaskMismatch, match="params"):
            router.invoke(
                Request("ci.rerun_job", "j", {"job_id": "j"}),
                Task("ci.rerun_job", "j", {"job_id": "SOMETHING-ELSE"}),
            )

    def test_matching_params_are_accepted(self, router):
        params = {"job_id": "j"}
        result = router.invoke(Request("ci.rerun_job", "j", params),
                               Task("ci.rerun_job", "j", params))
        assert result.handle is not None

    def test_a_clear_success_completes_the_claim(self, router):
        result = router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        assert result.claim is ClaimOutcome.COMPLETED
        assert router._idempotency.claim(result.idempotency_key).result_ref == result.handle.id

    def test_only_failed_releases_the_claim(self, registry, engine, store):
        """CANCELLED may mean the provider already accepted it, so releasing
        there would let the retry send twice. Only FAILED promises no effect."""
        from jarvis_core.backend import TaskState as TS

        assert TS.FAILED.guarantees_no_effect is True
        for state in (TS.CANCELLED, TS.INTERRUPTED, TS.SUCCEEDED, TS.PENDING):
            assert state.guarantees_no_effect is False

        class Cancelled(FakeBackend):
            def status(self, handle):
                return TaskStatus(handle=handle, state=TS.CANCELLED)

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Cancelled("cancelling", ["ci.rerun_job"]))
        result = router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        assert result.claim is ClaimOutcome.HELD
        # The Record must agree with the ledger: a held claim means uncertain.
        errors = [s.event for s in store.scan(kinds=[EventKind.TOOL_ERROR])]
        assert errors[-1].meta["effect_uncertain"] is True

    def test_a_lost_token_can_still_be_recovered_by_an_operator(
        self, registry, engine, store
    ):
        """A token dies with the exception that stranded its claim, and a HELD
        claim outlives the process holding it. Without a key-based path those
        keys are listed with no way to act on them."""
        class RecoveringBackend(FakeBackend):
            """Fails once, then works -- as a real transient outage would."""

            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.healthy_now = False

            def execute(self, task, idempotency_key=None):
                if not self.healthy_now:
                    raise RuntimeError("transient outage")
                return super().execute(task, idempotency_key)

        router = CapabilityRouter(registry, engine, store)
        backend = RecoveringBackend("flaky", ["ci.rerun_job"])
        router.register_backend(backend)
        request = Request("ci.rerun_job", "j", {"job_id": "j"})
        with pytest.raises(RuntimeError):
            router.invoke(request)

        # The claim is held, correctly -- but its token died with the exception.
        stranded = router.outstanding_claims()
        assert len(stranded) == 1
        backend.healthy_now = True
        with pytest.raises(DuplicateSuppressed):
            router.invoke(request)

        assert router.force_release(stranded[0]) is True
        assert router.outstanding_claims() == []
        assert router.invoke(request).handle is not None

    def test_force_release_reports_when_there_was_nothing_to_free(self, router):
        assert router.force_release("no-such-key") is False

    def test_an_override_is_permanently_recorded(self, registry, engine, store):
        """The one operation that can deliberately cause a duplicate effect
        must never be invisible in the trail."""
        from jarvis_core.record.projections import AuditProjection

        class Exploding(FakeBackend):
            def execute(self, task, idempotency_key=None):
                raise RuntimeError("boom")

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Exploding("flaky", ["ci.rerun_job"]))
        with pytest.raises(RuntimeError):
            router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))

        invoke_event = [s.event for s in store.scan(kinds=[EventKind.CAPABILITY_INVOKE])][0]
        key = router.outstanding_claims()[0]
        assert router.force_release(
            key, operator="user:harrison", reason="verified not sent",
            session="s1", caused_by=invoke_event.id,
        )

        overrides = [s.event for s in store.scan(kinds=[EventKind.CLAIM_OVERRIDE])]
        assert len(overrides) == 1
        assert overrides[0].is_permanent
        assert overrides[0].meta["reason"] == "verified not sent"
        assert overrides[0].actor_id == "user:harrison"
        assert overrides[0].actor is Actor.USER
        assert EventKind.CLAIM_OVERRIDE in [e.kind for e in AuditProjection(store).trail()]
        # Reachable from the affected session and from the invocation it unblocks.
        assert EventKind.CLAIM_OVERRIDE in [
            e.kind for e in AuditProjection(store).trail(session="s1")
        ]
        assert overrides[0].id in {e.id for e in AuditProjection(store).why(overrides[0].id)}
        assert invoke_event.id in {e.id for e in AuditProjection(store).why(overrides[0].id)}

    def test_an_automated_override_is_not_attributed_to_a_human(
        self, registry, engine, store
    ):
        """The exact mis-attribution _actor_of exists to prevent."""
        class Exploding(FakeBackend):
            def execute(self, task, idempotency_key=None):
                raise RuntimeError("boom")

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Exploding("flaky", ["ci.rerun_job"]))
        with pytest.raises(RuntimeError):
            router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        router.force_release(router.outstanding_claims()[0], operator="watcher:claim-gc")
        override = [s.event for s in store.scan(kinds=[EventKind.CLAIM_OVERRIDE])][0]
        assert override.actor is Actor.WATCHER

    # The full truth table from router.py, pinned so the three facts cannot
    # drift back into one another. (capability, state) -> (kind, uncertain).
    @pytest.mark.parametrize(
        "capability,state,expect_error,expect_uncertain",
        [
            # Side-effecting: a claim exists, so certainty is meaningful.
            ("ci.rerun_job", TaskState.SUCCEEDED, False, False),
            ("ci.rerun_job", TaskState.FAILED, True, False),
            ("ci.rerun_job", TaskState.CANCELLED, True, True),
            ("ci.rerun_job", TaskState.INTERRUPTED, True, True),
            ("ci.rerun_job", TaskState.PENDING, False, True),
            ("ci.rerun_job", TaskState.RUNNING, False, True),
            ("ci.rerun_job", TaskState.AWAITING_APPROVAL, False, True),
            ("ci.rerun_job", None, True, True),
            # Read-only: no claim, so nothing can be uncertain about an effect.
            ("ci.read_status", TaskState.SUCCEEDED, False, False),
            ("ci.read_status", TaskState.PENDING, False, False),
            ("ci.read_status", TaskState.RUNNING, False, False),
            ("ci.read_status", TaskState.FAILED, True, False),
            ("ci.read_status", None, True, False),
        ],
    )
    def test_the_event_truth_table(
        self, registry, engine, store, capability, state, expect_error, expect_uncertain
    ):
        """Three facts, computed separately: did the dispatch go cleanly, is a
        side effect's fate unknown, and must the trail show it."""
        from jarvis_core.record.projections import AuditProjection

        class Reporting(FakeBackend):
            def status(self, handle):
                if state is None:
                    raise RuntimeError("status endpoint down")
                return TaskStatus(handle=handle, state=state)

        label = f"{capability}-{state.value if state else 'none'}"
        fresh = RecordStore(store.root / label, store._keystore)
        router = CapabilityRouter(registry, engine, fresh)
        router.register_backend(Reporting("r", [capability]))
        params = {"job_id": "j"} if capability == "ci.rerun_job" else {}
        router.invoke(Request(capability, "j", params))

        kind = EventKind.TOOL_ERROR if expect_error else EventKind.TOOL_RESULT
        events = [s.event for s in fresh.scan(kinds=[kind])]
        assert len(events) == 1, f"{label} should be a {kind.value}"
        assert events[0].meta["effect_uncertain"] is expect_uncertain

        # A held claim is not a failure, but it blocks every retry of the
        # action, so it gets its own audit-visible kind rather than being
        # squeezed into TOOL_ERROR.
        trail = [e.kind for e in AuditProjection(fresh).trail()]
        assert (EventKind.TOOL_ERROR in trail) is expect_error, f"{label} failure visibility"
        assert (EventKind.CLAIM_HELD in trail) is expect_uncertain, f"{label} held visibility"

        # Healthy in-flight work still reaches the subconscious as a trace.
        if not expect_error:
            from jarvis_core.record.projections import ConsolidateProjection
            assert ConsolidateProjection(fresh).pending().total >= 1, label

    def test_a_dispatch_failure_also_records_the_held_claim(
        self, registry, engine, store
    ):
        """The most common way an action gets stranded -- so it must be
        enumerable by kind like every other held claim."""
        class Exploding(FakeBackend):
            def execute(self, task, idempotency_key=None):
                raise RuntimeError("boom")

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Exploding("flaky", ["ci.rerun_job"]))
        with pytest.raises(RuntimeError):
            router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))

        held = [s.event for s in store.scan(kinds=[EventKind.CLAIM_HELD])]
        assert len(held) == 1 and held[0].is_permanent
        assert held[0].meta["idempotency_key"] == router.outstanding_claims()[0]
        error = [s.event for s in store.scan(kinds=[EventKind.TOOL_ERROR])][0]
        assert error.meta["claim"] == "held"

    def test_a_failed_read_is_never_recorded_as_an_uncertain_effect(
        self, registry, engine, store
    ):
        """Only a side effect can be uncertain. A read that raised simply did
        not happen."""
        class Exploding(FakeBackend):
            def execute(self, task, idempotency_key=None):
                raise RuntimeError("boom")

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Exploding("flaky", ["ci.read_status"]))
        with pytest.raises(RuntimeError):
            router.invoke(Request("ci.read_status", "repo"))
        error = [s.event for s in store.scan(kinds=[EventKind.TOOL_ERROR])][0]
        assert error.meta["effect_uncertain"] is False
        assert error.meta["dispatch_failed"] is True
        # No claim existed, so nothing is held.
        assert [s.event for s in store.scan(kinds=[EventKind.CLAIM_HELD])] == []

    def test_dispatch_failure_is_distinct_from_an_unreadable_status(
        self, registry, engine, store
    ):
        """A backend whose dispatch path is healthy and whose status endpoint
        is merely down must not be scored as a failed dispatch."""
        class Silent(FakeBackend):
            def status(self, handle):
                raise RuntimeError("status endpoint down")

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Silent("silent", ["ci.rerun_job"]))
        router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        error = [s.event for s in store.scan(kinds=[EventKind.TOOL_ERROR])][0]
        assert error.meta["dispatch_failed"] is False
        assert error.meta["status_unreadable"] is True

    def test_an_unattributed_override_is_not_recorded_as_a_person(
        self, registry, engine, store
    ):
        class Exploding(FakeBackend):
            def execute(self, task, idempotency_key=None):
                raise RuntimeError("boom")

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Exploding("flaky", ["ci.rerun_job"]))
        with pytest.raises(RuntimeError):
            router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        router.force_release(router.outstanding_claims()[0])  # no operator given
        override = [s.event for s in store.scan(kinds=[EventKind.CLAIM_OVERRIDE])][0]
        assert override.actor is Actor.SYSTEM

    def test_a_failed_read_still_reaches_the_audit_trail(self, registry, engine, store):
        """Read-only work has no claim, but a failed read must not vanish."""
        from jarvis_core.record.projections import AuditProjection

        class Silent(FakeBackend):
            def status(self, handle):
                raise RuntimeError("status endpoint down")

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Silent("silent", ["ci.read_status"]))
        router.invoke(Request("ci.read_status", "repo"))
        assert EventKind.TOOL_ERROR in [e.kind for e in AuditProjection(store).trail()]

    def test_a_failed_override_records_nothing(self, router, store: RecordStore):
        assert router.force_release("no-such-key") is False
        assert [s.event for s in store.scan(kinds=[EventKind.CLAIM_OVERRIDE])] == []

    def test_a_clear_failure_releases_it_for_a_real_retry(self, registry, engine, store):
        class Failing(FakeBackend):
            def status(self, handle):
                return TaskStatus(handle=handle, state=TaskState.FAILED)

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Failing("flaky", ["ci.rerun_job"]))
        request = Request("ci.rerun_job", "j", {"job_id": "j"})
        assert router.invoke(request).claim is ClaimOutcome.RELEASED
        assert router.invoke(request).handle is not None  # retry permitted

    @pytest.mark.parametrize("state", [TaskState.PENDING, TaskState.RUNNING,
                                       TaskState.INTERRUPTED, TaskState.CANCELLED, None])
    def test_anything_unclear_holds_the_claim(self, registry, engine, store, state):
        """Guessing either way sends the message twice, or never."""
        class Unclear(FakeBackend):
            def status(self, handle):
                if state is None:
                    raise RuntimeError("status endpoint down")
                return TaskStatus(handle=handle, state=state)

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Unclear("unclear", ["ci.rerun_job"]))
        result = router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        assert result.claim is ClaimOutcome.HELD and result.settled is False
        assert router.outstanding_claims() == [result.idempotency_key]

    def test_resolving_closes_out_the_held_notice(self, registry, engine, store):
        """Otherwise an operator enumerating held claims by kind sees settled
        actions as stranded -- worse under retention, since claim.held is
        permanent while the paired tool.result is prunable."""
        class Pending(FakeBackend):
            def status(self, handle):
                return TaskStatus(handle=handle, state=TaskState.PENDING)

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Pending("queue", ["ci.rerun_job"]))
        result = router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        assert len([s.event for s in store.scan(kinds=[EventKind.CLAIM_HELD])]) == 1

        router.resolve(
            result.claim_token, ClaimOutcome.COMPLETED, "done",
            session=result.session, subject_keys=result.subject_keys,
            caused_by=result.event_id,
        )
        resolved = [s.event for s in store.scan(kinds=[EventKind.CLAIM_RESOLVED])]
        assert len(resolved) == 1 and resolved[0].is_permanent
        assert resolved[0].meta["idempotency_key"] == result.idempotency_key
        assert resolved[0].meta["outcome"] == "completed"

    def test_a_resolution_lands_in_the_same_trail_as_the_held_notice(
        self, registry, engine, store
    ):
        """Otherwise the held claim still reads as stranded in that session."""
        from jarvis_core.record.projections import AuditProjection

        class Pending(FakeBackend):
            def status(self, handle):
                return TaskStatus(handle=handle, state=TaskState.PENDING)

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Pending("queue", ["ci.rerun_job"]))
        result = router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}, session="s1"))
        router.resolve(
            result.claim_token, ClaimOutcome.COMPLETED, "done",
            session="s1", caused_by=result.event_id,
        )
        kinds = [e.kind for e in AuditProjection(store).trail(session="s1")]
        assert EventKind.CLAIM_HELD in kinds and EventKind.CLAIM_RESOLVED in kinds

    def test_a_concurrently_resolved_claim_is_not_reported_as_ours(
        self, registry, engine, store
    ):
        """Reporting it COMPLETED would leave no DONE row, so the next invoke
        re-sends an effect the Record claims already completed."""
        class Slow(FakeBackend):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.router = None

            def status(self, handle):
                # Someone force-releases while we are asking about status.
                self.router.force_release(self.router.outstanding_claims()[0])
                return TaskStatus(handle=handle, state=TaskState.SUCCEEDED)

        router = CapabilityRouter(registry, engine, store)
        backend = Slow("racy", ["ci.rerun_job"])
        backend.router = router
        router.register_backend(backend)
        result = router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        assert result.claim is ClaimOutcome.ALREADY_RESOLVED
        # The claim says who owns the ledger row; effect_landed says whether
        # retrying is safe. Here the effect did land.
        assert result.effect_landed is True

    @pytest.mark.parametrize(
        "capability,state,expected",
        [
            ("ci.rerun_job", TaskState.SUCCEEDED, True),
            ("ci.rerun_job", TaskState.FAILED, False),
            ("ci.rerun_job", TaskState.CANCELLED, None),
            ("ci.rerun_job", TaskState.INTERRUPTED, None),
            ("ci.rerun_job", TaskState.PENDING, None),
            ("ci.rerun_job", None, None),
            # A read has no side effect, so none landed -- False, meaning
            # safe to retry. None is reserved for genuinely not knowable, and
            # using it here would escalate every failed read to a human.
            ("ci.read_status", TaskState.SUCCEEDED, False),
            ("ci.read_status", TaskState.FAILED, False),
            ("ci.read_status", TaskState.CANCELLED, False),
            ("ci.read_status", None, False),
        ],
    )
    def test_effect_landed_is_independent_of_the_claim_outcome(
        self, registry, engine, store, capability, state, expected
    ):
        """ALREADY_RESOLVED arises from both a success and a failure, so a
        caller deciding retry-safety needs this fact separately."""
        class Reporting(FakeBackend):
            def status(self, handle):
                if state is None:
                    raise RuntimeError("status endpoint down")
                return TaskStatus(handle=handle, state=state)

        label = f"el-{capability}-{state.value if state else 'none'}"
        fresh = RecordStore(store.root / label, store._keystore)
        router = CapabilityRouter(registry, engine, fresh)
        router.register_backend(Reporting("r", [capability]))
        params = {"job_id": "j"} if capability == "ci.rerun_job" else {}
        result = router.invoke(Request(capability, "j", params))
        assert result.effect_landed is expected
        # The documented contract: False means retry is safe, None needs a human.
        if result.effect_landed is False:
            assert result.claim in {ClaimOutcome.RELEASED, ClaimOutcome.NOT_APPLICABLE,
                                    ClaimOutcome.ALREADY_RESOLVED}

    def test_already_resolved_from_a_failure_is_safe_to_retry(
        self, registry, engine, store
    ):
        """The half that produced the wrong retry decision: same claim
        outcome, opposite effect."""
        class RacyFailure(FakeBackend):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                self.router = None

            def status(self, handle):
                self.router.force_release(self.router.outstanding_claims()[0])
                return TaskStatus(handle=handle, state=TaskState.FAILED)

        router = CapabilityRouter(registry, engine, store)
        backend = RacyFailure("racy", ["ci.rerun_job"])
        backend.router = router
        router.register_backend(backend)
        result = router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        assert result.claim is ClaimOutcome.ALREADY_RESOLVED
        assert result.effect_landed is False  # safe to retry

    def test_a_held_notice_can_be_matched_to_its_closer(self, registry, engine, store):
        """Keys hash the action, so attempts share a key; only the generation
        distinguishes a notice from a later attempt's."""
        class Pending(FakeBackend):
            def status(self, handle):
                return TaskStatus(handle=handle, state=TaskState.PENDING)

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Pending("queue", ["ci.rerun_job"]))
        result = router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        router.resolve(result.claim_token, ClaimOutcome.COMPLETED, "done",
                       session=result.session, subject_keys=result.subject_keys)

        held = [s.event for s in store.scan(kinds=[EventKind.CLAIM_HELD])][0]
        resolved = [s.event for s in store.scan(kinds=[EventKind.CLAIM_RESOLVED])][0]
        assert held.meta["generation"] == resolved.meta["generation"]
        assert held.meta["idempotency_key"] == resolved.meta["idempotency_key"]

    def test_an_override_lands_in_the_same_trail_as_its_held_notice(
        self, registry, engine, store
    ):
        from jarvis_core.record.projections import AuditProjection

        class Exploding(FakeBackend):
            def execute(self, task, idempotency_key=None):
                raise RuntimeError("boom")

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Exploding("flaky", ["ci.rerun_job"]))
        with pytest.raises(RuntimeError):
            router.invoke(
                Request("ci.rerun_job", "j", {"job_id": "j"}, session="s1"),
                Task("ci.rerun_job", "j", {"job_id": "j"}, subject_keys=("project:jarvis",)),
            )
        router.force_release(
            router.outstanding_claims()[0],
            session="s1", subject_keys=("project:jarvis",),
        )
        kinds = [e.kind for e in AuditProjection(store).trail(session="s1")]
        assert EventKind.CLAIM_HELD in kinds and EventKind.CLAIM_OVERRIDE in kinds
        override = [s.event for s in store.scan(kinds=[EventKind.CLAIM_OVERRIDE])][0]
        assert override.subject_keys == ("project:jarvis",)

    def test_the_invocation_carries_what_resolve_needs(self, registry, engine, store):
        """A docstring telling callers to read fields off the Invocation is
        only true if the Invocation has them."""
        class Pending(FakeBackend):
            def status(self, handle):
                return TaskStatus(handle=handle, state=TaskState.PENDING)

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Pending("queue", ["ci.rerun_job"]))
        result = router.invoke(
            Request("ci.rerun_job", "j", {"job_id": "j"}, session="s1"),
            Task("ci.rerun_job", "j", {"job_id": "j"}, subject_keys=("project:jarvis",)),
        )
        assert result.session == "s1"
        assert result.subject_keys == ("project:jarvis",)

        router.resolve(
            result.claim_token, ClaimOutcome.COMPLETED, "done",
            session=result.session, subject_keys=result.subject_keys,
            caused_by=result.event_id,
        )
        resolved = [s.event for s in store.scan(kinds=[EventKind.CLAIM_RESOLVED])][0]
        assert resolved.session == "s1"
        assert resolved.subject_keys == ("project:jarvis",)

    def test_resolve_validates_before_touching_the_ledger(self, registry, engine, store):
        """An invalid argument must not settle a claim no path can then close."""
        class Pending(FakeBackend):
            def status(self, handle):
                return TaskStatus(handle=handle, state=TaskState.PENDING)

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Pending("queue", ["ci.rerun_job"]))
        result = router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        for bad in ((), "project:jarvis"):
            with pytest.raises(ValueError, match="subject_keys"):
                router.resolve(result.claim_token, ClaimOutcome.COMPLETED,
                               subject_keys=bad)
        # Still held, and still resolvable.
        assert router.outstanding_claims() == [result.idempotency_key]
        assert router.resolve(result.claim_token, ClaimOutcome.COMPLETED) is True

    def test_a_refused_resolution_records_nothing(self, registry, engine, store):
        class Failing(FakeBackend):
            def status(self, handle):
                return TaskStatus(handle=handle, state=TaskState.FAILED)

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Failing("flaky", ["ci.rerun_job"]))
        request = Request("ci.rerun_job", "j", {"job_id": "j"})
        first = router.invoke(request)
        router.invoke(request)  # supersedes it
        assert router.resolve(first.claim_token, ClaimOutcome.COMPLETED) is False
        assert [s.event for s in store.scan(kinds=[EventKind.CLAIM_RESOLVED])] == []

    def test_never_dispatched_is_distinguishable_from_status_unreadable(
        self, registry, engine, store
    ):
        """They need opposite recovery before an operator force-releases."""
        class Exploding(FakeBackend):
            def execute(self, task, idempotency_key=None):
                raise RuntimeError("boom")

        class Silent(FakeBackend):
            def status(self, handle):
                raise RuntimeError("status endpoint down")

        never = RecordStore(store.root / "never", store._keystore)
        r1 = CapabilityRouter(registry, engine, never)
        r1.register_backend(Exploding("flaky", ["ci.rerun_job"]))
        with pytest.raises(RuntimeError):
            r1.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        held = [s.event for s in never.scan(kinds=[EventKind.CLAIM_HELD])][0]
        assert held.meta["dispatch_failed"] is True and held.meta["handle"] is None

        unreadable = RecordStore(store.root / "unreadable", store._keystore)
        r2 = CapabilityRouter(registry, engine, unreadable)
        r2.register_backend(Silent("silent", ["ci.rerun_job"]))
        result = r2.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        held = [s.event for s in unreadable.scan(kinds=[EventKind.CLAIM_HELD])][0]
        assert held.meta["dispatch_failed"] is False
        assert held.meta["handle"] == result.handle.id

    def test_a_held_claim_is_resolved_with_its_token(self, registry, engine, store):
        class Pending(FakeBackend):
            def status(self, handle):
                return TaskStatus(handle=handle, state=TaskState.PENDING)

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Pending("queue", ["ci.rerun_job"]))
        result = router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        assert router.resolve(result.claim_token, ClaimOutcome.COMPLETED, "done") is True
        assert router.outstanding_claims() == []

    def test_a_superseded_token_cannot_resolve_a_newer_attempt(self, registry, engine, store):
        """The exact bug the token's generation exists to prevent."""
        class Failing(FakeBackend):
            def status(self, handle):
                return TaskStatus(handle=handle, state=TaskState.FAILED)

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Failing("flaky", ["ci.rerun_job"]))
        request = Request("ci.rerun_job", "j", {"job_id": "j"})
        first = router.invoke(request)     # released
        second = router.invoke(request)    # live retry, also released
        assert router.resolve(first.claim_token, ClaimOutcome.COMPLETED) is False
        assert first.claim_token.generation != second.claim_token.generation

    def test_resolve_refuses_a_nonsensical_outcome(self, router):
        result = router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        with pytest.raises(ValueError, match="cannot resolve"):
            router.resolve(result.claim_token, ClaimOutcome.HELD)

    def test_read_only_work_never_takes_a_claim(self, router):
        result = router.invoke(Request("ci.read_status", "repo"))
        assert result.claim is ClaimOutcome.NOT_APPLICABLE
        assert result.claim_token is None and result.idempotency_key is None

    @pytest.mark.parametrize(
        "actor,expected",
        [("user", Actor.USER), ("agent", Actor.AGENT), ("watcher:ci", Actor.WATCHER),
         ("subconscious", Actor.SUBCONSCIOUS), ("system", Actor.SYSTEM)],
    )
    def test_actors_are_not_all_attributed_to_the_human(self, router, store, actor, expected):
        """Attributing unattended work to the user is the one mistake an audit
        trail must never make."""
        router.invoke(Request("ci.read_status", "repo", actor=actor))
        invokes = [s.event for s in store.scan(kinds=[EventKind.CAPABILITY_INVOKE])]
        assert invokes[-1].actor is expected and invokes[-1].actor_id == actor

    def test_refusals_leave_a_trail(self, router, store: RecordStore):
        """A quarantined agent probing every capability must be visible."""
        for capability in ("ci.read_status", "ci.rerun_job", "message.send"):
            with pytest.raises(PolicyDenied):
                router.invoke(Request(capability, "t", quarantined=True))
        decisions = [s.event for s in store.scan(kinds=[EventKind.POLICY_DECISION])]
        assert len(decisions) == 3
        assert all(e.meta["quarantined"] is True for e in decisions)

    def test_machine_refusals_are_not_recorded_as_human_denials(self, router, store):
        """'The kill switch stopped it' must not read as 'you said no'."""
        with pytest.raises(PolicyDenied):
            router.invoke(Request("vehicle.drive", "car"))
        assert [s.event for s in store.scan(kinds=[EventKind.APPROVAL_DENY])] == []
        assert [s.event for s in store.scan(kinds=[EventKind.POLICY_DECISION])][-1] \
            .meta["outcome"] == "deny"

    def test_an_approval_gate_is_recorded_as_a_correlatable_request(self, router, store):
        with pytest.raises(ApprovalRequired) as caught:
            router.invoke(Request("message.send", "sam", {"to": "sam", "body": "hi"}))
        requests = [s.event for s in store.scan(kinds=[EventKind.APPROVAL_REQUEST])]
        assert len(requests) == 1 and requests[0].is_permanent
        assert requests[0].meta["approval_request_id"] == caught.value.request_id

    def test_unknown_capability_raises_the_documented_refusal_type(self, router):
        with pytest.raises(PolicyDenied, match="unknown capability"):
            router.invoke(Request("nope.invent", "t"))

    def test_a_mismatched_task_is_recorded_as_a_refusal(self, router, store: RecordStore):
        """Neither a dangling allow nor silence: a caller must not be able to
        suppress the trail of its own probing by attaching a bad task."""
        with pytest.raises(TaskMismatch):
            router.invoke(
                Request("ci.rerun_job", "j", {"job_id": "j"}),
                Task("ci.rerun_job", "j", {"job_id": "other"}),
            )
        decisions = [s.event for s in store.scan(kinds=[EventKind.POLICY_DECISION])]
        assert len(decisions) == 1 and decisions[0].meta["outcome"] == "deny"
        assert [s.event for s in store.scan(kinds=[EventKind.CAPABILITY_INVOKE])] == []

    def test_a_routing_failure_does_not_strand_the_claim(self, registry, engine, store):
        router = CapabilityRouter(registry, engine, store)
        request = Request("ci.rerun_job", "j", {"job_id": "j"})
        with pytest.raises(NoBackendAvailable):
            router.invoke(request)
        router.register_backend(FakeBackend("late", ["ci.rerun_job"]))
        assert router.invoke(request).handle is not None

    def test_an_unreadable_status_is_recorded_as_uncertain(self, registry, engine, store):
        class Silent(FakeBackend):
            def status(self, handle):
                raise RuntimeError("status endpoint down")

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Silent("silent", ["ci.rerun_job"]))
        router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        assert [s.event for s in store.scan(kinds=[EventKind.TOOL_RESULT])] == []
        errors = [s.event for s in store.scan(kinds=[EventKind.TOOL_ERROR])]
        assert len(errors) == 1 and errors[0].meta["effect_uncertain"] is True

    def test_a_failure_is_visible_in_the_audit_trail(self, registry, engine, store):
        from jarvis_core.record.projections import AuditProjection

        class Exploding(FakeBackend):
            def execute(self, task, idempotency_key=None):
                raise RuntimeError("boom")

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Exploding("flaky", ["ci.rerun_job"]))
        with pytest.raises(RuntimeError):
            router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        assert EventKind.TOOL_ERROR in [e.kind for e in AuditProjection(store).trail()]

    def test_a_failed_call_leaves_the_claim_held(self, registry, engine, store):
        """A stuck claim needs a human; a wrongly released one sends twice."""
        class Exploding(FakeBackend):
            def execute(self, task, idempotency_key=None):
                raise RuntimeError("boom")

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Exploding("flaky", ["ci.rerun_job"]))
        request = Request("ci.rerun_job", "j", {"job_id": "j"})
        with pytest.raises(RuntimeError):
            router.invoke(request)
        with pytest.raises(DuplicateSuppressed):
            router.invoke(request)


class TestScriptedWorkload:
    """Phase 0 exit criterion: a scripted workload routes end to end."""

    def test_fifty_tasks_route_and_remain_reconstructible(self, registry, engine, store):
        router = CapabilityRouter(registry, engine, store)
        router.register_backend(FakeBackend("primary", ["ci.read_status", "ci.rerun_job"]))

        for i in range(25):
            router.invoke(Request("ci.read_status", f"repo-{i}"))
            router.invoke(Request("ci.rerun_job", f"job-{i}", {"job_id": f"job-{i}"}))

        assert store.verify() == 150  # decision + invoke + result per task
        events = [s.event for s in store.scan(kinds=[EventKind.CAPABILITY_INVOKE])]
        assert len(events) == 50
        # Every action is reconstructible from the Record alone.
        assert all(e.meta["backend"] == "primary" and e.meta["policy"] for e in events)
        # ULIDs remained in write order despite the burst.
        assert [e.id for e in events] == sorted(e.id for e in events)
