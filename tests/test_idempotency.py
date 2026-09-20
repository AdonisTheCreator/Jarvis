"""Exactly-once side effects."""
import pytest

from jarvis_core.idempotency import ClaimState, IdempotencyLedger, derive_key


class TestKeyDerivation:
    def test_incidental_fields_do_not_change_the_key(self):
        """A retry carries a new trace id; it must still hash the same."""
        fields = ("to", "body")
        base = {"to": "sam", "body": "hi"}
        assert derive_key("m.send", "sam", {**base, "trace": "a"}, fields) == derive_key(
            "m.send", "sam", {**base, "trace": "b"}, fields
        )

    def test_meaningful_change_changes_the_key(self):
        fields = ("to", "amount")
        assert derive_key("pay", "acct", {"to": "x", "amount": 40}, fields) != derive_key(
            "pay", "acct", {"to": "x", "amount": 4000}, fields
        )

    def test_occasion_separates_deliberate_repeats(self):
        fields = ("to", "body")
        params = {"to": "sam", "body": "standup?"}
        assert derive_key("m.send", "sam", params, fields, occasion="mon") != derive_key(
            "m.send", "sam", params, fields, occasion="tue"
        )

    def test_missing_field_is_an_error_not_a_silent_key(self):
        with pytest.raises(ValueError, match="missing idempotency fields"):
            derive_key("m.send", "sam", {"to": "sam"}, ("to", "body"))

    def test_capability_with_no_key_fields_is_rejected(self):
        with pytest.raises(ValueError, match="no idempotency_key_fields"):
            derive_key("read.thing", "t", {}, ())


class TestLedger:
    def test_second_claim_is_in_flight_not_fresh(self):
        ledger = IdempotencyLedger()
        assert ledger.claim("k").should_execute is True
        assert ledger.claim("k").should_execute is False

    def test_completed_work_is_not_repeated(self):
        ledger = IdempotencyLedger()
        ledger.claim("k")
        ledger.complete("k", "result-1")
        claim = ledger.claim("k")
        assert claim.state is ClaimState.DONE and claim.result_ref == "result-1"

    def test_release_allows_a_genuine_retry(self):
        ledger = IdempotencyLedger()
        ledger.claim("k")
        ledger.release("k")
        assert ledger.claim("k").should_execute is True

    def test_release_cannot_undo_a_completed_claim(self):
        """Releasing a done claim would permit exactly the duplicate we prevent."""
        ledger = IdempotencyLedger()
        ledger.claim("k")
        ledger.complete("k")
        ledger.release("k")
        assert ledger.state("k") is ClaimState.DONE

    def test_concurrent_claims_yield_exactly_one_executor(self):
        import threading

        ledger = IdempotencyLedger()
        winners: list[bool] = []
        lock = threading.Lock()

        def attempt() -> None:
            won = ledger.claim("shared").should_execute
            with lock:
                winners.append(won)

        threads = [threading.Thread(target=attempt) for _ in range(32)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sum(winners) == 1


class TestHandleBindings:
    """Direct coverage for bind / key_for / unbind -- the claim lifecycle's
    most subtle part, and previously only exercised through the router."""

    def test_bind_and_resolve(self):
        ledger = IdempotencyLedger()
        ledger.claim("k")
        ledger.bind("k", "alpha:job-1")
        assert ledger.key_for("alpha:job-1") == "k"

    def test_unknown_handle_resolves_to_nothing(self):
        assert IdempotencyLedger().key_for("nope:1") is None

    def test_rebinding_the_same_key_is_idempotent(self):
        ledger = IdempotencyLedger()
        ledger.claim("k")
        ledger.bind("k", "alpha:job-1")
        ledger.bind("k", "alpha:job-1")
        assert ledger.key_for("alpha:job-1") == "k"

    def test_two_claims_cannot_share_a_handle_reference(self):
        """Silently overwriting strands the first claim forever."""
        ledger = IdempotencyLedger()
        ledger.claim("first")
        ledger.claim("second")
        ledger.bind("first", "alpha:job-1")
        with pytest.raises(ValueError, match="already bound to a different claim"):
            ledger.bind("second", "alpha:job-1")
        assert ledger.key_for("alpha:job-1") == "first"

    def test_completing_a_claim_drops_every_handle_pointing_at_it(self):
        """Keys hash the action, so a retry shares its predecessor's key. A
        dead handle left bound would settle the retry's live claim."""
        ledger = IdempotencyLedger()
        ledger.claim("k")
        ledger.bind("k", "alpha:job-1")
        ledger.bind("k", "alpha:job-2")
        ledger.complete("k", "result")
        assert ledger.key_for("alpha:job-1") is None
        assert ledger.key_for("alpha:job-2") is None

    def test_releasing_a_claim_drops_its_handles(self):
        ledger = IdempotencyLedger()
        ledger.claim("k")
        ledger.bind("k", "alpha:job-1")
        ledger.release("k")
        assert ledger.key_for("alpha:job-1") is None

    def test_bindings_do_not_leak_between_keys(self):
        ledger = IdempotencyLedger()
        ledger.claim("a")
        ledger.claim("b")
        ledger.bind("a", "alpha:1")
        ledger.bind("b", "alpha:2")
        ledger.complete("a")
        assert ledger.key_for("alpha:1") is None
        assert ledger.key_for("alpha:2") == "b"


class TestGenerations:
    """A late poll from an earlier attempt must not resolve a newer one."""

    def test_each_fresh_claim_gets_a_new_generation(self):
        ledger = IdempotencyLedger()
        first = ledger.claim("k")
        ledger.release("k")
        second = ledger.claim("k")
        assert second.generation > first.generation

    def test_a_stale_complete_is_refused(self):
        ledger = IdempotencyLedger()
        first = ledger.claim("k")
        ledger.release("k", generation=first.generation)
        second = ledger.claim("k")
        assert ledger.complete("k", generation=first.generation) is False
        assert ledger.state("k") is ClaimState.IN_FLIGHT
        assert ledger.complete("k", generation=second.generation) is True

    def test_a_stale_release_is_refused(self):
        ledger = IdempotencyLedger()
        first = ledger.claim("k")
        ledger.release("k", generation=first.generation)
        ledger.claim("k")
        assert ledger.release("k", generation=first.generation) is False
        assert ledger.state("k") is ClaimState.IN_FLIGHT

    def test_completing_a_done_claim_is_refused(self):
        ledger = IdempotencyLedger()
        ledger.claim("k")
        assert ledger.complete("k", "r1") is True
        assert ledger.complete("k", "r2") is False
        assert ledger.claim("k").result_ref == "r1"
