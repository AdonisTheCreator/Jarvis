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
| [09 — Decision Log](docs/09-DECISIONS.md) | What's been decided, why, and what would reverse it |
| [10 — Control Plane Bake-Off](docs/10-CONTROL-PLANE-BAKEOFF.md) | The measured comparison that settles D1 |

Start with **04** if you want the argument, **01** if you want the vision, **02** if you
want the part nobody has built yet, **09** if you want current state.

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

## Where we are

| Decision | Status |
|---|---|
| **D1** Control plane — OpenClaw or Hermes | **Deferred to a measured bake-off.** Both are strong on opposite axes; learning loop and memory are the stated priority, so we measure rather than guess. Two-week timebox, tiebreak OpenClaw. [→ doc 10](docs/10-CONTROL-PLANE-BAKEOFF.md) |
| **D2** Personal Jarvis — code or design | **Audit first**, with the decision rule written before the audit runs so it can't be rationalised afterwards. |
| **D3** First proactive watch | **CI / deploy health.** Unambiguous threshold, real cost of missing it, trusted structured trigger input. |
| **D4** Where the learning loop lives | **Our core**, emitting portable `SKILL.md` drafts — forced by D1. If it lived in a control plane, the bake-off would be unrunnable. |

D4 is the one that shapes the code: deferring the control-plane choice *and* prioritising
the learning loop together mean neither memory nor procedural learning can be rented. The
"no vendor types in the core" invariant stops being aspirational and becomes load-bearing.

**Next up:** Phase 0 (core contracts and the safety spine), then Phase 0.5 (the audit and
the bake-off, in parallel).

---

*"Do not build a feature into Jarvis when it can be represented as a discoverable
capability behind an adapter."*
