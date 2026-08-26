# 11 — The Record: Deep Memory as Execution Ledger

*The proposal: capture everything — main chats, subagent transcripts, thinking, every inline
edit — categorized, queryable, rollback-able, and usable as both a diagnostic tool and a
memory substrate, with a "subconscious" model helping to work it. This document says yes,
and then says the three things that make it work rather than becoming a swamp.*

---

## 1. The unification: this is the Audit Ledger

The most important structural claim in this document:

> **The Record and the Audit Ledger (`05-ARCHITECTURE.md` §8) are the same object.**
> One append-only event log. Many read projections.

They were specified separately, and building them separately would be a mistake — two write
paths over the same facts, guaranteed to diverge, doubling the most expensive infrastructure
in the system. They are not two systems. They are four *questions* asked of one log:

| Projection | Question it answers | Consumer |
|---|---|---|
| **Audit** | *Why did you do that? Under what authority?* | Policy engine, security review, R12 |
| **Recall** | *What happened, what did we decide, how did we do this?* | Foreground agent, the user |
| **Reconstruct** | *Put the world back the way it was at T.* | Rollback, checkpoints, forensics |
| **Consolidate** | *What is worth keeping, and what did we learn?* | Subconscious, sleep-time compute, D4 |

This is a genuine architectural win, not a tidy-up. The audit ledger has to be append-only,
independent of the runtimes, and tamper-evident **for safety reasons** (R12). Those are
exactly the properties a trustworthy deep memory needs anyway. Build it once, at safety
grade, and the memory system inherits integrity it would otherwise have to invent.

---

## 2. What Cursor actually does — and where we go past it

Worth being precise, because the reference point sets the bar. Cursor's checkpoints snapshot
modified files before significant agent changes and let you restore from any point in the
chat timeline. But their own docs are explicit about the limits:

- **Not version control.** Session-scoped and recent history only.
- **Automatically cleaned up.**
- **Manual edits aren't tracked** — only agent changes.

So Cursor gives you *session-scoped undo*. What's being described here is bigger: a
permanent, cross-session, queryable archive that the assistant can reason over. Cursor's
checkpoints are a session-shaped shadow of it. We're not copying the feature; we're building
the thing the feature is a slice of.

Which also means the hard parts Cursor sidesteps are ours: retention, deletion, indexing at
scale, and cross-session query.

---

## 3. Event taxonomy

Every entry is an immutable, content-addressed, causally-linked event. Categorisation
happens at write time — retrofitting structure onto an undifferentiated blob store is the
failure mode that turns deep memory into a swamp.

```
event {
  id            ULID                    # sortable, time-ordered
  ts            RFC3339 (monotonic seq) # ordering survives clock skew
  actor         user | agent:<id> | system | watcher:<id>
  session       session_id
  parent        event_id[]              # causal DAG, not a flat list
  kind          <see below>
  subject_keys  [<subject_id>]          # whose data is in here — drives §6 deletion
  payload_ref   blake3:<hash>           # content-addressed blob
  meta          { model, tokens, cost_usd, latency_ms, capability, policy_decision }
}
```

**Kinds**, grouped by projection relevance:

| Group | Kinds |
|---|---|
| Conversation | `user.turn` · `agent.turn` · `agent.reasoning` · `agent.ack` |
| Delegation | `subagent.spawn` · `subagent.result` · `subagent.error` |
| Tool use | `tool.call` · `tool.result` · `tool.error` |
| Mutation | `file.read` · `file.edit` (pre+post hash) · `file.create` · `file.delete` · `command.run` |
| Capability | `capability.invoke` · `policy.decision` · `approval.request` · `approval.grant` · `approval.deny` |
| Proactivity | `watch.fire` · `salience.score` · `delivery` · `delivery.outcome` |
| Memory | `memory.propose` · `memory.write` · `memory.forget` · `skill.draft` · `skill.approve` |
| Media | `audio.segment` · `screenshot` · `pov.capture` |
| System | `session.start` · `session.end` · `error` · `killswitch` · `health` |

Two design notes that matter later:

- **`parent` is a DAG, not a list.** With subagents running in parallel, a linear transcript
  is a lie. The causal graph is what makes "why did this happen" answerable.
- **`subject_keys` is not optional.** It is what makes §6 (forgetting) possible at all. Adding
  it later means rewriting the whole archive.

---

## 4. Storage math — the ambition is cheaper than it sounds

Rough sizing for a heavy day of use. These are order-of-magnitude, not precision.

| Stream | Raw / day | Stored / day | Per year |
|---|---|---|---|
| **Text** — turns, reasoning, tool I/O, logs | ~10 MB | ~2.5 MB (zstd ≈4×) | **~1 GB** |
| **Code state** — see note | — | diffs + refs only | **~0.1 GB / project** |
| **Voice** — Opus 24 kbps, 2 h of *post-wake* dialogue | ~22 MB | 22 MB | **~8 GB** |
| **Voice transcripts only** | — | ~3 KB | **~1 MB** |
| **Screenshots** — WebP q80, 2 h computer-use @ 6/min | ~216 MB | ~20 MB after dedup | **~7 GB** |
| **Indexes** — vectors (int8) + FTS + graph | — | — | **~3–5 GB** |

**The finding: text is free. Pixels and audio are the entire cost.**

A full-fidelity year of every word Jarvis and its subagents ever produced is about a
gigabyte. That is nothing — it fits in RAM. The storage question is not "can we afford deep
memory"; it is "what is the screenshot and audio retention policy," which is a policy
decision, not a hardware one.

Realistic total: **20–100 GB/year**, almost entirely determined by media retention. Five
years fits comfortably on a 2 TB NVMe with room to spare.

> **Note on code state — don't reinvent git.** Agent worktrees already produce a perfect
> content-addressed version history. The Record stores commit refs plus diffs of
> *uncommitted intermediate states* (the thing git doesn't see and Cursor throws away);
> git holds the blobs. This is the single largest storage saving available and it costs
> nothing.

---

## 5. Retention tiers

| Tier | Age | Contents | Medium |
|---|---|---|---|
| **Hot** | 0–90 d | Everything, full fidelity, fully indexed | NVMe |
| **Warm** | 90 d – 2 y | Text full · media keyframed and downsampled · indexes retained | Bulk SSD / HDD |
| **Cold** | 2 y+ | Text + summaries + embeddings · raw media dropped unless flagged | Archive + offsite |
| **Permanent** | — | Decisions, approvals, policy outcomes, audit records, approved skills, memory writes | Never expires |

The permanent tier is small — it's the *conclusions*, not the working. It's also the tier
that must survive a total loss of everything else, so it gets its own backup cadence.

---

## 6. The forgetting problem — and it is a real one

The charter commits to `forget()` working, and to every memory being deletable by hand.
That collides head-on with an append-only, content-addressed, deduplicated log. Blobs are
shared across events; you cannot delete one without breaking others; and rewriting an
append-only log destroys the tamper-evidence that makes it an audit ledger.

**The answer is crypto-shredding**, which is a solved pattern rather than a novel one:

- Every event's payload is encrypted at rest with a key derived per **subject** (a person, a
  project, a source, a session — whatever the deletion unit needs to be).
- Keys live in a separate keystore, indexed by `subject_keys`.
- `forget(subject)` destroys the key. The ciphertext stays; it becomes cryptographically
  meaningless. The log's structure, hashes and causal links survive intact.
- Destruction is itself an auditable event (`memory.forget`), so we can prove what was
  forgotten and when — which is exactly what "forgetting" in a trustworthy system requires.

This is recognised as valid erasure by the EDPB (Guidelines 5/2019), the UK ICO and CNIL,
given AES-256-class encryption, irreversible key destruction, and an audit trail. We are not
under GDPR obligation for a personal system, but the standard is the right one to hold — and
if bystander data is ever in the archive, the obligation may be real.

Derived artefacts are the trap: **embeddings, summaries and learned skills leak the content
they were derived from.** So the forget path must fan out — key destruction, plus index
tombstones, plus re-derivation of any summary or skill whose provenance names the destroyed
subject. Provenance on every memory write (already required by `05-ARCHITECTURE.md` §4) is
what makes that fan-out computable.

---

## 7. The Subconscious — right as a role, wrong as a fine-tune

The intuition is good: a background mind that knows the archive intimately and helps the
foreground one reach it. Two ways to build it, and the obvious one is the bad one.

**❌ Fine-tune a local model on the archive.** Bakes knowledge in lossily; stale the moment
a new session ends; hallucinates confidently about *your own history*, which is the worst
possible domain for confident invention; expensive to keep current; and it cannot honour
`forget()` — the deleted content is smeared irreversibly across the weights. That last point
alone disqualifies it under §6.

**✅ Retrieval and consolidation, with a small local model as the working mind.** Four
parts:

```
   THE RECORD           immutable, encrypted, content-addressed   ← ground truth
        │
        ▼
   THE INDEX            vector (int8) · full-text · causal graph · temporal
        │                       ▲
        │                       │ maintains, enriches, prunes
        ▼                       │
   RECALL  ◀────────────  THE SUBCONSCIOUS
   query-time:            idle-time: cheap local model, NARROW tools, NO egress
   plan → retrieve →      · consolidates episodes → candidate facts
   rerank → hand          · extracts SKILL.md drafts from successful traces (D4)
   EVIDENCE up            · mines failure patterns: "this breaks every time we…"
                          · writes multi-granularity summaries (session/day/week/project)
                          · pre-computes answers to likely questions
                          · maintains the index; prunes and re-embeds
```

This is sleep-time compute (`02-PROACTIVITY-RESEARCH.md` §3.6) pointed at the archive:
narrower tool set than the foreground agent, cheaper model, output to a review queue rather
than straight to canonical memory. It is current by construction, it can forget, and every
claim it makes is drillable to a source event.

**Where a fine-tune does earn its place** — and this is worth doing eventually: not on
*facts*, but on *judgment*. A small LoRA trained on our own accepted-vs-rejected routing
decisions, salience scores, and interruption outcomes could learn "when he says this, he
means that" and "this class of thing is worth interrupting for." That is style and policy,
regenerable from the Record, and it does not pretend to hold knowledge.

---

## 8. Recall is a capability, not an ambient ability

The single most dangerous thing in this document.

The Record is the **highest-value exfiltration target in the entire system** — every
conversation, every credential that ever appeared in a tool result, every private decision,
in one queryable place. If the foreground agent can query it freely, and that agent can be
steered by injected content (which is the whole premise of the Untrusted Ingest Rule), then
one hostile email can drain the archive. The literature already documents this class:
weaponizing agent memory for data exfiltration is a demonstrated attack, not a hypothetical.

So:

- **`memory.recall` is a capability descriptor** with an autonomy class, a scope, and an
  audit trail — not an ambient ability the model simply has.
- **Recall is scoped by default** to the current project and the last N sessions. Archive-wide
  search is a distinct, higher-class capability.
- **A quarantined agent gets no recall at all.** Not scoped recall — none. It has already
  been established that it may be under someone else's control.
- **The Subconscious has no network egress. Ever.** It reads the most sensitive store in the
  system; it must be structurally incapable of sending anything anywhere. Enforced at the
  network layer, verified by test, not by policy prompt.
- **Secret redaction happens at write time**, not read time. Tool results get scanned for
  credential patterns before the payload is stored. A secret that never enters the Record
  cannot leak from it.
- Every recall is itself an event. *"What has Jarvis looked up about me?"* must be
  answerable.

---

## 9. Rollback: be precise about what is reversible

Reconstruction is genuinely valuable and genuinely partial. Stating the boundary plainly
prevents a false sense of undo:

| Reversible | Compensatable | Irreversible |
|---|---|---|
| File edits, worktree state, config, memory writes, skill drafts | Sent messages (delete/retract), orders (cancel), commits (revert), calendar events | Anything a human read · money moved and settled · published content that was mirrored · a physical door that was opened |

`checkpoint(T)` restores the reversible column and **lists** the other two with their
compensating actions where they exist. It never silently implies the world went back.

This is also why the A3 autonomy class and Protocols exist: the deep archive gives excellent
*forensics* on irreversible actions, and no *undo* for them. Rollback is not a substitute
for the approval gate — a point worth holding onto, because a good undo story is exactly the
thing that tempts you to loosen the gate.

---

## 10. What this changes elsewhere

- `05-ARCHITECTURE.md` §8 — the Audit Ledger is redefined as the Audit *projection* of the
  Record. One write path.
- `05-ARCHITECTURE.md` §4 — canonical memory becomes a *derived, curated* store over the
  Record, with provenance pointing at source events. The Record is ground truth; memory is
  the conclusions.
- `06-ROADMAP.md` Phase 0 — the event schema, `subject_keys`, and per-subject encryption ship
  in Phase 0. They cannot be retrofitted.
- `07-EVALUATION.md` — add: recall scoping enforcement, subconscious egress isolation
  (verified at the network layer), forget-fanout correctness through derived artefacts, and
  write-time secret redaction.
