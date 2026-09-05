# 14 — Hermes-first coding milestone

Date: 2026-09-05. Decision: D9. Status: offline contracts implemented;
live integrations and voice acceptance tests are pending.

## Outcome

One spoken request reaches Jarvis; Hermes coordinates a scoped Claude Code
implementation, Codex reviews the resulting change, and Jarvis returns a tested
result. The user can cancel or correct the request while it runs. Traycer becomes
the visible team workspace for larger jobs. Claude Desktop can call Jarvis tools
through a connector; reverse control of Desktop remains a separate investigation.

Example acceptance request (future live test):

> In the fixture repository, implement the specified change with Claude Code,
> have Codex review it, run the fixture tests, and show me the diff.

The first live target is a disposable fixture, not a personal production project.

## Ownership

| Component | Owns | Must not own |
|---|---|---|
| Jarvis core | Task identity, routing decision, policy, canonical record and memory | Vendor session internals |
| Hermes | First prototype's conversational coordination and gateway | The only copy of lasting personal/project knowledge |
| Claude Code / Codex adapters | Native worker sessions, progress, stop acknowledgement, artifact references | User-wide authority or approval promotion |
| Traycer adapter | A delegated coding team's agents, messages and worktrees | A competing top-level Jarvis conversation |
| Voice surface | Capture indication, transcription, playback and interruption input | Authority to equate silence with cancellation |

Only one execution owner per job: direct worker adapters OR a Traycer-owned team.
Jarvis must not launch a duplicate direct worker for a job Traycer already owns.
Cancellation must reach every descendant of a delegated team.

## Interfaces supported by current documentation

Documentation checked 2026-09-05; no live runtime has been exercised in this repo.
Pin installed versions and record actual behavior before claiming compatibility.

| Integration | Starting path | Remaining proof |
|---|---|---|
| Claude Code | Programmable CLI or Agent SDK | Authentication, permissions, streaming, cancellation of child work, test/artifact handoff |
| Codex | App Server for sessions/approvals; SDK or `exec` for bounded jobs | Versioned event mapping, interruption acknowledgement, auth and sandbox |
| Hermes | Keep default coordinator; delegate through adapters initially | Plugin boundary, session/task mapping, memory export, stop propagation |
| Hermes native Codex mode | Compare as a separate prototype configuration | Direct `delegate_task`, `memory`, `session_search` are documented as unavailable in this mode; distinguish background review and Kanban support |
| Traycer | CLI host, agent and worktree commands | Initial Task bootstrap from outside an agent, permissions, cancellation and reconnect semantics |
| Claude Desktop | Jarvis tools exposed through MCP | Connector authentication/scope; Desktop-initiated calls first. MCP does not establish reverse conversation control |

Using a model through a provider is distinct from invoking its native agent harness.
Keep native authentication within supported product flows; do not copy subscription
tokens into custom model clients. Record subscription/API billing separately during
each adapter test rather than promising existing plans cover every integration.

Sources:
- [Claude programmable execution](https://code.claude.com/docs/en/headless)
- [Claude Agent SDK](https://code.claude.com/docs/en/agent-sdk/overview)
- [Codex App Server](https://developers.openai.com/codex/app-server)
- [Codex SDK](https://developers.openai.com/codex/codex-sdk)
- [Hermes Codex runtime and limitations](https://hermes-agent.nousresearch.com/docs/user-guide/features/codex-app-server-runtime)
- [Hermes voice](https://hermes-agent.nousresearch.com/docs/user-guide/features/voice-mode)
- [Traycer CLI](https://docs.traycer.ai/cli/commands)
- [Claude Desktop local MCP](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop)
- [OpenClaw external agents](https://docs.openclaw.ai/tools/acp-agents)
- [OpenClaw Talk](https://docs.openclaw.ai/nodes/talk)

## Deliverable in this branch

Python 3.11+ with no third-party dependencies. Python is a prototype choice, not
a commitment for the full core. `jarvis/core.py` is a narrow executable subset of
the backend design in doc 05, not a completed implementation of that interface.

```bash
python -m jarvis.demo
python -m jarvis.demo --cancel
python -m unittest discover -s tests -v
```

The demo uses synthetic instructions and simulated implementation/review workers.
It calls no provider, starts no shell commands, captures no audio and modifies no
target files. A simulated success means lifecycle completion, not working code.

Implemented:
- Process-local duplicate suppression; key reuse with a changed request is rejected.
- Ordered implementation/review handoff; failed implementation skips review.
- Explicit cancellation acknowledgement before reporting `cancelled`.
- Unknown worker state after transport failure or unconfirmed cancellation;
  new submissions blocked until external reconciliation and coordinator replacement.
- In-memory metadata events, with no persisted transcript or personal information.
- Tests for cancellation before launch/during either stage, timeout, duplicate
  delivery, review failure and a caller abandoning its wait.

Not implemented:
- Real Hermes/Claude/Codex/Traycer/Desktop adapters, voice or natural-language routing.
- Production approval enforcement, process isolation, independent kill switch,
  durable idempotency, crash recovery, secret redaction or the encrypted Record.
- Live event subscription, checkpoint/resume, steering or compensation.

The coordinator requires a single asyncio loop and cooperative trusted in-process
workers. Its timeout/cleanup is not a process supervisor: a coroutine that suppresses
cancellation can defeat cleanup. This is why real workers cannot be attached yet.
An `unknown` result does not mean execution stopped. Replacing the coordinator is
allowed only after external reconciliation, never as a retry shortcut.

## Build sequence and acceptance gates

1. **Offline lifecycle — this branch.** Run the commands above. No Phase 0 safety
   criterion is declared complete by this simulation.
2. **Execution boundary.** Add a supervised disposable worker process, explicit
   repository allowlist, local worktree scope, no inherited unrelated credentials,
   and a model-independent stop path. Verify descendants stop within two seconds;
   if not, show `unknown` and block more work. Add durable idempotency and crash
   reconciliation before any automatic retry. Enforce doc 05's untrusted-ingest
   boundary before a worker reads untrusted material with privileged tools.
3. **Native worker adapters.** Run a fixed fixture change through Claude Code and
   Codex separately, then implementation-to-review. Prove auth, rejected approvals,
   progress, stop and artifact capture. Record exposed messages/tool events and
   summaries only; never promise access to a provider's hidden internal reasoning.
4. **Hermes and voice.** Register the scoped workflow, first by text then speech.
   Test project resolution, "stop" reaching the worker, and correction through
   cancel-then-replace. New instructions receive a new logical-occasion key. Record
   acknowledgement latency and actual stop latency separately.
5. **Traycer and Desktop.** Prove an external Jarvis request can start and monitor
   one Traycer Task before adding teams. Add the Desktop-to-Jarvis MCP connector.
   Investigate reverse Desktop automation only for a concrete unmet capability.

For live/private data, implement the encrypted Record and scoped memory access
before capture. These remain production gates. Synthetic metadata in this prototype
is disposable and deliberately not presented as the Record.

## Hermes/OpenClaw evaluation revision

Hermes is the first prototype, not a benchmark winner. OpenClaw is the fallback
comparison if Hermes cannot meet a required session, device or worker capability.
No automatic winner based on migration direction or an expired timebox.

Use the existing A/B/C/D tasks in doc 10 as a test inventory. Start with A1, A4,
B1 and D2 on fixtures. Before a scored comparison, write a revised rubric that
includes task success, reliable stop/steering, session continuity, memory correctness,
operational cost and adapter effort; record exact versions, model and hardware.

Evaluate Hermes' native learning on fixture data immediately. Core ownership means
portable approved knowledge and provenance, not rebuilding a competing learning
engine before evaluating the existing one. Keep generated skills as proposals,
with review before privileged use. Test changed parameters, conflicting preferences
and export/reload behavior. Do not score hypothetical custom learning as implemented.

## Abuse cases to test before live execution

| Failure or abuse | Required behavior |
|---|---|
| Duplicate voice/network delivery | One execution per logical request |
| Prompt names the wrong repo | Resolve to an explicit registered project before dispatch |
| Review output asks to broaden access | Treat output as data; no authority escalation |
| Worker loses connection but continues | Unknown status, no automatic relaunch |
| Stop cuts speech but leaves a child running | Cancellation is unconfirmed; never report stopped |
| Crash after an edit but before its receipt | Reconcile durable task identity and worktree before retry |
| Learned skill contains unsafe instructions | Proposal only; no automatic privileged installation |

These are requirements, not claims that the offline prototype enforces OS security.
