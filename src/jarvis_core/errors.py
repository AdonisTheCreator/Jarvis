"""Core exception hierarchy.

Every error carries enough structure to be recorded in the Record without a
human having to parse a message string.
"""
from __future__ import annotations


class JarvisCoreError(Exception):
    """Base for everything raised by the core."""


class PolicyDenied(JarvisCoreError):
    """The Policy Engine refused an action.

    Raised *before* execution, never after. Carries the reason so the refusal is
    explainable from the audit projection alone.
    """

    def __init__(self, capability: str, reason: str, autonomy_class: str | None = None) -> None:
        self.capability = capability
        self.reason = reason
        self.autonomy_class = autonomy_class
        super().__init__(f"policy denied {capability}: {reason}")


class ApprovalRequired(JarvisCoreError):
    """The action is permitted but needs a scoped human approval first."""

    def __init__(self, capability: str, request_id: str) -> None:
        self.capability = capability
        self.request_id = request_id
        super().__init__(f"approval required for {capability} (request {request_id})")


class ApprovalInvalid(JarvisCoreError):
    """An approval token was presented but does not authorize this action.

    Covers: expired, already spent, wrong capability, or parameters that do not
    match the ones the human saw.
    """


class KillSwitchEngaged(JarvisCoreError):
    """All autonomous execution is halted. Nothing proceeds until released."""


class SubjectForgotten(JarvisCoreError):
    """The payload exists but its key was destroyed. This is a success, not a bug."""

    def __init__(self, subject: str) -> None:
        self.subject = subject
        super().__init__(f"subject {subject!r} was forgotten; payload is unrecoverable")


class RecordIntegrityError(JarvisCoreError):
    """The append-only log failed a hash or ordering check."""


class UnredactableSecret(JarvisCoreError):
    """A credential was found in a payload that cannot be rewritten in place.

    Refusing the write is the point. This module exists so a credential never
    enters the Record, and "the surrounding bytes were not text" is not a
    reason to make an exception -- the archive outlives every assumption about
    who will read it.
    """

    def __init__(self, labels: tuple[str, ...]) -> None:
        self.labels = labels
        super().__init__(
            f"payload is not UTF-8 and contains {list(labels)}; it cannot be "
            "redacted in place and will not be stored"
        )
