"""Scoped, single-use approval tokens (docs/05 §5.2).

An approval binds to **(capability, target, exact parameters, expiry,
single-use)**. "Approve this agent" is not expressible in the schema -- there
is no field for it, which is the point. An open-ended grant is how a system
with good rules ends up behaving like one without any.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping

from typing import Protocol as TypingProtocol

from ..errors import ApprovalInvalid
from ..ids import new_ulid

DEFAULT_TTL_SECONDS: int = 300


def params_fingerprint(params: Mapping[str, Any]) -> str:
    """Stable hash of the exact parameters the human was shown.

    If the parameters change between approval and execution -- a different
    recipient, a different amount -- the fingerprint changes and the token no
    longer authorizes the call. That is the whole mechanism.
    """
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.blake2b(canonical.encode(), digest_size=16).hexdigest()


@dataclass(frozen=True, slots=True)
class ApprovalToken:
    """Proof that a human approved one specific action, once."""

    id: str
    capability: str
    target: str
    params_hash: str
    expires_at: float
    signature: str

    def is_expired(self, *, now: float | None = None) -> bool:
        return (now if now is not None else time.time()) >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "capability": self.capability,
            "target": self.target,
            "params_hash": self.params_hash,
            "expires_at": self.expires_at,
            "signature": self.signature,
        }


class SpentStore(TypingProtocol):
    """Where spent approval ids live.

    Deliberately an interface: single-use is only true if "already spent"
    survives a restart. The in-memory default does not, so a captured token
    could be replayed after a restart inside its TTL -- acceptable while the
    whole core is in-memory, and a real hazard the moment anything else is
    durable. Back it with the same store as the Record before going live.
    """

    durable: bool
    """Whether "already spent" survives a restart. Declared, not optional: a
    default of True would fail open for a store that simply omitted it."""

    def try_spend(self, token_id: str) -> bool:
        """Atomically mark spent. False if it was already spent.

        A separate ``contains`` then ``add`` is not atomic across processes,
        so two workers could redeem the same captured token concurrently --
        which is exactly what single-use exists to prevent.
        """
        ...


class InMemorySpentStore:
    """Process-local. Honest about its scope rather than pretending."""

    durable: bool = False

    def __init__(self) -> None:
        self._ids: set[str] = set()
        self._lock = threading.Lock()

    def try_spend(self, token_id: str) -> bool:
        with self._lock:
            if token_id in self._ids:
                return False
            self._ids.add(token_id)
            return True


class ApprovalLedger:
    """Issues, verifies and spends approval tokens.

    Tokens are HMAC-signed so a forged one is detectable, and single-use so a
    captured one cannot be replayed. Both matter once approvals can be granted
    by voice from a phone (docs/15 §7).
    """

    def __init__(self, secret: bytes, spent: SpentStore | None = None) -> None:
        if len(secret) < 32:
            raise ValueError("approval secret must be at least 32 bytes")
        self._secret = secret
        self._spent: SpentStore = spent if spent is not None else InMemorySpentStore()
        self._lock = threading.Lock()

    @property
    def durable(self) -> bool:
        """Whether single-use survives a restart.

        Fails closed: a store that does not declare ``durable`` is treated as
        non-durable, because assuming otherwise would silently claim a
        guarantee nobody made.
        """
        return bool(getattr(self._spent, "durable", False))

    def issue(
        self,
        capability: str,
        target: str,
        params: Mapping[str, Any],
        *,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        now: float | None = None,
    ) -> ApprovalToken:
        issued_at = now if now is not None else time.time()
        token_id = new_ulid()
        params_hash = params_fingerprint(params)
        expires_at = issued_at + ttl_seconds
        return ApprovalToken(
            id=token_id,
            capability=capability,
            target=target,
            params_hash=params_hash,
            expires_at=expires_at,
            signature=self._sign(token_id, capability, target, params_hash, expires_at),
        )

    def redeem(
        self,
        token: ApprovalToken,
        capability: str,
        target: str,
        params: Mapping[str, Any],
        *,
        now: float | None = None,
    ) -> None:
        """Consume ``token`` for this exact call, or raise ``ApprovalInvalid``.

        Checked in order of cheapness, but every failure is equally fatal --
        there is no "close enough" approval.
        """
        expected = self._sign(
            token.id, token.capability, token.target, token.params_hash, token.expires_at
        )
        if not hmac.compare_digest(expected, token.signature):
            raise ApprovalInvalid("approval signature does not verify")
        if token.is_expired(now=now):
            raise ApprovalInvalid(f"approval {token.id} expired")
        if token.capability != capability:
            raise ApprovalInvalid(
                f"approval is for {token.capability!r}, not {capability!r}"
            )
        if token.target != target:
            raise ApprovalInvalid(f"approval is for target {token.target!r}, not {target!r}")
        if token.params_hash != params_fingerprint(params):
            raise ApprovalInvalid(
                "parameters changed since approval -- the human approved a different action"
            )
        # Atomic in the store, not merely under this process's lock: a shared
        # durable store must be safe against two workers at once.
        if not self._spent.try_spend(token.id):
            raise ApprovalInvalid(f"approval {token.id} was already used")

    def _sign(
        self, token_id: str, capability: str, target: str, params_hash: str, expires_at: float
    ) -> str:
        message = f"{token_id}|{capability}|{target}|{params_hash}|{expires_at!r}".encode()
        return hmac.new(self._secret, message, hashlib.blake2b).hexdigest()
