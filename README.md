# Jarvis

A personal AI operating layer: **one identity, many hands.**

One persistent assistant at the surface. Underneath, a small core we own — capability
router, policy engine, canonical memory, audit ledger, and a proactivity plane — dispatching
to interchangeable agent runtimes, devices and services.

Dedicated to God. See [`docs/00-DEDICATION-AND-CHARTER.md`](docs/00-DEDICATION-AND-CHARTER.md) —
the charter translates that dedication into seven binding engineering constraints.

---

## Where this stands

This repository currently holds the **research and architecture phase**. No code yet, on
purpose: the contracts come before the integrations.

| Doc | What it answers |
|---|---|
| [00 — Dedication & Charter](docs/00-DEDICATION-AND-CHARTER.md) | What we're committed to, and where each commitment is enforced |
| [01 — JARVIS Character Study](docs/01-JARVIS-CHARACTER-STUDY.md) | What the fictional JARVIS actually does → 13 testable requirements |
| [02 — Proactivity Research](docs/02-PROACTIVITY-RESEARCH.md) | How agents act without being prompted, and when they should stay quiet |
| [03 — Agent OS Landscape](docs/03-AGENT-OS-LANDSCAPE.md) | Verified state of OpenClaw, Hermes, Personal Jarvis, Home Assistant, et al. |
| [04 — Unification Viability](docs/04-UNIFICATION-VIABILITY.md) | **Can we merge the agent OSes?** Verdict and reasoning |
| [05 — Architecture](docs/05-ARCHITECTURE.md) | The refined design and its core contracts |
| [06 — Roadmap](docs/06-ROADMAP.md) | Phased build order with testable exit criteria |
| [07 — Evaluation](docs/07-EVALUATION.md) | Acceptance tests, including proactivity and adversarial suites |
| [08 — Sources](docs/08-SOURCES.md) | Everything above, with verification status |

Start with **04** if you want the argument, **01** if you want the vision, **02** if you
want the part nobody has built yet.

---

## The three findings that shaped the design

**1. The agent OSes are substitutes, not layers.**
OpenClaw, Hermes and Personal Jarvis each implement the same six primitives — control
plane, channels, skills, execution backends, memory, scheduler. Hermes even ships an
importer that migrates a user *off* OpenClaw. Stacking them means three routers, three
memory writers, and duplicate side effects. **Pick one control plane. Attach everything
else as a runtime behind an adapter.** ([04](docs/04-UNIFICATION-VIABILITY.md))

**2. The real merge is already happening one layer down.**
MCP for tools, A2A for agent-to-agent, `SKILL.md` for portable capabilities, and the
agent-harness plugin pattern for runtime ownership. Write capabilities in portable formats
and the underlying agent OS becomes a deployment detail. That is "best of all worlds" —
achieved by *not* running all the worlds at once. ([03](docs/03-AGENT-OS-LANDSCAPE.md) §3)

**3. Proactivity is the product, and it is unbuilt.**
The shipped proactive assistants are all overnight digests. Nobody has a good model of
*when to interrupt a human*. The fictional JARVIS does — three triggers for unprompted
speech, and continuous state routed to the visual periphery so that audio is reserved for
things that change what you do next. That, plus decades of HCI interruptibility research,
is a real design. ([01](docs/01-JARVIS-CHARACTER-STUDY.md) §3–4, [02](docs/02-PROACTIVITY-RESEARCH.md))

---

## Architecture at a glance

```
  SURFACES     room satellites · phone · glasses · desktop · car · channels
                                     │
  ★ JARVIS     Identity · Capability Router · Policy Engine · Protocols ·      ← ours,
    CORE       Canonical Memory · Audit Ledger · PROACTIVITY PLANE               small,
                                     │                                           permanent
  CONTROL      ONE of {OpenClaw | Hermes}                                      ← replaceable
    PLANE      sessions · channels · node registry · skills · tools · cron
                                     │
  RUNTIMES     Claude Code · Codex · Hermes · computer-use · LangGraph         ← swappable
                                     │
  PERIPHERALS  MCP · Home Assistant · Tesla Fleet · store APIs · shell · browser
```

**Invariant:** no file in the core imports a vendor type. If it does, it belongs in an
adapter.

---

## Design rules

1. **One control plane. Exactly one.**
2. **One owner per capability class, written down.** Two providers is fine; two owners is a bug.
3. **The core stays small.** If every project above is abandoned, we rewrite adapters, not the system.
4. **Autonomy is earned per capability, never granted per agent.** ([02](docs/02-PROACTIVITY-RESEARCH.md) §6)
5. **High-consequence actions are pre-declared Protocols**, never composed at runtime. ([05](docs/05-ARCHITECTURE.md) §5.3)
6. **Any agent reading untrusted content is quarantined**: no credentials, no egress, output is typed data only. ([05](docs/05-ARCHITECTURE.md) §5.5)
7. **A proactive message that didn't change the next action is a defect** — and it is measured. ([07](docs/07-EVALUATION.md) §3)
8. **The monitor is independent of the actor.** The kill switch cannot be reached by the agents it governs. ([05](docs/05-ARCHITECTURE.md) §5.4)

---

## Next decision points

Listed in [04 §8](docs/04-UNIFICATION-VIABILITY.md#8-open-questions-that-genuinely-need-a-decision).
The load-bearing ones: which control plane, whether Personal Jarvis contributes code or
only design, where canonical memory lives, and which surface comes first.

---

*"Do not build a feature into Jarvis when it can be represented as a discoverable
capability behind an adapter."*
