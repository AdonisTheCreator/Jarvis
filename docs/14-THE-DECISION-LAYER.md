# 14 — The Decision Layer: Jev, and Adjudicated Retention

*Source: `Jarvis_Handoff_Jev_Claudex_Archify` (2026-09-19). Verified 2026-09-20 against
current coverage. The handoff's own instruction — treat vendor numbers as claims — is
respected below; every figure is labelled.*

---

## 1. The instinct is right, and it's bigger than filing

The read was "this may be the filing system." It is — and the reason it's a good filing
system is the reason it's a good **twelve other things**. Jev is not a better model for our
stack. It's a *missing component class*.

Every architecture doc here is full of small bounded decisions that currently have no good
home. They're too cheap to justify a frontier call, too consequential to hard-code, and too
frequent to ask a human. I'd been writing "score this," "decide that," "classify this"
without naming what would do it. That component now exists.

**What Jev is, precisely:** a hosted decision model that takes unstructured program state
plus questions with *predefined answer options*, and returns typed answers with **calibrated
probabilities** — in 70–500 ms, with several questions per request evaluated in parallel.
Trained on synthetic data only (RLCD). **$0.042 per million input tokens; output free.**

**What it is not:** it cannot write free text — no tool arguments, no search queries, no
prose. The vendor itself reports weaker accuracy on multi-step reasoning. And "can't
hallucinate" means only that it can't invent an option outside the given set; **it can still
pick the wrong one**, and a wrong typed answer is more dangerous than a wrong paragraph
precisely because it arrives looking valid.

---

## 2. Where it fits: the Jev-shaped holes already in our design

These are all places where existing docs say "score," "classify," "decide," or "route" and
then wave at the mechanism. Every one is a bounded choice over structured state.

| # | Decision | Options | Doc |
|---|---|---|---|
| 1 | **Salience** — does this change the next action? | act / propose / notify / digest / log | 02 §4 |
| 2 | **Modality routing** | audio / HUD / push / card / silent / defer | 02 §5, R6 |
| 3 | **Interruptibility** | interrupt now / hold to breakpoint / batch | 02 §5.3 |
| 4 | **Capability routing** | which backend, which model tier | 05 §6.3 |
| 5 | **Trigger triage** | real / flapping / duplicate | 02 §3.3 |
| 6 | **Untrusted-ingest triage** | surface / file / discard | 02 §7 |
| 7 | **Event categorisation at write time** | `kind`, `subject_keys` | 11 §3 |
| 8 | **Recall planning** | which index, which scope | 11 §7 |
| 9 | **Promotion / demotion** | promote / hold / demote | 02 §6 |
| 10 | **Skill-draft triage** | worth extracting / not | 11 §7, D4 |
| 11 | **Consolidation triage** | keep as fact / summarise / drop | 11 §7 |
| 12 | **Retention adjudication** | keep / compress / derive / delete | §3 below |

Note what this *replaces*: a pile of hand-tuned heuristics and threshold constants that
would have rotted, plus a pile of small LLM calls that would have been slow and expensive.

**And a finding worth lingering on.** On the WebMCP benchmark, Jev solved 49/49 tasks with
structured tools and only **25/49** without them. That is an independent validation of the
capability registry: *a clean, well-named action space roughly doubles decision accuracy.*
The registry was justified for policy and routing clarity. It now pays for itself twice.

---

## 3. Adjudicated retention — the screenshot answer, designed out

The proposal: hold screenshots 30 days, then **determine** whether to keep, compress or
delete. That's better than my "decision frames only" suggestion, because it defers the
judgment to when the evidence exists — by day 30 we know whether anything ever referenced
that frame.

### The adjudication pass

Runs monthly over everything aged past 30 days. One Jev call per item (batched questions):

| Verdict | Action |
|---|---|
| `keep_full` | Untouched. Referenced by an open issue, an unresolved failure, a decision, or user-flagged |
| `keep_decision_frames` | Keep the before/after pair around each capability invocation; drop the intermediate stream |
| `compress` | Downsample resolution and quality; keep the sequence |
| `derive_and_drop` | Keep OCR text + a description + event metadata; drop the pixels |
| `delete` | Nothing of value survives |

**Signals it decides from** — all structured, all already in the Record: did the run succeed
or fail (failures are worth more); was it ever recalled after capture; does an open
issue/PR/decision reference the event; is it a decision frame; perceptual novelty versus
neighbours; did a human ever look at it; did the session produce a learned skill; **does it
contain a third party**; is it flagged.

### The five rules that make it safe

1. **Low confidence escalates to the more conservative option, never the cheaper one.** The
   handoff states this as a general Jev principle and it inverts correctly here: for
   retention, thorough = *keep*. Below threshold → `compress`, never `delete`.
2. **Adjudication marks; it never deletes.** A grace period (another 30 days) elapses before
   the reaper runs, so a bad pass is recoverable.
3. **Every verdict is an event**, with the option chosen and its probability. So "was the
   adjudicator too aggressive last quarter?" is answerable, and the thresholds are tunable
   against evidence rather than vibes.
4. **A tombstone survives deletion.** What was deleted, when, and under which verdict stays
   in the Record even when the bytes don't.
5. **Third parties bias toward deletion, not retention.** Charter commitment 4. This is the
   one signal where the conservative direction is *delete*, and the adjudicator must know it.

`forget()` is unaffected and always wins — user-initiated erasure is immediate
crypto-shredding (doc 11 §6), never routed through adjudication.

### This generalises past screenshots

Same pass, same shape, different options — audio (keep / transcript-only), full-file read
blobs, verbose tool output, superseded index shards. Retention stops being a policy constant
and becomes a per-item judgment.

---

## 4. The cost math, which is the actual unlock

At $0.042/M input with free output, adjudicating ~200 tokens of structured state per item:

| Pass | Volume / year | Tokens | Cost / year |
|---|---|---|---|
| Screenshot adjudication (monthly, ~22k items/pass) | ~263k items | ~53 M | **~$2** |
| Every Record event categorised at write (~10k/day) | ~3.65 M events | ~730 M | **~$31** |
| Salience + modality on every watch fire (~300/day) | ~110k | ~22 M | **~$1** |

**The whole decision layer runs for well under $50/year.** The same work through a frontier
model at ~$2/M input would be ~$1,600 — and would add hundreds of milliseconds to paths that
need to be invisible.

That changes the design, not just the budget. "Pick a retention policy" becomes "decide per
item, forever." "Estimate salience with a heuristic" becomes "score every candidate
properly." Decisions we would have skipped because they weren't worth a model call are now
free.

*(Independent datapoint, builder-reported: `jev-codex-router` reports ~60% cost reduction
versus always-frontier over a 237-turn replay. Unverified, but the shape matches.)*

---

## 5. The hard boundary: Jev decides, the Policy Engine authorizes

The most important line in this document.

> **A calibrated probability is not an approval.**

Jev at 0.97 that an action is safe is **not** an A3 authorization. It is an input to routing,
never a grant of authority. This is R7a restated — *the persona is never the security
boundary* — and it applies identically to a decision model, which is if anything more
seductive because it returns a number.

Concretely:
- Jev may choose **which** backend, **which** modality, **whether** to surface, **what** to
  retain.
- Jev may **never** be the thing that authorizes an A3 action, grants an approval token,
  overrides a policy decision, or decides that a Protocol's preconditions are met.
- A quarantined agent's ingest triage runs on Jev, and its output is still only a `Proposal`.
- The kill switch, the policy engine and the audit projection remain independent of it (R12).

---

## 6. Calibration is a claim; we have the dataset to check it

The entire value proposition is that the probabilities are *calibrated*. If the 0.8 bucket
isn't right about 80% of the time, every threshold in §3 and §2 is meaningless.

The happy accident: **the Record already logs every decision and its outcome** (D5). That's
precisely the dataset needed to plot a reliability diagram over our *own* decision types. So:

- Log `(decision_type, options, chosen, probability, eventual_outcome)` from day one.
- Monthly: reliability diagram per decision type. Report Brier score and ECE.
- **Thresholds are set from our measured curve, not from the vendor's.** Calibration is
  domain-specific; there is no reason to assume it transfers to our state shapes.
- A decision type whose calibration is poor gets demoted to a deterministic rule or escalated
  to an LLM. Per type, not globally.

This is the "measure before trusting" principle from the handoff, and it costs us nothing
extra because D5 already built the instrumentation.

---

## 7. Risk, and the fallback rule

Jev was released **five days** before this was written. Early access, waitlist-gated, single
vendor, proprietary hosted API, synthetic-training-only, and essentially every published
performance figure is self-reported.

**Therefore: every Jev decision point ships with a deterministic fallback that is good enough
to run on indefinitely.** Not a stub — a real default. If Jev is unavailable, degraded, or
gets deprecated, the system keeps working with slightly worse decisions and slightly higher
cost.

Applying the handoff's own rule, correctly split:
- **Fail open for speed.** Routing, modality, retention triage → fall back to the safe default
  (default model tier; digest; `compress`) and carry on.
- **Fail closed for safety.** Anything touching policy, ingest quarantine, or approval →
  unavailable means *deny*, never *allow*.

And two usage constraints from the vendor's own stated limits: **single bounded decisions
only, never chains** (weak multi-step reasoning), and **never for anything requiring free
text** (it structurally cannot).

---

## 8. Claudex Loop — cross-provider review, and the principle worth stealing

Claudex Loop enforces one rule: **whoever built it never grades it.** Claude drafts `PLAN.md`,
Codex attacks it, Claude revises — capped at 5 rounds — then one provider builds and the
*other* inspects. Its first greenfield run logged 55 findings across 5 rounds converging
26 → 15 → 12 → 2 → 0, including one fatal architecture flaw.

Three things here are directly ours:

1. **Cross-*provider* independence is a stronger form of R12.** I'd written "the monitor is
   independent of the actor" as a process property. This says it should also be a *vendor*
   property: a reviewer sharing the builder's failure modes isn't a reviewer. Adopt for the
   Worker–Critic loop (Phase 4) — the critic comes from a different provider than the builder.
2. **Blocked runs and exhausted budgets surface as failures, never approval.** That is
   fail-closed, correctly applied to a review loop, and it is exactly the discipline our
   evaluation suite needs.
3. **A hard round cap**, deliberately. Unbounded critic loops are how you burn a day.

The proposed Jev gate on the loop generalises cleanly and is the same shape as our promotion
ladder: Jev decides **loop depth** (none / single review / full loop), **reviewer persona**,
**finding triage** (must-fix / nice-to-have / noise), and **stop signal** — four bounded
decisions in milliseconds each, gating an expensive cycle. Low confidence escalates to the
*more* thorough path.

*This lands squarely on Super Coder's generation council and its AI quality judge, which are
already a same-provider review loop. Worth a separate look; out of scope here.*

---

## 9. Archify — adopt the principle, the tool is optional

The handoff's verdict is right: Archify is mainly for human understanding, and a maintained
`ARCHITECTURE.md` per repo gets most of the benefit free. But two of its properties are
things we want *everywhere*, independent of the tool:

- **Fail-closed validation** — if the agent invents a component, validation fails with
  diagnostics rather than rendering a confident wrong diagram.
- **Repo evidence** — every node links to the exact file and line range proving it exists.

That is the provenance discipline from doc 11 applied to generated artefacts: *a claim
carries its evidence, or it doesn't ship.* Adopt it as a rule for anything Jarvis generates
about a codebase.

The suggested 20-minute test on the largest repo is a good cheap experiment. Note there are
two unrelated projects called Archify (`tt-a1i/archify`, MIT agent skill; and
`Aryan1718/Archify`, an npx CLI) — check which a given reference means.

---

## 10. Triage placement (doc 13)

| Thing | Class | Placement |
|---|---|---|
| **Jev** | **1 — provider**, serving a capability class nothing else serves | The `decide.*` family. Never owns policy, memory or the ledger (§5) |
| **Claudex Loop** | 3 — skill / pattern | Cross-provider critic for Phase 4. Adopt the independence + fail-closed rules now |
| **Archify** | 2 — optional tool; 0-cost principle | Adopt fail-closed validation + evidence links; the tool is a 20-min experiment |

Jev passes the standing test cleanly. *What breaks if we remove it in six months?* Decisions
get worse and slightly more expensive, and every one of them has a deterministic fallback
(§7). Nothing structural. That is exactly the profile of a safe class-1 adoption — and the
reason it can be adopted fast.
