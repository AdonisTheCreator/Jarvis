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

STANDARD_POINTS: tuple[DecisionPoint, ...] = (
    SALIENCE, MODALITY, INTERRUPTIBILITY, TRIGGER_TRIAGE, PROMOTION,
    RETENTION, CONSOLIDATION, FORGET_FANOUT, MEMORY_CONFLICT,
    TIER_ADEQUACY, POLICY_PARSE, POLICY_CONFLICT,
    SESSION_ATTENTION, LOOP_DEPTH, FINDING_TRIAGE, FLAKE,
    BISECT_RANK, REGRESSION_DEDUPE, SUPERSESSION, DRIFT,
    ADDRESSED, BARGE_IN,
    INGEST_TRIAGE, AUTONOMY_PROPOSAL,
)
