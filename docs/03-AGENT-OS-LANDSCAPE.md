# 03 — Agent OS Landscape: Verified Findings

*Verification pass run 2026-08-25 against project repos, official docs and current
coverage. This corrects and extends the source blueprint. Claims are marked
**[verified]** (confirmed against a primary or strong secondary source),
**[reported]** (secondary sources only), or **[unverified]**.*

---

## 1. The convergence nobody in the draft noticed

Read side by side, OpenClaw, Hermes and Personal Jarvis are not complementary layers.
They are three implementations of **the same six primitives**:

| Primitive | OpenClaw | Hermes Agent | Personal Jarvis |
|---|---|---|---|
| Control plane / process | Gateway (sessions, tools, events, channels) | Gateway (separate process, unified messaging) | Router-Brain + EventBus |
| Surfaces / channels | WhatsApp, Telegram, Slack, Discord, Signal, iMessage, Google Chat, Teams, Matrix… | Telegram, Discord, Slack, WhatsApp, Signal, Email, CLI (20+ platforms) | Desktop, browser, Telegram, Discord, telephony |
| Extension format | Skills (`SKILL.md`) + tools + plugin SDK | Skills (agentskills.io-compatible) + plugins | Harnesses + MCP |
| Execution backends | Host + optional sandbox; agent-harness plugins | 7 terminal backends: local, Docker, SSH, Singularity, Modal, Daytona, Vercel Sandbox | Claude Code, Codex CLI, Open Interpreter, Python, MCP remote, computer-use |
| Memory | Persistent memory + sessions | 3-layer (working / episodic / semantic-skill), FTS5 session search, Honcho user modeling | Markdown knowledge wiki, shared across channels |
| Scheduler | Built-in cron | Built-in cron with cross-platform delivery | Missions + critic loop |

**They are substitutes, not layers.** The decisive evidence:

> **Hermes' setup wizard automatically detects `~/.openclaw` and offers to migrate** —
> importing persona files, memories, skills, command allowlists, messaging settings, API
> keys and workspace instructions. **[verified — Hermes README]**

You do not write a migration importer for a system you intend to run *underneath* you.
That is a replacement path. The blueprint's plan to run Personal Jarvis **on top of**
OpenClaw **on top of** Hermes stacks three control planes that each expect to own
sessions, channels, skills, memory and scheduling.

---

## 2. Project-by-project

### 2.1 OpenClaw — the strongest control-plane candidate **[verified]**
- Self-hosted **Gateway** as local control plane for sessions, tools, events, channel
  connections; operable via Control UI, CLI and TUI.
- **Nodes**: device-local companion apps adding voice, Canvas, camera, screen and
  device-local actions; a connected headless node **publishes its own skills into the
  agent's skill list while connected and withdraws them on disconnect** — a genuinely
  well-designed capability-presence model, and exactly what the "distributed presence"
  section of the blueprint needs.
- **Security posture is explicit and correct**: inbound messages treated as untrusted;
  unknown DM senders require pairing approval (`openclaw pairing approve <channel> <code>`);
  tools run on host by default with optional sandboxing.
- **Scale**: surpassed 100k+ GitHub stars in early 2026; ClawHub marketplace; the
  community skills registry is in the thousands (VoltAgent's curated set cites 5,400+
  filtered from the official registry). **[reported]**
- Lineage: formerly Clawdbot / Moltbot. Node 22.22.3+/24.15+/25.9+/26 recommended.

**Agent-harness plugin SDK — the key finding.** OpenClaw supports external runtimes
owning the low-level agent session. In the official Codex harness:

> Codex owns model discovery, native thread resume, native tool continuation, native
> compaction and app-server execution. **OpenClaw still owns chat channels, session
> files, model selection, dynamic tools, approvals, media delivery, and the visible
> transcript mirror.** **[verified — OpenClaw plugin docs]**

Their stated design rule is worth adopting verbatim: *if OpenClaw owns the surface it can
run normal plugin hooks; if the native runtime owns the surface it needs runtime events or
native hooks; if the native runtime owns canonical thread state, OpenClaw mirrors and
projects context rather than rewriting unsupported internals.*

This is the proof that "one control plane, interchangeable runtimes" works in practice —
and it is *also* the proof that the control plane should be singular.

### 2.2 Hermes Agent (Nous Research) — the strongest cognition/learning candidate **[verified]**
- Positioning: "the agent that grows with you." Closed learning loop: creates skills from
  experience, improves them during use, nudges itself to persist knowledge, searches its
  own past conversations, builds a deepening user model across sessions.
- **Three-layer memory** (working / episodic / semantic-skill) + FTS5 session search with
  LLM summarization for cross-session recall + Honcho dialectic user modeling.
- **Seven terminal backends** including serverless-persistent ones (Daytona, Modal) that
  hibernate when idle and wake on demand — relevant to cheap always-on watchers.
- Subagent spawning for parallel workstreams; Python scripts calling tools over RPC to
  collapse multi-step pipelines into low-context turns.
- Cron scheduler with delivery to any platform.
- Separate `hermes-agent-self-evolution` repo: DSPy + GEPA optimizing skills, prompts and
  code by reading execution traces. **[verified]** — powerful, and squarely R13 risk class.

### 2.3 Personal Jarvis — real, useful, but *not* the top of the stack **[verified]**
- Real project (`PersonalJarvis/PersonalJarvis`, also on PyPI as `personal-jarvis`).
- Self-described as a **voice-driven meta-orchestrator**, not a voice assistant: "a fast
  Router-Brain that listens, decides and delegates," with heavy work to interchangeable
  harnesses (Claude Code, Codex CLI, MCP, computer-use) that run isolated, get reviewed by
  a critic, and report back.
- Layered architecture with a typed immutable EventBus; higher layers reach lower layers
  only through protocols. Provider-agnostic (Gemini/Claude/OpenAI/OpenRouter). Runs
  headless→full voice desktop. **Self-modifying** (R13 risk class).
- **The problem**: it is a *router*. Putting it above OpenClaw creates router-over-router.
  Its genuinely differentiated asset is the **voice pipeline and fast-acknowledge path**
  (wake → VAD → STT → route → ack in <1s → TTS), plus the Worker–Critic loop.

**Assessment**: harvest the voice pipeline design and the critic loop; do not adopt it as
the crown. If we use the code, use it as a **voice node** attached to the control plane —
not as the layer the control plane reports to.

### 2.4 Home Assistant — the mature physical layer **[verified]**
- Ships **"Hey Jarvis"** as a stock wake word alongside "Okay Nabu" and "Hey Mycroft."
- **microWakeWord** (Kevin Ahrendt) runs on-device on ESPHome satellites *and* in the
  Android companion app — works with the phone locked and the app backgrounded.
  **openWakeWord** runs server-side for low-power satellites that only stream audio.
- Automations are mature trigger-class 3.3 threshold watchers. This is the one component in
  the whole stack that is genuinely production-grade and battle-tested at scale.

### 2.5 Supporting cast
- **LangGraph** — durable execution, checkpointing, resumability, HITL interrupts,
  namespaced long-term store with semantic search, platform cron. Correct use: the
  *durable-execution substrate* for long-lived proactive work (§8 of doc 02). Incorrect
  use: as the persona or a second router. **[verified]**
- **LangChain Agent Inbox** — inbox UX for HITL agents; the three patterns (notify /
  question / review) are the right vocabulary for our promotion ladder. **[verified]**
- **Letta / MemGPT** — OS-inspired tiered memory (core/recall/archival) plus **sleep-time
  compute**: a background agent sharing memory blocks with the foreground agent, narrower
  tools, cheaper model, ~5× less test-time compute for equal accuracy. Adopt the *pattern*
  regardless of whether we adopt the *product*. **[verified]**
- **Traycer** — desktop orchestration for parallel CLI coding agents (harness ids:
  `claude`, `codex`, `opencode`, `traycer`, `cursor`), worktree ops, agent-to-agent
  messaging, CLI for automation. Legitimate for the software-engineering command centre.
  **[verified]**
- **VisionClaw** (`Intent-Lab/VisionClaw`) — real. Meta Wearables **DAT SDK** (iOS +
  Android) + **Gemini Live API** for realtime multimodal + optional OpenClaw for actions.
  Note the actual split: Gemini Live handles see/hear/converse and *hands off* to OpenClaw
  for tool execution. **[verified]** This is a working reference implementation of exactly
  the "sensor node → control plane" pattern we want.

---

## 3. The protocol layer — where "merging" is actually happening

The real convergence is not in codebases. It is in three artifacts:

| Protocol | Role | Adoption |
|---|---|---|
| **MCP** | Agent ↔ tools (vertical) | ~97M monthly SDK downloads; 10k–18k active servers **[reported]** |
| **A2A** | Agent ↔ agent (horizontal) | v1.0 shipped early 2026; async/streaming task delegation **[reported]** |
| **`SKILL.md` / agentskills.io** | Portable capability packaging | OpenClaw registry (thousands); Hermes compatible **[verified]** |

Both MCP and A2A now sit under the **Agentic AI Foundation** (Linux Foundation), ~190
member orgs including Anthropic, Google, OpenAI, Microsoft, AWS — no single vendor
controls either. **[reported]**

**This is the answer to "merge the agent OSes."** You don't merge the runtimes; you write
capabilities in the portable formats, and the runtimes become swappable. A skill written
as `SKILL.md` runs under OpenClaw *or* Hermes. A tool exposed over MCP is reachable from
every runtime in this document. That is the "best of all worlds" — obtained by *not*
running all the worlds at once.

---

## 4. Corrections to the source blueprint

| Blueprint claim | Finding |
|---|---|
| Personal Jarvis = experience layer *above* OpenClaw *above* Hermes | Three control planes stacked. Hermes ships an OpenClaw **migration importer** — they are substitutes. **Pick one.** |
| "Hermes = adaptive cognition backend, OpenClaw = control plane" | Both are full agent OSes with their own gateway, channels, skills, memory and cron. The split is not natural; it must be *imposed* and defended. |
| Proactivity is Phase 6 | Proactivity is the product. The digest is Phase 1. See doc 02. |
| "Harden & daily-drive" is Phase 8 | The policy engine, audit ledger and kill switch are Phase 0. A proactive agent with the lethal trifecta open cannot be retrofitted safe. |
| Capability map "GREEN" = ready | Correctly caveated in the source, but worth restating: GREEN means *the platform API exists*, not that an adapter exists. Every GREEN row is still weeks of work. |
| LangGraph "only if needed" | Needed — but as durable execution for proactive work, not as an orchestration alternative. Right conclusion, wrong reason. |
| Letta as a memory fallback | The *sleep-time compute pattern* is worth adopting immediately regardless of Letta the product. |
| Missing entirely | Proactivity plane; interruptibility/modality routing; the Untrusted Ingest Rule; Protocols as a construct; idempotency; the promotion ladder. |

---

## 5. Ecosystem risk to price in

All three candidate control planes are young, fast-moving, single-vendor-ish open-source
projects. OpenClaw was renamed twice (Clawdbot → Moltbot → OpenClaw) inside about a year.
Interfaces will churn.

**This is the strongest argument for the architecture in doc 05**: the only things we
build ourselves are the Capability Router, Policy Engine, Canonical Memory and Audit
Ledger — roughly the smallest possible core — and everything else is behind an adapter we
can rewrite in a weekend. If OpenClaw dies, we lose adapters, not the system.

---

*Sources in `08-SOURCES.md`.*
