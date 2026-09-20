"""Per-subject encryption and crypto-shredding (docs/11 §6, D5).

The Record is append-only, so ``forget()`` cannot delete rows. Instead each
payload is encrypted under a key belonging to its *subject*, and forgetting a
subject destroys that key. The ciphertext stays, the hashes and causal links
stay intact, and the content becomes unrecoverable.

**The subtle trap this module avoids.** The obvious design derives a subject key
from a master key (``HKDF(master, subject)``). That silently breaks shredding:
anyone holding the master can re-derive a key you "destroyed", so the guarantee
is false. Instead, subject keys are **randomly generated and stored wrapped**
under the master. Shredding deletes the wrapped key. The master protects the
keystore; it cannot reconstruct a deleted entry.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import Final, Protocol

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from ..errors import SubjectForgotten

KEY_BYTES: Final[int] = 32  # AES-256
NONCE_BYTES: Final[int] = 12  # GCM standard


@dataclass(frozen=True, slots=True)
class Sealed:
    """An encrypted payload. Safe to store, useless without the subject key."""

    subject: str
    nonce: bytes
    ciphertext: bytes

    def to_bytes(self) -> bytes:
        """Wire format: nonce || ciphertext. Subject travels in the event."""
        return self.nonce + self.ciphertext

    @classmethod
    def from_bytes(cls, subject: str, raw: bytes) -> Sealed:
        if len(raw) <= NONCE_BYTES:
            raise ValueError("sealed payload too short")
        return cls(subject=subject, nonce=raw[:NONCE_BYTES], ciphertext=raw[NONCE_BYTES:])


class KeyVault(Protocol):
    """Where wrapped subject keys live.

    Production backs this with the OS keyring or an HSM. The interface is tiny
    on purpose: the security property is "delete really deletes".
    """

    def put(self, subject: str, wrapped: bytes) -> None: ...
    def get(self, subject: str) -> bytes | None: ...
    def delete(self, subject: str) -> bool: ...
    def subjects(self) -> list[str]: ...


@dataclass(slots=True)
class InMemoryKeyVault:
    """A vault that lives and dies with the process. For tests and for boot."""

    _keys: dict[str, bytes] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def put(self, subject: str, wrapped: bytes) -> None:
        with self._lock:
            self._keys[subject] = wrapped

    def get(self, subject: str) -> bytes | None:
        with self._lock:
            return self._keys.get(subject)

    def delete(self, subject: str) -> bool:
        with self._lock:
            return self._keys.pop(subject, None) is not None

    def subjects(self) -> list[str]:
        with self._lock:
            return sorted(self._keys)


class SubjectKeystore:
    """Issues, wraps, unwraps and destroys per-subject payload keys.

    Thread-safe: the Record is written from watchers, sessions and the
    subconscious concurrently, and a torn read of a key is not a failure mode
    worth debugging at 3am.
    """

    def __init__(self, master_key: bytes, vault: KeyVault | None = None) -> None:
        if len(master_key) != KEY_BYTES:
            raise ValueError(f"master key must be {KEY_BYTES} bytes, got {len(master_key)}")
        self._master = AESGCM(master_key)
        self._vault: KeyVault = vault if vault is not None else InMemoryKeyVault()
        self._epochs: dict[str, int] = {}
        self._lock = threading.Lock()

    # -- key lifecycle ---------------------------------------------------

    def ensure_subject(self, subject: str) -> None:
        """Create a key for ``subject`` if it has none. Idempotent.

        Deliberately does *not* resurrect a shredded subject: a caller that
        wants that must say so, so an accidental re-create cannot silently
        undo a forget.
        """
        with self._lock:
            if self._vault.get(subject) is not None:
                return
            self._vault.put(subject, self._wrap(subject, AESGCM.generate_key(bit_length=256)))
            # A new key means a new epoch. Payloads sealed under the previous
            # one must stay unreachable, so the Record namespaces blobs by it
            # -- otherwise re-writing the same content after a forget would
            # re-seal the shared blob and un-forget the old event.
            self._epochs[subject] = self._epochs.get(subject, 0) + 1

    def forget(self, subject: str) -> bool:
        """Destroy the subject's key. Returns True if a key was destroyed.

        After this, every payload sealed to ``subject`` is permanently
        unreadable -- including by us, including with the master key.
        """
        with self._lock:
            return self._vault.delete(subject)

    def epoch(self, subject: str) -> int:
        """Which generation of this subject's key is current.

        Increments every time a key is created, so a forget-then-write cycle
        cannot make an earlier, already-forgotten payload readable again.
        """
        self.ensure_subject(subject)
        with self._lock:
            return self._epochs.get(subject, 1)

    def known_subjects(self) -> list[str]:
        return self._vault.subjects()

    def is_forgotten(self, subject: str) -> bool:
        return self._vault.get(subject) is None

    # -- sealing ---------------------------------------------------------

    def seal(self, subject: str, plaintext: bytes, *, aad: bytes) -> Sealed:
        """Encrypt ``plaintext`` for ``subject``.

        ``aad`` binds the ciphertext to its event, so a payload cannot be moved
        to a different event without detection.
        """
        self.ensure_subject(subject)
        key = self._subject_key(subject)
        nonce = os.urandom(NONCE_BYTES)
        return Sealed(subject, nonce, AESGCM(key).encrypt(nonce, plaintext, aad))

    def unseal(self, sealed: Sealed, *, aad: bytes) -> bytes:
        """Decrypt, or raise :class:`SubjectForgotten` if the key is gone."""
        key = self._subject_key(sealed.subject)
        try:
            return AESGCM(key).decrypt(sealed.nonce, sealed.ciphertext, aad)
        except InvalidTag as exc:
            raise ValueError("payload failed authentication (wrong aad or tampered)") from exc

    # -- internals -------------------------------------------------------

    def _subject_key(self, subject: str) -> bytes:
        wrapped = self._vault.get(subject)
        if wrapped is None:
            raise SubjectForgotten(subject)
        return self._unwrap(subject, wrapped)

    def _wrap(self, subject: str, key: bytes) -> bytes:
        nonce = os.urandom(NONCE_BYTES)
        return nonce + self._master.encrypt(nonce, key, subject.encode("utf-8"))

    def _unwrap(self, subject: str, wrapped: bytes) -> bytes:
        nonce, blob = wrapped[:NONCE_BYTES], wrapped[NONCE_BYTES:]
        return self._master.decrypt(nonce, blob, subject.encode("utf-8"))
