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
