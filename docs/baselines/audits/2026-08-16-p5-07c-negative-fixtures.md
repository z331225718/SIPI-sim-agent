# P5-07c Negative Fixture Executions — Audit Record

- Date (UTC): 2026-08-16
- Scope: P5-07 sub-slice 07c (executable negative fixtures over the
  property checker)
- Status: delivered and mechanically bound; P5-07 property/negative
  surface complete (product-side validation still pending sipi-com)

## Method

Ten single-point mutations of the canonical JSON v2, each asserted to be
rejected by the property checker: bad kind; non-finite literal;
unparsable literal; unquoted string literal; invalid inf literal;
evaluated default without value; needs-oracle default without
expression; resolved reference without chain; invalid required flag;
empty entry.

## Result

- 10/10 mutations rejected as expected (one mutation bug found and fixed:
  update() kept the original value, so the evaluated-no-value case
  initially passed; mutations now explicitly remove fields).
- Evidence `p5-07-negative-fixture-evidence.v1.yaml`, hash-bound.

## Scope discipline

No compare, no product validation (sipi-com pending); the negative
surface defines what must fail, executable today.

## Binding

- Verifier `verify_p5_07c_negative_fixtures.py` + 4 tests;
- PLAN **P5-07c**; ledger note/gate; coverage gates 88 -> 89.
