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


class TestCanonicalisationIsOrderFree:
    """`sort_keys=True` in two json.dumps calls. CPython preserves insertion
    order, so a test that builds both dicts the same way passes either way --
    and the property is exactly that it must not matter."""

    def test_an_idempotency_key_ignores_parameter_order(self):
        """Keys hash the *action*. A retry that rebuilt its params dict in a
        different order would hash differently and send the message twice."""
        from jarvis_core.idempotency import derive_key

        fields = ("to", "body")
        first = derive_key("message.send", "sms", {"to": "+1", "body": "hi"}, fields)
        second = derive_key("message.send", "sms", {"body": "hi", "to": "+1"}, fields)
        assert first == second

    def test_an_approval_fingerprint_ignores_parameter_order(self):
        """The fingerprint is what binds an approval to the parameters a human
        saw. Order-sensitive, it would reject the very call it authorized."""
        from jarvis_core.policy.approval import params_fingerprint

        assert params_fingerprint({"door": "front", "minutes": 5}) == \
            params_fingerprint({"minutes": 5, "door": "front"})


class TestEntropyRedaction:
    """The heuristic's *positive* case: without it, a novel credential format
    the patterns do not know goes into the archive in the clear."""

    def test_a_long_high_entropy_token_is_removed(self):
        from jarvis_core.record.redact import redact

        secret = "Zx9Qw2Lm4Pv7Rt1Ys6Bn3Kd8Hg5Jf0Ac"     # 32 chars, no known prefix
        report = redact(f"export CUSTOM_CREDENTIAL={secret}")
        assert "high-entropy" in report.labels and secret not in report.text

    def test_a_low_entropy_string_of_the_same_length_survives(self):
        from jarvis_core.record.redact import redact

        assert redact("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa").labels == ()

    def test_the_scan_can_be_turned_off(self):
        from jarvis_core.record.redact import redact

        secret = "Zx9Qw2Lm4Pv7Rt1Ys6Bn3Kd8Hg5Jf0Ac"
        assert redact(secret, entropy_scan=False).labels == ()

    def test_text_payloads_report_that_they_were_scanned(self):
        from jarvis_core.record.redact import redact_bytes

        _, report = redact_bytes(b"nothing secret here")
        assert report.scanned is True

    def test_binary_payloads_are_pattern_scanned_not_entropy_scanned(self):
        """A lossy decode of a compressed file is high-entropy gibberish. If
        the binary path entropy-scanned, every screenshot with a long base64
        run inside it would be refused as a credential."""
        from jarvis_core.record.redact import redact_bytes

        blob = b"\xff\xd8\xff\xe0" + b"Zx9Qw2Lm4Pv7Rt1Ys6Bn3Kd8Hg5Jf0Ac" + b"\x89\x00\xfe"
        payload, report = redact_bytes(blob)
        assert payload == blob and report.labels == () and report.scanned is False


class TestMemoryReads:
    def _memory(self):
        memory = CanonicalMemory()
        prov = Provenance(source_events=("e1",), subject_keys=("project:jarvis",))
        first = memory.write(MemoryClass.USER_FACTS, "coffee", "black", prov)
        second = memory.write(MemoryClass.USER_FACTS, "coffee", "oat", prov)
        other = memory.write(MemoryClass.PROJECT, "coffee", "unrelated", prov)
        return memory, first, second, other

    def test_history_is_scoped_to_one_class_and_one_key(self):
        """Same key under a different class is a different fact, and mixing
        them makes the correction history of one look like the other's."""
        memory, first, second, other = self._memory()
        assert [f.id for f in memory.history(MemoryClass.USER_FACTS, "coffee")] == \
            [first.id, second.id]
        assert other.id not in {f.id for f in memory.history(MemoryClass.USER_FACTS, "coffee")}

    def test_superseded_facts_are_hidden_by_default_and_available_on_request(self):
        memory, first, second, other = self._memory()
        assert first.id not in {f.id for f in memory.all_facts()}
        assert first.id in {f.id for f in memory.all_facts(active_only=False)}


class TestRecallBound:
    def test_the_since_event_itself_is_excluded(self, store: RecordStore):
        """Exclusive, matching ConsolidateProjection.pending, so an id shared
        between them does not double-count the anchor."""
        from jarvis_core.record.projections import RecallScope, ScopeGrants
        from jarvis_core.record.projections import RecallProjection

        mark = store.append(evt(), b"auth at the mark")
        after = store.append(evt(), b"auth after it")
        hits = RecallProjection(
            store, ScopeGrants({"user": frozenset(RecallScope)})
        ).search("auth", actor="user", scope=RecallScope.RECENT, since_event=mark.event.id)
        assert [h.event.id for h in hits] == [after.event.id]


class TestPayloadSubject:
    def test_a_payload_about_someone_else_is_sealed_under_their_key(self, store):
        """An event in the project's stream whose *content* is about a person:
        forgetting the person must take the payload, not the event."""
        stored = store.append(
            evt(subject_keys=["project:jarvis", "person:guest"]),
            b"what the guest said",
            payload_subject="person:guest",
        )
        assert stored.event.meta["payload_subject"] == "person:guest"
        assert store.payload(stored.event) == b"what the guest said"
        store.forget_subject("person:guest")
        assert store.payload_or_none(stored.event) is None
        assert store.verify() == 1          # the event itself survives

    def test_the_default_subject_is_not_annotated(self, store: RecordStore):
        """Only a divergence is worth recording; annotating every event with
        what the first subject key already says is noise in the archive."""
        stored = store.append(evt(subject_keys=["project:jarvis"]), b"ordinary")
        assert "payload_subject" not in stored.event.meta


class TestOverrideRace:
    def test_a_claim_released_between_the_peek_and_the_release_reports_false(self, router):
        """Two operators overriding the same stranded claim: only one release
        actually happens, and the loser must not record an override it did not
        perform."""
        key = "contended-key"
        claim = router._idempotency.claim(key)
        assert router._idempotency.release(claim.token) is True   # the winner

        peeked = router._idempotency.peek(key)
        assert peeked is None
        assert router.force_release(
            key, operator="user:harrison", session="s1", subject_keys=["project:jarvis"],
        ) is False


class TestZeroIsAValidConfidence:
    """`0.0 <= x` with the bound flipped to `<` rejected exactly zero. A
    decider that is certain of nothing reports 0.0, and so does every
    fallback, so zero is the most common value there is."""

    def test_provenance_accepts_it(self):
        assert Provenance(
            source_events=("e1",), subject_keys=("s",), confidence=0.0
        ).confidence == 0.0

    def test_a_calibration_observation_accepts_it(self):
        log = CalibrationLog()
        log.record("p", 0.0, correct=False)
        assert log.report("p").n == 1

    def test_a_quarantined_proposal_accepts_it(self):
        from jarvis_core.quarantine import QuarantinedWorker

        assert QuarantinedWorker("email").propose("something odd").confidence == 0.0


class TestVerdictProperties:
    def test_is_confident_means_the_model_answered(self):
        from jarvis_core.decide.types import DecisionResult

        for source in DecisionSource:
            result = DecisionResult("p", "a", 0.9, source)
            assert result.is_confident is (source is DecisionSource.MODEL)

    def test_allowed_means_allow_and_nothing_else(self, engine, registry, approvals):
        """REQUIRE_APPROVAL is not permission. It is the opposite: the thing
        that has to happen before there is any."""
        from jarvis_core.policy import Decision, Outcome

        for outcome in Outcome:
            decision = Decision(outcome=outcome, reason="r", capability="ci.rerun_job")
            assert decision.allowed is (outcome is Outcome.ALLOW)


class TestHaltReasonReachesTheHuman:
    def test_the_operators_words_are_in_the_denial(self, registry, approvals, protocols, tmp_path):
        """"kill switch engaged" tells you nothing you did not know. The
        sentinel's text is the only thing that says *why* everything stopped."""
        from jarvis_core.killswitch import FileKillSwitch
        from jarvis_core.policy import PolicyEngine

        sentinel = tmp_path / "HALT"
        sentinel.write_text("gas leak; everything off until I say")
        engine = PolicyEngine(registry, approvals, protocols, FileKillSwitch(sentinel))
        reason = engine.evaluate(Request("ci.rerun_job", "j")).reason
        assert "gas leak" in reason

    def test_a_reasonless_halt_still_says_something(self, registry, approvals, protocols, tmp_path):
        from jarvis_core.killswitch import FileKillSwitch
        from jarvis_core.policy import PolicyEngine

        sentinel = tmp_path / "HALT"
        sentinel.write_text("")
        engine = PolicyEngine(registry, approvals, protocols, FileKillSwitch(sentinel))
        assert "engaged" in engine.evaluate(Request("ci.rerun_job", "j")).reason


class TestStoredPayloadsAreRedactedByDefault:
    def test_a_novel_credential_format_does_not_reach_the_archive(self, store: RecordStore):
        """`redact_bytes(payload)` is called with no arguments, so the entropy
        scan's default is what protects every stored payload. Testing redact()
        directly leaves that default unasserted."""
        secret = "Zx9Qw2Lm4Pv7Rt1Ys6Bn3Kd8Hg5Jf0Ac"
        stored = store.append(evt(), f"device handle {secret} is live".encode())
        assert secret.encode() not in store.payload(stored.event)
        assert "high-entropy" in stored.event.meta["redacted"]


class TestForgetFanOutRevisiting:
    def test_a_chain_entirely_about_the_subject_is_not_double_counted(self):
        """Both facts are direct *and* one derives from the other. The skip in
        the traversal has to consider both sets, or a directly-removed fact is
        also reported as derived."""
        memory = CanonicalMemory()
        prov = Provenance(source_events=("e1",), subject_keys=("person:guest",))
        parent = memory.write(MemoryClass.USER_FACTS, "a", 1, prov)
        child = memory.write(
            MemoryClass.EPISODIC, "b", 2,
            Provenance(source_events=("e1",), subject_keys=("person:guest",),
                       derived_from=(parent.id,)),
        )
        report = memory.forget("person:guest")
        assert set(report.directly_removed) == {parent.id, child.id}
        assert report.derived_removed == ()
        assert report.total == 2          # not 3


class TestRecordWriteFailures:
    def test_a_record_that_refuses_the_invoke_event_frees_the_claim(
        self, registry, engine, store
    ):
        """Nothing has executed yet, so the claim is definitively free --
        leaving it held would block the retry that would have worked."""
        from test_router import CapabilityRouter, FakeBackend

        class Refusing:
            def __init__(self, real): self._real = real
            def __getattr__(self, name): return getattr(self._real, name)
            def append(self, *a, **kw): raise OSError("disk full")

        router = CapabilityRouter(registry, engine, Refusing(store))
        router.register_backend(FakeBackend("primary", ["ci.rerun_job"]))
        with pytest.raises(OSError):
            router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}))
        assert router._idempotency.in_flight() == []

    def test_a_failed_read_does_not_touch_the_ledger(self, registry, engine, store):
        """A read takes no claim, so the failure path must not try to release
        one -- there is nothing there to release."""
        from test_router import CapabilityRouter

        class Refusing:
            def __init__(self, real): self._real = real
            def __getattr__(self, name): return getattr(self._real, name)
            def append(self, *a, **kw): raise OSError("disk full")

        from test_router import FakeBackend
        router = CapabilityRouter(registry, engine, Refusing(store))
        router.register_backend(FakeBackend("primary", ["ci.read_status"]))
        with pytest.raises(OSError):        # the original error, not an AttributeError
            router.invoke(Request("ci.read_status", "repo"))
        assert router._idempotency.in_flight() == []


class TestEventsLandUnderTheRightSubject:
    def test_a_failure_event_carries_the_task_subjects_not_a_placeholder(
        self, registry, engine, store
    ):
        """An event filed under "system" can never be reached by the forget of
        the person it is actually about.

        Scoped to the events the router builds *from a task*. The policy
        decision is deliberately not one of them: it is written before a task
        exists, from a Request that has no subjects, and it is a permanent
        audit kind that is meant to outlive the forget anyway.
        """
        from jarvis_core.backend import Task
        from test_router import CapabilityRouter, FakeBackend

        class Exploding(FakeBackend):
            def execute(self, task, idempotency_key=None):
                raise RuntimeError("boom")

        router = CapabilityRouter(registry, engine, store)
        router.register_backend(Exploding("flaky", ["ci.rerun_job"]))
        task = Task("ci.rerun_job", "j", {"job_id": "j"}, subject_keys=("person:guest",))
        with pytest.raises(RuntimeError):
            router.invoke(Request("ci.rerun_job", "j", {"job_id": "j"}), task)
        from_task = [s.event for s in store.scan() if s.event.kind in (
            EventKind.CAPABILITY_INVOKE, EventKind.TOOL_ERROR, EventKind.CLAIM_HELD,
        )]
        assert from_task, "the failure path recorded nothing"
        for event in from_task:
            assert event.subject_keys == ("person:guest",), event.kind
