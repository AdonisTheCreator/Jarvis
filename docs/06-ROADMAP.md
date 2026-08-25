# 06 — Roadmap (Reordered)

*The source blueprint's roadmap is broadly sensible but ordered wrong in two places:
safety is Phase 8 and proactivity is Phase 6. Both belong at the front — safety because a
proactive agent cannot be retrofitted safe, and proactivity because it is the product.
This reorders and adds explicit exit criteria that are testable rather than narrative.*

---

## Phase 0 — Core contracts and the safety spine
**No devices. No voice. No integrations. Ship the boring part first.**

Build:
- Capability descriptor schema + registry (start with 3 capabilities, all A0/A1)
- `AgentBackend` adapter interface with idempotency keys
- **Policy Engine**: autonomy classes A0–A4, approval tokens (action+target+params+expiry+single-use)
- **Audit Ledger**: append-only, independent process
- **Kill switch**: out-of-band, model-independent, with a scheduled test
- **Untrusted Ingest Rule** implemented as an enforced quarantine role, not a convention
- Canonical Memory with provenance + a working `forget()`

Exit criteria:
- 50 scripted tasks route end-to-end with **zero vendor types in the core**
- Kill switch halts everything in <2s, verified from a test harness
- A quarantined agent handed adversarial content emits a `Proposal` and invokes **no**
  capability — three injection fixtures, all passing
- Every action reconstructible from the ledger alone

---

## Phase 1 — One control plane + the digest
**The first proactive surface, at the lowest possible risk.**

Build:
- Stand up **one** control plane (recommended: OpenClaw). Prove through the adapter:
  session create, tool invoke, channel route, approvals, cancel, event stream.
- Watch registry + delivery ledger
- **Morning/evening digest** (trigger classes 3.1 + 3.6) — L1 autonomy, no live interrupts
- Sleep-time consolidation job on a cheap model with a narrow tool set

Exit criteria:
- Digest delivered daily for 14 consecutive days without manual intervention
- User can enumerate every active watch and every fact the system holds about them
- Cost per day measured and bounded

---

## Phase 2 — Voice presence
Build: wake (local) → VAD → STT → route → **specific** ack <1s → TTS; barge-in
cancel/redirect; one canonical session across ≥2 nodes.

Exit criteria: wake-to-ack p95 <1s; barge-in stops a destructive action **100/100 times**;
a sentence started on node A completes on node B.

---

## Phase 3 — Threshold watches and the interruption model
Build: class 3.3 watches with dwell/hysteresis; salience scoring; interruptibility model;
**modality router**; interrupt budget. Autonomy ceiling L2 (notify only).

Exit criteria: **interruption precision ≥0.8** over 100 delivered items; **watch miss rate
≈0**; budget never exceeded; a killed watch raises within one cycle.

---

## Phase 4 — Specialist workers
Build: Claude Code / Codex adapters behind harness plugins; Worker–Critic loop; Traycer
for multi-agent topology if parallel worktrees are needed; screenshot/vision critic.

Exit criteria: measured success rate per backend on a fixed coding benchmark, and routing
that demonstrably uses those measurements.

---

## Phase 5 — Proposals and the promotion ladder
Build: Agent-Inbox-style proposals (notify / question / review); one-tap approve; L3→L4
promotion with observed/accepted thresholds; automatic demotion on rejection or error.

Exit criteria: at least one routine promoted to L4 on evidence; demotion fires correctly
on an induced failure; **no A3 action ever reaches L4**.

---

## Phase 6 — Physical world
Build: Home Assistant adapter (its automations *are* our class-3.3 watches — do not
duplicate them); room satellites with local wake; presence-based output routing; **first
Protocols declared** for anything A3.

Exit criteria: state verified after every physical action; no A3 physical action executes
outside a declared Protocol; bystander policy (doc 05 §7) implemented on every node.

---

## Phase 7 — Mobile, vehicle, wearable
Build: phone node (iOS node now; Android `VoiceInteractionService` as the deeper path);
Tesla Fleet adapter with virtual key; glasses via DAT SDK / VisionClaw pattern (sensor
node → control plane).

Exit criteria: 20+ vehicle commands tested safely; A3 vehicle actions (unlock, trunk) only
via Protocol + strong auth; glasses capture policy enforced and audited.

---

## Phase 8 — Dedicated core and daily-drive
Build: always-on machine (quiet, 64GB+, NVMe, UPS, encrypted backups — **not** a GPU box
until a workload proves it), local STT/TTS, secrets, scheduling; failure injection;
crash/network/provider-loss recovery.

Exit criteria: survives restart with missions and approvals intact or **fails closed**;
runs a week unattended; recovery from provider outage is graceful and visible.

---

## Ordering rules
1. **Nothing gains a permission it has not been measured under.**
2. **Hardware follows capability proof, never enthusiasm.** Every device is a node behind
   an adapter; buy after the adapter contract is stable.
3. **Autonomy is earned per capability**, never granted per agent.
4. **If a phase's exit criteria can't be measured, the phase isn't defined yet.**
