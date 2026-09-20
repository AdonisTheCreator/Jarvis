# 20 — The Decision Catalog

*Every place in the architecture where a bounded, calibrated decision earns its keep — and,
just as importantly, the places that look like decision points but are actually rules.*

**Admission test** (doc 14 §10), applied to every entry:
1. **Not decidable by code.** If a parser, a schema or a lookup settles it exactly, it's a rule.
2. **Input not already structured.** If you could write the `if`, write the `if`.
3. **Something escalates on low confidence.** If nothing changes when the answer is "unsure,"
   the probability is wasted and a rule is cheaper.

Every admitted entry carries a **deterministic fallback** (D9) — a real default, not a stub —
because the provider is five days old and single-vendor.

---

## A. Proactivity plane

| ID | Decision | Options | Fallback |
|---|---|---|---|
| A1 | **Salience** — does this change the user's next action? | `act` / `propose` / `notify` / `digest` / `log` | `digest` |
| A2 | **Modality** — where should this land? | `audio` / `hud` / `push` / `card` / `silent` / `defer` | `digest` |
| A3 | **Interruptibility** — is now a good moment? | `now` / `at_breakpoint` / `batch` | `at_breakpoint` |
| A4 | **Trigger triage** — is this watch firing for real? | `real` / `flapping` / `duplicate` | `real` (fail loud) |
| A5 | **Promotion** — has this routine earned more autonomy? | `promote` / `hold` / `demote` | `hold` |
| A6 | **Digest ranking** — what leads the brief? | rank | recency × severity |
| A7 | **Budget pressure** — degrade or spend the interrupt? | `spend` / `degrade` / `drop` | `degrade` |

*A4 note:* fails **loud**, not quiet. A missed threshold breach destroys trust in every watch.

## B. The Record and memory

| ID | Decision | Options | Fallback |
|---|---|---|---|
| B1 | **Event categorisation** at write time | `kind` enum, `subject_keys` | source-derived kind |
| B2 | **Retention adjudication** at day 30 (D9) | `keep_full` / `keep_decision_frames` / `compress` / `derive_and_drop` / `delete` | `compress` |
| B3 | **Consolidation triage** — is this worth remembering? | `fact` / `summarise` / `drop` | `summarise` |
| B4 | **Skill-draft triage** — is this trace worth extracting? | `extract` / `skip` | `skip` |
| B5 | **Recall planning** — which index, which scope? | `project` / `recent` / `archive` / `none` | `project` |
| B6 | **Retrieval rerank** — which 12 of 500? | rank | vector score alone |
| B7 | **Forget fan-out scope** — which derived artefacts leak this subject? | per-artefact `affected` / `clean` | **all** (over-delete; correctness beats cost) |
| B8 | **Memory conflict** — new fact contradicts an old one | `supersede` / `coexist` / `ask` | `ask` |

*B7 note:* the only entry whose fallback is deliberately **more** expensive than the decision.
A forget that misses a derived artefact is a broken promise, so the fallback over-deletes.

## C. Routing and policy (D17)

| ID | Decision | Options | Fallback |
|---|---|---|---|
| C1 | **Task classification** | capability-class enum | keyword map |
| C2 | **Tier adequacy** — is the default model enough? | `adequate` / `upgrade` / `downgrade` | `adequate` |
| C3 | **Policy parse validation** — does the parse match the utterance? | `matches` / `drifts` / `ambiguous` | `ambiguous` → ask |
| C4 | **Policy conflict** at write time | `consistent` / `conflicts` / `underspecified` | `conflicts` → ask |
| C5 | **Backend selection** among eligible providers | rank | registry score |
| C6 | **Failover** — provider degraded, where next? | rank of healthy | next by score |

## D. Sessions and the dev loop (D13, D10)

| ID | Decision | Options | Fallback |
|---|---|---|---|
| D1 | **Session attention** — does this need the human? | `blocked` / `working` / `finished` / `failed` | state machine on last event |
| D2 | **Loop depth** — how much review does this change deserve? | `none` / `single` / `full` | `single` |
| D3 | **Reviewer persona** | `senior` / `security` / `ops` | `senior` |
| D4 | **Finding triage** | `must_fix` / `nice_to_have` / `noise` | `must_fix` |
| D5 | **Stop signal** — has the loop converged? | `continue` / `stop` | `continue` to the cap |
| D6 | **Flake vs. real** | `flake` / `real` / `unknown` | `real` |
| D7 | **Status summarisation** — what's the bottleneck? | rank | oldest blocked |

## E. The Timeless Codebase (doc 19)

| ID | Decision | Options | Fallback |
|---|---|---|---|
| E1 | **Bisect pre-ranking** | `likely` / `unlikely` / `impossible` | plain bisect |
| E2 | **Regression dedupe** | `same` / `related` / `novel` | exact-hash match |
| E3 | **Change intent** | `feature`/`fix`/`refactor`/`perf`/`docs`/`revert`/`risky` | conventional-commit prefix |
| E4 | **Blast radius** | subsystem set | directory map |
| E5 | **Decision supersession** | `supersedes` / `refines` / `conflicts` / `unrelated` | none — flag for review |
| E6 | **Reference selection** — which prior version to learn from? | rank | most recent |
| E7 | **Drift** — code vs. the decision that authorized it | `consistent` / `drifted` / `superseded` | none — periodic review |
| E8 | **Root-cause direction** | subsystem set | blast radius of recent changes |

## F. Voice and presence

| ID | Decision | Options | Fallback |
|---|---|---|---|
| F1 | **Addressed to Jarvis?** — post-wake disambiguation | `to_jarvis` / `ambient` / `unclear` | `unclear` → no action |
| F2 | **Which node answers?** | node id | nearest by wake RSSI |
| F3 | **Barge-in intent** | `stop` / `redirect` / `continue` | `stop` (safest) |
| F4 | **Intent ambiguity** — ask or proceed? | `proceed` / `clarify` | `clarify` |

## G. Safety and health

| ID | Decision | Options | Fallback |
|---|---|---|---|
| G1 | **Untrusted-ingest triage** — what to do with this proposal | `surface` / `file` / `discard` | `file` |
| G2 | **Autonomy-class *proposal*** for a new capability | suggested class | **most restrictive** |
| G3 | **Health degradation** — real or transient? | `real` / `transient` | `real` |
| G4 | **Anomaly** — is this run unlike our own history? | `normal` / `unusual` | `normal`, logged |

> **G2 is a proposal, never a grant.** The hard boundary from D9 holds everywhere in this
> catalog: **Jev decides; the Policy Engine authorizes.** No entry above may grant an approval
> token, authorize an A3 action, override a policy decision, or judge a Protocol's
> preconditions met.

---

## What was rejected, and why

Discipline is the point of the admission test. These look like decision points and aren't:

| Rejected | Why | What it actually is |
|---|---|---|
| Architecture-claim validation (Archify, D11) | **Decidable** — parse the AST, resolve the symbol, compare ranges | A parser |
| Schema / policy validation | Decidable | JSON Schema |
| Permission checks | Decidable, and must be deterministic + auditable | The Policy Engine |
| Idempotency-key collision | Decidable | A hash lookup |
| Secret redaction at write time | Pattern matching; a probabilistic miss leaks a credential | Regex + entropy heuristics |
| Rate limiting / interrupt budget accounting | Arithmetic | A counter |
| "Is this file a test file?" | Path convention | A glob |
| Cache invalidation | Decidable from the dependency graph | A graph walk |
| Wake-word detection | A trained detector already exists and runs on a microcontroller | microWakeWord |
| Cost calculation | Arithmetic | Multiplication |

The pattern: **anything that must be exactly right, auditable, or is already exact — is a rule.**
Anything that is a judgment where "unsure" changes the next step — is a decision.

---

## Volume and cost

Rough annual envelope at $0.042/M input, ~200 tokens of state per call:

| Plane | Calls/year | Cost/year |
|---|---|---|
| A · Proactivity | ~150k | ~$1.30 |
| B · Record & memory | ~4M (dominated by B1 write-time) | ~$34 |
| C · Routing & policy | ~50k | ~$0.40 |
| D · Sessions & dev loop | ~100k | ~$0.85 |
| E · Timeless Codebase | ~500k (rerank-heavy) | ~$4.20 |
| F · Voice & presence | ~80k | ~$0.70 |
| G · Safety & health | ~200k | ~$1.70 |
| **Total** | **~5M** | **≈ $43** |

Forty-three dollars a year to make every one of these decisions properly instead of with a
hand-tuned constant. That is the whole argument, and it is why the catalog is worth keeping
exhaustive — **the marginal decision is nearly free, so the only real cost is discipline about
which ones are genuinely judgments.**

---

## Implementation contract

Every entry is registered as a `DecisionPoint` with: a stable `id`, the option set, the state
schema, the deterministic fallback, an escalation target, and a calibration bucket. The
registry is the single place the catalog becomes code, so §"What was rejected" stays enforced:
**a decision point that cannot name its fallback cannot be registered.**

Calibration is tracked **per `id`** — E5 and D6 will calibrate very differently — and a point
whose reliability diagram goes bad is demoted to its fallback automatically, with a notice.
