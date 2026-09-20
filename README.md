# Jarvis

A personal AI operating layer: **one identity, many hands.**

One persistent assistant at the surface. Underneath, a small core we own — capability
router, policy engine, canonical memory, audit ledger, and a proactivity plane — dispatching
to interchangeable agent runtimes, devices and services.

Dedicated to God. See [`docs/00-DEDICATION-AND-CHARTER.md`](docs/00-DEDICATION-AND-CHARTER.md) —
the charter translates that dedication into seven binding engineering constraints.

---

## Where this stands

This repository holds the **research, architecture and offline contract prototype**.
The first executable milestone simulates implementation → review and cancellation;
it does not yet connect to live agents. **Hermes is our first prototype choice** (D9),
with Codex, Claude Code, Traycer and Claude Desktop integration work mapped in
[14 — Hermes-first milestone](docs/14-HERMES-FIRST-MILESTONE.md).

Run with Python 3.11+ (no third-party dependencies):

```bash
python -m jarvis.demo
python -m jarvis.demo --cancel
python -m unittest discover -s tests -v
```

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
| [11 — The Record](docs/11-THE-RECORD.md) | Deep memory as one execution ledger: capture, retention, forgetting, the subconscious |
| [12 — The Core Machine](docs/12-JARVIS-CORE-HARDWARE.md) | What the dedicated box is for, sized against the workload |
| [13 — Integration Triage](docs/13-INTEGRATION-TRIAGE.md) | How to explore constantly without the stack sprawling |
| [14 — Hermes-first Milestone](docs/14-HERMES-FIRST-MILESTONE.md) | Runnable offline prototype, integration paths, and gates to a spoken coding workflow |
| [15 — Voice, Models & App Connections](docs/15-VOICE-MODELS-AND-APP-CONNECTIONS.md) | Local transcription research, spoken model modes, phone/home devices and an integration pattern for our apps |
| [16 — Ten Acceptance Flows](docs/16-TEN-ACCEPTANCE-FLOWS.md) | Ten user-endorsed scenarios, feasibility, failure cases and first live acceptance targets |

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

**4. Deep memory and the audit ledger are the same object.**
Full-fidelity capture of every chat, subagent trace, reasoning step and file edit is one
append-only content-addressed event log with four read projections. The ledger already had to
be tamper-evident and runtime-independent for safety; memory inherits that integrity for free.
A year of every word the system produces is about a gigabyte — the ambition is cheap, and media
retention is the only real cost. ([11](docs/11-THE-RECORD.md))

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
9. **Forgetting works by destroying keys, not by rewriting history.** Per-subject encryption from the first write. ([11](docs/11-THE-RECORD.md) §6)
10. **The subconscious has no network egress, and recall is a scoped capability.** The archive is the highest-value target in the system. ([11](docs/11-THE-RECORD.md) §8)

---

## Where we are

| Decision | Status |
|---|---|
| **D1 / D9** Control plane — OpenClaw or Hermes | **Hermes-first prototype.** Production selection remains evidence-based. D9 supersedes the mandatory full bake-off prerequisite and automatic OpenClaw tiebreak. [→ doc 14](docs/14-HERMES-FIRST-MILESTONE.md) |
| **D2** Personal Jarvis — code or design | **Audit first**, with the decision rule written before the audit runs so it can't be rationalised afterwards. |
| **D3** First proactive watch | **CI / deploy health.** Unambiguous threshold, real cost of missing it, trusted structured trigger input. |
| **D4** Where the learning loop lives | **Our core**, emitting portable `SKILL.md` drafts — forced by D1. If it lived in a control plane, the bake-off would be unrunnable. |
| **D5** Deep memory vs. the audit ledger | **One object.** An append-only, content-addressed event log with four projections — Audit, Recall, Reconstruct, Consolidate. Built once, at safety grade. |
| **D6** The subconscious | **Retrieval and consolidation on idle time, not a fine-tune.** A fine-tune cannot honour `forget()`. No network egress, ever; recall is a scoped capability. |
| **D7** How to evaluate anything new | **Triage by the layer it wants to own.** Models and skills are free — explore constantly. Control planes and memory-owners are not. |
| **D8** Grok | **Add as a provider now.** The differentiated asset is realtime X search as a capability, not the model — and not the $3/hr voice API. |

Two of these shape the code more than the rest. **D4**: deferring the control-plane choice
*and* prioritising the learning loop together mean neither memory nor procedural learning can
be rented — "no vendor types in the core" stops being aspirational. **D5**: the event schema,
causal DAG and per-subject encryption have to exist before the first event is written, because
none of the three can be retrofitted onto an archive.

**Next up:** the supervised execution boundary and native worker adapters in
[doc 14](docs/14-HERMES-FIRST-MILESTONE.md), followed by Hermes text/voice integration.
The offline prototype does not satisfy the remaining Phase 0 production safety gates.

---

*"Do not build a feature into Jarvis when it can be represented as a discoverable
capability behind an adapter."*
