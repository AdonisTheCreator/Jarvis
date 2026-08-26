# 13 — Integration Triage

*"There's so many things we could explore" is true, and it is also how stacks die. This is a
decision procedure so that exploring stays cheap and committing stays deliberate. Six
classes, ordered by what they cost us — not by how interesting they are.*

---

## The rule

For any new thing X — a model, a tool, a framework, a product — ask **what layer does X want
to own?** The layer determines the cost, and the cost determines the bar.

| # | X is a… | Where it goes | Cost to add | Cost to remove | Bar to clear |
|---|---|---|---|---|---|
| 1 | **Model / provider** | Config behind the router | ~1 hour | ~0 | *Just add it.* Route by measurement. |
| 2 | **Tool or service** | MCP server, or an adapter | Hours–days | Low | A capability actually needs it |
| 3 | **Capability packaging** | `SKILL.md` | Hours | ~0 | It's a workflow we repeat |
| 4 | **Runtime / harness** | Harness adapter behind the control plane | 1–2 weeks | Medium | A measured task class where it wins |
| 5 | **Control plane / agent OS** | **Competes with the one we have** | Re-architecture | Very high | Bake-off only (doc 10) |
| 6 | Wants to own **memory, identity, policy or the ledger** | **Nowhere** | — | — | **No.** Core-owned, non-negotiable |

Two properties make this work:

- **Classes 1–3 are nearly free.** Explore freely, constantly, without ceremony. Adding a
  provider or writing a skill is an afternoon, and removing it costs nothing. Most curiosity
  should land here.
- **Classes 5–6 are where projects die.** Every "let's also use Y" that turns out to be a
  class 5 is a second router, and every class 6 is a piece of the system we no longer own.

**The failure mode this prevents:** something arrives looking like class 1 ("it's just a
better model") and turns out to be class 5 ("…which comes with its own agent runtime,
memory, and channel integrations"). Classify by *what it wants to own*, not by how it's
marketed.

---

## Worked example: Grok

The question was whether Grok deserves a place in the stack once it has an API. It has had
one for a while — Grok 4.6 at 500K context, roughly $2/M in and $6/M out, plus built-in
tools and a realtime Voice Agent API. So the real question is *which class is it?*

It's three separate things wearing one name, and they land in three different rows:

**1. Grok-as-model → class 1. Add it.**
A provider config line. The router already scores backends on capability match, measured
success rate, latency and cost; Grok becomes another candidate and earns traffic by
performing. No architectural discussion required. This is exactly the case the router exists
to make boring — and the reason routing must never be by product name.

**2. Grok-as-X-search → class 2, and genuinely differentiated.**
Native realtime X/social search (~$5/1K calls) is a capability **nothing else in the stack
can serve.** That's a real capability descriptor — `research.social_realtime` — not a model
preference. This is the strongest argument for Grok and it has nothing to do with how good
the model is. Worth noting the boundary carefully: social content is *maximally* untrusted
input, so this capability runs under the Untrusted Ingest Rule with no exceptions.

**3. Grok-as-voice-agent → class 1, but read doc 12 §4 first.**
The realtime Voice Agent API at **$3.00/hour** is a legitimate option for the voice layer and
a useful benchmark for what local STT/TTS has to beat. But 2 hours/day comes to ~$2,190/year,
which buys the GPU outright in under a year — and cloud realtime voice means the always-on
microphone path terminates at someone else's server. Fine as a bridge before tier C hardware
exists; not the destination.

**Verdict:** add as a provider now (free), design `research.social_realtime` as a capability
when a real question needs it, and treat the voice API as a stopgap rather than a plan.

---

## Applying it to things already in play

| Thing | Class | Status |
|---|---|---|
| Claude / OpenAI / Gemini / Grok models | 1 | Add freely; route by measurement |
| Home Assistant | 2 | Adapter. Its automations *are* our threshold watches |
| Tesla Fleet API | 2 | Adapter, phase 7, A3 actions behind Protocols |
| Traycer | 4 | Only if parallel worktree topology needs it |
| Claude Code / Codex | 4 | Harness adapters, phase 4, measured per task class |
| LangGraph | 4 | Durable execution substrate only — never a second router |
| Letta | 6 → rejected as product, adopted as pattern | Sleep-time compute is ours (D4) |
| OpenClaw / Hermes | 5 | Bake-off, doc 10 |
| Personal Jarvis | 5 if adopted whole, 2 as a voice node | Audit first (D2) |
| VisionClaw | 2 | Sensor node pattern; reference implementation |

---

## The standing question for anything new

> **What breaks if we remove it in six months?**

Class 1–3: nothing. Class 4: we lose an adapter and re-route. Class 5: we re-architect.
Class 6: we lose something we can't get back.

If the honest answer is 5 or 6, it goes through a bake-off with a rubric fixed in advance —
never through enthusiasm, and never through a demo.
