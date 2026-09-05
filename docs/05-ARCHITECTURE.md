# 05 — Refined Architecture

> **2026-09-05, D9:** Hermes is the first prototype control plane. Doc 14 brings
> the coding workflow forward as a staged fixture experiment. Core ownership of
> memory means portable approved knowledge; Hermes may generate learning proposals
> before a custom extraction engine exists. This document describes the target
> architecture, not the capabilities of the current offline simulation.

*This supersedes §8–§12 and §24 of the source blueprint. It keeps the good parts
(capability routing, adapter contract, memory classes, risk tiers) and adds the four
things that were missing: the Proactivity Plane, Protocols, the Untrusted Ingest boundary,
and an audit ledger independent of the agents it governs.*

---

## 1. Layers

| L | Layer | Owner | Replaceable? |
|---|---|---|---|
| **L0** | **Surfaces / Nodes** — room satellites, phone, glasses, desktop, car, chat channels | Vendors + control plane | Yes, individually |
| **L1** | **Presence** — wake, VAD, STT, barge-in, TTS, session continuity across nodes | Control plane + voice node | Yes |
| **L2** | **★ Jarvis Core** — Identity, Capability Router, Policy Engine, Protocols, Canonical Memory, Audit Ledger, **Proactivity Plane** | **Us** | **No — this is the project** |
| **L3** | **Control Plane** — exactly one of {OpenClaw \| Hermes}: sessions, channels, node registry, skills, tool execution, cron | Vendor | Yes (that's the point) |
| **L4** | **Runtimes** — Claude Code, Codex, Hermes-as-runtime, computer-use, LangGraph (durable execution) | Vendors | Yes, behind harness adapters |
| **L5** | **Peripherals** — MCP servers, Home Assistant, Tesla Fleet, store APIs, shell, browser | Vendors | Yes |

**Design invariant:** L2 contains no vendor concepts. No file in the core imports an
OpenClaw or Hermes type. If it does, it belongs in an adapter.

---

## 2. Presence layer (L1)

Fixed pipeline, swappable providers — the Personal Jarvis design is right here and worth
copying directly:

```
  wake word (on-device) → VAD → STT → Core route → fast ACK (<1s) → work → TTS
                                            └── heavy work detaches ──┘
```

Requirements:
- **Wake detection is local, always.** microWakeWord on satellites and phones;
  openWakeWord server-side for low-power devices that only stream. Never cloud wake.
- **Fast-acknowledge path.** Acknowledge intent inside ~1s on a small/local model, then
  detach. The acknowledgement must be *specific* ("Starting the build") not generic
  ("Working on it") — a generic ack hides misrouting until it's expensive.
- **Barge-in is first-class.** "Stop," "no, the other repo," "don't send it" must reach a
  running task and take effect. This is a *cancel/redirect* API on the router, not a TTS
  feature. Untested barge-in is the single most common way voice assistants become unsafe.
- **Any node, one session.** R2 — a sentence started in the kitchen finishes in the office.
- **Audio carries decisions, not logs.** R11.

---

## 3. Proactivity Plane (L2) — the piece the blueprint lacks

Full specification in `02-PROACTIVITY-RESEARCH.md`. Structure:

```
  ┌── 3.1 WATCH REGISTRY ──────────────────────────────────────────┐
  │  every watch: id, trigger class, predicate, dwell, criticality, │
  │  owner, created_by, last_fired, health   ← user-enumerable      │
  └────────────────────────┬───────────────────────────────────────┘
                           │  fires
  ┌────────────────────────▼───────────────────────────────────────┐
  │  3.2 EVALUATOR — salience score; dedupe against delivery ledger │
  └────────────────────────┬───────────────────────────────────────┘
                           │  candidate
  ┌────────────────────────▼───────────────────────────────────────┐
  │  3.3 OUTPUT ROUTER — interruptibility × urgency → modality      │
  │  {audio | HUD | push | desktop card | silent log | digest}      │
  │  + interrupt budget enforcement                                 │
  └────────────────────────┬───────────────────────────────────────┘
                           │  delivery
  ┌────────────────────────▼───────────────────────────────────────┐
  │  3.4 PROMOTION LADDER — L0 observe → L1 digest → L2 notify →    │
  │  L3 propose → L4 act+tell → L5 act.  Earned slowly, lost fast.  │
  └─────────────────────────────────────────────────────────────────┘
```

Non-negotiables:
- **Unprompted audio requires one of the three JARVIS triggers** (R4): registered
  threshold breach, completion of delegated work, or a decision-material consequence.
- **Interrupt budget** on high-cost channels; over-budget candidates degrade a level
  rather than queue. Only user-marked `critical` watches bypass.
- **Every delivery is logged with an outcome** so interruption precision (R5) is
  measurable from day one.
- **Watch health is surfaced.** A dead watch must raise (R3). Silent watch death is the
  failure that destroys trust in everything else.

---

## 4. Canonical Memory (L2)

One owner per class (Rule 2 of doc 04). Human-readable and hand-editable wherever
possible — the Personal Jarvis Markdown-wiki instinct is correct and should be kept.

> **Revised by D5:** canonical memory is a *derived, curated* store over the Record (§8).
> The Record is ground truth — what happened. Memory holds the conclusions, with provenance
> pointing back at the source events. That is what makes a memory correctable: you can always
> re-derive it.

| Class | Contents | Owner | Written by |
|---|---|---|---|
| `identity` | Persona, tone, values, user-set boundaries | **Core** | Human only |
| `user_facts` | Facts & preferences, each with provenance + timestamp + confidence | **Core** | Core, on approval |
| `project` | Decisions, specs, repos, artifacts, open threads | **Core** | Core + runtimes via API |
| `episodic` | What happened; searchable, summarized, time-aware | **Core** (index) | Core |
| `procedural` | "How we do this" — skills/workflows | **`SKILL.md` files** | Drafted by agents, approved by human |
| `operational` | Live missions, device state, sessions, locks, approvals | **Control plane** | Control plane |

Rules:
- **Provenance is mandatory.** Every fact records where it came from and when. A fact with
  no provenance is a bug, not a memory.
- **Forgetting is a first-class API.** `forget(fact_id)` and `forget(source)` must work,
  including through derived summaries.
- **Runtimes do not write memory directly.** They emit proposals; the core writes.
- **Sleep-time consolidation** (R9): a background agent with a *narrower* tool set and a
  cheaper model consolidates episodic → user_facts during idle windows, and writes to a
  review queue, not straight to canonical.

### 4.1 The procedural learning loop (core-owned — decision D4)

Learning "how we do this" is **ours**, not rented from a control plane. Forced by D1: if
the loop lived inside OpenClaw or Hermes, switching control planes would mean abandoning
it, and the bake-off in doc 10 would be unrunnable.

```
  completed task ─▶ execution trace
                        │
                        ▼  (sleep-time: cheap model, narrow tools)
              candidate skill extraction
                        │
                        ▼
                  SKILL.md  DRAFT ──▶ human diff & approve ──▶ skills/
                                                                  │
                                          any control plane loads it, unchanged
```

Rules:
- **Drafts only.** R13 applies to our own learning loop exactly as much as to a vendor's.
  Nothing writes a live skill into a running privileged system.
- **Portable format.** `SKILL.md` / agentskills.io — the one capability artifact both
  control-plane candidates already load.
- **Extraction is sleep-time work**: narrower tool set than the foreground agent, cheaper
  model, output to a review queue.
- **Trace-driven, not outcome-driven.** The interesting signal is *why* a step failed, not
  merely that it did. Hermes' self-evolution work (DSPy + GEPA over execution traces) is
  the right quality bar to aim at — a technique to adopt, not a dependency to take.
- A learned skill that misfires when a parameter changes is worse than no skill. Skill
  robustness is measured explicitly (doc 10, task C2).

---

## 5. Policy Engine (L2)

### 5.1 Autonomy classes
Extends the blueprint's tiers. Class is a property of the **capability**, never of the
agent.

| Class | Examples | Default |
|---|---|---|
| **A0 Observe** | Read status, search, summarize, check battery | Automatic; logged |
| **A1 Reversible personal** | Lights, media, precondition car, create draft/worktree | Automatic once enabled |
| **A2 External low-impact** | Routine message, calendar event, open a ride request | Ask, until the routine is promoted |
| **A3 Financial / public / physical access** | Purchase, publish, unlock doors, change access control | **Protocol + explicit confirm + strong auth** |
| **A4 Safety-critical / unsupported** | Vehicle motion control, bypassing safety systems, unrecoverable deletion | **Blocked. No override path.** |

### 5.2 Approval tokens
An approval binds to **(action, target, exact parameters, expiry, single-use)**. Never to
an agent, never to a session, never open-ended. "Approve this agent" is not expressible in
the schema — deliberately.

### 5.3 Protocols (R8) — pre-declared high-consequence macros
The JARVIS design pattern, made real. Any A3-class action **must** exist as a Protocol:

```yaml
protocol: leaving_in_fifteen
declared_by: human
reviewed_on: 2026-08-25
steps:
  - vehicle.read_state          # A0
  - vehicle.precondition        # A1
  - vehicle.set_charge_limit    # A1  (fixed param: 80)
  - calendar.check_conflicts    # A0
blast_radius: "cabin climate + charge limit; no locks, no navigation, no spend"
auth_required: voice_match
confirm: none                   # every step is A1 or below
expiry: null
undo: vehicle.stop_climate
```

Properties: fixed parameter set, written blast radius, required auth level, confirmation
phrase, expiry, declared undo (or explicit `undo: none`, which forces `confirm: explicit`).

**The agent may invoke a Protocol. The agent may never compose a new A3 sequence at
runtime.** This removes in-the-moment model judgment from every dangerous path.

### 5.4 Kill switch and independence (R12)
- Local, immediate, model-independent. Halts autonomous execution, revokes live sessions,
  disables all watches.
- **Runs outside every agent runtime it governs.** Not a tool. Not reachable by an agent.
  Physically separate process, ideally separate machine from L3/L4.
- The audit ledger and policy engine share this property. "The assistant is down" must
  never imply "the guardrails are down."
- **Tested on a schedule**, like a fire alarm. An untested kill switch is decorative.

### 5.5 The Untrusted Ingest Rule
> Any agent that reads untrusted content is quarantined: **no private-data credentials, no
> outbound network except to the router, output restricted to a typed `Proposal`** — never
> a tool call, never an instruction.

This breaks the lethal trifecta per task rather than trying to make models
injection-resistant, which is not currently achievable. See `02-PROACTIVITY-RESEARCH.md` §7.

---

## 6. Capability Router (L2)

### 6.1 Capability descriptor
```yaml
capability: vehicle.navigate
provider: TeslaFleetAdapter
device: tesla.model_y
permissions: [vehicle_location, vehicle_commands]
autonomy_class: A1
reversible: true
undo: vehicle.clear_navigation
privacy_class: personal_location
confirmation: none_if_destination_unambiguous
availability: online          # health-checked
latency_p50_ms: 1400
cost_per_call: 0
outputs: [car_navigation, phone, glasses]
fallback: [phone_navigation]
idempotency: destination_hash
```

### 6.2 Backend adapter interface
The blueprint's interface, corrected — `execute` must take an idempotency key, and
`estimate` must be cheap enough to call on every route:

```ts
interface AgentBackend {
  id: string
  capabilities: Capability[]
  permissions: PermissionProfile
  health(): HealthStatus
  estimate(task): { cost, latencyMs, confidence }      // no LLM call
  execute(task, ctx, idempotencyKey): TaskHandle
  stream(taskId): EventStream
  status(taskId): TaskStatus
  interrupt(taskId, instruction): Result               // barge-in target
  resume(taskId): Result
  cancel(taskId): Result
  compensate(taskId): Result | NotSupported            // declared undo
}
```

### 6.3 Routing
Score, don't branch: `capability match × permission fit × historical success rate ×
health × (1/latency) × (1/cost) × privacy fit × user preference`. Explainable in debug
mode; silent in normal conversation.

**Routing must not require an LLM call in the common path.** A registry lookup plus a
score is microseconds; a model call is hundreds of milliseconds and is how latency
stacking starts.

### 6.4 Idempotency
Every side-effecting call carries a key derived from (capability, target, params, logical
occasion). Enforced at the adapter boundary. This is what prevents at-least-once delivery
plus multi-layer retries from producing duplicate sends, purchases, deletes and commits.

---

## 7. Bystander and privacy policy (charter commitment 4)

Enforced, not aspirational:
- On-device wake detection only; raw audio never leaves a node pre-wake.
- Visible capture indicator whenever a camera or mic is live.
- Raw audio/video buffers are short-lived and never persisted without an explicit act.
- **No silent identification of any person**, ever — not bystanders, not known contacts.
- POV imagery is stored only on an explicit "remember this," and is listed in a
  user-reviewable capture log.
- One-word command pauses sensing and erases the recent buffer, on every node.
- Guests can ask what is recording and get a truthful, specific answer.

---

## 8. The Record and its projections (L2)

> **Revised by decision D5.** The Audit Ledger and the deep-memory store are **one object**:
> a single append-only, content-addressed event log with four read projections. Full spec in
> [`11-THE-RECORD.md`](11-THE-RECORD.md).

Every action records: user utterance (or trigger id) → interpreted intent → selected
capability → parameters → policy decision → approval event (if any) → backend → result →
compensating action available/taken. Plus, at the same fidelity: subagent transcripts,
reasoning, every file edit, and every proactive delivery and its outcome.

| Projection | Question | Consumer |
|---|---|---|
| **Audit** | Why did you do that, under what authority? | Policy engine, security review (R12) |
| **Recall** | What happened, what did we decide, how do we do this? | Foreground agent, the user |
| **Reconstruct** | Put the world back the way it was at T | Rollback, checkpoints, forensics |
| **Consolidate** | What's worth keeping, and what did we learn? | Subconscious, sleep-time compute (D4) |

Append-only. Content-addressed. Causally linked as a DAG, not a flat transcript — with
subagents running in parallel, a linear log is a lie. Independent of the runtimes (R12).
Encrypted per subject so that `forget()` works by key destruction rather than by rewriting an
append-only log (D5). Readable without exposing secrets, because redaction happens at write
time.

This is what makes "explain why you did that" answerable, and it is what makes the whole
system debuggable when something goes wrong at 3am with nobody watching.

---

## 9. What we are explicitly *not* building

- A second router. (Personal Jarvis becomes a node or a design reference, not a crown.)
- A phone OS. Android's `VoiceInteractionService` is the correct ladder rung; a GrapheneOS
  fork requires a capability Android genuinely cannot provide, which we have not found.
- Vehicle motion control. Tesla Fleet API does not expose steering/throttle/braking, and
  `remote_start_drive` authorizes keyless driving — it does not drive. A4. Blocked.
- Live self-modification of a privileged running system (R13).
- Any engagement metric.
