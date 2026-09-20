"""Canonical memory: provenance, proposals, and an erasure that really erases."""
import pytest

from jarvis_core.memory import (
    CORE_OWNED, CanonicalMemory, MemoryClass, Proposal, Provenance,
)


def prov(**kw) -> Provenance:
    defaults = dict(source_events=("e1",), subject_keys=("person:guest",))
    return Provenance(**{**defaults, **kw})


class TestProvenance:
    def test_a_fact_with_no_origin_is_rejected(self):
        with pytest.raises(ValueError, match="at least one source event"):
            Provenance(source_events=(), subject_keys=("s",))

    def test_subject_keys_are_required_so_the_fact_can_be_forgotten(self):
        with pytest.raises(ValueError, match="subject_keys"):
            Provenance(source_events=("e",), subject_keys=())

    def test_confidence_is_bounded(self):
        with pytest.raises(ValueError, match="between 0 and 1"):
            Provenance(source_events=("e",), subject_keys=("s",), confidence=1.5)


class TestWriteAndSupersede:
    def test_write_then_read(self):
        memory = CanonicalMemory()
        memory.write(MemoryClass.USER_FACTS, "coffee", "oat flat white", prov())
        assert memory.get(MemoryClass.USER_FACTS, "coffee").value == "oat flat white"

    def test_a_newer_fact_supersedes_the_old_one(self):
        memory = CanonicalMemory()
        first = memory.write(MemoryClass.USER_FACTS, "coffee", "black", prov())
        second = memory.write(MemoryClass.USER_FACTS, "coffee", "oat flat white", prov())
        assert memory.get(MemoryClass.USER_FACTS, "coffee").id == second.id
        assert memory.history(MemoryClass.USER_FACTS, "coffee")[0].superseded_by == second.id
        assert first.id != second.id

    def test_history_is_kept_so_memory_stays_correctable(self):
        memory = CanonicalMemory()
        for value in ("a", "b", "c"):
            memory.write(MemoryClass.PROJECT, "stack", value, prov())
        assert [f.value for f in memory.history(MemoryClass.PROJECT, "stack")] == ["a", "b", "c"]

    def test_classes_are_independent(self):
        memory = CanonicalMemory()
        memory.write(MemoryClass.USER_FACTS, "k", "user value", prov())
        memory.write(MemoryClass.PROJECT, "k", "project value", prov())
        assert memory.get(MemoryClass.USER_FACTS, "k").value == "user value"
        assert memory.get(MemoryClass.PROJECT, "k").value == "project value"


class TestProposals:
    def test_runtimes_propose_rather_than_write(self):
        memory = CanonicalMemory()
        memory.propose(Proposal(MemoryClass.USER_FACTS, "k", "v", prov()))
        assert memory.get(MemoryClass.USER_FACTS, "k") is None
        assert len(memory.pending()) == 1

    def test_accepting_a_proposal_writes_it(self):
        memory = CanonicalMemory()
        memory.propose(Proposal(MemoryClass.USER_FACTS, "k", "v", prov()))
        memory.accept(0)
        assert memory.get(MemoryClass.USER_FACTS, "k").value == "v"
        assert memory.pending() == ()

    def test_rejecting_discards_it(self):
        memory = CanonicalMemory()
        memory.propose(Proposal(MemoryClass.USER_FACTS, "k", "v", prov()))
        memory.reject(0)
        assert memory.pending() == () and memory.get(MemoryClass.USER_FACTS, "k") is None

    def test_identity_memory_is_written_by_humans_only(self):
        memory = CanonicalMemory()
        with pytest.raises(ValueError, match="humans only"):
            memory.propose(Proposal(MemoryClass.IDENTITY, "persona", "…", prov()))


class TestOwnership:
    """docs/05 §4: procedural lives in SKILL.md files, operational in the
    control plane. A canonical copy here is a second source of truth, which is
    the drift Rule 2 exists to prevent."""

    def test_a_class_owned_elsewhere_cannot_be_written_as_canonical(self):
        memory = CanonicalMemory()
        for owned_elsewhere in set(MemoryClass) - CORE_OWNED:
            with pytest.raises(ValueError, match="owned outside the core"):
                memory.write(owned_elsewhere, "k", "v", prov())

    def test_it_can_be_indexed_and_says_so(self):
        memory = CanonicalMemory()
        fact = memory.write(
            MemoryClass.PROCEDURAL, "deploy", "skills/deploy.md", prov(), index=True
        )
        assert fact.indexed is True

    def test_a_core_owned_class_is_not_an_index(self):
        """Otherwise 'indexed' stops meaning anything and a reader can no
        longer tell a pointer from the truth."""
        memory = CanonicalMemory()
        assert memory.write(MemoryClass.USER_FACTS, "coffee", "black", prov()).indexed is False
        with pytest.raises(ValueError, match="core-owned"):
            memory.write(MemoryClass.USER_FACTS, "coffee", "black", prov(), index=True)

    def test_accepting_a_proposal_for_a_borrowed_class_indexes_it(self):
        """The SKILL.md draft path: agents draft procedural memory, so accept
        must not be the hole that writes it as canonical."""
        memory = CanonicalMemory()
        memory.propose(Proposal(MemoryClass.PROCEDURAL, "deploy", "skills/deploy.md", prov()))
        assert memory.accept(0).indexed is True


class TestForgetFanOut:
    def _layered(self) -> tuple[CanonicalMemory, list[str]]:
        memory = CanonicalMemory()
        raw = memory.write(MemoryClass.EPISODIC, "visit", "guest came by", prov())
        summary = memory.write(
            MemoryClass.USER_FACTS, "guests", "a guest visited",
            prov(source_events=(), subject_keys=("system",), derived_from=(raw.id,)),
        )
        rollup = memory.write(
            MemoryClass.PROJECT, "social", "summary of summaries",
            prov(source_events=(), subject_keys=("system",), derived_from=(summary.id,)),
        )
        return memory, [raw.id, summary.id, rollup.id]

    def test_forget_reaches_transitively_derived_facts(self):
        """A summary of a summary still holds the content it came from."""
        memory, ids = self._layered()
        report = memory.forget("person:guest")
        assert report.directly_removed == (ids[0],)
        assert set(report.derived_removed) == {ids[1], ids[2]}
        assert report.total == 3
        assert list(memory.all_facts()) == []

    def test_unrelated_facts_survive(self):
        memory, _ = self._layered()
        keeper = memory.write(
            MemoryClass.PROJECT, "unrelated", "kept",
            prov(source_events=("e9",), subject_keys=("project:jarvis",)),
        )
        memory.forget("person:guest")
        assert [f.id for f in memory.all_facts()] == [keeper.id]

    def test_leaks_is_empty_after_a_correct_forget(self):
        memory, _ = self._layered()
        assert memory.leaks("person:guest")
        memory.forget("person:guest")
        assert memory.leaks("person:guest") == []

    def test_forgetting_an_unknown_subject_is_a_no_op(self):
        memory, _ = self._layered()
        assert memory.forget("person:nobody").total == 0
