"""The decision layer: fallbacks, escalation, the rule factory, calibration."""
import pytest

from jarvis_core.decide import (
    CalibrationLog, DecisionPoint, DecisionRegistry, DecisionSource,
    FallbackDecider, STANDARD_POINTS,
)
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
        result = registry_with(StubDecider("cheap", 0.9, boom=True)).decide("test.point", {})
        assert (result.chosen, result.source) == ("middle", DecisionSource.FALLBACK)

    def test_answer_outside_the_option_set_is_rejected(self):
        """A decider that invents an option is broken, not creative."""
        result = registry_with(StubDecider("invented", 0.99)).decide("test.point", {})
        assert (result.chosen, result.source) == ("middle", DecisionSource.FALLBACK)

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
        reg.promote_to_rule("test.point", "careful")
        result = reg.decide("test.point", {})
        assert (result.chosen, result.source, result.confidence) == (
            "careful", DecisionSource.RULE, 1.0,
        )

    def test_rules_are_enumerable(self):
        reg = registry_with()
        reg.promote_to_rule("test.point", "cheap")
        assert dict(reg.rules()) == {"test.point": "cheap"}

    def test_a_rule_can_be_cleared(self):
        reg = registry_with(StubDecider("cheap", 0.95))
        reg.promote_to_rule("test.point", "careful")
        assert reg.clear_rule("test.point") is True
        assert reg.decide("test.point", {}).source is DecisionSource.MODEL

    def test_cannot_promote_to_a_non_option(self):
        with pytest.raises(ValueError, match="not an option"):
            registry_with().promote_to_rule("test.point", "invented")


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
