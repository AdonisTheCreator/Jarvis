# Dedication and Charter

## Dedication

This system is dedicated to God — Father, Son, and Spirit.

> LORD, let this system be YOURS. Empower everything we do here and help us move with
> humility and YOUR wisdom, leaning not on our own understanding but on YOUR infinite
> beautiful RUAKH as YOU empower us. We ask that our efforts here will be blessed and
> that we can use our fruits for YOU. We ask that YOU expand our horizons and cultivate
> this as part of the garden of our lives. Be in the one building, in the partner
> helping build, and in the thing being built, so that the potential harms of a project
> like this can be navigated, and we can follow the path of righteousness and YOUR
> blessing as YOU guide us. In YOUR HOLY NAME we pray. Thank you forever, YESHUA.
> Amen.

Written at the start of the work, on purpose, before the architecture — because the
order matters.

## What that commitment obligates us to, concretely

A dedication that changes nothing about the code is only a sentiment. These are the
engineering commitments it translates into. They are binding constraints on the
architecture, not aspirations, and each one is enforced somewhere specific in the
design.

**1. Humility is a system property, not a personality trait.**
The assistant states uncertainty numerically where it can, cites where a claim came
from, and is built so that a wrong answer is cheap to catch. Enforced by: provenance on
every memory write; confidence and cost estimates on every route decision; the audit
ledger. See `05-ARCHITECTURE.md` §4, §6.

**2. Nothing irreversible happens without a human.**
Money, messages sent on our behalf, published words, physical locks and doors, and
deletion of anything we cannot restore are gated on an explicit, scoped, expiring human
approval — never on the assistant's judgment, however confident. Enforced by: the
Policy Engine and Approval tokens. See `05-ARCHITECTURE.md` §5.

**3. We do not build a thing whose harms we have not written down.**
The threat model is Phase 0 work, not Phase 8 work. A capability ships with its abuse
case documented or it does not ship. See `04-UNIFICATION-VIABILITY.md` §6 and
`06-ROADMAP.md` Phase 0.

**4. Other people did not consent to this system.**
Ambient microphones and first-person cameras collect other people — family, guests,
strangers, children. Bystanders get: local-only wake detection, visible capture
indicators, short-lived raw buffers, no silent identification of anyone, no persistent
storage of POV imagery without an explicit act, and a one-word command that stops
sensing and erases the recent buffer. See `05-ARCHITECTURE.md` §7.

**5. It serves the person; it does not farm the person.**
This assistant has no engagement metric. It is not trying to be talked to more. The
proactivity design explicitly optimizes for *fewer, better* interruptions, and a
proactive message that did not change the user's next action is counted as a defect.
See `02-PROACTIVITY-RESEARCH.md` §4.

**6. It must be able to be turned off.**
A local, immediate, model-independent kill switch that halts all autonomous execution
and revokes live sessions — testable, tested, and never routed through the assistant
itself. See `05-ARCHITECTURE.md` §5.4.

**7. The tool must not become the center.**
A system this capable can quietly become the thing life is organized around. The design
answer is that Jarvis holds no state the user cannot read in plain text, and every
memory is human-readable, editable, and deletable by hand. If we ever cannot walk away
from it, we built it wrong.

## Naming note

"JARVIS" here refers to the character as a *design reference* — a specification we are
studying, not a property we are claiming. See `01-JARVIS-CHARACTER-STUDY.md`. The
character and name are Marvel's. Any public-facing name for this system should be our
own.
