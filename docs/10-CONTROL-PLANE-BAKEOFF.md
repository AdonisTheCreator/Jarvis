# 10 — Control Plane Bake-Off

*Implements decision **D1**. Runs in Phase 0.5, after the core contracts exist and before
any control plane is running in anger. Two candidates, one adapter interface, a fixed task
set, and a scoring rubric written **before** the results come in.*

---

## 1. The actual question

Not "which project is better." Both are good. The question is narrower and answerable:

> **Does a control plane's native learning loop and memory measurably beat a strong model
> plus our own core-owned memory and `SKILL.md` skills — by enough to justify locking to
> it?**

Because the priority set in D1 is that learning and memory matter most, and because D4
puts both in our core regardless, the bake-off has to test whether renting them is
*better than* owning them. If it isn't, the decision collapses to the other axis — nodes,
channels, harness SDK, security posture — where OpenClaw currently leads.

---

## 2. Ground rules

1. **Both candidates sit behind the same `AgentBackend` adapter.** If a candidate needs the
   interface widened, that is a finding, and it is recorded as a cost.
2. **Same model, same keys, same machine, same tasks.** The only variable is the control
   plane.
3. **Our core owns memory in both arms.** Each candidate's native memory runs *in addition*,
   so we can compare what it adds — never as a replacement.
4. **Fixed task set, written first.** No task added after either arm has run.
5. **Findings recorded as they happen**, in this file, including the ones that don't fit
   the thesis.

---

## 3. Task set

Twelve tasks across four classes. Each is scripted, repeatable, and has a machine-checkable
success condition.

### Class A — Control plane fundamentals (4 tasks)
| # | Task | Checks |
|---|---|---|
| A1 | Create a session, invoke a tool, stream events, cancel mid-flight | Session lifecycle, cancel correctness |
| A2 | Route the same request through two channels; confirm one canonical transcript | Session identity across surfaces |
| A3 | Attach a headless node; confirm its skills appear and withdraw on disconnect | Capability presence model |
| A4 | Trigger an approval; deny it; confirm the action did not execute | Approval enforcement |

### Class B — Runtime ownership (2 tasks)
| # | Task | Checks |
|---|---|---|
| B1 | Run a coding task through an external harness (Claude Code or Codex) owning the session | Harness SDK maturity; who owns what |
| B2 | Switch harness mid-conversation; confirm transcript continuity | Transcript mirror quality |

### Class C — Learning and memory — **the decisive class** (4 tasks)
| # | Task | Checks |
|---|---|---|
| C1 | Perform a 6-step workflow three times; measure whether a reusable skill is produced, and its quality | Skill extraction — *native vs. our core* |
| C2 | Re-run the workflow with one parameter changed; does the learned skill generalise or misfire? | Skill robustness — the failure mode that matters |
| C3 | Ask a question answerable only from a session 30+ conversations back | Cross-session recall |
| C4 | State a preference, contradict it two sessions later; check which survives and whether provenance is intact | Memory correctness under conflict |

### Class D — Safety and operations (2 tasks)
| # | Task | Checks |
|---|---|---|
| D1 | Feed adversarial content through a watcher (injection fixtures from doc 07 §4) | Untrusted Ingest Rule holds through the adapter |
| D2 | Kill the process mid-task; restart | Recovery, or fail-closed. Never fail-open |

---

## 4. Scoring rubric — fixed in advance

| Axis | Weight | Measured by |
|---|---|---|
| **Learning-loop lift over our core** | **30** | Class C1–C2. Scored as the *delta* against our own extraction on identical traces. **A native loop that ties our core scores 0, not full marks.** |
| **Memory quality** | **15** | C3–C4: recall accuracy, provenance integrity, conflict resolution |
| **Node / device model** | **15** | A3, plus what it takes to add a new node type |
| **Harness / runtime ownership** | **15** | B1–B2: does an external runtime own the session cleanly |
| **Adapter fit** | **10** | How much interface widening each candidate demanded (§2 rule 1) |
| **Safety posture** | **10** | D1–D2, plus credential handling observed during the run |
| **Operational cost** | **5** | Tokens and wall-clock across the full task set |

**Tiebreak, stated now so it can't be reasoned to afterwards:** if the totals are within
5 points, choose **OpenClaw** — because Hermes imports from OpenClaw one-way, so starting
there preserves an exit and starting on Hermes forecloses one.

---

## 5. What a decisive result looks like

- **Hermes wins the learning axis by >10 of its 30 points** → the loop is a real asset, not
  a README claim. Adopt Hermes as control plane, keep memory core-owned anyway (D4), and
  accept the weaker node story as a cost to be engineered around.
- **Learning delta is near zero** → the loop is replaceable by our core plus a strong model.
  Decision collapses to nodes, channels and harness SDK → **OpenClaw**.
- **Either candidate fails Class D** → it does not become the control plane, whatever it
  scores elsewhere. Safety is not a weighted axis with the others; it's a gate.
- **Both fail Class A3** → the node model we designed L0/L1 around doesn't exist as
  documented, and the presence layer needs rethinking before either is chosen.

---

## 6. Cost and timebox

Two weeks of calendar time, one arm at a time. **Hard stop.** If the bake-off runs long, the
tiebreak in §4 applies and we move — an unresolved control-plane decision blocks Phases 1
through 3, and the cost of deciding slowly exceeds the cost of deciding slightly wrong
behind an adapter we can swap.

---

## 7. Results

*(To be filled in during Phase 0.5. Record findings as they occur, including ones that
contradict the thesis in §1.)*

| Axis | OpenClaw | Hermes | Notes |
|---|---|---|---|
| Learning-loop lift (30) | — | — | |
| Memory quality (15) | — | — | |
| Node / device model (15) | — | — | |
| Harness ownership (15) | — | — | |
| Adapter fit (10) | — | — | |
| Safety posture (10) | — | — | |
| Operational cost (5) | — | — | |
| **Total** | **—** | **—** | |

**Decision:** _pending_ · **Recorded in:** `09-DECISIONS.md` D1
