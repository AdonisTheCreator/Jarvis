"""The decision layer: fallbacks, escalation, the rule factory, calibration."""
import re
from pathlib import Path

import pytest

from jarvis_core.decide import (
    CalibrationLog, DecisionPoint, DecisionRegistry, DecisionSource,
    FallbackDecider, STANDARD_POINTS,
)
from jarvis_core.decide.catalog import CATALOG_IDS, NOT_DECISION_POINTS
from jarvis_core.errors import PolicyDenied


class StubDecider:
    """A decider whose answer and confidence the test controls."""

    def __init__(self, chosen: str, confidence: float, *, up: bool = True, boom: bool = False):
        self.chosen, self.confidence, self.up, self.boom = chosen, confidence, up, boom

    def decide(self, point, state):
        if self.boom:
            raise RuntimeError("decider exploded")
        return self.chosen, self.confidence, None

    def available(self) -> bool:
        return self.up


POINT = DecisionPoint(
    id="test.point", options=("cheap", "middle", "careful"),
    fallback="middle", escalate_to="careful", min_confidence=0.7,
)


def registry_with(decider=None) -> DecisionRegistry:
    reg = DecisionRegistry(decider)
    reg.register(POINT)
    return reg


class TestDecisionPointValidation:
    def test_fallback_must_be_an_option(self):
        with pytest.raises(ValueError, match="fallback"):
            DecisionPoint(id="p", options=("a", "b"), fallback="z", escalate_to="a")

    def test_escalate_to_must_be_an_option(self):
        with pytest.raises(ValueError, match="escalate_to"):
            DecisionPoint(id="p", options=("a", "b"), fallback="a", escalate_to="z")

    def test_needs_at_least_two_options(self):
        with pytest.raises(ValueError, match="at least two"):
            DecisionPoint(id="p", options=("a",), fallback="a", escalate_to="a")

    def test_rejects_duplicate_options(self):
        with pytest.raises(ValueError, match="duplicate"):
            DecisionPoint(id="p", options=("a", "a"), fallback="a", escalate_to="a")


class TestResolution:
    def test_confident_answer_is_used(self):
        result = registry_with(StubDecider("cheap", 0.95)).decide("test.point", {})
        assert (result.chosen, result.source) == ("cheap", DecisionSource.MODEL)

    def test_low_confidence_escalates_to_the_conservative_option(self):
        """Never the cheaper one -- this is the rule from D9."""
        result = registry_with(StubDecider("cheap", 0.4)).decide("test.point", {})
        assert (result.chosen, result.source) == ("careful", DecisionSource.ESCALATED)

    def test_unavailable_decider_uses_the_fallback(self):
        result = registry_with(StubDecider("cheap", 0.99, up=False)).decide("test.point", {})
        assert (result.chosen, result.source) == ("middle", DecisionSource.FALLBACK)

    def test_null_decider_is_not_treated_as_low_confidence(self):
        """The bug this guards: a null decider must not re-escalate everything."""
        result = registry_with(FallbackDecider()).decide("test.point", {})
        assert (result.chosen, result.source) == ("middle", DecisionSource.FALLBACK)

    def test_a_crashing_decider_falls_back_rather_than_taking_the_system_down(self):
        """Same choice as an absent decider, different source: 'the decision
        layer is down' and 'the decision layer is erroring' want different
        responses, and one source hides the second behind the first."""
        result = registry_with(StubDecider("cheap", 0.9, boom=True)).decide("test.point", {})
        assert (result.chosen, result.source) == ("middle", DecisionSource.FAULT)

    def test_an_answer_outside_the_option_set_escalates_rather_than_falls_back(self):
        """A decider that invents an option is broken, not creative -- and more
        broken than one that is merely unsure, so it must not get the milder
        treatment. It used to: on record.retention the fallback is "compress"
        where low confidence says "keep_full", so a broken decider destroyed
        detail an unsure one would have kept."""
        result = registry_with(StubDecider("invented", 0.99)).decide("test.point", {})
        assert (result.chosen, result.source) == ("careful", DecisionSource.INVALID)
        assert result.chosen == registry_with().get("test.point").escalate_to

    def test_the_three_degraded_paths_are_told_apart(self):
        """Absent, erroring, and answering nonsense are three different alarms."""
        sources = {
            registry_with(StubDecider("cheap", 0.9, up=False)).decide("test.point", {}).source,
            registry_with(StubDecider("cheap", 0.9, boom=True)).decide("test.point", {}).source,
            registry_with(StubDecider("invented", 0.99)).decide("test.point", {}).source,
        }
        assert sources == {
            DecisionSource.FALLBACK, DecisionSource.FAULT, DecisionSource.INVALID,
        }

    def test_safety_critical_points_deny_when_unavailable(self):
        reg = DecisionRegistry(StubDecider("a", 0.9, up=False))
        reg.register(DecisionPoint(id="gate", options=("a", "b"), fallback="a",
                                   escalate_to="a", safety_critical=True))
        with pytest.raises(PolicyDenied):
            reg.decide("gate", {})

    def test_unknown_point_raises(self):
        with pytest.raises(KeyError):
            registry_with().decide("nope", {})


class TestRuleFactory:
    """docs/17 §2 -- the decision layer manufactures rules and retires itself."""

    def test_a_promoted_rule_short_circuits_the_model(self):
        reg = registry_with(StubDecider("cheap", 0.99))
        reg.promote_to_rule("test.point", "careful", actor="user:harrison")
        result = reg.decide("test.point", {})
        assert (result.chosen, result.source, result.confidence) == (
            "careful", DecisionSource.RULE, 1.0,
        )

    def test_rules_are_enumerable_and_attributed(self):
        """A rule outranks the decision layer permanently and answers with
        confidence 1.0. {point: chosen} cannot say who settled it."""
        reg = registry_with()
        reg.promote_to_rule("test.point", "cheap", actor="user:harrison", note="spoken")
        rule = reg.rules()["test.point"]
        assert (rule.chosen, rule.actor, rule.note) == ("cheap", "user:harrison", "spoken")
        assert rule.at > 0

    def test_an_anonymous_rule_is_refused(self):
        for blank in ("", "   "):
            with pytest.raises(ValueError, match="needs an actor"):
                registry_with().promote_to_rule("test.point", "cheap", actor=blank)

    def test_a_rule_can_be_cleared_and_the_lift_is_attributable_too(self):
        """Removing a policy is a policy write; the Record needs the same
        detail for the undo as for the promotion."""
        reg = registry_with(StubDecider("cheap", 0.95))
        reg.promote_to_rule("test.point", "careful", actor="user:harrison")
        lifted = reg.clear_rule("test.point")
        assert (lifted.chosen, lifted.actor) == ("careful", "user:harrison")
        assert reg.clear_rule("test.point") is None
        assert reg.decide("test.point", {}).source is DecisionSource.MODEL

    def test_cannot_promote_to_a_non_option(self):
        with pytest.raises(ValueError, match="not an option"):
            registry_with().promote_to_rule("test.point", "invented", actor="user")


class TestStandardCatalog:
    def test_every_point_registers(self):
        reg = DecisionRegistry()
        reg.register_all(STANDARD_POINTS)
        assert len(reg.ids()) == len(STANDARD_POINTS)

    def test_point_ids_are_unique(self):
        ids = [p.id for p in STANDARD_POINTS]
        assert len(ids) == len(set(ids))

    def test_every_point_has_a_safe_fallback_rather_than_denying(self):
        """A design property, asserted: if a point cannot name a safe default,
        it is probably a rule wearing a decision's clothes (docs/20)."""
        assert [p.id for p in STANDARD_POINTS if p.safety_critical] == []

    def test_flake_never_defaults_to_flake(self):
        flake = next(p for p in STANDARD_POINTS if p.id == "devloop.flake")
        assert flake.fallback == "real" and flake.escalate_to == "real"

    def test_retention_never_defaults_to_delete(self):
        retention = next(p for p in STANDARD_POINTS if p.id == "record.retention")
        assert retention.fallback != "delete" and retention.escalate_to == "keep_full"

    def test_autonomy_proposal_falls_back_to_the_most_restrictive_class(self):
        point = next(p for p in STANDARD_POINTS if p.id == "safety.autonomy_proposal")
        assert point.fallback == "A4" and point.escalate_to == "A4"


class TestTheDocIsTheContract:
    """docs/20 says "every entry is registered as a DecisionPoint". It said
    that while listing 44 entries against 24 registered ones, which is how a
    contract becomes a wish. This reads the doc."""

    DOC = Path(__file__).resolve().parents[1] / "docs" / "20-DECISION-CATALOG.md"

    def doc_ids(self) -> set[str]:
        return set(re.findall(r"^\| ([A-G]\d+) \|", self.DOC.read_text(), re.M))

    def test_the_doc_lists_what_we_think_it_lists(self):
        """A guard against the guard: if the tables stop parsing, everything
        below passes vacuously."""
        assert len(self.doc_ids()) >= 40

    def test_every_documented_entry_is_registered_or_explicitly_excluded(self):
        accounted = set(CATALOG_IDS) | set(NOT_DECISION_POINTS)
        missing = self.doc_ids() - accounted
        assert not missing, (
            f"docs/20 lists {sorted(missing)} with no registered point and no "
            "reason for being excluded. Register it, or say in "
            "NOT_DECISION_POINTS why it is not a bounded choice."
        )

    def test_nothing_is_claimed_that_the_doc_does_not_list(self):
        stale = (set(CATALOG_IDS) | set(NOT_DECISION_POINTS)) - self.doc_ids()
        assert not stale, f"{sorted(stale)} no longer appear in docs/20"

    def test_an_entry_is_registered_or_excluded_but_not_both(self):
        assert not set(CATALOG_IDS) & set(NOT_DECISION_POINTS)

    def test_every_mapped_id_resolves_to_a_real_point(self):
        registered = {point.id for point in STANDARD_POINTS}
        assert set(CATALOG_IDS.values()) == registered

    def test_every_exclusion_gives_a_reason(self):
        assert all(reason.strip() for reason in NOT_DECISION_POINTS.values())

    def test_the_exclusions_are_the_shapes_the_type_cannot_hold(self):
        """Ranking, compound output, deployment-scoped options -- and nothing
        else. "Excluded" must not become a place to put the inconvenient."""
        allowed = {"ranking", "compound", "deployment-scoped"}
        for doc_id, reason in NOT_DECISION_POINTS.items():
            assert reason.split(":")[0] in allowed, f"{doc_id}: {reason}"


class TestCalibration:
    def test_perfect_calibration_scores_near_zero_error(self):
        log = CalibrationLog()
        for _ in range(90):
            log.record("p", 0.9, correct=True)
        for _ in range(10):
            log.record("p", 0.9, correct=False)
        report = log.report("p")
        assert report.n == 100
        assert report.ece < 0.02
        assert report.is_trustworthy()

    def test_overconfidence_is_detected(self):
        log = CalibrationLog()
        for i in range(100):
            log.record("p", 0.95, correct=i < 50)  # claims 95%, delivers 50%
        report = log.report("p")
        assert report.ece > 0.4
        assert not report.is_trustworthy()
        assert "p" in log.untrustworthy()

    def test_tracked_per_point_not_globally(self):
        log = CalibrationLog()
        for i in range(60):
            log.record("good", 0.9, correct=i < 54)
            log.record("bad", 0.9, correct=i < 6)
        assert log.report("good").is_trustworthy()
        assert not log.report("bad").is_trustworthy()
        assert set(log.untrustworthy()) == {"bad"}

    def test_empty_log_is_not_trustworthy(self):
        assert not CalibrationLog().report("p").is_trustworthy()

    def test_a_new_point_is_not_the_same_as_a_broken_one(self):
        """Both mean 'do not believe the thresholds' and want opposite
        responses: one needs traffic, the other needs demoting. A single
        SUSPECT demotes a perfectly calibrated point for being new."""
        log = CalibrationLog()
        for i in range(10):
            log.record("new", 0.9, correct=i < 9)      # calibrated, thin
        for i in range(100):
            log.record("broken", 0.95, correct=i < 50)  # plenty, and wrong

        assert log.report("new").verdict() == "insufficient-data"
        assert log.report("broken").verdict() == "miscalibrated"
        assert not log.report("new").is_trustworthy()
        assert set(log.untrustworthy()) == {"broken"}    # the thin one is not demoted
        assert "insufficient-data" in log.report("new").summary()

    def test_a_stricter_bar_is_honoured_rather_than_swallowed(self):
        """untrustworthy() took **kwargs, so a misspelled threshold silently
        fell back to the default and a caller asking for strict got lax."""
        log = CalibrationLog()
        for i in range(100):
            log.record("p", 0.9, correct=i < 85)   # ece ~= 0.05: fine by default
        assert log.untrustworthy() == {}
        assert set(log.untrustworthy(max_ece=0.01)) == {"p"}
        assert log.untrustworthy(min_samples=200) == {}
        with pytest.raises(TypeError):
            log.untrustworthy(min_sample=1)        # the typo is now loud

    def test_an_out_of_range_confidence_is_refused(self):
        """It falls in no bucket while still counting in n, which divides ECE
        down and makes a miscalibrated point look better than it is."""
        log = CalibrationLog()
        for bad in (-0.1, 1.5):
            with pytest.raises(ValueError, match="between 0 and 1"):
                log.record("p", bad, correct=True)
