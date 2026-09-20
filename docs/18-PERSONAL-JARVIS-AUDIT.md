# 18 — Personal Jarvis: Audit Findings (D2)

**Run:** 2026-09-20 · **Commit:** `888df0c` (2026-09-19, *"Add private evidence-backed learning
loops for Jarvis agents (#185)"*) · **License:** Apache 2.0

**Scope caveat, stated up front:** this is the **static half** of the D2 checklist. No VM, no
microphone and no GPU were available, so the runtime items — test-suite pass rate, measured
wake-to-ack, and whether the critic loop improves outcomes — are **not** answered here. That
matters, because one of them is now the deciding criterion (§7).

---

## 1. Scale

| Metric | Value |
|---|---|
| Repository | 264 MB |
| Python files | 3,934 |
| Lines of Python | ~330,000 |
| Test files (`test_*.py`) | **2,176** |
| Last commit | one day before this audit |

The blueprint's read — *"substantially more engineered than a weekend voice + LLM demo"* — is
confirmed and if anything understated. A ~330k-line codebase with 2,176 test files is a serious
project. It is also moving fast, which cuts both ways (§6).

---

## 2. Self-modification — **PASS**, and better than expected

This was the decisive criterion, and the answer is unambiguous.

Generated skills go through a **forced draft lifecycle**, and the enforcement is in code with
an audit trail, not a convention:

> `jarvis/skills/authoring/draft_writer.py` — *"state=draft is ALWAYS forced. If the
> Jarvis-Agent-Author draft outputs `state != "draft"`, we note the override in the result
> (`forced_state_override=True`) — the caller writes that to the audit."*

The discipline is pervasive rather than a single checkpoint:

- `jarvis/society/learning.py` → `keep_draft()` *"preserves the draft lifecycle even inside the
  private namespace"*, and `promote_to_global()` copies a skill into the user's global skills
  directory **as a draft** — so even promotion does not activate.
- **184 occurrences of `draft`** across `jarvis/skills/`.
- Path-traversal defense-in-depth on skill slugs (`_resolve_clash_safe_slug`, `_resolved_target`).

**A model in this system cannot write itself a live capability.** That is exactly the property
D2's decision rule required and R13 demands, implemented about the way we would have.

### One caveat worth recording, not a violation
`jarvis/agent_chat/jarvis_harness.py` → `install_agy_jarvis_plugin()` writes `plugin.json` and
`mcp_config.json` into `<cwd>/.agents/plugins/…` so a print-mode sub-agent mounts Jarvis' own
tools. It is **workspace-scoped, additive, failure-tolerant, and explicitly does not touch the
global MCP config.** Still: it is a privilege-granting write performed automatically. In our
stack this belongs behind an explicit capability with an autonomy class, not as a silent
side-effect of starting a sub-agent. (A parallel path writes a marker-delimited block into
`.grok/config.toml` for Grok Build.)

---

## 3. Telemetry and outbound network — **clean**

- **No analytics phone-home.** Zero hits for PostHog, Sentry, Mixpanel, Amplitude or similar.
- `jarvis/telemetry/` is **performance instrumentation** — `latency.py`, `latency_log.py`,
  `replay.py`, `retention.py`. Local, and about the system's own speed.
- Every outbound host in the Python source resolves to a model provider (OpenAI, x.ai, Google,
  OpenRouter, Groq, Ollama, HuggingFace, ElevenLabs, Cartesia, NVIDIA), an integration target
  the user opts into (Discord, Slack, Spotify, Asana, GitHub), or a documentation/console URL.
  Nothing unexplained.

---

## 4. Secrets — **OS keyring, no plaintext**

`keyring` is used from `jarvis/core/config.py` and the provider plugins. A targeted grep for
API keys, tokens or passwords being written via `write_text` / `json.dump` returned **nothing**.
That matches the blueprint's claim and satisfies the credential-isolation principle.

---

## 5. Two modules that are ahead of our own design

### 5.1 Computer-use has the right shape
`jarvis/cu/` is `capture.py` → `target_guard.py` → `actuate/` → `verify.py` → `ledger.py`, plus
`indicator/`. That is capture, **guard the target**, act, **verify the result**, **record it** —
the action-verification discipline doc 05 §5 asks for, already built. `target_guard.py` binds
foreground window identity to the input coordinate space, which is the correct defense against
the classic computer-use failure of clicking the right coordinates in the wrong window.
`indicator/` suggests a visible capture indicator (charter commitment 4).

`jarvis/safety/` is a real policy layer, not a prompt: `approval.py`, `approval_surface.py`,
`command_impact.py`, `explicit_intent.py`, `risk_tier.py`, `tool_executor.py`.

### 5.2 Their retention module validates our storage math — in the field
`jarvis/telemetry/retention.py` sweeps screenshot blobs, content-addressed by sha256, and its
docstring contains the most useful number in this audit:

> *"without a retention sweep the directory grows without bound (**observed in the field: ~91k
> files / ~38 GB**)."*

That is empirical confirmation of doc 11 §4: **text is free, pixels are the entire cost.** Our
estimate of ~7 GB/year post-dedup is the same order as their field observation for a heavier
capture rate with no dedup.

Their solution is a blunt age sweep — delete blobs older than *N* days by mtime, with
`retention_days <= 0` meaning *off*, never *delete everything* (a good fail-safe). **That is
precisely the fixed policy D9 improves on**: adjudicated retention judges each item at day 30
on whether anything ever referenced it, instead of deleting on age alone. Independent evidence
that the problem is real and that the obvious answer leaves value on the floor.

---

## 6. Risks to carry forward

1. **Velocity.** Last commit one day before audit; the HEAD commit adds *learning loops*. A
   dependency this fast-moving must be **pinned**, and the pin must be re-audited on bump.
2. **Surface area.** `agent_accounts.py`, `agent_login_flow.py`, `claude_auth.py`,
   `claude_credentials.py`, `codex_auth.py`, `codex_login_guard.py`, per-provider quota state.
   It manages *provider account sessions*, which is a larger credential footprint than "reads an
   API key." Worth a dedicated pass before any adoption that isn't a sandboxed voice node.
3. **Automatic tool-grant writes** (§2 caveat) need an explicit capability in our stack.
4. **Cold start is slow.** `desktop-ttu-latest.json` reports median **voice-ready ≈ 12.8 s** and
   voice-usable ≈ 13.5 s from spawn, with the webserver constructor alone at ≈ 8.7 s. For an
   always-on service this is mostly irrelevant — but it is **not** the wake-to-ack number, and
   it must not be mistaken for one (§7).

---

## 7. Verdict: the static audit passes; **D2 is one measurement from closing**

Against D2's pre-registered decision rule:

| Criterion | Result |
|---|---|
| Self-modification into a live privileged process without a human diff → *design only* | **PASS** — drafts forced, overrides audited (§2) |
| Telemetry / outbound / secrets clean | **PASS** (§3, §4) |
| Wake-to-ack p95 > 1.2 s on our hardware → *design only* | **UNMEASURED** — needs a VM and a microphone |

The criterion that would have disqualified it did not fire, and the one that decides adoption
has not been measured. So the honest status is:

> **Static audit clean. The remaining question is per-utterance voice latency on our hardware —
> not the 12.8 s cold-start figure, which is a different measurement.**

**Recommended next step**, and it is small: stand up the pinned commit in a VM, run the test
suite for a pass rate, and measure wake → acknowledgement over ~50 utterances. If p95 lands
under 1.2 s, adopt it as a pinned voice node with skill authoring disabled at config and
verified by test. If not, take the pipeline design and implement it ourselves — which was
always the fallback and costs us little, because §5 shows the parts worth learning from are
legible in the source either way.

**Independent of the verdict, three things are worth stealing now:** the forced-draft skill
lifecycle (§2), the capture → guard → actuate → verify → ledger loop (§5.1), and the field
evidence that screenshot retention is the real storage problem (§5.2).
