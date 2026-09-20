# 16 — Model Topology: There Is No "Main Jarvis Model"

*Answers: "should our main Jarvis model be a fast large leading local model plus Jev, so we can
patch in and route to other models by voice?"*

---

## 1. The reframe

The instinct — local front + Jev + routing — is right. But the premise underneath it should be
dropped, because it's the one thing this architecture has avoided everywhere else:

> **Jarvis's identity is not a model. It's the core.**

The persona, the relationship, the boundaries, the way it talks, what it remembers, what it
refuses — all of that lives in the `identity` memory class, the policy engine and the Record
(doc 05 §4–5). Naming a "main model" couples the identity to a vendor, and then a model
deprecation is an identity change. That's exactly the lock-in the whole stack is built to
avoid.

What actually exists is a **topology of roles**, each filled by whatever currently serves it
best, with the persona constant across all of them.

---

## 2. The topology

| Role | What runs it | Where | Why this tier |
|---|---|---|---|
| **Voice front** | small-fast (3–8B) + STT + TTS | **local, resident** | Sub-second specific ack, barge-in, disambiguation, "what's my status" |
| **Decision layer** | **Jev** | hosted | Every bounded choice, 70–500 ms, ~free (doc 14) |
| **Subconscious** | mid local (14–32B) | **local, resident** | Consolidation, extraction, reranking — reads everything, so it must not leave (doc 12 §3) |
| **Reasoning** | frontier, routed | cloud | Actual thinking, hard coding, research |
| **Specialists** | Claude Code / Codex / etc. | local or cloud | Repo work behind harness adapters (doc 15) |

Five roles. No crown.

---

## 3. On "fast large leading local" — the tension worth naming

Those four words pull against each other. At 24 GB VRAM you're running a ~32B class model at
Q4. *Leading* is not local in 2026 without tier-D hardware, and even then you're trading
prefill throughput for capacity (doc 12 §5).

The good news is that **you don't need it to be**, because the ack path and the reasoning path
are different paths:

```
  "Jarvis, fix the failing build on jarvis-core."
        │
        ├─▶ local 8B  ──▶  "Starting on jarvis-core — the auth test."   ← <1s, specific
        │                   (R11: names the interpreted intent)
        │
        └─▶ Jev: route ──▶ frontier / Claude Code session ──▶ work happens
                                        │
                                        └─▶ output router ──▶ digest or notify
```

One voice, two paths. The local model's job is **conversation and speed**, not reasoning. A
*specific* acknowledgement is well within an 8B's ability when it's reading a parsed intent
plus the capability registry — and specificity is what makes misrouting cheap to catch (doc 05
§2).

**Where a bigger local model genuinely earns its cost:** reasoning over the Record itself
(which must not leave the machine), and offline resilience. Both are tier-D arguments, not
reasons to make it the default brain.

---

## 4. Routing by voice — automatic, with manual override

Both, and the second one is a real capability rather than a config file:

- **Automatic**: the router scores on capability match, measured success rate, health, latency,
  cost and privacy class (doc 05 §6.3). Jev makes the call in milliseconds. You never hear a
  framework name.
- **Manual override**: *"use Opus for this one"*, *"keep this local"*, *"don't send that to the
  cloud."* That's `route.pin` — a capability with a descriptor, scoped to a task or a session,
  logged in the Record like everything else.

The second matters more than it looks: **"keep this local" is a privacy control the user can
speak.** It should work mid-sentence and it should be honoured absolutely — a pinned-local task
that silently burst to cloud would be a serious breach of charter commitment 7.

---

## 5. What this commits us to testing

If identity lives in the core rather than a model, that's a claim we have to verify, not
assert. Add to `07-EVALUATION.md`:

- **Persona consistency across backends.** Same system prompt + same memory → the voice should
  read the same whether the local 8B is answering "what's my status" or a frontier model is
  answering something hard. Blind-rate responses from each backend for tone, verbosity,
  honesty about uncertainty, and refusal behaviour.
- **Route transparency.** The user can always ask "who did that?" and get an honest answer from
  the Record — without it being narrated unprompted.
- **`route.pin` enforcement.** A task pinned local never touches a cloud provider. Verified at
  the network layer, not by asking the model.
- **Ack specificity.** The acknowledgement names the interpreted intent, so misroutes surface
  in under a second rather than after the work.

---

## 6. The practical answer

**Yes** to a fast local front plus Jev, exactly as proposed.
**No** to that combination being "the main Jarvis model" — because there isn't one, and
building as though there is quietly recreates the vendor coupling we designed the core to
prevent.

Concretely, in build order:

| Phase | What's local | What's hosted |
|---|---|---|
| 0–1 | nothing (tier A: use the existing PC) | everything; Jev for decisions |
| 2 | STT, TTS, small-fast front | frontier reasoning, specialists |
| 3+ | + mid model for the subconscious | frontier reasoning, specialists |
| later | + bigger local model **if** privacy or offline resilience demands it | — |
