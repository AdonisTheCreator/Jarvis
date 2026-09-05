# 09 — Decision Log

*Append-only. Each entry records what was decided, why, what it commits us to, and what
evidence would reverse it. A decision with no reversal condition written down is a belief,
not a decision.*

---

## D1 — Control plane: **deferred to a measured bake-off**
**Date:** 2026-08-25 · **Status:** Open, scheduled · **Supersedes:** the recommendation in
`04-UNIFICATION-VIABILITY.md` §5

**Decision.** Do not commit to OpenClaw or Hermes yet. Build the Phase 0 core against a
stub adapter, then run a structured bake-off (`10-CONTROL-PLANE-BAKEOFF.md`) and decide on
measurement.

**Why.** The stated priority is that *learning loops and strong memory matter most for an
agent* — and those are precisely Hermes' differentiators, while the node/device model and
harness SDK are OpenClaw's. The two candidates are strong on opposite axes, and the honest
position is that I cannot tell from documentation which axis matters more for how this
system will actually be used. That is exactly the case where measurement beats a
recommendation.

**What it commits us to.**
- The Phase 0 core must be written against the adapter interface with **no vendor types**,
  which was already the invariant. Deferring makes that invariant load-bearing rather than
  aspirational — a good forcing function.
- **The learning loop and canonical memory must be core-owned** (see D4 below). If we let
  either live inside a control plane, we cannot run the bake-off, because switching would
  mean losing them. Deferring the choice *requires* portability.
- Roughly two weeks of extra calendar time before a control plane is running in anger.

**What reverses it.** Bake-off results (§ scoring in doc 10), or discovering during Phase 0
that one candidate cannot satisfy the adapter interface at all — which is itself a result.

**Note on migration direction.** Hermes imports from OpenClaw, one way. If the bake-off is
close, that asymmetry is a tiebreak *toward OpenClaw*, because it preserves an exit.

---

## D2 — Personal Jarvis: **audit first, decide after**
**Date:** 2026-08-25 · **Status:** Open, scheduled for Phase 0.5

**Decision.** Fork and pin it, reproduce the install in a VM, run its test suite, and
inventory what it actually does before deciding whether any of its code enters the stack.

**Why.** Its two genuinely differentiated assets — the sub-second acknowledge voice path
and the Worker–Critic retry loop — are worth real money to us. Its advertised
self-modification is a serious risk in the most privileged path in the system. Both of
those claims deserve to be checked rather than taken from a README.

**Audit checklist** (Phase 0.5 exit criteria):
- [ ] Install reproduced in an isolated VM from a pinned commit
- [ ] Test suite runs; pass rate and coverage recorded
- [ ] **Every outbound network call** enumerated, with destination and trigger
- [ ] Secret handling traced end to end — where keys are read, held, and logged
- [ ] **Every self-modification path** found and documented: what can it rewrite, when,
      with what approval, and is there a rollback
- [ ] Telemetry: what leaves the machine, to whom, and can it be disabled
- [ ] Computer-use action surface: what can it click, type, and execute
- [ ] Mission isolation: is worker execution actually isolated, and from what
- [ ] Voice path measured: real wake-to-ack p50/p95 on our hardware
- [ ] Critic loop measured: does the retry cycle actually improve outcomes, or just cost

**Decision rule set in advance** (so the audit can't be rationalised afterwards):
- Any self-modification path that can write to a running privileged process without a
  human diff → **design only, reimplement**.
- Wake-to-ack p95 above 1.2s on our hardware → the pipeline isn't the asset we thought it
  was → **design only**.
- Clean audit and a fast voice path → **adopt as a pinned voice node**, with
  self-modification disabled at the config level and verified by test.

**What reverses it.** Nothing before the audit runs. That's the point.

---

## D3 — First proactive watch: **CI / deploy health**
**Date:** 2026-08-25 · **Status:** Decided

**Decision.** The first registered watch is CI and deploy health.

**Why it's the right first watch.**
- **Unambiguous threshold.** A build is red or green. No inference, no judgment call.
- **Real cost of missing it.** A silent miss has an obvious consequence, which means the
  watch-liveness metric is honestly testable.
- **No untrusted input in the trigger path.** Status is structured data from a trusted API.
  (Note the boundary carefully: *check-run names, job logs and PR comment bodies are
  untrusted* — anyone who can open a PR or install an app can write them. So the trigger is
  clean, but any summarization of log content runs under the Untrusted Ingest Rule.)
- **It exercises the software-engineering command centre** we want anyway, and it produces
  the first real capability descriptors.

**What it commits us to.** The first three capabilities in the registry are
`ci.read_status` (A0), `ci.read_logs` (A0, quarantined ingest), `ci.rerun_job` (A1,
idempotent). Autonomy ceiling for all three in Phase 1 is **L1 — digest only.** No live
interruption until Phase 3, when the interruptibility model exists to justify it.

**What reverses it.** Nothing; it's a starting point, not an exclusive one. Calendar
conflicts and vehicle readiness follow once the pattern is proven.

---

## D4 — Consequence of D1: **the learning loop is core-owned**
**Date:** 2026-08-25 · **Status:** Decided (follows necessarily from D1)

**Decision.** Procedural learning — observing a completed workflow and turning it into a
reusable skill — is implemented in the Jarvis Core and emits **`SKILL.md` drafts**, not
control-plane-native artifacts.

**Why this is forced.** The stated priority is that learning loops and memory matter most.
If either lives inside OpenClaw or Hermes, then D1's bake-off is unrunnable — switching
control planes would mean abandoning the thing we said we cared about most. Deferring the
control-plane choice *and* prioritising the learning loop together imply that the learning
loop cannot be rented.

**Shape.**
```
  completed task → trace → [core] candidate skill extraction (sleep-time, cheap model)
                              ↓
                        SKILL.md DRAFT → human diff & approve → skills/ (portable)
                              ↓
                    control plane loads it · any control plane · unchanged
```

- Drafts, never live writes. This is R13 and it applies to our own learning loop exactly as
  much as to a vendor's.
- `SKILL.md` / agentskills.io format, because it is the one capability artifact both
  candidates already load.
- Extraction runs as sleep-time compute: narrower tool set than the foreground agent,
  cheaper model, writes to a review queue.
- Hermes' self-evolution work (DSPy + GEPA reading execution traces to explain *why*
  something failed, then proposing targeted improvements) is the right reference for the
  *extraction quality* bar — and something we can adopt as a technique without adopting it
  as a dependency.

**What it commits us to.** Memory stays core-owned per `05-ARCHITECTURE.md` §4 — no
exceptions, including for whichever control plane wins. The control plane owns
`operational` state only.

**What reverses it.** Evidence from the bake-off that a control plane's native learning
loop measurably beats ours on the same tasks by a wide enough margin to justify lock-in.
Doc 10 tests exactly this.

---

## D5 — **The Record and the Audit Ledger are one object**
**Date:** 2026-08-25 · **Status:** Decided · **Detail:** [`11-THE-RECORD.md`](11-THE-RECORD.md)

**Decision.** Full-fidelity capture of all agent activity — main chats, subagent
transcripts, reasoning, every file edit, tool call, policy decision and delivery — is
implemented as **one append-only, content-addressed event log with four read projections**:
Audit, Recall, Reconstruct, Consolidate. The Audit Ledger from `05-ARCHITECTURE.md` §8 is
now the Audit projection of the Record, not a separate store.

**Why.** They were specified separately and would have been built separately — two write
paths over the same facts, guaranteed to diverge, doubling the most expensive infrastructure
in the system. The audit ledger already has to be append-only, tamper-evident and
independent of the runtimes for safety reasons (R12); those are exactly the properties a
trustworthy deep memory needs. Build it once at safety grade and memory inherits the
integrity.

**What it commits us to.**
- The event schema, causal `parent` DAG, and **`subject_keys`** ship in **Phase 0**. None of
  the three can be retrofitted onto an existing archive.
- Payloads are encrypted per subject from the first write, so `forget()` works by
  **crypto-shredding** — destroy the key, leave the ciphertext, preserve the log's hashes and
  causal structure. Recognised as valid erasure by the EDPB, ICO and CNIL given AES-256-class
  encryption and auditable, irreversible key destruction.
- `forget()` must fan out through derived artefacts — embeddings, summaries and learned
  skills leak what they were derived from. Provenance makes the fan-out computable.
- Canonical memory (`05-ARCHITECTURE.md` §4) is redemoted to a *derived, curated* store over
  the Record. The Record is ground truth; memory holds the conclusions.
- Code state uses git, not our blob store — worktrees already give content-addressed history.
  The Record keeps commit refs plus diffs of uncommitted intermediate states.

**Storage reality check.** A full-fidelity year of every word Jarvis and its subagents
produce is roughly **1 GB**. Media is the only real cost. Retention is a policy question, not
a hardware one.

**What reverses it.** Nothing foreseeable. If the log's write throughput becomes a
bottleneck the projections can be split across stores, but the single write path stays.

---

## D6 — **The subconscious is retrieval and consolidation, not a fine-tune**
**Date:** 2026-08-25 · **Status:** Decided · **Detail:** [`11-THE-RECORD.md`](11-THE-RECORD.md) §7–8

**Decision.** The "subconscious" is a background service — a cheap local model with a narrow
tool set, running on idle time — that maintains the index, consolidates episodes into
candidate facts, extracts `SKILL.md` drafts from successful traces, mines failure patterns,
and writes multi-granularity summaries. It is **not** a model fine-tuned on the archive.

**Why not the fine-tune.** It bakes knowledge in lossily, is stale the moment a session ends,
hallucinates confidently about *our own history* — the worst possible domain for confident
invention — and, decisively, **it cannot honour `forget()`**: deleted content is smeared
irreversibly across the weights. That alone disqualifies it under D5.

**Where a fine-tune does earn its place, later.** Not on facts, on judgment: a small LoRA over
our own accepted-vs-rejected routing decisions, salience scores and interruption outcomes.
That's style and policy, regenerable from the Record, and it holds no knowledge to leak.

**Two hard constraints, both enforced at the network layer rather than by prompt.**
- **The subconscious has no egress. Ever.** It reads the most sensitive store in the system;
  it must be structurally incapable of sending anything anywhere.
- **`memory.recall` is a capability with an autonomy class and a scope**, not an ambient
  ability. Scoped to current project + last N sessions by default; archive-wide search is a
  separate, higher class; **a quarantined agent gets no recall at all.** The Record is the
  highest-value exfiltration target in the system, and weaponizing agent memory for
  exfiltration is a documented attack, not a hypothetical.
- **Secret redaction happens at write time.** A credential that never enters the Record cannot
  leak from it.

**What reverses it.** Nothing on the fine-tune-for-facts question. The LoRA-for-judgment
piece is scheduled work, not a reversal.

---

## D7 — **Integration triage: classify by what a thing wants to own**
**Date:** 2026-08-25 · **Status:** Decided · **Detail:** [`13-INTEGRATION-TRIAGE.md`](13-INTEGRATION-TRIAGE.md)

**Decision.** Every candidate addition is classified 1–6 by the layer it wants to own.
Classes 1–3 (models, tools, skills) are near-free: explore constantly, no ceremony. Class 4
(runtimes) needs a measured task class where it wins. Class 5 (control planes) goes through
a bake-off. Class 6 (anything wanting memory, identity, policy or the ledger) is refused.

**Why.** Curiosity is an asset and stack sprawl is a failure mode, and the difference between
them is entirely about which layer the new thing claims. The standing test:
*what breaks if we remove it in six months?*

**The trap it exists to catch.** Things arrive looking like class 1 ("just a better model")
and turn out to be class 5 ("…which brings its own runtime, memory and channels"). Classify
by what it wants to own, never by how it's marketed.

---

## D8 — **Grok: add as a provider now; the real asset is X search, not the model**
**Date:** 2026-08-25 · **Status:** Decided

**Decision.** Grok is three things in three different triage classes:
1. **Model** → class 1. Add as a provider; the router scores it against the others on
   measured success, latency and cost. No architectural discussion needed.
2. **Realtime X / social search** → class 2, and the genuinely differentiated one. Nothing
   else in the stack can serve it. Becomes the capability `research.social_realtime` — run
   under the Untrusted Ingest Rule without exception, since social content is maximally
   hostile input.
3. **Voice Agent API** → class 1, useful as a bridge and as the benchmark local voice must
   beat. Not the destination: ~$3.00/hour means 2 h/day is ~$2,190/year, and it terminates the
   always-on microphone path on someone else's server.

**Why it's already answered.** The API has existed for a while — Grok 4.6, 500K context,
roughly $2/M in and $6/M out. The interesting finding wasn't availability, it was that the
model is the *least* differentiated of the three things.

---

## D9 — **Hermes-first prototype and native coding workers**
**Date:** 2026-09-05 · **Status:** Accepted direction; implementation staged ·
**Supersedes:** D1's prototype prerequisite and migration tiebreak; D4's requirement
to implement custom extraction before evaluation; doc 10's historical scoring and
automatic fallback. Core ownership and production safety obligations remain.

**Decision.** Prototype Hermes first, with separate native Claude Code and Codex
worker adapters. Test its native Codex runtime as an alternative configuration,
accounting for documented delegation/memory tool limitations. Bring a disposable
coding fixture workflow forward before the full device roadmap. Traycer is the
planned visible team workspace behind a scoped adapter. Claude Desktop initially
connects as a client of Jarvis tools through MCP; reverse control is unverified.

**Why.** The user prioritized plain-language task completion, real access to coding
agents, Traycer collaboration, and Hermes. Current documentation establishes
programmable Claude Code/Codex interfaces and a Traycer CLI. We can evaluate the
useful workflow before building every long-term subsystem. Documentation support
is not a passed runtime test.

**What it commits us to.**
- One execution owner per job; no duplicate direct and Traycer-owned dispatch.
- An offline simulation first, then supervised fixture workers, native adapters,
  Hermes text/voice, Traycer and Desktop. Detailed gates in doc 14.
- Confirm worker/descendant stop before reporting cancellation. Unknown external
  state blocks new work until reconciled; never silently relaunch after a timeout.
- Keep approved knowledge and provenance portable. Evaluate Hermes' learning
  proposals now without claiming a custom learning engine already exists.
- No production/private-data capture before the encrypted Record and scoped memory
  path exist. The current in-memory synthetic event list is not that Record.
- Preserve the charter and Phase 0 live-execution gates. No benchmark victory or
  production readiness is claimed by this decision.

**What reverses it.** Hermes fails a required worker, stop, session, voice or memory
portability test, or demands more adapter complexity than the same fixture on
OpenClaw. Run that comparison with pinned versions and a rubric written beforehand.
An importer direction or expired timebox is insufficient to pick a winner.
