"""The Record: append-only integrity, sealing, and crypto-shredding."""
import json
import os
import threading

import pytest

from jarvis_core.errors import RecordIntegrityError, SubjectForgotten
from jarvis_core.ids import content_hash, new_ulid, ulid_timestamp_ms
from jarvis_core.record import Actor, EventKind, RecordStore, SubjectKeystore, make_event
from jarvis_core.record.events import PERMANENT_KINDS, PRUNABLE_KINDS, Event


def evt(**kw):
    kw.setdefault("actor", Actor.USER)
    kw.setdefault("session", "s1")
    kw.setdefault("subject_keys", ["project:jarvis"])
    return make_event(kw.pop("kind", EventKind.USER_TURN), **kw)


class TestIds:
    def test_ulid_is_time_ordered(self):
        assert new_ulid(1_000) < new_ulid(2_000) < new_ulid(3_000)

    def test_ulid_roundtrips_timestamp(self):
        assert ulid_timestamp_ms(new_ulid(1_700_000_000_123)) == 1_700_000_000_123

    def test_content_hash_is_stable_and_distinguishing(self):
        assert content_hash(b"a") == content_hash(b"a")
        assert content_hash(b"a") != content_hash(b"b")

    def test_ids_are_monotonic_within_a_single_millisecond(self):
        """Plain ULIDs only sort across milliseconds; a busy moment shuffles
        them, and the Record relies on id order being write order."""
        batch = [new_ulid(42_000) for _ in range(200)]
        assert batch == sorted(batch)
        assert len(set(batch)) == 200

    def test_ids_are_unique_under_concurrency(self):
        import threading

        produced: list[str] = []
        lock = threading.Lock()

        def work() -> None:
            ids = [new_ulid() for _ in range(300)]
            with lock:
                produced.extend(ids)

        threads = [threading.Thread(target=work) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(set(produced)) == 2400


class TestEventSchema:
    def test_subject_keys_are_mandatory(self):
        # An event with no subject could never be selectively forgotten.
        with pytest.raises(ValueError, match="subject_keys"):
            make_event(EventKind.USER_TURN, actor=Actor.USER, session="s", subject_keys=[])

    def test_a_bare_string_subject_is_rejected(self):
        """A string is iterable, so it would silently become a per-character
        subject tuple -- and could then never be forgotten by the name the
        caller meant."""
        with pytest.raises(TypeError, match="not the string"):
            make_event(EventKind.USER_TURN, actor=Actor.USER, session="s",
                       subject_keys="project:jarvis")
        # The constructor guards both sequence params, for callers that
        # bypass make_event.
        with pytest.raises(TypeError, match="not the string"):
            Event(id=new_ulid(), kind=EventKind.USER_TURN, actor=Actor.USER,
                  session="s", subject_keys="project:jarvis")
        with pytest.raises(TypeError, match="not the string"):
            Event(id=new_ulid(), kind=EventKind.USER_TURN, actor=Actor.USER,
                  session="s", subject_keys=("x",), parent="01ABCDEF")

    def test_a_bare_string_parent_is_rejected(self):
        """Same trap: a parent id split into characters would silently produce
        a DAG of nonexistent ancestors."""
        with pytest.raises(TypeError, match="not the string"):
            make_event(EventKind.USER_TURN, actor=Actor.USER, session="s",
                       subject_keys=["x"], parent="01ABCDEF")

    def test_event_cannot_be_its_own_parent(self):
        eid = new_ulid()
        with pytest.raises(ValueError, match="itself as a parent"):
            Event(id=eid, kind=EventKind.USER_TURN, actor=Actor.USER, session="s",
                  subject_keys=("x",), parent=(eid,))

    def test_roundtrip(self):
        original = evt(meta={"k": "v"})
        assert Event.from_dict(original.to_dict()) == original

    def test_permanent_kinds_cover_the_audit_trail(self):
        for kind in (EventKind.POLICY_DECISION, EventKind.APPROVAL_GRANT,
                     EventKind.MEMORY_FORGET, EventKind.KILLSWITCH):
            assert kind in PERMANENT_KINDS

    def test_every_kind_is_classified(self):
        """Adding a kind must force a retention choice.

        Matching on name prefixes only *looked* like coverage: EventKind.DECISION
        escaped it and sat in the prunable tier despite docs/11 §5 putting
        decisions in the permanent one. Every kind is now explicitly one or the
        other, and a new one belongs to neither until someone decides.
        """
        unclassified = set(EventKind) - PERMANENT_KINDS - PRUNABLE_KINDS
        assert not unclassified, (
            f"unclassified event kinds: {sorted(k.value for k in unclassified)} -- "
            "add each to PERMANENT_KINDS or PRUNABLE_KINDS"
        )

    def test_the_two_retention_tiers_do_not_overlap(self):
        assert not (PERMANENT_KINDS & PRUNABLE_KINDS)

    def test_every_audit_kind_is_permanent(self):
        """Otherwise the trail outlives its own evidence: a permanent
        claim.held whose parent invoke was pruned leaves why() unable to say
        under what authority the blocked action ran."""
        from jarvis_core.record.projections import AUDIT_KINDS

        prunable_audit = AUDIT_KINDS & PRUNABLE_KINDS
        assert not prunable_audit, (
            f"audit kinds in the prunable tier: "
            f"{sorted(k.value for k in prunable_audit)}"
        )

    def test_the_claim_story_is_permanent_end_to_end(self):
        """A blocked action, its resolution, and any manual override."""
        for kind in (EventKind.CLAIM_HELD, EventKind.CLAIM_RESOLVED,
                     EventKind.CLAIM_OVERRIDE, EventKind.DECISION):
            assert kind in PERMANENT_KINDS


class TestCryptoShredding:
    def test_seal_unseal_roundtrip(self, keystore: SubjectKeystore):
        sealed = keystore.seal("s", b"secret", aad=b"evt")
        assert keystore.unseal(sealed, aad=b"evt") == b"secret"

    def test_aad_binds_payload_to_its_event(self, keystore: SubjectKeystore):
        sealed = keystore.seal("s", b"secret", aad=b"evt-1")
        with pytest.raises(ValueError, match="authentication"):
            keystore.unseal(sealed, aad=b"evt-2")

    def test_forget_destroys_the_key(self, keystore: SubjectKeystore):
        sealed = keystore.seal("s", b"secret", aad=b"e")
        assert keystore.forget("s") is True
        with pytest.raises(SubjectForgotten):
            keystore.unseal(sealed, aad=b"e")

    def test_recreating_a_subject_does_not_resurrect_payloads(self, keystore):
        """The trap a derived-key design falls into: shredding must be final."""
        sealed = keystore.seal("s", b"secret", aad=b"e")
        keystore.forget("s")
        keystore.ensure_subject("s")  # new random key, not a re-derivation
        with pytest.raises(ValueError, match="authentication"):
            keystore.unseal(sealed, aad=b"e")


class TestRecordStore:
    def test_append_and_read_back(self, store: RecordStore):
        stored = store.append(evt(), b"hello")
        assert store.payload(stored.event) == b"hello"

    def test_chain_verifies(self, store: RecordStore):
        for _ in range(5):
            store.append(evt(), b"x")
        assert store.verify() == 5

    def test_tampering_breaks_the_chain(self, store: RecordStore):
        store.append(evt(), b"one")
        store.append(evt(), b"two")
        lines = store.log_path.read_text().splitlines()
        row = json.loads(lines[0])
        row["event"]["session"] = "tampered"
        store.log_path.write_text(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" + lines[1] + "\n"
        )
        with pytest.raises(RecordIntegrityError):
            store.verify()

    def test_forget_leaves_the_chain_intact(self, store: RecordStore):
        """Otherwise forgetting would be indistinguishable from tampering."""
        stored = store.append(evt(subject_keys=["person:guest"]), b"private")
        assert store.verify() == 1
        store.forget_subject("person:guest")
        assert store.verify() == 1
        assert store.payload_or_none(stored.event) is None
        with pytest.raises(SubjectForgotten):
            store.payload(stored.event)

    def test_secrets_are_redacted_on_the_way_in(self, store: RecordStore):
        stored = store.append(evt(), b"key=sk-ant-api03-aaaaaaaaaaaaaaaaaaaaaaaaaa")
        assert b"sk-ant" not in store.payload(stored.event)
        assert stored.event.meta["redacted"] == ["anthropic-key"]

    def test_identical_payloads_are_stored_once(self, store: RecordStore):
        a = store.append(evt(), b"same content")
        b = store.append(evt(), b"same content")
        assert a.event.payload_ref == b.event.payload_ref

    def test_causal_parents_are_preserved(self, store: RecordStore):
        root = store.append(evt())
        child = store.append(evt(parent=[root.event.id]))
        assert root.event.id in child.event.parent

    def test_scan_filters_by_kind(self, store: RecordStore):
        store.append(evt(kind=EventKind.USER_TURN))
        store.append(evt(kind=EventKind.POLICY_WRITE))
        kinds = [s.event.kind for s in store.scan(kinds=[EventKind.POLICY_WRITE])]
        assert kinds == [EventKind.POLICY_WRITE]

    def test_same_payload_under_two_subjects_stays_isolated(self, store: RecordStore):
        """Sharing a content-addressed blob across subjects would mean one
        subject's forget leaves another's copy readable. That is a leak, not a
        saving, so blobs are namespaced per subject."""
        mine = store.append(evt(subject_keys=["project:jarvis"]), b"identical text")
        theirs = store.append(evt(subject_keys=["person:guest"]), b"identical text")
        assert store.payload(mine.event) == store.payload(theirs.event) == b"identical text"

        store.forget_subject("person:guest")
        assert store.payload_or_none(theirs.event) is None
        assert store.payload(mine.event) == b"identical text"  # unaffected

    def test_writing_after_a_forget_neither_loses_nor_resurrects(self, store):
        """Both halves, which pull against each other:

        the new write must be readable (reusing a blob sealed under the
        destroyed key would be silent data loss), and the old event must stay
        forgotten (re-sealing a shared blob would un-forget it).
        """
        old = store.append(evt(subject_keys=["person:guest"]), b"same content")
        assert store.payload(old.event) == b"same content"
        store.forget_subject("person:guest")

        new = store.append(evt(subject_keys=["person:guest"]), b"same content")
        assert store.payload(new.event) == b"same content"      # not lost
        assert store.payload_or_none(old.event) is None         # not resurrected
        assert store.verify() == 2

    def test_the_epoch_survives_a_restart(self, store: RecordStore, keystore):
        """Held in process memory it reset, and the dedup then reused a blob
        sealed under the previous run's destroyed key."""
        store.append(evt(subject_keys=["person:guest"]), b"same content")
        store.forget_subject("person:guest")
        assert store.current_epoch("person:guest") == 2

        reopened = RecordStore(store.root, keystore)
        assert reopened.current_epoch("person:guest") == 2
        fresh = reopened.append(evt(subject_keys=["person:guest"]), b"same content")
        assert reopened.payload(fresh.event) == b"same content"

    def test_a_write_racing_a_forget_is_not_silently_lost(self, store: RecordStore):
        """The destroy and the bump have to be one atomic step. Between them
        the epoch reads stale, so an append lands in the *old* namespace,
        dedups onto a blob sealed under the key just destroyed, and a write
        that returned successfully reads back as forgotten."""
        old = store.append(evt(subject_keys=["person:guest"]), b"same content")

        destroying, appended = threading.Event(), threading.Event()
        destroy = store._keystore.forget

        def watched_forget(subject: str) -> bool:
            destroying.set()
            appended.wait(0.15)   # the appender must be held off, not raced
            return destroy(subject)

        store._keystore.forget = watched_forget
        forgetter = threading.Thread(
            target=store.forget_subject, args=("person:guest",), daemon=True
        )
        forgetter.start()
        assert destroying.wait(1.0)
        try:
            stored = store.append(evt(subject_keys=["person:guest"]), b"same content")
        finally:
            appended.set()
        forgetter.join(2.0)

        assert store.payload(stored.event) == b"same content"   # not lost
        assert store.payload_or_none(old.event) is None         # still forgotten
        assert store.verify() == 2

    def test_the_epoch_advances_before_the_key_is_destroyed(self, store: RecordStore):
        """Bumping second is unrepairable: the retried forget returns False
        because the key is already gone, so the epoch stays behind and the
        next identical write dedups onto a blob nobody can open again."""
        store.append(evt(subject_keys=["person:guest"]), b"same content")

        def unavailable(subject: str) -> bool:
            raise OSError("keyring unavailable")

        store._keystore.forget = unavailable
        with pytest.raises(OSError):
            store.forget_subject("person:guest")
        assert store.current_epoch("person:guest") == 2

        del store._keystore.forget          # the keyring comes back
        assert store.forget_subject("person:guest")
        stored = store.append(evt(subject_keys=["person:guest"]), b"same content")
        assert store.payload(stored.event) == b"same content"

    def test_an_unreadable_epoch_fails_closed(self, store: RecordStore):
        """Returning 1 for a corrupt EPOCH file collapses the namespace back
        onto e1/, which is exactly where the blobs of a destroyed key live.
        An *absent* file is a different fact and still means epoch 1."""
        assert store.current_epoch("person:guest") == 1     # nothing forgotten yet

        store.append(evt(subject_keys=["person:guest"]), b"private")
        store.forget_subject("person:guest")
        store._epoch_path("person:guest").write_text("e2", encoding="utf-8")

        with pytest.raises(RecordIntegrityError):
            store.current_epoch("person:guest")
        with pytest.raises(RecordIntegrityError):
            store.append(evt(subject_keys=["person:guest"]), b"private")

    def test_a_failed_seal_does_not_strand_the_epoch_lock(self, store: RecordStore):
        """acquire() sat above its try:, so a raise in between held the lock
        for the life of the process and every later append and forget hung."""
        def offline(*args, **kwargs):
            raise RuntimeError("HSM offline")

        store._keystore.seal = offline
        with pytest.raises(RuntimeError):
            store.append(evt(subject_keys=["person:guest"]), b"private")
        del store._keystore.seal

        recovered = threading.Event()

        def retry() -> None:
            store.append(evt(subject_keys=["person:guest"]), b"private")
            store.forget_subject("person:guest")
            recovered.set()

        thread = threading.Thread(target=retry, daemon=True)
        thread.start()
        assert recovered.wait(2.0), "the epoch lock was never released"

    def test_reading_never_resurrects_a_shredded_subject(self, store: RecordStore):
        """With a real keyring this would write a fresh key for a subject the
        user asked to erase."""
        stored = store.append(evt(subject_keys=["person:guest"]), b"private")
        store.forget_subject("person:guest")
        assert store._keystore.is_forgotten("person:guest")

        assert store.payload_or_none(stored.event) is None
        assert store._keystore.is_forgotten("person:guest")
        assert "person:guest" not in store._keystore.known_subjects()

    def test_payload_free_events_read_as_none(self, store: RecordStore):
        """Policy decisions, approvals and killswitch events carry none, and a
        projection must not raise on them."""
        stored = store.append(evt(kind=EventKind.POLICY_DECISION))
        assert stored.event.payload_ref is None
        assert store.payload_or_none(stored.event) is None

    def test_dedup_still_holds_within_one_key_epoch(self, store: RecordStore):
        a = store.append(evt(subject_keys=["project:jarvis"]), b"same content")
        b = store.append(evt(subject_keys=["project:jarvis"]), b"same content")
        assert a.event.payload_ref == b.event.payload_ref
        assert a.event.meta["payload_epoch"] == b.event.meta["payload_epoch"]

    def test_concurrent_writes_of_one_payload_all_land(self, store: RecordStore):
        """A shared temp path races: writers destroy each other's file and
        their events never reach the log."""
        payload = b"x" * 200_000
        errors: list[Exception] = []
        lock = threading.Lock()

        def write() -> None:
            try:
                store.append(evt(subject_keys=["project:jarvis"]), payload)
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=write) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors, errors
        assert store.verify() == 8
        assert all(store.payload(s.event) == payload for s in store.scan())

    def test_tampering_with_a_blob_is_not_mistaken_for_a_forget(self, store):
        """Reading a tampered payload as None would hide it, since verify()
        only covers the log, not the blobs."""
        stored = store.append(evt(subject_keys=["project:jarvis"]), b"private")
        path = store._blob_path(
            stored.event.payload_ref, "project:jarvis",
            int(stored.event.meta["payload_epoch"]),
        )
        raw = bytearray(path.read_bytes())
        raw[-1] ^= 0xFF
        path.write_bytes(bytes(raw))
        with pytest.raises(ValueError, match="authentication"):
            store.payload_or_none(stored.event)

    def test_reopening_continues_the_chain(self, store: RecordStore, keystore):
        store.append(evt(), b"first")
        reopened = RecordStore(store.root, keystore)
        reopened.append(evt(), b"second")
        assert reopened.verify() == 2
