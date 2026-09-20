"""The Record: append-only integrity, sealing, and crypto-shredding."""
import json
import os

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

    def test_reopening_continues_the_chain(self, store: RecordStore, keystore):
        store.append(evt(), b"first")
        reopened = RecordStore(store.root, keystore)
        reopened.append(evt(), b"second")
        assert reopened.verify() == 2
