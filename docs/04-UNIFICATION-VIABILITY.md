# 04 — Can We Merge the Agent OSes? Viability Verdict

*The question from the brief: "I'm not sure it was fully aligned when it pitched the idea
of different agent OS as different agents — I'm thinking a more unified agentic stack that
could maybe merge these open source agent OS together to get the best of all worlds. Let's
check viability."*

---

## 1. Verdict, up front

**The instinct is right. The mechanism is wrong. There is a third option, and it is the
correct one.**

| Option | Viable? | Why |
|---|---|---|
| **A. Different agent OSes as different agents** (the draft's plan) | ❌ **No** | Stacks three control planes that each claim ownership of sessions, channels, skills, memory and scheduling. Produces duplicate routing, duplicate retries → duplicate side effects, three memory writers, permission inheritance across layers, and latency stacking. The draft names all of these as risks and then adopts the architecture that causes them. |
| **B. Merge the codebases into one unified agent OS** | ❌ **No** | You would be resolving two-to-three conflicting ownership models for six primitives, then maintaining that fork against upstreams that renamed themselves twice in a year. The cost is a permanent full-time job and the reward is a system nobody else can help you run. |
| **C. One control plane, interchangeable runtimes, portable capability artifacts, and a small core we own** | ✅ **Yes** | This is what "best of all worlds" actually looks like. It is also demonstrably what the ecosystem already does — see §3. |

The rest of this document is the evidence.

---

## 2. Why Option A fails — the three-router problem

The draft's stack is:

```
  Personal Jarvis  (Router-Brain: listens, decides, delegates)
        ↓
  OpenClaw         (Gateway: source of truth for sessions, routing, channels)
        ↓
  Hermes           (agent core: own gateway, memory, skills, cron, subagents)
        ↓
  Codex / Claude Code / computer-use
```

Every one of those first three layers is a **complete agent OS** with its own gateway,
channel set, skill format, memory store and scheduler (see `03-AGENT-OS-LANDSCAPE.md` §1).
Stacking them creates six concrete failures:

1. **Ownership ambiguity per primitive.** Who owns the canonical session — Jarvis or the
   OpenClaw gateway? The draft itself lists this as an open question and never answers it.
   It is not answerable while both are running; it is only resolvable by deletion.
2. **Duplicate side effects.** Three layers with independent retry logic over
   at-least-once transports. A retried "send the message" at layer 2 and layer 3 sends it
   twice. The draft flags this risk and proposes no fix.
3. **Latency stacking.** Voice → router reasons → gateway routes → agent core reasons →
   model. If every layer invokes an LLM to decide, wake-to-first-word blows past the
   ~1s budget that makes voice feel alive.
4. **Divergent memory.** Three frameworks with three memory systems writing user facts.
   Within a month you have three different answers to "what did we decide about X."
5. **Permission inheritance.** A coding worker reached through two parent runtimes
   inherits whatever the widest parent holds. The draft's own least-privilege principle is
   unenforceable across a stack whose layers each hold full credential sets.
6. **Upgrade churn, cubed.** Three fast-moving projects; any interface change anywhere
   breaks the chain.

**The tell is in the source document itself.** §8 contains a callout headed *"Avoid
architecture lasagna: do not make every request traverse Jarvis → OpenClaw → Hermes →
Letta → LangGraph → model."* And then §31's recommended stack does exactly that. The
warning was right; the architecture didn't follow it.

**The other tell:** Hermes ships an **OpenClaw migration importer** that pulls persona,
memories, skills, allowlists, messaging settings and API keys out of `~/.openclaw`. That
is what a *replacement* looks like. Nobody writes an importer for a system they intend to
sit on top of.

---

## 3. Why Option C works — the merge is already happening, one layer down

"Merge the agent OSes to get the best of all worlds" is a real and achievable goal. It
just happens at the **artifact and protocol layer**, not the process layer:

| Layer | Merge mechanism | Status |
|---|---|---|
| Tools | **MCP** — one tool speaks to every runtime | ~97M monthly SDK downloads; 10k–18k servers |
| Capabilities | **`SKILL.md` / agentskills.io** — one skill runs under OpenClaw *or* Hermes | Thousands in the OpenClaw registry; Hermes compatible |
| Agent↔agent | **A2A v1.0** — structured task delegation, sync/stream/async | Shipped early 2026 |
| Runtimes | **Agent-harness plugin SDK** — an external runtime owns the session; the control plane keeps channels, approvals, transcript | Proven in production by OpenClaw's Codex harness |
| Governance | MCP + A2A under the **Agentic AI Foundation** (Linux Foundation, ~190 orgs) | No single vendor controls the seams |

Write the capability once in a portable format and the underlying agent OS becomes a
*deployment detail*. That is the actual "best of all worlds": not running OpenClaw and
Hermes and Personal Jarvis simultaneously, but being able to **swap which one is running
without losing anything you built**.

The strongest existence proof is OpenClaw's Codex harness, whose published split is
exactly the contract we want:

> Codex owns the low-level agent session (model discovery, native thread resume, native
> tool continuation, native compaction, app-server execution). OpenClaw owns chat
> channels, session files, model selection, dynamic tools, approvals, media delivery and
> the visible transcript mirror.

One control plane. A foreign runtime owning the hard part. A clean seam. It already ships.

---

## 4. The recommended shape

```
                    ┌──────────────────────────────────────────┐
   SURFACES         │ room satellites · phone · glasses ·      │
   (nodes)          │ desktop · car · channels                 │
                    └──────────────────┬───────────────────────┘
                                       │
                    ┌──────────────────▼───────────────────────┐
   ★ JARVIS CORE    │  Identity · Capability Router ·          │   ← WE OWN THIS.
   (ours, small,    │  Policy Engine · Protocols ·             │     ~5k LOC.
    boring, stable) │  Canonical Memory · Audit Ledger ·       │     Never forked into
                    │  PROACTIVITY PLANE                       │     anyone's repo.
                    └──────────────────┬───────────────────────┘
                                       │
                    ┌──────────────────▼───────────────────────┐
   CONTROL PLANE    │  ONE of {OpenClaw | Hermes}              │   ← replaceable
   (theirs, one)    │  sessions · channels · node registry ·   │
                    │  skills · tool execution · cron          │
                    └──────────────────┬───────────────────────┘
                                       │
                    ┌──────────────────▼───────────────────────┐
   RUNTIMES         │ Claude Code · Codex · Hermes-as-runtime ·│   ← behind harness
   (many, swappable)│ computer-use · LangGraph (durable exec)  │     adapters
                    └──────────────────┬───────────────────────┘
                                       │
                    ┌──────────────────▼───────────────────────┐
   PERIPHERALS      │ MCP servers · Home Assistant · Tesla     │
                    │ Fleet · store APIs · shell · browser     │
                    └──────────────────────────────────────────┘
```

Three rules make this work:

**Rule 1 — One control plane. Exactly one.** Not one primary and one secondary. One.

**Rule 2 — One owner per capability class, written down.** The capability registry is the
document of record. Two providers for a capability is fine (with a scored fallback); two
*owners* is a bug.

**Rule 3 — The core is ours and stays small.** Router, policy, memory, ledger, proactivity.
It holds no vendor concepts. If every project in this document is abandoned, the core
survives and we rewrite adapters.

---

## 5. Which control plane?

| | **OpenClaw** | **Hermes Agent** |
|---|---|---|
| Ecosystem scale | 100k+ stars, ClawHub, thousands of registry skills | Smaller, newer, Nous-backed |
| Device/node model | **Strong** — nodes publish/withdraw skills on connect/disconnect; iOS/Android/macOS/headless | Weaker — messaging-first |
| Channel breadth | Very broad (10+ incl. iMessage, Matrix, Teams) | Broad (20+ platforms, incl. email) |
| External runtime ownership | **Agent-harness plugin SDK, proven with Codex** | Subagents; less evidence of foreign-runtime ownership |
| Memory | Persistent, session-scoped | **Strong** — 3-layer, FTS5 search, Honcho user modeling |
| Learning loop | No | **Yes** — autonomous skill creation + self-improvement (DSPy/GEPA) |
| Execution isolation | Host default, optional sandbox | **7 backends** incl. serverless-hibernating (Modal, Daytona) |
| Security posture | Explicit: untrusted inbound, DM pairing approval | Less documented |
| Migration pressure | — | **Imports from OpenClaw** (one-way) |

**Recommendation: OpenClaw as the control plane; Hermes attached as a *runtime* for
learned-procedure work, if and when we can show a task class where its learning loop
measurably beats a strong model over MCP.**

Reasoning: the node/device model and the harness SDK are the two things this project
cannot easily rebuild, and OpenClaw has both. Hermes' differentiators (memory layers,
skill learning) are *patterns we can implement in our own core* — and must, since memory
is a core-owned concern (Rule 2). Note also that migration runs OpenClaw → Hermes, which
means starting on OpenClaw keeps that door open; starting on Hermes closes it.

**Where Personal Jarvis lands:** not as the crown. Harvest its two genuinely
differentiated assets — the **voice pipeline with the sub-second acknowledge path** and
the **Worker–Critic retry loop** — and run it as a *voice node* on the control plane, or
reimplement the pipeline directly. Do not let a second router into the stack.

---

## 6. Hard truths worth stating plainly

**6.1 This system has the lethal trifecta wide open, by design.** Private data (email,
repos, calendar, home, car), untrusted content (web, inbound mail, PR comments, app
reviews), and exfiltration vectors (send message, outbound HTTP, publish, purchase). All
three, permanently, on purpose. That is not a reason not to build it — it is the reason
the Policy Engine, Untrusted Ingest Rule and Audit Ledger are Phase 0 and not Phase 8. A
proactive agent cannot be retrofitted safe.

**6.2 Two components in the proposed stack rewrite themselves.** Personal Jarvis is
self-modifying; Hermes self-improves its own skills and, in the self-evolution repo,
its own prompts and code via DSPy/GEPA. Both are legitimately valuable. Both must write to
**drafts** that are diffed, approved and revertible before touching a privileged running
system. Never live self-modification on the machine holding the credentials.

**6.3 "Best of all worlds" has a hidden cost, and it isn't integration effort.** It is
ownership ambiguity. Each additional runtime multiplies the number of places a piece of
state can live. Budget the *decision* cost, not the *wiring* cost.

**6.4 The hardware order in the draft is right and should be defended.** Prove the
software on existing machines first. Every device — glasses, satellites, core box, car —
is a node behind an adapter. None of them should be bought to find out whether the
architecture works.

**6.5 The blueprint's own best line should be the project's motto**, and the draft
violates it: *"Do not build a feature into Jarvis when it can be represented as a
discoverable capability behind an adapter."*

---

## 7. What we should build first (and it isn't an integration)

The highest-value thing to build is not a connection between two agent OSes. It is the
**Proactivity Plane** (`02-PROACTIVITY-RESEARCH.md`), because:

- It is the actual product. "One intelligence, many hands" is a plumbing statement; *"it
  told me the thing I needed before I asked, and never told me anything else"* is the
  experience.
- **Nobody has built it well.** ChatGPT Pulse, Gemini Proactive Assistance and the
  reported Anthropic work are all scheduled overnight digests — trigger classes 3.1 + 3.6
  only. Live, well-timed, correctly-routed interruption is open ground.
- It is where the JARVIS character study is *ahead of the market*: the three-trigger
  policy, modality routing by cognitive load, and Protocols are design ideas the shipping
  products don't have.
- It is small, it is ours, and it is portable across every control plane in this document.

---

## 8. Open questions that genuinely need a decision

1. **Control plane**: OpenClaw (recommended) or Hermes? Reversible early, expensive later.
2. **Does Personal Jarvis code get used at all**, or do we take the voice-pipeline design
   and implement it directly as a node? (Adopting the code means adopting a self-modifying
   dependency in the voice path.)
3. **Where does canonical memory live** — our core (recommended, per Rule 2) or the control
   plane's store with our core as index?
4. **What is the first proactive watch?** It should be something with an unambiguous
   threshold, a real cost of missing it, and no untrusted input. Candidates: CI/deploy
   health, calendar conflict, vehicle charge state.
5. **Which surface first** — desktop voice, phone, or room satellite? This determines the
   node protocol work.
