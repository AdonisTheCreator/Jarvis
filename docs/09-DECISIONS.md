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

## D9 — **Adopt Jev as the decision layer; retention becomes adjudicated**
**Date:** 2026-09-20 · **Status:** Decided · **Detail:** [`14-THE-DECISION-LAYER.md`](14-THE-DECISION-LAYER.md)

**Decision.** Adopt Jev (TypeSafe's System One model) as the implementation of a `decide.*`
capability family covering twelve bounded-choice decision points already specified across
docs 02, 05 and 11 — salience, modality routing, interruptibility, capability routing,
trigger triage, ingest triage, event categorisation, recall planning, promotion/demotion,
skill-draft triage, consolidation triage, and retention adjudication.

**And: retention is no longer a fixed policy.** Everything is held at full fidelity for 30
days, then each item is judged individually — `keep_full` / `keep_decision_frames` /
`compress` / `derive_and_drop` / `delete`. Deferring the judgment to day 30 is the whole
point: by then we know whether anything referenced it, whether its run succeeded, and whether
a human ever looked at it. A fixed policy has to guess all of that in advance.

**Why.** These decisions were all specified without a mechanism — too cheap for a frontier
call, too consequential to hard-code, too frequent for a human. Jev returns typed answers
with calibrated probabilities in 70–500 ms at **$0.042/M input, output free**. The whole
decision layer runs for **under $50/year**; the same work through a frontier model would be
~$1,600 and would add hundreds of milliseconds to paths that must be invisible.

That changes the design, not just the budget: decisions we would have skipped because they
weren't worth a model call are now free.

**A finding worth keeping.** On WebMCP, Jev scored 49/49 with structured tools and 25/49
without. A clean, well-named action space roughly doubles decision accuracy — an independent
validation of the capability registry, which now pays for itself twice.

**What it commits us to.**
- **The hard boundary: Jev decides, the Policy Engine authorizes.** A calibrated probability
  is not an approval. Jev may choose *which* backend, *which* modality, *whether* to surface,
  *what* to retain. It may never grant an approval token, authorize an A3 action, override a
  policy decision, or judge a Protocol's preconditions met. R7a applies identically to a
  decision model — more so, because it returns a number.
- **Low confidence escalates to the more conservative option, never the cheaper one.** For
  retention that means *keep*.
- **Every decision point ships with a real deterministic fallback**, not a stub. Jev is five
  days old, early-access, waitlist-gated, single-vendor, synthetic-trained, and essentially
  every published figure is self-reported. Fail *open* for speed (routing, modality,
  retention → safe default); fail *closed* for safety (policy, quarantine, approval →
  unavailable means deny).
- **Single bounded decisions only, never chains** (vendor reports weak multi-step reasoning),
  and never where free text is required (it structurally cannot).
- **We verify calibration ourselves.** Log `(decision_type, options, chosen, probability,
  outcome)`; monthly reliability diagram, Brier score and ECE per decision type; thresholds
  set from *our* measured curve, not the vendor's. A poorly calibrated decision type is
  demoted to a deterministic rule or escalated — per type, not globally. D5 already built the
  instrumentation, so this costs nothing extra.

**What reverses it.** Measured calibration failure on our own decision types, or the early
access programme not supporting a daily driver. Both are survivable because of the fallback
rule — which is the point of the fallback rule.

---

## D10 — **Critics must be cross-provider, and blocked runs are failures**
**Date:** 2026-09-20 · **Status:** Decided

**Decision.** The Worker–Critic loop (Phase 4) adopts two rules from Claudex Loop:
**whoever built it never grades it, and the grader comes from a different provider**; and
**blocked runs or exhausted round budgets surface as failures, never as approval.** Plus a
deliberate hard round cap.

**Why.** R12 said the monitor must be independent of the actor as a *process* property. This
sharpens it to a *vendor* property: a reviewer that shares the builder's failure modes is not
a reviewer. Claudex Loop's first greenfield run logged 55 findings across 5 rounds converging
26 → 15 → 12 → 2 → 0, including one fatal architecture flaw — that convergence curve is the
argument.

**The Jev gate on top** is the same shape as our promotion ladder: four bounded decisions
(loop depth / reviewer persona / finding triage / stop signal) gating an expensive cycle,
with low confidence escalating to the more thorough path.

**Note for elsewhere:** Super Coder's generation council and AI quality judge are currently a
same-provider review loop. That's a real finding for that repo, not this one.

---

## D11 — **Archify: adopt the principle, the tool is a 20-minute experiment**
**Date:** 2026-09-20 · **Status:** Decided

**Decision.** Two of Archify's properties become rules for anything Jarvis generates about a
codebase: **fail-closed validation** (an invented component fails validation with diagnostics
rather than rendering a confident wrong diagram) and **evidence-linked claims** (every node
points at the file and line range proving it exists). The tool itself is optional — a
maintained `ARCHITECTURE.md` per repo gets most of the benefit free.

**Why.** This is doc 11's provenance discipline applied to generated artefacts: a claim
carries its evidence or it doesn't ship. The rule is worth more than the renderer.

**Note:** two unrelated projects share the name — `tt-a1i/archify` (MIT agent skill) and
`Aryan1718/Archify` (npx CLI). Check which a reference means.

---

## D12 — **Control plane: Hermes** (resolves D1)
**Date:** 2026-09-20 · **Status:** Decided · **Supersedes:** D1's deferral

**Decision.** Hermes Agent is the control plane. The bake-off (doc 10) is not cancelled — it
is **re-purposed from selection to validation**, and its Class C tasks become an ongoing
signal rather than a one-time test.

**Why it's defensible.** The stated priority from the start was that learning loops and memory
quality matter most, and that is Hermes' axis. Hermes also brings things that are real
regardless of which way the memory question lands: **seven terminal backends** including
serverless-hibernating ones (Modal, Daytona) that cost almost nothing between sessions —
directly useful for cheap always-on watchers and sandboxed execution — 20+ channels including
email, cron with cross-platform delivery, subagent spawning, and MCP.

**The consequence to hold honestly.** D4 puts memory and the procedural learning loop in our
core. Those are also Hermes' headline differentiators. So the thing Hermes was picked *for* is
largely the thing we're building ourselves either way — which means in practice **Hermes is
being adopted as a control plane (sessions, channels, execution backends, cron), and its
learning loop and memory become a reference implementation and a second opinion, not the
system of record.**

That is a coherent position; it just isn't the one the headline suggests. Two things follow:

1. **D4 becomes more important, not less.** Hermes will want to own memory. It must not. One
   owner per class (Rule 2), and that owner is the core.
2. **Running Hermes alongside our own extraction is now a continuous benchmark.** Doc 10's
   Class C stops being a gate and becomes a standing comparison — if their loop beats ours on
   the same traces, that's a signal to adopt techniques, not to hand over ownership.

**Costs accepted.**
- The OpenClaw → Hermes migration path is one-way. Starting here **forecloses that exit.**
  Accepted deliberately.
- Hermes' node/device story is weaker than OpenClaw's, so **more of the node protocol is ours
  to build** (L0/L1, doc 05). That work moves into our court; budget for it.

**What reverses it.** A bake-off validation failure on Class A (control-plane fundamentals) or
Class D (safety), either of which is a gate rather than a weighted axis.

---

## D13 — **Session control is one capability family, not an integration per tool**
**Date:** 2026-09-20 · **Status:** Decided · **Detail:** [`15-SESSION-CONTROL.md`](15-SESSION-CONTROL.md)

**Decision.** Phone→desktop dispatch, status reporting, steering and voice bridging are a
single `session.*` capability family (`list`/`status`/`create`/`send`/`stream`/`interrupt`/
`attach_voice`/`kill`) with **three adapter tiers**: native SDK, headless CLI + session files,
and tmux as the universal fallback.

**Two findings that shaped it.**
- **The harnesses already emit the Record.** Codex writes every session to `~/.codex/sessions/`
  as JSONL — prompts, responses, tool calls, tool results, timestamped. Claude Code emits
  `stream-json`. We ingest and normalise; we do not instrument.
- **The Claude Agent SDK exposes a programmatic approval callback.** That is where the Policy
  Engine plugs in *inside* the harness, so a phone-dispatched session inherits our autonomy
  classes and approval tokens rather than the harness's defaults. The seam already exists.

**Build order inverts the intuition.** Remote *awareness* before remote *control*: blocked,
failed and finished sessions as registered watches (A0 reads, L1 delivery) are the daily win,
and they need no steering at all. `"Codex has been on an approval prompt for 22 minutes"` is
R4 trigger 1, answered with one word.

**Two limits stated up front.** Live steering of a running Codex *thread* is not first-class
yet (open feature request for `turn/steer` against an existing `thread_id`); until it lands,
Codex steering goes through tmux and is brittle. And voice is for steering and status, not
authoring — dictating code is slower than letting the agent write it.

**Security.** `session.send`'s autonomy class follows the *target*, not the verb: A2 into a
sandboxed worktree, **A3 into a session holding shell and credentials on the primary account**
— and A3 means a Protocol. Private network overlay only, never an exposed port. Strong auth on
the phone node. The kill switch reaches every tracked session. And **session output is
untrusted content** — a session that read a hostile file and can be steered from a phone closes
the injection loop.

---

## D14 — **There is no "main Jarvis model"**
**Date:** 2026-09-20 · **Status:** Decided · **Detail:** [`16-MODEL-TOPOLOGY.md`](16-MODEL-TOPOLOGY.md)

**Decision.** Adopt the proposed shape — fast local front + Jev + routing — but reject the
premise that any of them is "the main model." Identity lives in the core (the `identity`
memory class, the policy engine, the Record), not in a model. Five roles: **voice front**
(small-fast local, resident), **decision layer** (Jev), **subconscious** (mid local, resident),
**reasoning** (frontier, routed), **specialists** (harness adapters).

**Why the premise matters.** Naming a main model couples the identity to a vendor, so a model
deprecation becomes an identity change. That is precisely the lock-in the core exists to
prevent — and it would be a strange place to accept it after refusing it everywhere else.

**On "fast large leading local":** those words pull against each other. At 24 GB you get ~32B
at Q4; *leading* is not local in 2026 without tier-D hardware. It doesn't need to be, because
the ack path and the reasoning path are different paths — the local model does conversation
and speed, the frontier model does the thinking, and the user hears one voice. A bigger local
model earns its cost only for reasoning over the Record itself (which must not leave the
machine) and offline resilience.

**Adds `route.pin`** as a real capability: *"use Opus for this"*, *"keep this local"*, *"don't
send that to the cloud."* The second is a spoken privacy control and must be honoured
absolutely — a pinned-local task that silently burst to cloud would breach charter commitment
7. Verified at the network layer.

**New tests** (doc 07): persona consistency across backends, route transparency, `route.pin`
enforcement, ack specificity.

---

## D15 — **Grok Bot: a worker for one bounded job, later — not a competitor**
**Date:** 2026-09-20 · **Status:** Decided

**Triage correction.** Grok the *model* is class 1 (D8). **Grok Bot is class 4** — persistent
named agents on xAI's cloud computers, signing into apps and driving their interfaces rather
than using APIs, continuing after the laptop closes, ~$120/seat/month. A runtime *and* a
deployment *and* its own persistence.

**Is Jarvis just a larger Grok Bot?** No — and the question is worth answering precisely,
because it names what Jarvis must be good at to deserve building. The overlap is "an agent does
multi-step work for you," which is the commodity part. What Grok Bot **structurally cannot
have** is: your own Record, your own policy engine over irreversible actions, your own device
nodes, proactivity on your own registered thresholds, Protocols, and the ability to forget.
*If those aren't materially better than a subscription's defaults, we built the wrong thing.*

**Where it genuinely wins**, and this should be conceded plainly: authenticated web tasks on
services with no API. It has a persistent cloud computer with logged-in sessions; our
equivalent is computer-use, which is local and brittle. That's a real capability —
`web.authenticated_task` — that nothing else in our stack serves well.

**Adopt only if a recurring need appears, and then bounded:**
- **Dedicated scoped accounts only.** Never primary credentials, never anything that can move
  money or change access control. It signs in *as you*, on someone else's machine.
- **It bypasses APIs by driving UIs**, so there is no structured audit — our Record gets only
  what the adapter can observe. That is a genuine hole in the ledger and must be stated, not
  papered over.
- Its own memory and persistence make it a class-6 risk if we ever depend on state it holds.
- The coverage note that it "reaches employees through subscriptions, not a security review"
  is the governance problem in one line. It applies to us too.

**Not Phase 0–2.**

---

## D16 — **God's Eye View: adopt as an output surface; not for weather**
**Date:** 2026-09-20 · **Status:** Decided

**Decision.** Adopt `bilawalsidhu/gods-eye-view` (MIT, open-sourced 2026-08-24) as a **visual
output surface / node**, not as a data source. Use a dedicated weather API (NOAA/NWS or
equivalent) for weather reporting.

**Why not for weather.** Its environmental layers are FIRMS fires, USGS earthquakes and an
opt-in cockpit cloud effect; actual weather radar and satellite imagery are an **open issue,
not a shipped feature**. "Will it rain" is a structured question with an authoritative free
answer one API call away. Routing it through a 3D globe would be slower, less accurate and less
reliable.

**Why adopt it anyway.** It is a photorealistic globe fusing live aircraft, ships, satellites,
earthquakes, fires, traffic, infrastructure and public cameras — and **it already has a
realtime voice agent driving the camera through 28 tools.** That is architecturally the node
pattern from doc 05 §2, already built: a surface the output router can target. It fills the
modality tier we are shortest on (doc 02 §5 wants peripheral/visual surfaces and we currently
have none).

*"Show me the fires near the cabin"* routes to the globe. *"Is it going to rain"* routes to the
weather API and comes back as one spoken sentence. **Different capabilities, different
surfaces — which is the whole point of output routing.**

**The boundary to hold.** It fuses OSINT including public cameras and live aircraft and ship
tracking. That is surveillance-adjacent, and charter commitment 4 applies: **use it for
situational awareness about places and conditions, never about people.** No tracking
individuals, no following named vessels or aircraft, no building a picture of where someone is.
MIT licensing means we can self-host and enforce that by removing capabilities, not just by
policy.

---

## D17 — **Routing policy is spoken, persistent, and position-scoped**
**Date:** 2026-09-20 · **Status:** Decided · **Detail:** [`17-ROUTING-POLICY.md`](17-ROUTING-POLICY.md)

**Decision.** Add `route.policy.*` (`set` / `exclude` / `allow_override` / `list` / `clear`) as
A1 capabilities authored **by voice**, and extend the capability descriptor with a **Model
Cabinet**: per-position rules for `primary`, `subagent`, `critic` and `background`.

**The insight that drove it** — and it reframes doc 14 §10: **the decision layer is a rule
factory, not a rule substitute.** "Which tier for this?" is a judgment while no rule exists, so
Jev decides and proposes. The moment the user says *"always use Fable 5.1 for coding tasks,"*
that judgment becomes a deterministic rule and Jev never decides it again. Jev call volume
falls, determinism rises, cost and latency fall. **It spends its life putting itself out of a
job.** Every rule records the decision that preceded it and the utterance that authorized it,
so *"why does it always use Fable for coding?"* answers itself from the Record.

**Position-scoping is a cost primitive.** Subagents multiply: at $10/$50 per M, one Fable turn
is a considered purchase and eight parallel Fable subagents is a different order of spend, for
work that is usually narrower than the turn that spawned it. Hence `subagent: deny: [fable-5-1]`
as a distinct concept from `primary`.

**The hybrid division, precisely** (this is the answer to "Jev in tandem with Jarvis main"):
**generate with the LLM, validate with Jev, execute with a rule.** A local model parses free
text into a draft policy — Jev structurally cannot, it writes no free text — Jev then answers
the bounded question *does this parse match what was said?* `{matches | drifts | ambiguous}`,
and ambiguity costs one clarifying question. Reusable wherever free text becomes structure:
skill drafts, watch definitions, Protocol declarations, memory writes.

**Two rules this commits us to.**
- **Override beats exclusion.** `route.policy.exclude` binds *automatic selection*;
  `route.pin` — a deliberate human choice — always wins. The user is not a thing the router
  protects itself from. The single exception is the general rule reasserting itself: an override
  can never exceed an **autonomy class**. Routing preferences are preferences; policy is policy.
- **Conflict detection at write time.** Denying Fable at `subagent` while D10 requires a critic
  from a different provider than the builder can empty the legal critic set. That must surface
  when the policy is written, never as a silent same-provider fallback at 2am.

**Two behavioural rules the dialogue demonstrated.** Confirm the *exact* change ("I'm wiping
Fable from the subagents list"), never a vague ack. And **narrate an inferred reason, act only
on the stated one** — saying "watching our costs is wise" exposes an assumption the user never
stated so it can be corrected in one word; silently acting on it would be the R7 violation.

---

## D2 — **UPDATE: static audit clean; one measurement from closing**
**Date:** 2026-09-20 · **Status:** Partially resolved · **Detail:** [`18-PERSONAL-JARVIS-AUDIT.md`](18-PERSONAL-JARVIS-AUDIT.md)

The static half of the audit ran against commit `888df0c` (Apache 2.0, ~330k lines of Python,
3,934 files, **2,176 test files**, last commit one day prior).

**The criterion that would have disqualified it did not fire.** Generated skills go through a
**forced draft lifecycle** enforced in code with an audit trail — *"state=draft is ALWAYS
forced… we note the override in the result"* — and even `promote_to_global()` lands as a draft.
A model in that system cannot write itself a live capability. Telemetry is local performance
instrumentation with no analytics phone-home; every outbound host is a provider, an opted-in
integration, or a docs URL; secrets live in the OS keyring with no plaintext writes found.

**What remains:** per-utterance **wake-to-ack on our hardware**, which needs a VM and a
microphone and was not measurable in this environment. The shipped `desktop-ttu-latest.json`
reports median voice-ready ≈ 12.8 s, but that is **cold start from spawn, not wake-to-ack** —
the two must not be conflated, and for an always-on service the first is largely irrelevant.

**Next step to close:** pinned commit in a VM, test-suite pass rate, and wake → acknowledgement
over ~50 utterances. Under 1.2 s p95 → adopt as a pinned voice node with skill authoring
disabled at config and verified by test. Over → design only, as originally planned.

**Adopt regardless of the verdict:** the forced-draft skill lifecycle; the computer-use loop
`capture → target_guard → actuate → verify → ledger`; and the field datapoint from their
retention module — **~91k screenshot files / ~38 GB observed without a sweep**, which confirms
doc 11 §4 (text is free, pixels are the cost) and is exactly the fixed-age policy D9 improves
on with per-item adjudication.

**One caveat to carry:** `install_agy_jarvis_plugin()` writes `mcp_config.json` into the
workspace automatically to mount Jarvis' tools into a sub-agent. Workspace-scoped, additive,
and it does not touch the global config — but it is a privilege-granting write performed as a
silent side-effect. In our stack that needs an explicit capability with an autonomy class.

---

## D18 — **Phase 0 built: what shipped, and what building it revealed**
**Date:** 2026-09-20 · **Status:** Complete · **Code:** `src/jarvis_core/`

**Shipped.** The Record (append-only, content-addressed, causal DAG,
per-subject crypto-shredding, write-time redaction, hash-chain tamper
evidence), the Policy Engine (A0–A4, scoped single-use approvals, Protocols,
kill switch), the decision layer (24 registered points, mandatory fallbacks,
the rule factory, per-point calibration), canonical memory (provenance,
proposals, transitive forget), the capability router (authorize → claim →
execute → record), idempotency, the backend contract, and the quarantine
boundary. **214 tests.**

**Stdlib-only except `cryptography`.** The core's vendor-freedom invariant is
now enforced by `tests/test_invariants.py`, which parses every core module and
fails on a vendor import or a vendor-named class. An architectural rule that
nothing checks decays silently; this one cannot.

### Four bugs the build surfaced, each worth keeping

1. **Redaction pattern shadowing.** `sk-ant-…` matched the OpenAI pattern
   first, so Anthropic keys were redacted under the wrong label. Correct
   redaction, lying audit trail. Ordering now runs most-specific first.

2. **The null decider reported itself available.** Its zero-confidence answer
   was then *re-escalated* as though a model had been unsure — quietly turning
   "no decision layer configured" into "escalate everything". Fixed by making
   absence explicit: `available()` is False, so each point's own fallback
   applies.

3. **`safety_critical` was set on five points whose fallback was already the
   safe answer.** Denying there is strictly worse than falling back — refusing
   to forget because the decision layer is down is not failing closed, it is
   failing. Removed, and the property is now asserted: every standard point has
   a safe fallback, and a point that cannot name one is probably a rule wearing
   a decision's clothes.

4. **Two found only because a test existed**, which is the argument for writing
   them first:
   - *Content-addressed blobs were shared across subjects.* One subject's
     payload could serve another's event, so a shared blob **survived one of
     them being forgotten**. A leak, not a saving. Blobs are now namespaced per
     subject, and the layering corrected: the **AAD binds payload → subject**,
     the **hash chain binds event → payload**. Binding the AAD to the event id
     had also made dedup impossible, so the fix restores it.
   - *ULIDs are only time-ordered across milliseconds.* Within one, the random
     component decides order arbitrarily — and the Record relies on id order
     being write order. A busy moment shuffles the log. Now monotonic per the
     ULID spec, with auto-generated timestamps that never regress, so an NTP
     correction cannot make the log appear to go backwards.

### Exit criteria, against `docs/06`

| Criterion | Status |
|---|---|
| 50 scripted tasks route end to end, zero vendor types in the core | ✅ `test_router.py::TestScriptedWorkload`, `test_invariants.py` |
| Kill switch halts, verified from a test harness | ✅ including the fail-closed path and the human-observe carve-out |
| Quarantined agent + adversarial content → Proposal, no capability invoked | ✅ three injection fixtures (email, PR comment, app review) |
| Every action reconstructible from the Record alone | ✅ invoke *and* outcome recorded; audit walks the causal DAG |
| `forget()` destroys the key, leaves hashes and links intact, fans out | ✅ including transitive derived facts |

### What is deliberately not built yet
Durable idempotency (in-memory is honest about its scope), a real Jev adapter
(waitlist), vector/FTS indexes for Recall, and the Hermes adapter. All are
Phase 0.5+ and none require changing a Phase 0 contract.

---

## D19 — **Delete the async settlement protocol rather than fix it**
**Date:** 2026-09-20 · **Status:** Decided · **Code:** `router.py`, `idempotency.py`

**Decision.** Remove the asynchronous claim-settlement machinery from the router
— handle bindings, the poll-until-resolved loop, and the seven-state outcome —
and replace it with a **caller-held claim token**. The router resolves what it
can see at dispatch (`COMPLETED`, `RELEASED`) and otherwise reports `HELD`,
handing back a token the caller uses to resolve it once it actually knows.

**Why, stated plainly.** Six review rounds produced 29 findings. Round one was
spread across the codebase; **rounds two through six were all in this one
subsystem**, and each fix created the next hole:

| Round | Fix | What it caused |
|---|---|---|
| 2 | Settle from the handle's echoed key | Adapters aren't required to echo it → claims stranded |
| 3 | Router keeps an in-process handle→key map | Not durable; stale handles settled live retries |
| 4 | Move the map into the ledger | Handle-id collisions across backends |
| 5 | Add generations to guard stale resolution | The guard was **inert** — nothing carried the generation |

The round-five guard reading the *live* generation instead of the attempt's own
was the tell. I wasn't fixing a bug; I was maintaining a protocol that had no
business existing yet.

**What was actually required.** `docs/06` Phase 0 asks for *exactly-once side
effects*. It does not ask for an async settlement protocol — and there is no
async backend, no durable ledger, and nothing to verify it against. This was
speculative complexity, which `docs/04` Rule 3 exists to prevent: **the core
stays small.**

**What the token fixes structurally**, rather than by patch:
- The token carries its own generation, so a late resolution from an abandoned
  attempt cannot settle a newer one sharing the key. (Keys hash the *action*,
  so every retry shares its predecessor's key — this is the central hazard.)
- No handle bindings, so no collisions, no staleness, no durability gap.
- `HELD` means one thing: *not knowable yet, so the action stays blocked*. The
  earlier `PENDING`/`STUCK`/`UNKNOWN` split existed to paper over ambiguities
  the bindings created. (`ALREADY_RESOLVED` went with them and was restored two
  rounds later: "someone else resolved it first" turned out to be a genuinely
  distinct fact rather than an artefact of the bindings. Cutting it was one
  step too far.)
- Anything unclear — pending, interrupted, or a `status()` call that raised —
  holds the claim. Guessing in either direction sends the message twice or
  never.

**Result:** −106 lines, 5 outcome states instead of 7, 6 ledger methods instead
of 8. The review rounds that followed added `ALREADY_RESOLVED` back and split
`effect_landed` out of the claim outcome, on the same principle: one value,
one fact.

**The general lesson, worth keeping.** When review findings stop converging and
start circling one component, the component is usually the problem. The fix is
not a better patch — it is asking what the thing was actually required to do.

---

## D20 — **A guard that cannot fail is not a guard: mutation-test every one**
**Date:** 2026-09-20 · **Status:** Decided · **Code:** `killswitch.py`, `memory.py`,
`record/redact.py`, `record/projections.py`, `decide/registry.py`

**Decision.** Every check whose job is to catch a failure must be verified by
*causing* that failure and watching the check go red. A guard that has never
been seen to fail is documentation, and the test that covers it is a second
piece of documentation agreeing with the first.

**Why, stated plainly.** Review rounds 25–27 found six of them, all in code
that read as careful and all of it mine. In each case a test passed, a
docstring made a confident claim, and the claim was false:

| Guard | What it claimed | What it did |
|---|---|---|
| `FileKillSwitch` | Fails closed on a missing mount or an unreadable sentinel | `Path.exists()` swallows ENOENT, ENOTDIR, ELOOP and EBADF, so the fail-closed branch was unreachable for exactly those faults. A detached mount read as *not engaged*. The test that "covered" it raised a synthetic `OSError` the real API never raises. |
| `CanonicalMemory.leaks()` | Detects a broken forget fan-out | Looked only at `subject_keys` — the set `forget` removes *directly*. Deleting the entire traversal left it reporting all clear. |
| `CORE_OWNED` | The memory-ownership boundary (docs/05 §4) | Defined, documented, referenced by nothing. |
| `redact_bytes` | A credential never enters the Record | Any payload that was not valid UTF-8 was waved through untouched, with an empty report that reads in the audit projection as *we looked and it was clean*. |
| `RecallScope` | Recall is a capability with an autonomy class, not an ambient ability | A plain argument the caller chose for itself, on what the same docstring calls the highest-value exfiltration target in the system. |
| `DecisionRegistry.decide` | An out-of-option answer is rejected | Rejected it to the **fallback**, which for `record.retention` is `compress` where low confidence says `keep_full` — so a decider emitting nonsense destroyed detail an unsure one would have kept. Broken got the milder treatment than unsure. |

**The shape they share.** Every one of them fails in the *safe-looking*
direction: absent, empty, clean, allowed, cheaper. That is not a coincidence.
A guard is written while thinking about the dangerous path, and the benign
default is whatever the language does when nothing happens. So the untested
branch is always the one that matters, and it always looks fine in green CI.

**What it commits us to.** For each guard: write the mutation, run it, confirm
the matching test — not merely *a* test — goes red, then revert. All six fixes
here carry one. Two of them turned nothing red at all before the fix, which is
the entire point of the exercise.

**What reverses it.** Nothing about the principle. The *mechanism* is worth
revisiting: these were run by hand and are not repeatable. If the count of
guards keeps rising, a mutation-testing harness (`mutmut`, `cosmic-ray`) over
`src/jarvis_core/` earns its keep — with the caveat that a general mutation
tool scores *lines*, and what matters here is whether the right test failed.

**Relation to D19.** D19 said: when findings circle one component, the
component is the problem. D20 is the other half: when findings stop appearing,
check whether that is convergence or whether the checks have simply stopped
looking. Rounds 20–24 all landed in one subsystem (D19's lesson); rounds 25–27
found six defects in modules that had produced none, because this was the first
pass that tried to *break* them rather than read them.
