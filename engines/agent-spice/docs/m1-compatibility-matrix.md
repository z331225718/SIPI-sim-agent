# M1 HSPICE Compatibility Matrix

| Feature | Status | Test Coverage |
|---|---|---|
| `.include` / `.inc` | supported; `.inc` is rewritten to `.include` | `tests/test_hspice_converter.py` |
| `.lib` discovery | audited and reported | `tests/test_hspice_audit.py` |
| `.param` passthrough | supported in generated case decks | `tests/fixtures/hspice/simple_pi.sp`, `tests/test_smoke_fixtures.py` |
| `.alter` expansion | supported with deterministic case names | `tests/test_hspice_alter.py`, `tests/test_cli_run_hspice.py` |
| `.probe` to `.print` | supported | `tests/test_hspice_converter.py`, `tests/test_smoke_fixtures.py` |
| `.measure` normalization | supported for output request metadata | `tests/test_hspice_measure.py` |
| Backend command construction | ngspice and Xyce command adapters | `tests/test_backend_commands.py` |
| XDM invocation command | HSPICE-to-Xyce command construction supported | `tests/test_backend_commands.py` |
| Case artifacts | `case.cir` and `compat_report.json` are written per case | `tests/test_deck_builder.py` |
| `run-hspice` CLI | converts HSPICE deck cases without requiring simulator execution | `tests/test_cli_run_hspice.py`, `tests/test_smoke_fixtures.py` |

## Deferred Beyond M1

| Feature | Reason |
|---|---|
| Full Synopsys HSPICE syntax parity | MVP focuses on the PI deck subset and emits compatibility data for unsupported directives. |
| Real ngspice/Xyce execution in unit tests | Tests must not depend on local simulator installations. |
| Production S-parameter model quality gates | Metadata loading and VectorFitting wrapper are in place; deeper quality policy is a later phase. |
