# 16 — Ten acceptance flows

Logged 2026-09-06. User endorsed these examples as the intended Jarvis experience.
These are proposed acceptance scenarios, not implemented integrations or passed
tests. Current runnable code tests only synthetic task lifecycle behavior.

## 1. Flights, dinner and a coding team

User asks for Singapore flights next month using their comfort/price preferences.
While the search runs, they request dinner-order and Traycer status, then change
the trip from seven to ten days. Jarvis acknowledges the change and handles all
three jobs independently.

Expected response: “Traycer finished; two tests failed. Dinner is confirmed for
6:15. I found three flights; award availability isn't verified yet.”

Architecture fit: yes, conditional on authenticated service access. Verify award
inventory, miles balance and cash fees separately from cash fares. A cart is not
an order. Status checks do not authorize checkout; an already-approved exact order
may be completed within that authority, otherwise ask for the concrete purchase.
Offer flight monitoring only as an option; do not create it without acceptance.

Failure test: a stale seven-day result arrives after the correction. Reject it by
request version. A failure in one job must not cancel its siblings.

## 2. Spoken software work and a scope change

User asks Traycer to build recurring expenses for Oikonomos, Claude Code implementing
and Codex reviewing, consistent with existing design. Mid-work: “Don't touch the
dashboard yet; start with settings.”

Expected response: isolated branch, revised specification, settings preview,
review findings, fixed timezone bug and relevant test evidence.

Architecture fit: yes; close to the initial coding milestone. Shared specs,
artifact references, worktree isolation and one execution owner per job are needed.

Failure test: agents continue the old specification or edit conflicting files.
Pause affected work, reconcile changes and issue a new specification version.
Acknowledgement alone does not apply the correction.

## 3. Switch model without losing the conversation

User discusses app pricing locally, requests Astra with heavy reasoning to challenge
assumptions, then asks to return to local after completion.

Expected behavior: explicit foreground switch or delegated-job semantics, confirmed
backend readiness, relevant context handoff and a summary returned to local.

Architecture fit: yes with context/state transfer. No shared hidden reasoning or
promise of identical understanding. Model changes do not erase tasks or authority.

Failure test: summarization drops “never charge for this feature.” Carry protected
explicit constraints verbatim alongside summaries. Report actual active model.

## 4. Protect a concentration session

User begins a ninety-minute writing session, asking Jarvis to watch deployment and
dinner and interrupt only when they are needed.

Expected behavior: background checks; nonurgent results delivered visually or held
for a digest. A failed deployment that leaves the existing version working is
reported with its actual impact, not automatically treated as an emergency.

Architecture fit: yes after watches and the interruption policy exist. Persist the
focus preference across model/device changes and enforce interruption budgets.

Failure test: every worker claims urgency. Workers supply facts; the central
delivery policy determines whether the user must be interrupted. Surface dead watches.

## 5. Meeting into coordinated work

With participants' agreement, Jarvis records product-meeting notes. Afterward the
user asks for draft tickets, roadmap comparison and a follow-up draft.

Expected response: distinguish four decisions, three ideas and one unresolved
disagreement; prepare drafts without inventing commitments.

Architecture fit: conditional on capture/transcription and document/task access.
Resolve recipients before any authorized sending.

Failure test: “Maybe Natalie could handle that” becomes an assignment. Preserve
discussion, proposal, decision and accepted responsibility as separate categories.

## 6. Stewardship analysis across finances and projects

User asks whether buying the Jarvis computer this month fits upcoming bills,
business commitments and their reserve policy. Two expenses lack final amounts;
user requests conservative estimates.

Expected behavior: calculate a range and reserve impact with deterministic arithmetic,
explicit assumptions, data coverage and freshness. No purchase is implied.

Architecture fit: conditional on reliable authorized financial records. This is
scenario analysis, not a claim of complete financial visibility.

Failure test: missing account or recent transaction changes the conclusion. Expose
the missing coverage; do not present uncertain inputs as confirmed balances.

## 7. A household routine follows the conversation between rooms

In the kitchen: “I'm leaving in fifteen minutes; get the house ready.” In the office:
“Natalie's staying; leave her room alone.”

Expected behavior: invoke a predefined routine, update its scope, respond on the
appropriate device and preserve unaffected household preferences.

Architecture fit: conditional on supported home controls, device/session continuity
and an explicit identity strategy. A familiar voice alone is not sensitive authority.

Failure test: multiple microphones execute the same command twice, or the wrong
speaker is assumed. Deduplicate across devices and track request ownership.

## 8. Creative collaboration across references and tools

User asks for First Tribe materials, opening-scene contradictions and three stronger
expedition motivations. They choose option two and ask for a revised outline and
shot-list draft while preserving the riverbank scene.

Expected behavior: versioned drafts, preserved protected scene and a clear list of
downstream continuity implications.

Architecture fit: yes for accessible documents. Specific editing-app operation is
conditional on supported APIs or a separately tested computer-use workflow.

Failure test: an agent “improves” away an intentional choice. Preserve requirements,
diffs and recoverable versions. Creative judgment remains a proposal.

## 9. Phone assistance during connection loss

User requests a saved hotel address and asks to shift tomorrow's plan an hour later.
The connection to the core drops. The calendar changes elsewhere before reconnection.

Expected response: give the locally cached address if available; mark the change as
queued, not applied. Reconcile the latest calendar and flag the new conflict before
performing the change.

Architecture fit: partial; explicitly add phone cache, authenticated reconnect,
local fallback behavior and a durable action queue. Local STT alone is insufficient.

Failure test: “done” is said before submission, or reconnect duplicates an action.
Track queued/submitted/confirmed/uncertain states and reconcile before retry.

## 10. Selectively stop a multi-app chain

User: “Stop everything related to Singapore. Keep the coding team running.” Flight
search, an authorized price watch and possibly a submitted booking are in flight.

Expected response: search/watch stopped only when confirmed; coding continues;
submitted booking status is checked and reported separately.

Architecture fit: mandatory design requirement, not a guaranteed rollback. Group
related tasks and propagate cancellation to every descendant. Record commitment
boundaries and declared compensation support.

Failure test: cancelling local waiting is reported as stopping external execution.
Report unknown until reconciled. A completed booking may require a separate,
possibly costly cancellation; do not pretend it was never submitted.

## Cross-cutting requirements

| Requirement | Observable outcome |
|---|---|
| Independent jobs | Foreground conversation remains responsive |
| Versioned instructions | Corrections invalidate stale work/results |
| Shared task record | Models/devices agree on state and constraints |
| Evidence-backed status | Done/ordered/stopped requires a receipt or verification |
| Scoped authority | Read, draft, commit and cancel are separate operations |
| Reconciliation | Timeout/restart does not trigger blind duplicate execution |
| Delivery policy | Results interrupt only when warranted |
| Context handoff | Important constraints survive model changes |

First live end-to-end scenarios: **1, 2, 3 and 10**, starting with disposable fixtures
and simulated external purchases. No real booking or checkout is required to test
those contracts. Later extend to actual services under explicit scoped authority.

Design gaps made explicit by this exercise: phone offline operation, cross-device
handoff, selective task-group cancellation, instruction revisions, and committed
external action reconciliation. The existing offline coordinator is not claimed
to implement all of these.
