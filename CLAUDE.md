# Jarvis — working notes

A personal AI operating layer. **One identity, many hands.**

## Orientation, in order

1. `README.md` — what this is and where it stands.
2. `docs/09-DECISIONS.md` — **read this first when resuming.** Every decision,
   why it was taken, and what evidence would reverse it. D1–D18.
3. `docs/05-ARCHITECTURE.md` — layers and contracts.
4. `docs/20-DECISION-CATALOG.md` — where the decision layer is and isn't used.

## The invariant that matters most

> **No module in `src/jarvis_core/` may import a vendor type.**

Control planes, agent runtimes and model providers live behind adapters.
`tests/test_invariants.py` asserts this — it is not a convention. The core's
only third-party dependency is `cryptography`, and that is deliberate: crypto
is the last thing to hand-roll, and everything else being stdlib is what keeps
the core small enough to survive any of its vendors being abandoned.

## Layout

```
src/jarvis_core/
  ids.py          monotonic ULIDs, content addressing
  errors.py       typed failures, structured enough to record
  autonomy.py     A0-A4. Top level because a class belongs to a capability
  capability.py   descriptors, registry, Model Cabinet (D17)
  backend.py      the adapter contract every runtime implements
  idempotency.py  exactly-once side effects
  killswitch.py   read-only from the core; fails closed
  quarantine.py   the Untrusted Ingest Rule; Proposals
  memory.py       canonical memory, provenance, transitive forget
  router.py       authorize -> claim -> execute -> record
  policy/         approvals, Protocols, the engine
  record/         events, crypto-shredding, redaction, store, projections
  decide/         decision points, fallbacks, catalog, calibration
```

## Rules that are easy to break by accident

- **Every event needs `subject_keys`.** An event without one can never be
  forgotten. The constructor refuses.
- **Blobs are namespaced per subject.** Sharing them across subjects means one
  subject's forget leaves another's copy readable.
- **The AAD binds payload → subject; the hash chain binds event → payload.**
  Don't move the binding into the event id; that kills dedup and reopens the
  leak above.
- **A decision point without a fallback cannot be registered.** If you can't
  name one, it's probably a rule wearing a decision's clothes.
- **Low confidence escalates to the *more conservative* option**, named
  explicitly per point. Never the cheaper one.
- **Jev decides; the Policy Engine authorizes.** A calibrated probability is
  never an approval.
- **Runtimes propose memory; the core writes it.**
- **The claim token carries its generation.** Keys hash the *action*, so every
  retry shares its predecessor's key; without the generation a late resolution
  settles a newer attempt. Anything unclear holds the claim — guessing sends
  the message twice or never.

## Commands

```bash
python3 -m pytest -q          # 261 tests, ~0.6s
python3 -m pytest tests/test_invariants.py    # the vendor-freedom check
```

## Status

Phase 0 is complete and tested. Phase 0.5 is next: the Personal Jarvis audit is
done statically (`docs/18`) and needs a VM for wake-to-ack; the control-plane
bake-off (`docs/10`) is now validation rather than selection, since D12 chose
Hermes.
