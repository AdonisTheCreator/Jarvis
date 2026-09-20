# Jarvis — working notes

A personal AI operating layer. **One identity, many hands.**

## Orientation, in order

1. `README.md` — what this is and where it stands.
2. `docs/09-DECISIONS.md` — **read this first when resuming.** Every decision,
   why it was taken, and what evidence would reverse it. D1–D18.
3. `docs/05-ARCHITECTURE.md` — layers and contracts.
4. `docs/20-DECISION-CATALOG.md` — where the decision layer is and isn't used.
   44 entries: 33 registered, 11 that are rankings, compound or deployment-scoped.
   `tests/test_decide.py` reads that doc, so the split cannot drift.

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
- **Blobs are namespaced per subject *and key epoch*.** Sharing across subjects
  leaves one subject's forget with another's copy readable; sharing across
  epochs lets a write after a forget re-seal the blob and un-forget the old
  event. Both halves pull against each other and both are tested.
- **A Protocol's declared target and params bind.** Checking the capability
  name alone makes the fixed parameter set decorative and reintroduces exactly
  the in-the-moment judgment Protocols exist to remove.
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
- **A recall scope is granted, not chosen.** `RecallProjection` takes a
  `RecallAuthority`; the caller asks for a scope and something else decides.
  The Record is the highest-value exfiltration target in the system, so a
  scope the caller picks for itself is not a scope.
- **A guard must be able to fail.** Seven bugs here were guards that could
  not: an inert generation check, a `leaks()` diagnostic blind to the broken
  fan-out it existed to detect, a kill switch whose fail-closed branch was
  unreachable because `Path.exists()` swallows the errno, and a
  `Capability.__post_init__` that computed a condition and then did nothing
  with it. Break the thing a guard protects and watch it go red, or it is
  decoration. `tools/mutation_sweep.py` does this wholesale (D20).
- **"No undo" is a declaration, not an absence.** An external, irreversible
  capability must set `undo` — a compensating capability, or `NO_UNDO`. `None`
  means nobody has said, and the checkpoint's irreversible bucket needs to
  tell those apart.
- **A class the core does not own may be indexed, never copied.** `procedural`
  lives in SKILL.md files and `operational` in the control plane; a canonical
  copy here is a second owner, which is the drift docs/04 Rule 2 forbids.
- **The claim token carries its generation.** Keys hash the *action*, so every
  retry shares its predecessor's key; without the generation a late resolution
  settles a newer attempt. Anything unclear holds the claim — guessing sends
  the message twice or never.

## Commands

```bash
python3 -m pytest -q          # 406 tests, ~1.5s
python3 -m pytest tests/test_invariants.py    # the vendor-freedom check
python3 tools/mutation_sweep.py               # break each guard; see if a test notices
```

`mutation_sweep.py` is slow (~7 min for the whole core) and is meant to be run
after adding a guard, not on every change. A survivor is a branch nothing
asserts; read them rather than the count, since it scores branches, not whether
the *right* test failed.

## Status

Phase 0 is complete and tested. Phase 0.5 is next: the Personal Jarvis audit is
done statically (`docs/18`) and needs a VM for wake-to-ack; the control-plane
bake-off (`docs/10`) is now validation rather than selection, since D12 chose
Hermes.
