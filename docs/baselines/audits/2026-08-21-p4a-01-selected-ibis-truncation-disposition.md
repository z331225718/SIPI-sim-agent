# P4A-01 Selected IBIS Truncation Disposition

## Exact Identity Result

The tracked `fixtures/ibis/as4c512m16md4v-053bin.ibs` object is 4,215,925
bytes with SHA-256
`d72cf62b56d67d30f4004f56ea3b79b4cb1241615692b147682f47540e615a0b`.
It has no `[End]` record and ends mid-token with `9.4000e-`.

The Alliance Memory object retrieved from the canonical product download URL
is 6,138,000 bytes with SHA-256
`53e27609dbb81e7685456a48c611111fed34ca14477623e46a9a9a582a7a646b`.
The tracked object is an exact strict byte prefix of that object and is missing
1,922,075 trailing bytes. The external object has one final `[End]`, 95 model
declarations, four model selectors, and a declared `CKE_PIN` model. Every
selector branch resolves to a declared model.

## Disposition

The tracked object is unusable for a semantic or electrical profile. It may be
used only as an exact structural-prefix/truncation observation. In particular,
the missing `DQ_PIN -> DQ_60OHM_60OHM_PREEMP_ON` declaration must not be
synthesized, and a later unresolved reference must not be guessed from the
truncated bytes.

The complete official bytes remain in external operator custody. Retrieval and
identity observation do not establish redistribution or product-fixture rights,
so this audit does not copy them into the worktree or promote either object into
a runtime, acceptance, or release profile.

This disposition is not general IBIS compatibility, electrical behavior,
transient integration, model/corner/PVT selection, or release evidence.
