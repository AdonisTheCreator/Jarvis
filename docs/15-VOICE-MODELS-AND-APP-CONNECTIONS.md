# 15 — Voice, model modes, devices and app connections

Logged 2026-09-06 from the project conversation. This is a consolidated design
record, not a verbatim transcript. D10 records the accepted direction. Features
below are proposed unless explicitly identified as part of the offline prototype.

## User intent

The user wants accurate local transcription with no per-minute service charge,
natural conversation, model selection by voice, and multiple background jobs while
remaining focused on creative work. The Astra demonstration inspired the experience;
it is not evidence that our integrations already work. The user is away from the
laptop, so hardware selection and live microphone testing remain pending.

The user also wants future apps they build to connect easily to Jarvis. Design
those apps for integration from the start rather than relying on UI automation alone.

## Accepted system shape

| Part | Direction |
|---|---|
| Wake detection | Small local detector; no large language model continuously running just to listen |
| Transcription | Local streaming model; select through voice/hardware measurements |
| Immediate acknowledgement | Local audio such as “Yessir”; acknowledgement is not proof work started |
| Everyday conversation | Capable local model if it passes correction, tool-use and latency tests |
| Hard reasoning | Explicit hosted modes, including Astra where authenticated and available |
| Execution | Scoped APIs/tools and native workers; browser/computer use when necessary |
| Identity and memory | Jarvis-owned, portable across models and devices |
| Coordination | Hermes first; one execution owner per job |

Local hearing is independent of the conversational model. Local-only mode excludes
cloud model routing; Astra is a hosted option, not a local download. Local inference
has hardware/electricity costs even without service fees. API and subscription
coverage must be verified for each supported integration.

## Transcription research snapshot

Research discussed 2026-09-06. Prices and capabilities are a dated snapshot, not a
benchmark or promise of current availability at implementation time.

| Candidate | Place in evaluation | Notes |
|---|---|---|
| Moonshine Voice | First lightweight local contender | On-device streaming; current streaming models MIT-licensed; legacy non-English non-streaming exceptions exist |
| NVIDIA Nemotron ASR Streaming English 0.6B | Second local contender for the core machine | Native streaming, configurable 80/160/560/1120 ms chunks; chunk size is not total response latency |
| Nemotron 3.5 ASR 0.6B | Multilingual extension if needed | NVIDIA recommends the English model for English-only use; not every listed language is ready without adaptation |
| Voxtral Mini 4B Realtime | Additional local contender | Apache 2.0 open weights; measure hardware demands |
| faster-whisper | Baseline | Offline model adapted to streaming with wrappers; not automatically the final voice engine |
| Deepgram Flux | Optional hosted conversational benchmark | Integrated turn detection; English rate seen: $0.0065/min ($0.39/hour) |
| Soniox | Optional inexpensive hosted comparison | Approx. $0.12/hour streaming equivalent; token/context usage can affect cost |
| ElevenLabs Scribe v2 Realtime | Optional hosted comparison | Listed $0.39/hour; advertised ~150 ms transcription latency is not end-to-end Jarvis latency |

The user's subsequent preference is **local transcription as the destination**.
No cloud benchmark upload is implicitly authorized by recording this shortlist.
At 60 billed hours, the listed Soniox and Flux rates imply about $7.20 and $23.40
respectively, excluding extras, reasoning and speech synthesis. Trial credits are
not an ongoing free service.

Proposed evaluation: 30–50 user recordings, replayed at original speaking speed,
with quiet/noisy conditions, pauses, corrections, numbers, negation and project
names (Jarvis, Traycer, Codex, Oikonomos). Measure word/entity accuracy, stable text
delay, false end-of-turn decisions and end-to-end reply/stop latency on target
hardware. No winner has been measured yet.

Example: “Have Claude work on the budget app… actually use Codex, and don't commit
anything yet.” Preserve the correction and negation. Partial transcripts are
revisable input, not independent authorized actions.

Seamless conversation also requires speech activity detection, turn-taking,
echo cancellation, interruption during playback, and actual worker cancellation.
Stopping spoken audio and stopping a submitted task are different operations.

## Model modes and continuity

Qwen3.5-9B is a provisional local conversation candidate mentioned in Hermes' local
guide, not a selected winner. Hardware, quantization, context length and concurrent
transcription/workers determine usable speed. A small model must pass reliable
tool selection and correction tests; otherwise keep listening local and offer an
explicit stronger model for complex work.

| Spoken control | Contract |
|---|---|
| “Use Astra with heavy reasoning” | Change foreground model and supported reasoning configuration |
| “Have Astra think through this” | Delegate one job without changing foreground conversation |
| “Go back to local” | Change foreground model back; do not silently cancel hosted jobs |
| “Local only for this conversation” | Block new cloud routing; disclose and resolve any already-running cloud work |
| “Which model am I talking to?” | Read actual runtime state, never infer from personality |

Desired exchange:

> User: “Jarvis?”
> Jarvis: “Yessir.”
> User: “Astra, heavy reasoning.”
> Jarvis: “Switching, sir.”
> Jarvis, after backend confirmation: “Astra is ready. What would you like to work on?”

“Heavy reasoning” is a friendly configuration alias. Confirm backend availability
before announcing readiness. Hermes supports switching configured providers/models
and delegating to other models; voice commands require our integration. Its docs
warn that switching model resets the prompt cache. Astra's API documents async
tools, mid-turn steering and reasoning updates; Hermes exposure of each remains
unverified.

Carry explicit constraints verbatim plus relevant conversation, task state and
summaries. Models do not share hidden internal reasoning. Never promise full
private reasoning capture or identical understanding after a model change.

## Listening surfaces

| Surface | Proposed route | Limitation |
|---|---|---|
| Home Assistant Voice Preview Edition | On-device “Hey Jarvis” wake; stream activated speech to local core | Bridge its pipeline to Jarvis; not automatic Hermes integration |
| Android | Home Assistant companion wake detection | Documented locked/background support; verify target device and battery behavior |
| iPhone | Assist shortcut, Siri invocation, widget or active conversation | Do not assume unrestricted custom background wake equivalent to Siri |
| Amazon Echo | Custom Alexa skill bridge | Normally Alexa wake + skill invocation; not replacement of its listening system |

One always-on core hosts transcription, conversation and background work. A sleeping
laptop cannot keep those jobs running. Remote phone access needs an authenticated
connection; local recognition alone supplies neither offline memory nor service
access. Phone-side cache and reconnection behavior need explicit design (doc 16,
flow 9). Preserve visible capture/mute behavior and the charter's bystander rules.

## Future apps: make integration an intentional product capability

User aspiration: “any possible app I make or anything can be connected really easily.”
Accepted engineering goal: a repeatable integration pattern for apps we own.
This does not imply universal access to third-party apps or zero integration work.

Proposed app contract, to implement and validate later:
- A versioned API, optionally exposed as MCP tools, for a small named capability set.
- Separate read/status, draft/preview and commit operations.
- Scoped authentication; app permissions remain authoritative.
- Stable resource IDs, schemas, explicit errors and verified operation receipts.
- Idempotency keys and status lookup for side-effecting operations.
- Progress/completion events or webhooks with replay/deduplication semantics.
- Declare cancel/undo support and the point beyond which an action is committed.
- An artifact link or preview Jarvis can return to the user.

Example future capabilities: budget summaries and draft recurring expenses;
music practice plans; creative-project references and versioned outlines.
These are proposed shapes, not existing app endpoints. Computer use is a useful
fallback for accessible UI-only workflows, with app-specific testing and evidence.

## Sources retained from the research conversation

- https://github.com/moonshine-ai/moonshine
- https://huggingface.co/nvidia/nemotron-speech-streaming-en-0.6b
- https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b
- https://huggingface.co/mistralai/Voxtral-Mini-4B-Realtime-2602
- https://github.com/SYSTRAN/faster-whisper
- https://developers.deepgram.com/docs/flux/quickstart
- https://deepgram.com/pricing
- https://soniox.com/docs/stt/rt/real-time-transcription
- https://soniox.com/pricing
- https://elevenlabs.io/pricing/api
- https://hermes-agent.nousresearch.com/docs/guides/local-llm-on-mac
- https://hermes-agent.nousresearch.com/docs/reference/faq
- https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation
- https://developers.openai.com/api/docs/guides/latest-model
- https://www.home-assistant.io/voice-pe/
- https://www.home-assistant.io/voice_control/android/
- https://www.home-assistant.io/voice_control/apple/
- https://developer.amazon.com/en-US/docs/alexa/custom-skills/understanding-how-users-invoke-custom-skills.html
