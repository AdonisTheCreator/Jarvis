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

import os
import stat
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

    Encoding "engaged" as the *presence* of a file fights that, because every
    way of failing to see the file looks like absence, which looks like
    "carry on". ``Path.exists()`` makes it worse: it swallows ENOENT,
    ENOTDIR, ELOOP and EBADF and returns False, so a sentinel whose mount has
    gone away reads as not engaged. So we stat the sentinel ourselves, and on
    ENOENT we also check that the directory it would live in is still there.
    Absent from a directory we can see is the one honest "not engaged"; every
    other outcome is "I cannot see the switch", which means stop.
    """

    def __init__(self, sentinel: Path | str) -> None:
        self._sentinel = Path(sentinel)

    def _state(self) -> tuple[bool, str | None]:
        """``(engaged, reason)``. One place, so is_engaged and reason agree."""
        try:
            os.stat(self._sentinel)
        except FileNotFoundError:
            if self._holder_visible():
                return False, None
            return True, "kill switch location unreachable; failing closed"
        except OSError as exc:
            return True, f"kill switch unreadable ({exc.strerror}); failing closed"
        return True, None

    def _holder_visible(self) -> bool:
        """Is the directory the sentinel would live in still a directory?

        A detached mount, a parent replaced by a file, a revoked permission:
        all of them make an absent sentinel mean something other than "the
        operator has not engaged it".
        """
        try:
            return stat.S_ISDIR(os.stat(self._sentinel.parent).st_mode)
        except OSError:
            return False

    def is_engaged(self) -> bool:
        return self._state()[0]

    def reason(self) -> str | None:
        engaged, why = self._state()
        if not engaged:
            return None
        if why is not None:
            return why
        try:
            return self._sentinel.read_text(encoding="utf-8").strip() or "engaged"
        except OSError:
            return "kill switch unreadable; failing closed"


class NullKillSwitch(KillSwitch):
    """Never engaged. For tests, and only for tests."""

    def is_engaged(self) -> bool:
        return False

    def reason(self) -> str | None:
        return None
