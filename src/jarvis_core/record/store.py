"""The append-only Record store (docs/11, D5).

One write path, four read projections. On disk:

    <root>/log.jsonl     one line per event: {chain, event}
    <root>/blobs/<b2>/   sealed payloads, content-addressed

Two integrity properties, both of which must survive ``forget()``:

* **Append-only with tamper evidence.** Each line carries
  ``chain = H(prev_chain || canonical_event_json)``. Rewriting or removing any
  earlier line breaks every chain value after it.
* **Shredding leaves structure intact.** Payloads are sealed per subject
  (``crypto``). Destroying a subject key makes payloads unreadable while ids,
  hashes, causal parents and the chain remain verifiable -- which is what lets
  the audit projection stay trustworthy after a forget.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Literal, Sequence

from ..errors import RecordIntegrityError, SubjectForgotten
from ..ids import content_hash
from .crypto import Sealed, SubjectKeystore
from .events import Event, EventKind
from .redact import RedactionReport, redact_bytes

GENESIS: str = "0" * 64
Projection = Literal["audit", "recall", "reconstruct", "consolidate"]


def _chain(previous: str, event_json: str) -> str:
    return hashlib.blake2b(f"{previous}|{event_json}".encode(), digest_size=32).hexdigest()


@dataclass(frozen=True, slots=True)
class StoredEvent:
    """An event as it sits in the log, with its chain value."""

    event: Event
    chain: str


class RecordStore:
    """Append-only event log with sealed, content-addressed payloads.

    Thread-safe. The Record is written concurrently by sessions, watchers and
    the subconscious; a torn append would break the chain permanently.
    """

    def __init__(self, root: Path | str, keystore: SubjectKeystore, *, redact: bool = True) -> None:
        self.root = Path(root)
        self.blobs = self.root / "blobs"
        self.log_path = self.root / "log.jsonl"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self.log_path.touch(exist_ok=True)
        self._keystore = keystore
        self._redact = redact
        self._lock = threading.Lock()
        self._epoch_lock = threading.Lock()
        self._head = self._read_head()

    # -- writing ---------------------------------------------------------

    def append(
        self,
        event: Event,
        payload: bytes | None = None,
        *,
        payload_subject: str | None = None,
    ) -> StoredEvent:
        """Seal ``payload``, write the blob, append the event. Atomic per call.

        ``payload_subject`` defaults to the event's first subject key -- the
        subject whose ``forget()`` should render this payload unreadable.
        """
        report: RedactionReport | None = None
        if payload is not None:
            if self._redact:
                payload, report = redact_bytes(payload)
            subject = payload_subject or event.subject_keys[0]
            ref = content_hash(payload)
            event = event.with_payload(ref)
            if payload_subject is not None and payload_subject != event.subject_keys[0]:
                event = Event.from_dict(
                    {**event.to_dict(), "meta": {**event.meta, "payload_subject": payload_subject}}
                )
            # Read the epoch, seal, and write the blob under one lock, which
            # forget_subject also takes. Sampling the epoch outside it lets a
            # forget land in the window, so the event records a stale epoch and
            # its payload -- sealed under a live key -- reads back as forgotten.
            with self._epoch_lock:
                epoch = self.current_epoch(subject)
                event = Event.from_dict(
                    {**event.to_dict(), "meta": {**event.meta, "payload_epoch": epoch}}
                )
                sealed = self._keystore.seal(
                    subject, payload, aad=event.payload_aad(subject)
                )
                self._write_blob(ref, subject, epoch, sealed)

        if report is not None and (report.redacted or not report.scanned):
            meta = dict(event.meta)
            if report.redacted:
                meta["redacted"] = list(report.labels)
            if not report.scanned:
                # An empty "redacted" on a binary payload would read as "we
                # looked and it was clean". We looked at what we could decode.
                meta["redaction_scanned"] = False
            event = Event.from_dict({**event.to_dict(), "meta": meta})

        with self._lock:
            chain = _chain(self._head, event.to_json())
            line = json.dumps(
                {"chain": chain, "event": event.to_dict()},
                sort_keys=True,
                separators=(",", ":"),
            )
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()
                os.fsync(handle.fileno())  # a torn append breaks the chain forever
            self._head = chain
            return StoredEvent(event=event, chain=chain)

    def _write_blob(self, ref: str, subject: str, epoch: int, sealed: Sealed) -> None:
        path = self._blob_path(ref, subject, epoch)
        if path.exists():
            # Safe again now that blobs are namespaced by key epoch: an
            # existing blob at this path was sealed under the *current* key, so
            # reusing it neither loses data nor un-forgets any.
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        # A unique temp name per writer. A shared one races: concurrent writers
        # of the same payload destroy each other's file and their events never
        # reach the log.
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_bytes(subject.encode("utf-8") + b"\0" + sealed.to_bytes())
        tmp.replace(path)

    def _namespace(self, subject: str) -> Path:
        return self.blobs / hashlib.blake2b(subject.encode(), digest_size=8).hexdigest()

    def _epoch_path(self, subject: str) -> Path:
        return self._namespace(subject) / "EPOCH"

    def current_epoch(self, subject: str) -> int:
        """Which generation of this subject's key the blobs on disk belong to.

        Durable, and owned by the store rather than the keystore, for two
        reasons the review found the hard way: held in process memory it reset
        on restart and the dedup then reused a blob sealed under the previous
        run's destroyed key; and reading it must never create a key, or a
        single read would resurrect a subject the user asked to erase.
        """
        path = self._epoch_path(subject)
        if not path.exists():
            return 1  # nothing forgotten yet
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError) as exc:
            # Fail closed. Returning 1 would collapse the namespace back to
            # e1/ and un-namespace blobs whose key was destroyed.
            raise RecordIntegrityError(
                f"epoch for {subject!r} is unreadable; refusing to assume it is 1"
            ) from exc

    def _bump_epoch_locked(self, subject: str) -> int:
        """Advance the epoch. Caller holds ``_epoch_lock``."""
        nxt = self.current_epoch(subject) + 1
        path = self._epoch_path(subject)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"EPOCH.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(str(nxt), encoding="utf-8")
        tmp.replace(path)
        return nxt

    def _blob_path(self, ref: str, subject: str, epoch: int) -> Path:
        """Blobs are namespaced per subject **and key epoch**.

        Content addressing dedupes within one subject and epoch, which is where
        the repetition actually is. Sharing across subjects would let one
        subject's forget leave another's copy readable; sharing across epochs
        would let a write after a forget re-seal the blob and make the
        already-forgotten event readable again.
        """
        digest = ref.split(":", 1)[1]
        return self._namespace(subject) / f"e{epoch}" / digest[:2] / digest

    # -- reading ---------------------------------------------------------

    def __iter__(self) -> Iterator[StoredEvent]:
        return self.scan()

    def scan(self, *, kinds: Sequence[EventKind] | None = None) -> Iterator[StoredEvent]:
        """Walk the log in write order. ULIDs make that time order too."""
        wanted = set(kinds) if kinds else None
        with self.log_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                event = Event.from_dict(row["event"])
                if wanted is None or event.kind in wanted:
                    yield StoredEvent(event=event, chain=row["chain"])

    def payload(self, event: Event) -> bytes:
        """Unseal an event's payload.

        Raises :class:`SubjectForgotten` if the subject was forgotten -- which
        is a correct outcome, not an error to swallow.
        """
        if event.payload_ref is None:
            raise ValueError(f"event {event.id} carries no payload")
        subject = str(event.meta.get("payload_subject") or event.subject_keys[0])
        epoch = int(event.meta.get("payload_epoch", 1))
        if epoch < self.current_epoch(subject):
            # The key that sealed this is gone. Say so precisely rather than
            # letting it surface as an authentication failure, which would be
            # indistinguishable from tampering.
            raise SubjectForgotten(subject)
        raw = self._blob_path(event.payload_ref, subject, epoch).read_bytes()
        stored_subject, _, body = raw.partition(b"\0")
        sealed = Sealed.from_bytes(stored_subject.decode("utf-8"), body)
        return self._keystore.unseal(sealed, aad=event.payload_aad(stored_subject.decode("utf-8")))

    def payload_or_none(self, event: Event) -> bytes | None:
        """Like :meth:`payload`, but forgotten subjects read as ``None``.

        For projections that must keep working across a forget -- audit, and
        any listing that shows *that* something happened without its content.
        """
        if event.payload_ref is None:
            return None  # nothing to read; policy decisions carry no payload
        try:
            return self.payload(event)
        except (SubjectForgotten, FileNotFoundError):
            # A destroyed key raises SubjectForgotten; its blob may also be
            # gone. Both mean "forgotten", which a projection must tolerate.
            # An authentication failure is *not* caught: that means tampering,
            # and silently reading it as forgotten would hide it.
            return None

    # -- integrity -------------------------------------------------------

    def verify(self) -> int:
        """Re-walk the chain. Returns the number of events verified.

        Deliberately independent of payload readability: a log whose subjects
        have all been forgotten must still verify, or ``forget()`` would look
        indistinguishable from tampering.
        """
        previous = GENESIS
        count = 0
        for stored in self.scan():
            expected = _chain(previous, stored.event.to_json())
            if expected != stored.chain:
                raise RecordIntegrityError(
                    f"chain broken at event {stored.event.id}: "
                    f"expected {expected[:12]}…, found {stored.chain[:12]}…"
                )
            previous = stored.chain
            count += 1
        return count

    def _read_head(self) -> str:
        head = GENESIS
        with self.log_path.open(encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    head = json.loads(line)["chain"]
        return head

    # -- forgetting ------------------------------------------------------

    def forget_subject(self, subject: str) -> bool:
        """Crypto-shred ``subject``.

        Destroys the key only. Callers are responsible for the *fan-out* to
        derived artefacts -- embeddings, summaries, learned skills (docs/11 §6)
        -- which is why this returns rather than pretending to be complete.
        """
        # Same lock as the payload path in append(), so a write cannot be
        # sealing under a key this is about to destroy.
        with self._epoch_lock:
            # Bump *before* destroying. A crash between the two then leaves the
            # epoch advanced, which is the safe direction -- later writes land
            # in a fresh namespace. The reverse order strands the epoch, and a
            # retried forget returns False so it can never be repaired.
            self._bump_epoch_locked(subject)
            return self._keystore.forget(subject)
