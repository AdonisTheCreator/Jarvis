"""Identifiers and content addressing.

ULIDs are used for event ids because they sort lexicographically by creation
time, which makes the append-only log scannable in order without a secondary
index -- and they carry no PII, unlike a timestamp plus a hostname.

Content addressing uses BLAKE2b-256 (stdlib; ``blake3`` is not, and the extra
dependency is not worth the speed here).
"""
from __future__ import annotations

import hashlib
import os
import time
from typing import Final

# Crockford base32: no I, L, O, U -- unambiguous when read aloud, which matters
# for a system whose primary interface is voice.
_CROCKFORD: Final[str] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_TIME_BYTES: Final[int] = 6  # 48 bits of milliseconds -> good until year 10889
_RAND_BYTES: Final[int] = 10  # 80 bits of randomness
ULID_LENGTH: Final[int] = 26

BLOB_PREFIX: Final[str] = "b2"


def _encode_crockford(data: bytes, length: int) -> str:
    """Encode ``data`` as Crockford base32, left-padded to ``length`` chars."""
    number = int.from_bytes(data, "big")
    out = []
    for _ in range(length):
        number, remainder = divmod(number, 32)
        out.append(_CROCKFORD[remainder])
    return "".join(reversed(out))


def new_ulid(when_ms: int | None = None) -> str:
    """Return a fresh ULID.

    ``when_ms`` is injectable so tests can pin ordering without sleeping.
    """
    ms = int(time.time() * 1000) if when_ms is None else when_ms
    if ms < 0:
        raise ValueError("timestamp must not be negative")
    payload = ms.to_bytes(_TIME_BYTES, "big") + os.urandom(_RAND_BYTES)
    return _encode_crockford(payload, ULID_LENGTH)


def ulid_timestamp_ms(ulid: str) -> int:
    """Recover the millisecond timestamp encoded in a ULID."""
    if len(ulid) != ULID_LENGTH:
        raise ValueError(f"not a ULID: {ulid!r}")
    number = 0
    for char in ulid.upper():
        try:
            number = number * 32 + _CROCKFORD.index(char)
        except ValueError as exc:  # noqa: PERF203 - clearer than a comprehension
            raise ValueError(f"invalid ULID character {char!r}") from exc
    # Shift off the 80 random bits.
    return number >> (_RAND_BYTES * 8)


def content_hash(data: bytes) -> str:
    """Content address for a payload blob, as ``b2:<64 hex chars>``."""
    return f"{BLOB_PREFIX}:{hashlib.blake2b(data, digest_size=32).hexdigest()}"


def verify_content_hash(data: bytes, expected: str) -> bool:
    """Constant-time check that ``data`` hashes to ``expected``."""
    import hmac

    return hmac.compare_digest(content_hash(data), expected)
