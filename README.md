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
| [11 — The Record](docs/11-THE-RECORD.md) | Deep memory as one execution ledger: capture, retention, forgetting, the subconscious |
| [12 — The Core Machine](docs/12-JARVIS-CORE-HARDWARE.md) | What the dedicated box is for, sized against the workload |
| [13 — Integration Triage](docs/13-INTEGRATION-TRIAGE.md) | How to explore constantly without the stack sprawling |
| [14 — The Decision Layer](docs/14-THE-DECISION-LAYER.md) | Jev, adjudicated retention, cross-provider critics |
| [15 — Session Control](docs/15-SESSION-CONTROL.md) | Phone→desktop dispatch, the coding command centre, voice bridging |
| [16 — Model Topology](docs/16-MODEL-TOPOLOGY.md) | Why there is no "main Jarvis model" |
| [17 — Routing Policy](docs/17-ROUTING-POLICY.md) | Spoken policy authorship, the Model Cabinet, and the decision layer as a rule factory |
| [18 — Personal Jarvis Audit](docs/18-PERSONAL-JARVIS-AUDIT.md) | D2 findings against commit `888df0c` |

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
11. **Jev decides; the Policy Engine authorizes.** A calibrated probability is never an approval. ([14](docs/14-THE-DECISION-LAYER.md) §5)
12. **Low confidence escalates to the more thorough path, never the cheaper one.** ([14](docs/14-THE-DECISION-LAYER.md) §3)
13. **Write the rule when the input is structured and the question is decidable.** Jev is for judgments over messy state — its edge is knowing when it doesn't know. ([14](docs/14-THE-DECISION-LAYER.md) §10)
14. **Remote awareness before remote control.** A blocked session you hear about beats a session you can drive. ([15](docs/15-SESSION-CONTROL.md) §1)
15. **Generate with the LLM, validate with Jev, execute with a rule.** Wherever free text becomes structure. ([17](docs/17-ROUTING-POLICY.md) §3)
16. **Narrate the inferred reason; act only on the stated one.** ([17](docs/17-ROUTING-POLICY.md) §6)

---

## The code

Phase 0 is built and tested: `src/jarvis_core/`, 304 tests, stdlib-only except
`cryptography`. The invariant that no core module may import a vendor type is
**asserted by the test suite**, not merely documented.

```
ids · errors · autonomy · capability · backend · idempotency · killswitch
quarantine · memory · router · policy/ · record/ · decide/
```

Start at `CLAUDE.md` for orientation, or `docs/09-DECISIONS.md` for why anything
is the way it is.

## Where we are

| Decision | Status |
|---|---|
| **D1** Control plane — OpenClaw or Hermes | **Deferred to a measured bake-off.** Both are strong on opposite axes; learning loop and memory are the stated priority, so we measure rather than guess. Two-week timebox, tiebreak OpenClaw. [→ doc 10](docs/10-CONTROL-PLANE-BAKEOFF.md) |
| **D2** Personal Jarvis — code or design | **Audit first**, with the decision rule written before the audit runs so it can't be rationalised afterwards. |
| **D3** First proactive watch | **CI / deploy health.** Unambiguous threshold, real cost of missing it, trusted structured trigger input. |
| **D4** Where the learning loop lives | **Our core**, emitting portable `SKILL.md` drafts — forced by D1. If it lived in a control plane, the bake-off would be unrunnable. |
| **D5** Deep memory vs. the audit ledger | **One object.** An append-only, content-addressed event log with four projections — Audit, Recall, Reconstruct, Consolidate. Built once, at safety grade. |
| **D6** The subconscious | **Retrieval and consolidation on idle time, not a fine-tune.** A fine-tune cannot honour `forget()`. No network egress, ever; recall is a scoped capability. |
| **D7** How to evaluate anything new | **Triage by the layer it wants to own.** Models and skills are free — explore constantly. Control planes and memory-owners are not. |
| **D8** Grok | **Add as a provider now.** The differentiated asset is realtime X search as a capability, not the model — and not the $3/hr voice API. |
| **D9** The decision layer | **Adopt Jev.** Twelve bounded-choice decision points across the architecture had no mechanism. Typed answers with calibrated probabilities in 70–500 ms for under $50/year. Retention becomes per-item adjudication at 30 days. |
| **D10** Critics | **Cross-provider, fail-closed, hard round cap.** A reviewer sharing the builder's failure modes is not a reviewer. |
| **D11** Generated architecture claims | **Fail-closed validation and evidence-linked claims.** A claim carries its evidence or it doesn't ship. |
| **D12** Control plane | **Hermes.** Resolves D1. The bake-off is re-purposed from selection to validation; Class A and D stay gates. |
| **D13** Session control | **One `session.*` family, three adapter tiers.** Remote awareness before remote control. The harnesses already emit the Record; the Agent SDK's approval callback is where policy plugs in. |
| **D14** Model topology | **No main model.** Five roles — voice front, decision layer, subconscious, reasoning, specialists. Identity lives in the core, not in a vendor. |
| **D15** Grok Bot | **A worker for authenticated web tasks, later — not a competitor.** It cannot have your Record, your policy, your devices, or the ability to forget. |
| **D16** God's Eye View | **Adopt as a visual output surface, not a data source.** Use a real weather API for weather. Situational awareness about places, never people. |
| **D17** Routing policy | **Spoken, persistent, position-scoped.** And the reframe: the decision layer *manufactures* rules from its own decisions — it spends its life putting itself out of a job. |
| **D2** (update) | **Static audit clean.** Forced-draft skill lifecycle, no phone-home, keyring secrets. One measurement — wake-to-ack on our hardware — from closing. |

Two of these shape the code more than the rest. **D4**: deferring the control-plane choice
*and* prioritising the learning loop together mean neither memory nor procedural learning can
be rented — "no vendor types in the core" stops being aspirational. **D5**: the event schema,
causal DAG and per-subject encryption have to exist before the first event is written, because
none of the three can be retrofitted onto an archive.

**D12** settles the control plane: **Hermes**. One consequence worth holding onto — D4 already
puts memory and the learning loop in our core, and those are Hermes' headline features. So
Hermes is adopted for its control plane (sessions, channels, seven execution backends, cron),
with its learning loop as a continuous benchmark against ours rather than the system of record.

**D9** changed what's affordable: a decision model at $0.042/M input
makes per-item judgment free, so "pick a retention policy" becomes "decide per item, forever."
The hard boundary holds — **Jev decides, the Policy Engine authorizes**; a calibrated
probability is not an approval.

**Next up:** Phase 0 (core contracts, the Record, and the safety spine), then Phase 0.5 (the
Personal Jarvis audit and the control-plane bake-off, in parallel).

---

*"Do not build a feature into Jarvis when it can be represented as a discoverable
capability behind an adapter."*
