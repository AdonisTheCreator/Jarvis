"""The Untrusted Ingest Rule (docs/05 §5.5, docs/02 §7).

    Any agent that reads untrusted content is quarantined: no private-data
    credentials, no outbound network except to the router, and its only
    permitted output is typed data -- a Proposal -- never a tool call and never
    an instruction.

This breaks the lethal trifecta *per task* rather than trying to make models
injection-resistant, which is not currently achievable. The point is
structural: a quarantined worker has nothing to exfiltrate with and no way to
act, so a successful injection produces a suspicious ``Proposal`` and nothing
else.

Proactive agents are the maximum-exposure case, because the ingest happens with
no human watching.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .ids import new_ulid


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """A pointer back to source content, never the content itself.

    Keeping evidence as *references* is what lets a human drill from any claim
    to the original text without the router having to swallow the untrusted
    bytes on the way.
    """

    event_id: str
    excerpt_hash: str
    location: str = ""


@dataclass(frozen=True, slots=True)
class Proposal:
    """The only thing a quarantined worker may emit.

    Note what is absent: no capability invocation, no tool name, no arguments,
    no instruction. ``suggested_capability`` is a *string the router may ignore*,
    not a call -- the router, which never ingested the untrusted bytes, decides
    what to do under policy.
    """

    id: str
    summary: str
    evidence: tuple[EvidenceRef, ...]
    suggested_capability: str | None = None
    confidence: float = 0.0
    source: str = "unknown"
    meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.summary.strip():
            raise ValueError("a proposal must say something")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


class QuarantinedWorker:
    """A worker that has touched untrusted content.

    It holds no credentials and exposes no way to act. The type system does
    the enforcing: there simply is no ``invoke`` on this object.
    """

    def __init__(self, source: str) -> None:
        self.source = source
        self._proposals: list[Proposal] = []

    def propose(
        self,
        summary: str,
        *,
        evidence: Sequence[EvidenceRef] = (),
        suggested_capability: str | None = None,
        confidence: float = 0.0,
        **meta: Any,
    ) -> Proposal:
        proposal = Proposal(
            id=new_ulid(),
            summary=summary,
            evidence=tuple(evidence),
            suggested_capability=suggested_capability,
            confidence=confidence,
            source=self.source,
            meta=meta,
        )
        self._proposals.append(proposal)
        return proposal

    def proposals(self) -> Sequence[Proposal]:
        return tuple(self._proposals)
