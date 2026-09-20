"""The vertical slice from docs/17 §8, end to end.

Voice in -> classify -> propose -> human answers -> policy written -> recorded
-> deterministic routing thereafter -> enumerable -> undoable.

Everything here is A0/A1 and nothing is irreversible, which is why it is the
right first slice: if this works, the architecture is real.
"""
from jarvis_core.capability import ModelCabinet, ModelPosition, PositionPolicy
from jarvis_core.decide import DecisionRegistry, DecisionSource, STANDARD_POINTS
from jarvis_core.record import Actor, EventKind, RecordStore, make_event

PROVIDERS = {"fable-5-1": "anthropic", "sonnet-5": "anthropic", "grok-4-6": "xai"}


class ScriptedDecider:
    """Stands in for the hosted decision model until access lands."""

    def __init__(self, answers: dict[str, tuple[str, float]]):
        self.answers = answers
        self.calls: list[str] = []

    def decide(self, point, state):
        self.calls.append(point.id)
        chosen, confidence = self.answers[point.id]
        return chosen, confidence, None

    def available(self) -> bool:
        return True


def test_spoken_routing_policy_round_trip(store: RecordStore):
    decider = ScriptedDecider({
        "routing.tier_adequacy": ("upgrade", 0.55),   # unsure -> propose, don't assume
        "routing.policy_parse": ("matches", 0.93),
        "routing.policy_conflict": ("consistent", 0.9),
    })
    decisions = DecisionRegistry(decider)
    decisions.register_all(STANDARD_POINTS)

    # 1. "Can we run these new features on the budget app?"
    turn = store.append(
        make_event(EventKind.USER_TURN, actor=Actor.USER, session="s1",
                   subject_keys=["project:budget-app"]),
        b"can we run these new features on the budget app",
    )

    # 2. Low confidence that the default tier is adequate -> propose, never assume.
    adequacy = decisions.decide("routing.tier_adequacy", {"task": "coding.repository"})
    assert adequacy.source is DecisionSource.ESCALATED
    assert adequacy.chosen == "adequate"  # escalates to the conservative option

    # 3. The human answers with a standing policy, spoken.
    utterance = "always use Fable 5.1 for coding tasks, but not as a subagent"
    parse = decisions.decide("routing.policy_parse", {"utterance": utterance})
    assert parse.chosen == "matches" and parse.source is DecisionSource.MODEL

    cabinet = ModelCabinet(positions={
        ModelPosition.PRIMARY: PositionPolicy(default="fable-5-1"),
        ModelPosition.SUBAGENT: PositionPolicy(default="sonnet-5",
                                               deny=frozenset({"fable-5-1"})),
        ModelPosition.CRITIC: PositionPolicy(default="auto",
                                             require_different_provider_than_builder=True),
    })

    # 4. Conflicts surface at write time, not at 2am.
    assert cabinet.conflicts(PROVIDERS) == []
    conflict = decisions.decide("routing.policy_conflict", {"cabinet": "…"})
    assert conflict.chosen == "consistent"

    # 5. The write is an event, carrying the utterance that authorized it.
    written = store.append(
        make_event(EventKind.POLICY_WRITE, actor=Actor.USER, session="s1",
                   subject_keys=["project:budget-app"], parent=[turn.event.id],
                   meta={"utterance": utterance, "decision": parse.point_id}),
        utterance.encode(),
    )
    assert written.event.is_permanent

    # 6. The judgment is now a rule. The model is no longer asked.
    decisions.promote_to_rule("routing.tier_adequacy", "upgrade")
    before = len(decider.calls)
    again = decisions.decide("routing.tier_adequacy", {"task": "coding.repository"})
    assert (again.chosen, again.source) == ("upgrade", DecisionSource.RULE)
    assert len(decider.calls) == before, "a promoted rule must not call the decider"

    # 7. Enumerable, and the exclusion holds for automatic selection only.
    assert dict(decisions.rules()) == {"routing.tier_adequacy": "upgrade"}
    assert cabinet.permits(ModelPosition.SUBAGENT, "fable-5-1") is False
    assert cabinet.permits(ModelPosition.SUBAGENT, "fable-5-1", manual=True) is True

    # 8. Spoken undo, and the Record still verifies.
    assert decisions.clear_rule("routing.tier_adequacy") is True
    assert dict(decisions.rules()) == {}
    assert store.verify() == 2

    # 9. The whole exchange is reconstructible, with causality intact.
    events = [s.event for s in store.scan()]
    assert events[1].parent == (events[0].id,)
    assert store.payload(events[1]) == utterance.encode()
