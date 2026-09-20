"""Write-time secret redaction (docs/11 §8).

A credential that never enters the Record cannot leak from it. Redaction
happens on the way *in*, not on the way out, because the archive outlives every
assumption about who will read it.

This is deliberately a **rule, not a decision** (docs/20, rejected list): a
probabilistic miss here leaks a credential, so it must be exact, cheap and
auditable. Patterns plus an entropy heuristic, with the bias set to
over-redact -- a redacted non-secret is an inconvenience, the reverse is a
breach.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Final, Iterable, Pattern

from ..errors import UnredactableSecret

REDACTED: Final[str] = "[REDACTED:{label}]"

#: Ordered most-specific first so a matched provider key is not also caught by
#: the generic assignment rule.
_PATTERNS: Final[tuple[tuple[str, Pattern[str]], ...]] = (
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    # anthropic BEFORE openai: "sk-ant-..." is a subset of the "sk-..." shape,
    # and a mislabelled redaction makes the audit trail lie about what leaked.
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("google-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("private-key", re.compile(r"-----BEGIN[ A-Z]*PRIVATE KEY-----[\s\S]*?-----END[ A-Z]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}")),
    ("url-credentials", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/@:]+:[^\s/@]+@")),
    # Generic `KEY = "value"` assignments. Last, and narrow: the name must look
    # like a secret AND the value must be long enough to be one.
    (
        "assigned-secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|token|password|passwd|client[_-]?secret)\b"
            r"\s*[:=]\s*[\"']?([A-Za-z0-9/+_\-]{16,})[\"']?"
        ),
    ),
)

#: Below this, a long random-looking string is probably a hash or an id we want
#: to keep. Above it, assume secret.
_ENTROPY_THRESHOLD: Final[float] = 4.0
_ENTROPY_MIN_LEN: Final[int] = 32


@dataclass(frozen=True, slots=True)
class RedactionReport:
    """What was removed. Recorded in event meta so redaction is auditable."""

    text: str
    labels: tuple[str, ...]
    scanned: bool = True
    """False when the payload could not be rewritten and was only checked.

    ``labels`` being empty then means "nothing found in what we could read",
    not "nothing is there", and the two must not look alike to a reader of the
    audit projection.
    """

    @property
    def redacted(self) -> bool:
        return bool(self.labels)


def shannon_entropy(value: str) -> float:
    """Bits of entropy per character."""
    if not value:
        return 0.0
    counts: dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    length = len(value)
    return -sum((n / length) * math.log2(n / length) for n in counts.values())


def _redact_high_entropy(text: str) -> tuple[str, bool]:
    """Catch novel credential formats the patterns above do not know."""
    hit = False

    def _replace(match: re.Match[str]) -> str:
        nonlocal hit
        token = match.group(0)
        if shannon_entropy(token) >= _ENTROPY_THRESHOLD:
            hit = True
            return REDACTED.format(label="high-entropy")
        return token

    return re.sub(rf"\b[A-Za-z0-9/+_\-]{{{_ENTROPY_MIN_LEN},}}\b", _replace, text), hit


def redact(text: str, *, entropy_scan: bool = True) -> RedactionReport:
    """Return ``text`` with credentials replaced, plus what was found."""
    labels: list[str] = []
    for label, pattern in _PATTERNS:
        text, count = pattern.subn(REDACTED.format(label=label), text)
        if count:
            labels.append(label)
    if entropy_scan:
        text, hit = _redact_high_entropy(text)
        if hit:
            labels.append("high-entropy")
    return RedactionReport(text=text, labels=tuple(labels))


def redact_bytes(payload: bytes, *, entropy_scan: bool = True) -> tuple[bytes, RedactionReport]:
    """Redact a UTF-8 payload. A non-UTF-8 payload is scanned, not rewritten.

    Rewriting bytes we cannot decode would corrupt them, so they are stored
    as-is -- but they are still *checked*, on a lossy decode, and a credential
    found in one raises :class:`UnredactableSecret` rather than being archived.
    Letting a key through because the bytes around it were not text inverts the
    only bias this module has.

    The check is patterns-only: a lossy decode of binary turns every run of
    bytes into high-entropy gibberish, so the entropy heuristic would reject
    every screenshot and archive in the system.
    """
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        found = redact(payload.decode("utf-8", "ignore"), entropy_scan=False).labels
        if found:
            raise UnredactableSecret(found)
        return payload, RedactionReport(text="", labels=(), scanned=False)
    report = redact(text, entropy_scan=entropy_scan)
    return report.text.encode("utf-8"), report


def scan(texts: Iterable[str]) -> tuple[str, ...]:
    """Labels found across ``texts``, without producing redacted output."""
    found: set[str] = set()
    for text in texts:
        found.update(redact(text).labels)
    return tuple(sorted(found))
