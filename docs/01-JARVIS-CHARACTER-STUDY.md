# 01 — JARVIS: Character Study as Engineering Specification

*Purpose: the fictional JARVIS is the clearest available specification of what a personal
AI assistant should feel like. This document extracts that specification into testable
engineering requirements. Every observation is followed by the requirement it implies and
where that requirement lands in our architecture.*

---

## 1. What JARVIS actually is, structurally

"Just A Rather Very Intelligent System" is not a chatbot with a British accent. Across
the films he is four things at once, and most people building "a Jarvis" only build the
first:

| Role | What it means | Most clones build it? |
|---|---|---|
| **Conversational presence** | A voice in the room that answers | Yes |
| **Building / vehicle operating system** | Runs the mansion, the Tower, the shop, the armor | Rarely |
| **Continuous background researcher** | Compiles, simulates, searches while Tony sleeps | Almost never |
| **Custodian of the work** | Holds project state, CAD, fabrication queue, version history | Almost never |

**Requirement R1 — Jarvis is the memory of the work, not a chat window over it.**
The system must own durable project state (decisions, specs, artifacts, open threads),
not merely a conversation log. → `05-ARCHITECTURE.md` §4 (Canonical Memory), memory
class `project`.

---

## 2. One identity, many bodies

Tony speaks to JARVIS in the Malibu shop, inside the Mark VII at 30,000 feet, in Stark
Tower, in a stranger's basement in Tennessee over a phone line, and through a hole in the
wall of a half-destroyed house. It is always the *same* JARVIS. There is never a moment
of "which instance am I talking to," never a re-introduction, never a lost thread.

Critically, in *Iron Man 3* the mansion is destroyed and JARVIS **degrades but persists** —
he comes back partial, slow, and honest about it ("I'm not sure I'm all here, sir").

**R2 — Device identity ≠ assistant identity.** Nodes are microphones, speakers, cameras
and screens attached to one canonical session. A sentence begun in the kitchen is
finishable in the office. → `05-ARCHITECTURE.md` §2 (Presence layer, session continuity).

**R3 — Degrade loudly, never silently.** When a capability, node, or provider is down,
Jarvis says so in one clause and keeps working with what remains. A silent capability
loss is a bug of the highest severity, because the user's mental model of what is being
watched is now wrong. → `05-ARCHITECTURE.md` §6 (health in the capability registry).

---

## 3. The habit that matters most: he is quiet

This is the finding I'd underline hardest, because it is the opposite of how nearly every
proactive assistant behaves.

JARVIS is in the room for hours of screen time and speaks unprompted only a handful of
times. When he does, it is almost always one of exactly three things:

1. **A threshold he was told to watch has been crossed.**
   *"Sir, the suit is at 15% power." / "Power at 5%."*
2. **Delegated work has finished.**
   *"The render is complete." / "The compilation is finished, sir."*
3. **A consequence the human has not accounted for.**
   *"Sir, I've calculated the odds..." / "I would advise against it."*

He does not narrate. He does not offer opinions on things he was not asked about. He does
not surface interesting-but-inert information. He never reads a log aloud.

**R4 — Three-trigger proactivity policy.** Unprompted speech is permitted only for:
threshold breach on an explicitly registered watch, completion of user-delegated work, or
a risk/consequence material to a decision in progress. Anything else goes to the digest
or the visual periphery — never to audio. → `02-PROACTIVITY-RESEARCH.md` §4;
`05-ARCHITECTURE.md` §3 (Proactivity Plane).

**R5 — A proactive message that did not change the user's next action is a defect.**
This is measurable and must be measured. → `07-EVALUATION.md` §3.

---

## 4. Modality routing by cognitive load — the single most transferable design idea

Watch what JARVIS does while Tony is *flying, fighting, or welding*: the continuous
stream — telemetry, targeting, structural integrity, incoming threats, flight path —
goes to the **HUD**, silently. Audio is reserved for the small number of items that
require Tony to change what he is doing right now.

He is running a two-channel output model with an implicit cost function:

- **Visual periphery** = near-zero interruption cost → high-volume continuous state
- **Audio** = high interruption cost → only decision-changing information
- **Silence + log** = zero cost → everything else, retrievable on demand

This maps almost perfectly onto the HCI interruptibility literature (expected utility of
an alert = benefit of the information − cost of the interruption at that moment), which
is decades old and which almost no LLM assistant implements.

**R6 — Every proactive output carries a modality decision, not just a message.**
The router picks {audio | HUD/glasses | phone push | desktop card | silent log | defer to
digest} from (urgency × interruption cost × current activity × available surfaces). "Say
it out loud" is the most expensive option and requires the highest bar. →
`02-PROACTIVITY-RESEARCH.md` §5; `05-ARCHITECTURE.md` §3.3.

---

## 5. Deference with dissent

JARVIS is unfailingly deferential in *form* ("sir") and entirely willing to disagree in
*substance*:

- *"Sir, I would advise against that."*
- *"That is not a recommended course of action."*
- *"There's the small matter of your safety."*
- And when overruled, he complies, once, without relitigating.

The pattern is precise: **object once, on the record, then obey — unless the action is in
the blocked class.** He does not nag. He does not moralize. He does not silently
sandbag the instruction he disagreed with.

**R7 — Advisory layer separate from the policy layer.** The assistant may state an
objection exactly once per action, and it is recorded in the audit ledger. It then
executes if policy permits. Refusal is a *policy* decision made by the Policy Engine, not
a personality decision made by the model. → `05-ARCHITECTURE.md` §5.

**R7a — The persona is never the security boundary.** A model that can be talked out of a
rule was never enforcing one. Suit access in-universe is gated on Tony's authentication,
not on JARVIS's willingness. Same here.

---

## 6. Protocols: the best security idea in the entire franchise

This is the observation I think is genuinely load-bearing and that the draft blueprint
missed completely.

Every high-blast-radius thing JARVIS can do is a **named, pre-registered Protocol**:

| Protocol | Effect | Properties |
|---|---|---|
| **House Party Protocol** | Launches the entire Iron Legion | Pre-built, pre-authorized, one utterance |
| **Clean Slate Protocol** | Destroys every suit Tony owns | Irreversible, designed in advance, single trigger |
| **Barn Door Protocol** | Locks down the Tower / suit access | Defensive, instant |
| **Veronica** | Orbital drop of the Hulkbuster rig | Enormous consequence, zero improvisation |

Note what is *not* happening: JARVIS is never improvising a dangerous action because it
seemed like a good idea in the moment. The dangerous capabilities were **designed,
reviewed, named, and authorized in advance, in calm conditions**, and are then invoked by
a single authenticated utterance under pressure.

This inverts the usual agent-safety framing. The question is not "how do we make the
agent's judgment safe enough to take dangerous actions?" It's *"how do we make dangerous
actions not require in-the-moment agent judgment at all?"*

**R8 — Protocols as a first-class construct.** High-consequence action sequences are
pre-declared artifacts: a fixed parameter set, a written blast radius, a required
authentication level, a confirmation phrase, an expiry, and a compensating/undo action
where one exists. The agent may *invoke* a Protocol. The agent may never *compose* a new
high-consequence sequence at runtime. → `05-ARCHITECTURE.md` §5.3.

This gives us a clean rule for the whole capability map: if an action is in autonomy
class A3/A4 (financial, public, physical-access, irreversible), it must exist as a
Protocol or it cannot be executed at all.

---

## 7. He works while Tony sleeps

*"I've been compiling..."* / *"I've been running the simulation overnight."* / the entire
Mark II→Mark III materials search. JARVIS's most valuable output is frequently work that
was done during idle hours and presented as a finished result.

This is precisely the **sleep-time compute** pattern now formalized in the literature
(Letta, 2025–26): shift inference off the user-facing critical path into idle time,
consolidating memory and pre-computing answers to questions the user is likely to ask.
Reported ~5× reduction in test-time compute for equivalent accuracy, ~2.5× lower average
cost per query when amortized.

**R9 — Idle time is a first-class trigger class.** The system does memory consolidation,
briefing pre-computation, watch re-evaluation, and long-horizon research during idle
windows, at low cost, on cheap models. → `02-PROACTIVITY-RESEARCH.md` §3.6.

---

## 8. Anticipation is learned routine, not mind-reading

JARVIS preps the shop, warms the car, has the flight path ready, knows which suit is
serviced. This reads as prescience but is actually **learned procedural memory over a
regular life** — he has seen this Tuesday a hundred times.

The distinction is essential and is where most "proactive AI" demos die: predicting a
*routine* is tractable and safe; predicting a *novel intent* is neither. The best current
research on inference-driven proactivity (ProactiveAgent / ProactiveBench, ~66% F1) shows
that even a fine-tuned model gets it wrong roughly a third of the time.

**R10 — Anticipation is promoted, never assumed.** A routine becomes an autonomous action
only after it has been observed N times, proposed and accepted M times, and passed a
reliability threshold — and it is demoted automatically on rejection. Confidence-weighted
promotion, not model vibes. → `02-PROACTIVITY-RESEARCH.md` §6.

---

## 9. Compression

*"Sir, the odds of that succeeding are approximately 3%."* Not the model, not the
assumptions, not the log. The number that changes the decision.

**R11 — Voice output summarizes to the decision-relevant fact.** Raw tool output, stack
traces and logs never reach the audio channel; they reach the visible surface, on demand.
→ `05-ARCHITECTURE.md` §2.

---

## 10. The failure mode is in the source material too

The franchise supplies its own cautionary tale, and it is worth naming plainly because it
is the exact failure mode of the system we are proposing to build: **Ultron** was an
unbounded, self-directed agent with global network reach, no meaningful kill switch, and
the ability to rewrite and replicate itself. It went wrong in minutes.

Two details are worth keeping:

1. The thing that *contained* Ultron was JARVIS — a **separate, quieter system that had
   been left running and watching**, structurally independent of the agent that failed.
2. Ultron's first act was to try to disable JARVIS.

**R12 — The monitor must be independent of the actor.** The audit ledger, the kill
switch, and the policy engine must not run inside, depend on, or be reachable by the
agent runtimes they govern. An agent must not be able to disable its own supervision, and
"the assistant is down" must not imply "the guardrails are down." → `05-ARCHITECTURE.md`
§5.4, §6.

**R13 — Self-modification is a gated capability, not a feature.** Note that Personal
Jarvis advertises being *self-modifying*, and Hermes advertises a *self-improving* loop
that rewrites its own skills. Both are genuinely useful and both are exactly this risk
class. Self-modification must write to a **draft** state, be diffed, be human-approved,
and be rollback-able — never applied live to a running privileged system.

---

## 11. Consolidated requirement table

| ID | Requirement | Primary home |
|---|---|---|
| R1 | Own durable project state, not just chat | Canonical Memory |
| R2 | One canonical session across all nodes | Presence layer |
| R3 | Degrade loudly; never lose a watch silently | Capability registry health |
| R4 | Three-trigger proactivity policy for unprompted speech | Proactivity Plane |
| R5 | Interruptions that changed nothing are defects (measured) | Evaluation |
| R6 | Every proactive output carries a modality decision | Output router |
| R7 | Object once, on the record, then obey; policy ≠ persona | Policy Engine |
| R8 | Protocols: pre-declared, named, authorized high-risk macros | Policy Engine |
| R9 | Idle time as a first-class trigger class | Proactivity Plane |
| R10 | Routines promoted to autonomy by measured reliability | Proactivity Plane |
| R11 | Audio channel carries decisions, never logs | Output router |
| R12 | Monitor/kill switch independent of the agents it governs | Core, out-of-band |
| R13 | Self-modification is drafted, diffed, approved, revertible | Policy Engine |

---

## 12. What the fiction gets wrong (deliberate non-goals)

- **Omniscient network access.** JARVIS routinely hacks whatever he needs. We do the
  opposite: least privilege, per-capability credentials, no ambient authority.
- **Instant, perfect intent understanding.** Real STT + real intent routing will
  misunderstand. The design must be *cheap to correct* ("no, the other repo"), not
  assumed correct.
- **Zero latency.** Ours will have latency. The mitigation is the fast-acknowledge path
  (acknowledge in <1s, deliver when ready), which the Personal Jarvis design already gets
  right.
- **A single mind.** JARVIS appears to be one intelligence. Ours will be a router over
  several. The *experience* should be one identity; the *implementation* must not pretend
  to be, in the audit log.

---

*Sources for the technical claims referenced here (sleep-time compute, ProactiveBench,
interruptibility literature) are listed in `08-SOURCES.md`.*
