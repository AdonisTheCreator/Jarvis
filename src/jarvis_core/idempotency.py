"""Exactly-once side effects (docs/02 §8, docs/05 §6.4).

At-least-once delivery plus retries at more than one layer is how a system
sends the message twice, buys the thing twice, or deletes it twice. The fix is
a key derived from *what the action is*, not from when it was attempted, and
enforced at the adapter boundary so no call site can forget.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping, Sequence


class ClaimState(StrEnum):
    FRESH = "fresh"
    """First time this action has been seen. Proceed."""
    IN_FLIGHT = "in_flight"
    """A previous attempt is still running. Do NOT start a second one."""
    DONE = "done"
    """Already completed. Return the recorded result instead of repeating it."""


@dataclass(frozen=True, slots=True)
class Claim:
    key: str
    state: ClaimState
    result_ref: str | None = None

    @property
    def should_execute(self) -> bool:
        return self.state is ClaimState.FRESH


def derive_key(
    capability: str,
    target: str,
    params: Mapping[str, Any],
    key_fields: Sequence[str],
    *,
    occasion: str | None = None,
) -> str:
    """Derive a stable idempotency key.

    Only ``key_fields`` participate, so incidental parameters -- a trace id, a
    retry counter, a timestamp -- do not make the same action look new. That is
    the whole trick: a retry must hash to the same key, a genuinely different
    action must not.

    ``occasion`` separates deliberate repeats ("send the same reminder again
    tomorrow") from accidental ones. Same action, different occasion, different
    key.
    """
    if not key_fields:
        raise ValueError(
            f"capability {capability!r} declares no idempotency_key_fields; "
            "it must not be treated as side-effecting"
        )
    missing = [field for field in key_fields if field not in params]
    if missing:
        raise ValueError(f"{capability!r} is missing idempotency fields: {missing}")

    material = {
        "capability": capability,
        "target": target,
        "params": {field: params[field] for field in sorted(key_fields)},
        "occasion": occasion,
    }
    canonical = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.blake2b(canonical.encode(), digest_size=16).hexdigest()


class IdempotencyLedger:
    """Tracks which side effects have been claimed, started and finished.

    In deployment this is durable -- a ledger that forgets across a restart
    permits exactly the duplicate it exists to prevent. The in-memory default
    is honest about its scope rather than pretending otherwise.
    """

    def __init__(self) -> None:
        self._states: dict[str, Claim] = {}
        self._lock = threading.Lock()

    def claim(self, key: str) -> Claim:
        """Atomically claim ``key``. Only a FRESH claim may execute."""
        with self._lock:
            existing = self._states.get(key)
            if existing is not None:
                return existing
            claim = Claim(key=key, state=ClaimState.IN_FLIGHT)
            self._states[key] = claim
            return Claim(key=key, state=ClaimState.FRESH)

    def complete(self, key: str, result_ref: str | None = None) -> None:
        with self._lock:
            self._states[key] = Claim(key=key, state=ClaimState.DONE, result_ref=result_ref)

    def release(self, key: str) -> None:
        """Abandon a claim after a failure that did *not* take effect.

        Call this only when the side effect provably did not happen. When in
        doubt, leave the claim in flight: a stuck claim needs a human, a
        wrongly released one sends the message twice.
        """
        with self._lock:
            current = self._states.get(key)
            if current is not None and current.state is ClaimState.IN_FLIGHT:
                del self._states[key]

    def in_flight(self) -> list[str]:
        """Keys still claimed but not completed.

        A claim can legitimately sit here (work in progress) or be *stuck* --
        an interrupted effect nobody resolved. Either way it blocks the retry,
        so it must be enumerable rather than silently permanent.
        """
        with self._lock:
            return sorted(
                key for key, claim in self._states.items()
                if claim.state is ClaimState.IN_FLIGHT
            )

    def state(self, key: str) -> ClaimState | None:
        with self._lock:
            claim = self._states.get(key)
            return claim.state if claim else None
