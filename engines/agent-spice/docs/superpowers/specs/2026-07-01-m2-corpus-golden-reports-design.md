# M2 Corpus Golden Reports Design

## Goal

Create a small, repeatable HSPICE compatibility corpus that turns deck compatibility from an ad hoc smoke check into a golden-report regression suite.

## Scope

This slice extends the existing `run-hspice` artifact path. It does not add a new CLI command. The core deliverables are:

- a richer per-case `compat_report.json`;
- a `tests/fixtures/hspice/corpus/` layout for synthetic-real decks;
- golden JSON tests that compare generated compatibility reports with checked-in expected reports.

## Non-Goals

- Do not add the full 10+ internal deck library yet.
- Do not check in private, encrypted, or vendor-proprietary models.
- Do not add waveform or commercial-tool numeric golden comparisons.
- Do not lock full XDM logs or generated solver output text.
- Do not implement deep HSPICE dialect support such as `.data`, `.step`, Monte Carlo, or encrypted models.

## Report Schema

Keep the existing `compat_report.json` filename and preserve the existing top-level `backend`, `actions`, and `unsupported` fields. Add stable, deterministic fields:

```json
{
  "schema_version": 1,
  "backend": "ngspice",
  "deck": {
    "id": "vrm_decap_pdn",
    "source": "tests/fixtures/hspice/corpus/vrm_decap_pdn/vrm_decap_pdn.sp",
    "sha256": "..."
  },
  "case": {
    "name": "vrm_decap_pdn__base",
    "kind": "base",
    "alter_label": null
  },
  "audit": {
    "directive_counts": {},
    "includes": [],
    "libraries": [],
    "unsupported_directives": []
  },
  "outputs": {
    "probes": [],
    "measures": []
  },
  "actions": [],
  "unsupported": [],
  "summary": {
    "status": "auto_converted",
    "rewrites": 0,
    "drops": 0,
    "unsupported": 0
  }
}
```

The report must avoid absolute paths, timestamps, solver versions, and machine-specific fields so golden comparison is stable on local and remote Windows machines.

## Corpus Layout

Keep existing flat fixtures untouched:

```text
tests/fixtures/hspice/
  simple_pi.sp
  alter_pi.sp
```

Add corpus decks under:

```text
tests/fixtures/hspice/corpus/
  vrm_decap_pdn/
    vrm_decap_pdn.sp
    case.yaml
    deps/
      decap.inc
    golden/
      ngspice/
        vrm_decap_pdn__base/
          compat_report.json
          case.cir
  alter_corners/
    alter_corners.sp
    case.yaml
    golden/
      ngspice/
        alter_corners__base/compat_report.json
        alter_corners__alter_001_fast/compat_report.json
        alter_corners__alter_002_slow/compat_report.json
  include_lib_subckt/
    include_lib_subckt.sp
    case.yaml
    deps/
      models.inc
      corners.lib
    golden/
      ngspice/
        include_lib_subckt__base/
          compat_report.json
          case.cir
  measure_outputs/
    measure_outputs.sp
    case.yaml
    golden/
      ngspice/
        measure_outputs__base/compat_report.json
```

Each `case.yaml` records `id`, `top`, `source_kind`, `features`, `expected_cases`, `backends`, `compat_tier`, `deps`, and `notes`. The first implementation uses `ngspice` golden reports because it is the stable lightweight converter path. `xyce-xdm` corpus coverage can be added after this schema settles.

## Data Flow

For each corpus deck:

1. `run_hspice(deck, backend_name="ngspice", output_root=<tmp>, execute=False)` expands `.alter` cases.
2. Each run directory receives `case.cir` and the richer `compat_report.json`.
3. The pytest corpus harness compares generated JSON and selected `case.cir` files to `golden/ngspice/...`.
4. Any report schema drift, case naming drift, audit/output extraction regression, or conversion action regression fails the test.

## Error Handling

Unsupported directives are reported through the existing `unsupported` field and summarized in `summary.status`. For this slice, unsupported diagnostics are directive-level rather than line-precise. Later work can add line numbers and remediation suggestions without changing the corpus layout.

## Testing

Use TDD:

- first add failing tests for enriched report serialization;
- then add failing CLI/case metadata tests;
- then add corpus fixture golden tests;
- finally verify the full suite and run `xyce-xdm` smoke to ensure M2-A was not regressed.

## Follow-Up

After this slice lands, the next step is to add redacted-real team decks and a corpus-level summary report. The later summary should count decks, expanded cases, rewrites, drops, unsupported directives, and pass/fail status per backend.
