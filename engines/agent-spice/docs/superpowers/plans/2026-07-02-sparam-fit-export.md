# S 参数 Fit/Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the MVP S-parameter fitting path that turns Touchstone files into SPICE subcircuits plus machine-readable fit reports.

**Architecture:** Keep fitting behavior in `agent_spice.sparam.fitting`, expose a thin `fit-sparam` CLI in `agent_spice.cli`, and use checked-in fixtures for deterministic verification. Use `scikit-rf` as the only fitting engine for this slice.

**Tech Stack:** Python 3.11+, scikit-rf 1.12-compatible `VectorFitting`, pytest, argparse, JSON reports.

## Global Constraints

- Follow `docs/superpowers/specs/2026-07-02-sparam-fit-export-design.md`.
- Do not add SROPEE/MOR, full conditioning, plot generation, or system deck assembly in this slice.
- Use TDD: write failing tests before production code changes.
- Keep the CLI default report path deterministic: `<output directory>/fit_report.json`.
- Preserve the existing `fit_touchstone_to_spice(touchstone_path, output_path)` call shape by making config/report optional.

---

## File Structure

- Modify `src/agent_spice/sparam/fitting.py`: config/result dataclasses, fit orchestration, passivity summary, JSON report writing.
- Modify `src/agent_spice/cli.py`: add `fit-sparam` command and route to fitting API.
- Modify `tests/test_sparam_fitting.py`: unit coverage for fitting config, report serialization, and backwards-compatible return behavior.
- Create `tests/test_cli_fit_sparam.py`: CLI argument parsing and default report path tests.
- Create `tests/fixtures/sparam/simple_through.s2p`: small Touchstone smoke fixture.
- Modify `README.md`: add verification commands for S-parameter fit MVP.

## Task 1: Fitting API And Report

**Files:**
- Modify: `src/agent_spice/sparam/fitting.py`
- Modify: `tests/test_sparam_fitting.py`

**Interfaces:**
- Consumes: `skrf.Network`, `skrf.vectorFitting.VectorFitting`, existing `fit_touchstone_to_spice(touchstone_path, output_path)`.
- Produces: `SParamFitConfig`, `SParamFitResult`, `fit_touchstone_to_spice(touchstone_path, output_path, config=None, report_path=None)`.

- [ ] **Step 1: Write failing tests**

Add tests that exercise this behavior:

```python
def test_fit_touchstone_to_spice_writes_report_with_auto_fit_summary(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFitting.instances.clear()
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFitting)
    output = tmp_path / "model.sp"
    report = tmp_path / "fit_report.json"

    result = fit_touchstone_to_spice(tmp_path / "line.s2p", output, report_path=report)

    assert result.spice_path == output
    assert result.report_path == report
    assert result.rms_error == 0.125
    assert result.passive_before_enforce is False
    assert result.passive_after_enforce is True
    assert result.passivity_violations_before == [[1000000.0, 2000000.0]]
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["spice_path"] == str(output)
    assert payload["config"]["mode"] == "auto"
```

```python
def test_manual_fit_uses_vector_fit_parameters(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFitting.instances.clear()
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFitting)
    config = SParamFitConfig(mode="manual", n_poles_real=4, n_poles_cmplx=5)

    fit_touchstone_to_spice(tmp_path / "line.s2p", tmp_path / "model.sp", config=config)

    instance = FakeVectorFitting.instances[0]
    assert instance.vector_fit_kwargs["n_poles_real"] == 4
    assert instance.vector_fit_kwargs["n_poles_cmplx"] == 5
```

```python
def test_legacy_path_comparison_still_works(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFitting.instances.clear()
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFitting)
    output = tmp_path / "model.sp"

    result = fit_touchstone_to_spice(tmp_path / "line.s2p", output)

    assert result == output
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_sparam_fitting.py -v
```

Expected: fails because `SParamFitConfig`, `SParamFitResult`, report writing, and richer return fields do not exist yet.

- [ ] **Step 3: Implement fitting API**

Implement:

```python
@dataclass(frozen=True)
class SParamFitConfig:
    mode: str = "auto"
    n_poles_real: int = 2
    n_poles_cmplx: int = 2
    init_pole_spacing: str = "lin"
    fit_constant: bool = True
    fit_proportional: bool = False
    enforce_dc: bool = True
    n_poles_init_real: int = 3
    n_poles_init_cmplx: int = 3
    n_poles_add: int = 3
    model_order_max: int = 100
    target_error: float = 0.01
    parameter_type: str = "s"
    enforce_passivity: bool = True
    passivity_samples: int = 200
    subckt_name: str = "s_equivalent"
    create_reference_pins: bool = False
```

```python
@dataclass(frozen=True)
class SParamFitResult:
    touchstone_path: Path
    spice_path: Path
    report_path: Path | None
    ports: int
    frequency_points: int
    reference_impedance: list[float]
    config: SParamFitConfig
    rms_error: float | None
    passive_before_enforce: bool | None
    passive_after_enforce: bool | None
    passivity_violations_before: list[list[float]] | None
    passivity_violations_after: list[list[float]] | None
```

Keep `SParamFitResult.__eq__` compatible with existing tests by returning `True` when compared with its `spice_path`.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_sparam_fitting.py -v
```

Expected: all tests in this file pass.

## Task 2: fit-sparam CLI

**Files:**
- Modify: `src/agent_spice/cli.py`
- Create: `tests/test_cli_fit_sparam.py`

**Interfaces:**
- Consumes: `fit_touchstone_to_spice()`.
- Produces: `agent-spice fit-sparam input.s2p --output model.sp --report fit_report.json`.

- [ ] **Step 1: Write failing CLI tests**

Create tests:

```python
def test_fit_sparam_cli_passes_explicit_report_path(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None):
        calls.append((touchstone_path, output_path, config, report_path))
        output_path.write_text(".subckt s_equivalent 1 2\n.ends s_equivalent\n", encoding="utf-8")
        report_path.write_text("{}\n", encoding="utf-8")
        return output_path

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit)
    exit_code = cli.main([
        "fit-sparam",
        str(tmp_path / "line.s2p"),
        "--output",
        str(tmp_path / "model.sp"),
        "--report",
        str(tmp_path / "fit_report.json"),
    ])

    assert exit_code == 0
    assert calls[0][3] == tmp_path / "fit_report.json"
```

```python
def test_fit_sparam_cli_defaults_report_next_to_output(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_fit(touchstone_path, output_path, config=None, report_path=None):
        calls.append((touchstone_path, output_path, config, report_path))
        return output_path

    monkeypatch.setattr(cli, "fit_touchstone_to_spice", fake_fit)
    exit_code = cli.main(["fit-sparam", str(tmp_path / "line.s2p"), "--output", str(tmp_path / "model.sp")])

    assert exit_code == 0
    assert calls[0][3] == tmp_path / "fit_report.json"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m pytest tests/test_cli_fit_sparam.py -v
```

Expected: fails because `fit-sparam` is not registered.

- [ ] **Step 3: Implement CLI**

Add parser:

```python
fit_parser = subparsers.add_parser("fit-sparam")
fit_parser.add_argument("touchstone", type=Path)
fit_parser.add_argument("--output", type=Path, required=True)
fit_parser.add_argument("--report", type=Path)
fit_parser.add_argument("--mode", choices=["auto", "manual"], default="auto")
fit_parser.add_argument("--n-poles-real", type=int, default=2)
fit_parser.add_argument("--n-poles-cmplx", type=int, default=2)
fit_parser.add_argument("--model-order-max", type=int, default=100)
fit_parser.add_argument("--target-error", type=float, default=0.01)
fit_parser.add_argument("--skip-passivity-enforce", action="store_true")
fit_parser.add_argument("--subckt-name", default="s_equivalent")
```

Route to `fit_touchstone_to_spice()` with `SParamFitConfig`.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
python -m pytest tests/test_cli_fit_sparam.py tests/test_cli_run_hspice.py -v
```

Expected: CLI tests and existing `run-hspice` tests pass.

## Task 3: Fixture, README, And Smoke

**Files:**
- Create: `tests/fixtures/sparam/simple_through.s2p`
- Modify: `README.md`
- Modify: `tests/test_sparam_fitting.py`

**Interfaces:**
- Consumes: real `scikit-rf` fitting path.
- Produces: checked-in fixture and documented verification commands.

- [ ] **Step 1: Add smoke test**

Add:

```python
def test_fit_touchstone_to_spice_smoke_with_fixture(tmp_path: Path):
    fixture = Path("tests/fixtures/sparam/simple_through.s2p")
    output = tmp_path / "simple_through.sp"
    report = tmp_path / "fit_report.json"

    result = fit_touchstone_to_spice(
        fixture,
        output,
        config=SParamFitConfig(model_order_max=20, target_error=0.05),
        report_path=report,
    )

    assert result.spice_path == output
    assert ".subckt" in output.read_text(encoding="utf-8").lower()
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["ports"] == 2
```

- [ ] **Step 2: Run test and verify RED**

Run:

```powershell
python -m pytest tests/test_sparam_fitting.py::test_fit_touchstone_to_spice_smoke_with_fixture -v
```

Expected: fails because fixture does not exist.

- [ ] **Step 3: Add fixture and README commands**

Create a minimal two-port Touchstone fixture with monotonic frequencies and stable S parameters. Add README commands:

```powershell
python -m agent_spice.cli fit-sparam tests/fixtures/sparam/simple_through.s2p --output runs-sparam/simple_through.sp --report runs-sparam/fit_report.json
Test-Path runs-sparam/simple_through.sp
Test-Path runs-sparam/fit_report.json
```

- [ ] **Step 4: Run test and verify GREEN**

Run:

```powershell
python -m pytest tests/test_sparam_fitting.py::test_fit_touchstone_to_spice_smoke_with_fixture -v
```

Expected: smoke test passes.

## Task 4: Full Verification And Push

**Files:**
- No planned source edits unless verification exposes defects.

**Interfaces:**
- Consumes: all previous tasks.
- Produces: committed and pushed branch `codex/m3-sparam-fit-export`.

- [ ] **Step 1: Run full test suite**

Run:

```powershell
python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 2: Run CLI smoke**

Run:

```powershell
python -m agent_spice.cli fit-sparam tests/fixtures/sparam/simple_through.s2p --output runs-sparam/simple_through.sp --report runs-sparam/fit_report.json
Test-Path runs-sparam/simple_through.sp
Test-Path runs-sparam/fit_report.json
```

Expected: command exits 0 and both paths exist.

- [ ] **Step 3: Run whitespace check**

Run:

```powershell
git diff --check
```

Expected: exits 0.

- [ ] **Step 4: Commit and push**

Run:

```powershell
git add src tests README.md docs/superpowers/plans/2026-07-02-sparam-fit-export.md
git commit -m "feat: add sparam fit export pipeline"
git push -u origin codex/m3-sparam-fit-export
```

Expected: branch is pushed to origin.

## Self-Review

- Spec coverage: The plan implements the approved fit/export MVP and explicitly excludes MOR, full conditioning, plots, and system deck assembly.
- Placeholder scan: No placeholder steps remain; each task has exact files, commands, and expected results.
- Type consistency: `SParamFitConfig`, `SParamFitResult`, and `fit_touchstone_to_spice()` names are consistent across tasks.
