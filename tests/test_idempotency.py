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


class TestTokenResolution:
    """Tokens replace the handle-binding protocol: whoever took the claim
    holds the proof needed to resolve it."""

    def test_a_fresh_claim_yields_a_token(self):
        ledger = IdempotencyLedger()
        token = ledger.claim("k").token
        assert token.key == "k" and token.generation >= 1

    def test_completing_with_the_token_records_the_result(self):
        ledger = IdempotencyLedger()
        token = ledger.claim("k").token
        assert ledger.complete(token, "result-1") is True
        assert ledger.claim("k").result_ref == "result-1"

    def test_completing_twice_is_refused(self):
        ledger = IdempotencyLedger()
        token = ledger.claim("k").token
        ledger.complete(token, "r1")
        assert ledger.complete(token, "r2") is False
        assert ledger.claim("k").result_ref == "r1"

    def test_releasing_allows_a_genuine_retry(self):
        ledger = IdempotencyLedger()
        token = ledger.claim("k").token
        assert ledger.release(token) is True
        assert ledger.claim("k").should_execute is True

    def test_release_cannot_undo_a_completed_claim(self):
        """Releasing a done claim would permit exactly the duplicate we prevent."""
        ledger = IdempotencyLedger()
        token = ledger.claim("k").token
        ledger.complete(token)
        assert ledger.release(token) is False
        assert ledger.state("k") is ClaimState.DONE

    def test_each_attempt_gets_a_new_generation(self):
        ledger = IdempotencyLedger()
        first = ledger.claim("k").token
        ledger.release(first)
        second = ledger.claim("k").token
        assert second.generation > first.generation

    def test_a_stale_token_cannot_complete_a_newer_attempt(self):
        """Without this, a late resolution buries a re-claim: release then
        no-ops and the action is suppressed forever."""
        ledger = IdempotencyLedger()
        first = ledger.claim("k").token
        ledger.release(first)
        second = ledger.claim("k").token
        assert ledger.complete(first, "stale") is False
        assert ledger.state("k") is ClaimState.IN_FLIGHT
        assert ledger.complete(second, "fresh") is True

    def test_a_stale_token_cannot_release_a_newer_attempt(self):
        ledger = IdempotencyLedger()
        first = ledger.claim("k").token
        ledger.release(first)
        ledger.claim("k")
        assert ledger.release(first) is False
        assert ledger.state("k") is ClaimState.IN_FLIGHT

    def test_unresolved_claims_are_enumerable(self):
        ledger = IdempotencyLedger()
        ledger.claim("a")
        held = ledger.claim("b").token
        ledger.complete(held)
        assert ledger.in_flight() == ["a"]
