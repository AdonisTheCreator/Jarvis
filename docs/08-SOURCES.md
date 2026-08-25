# 08 — Sources

*Verification pass: 2026-08-25. Marked **[verified]** where checked against a primary
source (project repo / official docs) during this pass, **[reported]** where only strong
secondary sources were available. Two official doc hosts (`docs.openclaw.ai`,
`ironman.fandom.com`) were unreachable from this environment's network egress policy;
those claims were confirmed via repo READMEs and indexed doc excerpts instead and are
marked accordingly.*

## Agent OS / control planes
- **OpenClaw** — repo & README (Gateway as local control plane; channels; nodes; skills;
  plugin SDK; pairing approval; untrusted-inbound posture): https://github.com/openclaw/openclaw **[verified]**
- **OpenClaw docs** (agent runtimes, agent-harness plugin SDK, Codex harness ownership
  split, skills): https://docs.openclaw.ai/ — `concepts/agent-runtimes`,
  `plugins/sdk-agent-harness`, `plugins/codex-harness`, `tools/skills` **[verified via indexed excerpts; host blocked from this environment]**
- **OpenClaw scale / lineage** (100k+ stars; formerly Clawdbot/Moltbot): Milvus guide **[reported]**
- **OpenClaw skills registry scale** (5,400+ curated): https://github.com/VoltAgent/awesome-openclaw-skills **[reported]**
- **Hermes Agent** — repo & README (learning loop, 3-layer memory, FTS5 session search,
  Honcho user modeling, 7 terminal backends, cron, subagents, **OpenClaw migration
  importer**): https://github.com/nousresearch/hermes-agent **[verified]**
- **Hermes Agent docs**: https://hermes-agent.nousresearch.com/docs/ **[reported]**
- **Hermes self-evolution** (DSPy + GEPA over execution traces): https://github.com/NousResearch/hermes-agent-self-evolution **[verified]**
- **Personal Jarvis** — repo (Router-Brain dispatcher, harnesses, typed immutable EventBus,
  provider-agnostic, self-modifying): https://github.com/PersonalJarvis/PersonalJarvis · PyPI `personal-jarvis` **[verified]**

## Proactivity, ambient agents, memory
- **Proactive Agent: Shifting LLM Agents from Reactive Responses to Active Assistance** —
  ProactiveBench (6,790 events), fine-tuned F1 **66.47%**: https://arxiv.org/abs/2410.12361 · code: https://github.com/thunlp/ProactiveAgent **[verified]**
- **ProAgentBench** (real-world proactive assistance eval): https://arxiv.org/abs/2602.04482 **[reported]**
- **ProactiveEval** (unified eval framework for proactive dialogue): https://arxiv.org/pdf/2508.20973 **[reported]**
- **LangChain — Introducing ambient agents** (notify / question / review HITL patterns):
  https://www.langchain.com/blog/introducing-ambient-agents **[verified]**
- **LangChain Agent Inbox**: https://github.com/langchain-ai/agent-inbox **[verified]**
- **LangChain ambient-agent-101 / agents-from-scratch** (LangGraph persistence,
  checkpointing, resumability, platform cron): https://github.com/langchain-ai/ambient-agent-101 **[verified]**
- **Letta — Sleep-time Compute** (~5× less test-time compute for equal accuracy; ~2.5×
  lower amortized cost; background agent shares memory blocks, narrower tools, cheaper
  model): https://www.letta.com/blog/sleep-time-compute/ **[verified]**
- **Letta / MemGPT tiered memory** (core / recall / archival): Letta docs **[reported]**
- **Event-driven agent architecture** (70–90% latency reduction vs polling; zero idle
  cost): https://fast.io/resources/ai-agent-event-driven-architecture/ · https://atlan.com/know/event-driven-architecture-for-ai-agents/ **[reported]**

## Interruptibility / HCI
- **Attention-Sensitive Alerting** (Horvitz et al.) — expected utility of an alert =
  benefit − cost of interruption: https://arxiv.org/pdf/1301.6707 **[verified]**
- **Coordinates: Probabilistic Forecasting of Presence and Availability**: https://arxiv.org/pdf/1301.0573 **[verified]**
- **How Busy Are You? Predicting the Interruptibility Intensity of Mobile Users** (CHI'17): https://goodlife.aalto.fi/resources/pdfs/CHI17-predictinginterruptibility.pdf **[verified]**
- **Effects of intelligent notification management on users and their tasks** (SIGCHI): https://dl.acm.org/doi/10.1145/1357054.1357070 **[reported]**
- Nature Research Intelligence — user interruptibility & notification management (survey of
  breakpoint-deferral strategies) **[reported]**

## Security
- **The lethal trifecta** (private data + untrusted content + exfiltration vector;
  Willison's framing) and **OWASP 2026 Top 10 for Agentic Applications — ASI01 indirect
  prompt injection**: https://airia.com/blog/ai-security-in-2026-prompt-injection-the-lethal-trifecta-and-how-to-defend/ **[reported]**
- **The Promptware Kill Chain** (prompt injection → multistep malware delivery): https://arxiv.org/pdf/2601.09625 **[reported]**
- **Trojan Hippo: Weaponizing Agent Memory for Data Exfiltration**: https://arxiv.org/pdf/2605.01970 **[reported]** — directly relevant: our memory layer is an attack surface.

## Protocols
- **Survey of Agent Interoperability Protocols (MCP, ACP, A2A, ANP)**: https://arxiv.org/html/2505.02279v1 **[verified]**
- **MCP adoption** (~97M monthly SDK downloads; 10k–18k active servers), **A2A v1.0**
  (early 2026), **Agentic AI Foundation** under Linux Foundation (~190 orgs): https://www.mindstudio.ai/blog/six-agent-protocols-ai-builders-2026 · https://getstream.io/blog/ai-agent-protocols/ **[reported]**
- **agentskills.io / `SKILL.md`** portable skill format — referenced by Hermes as an open
  standard; OpenClaw skills use the same shape **[verified via project docs]**

## Devices and physical layer
- **Home Assistant wake words** — "Okay Nabu", **"Hey Jarvis"**, "Hey Mycroft": https://www.home-assistant.io/voice_control/about_wake_word/ **[verified]**
- **microWakeWord** (Kevin Ahrendt; on-device on ESPHome + Android companion, works
  locked/backgrounded): https://www.kevinahrendt.com/micro-wake-word **[verified]**
- **openWakeWord** (server-side for low-power satellites): Home Assistant voice docs **[verified]**
- **VisionClaw** — Meta Wearables DAT SDK (iOS/Android) + Gemini Live API + optional
  OpenClaw for actions: https://github.com/Intent-Lab/VisionClaw **[verified]**
- **Meta Ray-Ban Display / Device Access Toolkit** developer preview: https://developers.meta.com/blog/build-for-display-glasses/ **[reported — from source blueprint, not re-verified this pass]**
- **Brilliant Labs Halo** (open hardware/software glasses): https://brilliant.xyz/products/halo · https://docs.brilliant.xyz/halo/halo/ **[reported — from source blueprint]**
- **Tesla Fleet API** — vehicle commands; virtual vehicle key; **no steering/throttle/brake
  interface**: https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands **[reported — from source blueprint]**
- **Android `VoiceInteractionService`** (system-selected voice interactor, background
  hotword): https://developer.android.com/reference/android/service/voice/VoiceInteractionService **[reported — from source blueprint]**
- **Traycer CLI** (harness ids `claude|codex|opencode|traycer|cursor`; worktrees;
  agent-to-agent messaging): https://docs.traycer.ai/cli/commands **[verified via indexed excerpts]**

## Market context
- **ChatGPT Pulse** — overnight proactive briefings from chat history + connected
  Gmail/Calendar, presented as morning cards **[reported]**
- **Google Gemini Proactive Assistance**; reported Anthropic proactive assistant **[reported]**
- PCWorld, *Gemini, Claude, and ChatGPT are done waiting for your prompts* **[reported]**

## JARVIS (character reference)
- MCU wiki entries for **J.A.R.V.I.S.**, **House Party Protocol**, **Clean Slate Protocol**
  (marvelcinematicuniverse.fandom.com) **[reported — host blocked from this environment; behaviours in doc 01 are drawn from the films themselves]**
- Iron Man Wiki — J.A.R.V.I.S. capabilities overview **[reported]**

---

### Source-quality notes
1. The source blueprint's **"GREEN"** ratings mean *the platform API exists*, not that an
   adapter exists. Every GREEN row is still real integration work.
2. The blueprint's Appendix A transcript is archival and preserves earlier claims that the
   synthesis (and this document) supersede.
3. Every project in the "Agent OS" section is young and fast-moving. OpenClaw was renamed
   twice inside roughly a year. Treat all interface details as perishable — which is the
   argument for the adapter boundary in `05-ARCHITECTURE.md`.
