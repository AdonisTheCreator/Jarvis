# 17 — Routing Policy and the Model Cabinet

*Specced from a worked dialogue. It turns out to contain three mechanisms the architecture
didn't have — spoken policy authorship, position-scoped model rules, and the decision layer
acting as a **rule factory** rather than a rule substitute.*

---

## 1. The dialogue, annotated

```
USER    "Jarvis, can we run these new features on the budget app?"
                                          ← default tier loaded: local or Sonnet 5
JARVIS  "Yes sir. Would you like us to use Fable 5.1 for that?"
                                          ← [1] Jev: classify → coding.repository
                                              [2] Jev: is the default tier adequate?  LOW confidence
                                              [3] low confidence escalates → propose, don't assume

USER    "Absolutely. Also don't ask me next time — always use Fable 5.1 for coding tasks.
         Just make sure not to have it use Fable as a subagent class."
                                          ← [4] a POLICY WRITE, spoken
                                              [5] position-scoped exclusion

JARVIS  "Watching our costs is wise, sir. I'm wiping Fable from the subagents list.
         Would you like a manual override for specific uses?"
                                          ← [6] confirms the exact change, not a vague ack
                                              [7] narrates an inferred reason it was not told
                                              [8] offers the refinement the policy implies

USER    "Always — as long as it doesn't naturally end up that way, we're all good
         to use it on the specific tasks."
                                          ← [9] override beats exclusion; exclusion binds
                                              the ROUTER, not the user

JARVIS  "Very good, sir. Our Fable implementation is being used on the coding task."
```

Nine mechanisms in six lines. Five of them were already specced. Four were not.

---

## 2. The big one: the decision layer is a **rule factory**

This is the most important thing in the dialogue, and it closes the loop on doc 14 §10.

Before the user speaks, "which tier for this?" is a **judgment** over messy state — no rule
exists, so Jev decides. The moment the user says *"always use Fable 5.1 for coding tasks,"*
that judgment becomes a **deterministic rule**. Jev never decides it again.

```
  judgment ──▶ Jev decides ──▶ proposes ──▶ human answers ──▶ RULE WRITTEN
                    ▲                                              │
                    └──────────── no longer asked ◀────────────────┘
```

So the system doesn't just *use* rules where they fit — **it manufactures them from its own
decisions as you make choices.** Over time the Jev call volume falls, determinism rises, cost
falls, and latency falls. The decision layer is scaffolding that converts itself into
structure.

That is the promotion ladder (doc 02 §6) applied to routing, and it's the answer to "am I
overemphasizing Jev?" — **you use it where no rule exists yet, and it spends its life putting
itself out of a job.**

**A corollary worth designing for:** every rule records the Jev decision that preceded it and
the utterance that authorized it. So *"why does it always use Fable for coding?"* answers
itself from the Record, and a rule the user no longer wants is traceable to the moment they
asked for it.

---

## 3. Spoken policy authorship — `route.policy.*`

The user wrote system configuration by talking. That needs to be a first-class capability,
not a settings file someone edits later.

| Capability | Utterance | Autonomy |
|---|---|---|
| `route.policy.set` | "always use Fable 5.1 for coding tasks" | **A1** — reversible, logged |
| `route.policy.exclude` | "never Fable as a subagent" | **A1** |
| `route.policy.allow_override` | "but let me override per task" | **A1** |
| `route.policy.list` | "what are my routing rules?" | **A0** |
| `route.policy.clear` | "stop always using Fable for coding" | **A1** |
| `route.pin` (from D14) | "use Opus for this one" · "keep this local" | **A1** |

All A1: reversible, cheap to undo, enumerable on demand. **`route.policy.list` is not
optional** — a system that silently accumulates spoken rules becomes unpredictable, and R3
says a capability the user has lost track of is a bug.

### Parsing the utterance — the hybrid, precisely

This is the clean answer to *"Jev as a partial layer in tandem with Jarvis main."* That one
sentence needs three different components, and none of them can do the others' jobs:

```
  "always use Fable 5.1 for coding tasks, just don't use it as a subagent class"
                               │
   [ local small model ]  ─────┤  free text → structured draft policy
   generation                  │  (Jev structurally cannot do this — it writes no free text)
                               ▼
   [ Jev ]  ─────────────── does this parsed policy match what was said?
   validation                   {matches | drifts | ambiguous}          ← bounded, calibrated
                               │
                  ambiguous ───┴──▶ ask one clarifying question
                               ▼
   [ rule engine ]  ─────── write it. From now on it's deterministic.
   execution
```

**Generate with the LLM, validate with Jev, execute with a rule.** That's the hybrid pattern
generalized, and it's reusable anywhere free text has to become structure: skill drafts, watch
definitions, Protocol declarations, memory writes.

---

## 4. Position-scoped model rules — the Model Cabinet

*"Don't use it as a subagent class"* is a distinction our capability descriptor couldn't
express. A model can be welcome at the top of a task and unwelcome in fan-out, because
**subagents multiply**.

The arithmetic is why the instinct is right:

| Model | $/M in | $/M out | 8-way fan-out, relative |
|---|---|---|---|
| Fable 5.1 | $10.00 | $50.00 | **5× Sonnet** |
| Opus 5 | $5.00 | $25.00 | 2.5× |
| Sonnet 5 | $2.00 | $10.00 | 1× |
| Haiku 4.5 | $1.00 | $5.00 | 0.5× |

One Fable turn is a considered purchase. Eight parallel Fable subagents is a different order
of spending, for work that is usually narrower and more mechanical than the turn that spawned
it. So the cabinet is scoped by **position**, not just by model:

```yaml
model_policy:
  positions:
    primary:     { default: sonnet-5,  rules: [ {when: "task.class == coding.repository", use: fable-5-1} ] }
    subagent:    { default: sonnet-5,  deny: [fable-5-1] }        # ← the spoken exclusion
    critic:      { default: auto,      constraint: different_provider_than_builder }   # D10
    background:  { default: local,     deny: [fable-5-1, opus-5] }  # subconscious, watchers
  manual_override: allowed              # ← "always", from the dialogue
```

Four positions, because they have genuinely different economics and risk: **primary** (one
turn, high value), **subagent** (many, narrow), **critic** (must differ from the builder, D10),
**background** (unattended — and per doc 12 the least privileged thing in the system).

### Conflict detection is required, not optional

Two of these rules can fight. If Fable is denied at `subagent` and the D10 critic constraint
demands *a different provider than the builder*, a Fable-built task may find its legal critic
set empty. That must surface at policy-write time — *"that would leave no eligible critic when
Claude builds; shall I allow Fable as a critic but not a subagent?"* — and never at 2am as a
silent fallback to a same-provider critic.

Policy writes get a validation pass. Jev is well-shaped for it: `{consistent | conflicts |
underspecified}`.

---

## 5. Override beats exclusion — policy constrains the router, not the user

*"Always — as long as it doesn't naturally end up that way."*

That's a precise instruction and it deserves an explicit rule:

> **`route.policy.exclude` binds automatic selection. `route.pin` — a deliberate human choice —
> always wins.**

The user is not a thing the router is protecting itself from. An exclusion means *don't drift
into this*, not *I am forbidden from this*. The override is logged (so cost stays visible), and
it is not gated.

The one exception, and it's the general rule reasserting itself: an override cannot exceed an
**autonomy class**. "Use Fable for this" is a routing choice, A1. "Send the customer database
to a cloud model" is a privacy-class violation and the policy engine refuses it regardless of
who asked or how. **Routing preferences are preferences; policy is policy.**

---

## 6. Two behavioural rules the dialogue demonstrates

**Confirm the exact change, never a vague ack.** *"I'm wiping Fable from the subagents list"*
names the mutation. *"Done!"* would hide a misparse until it cost something. This is the
ack-specificity rule (doc 05 §2) applied to configuration.

**Narrate an inferred reason; act only on the stated one.** *"Watching our costs is wise"* —
the user never said cost. Inferring it and *saying it* is good: it exposes the assumption so it
can be corrected in one word. Inferring it and *acting on it* — quietly downgrading other
models to save money — would be exactly the R7 violation the architecture forbids. **Say the
inference out loud; execute only the instruction.**

The same line also shows the personality working correctly: it's warm, it's brief, and it's
doing real work (surfacing an assumption), not decorating.

---

## 7. What this adds elsewhere

- **`05-ARCHITECTURE.md` §6** — capability descriptors gain `model_policy` with the four
  positions and a `manual_override` flag.
- **`14-THE-DECISION-LAYER.md` §10** — §2 above is the missing half: Jev doesn't only replace
  rules where none fit, it *produces* them.
- **`02-PROACTIVITY-RESEARCH.md` §6** — routing policy is the ladder's first real instance: a
  proposal accepted once becomes a standing rule, demoted the moment the user overrides it
  twice in the other direction.
- **`07-EVALUATION.md`** — add: policy round-trip (utterance → parse → Jev validation → rule →
  observed routing matches the utterance), conflict detection (a policy that would empty the
  critic set is caught at write time), override precedence (`route.pin` beats an exclusion,
  never beats an autonomy class), and rule provenance (every rule traces to its utterance).
- **`11-THE-RECORD.md`** — `policy.write` joins the event taxonomy, carrying the utterance, the
  parse, the Jev validation, and the preceding decision.

---

## 8. Why this is a good first vertical slice

It exercises nearly the whole stack on something small and safe: voice in, Jev classification,
LLM parse, Jev validation, policy write, Record event, deterministic routing thereafter,
`route.policy.list` to inspect it, and a spoken undo. Every piece is A0/A1, nothing is
irreversible, and the failure mode is "it used the wrong model once."

If this slice works end to end, the architecture is real.
