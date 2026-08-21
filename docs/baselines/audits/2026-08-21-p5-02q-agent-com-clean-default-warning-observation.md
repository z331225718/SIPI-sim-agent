# P5-02q Agent-COM default and warning observation

This additive record captures one exact clean Agent-COM configuration
observation. It records source-backed defaults and a runtime warning only; it
does not claim product parity, a complete warning contract, or acceptance.

## Invocation and inputs

The pinned source is Agent-COM commit `5272ffe74702cd585054d975559b06f8afae7b6e`, tree `7094ab6e84989b218730c52432c70da10261f8ea`. The run loaded the same relative r480 workbook and used `overrides={'COMPUTE_TDILN': 1}`. The exact selected entry point was `load_config(...); cfg.materialize()`; no generated checkout path is part of this record.

Two fresh external observations were byte-identical: 1211 bytes and SHA-256 `4563a0fee6a96098717a347263323ae4a4e6fdc5fc41287d5f05f1dfd53e610c` for each payload. Both reported profile `BehaviorProfile(source_revision='r480', reader_semantics='r480', fix_ids=frozenset())` and options `CDR=MM`, `COMPUTE_TDILN=1`.

## Values and warning

Materialized values were `DER_CDR=0.01`, `Q_budget_adj=0.0`, `R_LM=0.95`, `samples_per_ui=32`, and `trunc=128.0`. The source-backed fallback literals and the `N_tc` prior-value alias are recorded in the companion evidence; this observation does not convert them into product defaults.

Both runs emitted warning code `R480-CONFIG-CONSUMPTION-PARTIAL` with severity `WARNING`. The warning is an observed code/severity pair, not a complete cross-runtime warning schema. The payload also reports one unimplemented and one inactive configuration field; no unobserved field is treated as equivalent or silently accepted.

## Boundary

The observation leaves workbook provenance, duplicate-key behavior across the full profile, warning payload parity, checkpoint alignment, and metric tolerance unresolved. It therefore remains a blocker record and does not close P5-02 or promote release evidence.
