"""Capability registry and the Model Cabinet (D17)."""
import pytest

from jarvis_core.autonomy import AutonomyClass as A
from jarvis_core.capability import (
    Capability, CapabilityRegistry, ModelCabinet, ModelPosition, PositionPolicy, PrivacyClass,
)

PROVIDERS = {"fable-5-1": "anthropic", "sonnet-5": "anthropic", "grok-4-6": "xai"}


def cabinet(**overrides) -> ModelCabinet:
    positions = {
        ModelPosition.PRIMARY: PositionPolicy(default="sonnet-5"),
        ModelPosition.SUBAGENT: PositionPolicy(default="sonnet-5", deny=frozenset({"fable-5-1"})),
        ModelPosition.CRITIC: PositionPolicy(
            default="auto", require_different_provider_than_builder=True
        ),
    }
    positions.update(overrides.pop("positions", {}))
    return ModelCabinet(positions=positions, **overrides)


class TestRegistry:
    def test_capabilities_default_to_disabled(self):
        assert Capability("x", A.A1_REVERSIBLE).enabled is False

    def test_duplicate_registration_is_rejected(self):
        registry = CapabilityRegistry([Capability("a", A.A0_OBSERVE)])
        with pytest.raises(ValueError, match="already registered"):
            registry.register(Capability("a", A.A0_OBSERVE))

    def test_require_raises_on_unknown(self, registry: CapabilityRegistry):
        with pytest.raises(KeyError):
            registry.require("nope")

    def test_classes_map_feeds_protocol_validation(self, registry: CapabilityRegistry):
        assert registry.classes()["door.unlock"] is A.A3_CONSEQUENTIAL

    def test_enable_returns_an_updated_capability(self, registry: CapabilityRegistry):
        assert registry.enable("ci.read_logs").enabled is True
        assert registry.require("ci.read_logs").enabled is True

    def test_side_effecting_is_derived_from_idempotency_fields(self):
        assert Capability("a", A.A0_OBSERVE).side_effecting is False
        assert Capability("b", A.A2_EXTERNAL, idempotency_key_fields=("to",)).side_effecting


class TestModelCabinet:
    def test_denied_model_is_blocked_for_automatic_selection(self):
        assert cabinet().permits(ModelPosition.SUBAGENT, "fable-5-1") is False

    def test_a_manual_pin_beats_an_exclusion(self):
        """docs/17 §5 -- policy binds the router, not the user."""
        assert cabinet().permits(ModelPosition.SUBAGENT, "fable-5-1", manual=True) is True

    def test_manual_override_can_be_turned_off(self):
        strict = cabinet(manual_override=False)
        assert strict.permits(ModelPosition.SUBAGENT, "fable-5-1", manual=True) is False

    def test_unconstrained_position_permits_anything(self):
        assert cabinet().permits(ModelPosition.BACKGROUND, "anything") is True

    def test_no_conflict_when_two_providers_survive(self):
        assert cabinet().conflicts(PROVIDERS) == []

    def test_cross_provider_critic_conflict_is_caught_at_write_time(self):
        """Denying a model can silently empty the legal critic set (D10 + D17)."""
        single_provider = {"fable-5-1": "anthropic", "sonnet-5": "anthropic"}
        problems = cabinet().conflicts(single_provider)
        assert len(problems) == 1 and "different provider" in problems[0]

    def test_denying_every_model_is_caught(self):
        blocked = cabinet(positions={
            ModelPosition.SUBAGENT: PositionPolicy(default="x", deny=frozenset(PROVIDERS)),
        })
        problems = blocked.conflicts(PROVIDERS)
        assert any("every known model is denied" in p for p in problems)


class TestPrivacy:
    def test_local_only_is_a_distinct_class(self):
        capability = Capability("memory.recall", A.A0_OBSERVE, privacy=PrivacyClass.LOCAL_ONLY)
        assert capability.privacy is PrivacyClass.LOCAL_ONLY
