"""The Record's event schema (docs/11 §3, D5).

One append-only, content-addressed log with four read projections: Audit,
Recall, Reconstruct, Consolidate. This module defines the thing that is
written; ``store`` defines how, ``crypto`` defines the confidentiality.

Two fields carry most of the design weight:

``parent``
    A causal **DAG**, not a previous-pointer. With subagents running in
    parallel a linear transcript is a fiction, and "why did this happen" is
    only answerable from the graph.

``subject_keys``
    Who or what this event is *about*. This is what makes ``forget()``
    possible at all (docs/11 §6), which is why it cannot be added later:
    an event written without it can never be selectively forgotten.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Mapping, Sequence

from ..ids import new_ulid, ulid_timestamp_ms


class EventKind(StrEnum):
    """Everything the Record can hold. Grouped as in docs/11 §3."""

    # Conversation
    USER_TURN = "user.turn"
    AGENT_TURN = "agent.turn"
    AGENT_REASONING = "agent.reasoning"
    AGENT_ACK = "agent.ack"
    # Delegation
    SUBAGENT_SPAWN = "subagent.spawn"
    SUBAGENT_RESULT = "subagent.result"
    SUBAGENT_ERROR = "subagent.error"
    # Tool use
    TOOL_CALL = "tool.call"
    TOOL_RESULT = "tool.result"
    TOOL_ERROR = "tool.error"
    # Mutation
    FILE_READ = "file.read"
    FILE_EDIT = "file.edit"
    FILE_CREATE = "file.create"
    FILE_DELETE = "file.delete"
    COMMAND_RUN = "command.run"
    # Capability and policy
    CAPABILITY_INVOKE = "capability.invoke"
    POLICY_DECISION = "policy.decision"
    APPROVAL_REQUEST = "approval.request"
    APPROVAL_GRANT = "approval.grant"
    APPROVAL_DENY = "approval.deny"
    POLICY_WRITE = "policy.write"  # D17: spoken routing policy
    # Proactivity
    WATCH_FIRE = "watch.fire"
    SALIENCE_SCORE = "salience.score"
    DELIVERY = "delivery"
    DELIVERY_OUTCOME = "delivery.outcome"
    # Decisions (docs/20)
    DECISION = "decision"  # a DecisionPoint result + its calibration record
    # Memory
    MEMORY_PROPOSE = "memory.propose"
    MEMORY_WRITE = "memory.write"
    MEMORY_FORGET = "memory.forget"
    SKILL_DRAFT = "skill.draft"
    SKILL_APPROVE = "skill.approve"
    # Media
    AUDIO_SEGMENT = "audio.segment"
    SCREENSHOT = "screenshot"
    POV_CAPTURE = "pov.capture"
    # System
    SESSION_START = "session.start"
    SESSION_END = "session.end"
    ERROR = "error"
    KILLSWITCH = "killswitch"
    HEALTH = "health"


class Actor(StrEnum):
    """Who caused the event. Coarse on purpose; the detail is in ``actor_id``."""

    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    WATCHER = "watcher"
    SUBCONSCIOUS = "subconscious"


#: Events the audit projection must never lose, whatever retention says
#: (docs/11 §5 "permanent" tier).
PERMANENT_KINDS: frozenset[EventKind] = frozenset(
    {
        EventKind.POLICY_DECISION,
        EventKind.APPROVAL_REQUEST,
        EventKind.APPROVAL_GRANT,
        EventKind.APPROVAL_DENY,
        EventKind.POLICY_WRITE,
        EventKind.MEMORY_WRITE,
        EventKind.MEMORY_FORGET,
        EventKind.SKILL_APPROVE,
        EventKind.KILLSWITCH,
    }
)

#: Kinds whose payloads are large binaries -- the retention adjudicator's
#: primary targets (D9, docs/14 §3).
MEDIA_KINDS: frozenset[EventKind] = frozenset(
    {EventKind.SCREENSHOT, EventKind.POV_CAPTURE, EventKind.AUDIO_SEGMENT}
)


@dataclass(frozen=True, slots=True)
class Event:
    """One immutable entry in the Record.

    ``payload_ref`` is a content address, never inline content: payloads are
    sealed separately so that forgetting a subject does not require rewriting
    the log.
    """

    id: str
    kind: EventKind
    actor: Actor
    session: str
    subject_keys: tuple[str, ...]
    parent: tuple[str, ...] = ()
    actor_id: str | None = None
    payload_ref: str | None = None
    meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.subject_keys:
            # Not a style rule: an event with no subject can never be forgotten.
            raise ValueError(
                f"event {self.id} has no subject_keys; it could never be forgotten "
                "(docs/11 §6). Use 'system' for genuinely subject-less events."
            )
        if self.id in self.parent:
            raise ValueError(f"event {self.id} lists itself as a parent")

    @property
    def timestamp_ms(self) -> int:
        """Creation time, recovered from the ULID rather than stored twice."""
        return ulid_timestamp_ms(self.id)

    @property
    def is_permanent(self) -> bool:
        return self.kind in PERMANENT_KINDS

    @property
    def is_media(self) -> bool:
        return self.kind in MEDIA_KINDS

    def payload_aad(self, subject: str) -> bytes:
        """Additional authenticated data for this event's sealed payload.

        Binds the ciphertext to **(subject, content ref)** rather than to the
        event id, which is a deliberate layering choice:

        * the **hash chain** already binds *event -> payload_ref*, so pointing
          an event at a different blob breaks verification;
        * the **AAD** binds *payload_ref -> subject*, so one subject's blob can
          never be unsealed as another's.

        Binding the AAD to the event id instead would make content addressing
        useless (identical payloads would seal differently per event) and --
        worse -- a blob shared between two subjects would survive one of them
        being forgotten. Subject-scoped sealing closes that hole.
        """
        if self.payload_ref is None:
            raise ValueError(f"event {self.id} has no payload to bind")
        return f"{subject}|{self.payload_ref}".encode()

    def with_payload(self, payload_ref: str) -> Event:
        """Return a copy carrying ``payload_ref``. Used before sealing."""
        return replace(self, payload_ref=payload_ref)

    # -- serialisation ---------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "actor": self.actor.value,
            "actor_id": self.actor_id,
            "session": self.session,
            "subject_keys": list(self.subject_keys),
            "parent": list(self.parent),
            "payload_ref": self.payload_ref,
            "meta": dict(self.meta),
        }

    def to_json(self) -> str:
        """Canonical JSON: sorted keys, compact, so hashing is stable."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Event:
        return cls(
            id=str(data["id"]),
            kind=EventKind(data["kind"]),
            actor=Actor(data["actor"]),
            actor_id=data.get("actor_id"),
            session=str(data["session"]),
            subject_keys=tuple(data.get("subject_keys") or ()),
            parent=tuple(data.get("parent") or ()),
            payload_ref=data.get("payload_ref"),
            meta=dict(data.get("meta") or {}),
        )


def make_event(
    kind: EventKind,
    *,
    actor: Actor,
    session: str,
    subject_keys: Sequence[str],
    parent: Sequence[str] = (),
    actor_id: str | None = None,
    meta: Mapping[str, Any] | None = None,
    when_ms: int | None = None,
) -> Event:
    """Build an event with a fresh id. ``when_ms`` is injectable for tests."""
    return Event(
        id=new_ulid(when_ms),
        kind=kind,
        actor=actor,
        actor_id=actor_id,
        session=session,
        subject_keys=tuple(subject_keys),
        parent=tuple(parent),
        meta=dict(meta or {}),
    )
