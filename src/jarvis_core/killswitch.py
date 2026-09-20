"""The kill switch (R12, docs/05 §5.4).

Local, immediate, model-independent. Halts autonomous execution and refuses
every capability above observation until released.

**It must not be reachable by the things it governs.** In deployment this is a
separate process, ideally on separate hardware, and the sentinel is a file only
that process can write. The core only ever *reads* it -- there is deliberately
no ``engage()`` that an agent could reach through a tool, because an agent that
can disable its own supervision has none.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class KillSwitch(ABC):
    """Read-only from the core's perspective."""

    @abstractmethod
    def is_engaged(self) -> bool:
        """True when all autonomous execution must stop."""

    @abstractmethod
    def reason(self) -> str | None:
        """Why it was engaged, if known."""


class FileKillSwitch(KillSwitch):
    """Backed by the presence of a sentinel file written out-of-band.

    Fails **closed**: if the sentinel cannot be read -- permissions, a missing
    mount, a disk error -- we assume engaged. An unreadable kill switch is
    indistinguishable from a tampered one, and the safe reading of "I don't
    know" is "stop".
    """

    def __init__(self, sentinel: Path | str) -> None:
        self._sentinel = Path(sentinel)

    def is_engaged(self) -> bool:
        try:
            return self._sentinel.exists()
        except OSError:
            return True  # fail closed

    def reason(self) -> str | None:
        try:
            if not self._sentinel.exists():
                return None
            return self._sentinel.read_text(encoding="utf-8").strip() or "engaged"
        except OSError:
            return "kill switch unreadable; failing closed"


class NullKillSwitch(KillSwitch):
    """Never engaged. For tests, and only for tests."""

    def is_engaged(self) -> bool:
        return False

    def reason(self) -> str | None:
        return None
