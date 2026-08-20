# P4B-02b51 AMI Text Document Statistics Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b51 (structural statistics over the parsed AMI text AST)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `ami_text_document_stats_v1.rs` in `sipi-ami-text`: `compute_ami_text_document_stats_v1`
computes structural statistics over a parsed `AmiTextDocumentV1` AST (P4B-02b0): total list count
(top-level forms plus nested lists), atom count, quoted token count, and maximum list nesting depth
(a top-level form is depth 1). This complements the tree-level depth/token statistics
(P4B-02b29/02b31) at the raw AST layer. Fail-closed: a document with no forms (`EmptyDocument`) is
strictly rejected. An independent Python reference replicates the tokenize and structural counting
over 4 test cases.

## Result

- 5 Rust unit tests green (mixed document categories; multiple forms; deep nesting max depth;
  quoted tokens not atoms; empty document fails closed).
- Cross-check: 4 test cases (mixed, two forms, deep nesting, empty text) driven through product
  runner `p4b_02b51_ami_text_document_stats_runner`; independent Python reference matches 100% on
  valid flags and all four counts; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b51_ami_text_document_stats.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b51-ami-text-document-stats-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b51-ami-text-document-stats-stage.v1.yaml`; source map
  `p4b-02b51-mit-source-map.v1.yaml`.
- PLAN **P4B-02b51**; ledger note/gate P4B-02; coverage gates 217 -> 218.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Structural only: no semantic interpretation of tokens.
- No release certification, no acceptance evidence.
