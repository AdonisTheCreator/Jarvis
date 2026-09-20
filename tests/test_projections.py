"""The four read projections over one log."""
import pytest

from jarvis_core.record import Actor, EventKind, RecordStore, make_event
from jarvis_core.errors import PolicyDenied
from jarvis_core.record.projections import (
    AuditProjection, Checkpoint, ConsolidateProjection, RecallProjection,
    RecallScope, ReconstructProjection, ScopeGrants,
)


#: A test actor granted every scope, so tests about *searching* are not
#: also tests about authorization. The authorization tests name their own.
ANY_SCOPE = ScopeGrants({"user": frozenset(RecallScope)})


def recall(store, authority=ANY_SCOPE) -> RecallProjection:
    return RecallProjection(store, authority)


def add(store, kind, *, parent=(), subjects=("project:jarvis",), payload=None, meta=None):
    return store.append(
        make_event(kind, actor=Actor.AGENT, session="s1",
                   subject_keys=subjects, parent=parent, meta=meta or {}),
        payload,
    )


class TestAudit:
    def test_trail_contains_only_authority_events(self, store: RecordStore):
        add(store, EventKind.USER_TURN, payload=b"chat")
        add(store, EventKind.POLICY_DECISION, meta={"outcome": "allow"})
        add(store, EventKind.APPROVAL_GRANT)
        kinds = [e.kind for e in AuditProjection(store).trail()]
        assert EventKind.USER_TURN not in kinds
        assert EventKind.POLICY_DECISION in kinds and EventKind.APPROVAL_GRANT in kinds

    def test_why_walks_the_causal_dag_not_a_scrollback(self, store: RecordStore):
        root = add(store, EventKind.USER_TURN, payload=b"do the thing")
        branch_a = add(store, EventKind.SUBAGENT_SPAWN, parent=[root.event.id])
        branch_b = add(store, EventKind.SUBAGENT_SPAWN, parent=[root.event.id])
        merged = add(store, EventKind.CAPABILITY_INVOKE,
                     parent=[branch_a.event.id, branch_b.event.id])
        ids = {e.id for e in AuditProjection(store).why(merged.event.id)}
        assert ids == {root.event.id, branch_a.event.id, branch_b.event.id, merged.event.id}

    def test_audit_survives_a_forget(self, store: RecordStore):
        """Otherwise erasure would blind the safety layer."""
        add(store, EventKind.POLICY_DECISION, subjects=["person:guest"], payload=b"allowed")
        store.forget_subject("person:guest")
        assert len(list(AuditProjection(store).trail())) == 1


class TestRecall:
    def test_quarantined_scope_returns_nothing(self, store: RecordStore):
        add(store, EventKind.USER_TURN, payload=b"the auth decision")
        assert recall(store).search("auth", actor="user", scope=RecallScope.NONE) == []

    def test_project_scope_excludes_other_projects(self, store: RecordStore):
        add(store, EventKind.USER_TURN, subjects=["project:jarvis"], payload=b"auth decision")
        add(store, EventKind.USER_TURN, subjects=["project:other"], payload=b"auth decision")
        hits = recall(store).search(
            "auth", actor="user", scope=RecallScope.PROJECT, project="jarvis"
        )
        assert len(hits) == 1

    def test_archive_scope_reaches_everything(self, store: RecordStore):
        add(store, EventKind.USER_TURN, subjects=["project:jarvis"], payload=b"auth decision")
        add(store, EventKind.USER_TURN, subjects=["project:other"], payload=b"auth decision")
        assert len(recall(store).search("auth", actor="user", scope=RecallScope.ARCHIVE)) == 2

    def test_search_tolerates_payload_free_events(self, store: RecordStore):
        """Policy decisions carry no payload; search must not raise on them."""
        add(store, EventKind.POLICY_DECISION)
        add(store, EventKind.USER_TURN, payload=b"the auth decision")
        hits = recall(store).search("auth", actor="user", scope=RecallScope.ARCHIVE)
        assert len(hits) == 1

    def test_recent_requires_a_bound(self, store: RecordStore):
        """Unbounded, it would silently equal ARCHIVE -- a narrower-looking
        scope with none of the narrowing."""
        add(store, EventKind.USER_TURN, payload=b"auth decision")
        with pytest.raises(ValueError, match="requires since_event"):
            recall(store).search("auth", actor="user", scope=RecallScope.RECENT)

    def test_recent_excludes_events_before_the_bound(self, store: RecordStore):
        add(store, EventKind.USER_TURN, payload=b"old auth decision")
        mark = add(store, EventKind.SESSION_START)
        add(store, EventKind.USER_TURN, payload=b"new auth decision")
        hits = recall(store).search(
            "auth", actor="user", scope=RecallScope.RECENT, since_event=mark.event.id
        )
        assert len(hits) == 1
        assert hits[0].payload == b"new auth decision"

    def test_project_scope_requires_a_project(self, store: RecordStore):
        with pytest.raises(ValueError, match="requires a project"):
            recall(store).search("auth", actor="user", scope=RecallScope.PROJECT)

    def test_a_caller_cannot_grant_itself_archive_scope(self, store: RecordStore):
        """The scope used to be a plain argument, so the Record's own docstring
        -- recall is a capability, not an ambient ability -- was a comment."""
        add(store, EventKind.USER_TURN, payload=b"auth decision")
        narrow = ScopeGrants({"watcher": frozenset({RecallScope.PROJECT})})
        with pytest.raises(PolicyDenied, match="scope"):
            recall(store, narrow).search("auth", actor="watcher", scope=RecallScope.ARCHIVE)
        assert recall(store, narrow).search(
            "auth", actor="watcher", scope=RecallScope.PROJECT, project="jarvis"
        )

    def test_an_unknown_actor_gets_nothing(self, store: RecordStore):
        """Unlisted means none, so adding an actor is a deliberate act."""
        add(store, EventKind.USER_TURN, payload=b"auth decision")
        for scope in (RecallScope.PROJECT, RecallScope.RECENT, RecallScope.ARCHIVE):
            with pytest.raises(PolicyDenied):
                recall(store, ScopeGrants({})).search(
                    "auth", actor="stranger", scope=scope, project="jarvis",
                    since_event="0",
                )

    def test_a_grant_is_not_a_ranking(self, store: RecordStore):
        """PROJECT and RECENT narrow along different axes, so holding one must
        not imply the other -- that implication is how ARCHIVE leaks out of
        something that looked narrower."""
        add(store, EventKind.USER_TURN, payload=b"auth decision")
        recent_only = ScopeGrants({"w": frozenset({RecallScope.RECENT})})
        with pytest.raises(PolicyDenied):
            recall(store, recent_only).search(
                "auth", actor="w", scope=RecallScope.PROJECT, project="jarvis"
            )

    def test_the_limit_keeps_the_newest_hits_not_the_oldest(self, store: RecordStore):
        """Scanning forward and breaking at the limit answered "what did we
        decide about X" with the first time it ever came up, so a superseded
        answer outranked the current one."""
        for i in range(5):
            add(store, EventKind.USER_TURN, payload=f"auth decision {i}".encode())
        hits = recall(store).search(
            "auth", actor="user", scope=RecallScope.ARCHIVE, limit=2
        )
        assert [h.payload for h in hits] == [b"auth decision 3", b"auth decision 4"]

    def test_forgotten_content_is_not_searchable(self, store: RecordStore):
        add(store, EventKind.USER_TURN, subjects=["person:guest"], payload=b"a private thing")
        store.forget_subject("person:guest")
        assert recall(store).search("private", actor="user", scope=RecallScope.ARCHIVE) == []


class TestReconstruct:
    def test_checkpoint_separates_the_three_buckets(self, store: RecordStore):
        mark = add(store, EventKind.SESSION_START)
        add(store, EventKind.FILE_EDIT, meta={"path": "a.py"})
        add(store, EventKind.CAPABILITY_INVOKE, meta={"capability": "message.send"})
        add(store, EventKind.CAPABILITY_INVOKE, meta={"capability": "payment.send"})
        checkpoint = ReconstructProjection(store).checkpoint(
            mark.event.id, compensatable_capabilities=["message.send"]
        )
        assert len(checkpoint.reversible) == 1
        assert len(checkpoint.compensatable) == 1
        assert len(checkpoint.irreversible) == 1
        assert checkpoint.fully_reversible is False

    def test_a_clean_checkpoint_reports_full_reversibility(self, store: RecordStore):
        mark = add(store, EventKind.SESSION_START)
        add(store, EventKind.FILE_EDIT, meta={"path": "a.py"})
        assert ReconstructProjection(store).checkpoint(mark.event.id).fully_reversible is True

    def test_events_before_the_mark_are_ignored(self, store: RecordStore):
        add(store, EventKind.FILE_EDIT, meta={"path": "old.py"})
        mark = add(store, EventKind.SESSION_START)
        assert ReconstructProjection(store).checkpoint(mark.event.id).reversible == ()


class TestConsolidate:
    def test_batches_are_split_by_what_the_subconscious_does_with_them(self, store):
        add(store, EventKind.USER_TURN, payload=b"x")
        add(store, EventKind.TOOL_RESULT, payload=b"y")
        add(store, EventKind.SCREENSHOT, payload=b"z")
        batch = ConsolidateProjection(store).pending()
        assert (len(batch.episodes), len(batch.traces), len(batch.media)) == (1, 1, 1)
        assert batch.total == 3

    def test_retention_candidates_are_media_only(self, store: RecordStore):
        add(store, EventKind.SCREENSHOT, payload=b"old")
        add(store, EventKind.USER_TURN, payload=b"text")
        cutoff = add(store, EventKind.SESSION_END)
        candidates = ConsolidateProjection(store).retention_candidates(
            older_than_event=cutoff.event.id
        )
        assert [e.kind for e in candidates] == [EventKind.SCREENSHOT]
