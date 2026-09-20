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
    CapabilityRouter, DuplicateSuppressed, NoBackendAvailable, TaskMismatch,
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


@pytest.fixture
def router(registry, engine, store):
    r = CapabilityRouter(registry, engine, store)
    r.register_backend(FakeBackend("primary", ["ci.read_status", "ci.rerun_job", "message.send"]))
    return r


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
        assert store.verify() == 3

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

    def test_a_queued_task_is_not_recorded_as_done(self, registry, engine, store):
        """A pending effect that later fails must stay retryable."""
        class Queueing(FakeBackend):
            def status(self, handle):
                return TaskStatus(handle=handle, state=TaskState.PENDING)

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Queueing("queue", ["ci.rerun_job"]))
        result = router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        assert result.settled is False

    def test_a_failed_async_task_releases_the_claim_for_a_real_retry(self, registry, engine, store):
        class Failing(FakeBackend):
            def status(self, handle):
                return TaskStatus(handle=handle, state=TaskState.FAILED)

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Failing("flaky", ["ci.rerun_job"]))
        request = Request("ci.rerun_job", "j", {"job_id": "j"})
        assert router.invoke(request).settled is True
        assert router.invoke(request).handle is not None  # retry permitted

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
        assert invokes[-1].actor is expected
        assert invokes[-1].actor_id == actor

    def test_refusals_leave_a_trail(self, router, store: RecordStore):
        """A quarantined agent probing every capability must be visible."""
        for capability in ("ci.read_status", "ci.rerun_job", "message.send"):
            with pytest.raises(PolicyDenied):
                router.invoke(Request(capability, "t", quarantined=True))
        denials = [s.event for s in store.scan(kinds=[EventKind.APPROVAL_DENY])]
        assert len(denials) == 3
        assert all(e.meta["quarantined"] is True for e in denials)

    def test_an_approval_gate_is_recorded_as_a_request(self, router, store: RecordStore):
        with pytest.raises(ApprovalRequired):
            router.invoke(Request("message.send", "sam", {"to": "sam", "body": "hi"}))
        requests = [s.event for s in store.scan(kinds=[EventKind.APPROVAL_REQUEST])]
        assert len(requests) == 1 and requests[0].is_permanent

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
