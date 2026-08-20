# P4A-03d Typed IBIS Model-Declaration Core - Audit Record

- Date (UTC): 2026-08-16
- Scope: P4A-03 sub-slice 03d (typed Model-declaration semantic core)
- Status: delivered and cross-checked against an independent observer on
  the authorized as4c512m16md4v-053bin.ibs. It lifts typed [Model]
  declarations (name + bounded Model_type) from the structural parser.

## Method

Scan structural records for [Model] blocks; each block's Model_type is a
bare keyword-value data line (Model_type  Input) which the structural
parser emits as a Data record with a Model_type lead token. This slice
reads that data lead token and maps the spelling to a bounded IBIS 5.0
ModelTypeV1 set (canonicalizing I/O to IO). An independent observer
scans the same file for [Model] + Model_type and compares.

## Result

- 67 model declarations lifted, matching the observer's 67.
- Model_type distribution: 27 Input + 40 I/O (product IO).
- sipi-ibis unit suite 45 tests green (7 new model-declaration tests).

## Binding

- Verifier verify_p4a_03d_model_declaration.py + 6 tests; crosscheck
  evidence docs/baselines/p4a-03d-model-declaration-crosscheck-evidence.v1.yaml.
- Charter p4a-03d-model-declaration-stage.v1.yaml; source map
  p4a-03d-mit-source-map.v1.yaml.
- PLAN **P4A-03d**; ledger note/gate P4A-03; coverage gates 92 -> 93.
