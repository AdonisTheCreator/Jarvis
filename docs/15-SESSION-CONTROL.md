# 15 — Session Control: Phone → Desktop, and the Coding Command Centre

*Answers: "Jarvis, start my task with Codex" · "patch me through to a voice chat with Codex in
X project" · "check on my terminal session with Claude and report back" · and "can we plug in
our coding platforms with Jarvis as orchestrator — Traycer on steroids?"*

*Short answer: yes, all of it, and it's one capability family rather than one integration per
tool. Two honest limits are named in §4.*

---

## 1. Lead with the part that's actually valuable

Remote **control** is the flashy version. Remote **awareness** is the one that changes a day.

You rarely want to drive Codex from a phone — typing by voice into a coding agent is slower
than waiting. What you want is:

> *"Codex has been sitting on an approval prompt for 22 minutes."*

That's a registered threshold watch (trigger class 3.3) on a session's state, delivered under
the three-trigger policy (R4), and answered with one utterance: *"approve it."* Blocked
sessions, failed test runs, and finished work are the highest-value proactive signals in the
whole system, because they're unambiguous, they cost real time when missed, and the trigger
input is trusted structured data.

So the build order inverts the intuition: **status and unblocking first, steering second,
voice bridge third.**

---

## 2. The abstraction: one `session.*` capability family

Not an integration per tool. One family, many adapters.

| Capability | Does | Autonomy |
|---|---|---|
| `session.list` | What's running, where, in what state | **A0** |
| `session.status` | One session: state, last activity, blocked-on, cost, diff size | **A0** |
| `session.create` | Start a session (harness, repo, branch, task, worktree) | **A1** in a sandboxed worktree |
| `session.send` | Inject a turn into a running session | **A2**, or **A3** if the target holds broad permissions |
| `session.stream` | Live event stream | **A0** |
| `session.interrupt` | Stop or redirect | **A1** |
| `session.attach_voice` | Duplex voice bridge (§5) | **A2** |
| `session.kill` | Terminate | **A1**, and reachable by the kill switch |

`session.send` deserves the scrutiny: it injects arbitrary instructions into a process running
with your credentials, from a phone, over a network. It is the highest-blast-radius capability
in this document and its class follows the *target*, not the verb.

---

## 3. Three adapter tiers — fidelity descending, coverage ascending

### Tier 1 — Native SDK (best fidelity)
**Claude Code → the Claude Agent SDK.** `query()` creates or resumes a session; the
`session_id` arrives in the first `SystemMessage` with `subtype === "init"`; pass
`resume: sessionId` to continue exactly where it left off. Options map onto the CLI flags —
`allowedTools`, `permissionMode`, `maxTurns`, `model`, `cwd`, `mcpServers`.

**The detail that matters most for us: the SDK exposes a programmatic approval callback.**
That is where the Policy Engine plugs in directly. A session dispatched from a phone inherits
*our* approval logic — autonomy classes, approval tokens, Protocols — rather than the
harness's defaults. We don't have to bolt policy on from outside; the seam already exists.
Hooks cover lifecycle gating on top.

Headless CLI equivalent: `-p/--print`, `--output-format stream-json`, `--continue`,
`--resume <id>`, `--allowedTools`, `--permission-mode`.

### Tier 2 — Headless CLI + session files
**Codex → `codex exec`**, with `codex exec resume --last` or `resume <session-id>`.

And a free win worth calling out: **every Codex session is already written to
`~/.codex/sessions/` as JSONL** — the full transcript, prompts, model responses, tool calls
and tool results, timestamped for replay. That is *precisely* the event stream doc 11 wants.
The adapter ingests JSONL → Record events. Same shape for Claude Code's `stream-json`.

**We do not have to instrument the harnesses to get the deep memory. They already emit it.**

The Rust **app-server** (Unix socket transport, resume/fork, remote SSH, sticky environments)
is the maturing programmatic surface here.

### Tier 3 — tmux (universal fallback)
```
tmux new-session -d -s codex-jarvis -c ~/src/jarvis
tmux send-keys -t codex-jarvis 'codex' Enter
tmux capture-pane -t codex-jarvis -p
```
Plus control mode (`tmux -C`) for a text protocol instead of a rendered terminal. This works
for *anything* — Claude, Codex, OpenCode, aider, a REPL, a build — and it crosses machines for
free, because tmux doesn't care where the client is:
`ssh jarvis-core 'tmux send-keys -t codex ...'`.

**One correctness trap:** `send-keys` is asynchronous — it returns when the keys are sent, not
when the command finishes. Never sleep a fixed interval and hope. Poll `capture-pane` for a
**marker you control** (append `; echo __JARVIS_DONE_$$`), or use the tier-1/2 event stream.

This tier is why a new coding tool is never blocked on us writing an adapter.

---

## 4. The two honest limits

**1. Live steering of a running Codex thread is not first-class yet.** Starting, resuming and
reading are solid; injecting a turn into an already-running thread is an open feature request
(a stable app-server protocol with `turn/start` / `turn/steer` against an existing
`thread_id`). Until it lands, Codex steering goes through tmux, which works but is brittle
against TUI changes. **Claude Code steering is good today** via the Agent SDK. Plan the
capability so the Codex adapter can swap from tmux to the protocol without touching callers.

**2. Voice is for steering and status, not for authoring.** Dictating code into a session is
slower than typing and much slower than letting the agent write it. The voice bridge earns its
place on *"what's the status," "approve it," "no, use the other branch," "stop."*

---

## 5. The voice bridge

`session.attach_voice` is a duplex bridge over a session handle — built once, works for every
harness that exposes a stream:

```
  phone mic → local STT → session.send ──▶ [ running session ]
                                                    │
  phone speaker ← TTS ← summarise ← session.stream ─┘
```

Two rules keep it usable:
- **Never pipe raw session output to TTS.** R11 — audio carries decisions, not logs. The
  bridge summarises: *"It's asking whether to drop the column. Say approve or deny."*
- **Barge-in maps to `session.interrupt`.** "Stop" must reach the session, not just the TTS.

---

## 6. "Traycer on steroids" — what we actually add

Traycer already does the part that's tedious: parallel worktree topology, harness ids
(`claude`, `codex`, `opencode`, `traycer`, `cursor`), agent-to-agent messaging, a CLI for
automation. **Don't rebuild it.** It's a class-4 runtime behind an adapter.

Our layer above and below is where the leverage is:

| Layer | What it adds |
|---|---|
| **Above** — capability router | Routes by *measured* success rate per task class, not by preference (doc 05 §6.3) |
| **Above** — Jev gate | Loop depth, reviewer persona, finding triage, stop signal — ms each (D10) |
| **Above** — policy | Protocols for dangerous ops; approval bound to action+params+expiry |
| **Above** — proactivity | Blocked/failed/finished sessions as registered watches; one status stream |
| **Above** — voice + phone | Every session reachable from any node, one canonical identity |
| **Below** — the Record | **One unified archive across every harness.** Codex JSONL + Claude `stream-json` + tmux captures, all normalised into one causal DAG |

That last row is the real differentiator, and it follows directly from D5. Today your history
is scattered across `~/.codex/sessions/`, Claude Code transcripts, Traycer boards and terminal
scrollback. Afterwards it's one queryable archive — *"what did we decide about the auth
refactor, in whichever tool we were using?"* becomes answerable.

**The compact state model** the user sees, regardless of how many sessions and providers were
involved:

```
PLANNING → IMPLEMENTING → TESTING → VISUAL QA → CRITIC REVIEW → READY → MERGED
```

*"What's the team doing?"* summarises bottlenecks and confidence. It never dumps logs.

---

## 7. Security — the part that needs real care

Injecting instructions into a credentialed process from a phone over a network is exactly the
shape of thing the Policy Engine exists for.

- **Network fabric is a private overlay** (Tailscale / WireGuard). Never an exposed port, never
  a public endpoint. The phone is an authenticated node on the gateway, nothing more.
- **Policy plugs into the harness, not around it** — via the Agent SDK approval callback (§3),
  so a phone-dispatched session cannot exceed what policy allows even if the harness would.
- **`session.send` class follows the target.** Sending into a sandboxed worktree session is
  A2. Sending into a session with shell and credentials on the primary account is A3, and A3
  means a Protocol.
- **The kill switch reaches sessions.** `session.kill` for every tracked session, out-of-band,
  independent of the runtimes (R12). Tested on the same schedule as everything else.
- **Session output is untrusted content.** A session that read a hostile file and can be
  steered from a phone closes the injection loop. Anything from `session.stream` that reaches
  a decision path goes through the Untrusted Ingest Rule — a `Proposal`, never an instruction.
- **Strong auth on the phone node** for anything above A1. A lost phone must not be a lost
  laptop.

---

## 8. Build order

| Step | Capability | Tier | Value |
|---|---|---|---|
| S1 | `session.list` / `status` + Record ingestion of Codex JSONL and Claude `stream-json` | 1–2 | Unified history immediately; no risk (A0) |
| S2 | Blocked / failed / finished session **watches** → digest, then notify | — | The actual daily win (§1) |
| S3 | `session.create` into a sandboxed worktree | 1–2 | "Start my task with Codex" |
| S4 | `session.send` + `interrupt`, policy-gated via the SDK approval callback | 1 | Unblocking by voice |
| S5 | tmux adapter as the universal fallback | 3 | Everything else, incl. cross-machine |
| S6 | `session.attach_voice` | — | "Patch me through" |
| S7 | Traycer adapter for multi-agent topology | 4 | Parallel teams, if needed |

S1 and S2 are worth building before anything in this document's title — they're A0/L1, they
need no steering, and they deliver the thing you'd actually notice.
