# 19 — The Timeless Codebase

*The idea: keep every version, decision and code change logged, and make the whole of it
queryable across time — where a bug entered, how the ecosystem evolved, what an older version
did, answered in milliseconds. This document says what git already gives you for free, what
the Record adds that git structurally cannot, and where the decision layer turns "possible in
principle" into "fast enough to do casually."*

---

## 1. Be precise about what's already solved

Git is very good at this and pretending otherwise would design the wrong thing:

| Question | Git already answers it |
|---|---|
| Which commit broke this? | `git bisect` — O(log n) builds |
| When did this string appear or vanish? | `git log -S` (pickaxe) |
| Who last touched this line and why? | `git blame` + commit message |
| What did this file look like in March? | `git show <rev>:<path>` |
| What changed between releases? | `git diff v1.6..v1.7` |

So the Timeless Codebase is **not** "version history." That exists, it's free, and it's
excellent. The value is in the layer git has no access to.

---

## 2. What the Record adds that git structurally cannot

> **`git bisect` finds which *commit* broke it. The Record finds which *decision* broke it —
> and the reasoning that produced it.**

That sentence is the whole product. Five things the Record holds that git never sees:

1. **The why, not just the what.** The conversation that produced the change, the reasoning
   trace, the alternatives considered and rejected, the review findings, the policy decision
   and approval, and *the failed attempts that were never committed.* A commit message is a
   lossy one-line summary of a two-hour argument.
2. **The uncommitted intermediate states.** Every edit an agent made and reverted; the three
   approaches tried before the fourth worked. Cursor throws these away at session end; git
   never had them. They're often the most informative record of *why* the final shape is what
   it is.
3. **Cross-repo and cross-tool.** Git is per-repository. The Record spans every repo, every
   harness (Codex JSONL, Claude `stream-json`, tmux captures — doc 15 §3), every session, and
   the non-code decisions that shaped them. *"What did we decide about auth, in whichever tool
   we happened to be using?"* has no git equivalent.
4. **The causal DAG.** Which subagent produced which edit, under which parent decision, with
   which model, under which routing policy. With parallel subagents a linear history is a
   fiction; the DAG is what actually happened.
5. **Decision provenance for non-code.** The Model Cabinet rules, watch definitions, Protocol
   declarations, memory writes — and the utterance that authorized each.

---

## 3. Queries this makes possible

Grouped by what they're actually for. The ones marked **⚡** are the ones git cannot answer at
any speed.

### Forensics
- ⚡ *"This auth bug — what were we thinking when we wrote that branch?"* → the commit, plus the
  conversation, the rejected alternative, and the review that passed it.
- ⚡ *"Did we already try this fix and revert it?"* → the uncommitted intermediates.
- *"Which commit introduced the regression?"* → bisect, but **pre-ranked** (§4.1).
- ⚡ *"Was this failure seen before?"* → dedupe against every prior failure across all repos.

### Evolution
- ⚡ *"How has our approach to error handling changed over 18 months?"* → decisions over time,
  not diffs.
- ⚡ *"Which decisions have we quietly reversed without noticing?"* → supersession detection
  (§4.5). **This is the one I'd expect to be most uncomfortable and most valuable.**
- ⚡ *"What does the code do now that no decision authorizes?"* → drift detection (§4.9).
- *"Show me every risky change to payments this quarter."* → change-intent classification.

### Reuse
- ⚡ *"How did we do rate limiting in the old service?"* → the implementation **and** why it
  was shaped that way, so you inherit the reasoning, not just the code.
- ⚡ *"Which of these 40 prior versions is the right reference for what I'm doing now?"*

### Health
- ⚡ *"Which subsystem generates the most rework?"* → edits-per-outcome across history.
- ⚡ *"Are we getting better?"* → review findings per change, over time, by subsystem.

---

## 4. Where the decision layer earns its place

Historical queries fan out over thousands of candidates. That is *exactly* the shape where a
70–500 ms bounded decision at $0.042/M changes what's feasible — not because it's smarter than
a frontier model, but because it's cheap enough to run **per candidate**.

Each entry below passes both tests from doc 14 §10 (not decidable by code; input not already
structured), and each has a deterministic fallback.

| # | Decision | Options | Why not a rule | Fallback |
|---|---|---|---|---|
| 4.1 | **Bisect pre-ranking** — could this commit plausibly cause this symptom? | `likely` / `unlikely` / `impossible` | Requires relating a symptom to a diff's semantics | Plain `git bisect` |
| 4.2 | **Regression dedupe** — is this the same failure as a past one? | `same` / `related` / `novel` | Error text varies; the *failure* is the same | Exact hash match only |
| 4.3 | **Change intent** at write time | `feature`/`fix`/`refactor`/`perf`/`docs`/`revert`/`risky` | Commit messages lie and conventions drift | Conventional-commit prefix if present |
| 4.4 | **Blast radius** — which subsystems does this touch? | bounded subsystem set | Import graph gives files, not *meaning* | Directory mapping |
| 4.5 | **Supersession** — does this decision contradict an earlier one? | `supersedes` / `refines` / `conflicts` / `unrelated` | Pure judgment over two prose decisions | None — flag for human review |
| 4.6 | **Retrieval rerank** — which 12 of 500 candidates matter? | rank | The whole point is relevance | Vector score alone |
| 4.7 | **Reference selection** — which prior version is the right model? | rank | Depends on the *current* intent | Most recent |
| 4.8 | **Flake vs. real** | `flake` / `real` / `unknown` | Pattern over history, not a threshold | `real` (fail closed) |
| 4.9 | **Drift** — does the code still match the decision that authorized it? | `consistent` / `drifted` / `superseded` | Semantic comparison of prose to code | None — periodic human review |
| 4.10 | **Root-cause direction** — where to look first | bounded subsystem set | Symptom→subsystem is learned, not derivable | Blast radius of recent changes |

**4.5 deserves special mention.** *"We decided the opposite of this in March"* is the failure
mode of every long-lived project, it is invisible by construction, and no tool currently
catches it. Running every new decision against the decision history at 200 tokens a comparison
makes it a background job that costs pennies. That is the most genuinely novel thing in this
document.

### The economics that make it casual
Reranking 500 historical candidates at ~200 tokens each = 100k tokens = **$0.004**. Half a cent
per deep historical query. Supersession-checking every new decision against 2,000 prior ones,
monthly: ~$0.02.

**That's what "in milliseconds" actually requires** — not a faster index, but a judgment cheap
enough to spend per candidate instead of per query.

---

## 5. How it's built — no new infrastructure

This is not a new system. It's **three projections of the Record** (D5), plus an index:

```
   THE RECORD  ─── append-only, content-addressed, causal DAG, per-subject encrypted
        │
        ├─▶ Reconstruct  ──▶  "what did the world look like at T"
        ├─▶ Recall       ──▶  semantic + FTS + graph query over all of it
        └─▶ Consolidate  ──▶  the subconscious, building the indexes that make §3 fast
                                 (idle-time, cheap model, narrow tools, NO egress)
```

Two implementation rules carried from earlier docs:

- **Don't reinvent git.** Commit refs + diffs of uncommitted intermediates. Git holds the
  blobs; the Record holds the meaning and the pointer. (doc 11 §4)
- **The harnesses already emit it.** Codex writes full JSONL transcripts to
  `~/.codex/sessions/`; Claude Code emits `stream-json`. We normalise into the DAG; we do not
  instrument. (doc 15 §3, D13)

So the Timeless Codebase is **mostly already funded** by decisions already made. What it adds
specifically: the code-aware index (symbol → history, subsystem → decisions), the ten decision
points in §4, and the query surface.

---

## 6. Honest limits

- **Recall is a scoped capability** (D6). A query that ranges over the entire archive is a
  higher autonomy class than one scoped to the current project, and a quarantined agent gets
  none. The Timeless Codebase makes the archive *more* valuable, which makes it a *bigger*
  exfiltration target — the constraint tightens as the feature gets better.
- **`forget()` must reach it.** Crypto-shredding renders payloads unreadable, but embeddings,
  summaries and the code-aware index are derived artefacts that leak their source. The forget
  fan-out (doc 11 §6) covers them or the guarantee is a lie.
- **Calibration is per-decision-type.** 4.5 (supersession) and 4.8 (flake) will calibrate very
  differently. Thresholds come from our measured reliability diagrams, never the vendor's
  (D9). A decision type that calibrates badly gets demoted to a rule or escalated.
- **It's only as good as what's in it.** The Record starts empty. The first six months are an
  investment with no visible payoff, which is exactly the kind of thing that gets skipped.
  Hence the schema is Phase 0 (D5): you cannot retrofit the history you didn't keep.

---

## 7. Why this is the strongest argument for the whole architecture

Everything else here has a plausible substitute. You could buy an assistant, rent an agent
runtime, use someone else's memory layer. But **nobody can sell you your own history**, and it
compounds: the archive is worth more in year three than year one, and it is the one asset in
this project that cannot be acquired, only accumulated.

That is also why the boring Phase 0 work — event schema, causal DAG, `subject_keys`,
per-subject encryption — is the highest-leverage code in the repository. Every day it doesn't
exist is a day of history that can never be recovered.
