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
class ClaimToken:
    """Proof of one specific claim attempt.

    Held by whoever took the claim, and required to resolve it. Carrying the
    generation is what stops a late resolution from an abandoned attempt
    settling a newer one that happens to share the key -- keys hash the
    *action*, so every retry of an action shares its predecessor's key.
    """

    key: str
    generation: int


@dataclass(frozen=True, slots=True)
class Claim:
    key: str
    state: ClaimState
    result_ref: str | None = None
    generation: int = 0

    @property
    def should_execute(self) -> bool:
        return self.state is ClaimState.FRESH

    @property
    def token(self) -> ClaimToken:
        return ClaimToken(key=self.key, generation=self.generation)


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
        self._generations: dict[str, int] = {}
        self._lock = threading.Lock()

    def claim(self, key: str) -> Claim:
        """Atomically claim ``key``. Only a FRESH claim may execute.

        Each successful claim gets a new *generation*. A late poll carrying an
        older generation cannot resolve a newer attempt -- without that, a
        stale ``complete()`` marks a re-claim DONE, ``release()`` then no-ops,
        and the action is suppressed permanently.
        """
        with self._lock:
            existing = self._states.get(key)
            if existing is not None:
                return existing
            self._generations[key] = self._generations.get(key, 0) + 1
            self._states[key] = Claim(
                key=key, state=ClaimState.IN_FLIGHT, generation=self._generations[key]
            )
            return Claim(key=key, state=ClaimState.FRESH, generation=self._generations[key])

    def complete(self, token: ClaimToken, result_ref: str | None = None) -> bool:
        """Mark a claim done. False when the token has been superseded."""
        with self._lock:
            current = self._states.get(token.key)
            if current is None or current.state is not ClaimState.IN_FLIGHT:
                return False
            if current.generation != token.generation:
                return False  # a late resolution from an abandoned attempt
            self._states[token.key] = Claim(
                key=token.key, state=ClaimState.DONE, result_ref=result_ref,
                generation=current.generation,
            )
            return True

    def release(self, token: ClaimToken) -> bool:
        """Abandon a claim after a failure that did *not* take effect.

        Call this only when the side effect provably did not happen. When in
        doubt, leave the claim in flight: a stuck claim needs a human, a
        wrongly released one sends the message twice.

        Returns False when there was nothing to release, or when the token has
        been superseded by a newer attempt.
        """
        with self._lock:
            current = self._states.get(token.key)
            if current is None or current.state is not ClaimState.IN_FLIGHT:
                return False
            if current.generation != token.generation:
                return False
            del self._states[token.key]
            return True

    def in_flight(self) -> list[str]:
        """Keys still claimed but not resolved.

        Includes healthy work in progress as well as claims nobody resolved.
        Either way they block the retry, so they must be enumerable rather
        than silently permanent.
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


