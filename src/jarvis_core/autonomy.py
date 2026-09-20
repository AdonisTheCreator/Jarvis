"""Autonomy classes (docs/05 §5.1).

Lives at the top level, not inside ``policy``: an autonomy class is a property
of a *capability*, and the Policy Engine merely reads it. Nesting it under
``policy`` created a capability -> policy -> engine -> capability import cycle,
which was the design telling us where the type belonged.

The class is a property of the **capability**, never of the agent. "This agent
is trusted" is not expressible here, deliberately: trust that travels with an
actor is how a coding worker ends up holding banking credentials.
"""
from __future__ import annotations

from enum import IntEnum


class AutonomyClass(IntEnum):
    """Ordered by blast radius. Higher is more dangerous."""

    A0_OBSERVE = 0
    """Read status, search, summarise. Automatic; logged."""

    A1_REVERSIBLE = 1
    """Reversible personal action -- lights, media, drafts, worktrees.
    Automatic once the capability is explicitly enabled."""

    A2_EXTERNAL = 2
    """External but low impact -- a routine message, a calendar event.
    Ask, until the specific routine is promoted (docs/02 §6)."""

    A3_CONSEQUENTIAL = 3
    """Financial, public, physical access, access control.
    Requires a declared Protocol, explicit confirmation and strong auth."""

    A4_BLOCKED = 4
    """Safety-critical or unsupported. Blocked, with no override path --
    not "ask harder", not "allow with a flag". Blocked."""

    @property
    def needs_approval(self) -> bool:
        return self >= AutonomyClass.A2_EXTERNAL

    @property
    def needs_protocol(self) -> bool:
        """A3 actions may only run as a pre-declared Protocol (R8, docs/01 §6).

        This is the JARVIS design pattern: dangerous capability that requires
        no in-the-moment model judgment, because the sequence was designed,
        reviewed and named in calm conditions.
        """
        return self == AutonomyClass.A3_CONSEQUENTIAL

    @property
    def is_blocked(self) -> bool:
        return self == AutonomyClass.A4_BLOCKED

    @property
    def label(self) -> str:
        return {
            AutonomyClass.A0_OBSERVE: "A0 observe",
            AutonomyClass.A1_REVERSIBLE: "A1 reversible",
            AutonomyClass.A2_EXTERNAL: "A2 external",
            AutonomyClass.A3_CONSEQUENTIAL: "A3 consequential",
            AutonomyClass.A4_BLOCKED: "A4 blocked",
        }[self]
