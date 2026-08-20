# P4B-02b61 AMI Text Form Heads Counting Core — Audit Record

- Date (UTC): 2026-08-16
- Scope: P4B-02 sub-slice 02b61 (top-level form head spelling counts)
- Status: delivered and cross-checked against an independent reference;
  P4B-02 main item stays open (reserved-name catalog and profile rules pending)

## Method

Implement `ami_text_form_heads_v1.rs` in `sipi-ami-text`: `count_ami_text_form_heads_v1` counts
the head spellings of the top-level forms of a parsed `AmiTextDocumentV1` AST (P4B-02b0): for each
form, the first item's spelling (atom or quoted token, raw spelling preserved — quoted heads keep
their quotes) is its head; the result maps each distinct head to its occurrence count. This
complements the document statistics (P4B-02b51) with the section-name landscape. Fail-closed: an
empty document (`EmptyDocument`) and any form whose first item is not an atom or quoted token
(`InvalidFormHead` — empty form or nested list head) are strictly rejected. An independent Python
reference replicates the tokenize and head counting over 4 test cases.

## Result

- 5 Rust unit tests green (repeated heads; single form; empty document; nested list head; empty
  form).
- Cross-check: 4 test cases (repeated heads, single form, nested list head, empty text) driven
  through product runner `p4b_02b61_ami_text_form_heads_runner`; independent Python reference
  matches 100% on valid flags, head maps, and error contexts; 4/4 product_owned_self_crosscheck_unbound.

## Binding

- Verifier `verify_p4b_02b61_ami_text_form_heads.py` + 6 tests; crosscheck evidence
  `docs/baselines/p4b-02b61-ami-text-form-heads-crosscheck-evidence.v1.yaml`.
- Charter `p4b-02b61-ami-text-form-heads-stage.v1.yaml`; source map
  `p4b-02b61-mit-source-map.v1.yaml`.
- PLAN **P4B-02b61**; ledger note/gate P4B-02; coverage gates 230 -> 231.

## Scope / Non-Claims

- Not a full AMI document parser; no reserved-name catalog, no defaults, no document decoding.
- Head counting only; no semantic interpretation of heads.
- No release certification, no acceptance evidence.
