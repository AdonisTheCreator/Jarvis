"""Branches a mutation sweep found that no test was asserting (D20).

Every test here exists because `tools/mutation_sweep.py` broke the guard
above it and the suite still passed. They are boundaries, error paths and
classification arms -- unglamorous, and exactly where the last round of real
defects was hiding.

Run the sweep after adding a guard:

    python3 tools/mutation_sweep.py
"""
import time

import pytest

from jarvis_core.autonomy import AutonomyClass as A
from jarvis_core.backend import TaskState
from jarvis_core.capability import NO_UNDO, Capability
from jarvis_core.decide import CalibrationLog, DecisionSource
from jarvis_core.decide.types import DecisionPoint
from jarvis_core.errors import PolicyDenied
from jarvis_core.ids import new_ulid
from jarvis_core.memory import CanonicalMemory, MemoryClass, Provenance
from jarvis_core.policy import Outcome, Request
from jarvis_core.policy.approval import ApprovalToken
from jarvis_core.record import Actor, EventKind, RecordStore, make_event
from jarvis_core.record.crypto import Sealed
from jarvis_core.record.projections import (
    Checkpoint, ConsolidateProjection, ReconstructProjection,
)

from test_decide import StubDecider, registry_with


def evt(kind=EventKind.USER_TURN, **kw):
    kw.setdefault("actor", Actor.AGENT)
    kw.setdefault("session", "s1")
    kw.setdefault("subject_keys", ["project:jarvis"])
    return make_event(kind, **kw)


class TestCapabilityDeclarations:
    """`__post_init__` used to assign undo = None on the branch where undo was
    already falsy -- a guard that computed a condition and did nothing."""

    def test_an_irreversible_external_capability_must_declare_its_undo(self):
        for autonomy in (A.A2_EXTERNAL, A.A3_CONSEQUENTIAL, A.A4_BLOCKED):
            with pytest.raises(ValueError, match="declares no undo"):
                Capability("door.unlock", autonomy, reversible=False)

    def test_no_undo_is_an_answer_and_absence_is_not(self):
        stated = Capability("door.unlock", A.A3_CONSEQUENTIAL, reversible=False, undo=NO_UNDO)
        assert stated.undo == NO_UNDO
        named = Capability("msg.send", A.A2_EXTERNAL, reversible=False, undo="msg.retract")
        assert named.undo == "msg.retract"

    def test_the_rule_stops_below_A2_and_at_reversible(self):
        """Internal and reversible things are not where the question bites."""
        assert Capability("ci.rerun", A.A1_REVERSIBLE, reversible=False).undo is None
        assert Capability("msg.send", A.A2_EXTERNAL, reversible=True).undo is None


class TestTaskStateContract:
    def test_terminal_states_are_exactly_the_four(self):
        terminal = {state for state in TaskState if state.terminal}
        assert terminal == {
            TaskState.SUCCEEDED, TaskState.FAILED,
            TaskState.CANCELLED, TaskState.INTERRUPTED,
        }
        assert not any(s.terminal for s in (
            TaskState.PENDING, TaskState.RUNNING, TaskState.AWAITING_APPROVAL,
        ))

    def test_only_failure_promises_the_effect_did_not_happen(self):
        assert [s for s in TaskState if s.guarantees_no_effect] == [TaskState.FAILED]


class TestExpiryIsInclusive:
    """An approval expiring "at" T is spent at T, not one tick later. A
    boundary on an authorization is a boundary worth asserting."""

    def test_an_approval_is_expired_at_its_deadline(self):
        approval = ApprovalToken(
            "a", "message.send", "t", "h", expires_at=1000.0, signature="s"
        )
        assert approval.is_expired(now=1000.0) is True
        assert approval.is_expired(now=999.999) is False

    def test_a_protocol_is_expired_at_its_deadline(self, registry, approvals, protocols):
        from jarvis_core.policy import PolicyEngine
        from jarvis_core.policy.protocols import (
            AuthLevel, ConfirmMode, Protocol, ProtocolStep,
        )

        protocols.declare(Protocol(
            name="house-party", declared_by="user:harrison", reviewed_on="2026-09-20",
            steps=(ProtocolStep("door.unlock", {"door": "garage"}, target="garage"),),
            blast_radius="the garage door only",
            expires_at=1000.0, confirm=ConfirmMode.EXPLICIT,
            auth_required=AuthLevel.STRONG, undo=None,
        ))
        engine = PolicyEngine(registry, approvals, protocols)
        params = {"door": "garage"}

        def ask(now):
            return engine.evaluate(
                Request("door.unlock", "garage", params,
                        approval=approvals.issue("door.unlock", "garage", params),
                        protocol="house-party", auth_level=AuthLevel.STRONG),
                now=now,
            )

        assert ask(999.999).outcome is Outcome.ALLOW
        expired = ask(1000.0)
        assert expired.outcome is Outcome.DENY and "expire" in expired.reason


class TestConfidenceBoundaries:
    def test_confidence_exactly_at_the_bar_is_believed(self):
        """`<` not `<=`: a decider that meets the threshold has met it, and
        escalating it would quietly raise every bar in the catalog."""
        point = registry_with().get("test.point")
        at_bar = registry_with(StubDecider("cheap", point.min_confidence)).decide("test.point", {})
        assert at_bar.source is DecisionSource.MODEL
        under = registry_with(
            StubDecider("cheap", point.min_confidence - 1e-9)
        ).decide("test.point", {})
        assert under.source is DecisionSource.ESCALATED

    def test_a_point_cannot_demand_impossible_or_free_confidence(self):
        for bad in (0.0, 1.0000001, -0.5):
            with pytest.raises(ValueError, match="min_confidence"):
                DecisionPoint("p", ("a", "b"), "a", "b", min_confidence=bad)
        assert DecisionPoint("p", ("a", "b"), "a", "b", min_confidence=1.0).min_confidence == 1.0

    def test_calibration_verdict_boundaries(self):
        """Exactly at min_samples is enough data; exactly at max_ece passes."""
        log = CalibrationLog()
        for i in range(50):
            log.record("p", 0.9, correct=i < 45)
        report = log.report("p")
        assert report.n == 50
        assert report.verdict(min_samples=50) != "insufficient-data"
        assert report.verdict(min_samples=51) == "insufficient-data"
        assert report.verdict(max_ece=report.ece) == "ok"
        assert report.verdict(max_ece=report.ece - 1e-9) == "miscalibrated"


class TestSealedWireFormat:
    def test_a_payload_of_nonce_length_alone_is_too_short(self):
        """Nonce || ciphertext: exactly a nonce leaves no ciphertext, and an
        empty ciphertext would unseal to empty rather than raising."""
        from jarvis_core.record.crypto import NONCE_BYTES
        with pytest.raises(ValueError, match="too short"):
            Sealed.from_bytes("s", b"\x00" * NONCE_BYTES)
        assert Sealed.from_bytes("s", b"\x00" * (NONCE_BYTES + 1)).ciphertext == b"\x00"


class TestIdBoundaries:
    def test_a_negative_timestamp_is_refused(self):
        with pytest.raises(ValueError, match="must not be negative"):
            new_ulid(when_ms=-1)
        assert new_ulid(when_ms=0)

    def test_randomness_rollover_rolls_into_the_next_millisecond(self):
        """The 2^80 branch is unreachable in practice, which is exactly why it
        is never exercised -- and it is the one that keeps ordering total.

        Note what is *not* claimed: an explicit ``when_ms`` is honoured
        exactly, so two calls passing the same one are not ordered against
        each other. Only auto-generated timestamps never go backwards.
        """
        from jarvis_core import ids
        saved = (ids._last_ms, ids._last_rand)
        try:
            with ids._state_lock:
                ids._last_ms, ids._last_rand = 5_000, ids._MAX_RAND
            rolled = new_ulid(when_ms=5_000)
            assert ids.ulid_timestamp_ms(rolled) == 5_001    # not 5_000: it wrapped
            assert new_ulid(when_ms=5_001) > rolled          # and the counter resumed
        finally:
            with ids._state_lock:
                ids._last_ms, ids._last_rand = saved


class TestCheckpointClassification:
    """The three buckets drive what a human is told can be put back, so an
    event landing in the wrong one is a false undo story."""

    def test_a_declared_compensation_beats_the_reversible_flag(self, store: RecordStore):
        store.append(evt(EventKind.CAPABILITY_INVOKE, meta={
            "capability": "message.send", "reversible": False,
        }))
        check = ReconstructProjection(store).checkpoint(
            "0", compensatable_capabilities=["message.send"]
        )
        assert len(check.compensatable) == 1 and not check.irreversible

    def test_an_undeclared_capability_is_irreversible_not_compensatable(self, store):
        store.append(evt(EventKind.CAPABILITY_INVOKE, meta={
            "capability": "door.unlock", "reversible": False,
        }))
        check = ReconstructProjection(store).checkpoint(
            "0", compensatable_capabilities=["message.send"]
        )
        assert len(check.irreversible) == 1 and not check.compensatable

    def test_the_reversible_flag_must_be_true_not_merely_truthy(self, store: RecordStore):
        """`is True`, so a string "false" out of some adapter's JSON does not
        become a promise that the world can be put back."""
        store.append(evt(EventKind.COMMAND_RUN, meta={"capability": "sh", "reversible": "yes"}))
        assert len(ReconstructProjection(store).checkpoint("0").irreversible) == 1

    def test_events_at_the_mark_itself_are_excluded(self, store: RecordStore):
        """Inclusive here would replay the anchor event on every restore."""
        mark = store.append(evt(EventKind.FILE_EDIT, meta={"capability": "fs"}))
        after = store.append(evt(EventKind.FILE_EDIT, meta={"capability": "fs"}))
        check = ReconstructProjection(store).checkpoint(mark.event.id)
        assert [e.id for e in check.reversible] == [after.event.id]

    def test_full_reversibility_needs_both_other_buckets_empty(self):
        one = (make_event(EventKind.FILE_EDIT, actor=Actor.AGENT, session="s",
                          subject_keys=["project:jarvis"]),)
        assert Checkpoint("x", reversible=one).fully_reversible is True
        assert Checkpoint("x", compensatable=one).fully_reversible is False
        assert Checkpoint("x", irreversible=one).fully_reversible is False
        assert Checkpoint("x", compensatable=one, irreversible=one).fully_reversible is False


class TestConsolidationBounds:
    def test_the_checkpoint_event_is_not_reconsolidated(self, store: RecordStore):
        """Exclusive, matching RecallScope.RECENT, so an id shared between them
        does not double-count the anchor."""
        mark = store.append(evt(EventKind.USER_TURN), b"first")
        after = store.append(evt(EventKind.USER_TURN), b"second")
        batch = ConsolidateProjection(store).pending(since_event=mark.event.id)
        assert [e.id for e in batch.episodes] == [after.event.id]

    def test_retention_excludes_media_at_the_boundary_itself(self, store: RecordStore):
        older = store.append(evt(EventKind.SCREENSHOT), b"png")
        edge = store.append(evt(EventKind.SCREENSHOT), b"png2")
        candidates = ConsolidateProjection(store).retention_candidates(
            older_than_event=edge.event.id
        )
        assert [e.id for e in candidates] == [older.event.id]


class TestLeakDiagnosticHalves:
    """Both arms of leaks() survived the sweep: the test only checked that it
    was truthy before a forget and empty after, which either arm alone
    satisfies."""

    def _fact(self, memory, **prov):
        return memory.write(
            MemoryClass.USER_FACTS, f"k{new_ulid()}", "v",
            Provenance(**{"source_events": ("e1",), "subject_keys": ("person:guest",), **prov}),
        )

    def test_it_names_facts_about_the_subject(self):
        memory = CanonicalMemory()
        mine = self._fact(memory)
        self._fact(memory, subject_keys=("project:jarvis",))
        assert memory.leaks("person:guest") == [mine.id]

    def test_it_names_a_fact_whose_parent_was_erased(self):
        """The arm that catches a broken fan-out: the summary survives and
        still contains what its erased parent said."""
        memory = CanonicalMemory()
        parent = self._fact(memory)
        child = memory.write(
            MemoryClass.EPISODIC, "summary", "about the guest",
            Provenance(source_events=(), subject_keys=("project:jarvis",),
                       derived_from=(parent.id,)),
        )
        # While the parent is present nothing dangles: the child is reachable
        # from it, and a correct forget would take both.
        assert memory.leaks("person:guest") == [parent.id]
        del memory._facts[parent.id]          # a fan-out that stopped too early
        assert memory.leaks("person:guest") == [child.id]


class TestRouterInputGuards:
    def test_an_override_needs_a_real_subject_list(self, router):
        """Both arms: a bare string is a sequence of characters, and an empty
        list makes an event nobody can ever forget."""
        for bad in ("person:guest", (), []):
            with pytest.raises(ValueError, match="non-empty sequence"):
                router.force_release(
                    "somekey", operator="user:harrison", session="s1", subject_keys=bad,
                )

    def test_overriding_a_claim_that_is_not_held_reports_false(self, router):
        assert router.force_release(
            "never-claimed", operator="user:harrison", session="s1",
            subject_keys=["project:jarvis"],
        ) is False


class TestProtocolLookup:
    def test_an_unknown_protocol_covers_nothing(self, protocols):
        """Fail closed on a name that was never declared -- the arm a typo in
        a spoken Protocol name takes."""
        assert protocols.covers("no-such-protocol", "door.unlock", target="garage") is False
