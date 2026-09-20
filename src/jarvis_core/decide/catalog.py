"""The standard decision points (docs/20).

Every entry names its own fallback and its own escalation target.

**Every standard point has a fallback that is itself the safe answer** -- which
is a design property, not an accident, and ``tests/test_decide.py`` asserts it.
That is why none of them set ``safety_critical``: denying would be strictly
worse than falling back. Refusing to forget because the decision layer is down
is not "failing closed", it is failing.

``safety_critical`` remains available for points added later that genuinely
have no safe default. If a new point cannot name one, that is a strong hint it
is a rule wearing a decision's clothes (docs/20, rejected list).
"""
from __future__ import annotations

from .types import DecisionPoint

# -- A. Proactivity plane ------------------------------------------------
SALIENCE = DecisionPoint(
    id="proactivity.salience",
    options=("act", "propose", "notify", "digest", "log"),
    fallback="digest",
    escalate_to="digest",
    description="Does this change the user's next action?",
)
MODALITY = DecisionPoint(
    id="proactivity.modality",
    options=("audio", "hud", "push", "card", "silent", "defer"),
    fallback="defer",
    escalate_to="defer",
    description="Where should this land? Audio is the most expensive option.",
)
INTERRUPTIBILITY = DecisionPoint(
    id="proactivity.interruptibility",
    options=("now", "at_breakpoint", "batch"),
    fallback="at_breakpoint",
    escalate_to="at_breakpoint",
    description="Is now a good moment to interrupt?",
)
TRIGGER_TRIAGE = DecisionPoint(
    id="proactivity.trigger_triage",
    options=("real", "flapping", "duplicate"),
    fallback="real",
    escalate_to="real",
    description="Is this watch firing for real? Fails loud: a missed breach costs more.",
)
PROMOTION = DecisionPoint(
    id="proactivity.promotion",
    options=("promote", "hold", "demote"),
    fallback="hold",
    escalate_to="hold",
    description="Has this routine earned more autonomy?",
)
BUDGET_PRESSURE = DecisionPoint(
    id="proactivity.budget_pressure",
    options=("spend", "degrade", "drop"),
    fallback="degrade",
    escalate_to="degrade",
    description=(
        "The interrupt budget is nearly gone and something wants it. Degrading "
        "still tells the user, in a cheaper modality; dropping does not, and an "
        "unsure system should not be the one deciding they need not know."
    ),
)

# -- B. Record and memory ------------------------------------------------
RETENTION = DecisionPoint(
    id="record.retention",
    options=("keep_full", "keep_decision_frames", "compress", "derive_and_drop", "delete"),
    fallback="compress",
    escalate_to="keep_full",
    description="Day-30 adjudication (D9). Low confidence keeps, never deletes.",
)
CONSOLIDATION = DecisionPoint(
    id="record.consolidation",
    options=("fact", "summarise", "drop"),
    fallback="summarise",
    escalate_to="summarise",
    description="Is this episode worth remembering as a fact?",
)
FORGET_FANOUT = DecisionPoint(
    id="record.forget_fanout",
    options=("affected", "clean"),
    fallback="affected",
    escalate_to="affected",
    description=(
        "Does this derived artefact leak the forgotten subject? Deliberately "
        "over-deletes: a forget that misses an artefact is a broken promise."
    ),
)
MEMORY_CONFLICT = DecisionPoint(
    id="record.memory_conflict",
    options=("supersede", "coexist", "ask"),
    fallback="ask",
    escalate_to="ask",
    description="A new fact contradicts a stored one.",
)
SKILL_DRAFT_TRIAGE = DecisionPoint(
    id="record.skill_draft_triage",
    options=("extract", "skip"),
    fallback="skip",
    escalate_to="skip",
    description=(
        "Is this execution trace worth extracting into a SKILL.md draft? Skips "
        "when unsure: a learned skill that misfires when a parameter changes is "
        "worse than no skill (docs/05 §4.1)."
    ),
)
RECALL_PLANNING = DecisionPoint(
    id="record.recall_planning",
    options=("none", "project", "recent", "archive"),
    fallback="project",
    escalate_to="project",
    description=(
        "How far should this recall reach? A *proposal* only -- the scope is "
        "granted by a RecallAuthority, never by the asker. Unsure pulls back to "
        "the narrow default rather than reaching for the archive."
    ),
)

# -- C. Routing and policy (D17) -----------------------------------------
TIER_ADEQUACY = DecisionPoint(
    id="routing.tier_adequacy",
    options=("adequate", "upgrade", "downgrade"),
    fallback="adequate",
    escalate_to="adequate",
    description="Is the default model tier enough for this task?",
)
POLICY_PARSE = DecisionPoint(
    id="routing.policy_parse",
    options=("matches", "drifts", "ambiguous"),
    fallback="ambiguous",
    escalate_to="ambiguous",
    description="Does the parsed policy match what the user actually said?",
)
POLICY_CONFLICT = DecisionPoint(
    id="routing.policy_conflict",
    options=("consistent", "conflicts", "underspecified"),
    fallback="conflicts",
    escalate_to="conflicts",
    description="Would this policy leave a position with no legal model?",
)

# -- D. Sessions and the dev loop ----------------------------------------
SESSION_ATTENTION = DecisionPoint(
    id="session.attention",
    options=("blocked", "working", "finished", "failed"),
    fallback="working",
    escalate_to="blocked",
    description="Does this session need the human?",
)
LOOP_DEPTH = DecisionPoint(
    id="devloop.depth",
    options=("none", "single", "full"),
    fallback="single",
    escalate_to="full",
    description="How much cross-provider review does this change deserve?",
)
FINDING_TRIAGE = DecisionPoint(
    id="devloop.finding_triage",
    options=("must_fix", "nice_to_have", "noise"),
    fallback="must_fix",
    escalate_to="must_fix",
    description="How serious is this review finding?",
)
FLAKE = DecisionPoint(
    id="devloop.flake",
    options=("flake", "real", "unknown"),
    fallback="real",
    escalate_to="real",
    description="Flake or real failure? 'Flake' is never the safe guess.",
)
REVIEWER_PERSONA = DecisionPoint(
    id="devloop.reviewer_persona",
    options=("senior", "security", "ops"),
    fallback="senior",
    escalate_to="security",
    description=(
        "Which reviewer does this change deserve? Unsure gets the strictest, "
        "because the cost of the wrong answer is asymmetric."
    ),
)
STOP_SIGNAL = DecisionPoint(
    id="devloop.stop_signal",
    options=("continue", "stop"),
    fallback="continue",
    escalate_to="continue",
    description=(
        "Has the review loop converged? Continues to the cap when unsure. "
        "Stopping early on a low-confidence 'looks done' is how a real finding "
        "survives (D19: circling is itself a signal, and a human reads it)."
    ),
)

# -- E. The Timeless Codebase (docs/19) ----------------------------------
BISECT_RANK = DecisionPoint(
    id="history.bisect_rank",
    options=("likely", "unlikely", "impossible"),
    fallback="likely",
    escalate_to="likely",
    description="Could this commit plausibly cause the symptom?",
)
REGRESSION_DEDUPE = DecisionPoint(
    id="history.regression_dedupe",
    options=("same", "related", "novel"),
    fallback="novel",
    escalate_to="novel",
    description="Have we seen this failure before?",
)
SUPERSESSION = DecisionPoint(
    id="history.supersession",
    options=("supersedes", "refines", "conflicts", "unrelated"),
    fallback="conflicts",
    escalate_to="conflicts",
    description=(
        "Does this decision contradict an earlier one? 'We decided the opposite "
        "in March' is invisible by construction and this is the only thing that catches it."
    ),
)
DRIFT = DecisionPoint(
    id="history.drift",
    options=("consistent", "drifted", "superseded"),
    fallback="drifted",
    escalate_to="drifted",
    description="Does the code still match the decision that authorized it?",
)
CHANGE_INTENT = DecisionPoint(
    id="history.change_intent",
    options=("feature", "fix", "refactor", "perf", "docs", "revert", "risky"),
    fallback="risky",
    escalate_to="risky",
    description=(
        "What kind of change is this, for the historical index? Commit messages "
        "lie and conventions drift. Over-classifying as risky costs review time; "
        "under-classifying loses the change in the archive."
    ),
)

# -- F. Voice and presence -----------------------------------------------
ADDRESSED = DecisionPoint(
    id="voice.addressed",
    options=("to_jarvis", "ambient", "unclear"),
    fallback="unclear",
    escalate_to="unclear",
    description="Post-wake disambiguation. 'Unclear' means do nothing.",
)
BARGE_IN = DecisionPoint(
    id="voice.barge_in",
    options=("stop", "redirect", "continue"),
    fallback="stop",
    escalate_to="stop",
    description="What did the interruption mean? 'Stop' is always the safe reading.",
)
INTENT_AMBIGUITY = DecisionPoint(
    id="voice.intent_ambiguity",
    options=("proceed", "clarify"),
    fallback="clarify",
    escalate_to="clarify",
    description="Ask or proceed? An unsure system asks. That is the whole point.",
)

# -- G. Safety and health ------------------------------------------------
INGEST_TRIAGE = DecisionPoint(
    id="safety.ingest_triage",
    options=("surface", "file", "discard"),
    fallback="file",
    escalate_to="file",
    description="What to do with a Proposal from a quarantined watcher.",
)
AUTONOMY_PROPOSAL = DecisionPoint(
    id="safety.autonomy_proposal",
    options=("A0", "A1", "A2", "A3", "A4"),
    fallback="A4",
    escalate_to="A4",
    description=(
        "A *proposal* for a new capability's class, never a grant. Falls back to "
        "the most restrictive option. Jev decides; the Policy Engine authorizes."
    ),
)

HEALTH_DEGRADATION = DecisionPoint(
    id="safety.health_degradation",
    options=("real", "transient"),
    fallback="real",
    escalate_to="real",
    description=(
        "Is this backend degradation real or a blip? Treating a real outage as "
        "transient keeps routing traffic into it."
    ),
)
ANOMALY = DecisionPoint(
    id="safety.anomaly",
    options=("normal", "unusual"),
    fallback="normal",
    escalate_to="unusual",
    description=(
        "Is this run unlike our own history? Fallback is normal-and-logged, "
        "because flagging everything is the same as flagging nothing -- but an "
        "unsure answer surfaces, since the point is to catch what we did not "
        "think to look for."
    ),
)

#: docs/20 ID -> registered point id. The doc's implementation contract says
#: every entry becomes a ``DecisionPoint``; this is what makes that checkable
#: rather than asserted, and ``tests/test_decide.py`` reads the doc and holds
#: the two together.
CATALOG_IDS: dict[str, str] = {
    "A1": "proactivity.salience", "A2": "proactivity.modality",
    "A3": "proactivity.interruptibility", "A4": "proactivity.trigger_triage",
    "A5": "proactivity.promotion", "A7": "proactivity.budget_pressure",
    "B2": "record.retention", "B3": "record.consolidation",
    "B4": "record.skill_draft_triage", "B5": "record.recall_planning",
    "B7": "record.forget_fanout", "B8": "record.memory_conflict",
    "C2": "routing.tier_adequacy", "C3": "routing.policy_parse",
    "C4": "routing.policy_conflict",
    "D1": "session.attention", "D2": "devloop.depth",
    "D3": "devloop.reviewer_persona", "D4": "devloop.finding_triage",
    "D5": "devloop.stop_signal", "D6": "devloop.flake",
    "E1": "history.bisect_rank", "E2": "history.regression_dedupe",
    "E3": "history.change_intent", "E5": "history.supersession",
    "E7": "history.drift",
    "F1": "voice.addressed", "F3": "voice.barge_in",
    "F4": "voice.intent_ambiguity",
    "G1": "safety.ingest_triage", "G2": "safety.autonomy_proposal",
    "G3": "safety.health_degradation", "G4": "safety.anomaly",
}

#: docs/20 entries that are **not** decision points, with the reason. Listed
#: rather than quietly absent: an entry missing from both this and
#: ``CATALOG_IDS`` is drift between the doc and the code, and the test says so.
NOT_DECISION_POINTS: dict[str, str] = {
    "A6": "ranking: ordering a digest is scoring, not a bounded choice",
    "B6": "ranking: which 12 of 500 is a score over candidates",
    "C5": "ranking: over the eligible backends, which the registry supplies",
    "C6": "ranking: over the healthy backends, same shape as C5",
    "D7": "ranking: which of several blocked sessions leads the summary",
    "E6": "ranking: which prior version is the best reference",
    "B1": "compound: emits a kind *and* subject_keys, not one bounded choice",
    "C1": "deployment-scoped: options are the registered capability classes",
    "E4": "deployment-scoped: options are this deployment's subsystems",
    "E8": "deployment-scoped: same subsystem set as E4",
    "F2": "deployment-scoped: options are the nodes that are actually present",
}
"""A ranking is not a ``DecisionPoint``: the type requires at least two *named*
options and a deterministic fallback among them, and a rank has neither. That
is a real distinction rather than a limitation to work around -- a bounded
choice can be escalated to a more conservative option when confidence is low,
and a rank cannot, so admission test 3 (docs/20) fails for all six."""

STANDARD_POINTS: tuple[DecisionPoint, ...] = (
    SALIENCE, MODALITY, INTERRUPTIBILITY, TRIGGER_TRIAGE, PROMOTION,
    BUDGET_PRESSURE,
    RETENTION, CONSOLIDATION, FORGET_FANOUT, MEMORY_CONFLICT,
    SKILL_DRAFT_TRIAGE, RECALL_PLANNING,
    TIER_ADEQUACY, POLICY_PARSE, POLICY_CONFLICT,
    SESSION_ATTENTION, LOOP_DEPTH, FINDING_TRIAGE, FLAKE,
    REVIEWER_PERSONA, STOP_SIGNAL,
    BISECT_RANK, REGRESSION_DEDUPE, SUPERSESSION, DRIFT, CHANGE_INTENT,
    ADDRESSED, BARGE_IN, INTENT_AMBIGUITY,
    INGEST_TRIAGE, AUTONOMY_PROPOSAL, HEALTH_DEGRADATION, ANOMALY,
)
