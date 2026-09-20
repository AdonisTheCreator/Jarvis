"""The Policy Engine: the refusals that must hold."""
import os
from pathlib import Path

import pytest

from jarvis_core.autonomy import AutonomyClass as A
from jarvis_core.errors import ApprovalInvalid, ApprovalRequired, PolicyDenied
from jarvis_core.killswitch import FileKillSwitch, NullKillSwitch
from jarvis_core.policy import (
    ApprovalLedger, AuthLevel, ConfirmMode, Outcome, PolicyEngine, Protocol,
    ProtocolRegistry, ProtocolStep, Request,
)


class TestAutonomyClasses:
    def test_ordering_is_by_blast_radius(self):
        assert A.A0_OBSERVE < A.A1_REVERSIBLE < A.A2_EXTERNAL < A.A3_CONSEQUENTIAL < A.A4_BLOCKED

    def test_a2_and_above_need_approval(self):
        assert not A.A0_OBSERVE.needs_approval and not A.A1_REVERSIBLE.needs_approval
        assert A.A2_EXTERNAL.needs_approval and A.A3_CONSEQUENTIAL.needs_approval

    def test_only_a3_needs_a_protocol(self):
        assert A.A3_CONSEQUENTIAL.needs_protocol
        assert not A.A2_EXTERNAL.needs_protocol and not A.A4_BLOCKED.needs_protocol


class TestApprovalTokens:
    def test_valid_token_redeems_once(self, approvals: ApprovalLedger):
        params = {"to": "sam", "body": "hi"}
        token = approvals.issue("message.send", "sam", params)
        approvals.redeem(token, "message.send", "sam", params)
        with pytest.raises(ApprovalInvalid, match="already used"):
            approvals.redeem(token, "message.send", "sam", params)

    def test_changed_parameters_invalidate(self, approvals: ApprovalLedger):
        token = approvals.issue("payment.send", "acct", {"amount": 40})
        with pytest.raises(ApprovalInvalid, match="parameters changed"):
            approvals.redeem(token, "payment.send", "acct", {"amount": 4000})

    def test_token_is_bound_to_its_capability_and_target(self, approvals: ApprovalLedger):
        params = {"x": 1}
        with pytest.raises(ApprovalInvalid, match="not 'door.unlock'"):
            approvals.redeem(approvals.issue("message.send", "t", params), "door.unlock", "t", params)
        with pytest.raises(ApprovalInvalid, match="target"):
            approvals.redeem(approvals.issue("message.send", "a", params), "message.send", "b", params)

    def test_expired_token_is_rejected(self, approvals: ApprovalLedger):
        token = approvals.issue("message.send", "t", {}, ttl_seconds=-1)
        with pytest.raises(ApprovalInvalid, match="expired"):
            approvals.redeem(token, "message.send", "t", {})

    def test_a_store_that_omits_durable_is_treated_as_non_durable(self):
        """Fails closed: assuming durability nobody declared would silently
        claim a guarantee that was never made."""
        class Undeclared:
            def try_spend(self, token_id: str) -> bool:
                return True

        assert ApprovalLedger(os.urandom(32), Undeclared()).durable is False

    def test_spending_is_atomic_under_concurrency(self):
        """Two workers must not both redeem the same captured token."""
        import threading

        ledger = ApprovalLedger(os.urandom(32))
        params = {"x": 1}
        token = ledger.issue("message.send", "sam", params)
        redeemed: list[bool] = []
        lock = threading.Lock()

        def attempt() -> None:
            try:
                ledger.redeem(token, "message.send", "sam", params)
                ok = True
            except ApprovalInvalid:
                ok = False
            with lock:
                redeemed.append(ok)

        threads = [threading.Thread(target=attempt) for _ in range(24)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sum(redeemed) == 1

    def test_the_default_spent_store_reports_itself_non_durable(self, approvals):
        """Single-use is only true if 'already spent' survives a restart. The
        in-memory default does not, and says so rather than pretending."""
        assert approvals.durable is False

    def test_a_durable_spent_store_makes_single_use_survive_a_restart(self):
        class Durable:
            """Stands in for a store backed by the same disk as the Record."""

            durable = True

            def __init__(self):
                self.ids: set[str] = set()

            def try_spend(self, token_id: str) -> bool:
                if token_id in self.ids:
                    return False
                self.ids.add(token_id)
                return True

        shared = Durable()
        secret = os.urandom(32)
        first = ApprovalLedger(secret, shared)
        assert first.durable is True
        token = first.issue("message.send", "sam", {"x": 1})
        first.redeem(token, "message.send", "sam", {"x": 1})

        restarted = ApprovalLedger(secret, shared)
        with pytest.raises(ApprovalInvalid, match="already used"):
            restarted.redeem(token, "message.send", "sam", {"x": 1})

    def test_forged_signature_is_rejected(self, approvals: ApprovalLedger):
        other = ApprovalLedger(os.urandom(32))
        forged = other.issue("door.unlock", "front", {})
        with pytest.raises(ApprovalInvalid, match="signature"):
            approvals.redeem(forged, "door.unlock", "front", {})


class TestPolicyEngine:
    def test_a0_is_automatic(self, engine: PolicyEngine):
        assert engine.evaluate(Request("ci.read_status", "repo")).outcome is Outcome.ALLOW

    def test_a1_is_automatic_once_enabled(self, engine: PolicyEngine):
        assert engine.evaluate(Request("ci.rerun_job", "job-1")).outcome is Outcome.ALLOW

    def test_disabled_capability_is_denied(self, engine: PolicyEngine):
        decision = engine.evaluate(Request("ci.read_logs", "repo"))
        assert decision.outcome is Outcome.DENY and "not enabled" in decision.reason

    def test_unknown_capability_fails_closed(self, engine: PolicyEngine):
        decision = engine.evaluate(Request("nope.invent", "t"))
        assert decision.outcome is Outcome.DENY and "unknown capability" in decision.reason

    def test_a2_requires_approval_then_allows(self, engine: PolicyEngine, approvals):
        params = {"to": "sam", "body": "hi"}
        first = engine.evaluate(Request("message.send", "sam", params))
        assert first.outcome is Outcome.REQUIRE_APPROVAL and first.approval_request_id
        token = approvals.issue("message.send", "sam", params)
        second = engine.evaluate(Request("message.send", "sam", params, approval=token))
        assert second.outcome is Outcome.ALLOW

    def test_a4_is_blocked_even_when_enabled(self, engine: PolicyEngine):
        decision = engine.evaluate(Request("vehicle.drive", "car"))
        assert decision.outcome is Outcome.DENY and "no override" in decision.reason

    def test_a4_cannot_be_unlocked_by_an_approval(self, engine: PolicyEngine, approvals):
        token = approvals.issue("vehicle.drive", "car", {})
        assert engine.evaluate(Request("vehicle.drive", "car", approval=token)).outcome is Outcome.DENY

    def test_quarantined_actor_gets_nothing(self, engine: PolicyEngine):
        """Not scoped recall -- none. It may already be under someone else's control."""
        decision = engine.evaluate(Request("ci.read_status", "repo", quarantined=True))
        assert decision.outcome is Outcome.DENY and "quarantined" in decision.reason

    def test_authorize_raises_rather_than_returning(self, engine: PolicyEngine):
        with pytest.raises(PolicyDenied):
            engine.authorize(Request("vehicle.drive", "car"))
        with pytest.raises(ApprovalRequired):
            engine.authorize(Request("message.send", "sam", {"to": "sam", "body": "x"}))


class TestA3RequiresAProtocol:
    def _protocol(self, **kw):
        defaults = dict(
            name="evening_lockup",
            steps=(ProtocolStep("door.unlock", {"door": "front"}),),
            blast_radius="front door only; no other locks",
            declared_by="harrison",
            reviewed_on="2026-09-20",
            auth_required=AuthLevel.STRONG,
            confirm=ConfirmMode.EXPLICIT,
            undo="door.lock",
        )
        return Protocol(**{**defaults, **kw})

    def test_a3_without_a_protocol_is_denied(self, engine: PolicyEngine, approvals):
        token = approvals.issue("door.unlock", "front", {})
        decision = engine.evaluate(Request("door.unlock", "front", approval=token))
        assert decision.outcome is Outcome.DENY
        assert "declared Protocol" in decision.reason

    def test_a3_inside_a_declared_protocol_is_allowed(self, engine, approvals, protocols):
        protocols.declare(self._protocol())
        params = {"door": "front"}
        token = approvals.issue("door.unlock", "front", params)
        decision = engine.evaluate(
            Request("door.unlock", "front", params, approval=token,
                    protocol="evening_lockup", auth_level=AuthLevel.STRONG)
        )
        assert decision.outcome is Outcome.ALLOW

    def test_a_protocols_declared_target_binds(self, engine, approvals, protocols):
        """target reaches the backend untouched, so a Protocol naming the front
        door must not authorize the garage."""
        protocols.declare(self._protocol(
            steps=(ProtocolStep("door.unlock", {"door": "front"}, target="front"),)
        ))
        params = {"door": "front"}
        token = approvals.issue("door.unlock", "garage", params)
        decision = engine.evaluate(
            Request("door.unlock", "garage", params, approval=token,
                    protocol="evening_lockup", auth_level=AuthLevel.STRONG)
        )
        assert decision.outcome is Outcome.DENY
        assert "on this target" in decision.reason

    def test_a_protocols_declared_parameters_bind(self, engine, approvals, protocols):
        """A Protocol that named the front door does not authorize the garage.
        Checking the capability alone would make the fixed parameter set
        decorative and reintroduce the in-the-moment judgment R8 removes."""
        protocols.declare(self._protocol())
        params = {"door": "garage"}
        token = approvals.issue("door.unlock", "front", params)
        decision = engine.evaluate(
            Request("door.unlock", "front", params, approval=token,
                    protocol="evening_lockup", auth_level=AuthLevel.STRONG)
        )
        assert decision.outcome is Outcome.DENY
        assert "with these parameters" in decision.reason

    def test_undeclared_extra_parameters_are_refused(self, engine, approvals, protocols):
        """Subset matching lets extras through unchecked -- the same fail-open
        shape as an unbound target."""
        protocols.declare(self._protocol())
        params = {"door": "front", "duration_minutes": 480}
        token = approvals.issue("door.unlock", "front", params)
        decision = engine.evaluate(
            Request("door.unlock", "front", params, approval=token,
                    protocol="evening_lockup", auth_level=AuthLevel.STRONG)
        )
        assert decision.outcome is Outcome.DENY

    def test_a_step_declaring_no_parameters_constrains_none(
        self, engine, approvals, protocols
    ):
        protocols.declare(self._protocol(steps=(ProtocolStep("door.unlock"),)))
        params = {"door": "anything"}
        token = approvals.issue("door.unlock", "front", params)
        decision = engine.evaluate(
            Request("door.unlock", "front", params, approval=token,
                    protocol="evening_lockup", auth_level=AuthLevel.STRONG)
        )
        assert decision.outcome is Outcome.ALLOW

    def test_protocol_must_actually_cover_the_capability(self, engine, approvals, protocols):
        protocols.declare(self._protocol(steps=(ProtocolStep("ci.rerun_job"),)))
        token = approvals.issue("door.unlock", "front", {})
        decision = engine.evaluate(
            Request("door.unlock", "front", approval=token,
                    protocol="evening_lockup", auth_level=AuthLevel.STRONG)
        )
        assert decision.outcome is Outcome.DENY
        assert "does not authorize" in decision.reason

    def test_weak_auth_is_rejected(self, engine, approvals, protocols):
        protocols.declare(self._protocol())
        params = {"door": "front"}
        token = approvals.issue("door.unlock", "front", params)
        decision = engine.evaluate(
            Request("door.unlock", "front", params, approval=token,
                    protocol="evening_lockup", auth_level=AuthLevel.SESSION)
        )
        assert decision.outcome is Outcome.DENY and "strong auth" in decision.reason


class TestProtocolDeclaration:
    def test_a3_protocol_must_require_explicit_confirmation(self, protocols: ProtocolRegistry):
        with pytest.raises(ValueError, match="confirm=explicit"):
            protocols.declare(Protocol(
                name="p", steps=(ProtocolStep("door.unlock"),), blast_radius="front door",
                declared_by="h", reviewed_on="2026-09-20",
                auth_required=AuthLevel.STRONG, confirm=ConfirmMode.NONE, undo="door.lock"))

    def test_a4_can_never_appear_in_a_protocol(self, protocols: ProtocolRegistry):
        with pytest.raises(ValueError, match="A4 step"):
            protocols.declare(Protocol(
                name="p", steps=(ProtocolStep("vehicle.drive"),), blast_radius="the car",
                declared_by="h", reviewed_on="2026-09-20",
                auth_required=AuthLevel.STRONG, confirm=ConfirmMode.EXPLICIT, undo=None))

    def test_no_undo_forces_confirmation(self, protocols: ProtocolRegistry):
        with pytest.raises(ValueError, match="must require confirmation"):
            protocols.declare(Protocol(
                name="p", steps=(ProtocolStep("ci.rerun_job"),), blast_radius="one job",
                declared_by="h", reviewed_on="2026-09-20", confirm=ConfirmMode.NONE, undo=None))

    def test_blast_radius_must_be_written_down(self, protocols: ProtocolRegistry):
        with pytest.raises(ValueError, match="blast radius"):
            protocols.declare(Protocol(
                name="p", steps=(ProtocolStep("ci.rerun_job"),), blast_radius="   ",
                declared_by="h", reviewed_on="2026-09-20", undo="x"))

    def test_protocols_are_immutable_once_declared(self, protocols: ProtocolRegistry):
        p = Protocol(name="p", steps=(ProtocolStep("ci.rerun_job"),), blast_radius="one job",
                     declared_by="h", reviewed_on="2026-09-20", undo="x")
        protocols.declare(p)
        with pytest.raises(ValueError, match="immutable"):
            protocols.declare(p)


class TestKillSwitch:
    def test_engaged_denies_everything_agent_initiated(self, registry, approvals, protocols, tmp_path):
        sentinel = tmp_path / "HALT"
        engine = PolicyEngine(registry, approvals, protocols, FileKillSwitch(sentinel))
        assert engine.evaluate(Request("ci.rerun_job", "j")).outcome is Outcome.ALLOW
        sentinel.write_text("manual halt")
        for capability in ("ci.rerun_job", "message.send", "door.unlock"):
            decision = engine.evaluate(Request(capability, "t"))
            assert decision.outcome is Outcome.DENY and "kill switch" in decision.reason

    @pytest.mark.parametrize("actor", ["user", "user:harrison", "User:Harrison"])
    def test_a_human_can_still_observe_while_halted(
        self, registry, approvals, protocols, tmp_path, actor
    ):
        """You must be able to see what is happening while everything is
        stopped -- including under the prefixed actor form the rest of the
        system uses, or the carve-out denies the very person diagnosing it."""
        sentinel = tmp_path / "HALT"
        sentinel.write_text("halted")
        engine = PolicyEngine(registry, approvals, protocols, FileKillSwitch(sentinel))
        assert engine.evaluate(
            Request("ci.read_status", "r", actor=actor)
        ).outcome is Outcome.ALLOW
        for other in ("agent", "watcher:ci", "subconscious", "system"):
            assert engine.evaluate(
                Request("ci.read_status", "r", actor=other)
            ).outcome is Outcome.DENY

    def test_an_unreadable_sentinel_fails_closed(
        self, registry, approvals, protocols, tmp_path
    ):
        """An unreadable kill switch is indistinguishable from a tampered one.

        The fault is real rather than simulated: a parent that is a file, not
        a directory, which is what a detached mount looks like from here. A
        mocked exception would have passed against the old implementation too,
        where ``Path.exists()`` swallowed this errno and answered "absent".
        """
        blocker = tmp_path / "mount"
        blocker.write_bytes(b"not a directory")
        switch = FileKillSwitch(blocker / "HALT")     # ENOTDIR on stat
        engine = PolicyEngine(registry, approvals, protocols, switch)
        assert switch.is_engaged() is True
        assert "failing closed" in (switch.reason() or "")

        # Everything actionable stops...
        decision = engine.evaluate(Request("ci.rerun_job", "job-1"))
        assert decision.outcome is Outcome.DENY and "kill switch" in decision.reason

        # ...but a human can still look, which is how you diagnose a halt.
        assert engine.evaluate(
            Request("ci.read_status", "r", actor="user")
        ).outcome is Outcome.ALLOW

    def test_a_sentinel_whose_directory_vanished_fails_closed(self, tmp_path):
        """The failure mode a presence-encoded switch invites: the file is
        absent because the *volume* is gone, and absence reads as "carry on".
        Absent from a directory we can still see is the only honest not-engaged.
        """
        holder = tmp_path / "mount"
        holder.mkdir()
        switch = FileKillSwitch(holder / "HALT")
        assert switch.is_engaged() is False
        assert switch.reason() is None

        holder.rmdir()                                 # the mount goes away
        assert switch.is_engaged() is True
        assert "unreachable" in (switch.reason() or "")

    def test_an_engaged_sentinel_still_reports_its_reason(self, tmp_path):
        sentinel = tmp_path / "HALT"
        sentinel.write_text("manual halt")
        assert FileKillSwitch(sentinel).reason() == "manual halt"
        sentinel.write_text("   ")
        assert FileKillSwitch(sentinel).reason() == "engaged"
