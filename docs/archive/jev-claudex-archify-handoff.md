# Archive — Jev / Claudex Loop / Archify handoff (2026-09-19)

> Source of record for `docs/14-THE-DECISION-LAYER.md`. Extracted verbatim from
> `Jarvis_Handoff_Jev_Claudex_Archify.pdf`. Vendor figures are claims, not verified results —
> the handoff says so itself and doc 14 preserves the labelling.

---


Jarvis Handoff: Jev, Claudex Loop & Archify
As of September 19, 2026 · Harrison
Purpose
This is a briefing for Jarvis on three tools Harrison researched in September 2026: Jev, Claudex Loop, and
Archify. The main takeaway: pair a fast decision model (Jev) with slower generative models, and use it to gate
expensive loops rather than replace them.
Treat the vendor numbers below as claims, not verified results. Where a figure comes from the vendor or a
single community benchmark, it is labeled that way.
Jev: what it is
Jev is a "System One" model from TypeSafe AI, released in early access on September 15, 2026. It returns
decisions, not text: you send it state plus questions with predefined answer options, and it returns typed
answers with calibrated probabilities.

Maker: TypeSafe AI, founded by Diogo Almeida, a former OpenAI researcher and RLHF co-inventor.

Training: synthetic data only, using a method TypeSafe calls Reinforcement Learning for Calibrated
Decisions (RLCD).

Speed and cost (vendor claims): roughly 70500 ms per response and about 100× faster and cheaper
than LLMs on suitable tasks. Output tokens are free; input is priced per billion tokens.

Parallel questions: several questions in one request are evaluated in parallel, so extra questions add little
latency.
Limits

It cannot write free text, such as tool arguments or search queries.

TypeSafe itself reports weaker accuracy on multi-step reasoning.

"Can't hallucinate" only means it can't invent outputs outside the predefined options. It can still pick the
wrong option.
Core design pattern
Jev picks the action; a small fast LLM writes any arguments; a strong LLM handles open-ended reasoning.
The WebMCP benchmark showed why this works: most of the difficulty in agent tasks is choosing the right
action, not writing the arguments.
On that benchmark, Jev plus Mercury 2.5 solved 49 of 49 tasks at about 112× lower model cost than GPT-6
Astra doing computer use with code execution. Jev replaced Astra there; it didn't speed Astra up. Without
WebMCP's structured tools, Jev solved only 25 of 49.
Jev: what builders are making
A handful of patterns dominate the community directory at madewithjev.com, which listed 42 builds in the
agents category alone as of September 19, 2026.


----- PAGE -----


Pattern
Example
Reported result
Model routing for coding
agents
jev-router routes each Claude Code or Codex turn to a
fast, balanced, strong, or long tier
Simple work goes to cheap models;
Astra only when needed
Model routing for coding
agents
jev-codex-router picks model, reasoning depth and
speed per turn
About 60% cheaper than always using a
frontier model (237-turn replay)
Model, tool and subagent
routing
JevRouter: one Jev decision over models, skills, MCP
tools and subagents, wrapped in hard permission
checks
Installs as an MCP server for Claude
Code or Codex
Browser and computer use
Browser Use + Jev, Stagehand + Jev, screenshot-free
Mac computer use
~90300 ms per decision; tasks for
fractions of a cent
Guardrails
Bouncer, pi-heed, Interlock check each agent tool call
against policy or the user's request
Bouncer reports about $0.04/day
Bulk judgment
Job crawler that finds and scores career pages
~5 min with an LLM vs ~20 s with Jev
Skill pre-routing
Slack agent classifies the right skill and tool before the
main agent runs
~2× faster
Most of these numbers are from the builders themselves and haven't been independently checked.
Claudex Loop: what it is
Claudex Loop is a Claude Code skill set, packaged by Chase AI, that makes two different model providers
check each other's work. The rule it enforces: whoever built it never grades it.
1
Recon and interview: the host conversation gathers requirements.
2
Plan hardening: Claude drafts PLAN.md; Codex attacks it; Claude revises. This repeats up to 5 rounds, a
deliberate hard cap, or until approval.
3
Build: either Claude or Codex builds (builder=claude or builder=codex).
4
Inspection: the other provider reviews the code. Blocked runs and exhausted round budgets surface as
failures, never as approval.
Each run produces PLAN.md (the what) and PLAN-REVIEW-LOG.md (the round-by-round why). A
claudex-route skill recommends models, such as Luna for focused fixtures, Terra for bounded
implementation, and Astra or Fable for hard reviews.
On its first greenfield run (a solo-creator CRM), the loop logged 55 findings across 5 rounds, converging 26,
15, 12, 2, 0, including one fatal architecture flaw.
Related: promptadvisers/claudex runs a similar loop through a Claude Code Stop hook with a different
reviewer persona each round. axeldelafosse/loop can run Claude and Codex reviews in parallel; an issue
both reviewers find is a stronger signal to fix.
Claudex Loop: proposed Jev gate
The proposed upgrade is to put Jev in front of the loop so the expensive plan-build-inspect cycle runs only
where it pays off. More rounds or more models mostly add cost; smarter triggering is the better lever.
Flow

Incoming change goes to Jev, which decides loop depth.


----- PAGE -----



Trivial: ship with no review. Moderate: single cross-model review. Risky: full Claudex Loop.

Inside the full loop, Jev triages each finding (must fix / nice to have / noise), then decides whether to stop.
Jev would make four small decisions, each in milliseconds:
1
Loop depth: full loop, single review, or none for this change.
2
Reviewer persona: senior engineer, security and data integrity, or ops.
3
Finding triage: each finding labeled must-fix, nice-to-have, or noise.
4
Stop signal: whether the loop has converged enough to end early.
Low-confidence Jev answers should fall back to the more thorough path, never the cheaper one.
Archify
Verdict: Archify is mainly for human understanding; it is optional for Jarvis. For moving between apps, a short,
maintained ARCHITECTURE.md or CLAUDE.md in each repo gives most of the benefit for free.
The main tool is tt-a1i/archify, an MIT-licensed agent skill for Cursor, Claude Code, Codex and OpenCode.
The agent writes a typed JSON description of components and relationships. Archify checks every component
against the actual source code, then renders a self-contained interactive HTML/SVG map.

Fail-closed: if the agent invents a component, validation fails with diagnostics instead of drawing a wrong
diagram.

Repo evidence: nodes link to the exact file and line range that proves they exist.

Architecture Delta: compares Before, Delta and After snapshots, useful for PR review.
A different project, Aryan1718/Archify (npx archify-cli init), generates architecture docs and a grounded
context pack for Codex or Claude Code. Worth checking which one a given reference means.
Suggested test: run it for about 20 minutes on the largest repo. If the map doesn't show anything new, drop it.
Design principles for Jarvis

Split decide from generate. Use Jev for bounded choices (route, classify, gate, check) and LLMs for
reasoning and writing.

Keep reviewers independent. The model that reviews must come from a different provider than the one
that built.

Use confidence thresholds. Below a set confidence, escalate to a stronger model or a human.

Fail open for speed, fail closed for safety. If routing fails, fall back to the default model rather than
blocking. If a guardrail check fails, block the action.

Structure the action space. Jev does much better choosing from clean, well-named tools than from raw
UI elements (49/49 vs 25/49 on WebMCP).

Measure before trusting. Replay real sessions to check savings and accuracy; most published figures
are self-reported.
Open questions


----- PAGE -----



Which Jarvis decisions are frequent and bounded enough to hand to Jev first?

Where do the Super Coder and Traycer workflows sit relative to the Claudex Loop gate?

What confidence threshold should trigger escalation, and does it differ by decision type?

Does Jev's early-access status and API availability support a daily-driver setup yet?
Sources

TypeSafe AI: Introducing System One Models and Jev
https://typesafe.ai/blog/introducing-system-one-models-and-jev

heise online: AI model Jev
https://www.heise.de/en/news/AI-model-Jev-to-make-machines-decide-faster-11457071.html

TechCrunch: A new kind of AI model from a ChatGPT inventor
https://techcrunch.com/2026/09/18/a-new-kind-of-ai-model-from-a-chatgpt-inventor-is-thrilling-developers/

The Register: TypeSafe AI debuts model for machines
https://www.theregister.com/ai-and-ml/2026/09/16/typesafe-ai-debuts-model-for-machines-that-plays-doom/5296711

LangChain: Building a harness with Jev
https://www.langchain.com/blog/building-a-harness-with-jev

Made with Jev: Agents and browsers
https://madewithjev.com/categories/agents-and-browsers

jev-router
https://github.com/gargpratyush/jev-router

jev-codex-router
https://github.com/0xNatoshi/jev-codex-router

JevRouter
https://github.com/BillionsBobby/JevRouter

chaseai-yt/claudex-loop
https://github.com/chaseai-yt/claudex-loop

Chase AI: Claudex Loop
https://www.chaseai.io/blog/claudex-loop-claude-code-plan-review

promptadvisers/claudex
https://github.com/promptadvisers/claudex

axeldelafosse/loop
https://github.com/axeldelafosse/loop

tt-a1i/archify
https://github.com/tt-a1i/archify

Better Stack: Archify
https://betterstack.com/community/guides/ai/archify-architecture/

Aryan1718/Archify
https://github.com/Aryan1718/Archify


----- PAGE -----


