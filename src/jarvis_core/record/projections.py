"""The four read projections over the Record (docs/11 §1, D5).

One write path, four questions:

======================  ==================================================
Audit                   Why did you do that, under what authority?
Recall                  What happened, what did we decide, how do we do this?
Reconstruct             Put the world back the way it was at T.
Consolidate             What is worth keeping, and what did we learn?
======================  ==================================================

They are views, not stores. Building them separately would mean two write
paths over the same facts, which is how they diverge.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Iterator, Mapping, Protocol, Sequence

from ..errors import PolicyDenied
from .events import Event, EventKind
from .store import RecordStore

#: Everything the audit projection cares about: authority, and its exercise.
AUDIT_KINDS: frozenset[EventKind] = frozenset(
    {
        EventKind.CAPABILITY_INVOKE,
        EventKind.POLICY_DECISION,
        EventKind.POLICY_WRITE,
        EventKind.APPROVAL_REQUEST,
        EventKind.APPROVAL_GRANT,
        EventKind.APPROVAL_DENY,
        EventKind.MEMORY_FORGET,
        EventKind.SKILL_APPROVE,
        EventKind.KILLSWITCH,
        EventKind.CLAIM_OVERRIDE,
        EventKind.CLAIM_HELD,
        EventKind.CLAIM_RESOLVED,
        # A capability that was invoked and then failed is audit-relevant: the
        # trail must not show an invoke with no sign of what became of it.
        EventKind.TOOL_ERROR,
    }
)

#: Events that changed the world outside the Record.
MUTATION_KINDS: frozenset[EventKind] = frozenset(
    {
        EventKind.FILE_EDIT,
        EventKind.FILE_CREATE,
        EventKind.FILE_DELETE,
        EventKind.COMMAND_RUN,
        EventKind.CAPABILITY_INVOKE,
    }
)


class RecallScope(StrEnum):
    """How far a recall may reach (D6).

    Recall is a **capability with an autonomy class**, not an ambient ability.
    The Record is the highest-value exfiltration target in the system, so the
    default is narrow and archive-wide search is a separate, higher class.
    """

    NONE = "none"
    """What a quarantined agent gets. Not scoped recall -- none."""
    PROJECT = "project"
    RECENT = "recent"
    """Bounded by ``since_event``, which :meth:`RecallProjection.search`
    requires for this scope. Without a bound it would silently equal
    ``ARCHIVE`` -- a narrower-looking scope with none of the narrowing, which
    is worse than not offering it."""
    ARCHIVE = "archive"


class AuditProjection:
    """Reconstructs authority. Must keep working after a forget."""

    def __init__(self, store: RecordStore) -> None:
        self._store = store

    def trail(self, *, session: str | None = None) -> Iterator[Event]:
        for stored in self._store.scan():
            event = stored.event
            if event.kind in AUDIT_KINDS and (session is None or event.session == session):
                yield event

    def why(self, event_id: str) -> list[Event]:
        """Walk the causal DAG backwards from ``event_id`` to its roots.

        This is the query that makes "why did you do that" answerable -- and
        with parallel subagents it is a graph walk, never a scroll back.
        """
        by_id = {stored.event.id: stored.event for stored in self._store.scan()}
        chain: list[Event] = []
        seen: set[str] = set()
        frontier = [event_id]
        while frontier:
            current = frontier.pop()
            if current in seen or current not in by_id:
                continue
            seen.add(current)
            event = by_id[current]
            chain.append(event)
            frontier.extend(event.parent)
        return sorted(chain, key=lambda e: e.id)


@dataclass(frozen=True, slots=True)
class RecallHit:
    event: Event
    payload: bytes | None
    """``None`` when the subject was forgotten. The event still surfaces --
    *that* something happened is not secret, its content is."""


class RecallAuthority(Protocol):
    """Decides whether ``actor`` may recall at ``scope``.

    A protocol, not an import of the Policy Engine, so ``record/`` stays free
    of ``policy/`` and the Record remains usable on its own. The router passes
    the real one in.
    """

    def permits(self, actor: str, scope: RecallScope) -> bool: ...


@dataclass(frozen=True, slots=True)
class ScopeGrants:
    """Which scopes each actor may use. An actor not listed gets none.

    Deliberately a *set* per actor rather than a maximum scope: PROJECT and
    RECENT narrow along different axes -- one by subject, one by time -- so
    ranking them would mean inventing an order that is not true, and an
    invented order is how ARCHIVE ends up implied by something narrower.
    """

    grants: Mapping[str, frozenset[RecallScope]]

    def permits(self, actor: str, scope: RecallScope) -> bool:
        return scope in self.grants.get(actor, frozenset())


class RecallProjection:
    """Scoped query over the Record.

    The scope is *requested* by the caller and *granted* by the authority.
    It used to be a plain argument, which made the class docstring's claim --
    recall is a capability with an autonomy class, not an ambient ability --
    into a comment: any holder of a store could ask for ARCHIVE and get the
    whole archive. On the system's highest-value exfiltration target that is
    the one place the claim has to be executable.
    """

    def __init__(self, store: RecordStore, authority: RecallAuthority) -> None:
        self._store = store
        self._authority = authority

    def search(
        self,
        needle: str,
        *,
        scope: RecallScope,
        actor: str,
        project: str | None = None,
        since_event: str | None = None,
        limit: int = 20,
    ) -> list[RecallHit]:
        if scope is RecallScope.NONE:
            # A quarantined agent may already be under someone else's control.
            return []
        if not self._authority.permits(actor, scope):
            raise PolicyDenied(
                "record.recall", f"{actor!r} may not recall at scope {scope}"
            )
        if scope is RecallScope.RECENT and since_event is None:
            raise ValueError(
                "RecallScope.RECENT requires since_event; without a bound it "
                "would silently equal ARCHIVE"
            )
        if scope is RecallScope.PROJECT and project is None:
            raise ValueError("RecallScope.PROJECT requires a project")
        needle_bytes = needle.lower().encode()
        # Most recent wins. Breaking out at the first ``limit`` matches
        # returned the *oldest* hits, since the log scans forward -- so
        # "what did we decide about X" answered with the first time it ever
        # came up, and superseded answers outranked the current one. A bounded
        # deque keeps the cost of the full scan but not its memory.
        hits: deque[RecallHit] = deque(maxlen=limit)
        for stored in self._store.scan():
            event = stored.event
            if not self._in_scope(event, scope, project, since_event):
                continue
            payload = self._store.payload_or_none(event)
            if payload is not None and needle_bytes in payload.lower():
                hits.append(RecallHit(event=event, payload=payload))
        return list(hits)

    @staticmethod
    def _in_scope(
        event: Event, scope: RecallScope, project: str | None, since_event: str | None
    ) -> bool:
        if scope is RecallScope.ARCHIVE:
            return True
        if scope is RecallScope.PROJECT:
            return any(key == f"project:{project}" for key in event.subject_keys)
        # RECENT: ULIDs sort by creation time, so the bound is a comparison.
        # Exclusive, matching ConsolidateProjection.pending, so a checkpoint id
        # shared between them does not double-count the anchor event.
        return since_event is not None and event.id > since_event


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """State at a point in time, with an honest account of what can be undone.

    docs/11 §9: reconstruction is genuinely partial, and saying so prevents a
    false sense of undo. A good undo story is exactly what tempts you to
    loosen the approval gate.
    """

    at_event: str
    reversible: tuple[Event, ...] = ()
    """File edits, config, memory writes -- restorable."""
    compensatable: tuple[Event, ...] = ()
    """Sent messages, orders, commits -- undoable via a declared compensation."""
    irreversible: tuple[Event, ...] = ()
    """Anything a human read, money settled, a door that was opened."""

    @property
    def fully_reversible(self) -> bool:
        return not self.compensatable and not self.irreversible

    def summary(self) -> str:
        return (
            f"checkpoint @{self.at_event}: {len(self.reversible)} reversible, "
            f"{len(self.compensatable)} compensatable, "
            f"{len(self.irreversible)} irreversible"
        )


class ReconstructProjection:
    """Answers 'what did the world look like at T', and what can be put back."""

    def __init__(self, store: RecordStore) -> None:
        self._store = store

    def checkpoint(
        self,
        at_event: str,
        *,
        compensatable_capabilities: Sequence[str] = (),
    ) -> Checkpoint:
        """Classify everything that happened *after* ``at_event``.

        Never claims the world went back -- it reports the three buckets and
        lets the caller decide.
        """
        compensatable_set = set(compensatable_capabilities)
        reversible: list[Event] = []
        compensatable: list[Event] = []
        irreversible: list[Event] = []

        for stored in self._store.scan():
            event = stored.event
            if event.id <= at_event:  # ULIDs sort by time
                continue
            if event.kind not in MUTATION_KINDS:
                continue
            capability = str(event.meta.get("capability", ""))
            if event.kind in {EventKind.FILE_EDIT, EventKind.FILE_CREATE}:
                reversible.append(event)
            elif capability in compensatable_set:
                compensatable.append(event)
            elif event.meta.get("reversible") is True:
                reversible.append(event)
            else:
                irreversible.append(event)

        return Checkpoint(
            at_event=at_event,
            reversible=tuple(reversible),
            compensatable=tuple(compensatable),
            irreversible=tuple(irreversible),
        )


@dataclass(slots=True)
class ConsolidationBatch:
    """Work for the subconscious: idle-time, cheap model, narrow tools, no egress."""

    episodes: list[Event] = field(default_factory=list)
    traces: list[Event] = field(default_factory=list)
    media: list[Event] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.episodes) + len(self.traces) + len(self.media)


class ConsolidateProjection:
    """Selects what the subconscious should look at next."""

    def __init__(self, store: RecordStore) -> None:
        self._store = store

    def pending(self, *, since_event: str | None = None) -> ConsolidationBatch:
        batch = ConsolidationBatch()
        for stored in self._store.scan():
            event = stored.event
            if since_event is not None and event.id <= since_event:
                continue
            if event.kind in {EventKind.USER_TURN, EventKind.AGENT_TURN}:
                batch.episodes.append(event)
            elif event.kind in {EventKind.SUBAGENT_RESULT, EventKind.TOOL_RESULT}:
                batch.traces.append(event)
            elif event.is_media:
                batch.media.append(event)
        return batch

    def retention_candidates(self, *, older_than_event: str) -> list[Event]:
        """Media aged past the hot window, for day-30 adjudication (D9)."""
        return [
            stored.event
            for stored in self._store.scan()
            if stored.event.is_media and stored.event.id < older_than_event
        ]
