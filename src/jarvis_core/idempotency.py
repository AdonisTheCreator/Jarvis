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
    generation: int = 0
    """Increments on every fresh claim, so a late poll cannot resolve a newer
    attempt that happens to share the key."""

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
        self._handles: dict[str, str] = {}
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

    def bind(self, key: str, handle_ref: str, *, generation: int | None = None) -> None:
        """Associate a backend handle with a claim.

        Lives here rather than in the router because the ledger is the durable
        side: an in-process map would be lost on restart while the claim it
        described stayed IN_FLIGHT forever, blocking every retry.

        ``handle_ref`` must be globally unique -- backends may mint colliding
        local ids, and resolving one backend's handle to another's claim is how
        polling B releases A.
        """
        with self._lock:
            existing = self._handles.get(handle_ref)
            if existing is not None and existing != key:
                # Two live claims cannot share a handle reference. Silently
                # overwriting strands the first one forever; raising surfaces
                # the adapter bug (usually a backend minting duplicate ids)
                # while it is still cheap to find.
                raise ValueError(
                    f"handle {handle_ref!r} is already bound to a different claim; "
                    "a backend must not reuse a handle id for two in-flight actions"
                )
            self._handles[handle_ref] = key

    def key_for(self, handle_ref: str) -> str | None:
        with self._lock:
            return self._handles.get(handle_ref)

    def complete(self, key: str, result_ref: str | None = None, *, generation: int | None = None) -> bool:
        """Mark a claim done. Returns False if it was already superseded."""
        with self._lock:
            current = self._states.get(key)
            if current is None or current.state is not ClaimState.IN_FLIGHT:
                return False
            if generation is not None and current.generation != generation:
                return False  # a stale poll from an earlier attempt
            self._states[key] = Claim(
                key=key, state=ClaimState.DONE, result_ref=result_ref,
                generation=current.generation,
            )
            self._unbind(key)
            return True

    def release(self, key: str, *, generation: int | None = None) -> bool:
        """Abandon a claim after a failure that did *not* take effect.

        Call this only when the side effect provably did not happen. When in
        doubt, leave the claim in flight: a stuck claim needs a human, a
        wrongly released one sends the message twice.

        Returns False when there was nothing to release, or when the caller's
        generation has been superseded by a newer attempt.
        """
        with self._lock:
            current = self._states.get(key)
            if current is None or current.state is not ClaimState.IN_FLIGHT:
                return False
            if generation is not None and current.generation != generation:
                return False
            del self._states[key]
            self._unbind(key)
            return True

    def _unbind(self, key: str) -> None:
        """Drop every handle pointing at ``key``. Caller holds the lock.

        Because keys hash the *action*, a retry shares its predecessor's key.
        Leaving a dead handle bound would let a late poll on it settle the
        retry's live claim -- and then a third attempt would duplicate the
        side effect.
        """
        for handle_ref in [h for h, k in self._handles.items() if k == key]:
            del self._handles[handle_ref]

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

    def generation(self, key: str) -> int | None:
        with self._lock:
            claim = self._states.get(key)
            return claim.generation if claim else None
