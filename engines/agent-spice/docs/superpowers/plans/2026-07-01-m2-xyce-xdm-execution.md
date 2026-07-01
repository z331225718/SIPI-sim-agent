# M2 Xyce XDM Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `agent-spice run-hspice --backend xyce-xdm --execute`, preserving HSPICE source, raw XDM output, normalized Xyce deck, stage logs, and a run summary per case.

**Architecture:** Keep single-command backends unchanged. Extend `XyceBackend` with a two-stage XDM-then-Xyce runner and let the CLI select that path only for `xyce-xdm`. Store stage logs in the existing per-case run directory.

**Tech Stack:** Python dataclasses, `subprocess.run`, `pathlib.Path`, pytest, existing `agent_spice` modules.

---

## File Structure

- Modify `src/agent_spice/backend/xyce.py`: command construction plus two-stage execution result types.
- Modify `src/agent_spice/cli.py`: route `xyce-xdm`, write `case.sp`, write `run_summary.json`.
- Modify `src/agent_spice/project.py`: allow `xyce-xdm` in manifests.
- Modify `tests/test_backend_commands.py`: red/green tests for corrected XDM command and two-stage execution.
- Modify `tests/test_cli_run_hspice.py`: red/green test for CLI artifacts and return code.
- Modify `tests/test_project_manifest.py`: ensure manifests accept `xyce-xdm`.

### Task 1: XDM Command and Two-Stage Backend

**Files:**
- Modify: `src/agent_spice/backend/xyce.py`
- Test: `tests/test_backend_commands.py`

- [ ] **Step 1: Write failing tests**

Add tests that assert the XDM command follows the documented XDM shape and that `run_hspice_via_xdm()` runs XDM before Xyce while writing stage logs.

```python
def test_xyce_xdm_command_converts_hspice_to_xyce(tmp_path: Path):
    source = tmp_path / "legacy.sp"
    output_dir = tmp_path / "xdm-out"

    backend = XyceBackend(xdm_executable="xdm_bdl")

    assert backend.xdm_command_for(source, output_dir) == [
        "xdm_bdl",
        "-s",
        "hspice",
        "-d",
        str(output_dir),
        "-o",
        "xyce",
        str(source),
    ]


def test_xyce_xdm_run_writes_stage_logs_and_summary(tmp_path: Path, monkeypatch):
    source = tmp_path / "case.sp"
    output = tmp_path / "case.cir"
    source.write_text(".end\n", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0] == "xdm_bdl":
            (tmp_path / "xdm-out").mkdir()
            (tmp_path / "xdm-out" / "case.sp").write_text(".end\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="xdm ok", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="xyce ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = XyceBackend(executable="Xyce", xdm_executable="xdm_bdl")

    result = backend.run_hspice_via_xdm(source, output, cwd=tmp_path)

    assert result.ok
    assert result.xdm.ok
    assert result.xyce is not None
    assert result.xyce.ok
    assert commands == [
        ["xdm_bdl", "-s", "hspice", "-d", str(tmp_path / "xdm-out"), "-o", "xyce", str(source.resolve())],
        ["Xyce", str(output.resolve())],
    ]
    assert output.read_text(encoding="utf-8") == ".end\n"
    assert (tmp_path / "xdm.stdout.log").read_text(encoding="utf-8") == "xdm ok"
    assert (tmp_path / "xyce.stdout.log").read_text(encoding="utf-8") == "xyce ok"
```

- [ ] **Step 2: Verify tests fail**

Run:

```powershell
python -m pytest tests/test_backend_commands.py::test_xyce_xdm_command_converts_hspice_to_xyce tests/test_backend_commands.py::test_xyce_xdm_run_writes_stage_logs_and_summary -v
```

Expected: fails because the command currently uses `-d xyce -o <output>` and `run_hspice_via_xdm()` does not exist.

- [ ] **Step 3: Implement minimal backend**

Add dataclasses `XyceXdmRunResult` and method `run_hspice_via_xdm()` in `src/agent_spice/backend/xyce.py`. Use `subprocess.run(..., text=True, capture_output=True, check=False, cwd=cwd)` for both stages. Run XDM with `-d <cwd>/xdm-out -o xyce`, copy `<cwd>/xdm-out/<source name>` to the requested Xyce deck path, then run Xyce on that copied deck.

- [ ] **Step 4: Verify tests pass**

Run:

```powershell
python -m pytest tests/test_backend_commands.py -v
```

Expected: all backend command tests pass.

### Task 2: CLI Artifacts and Backend Selection

**Files:**
- Modify: `src/agent_spice/cli.py`
- Test: `tests/test_cli_run_hspice.py`

- [ ] **Step 1: Write failing CLI test**

Add a test that runs `run_hspice(..., backend_name="xyce-xdm", execute=True)`, monkeypatches `XyceBackend.run_hspice_via_xdm`, and verifies `case.sp`, `case.cir`, stage logs, and `run_summary.json`.

```python
def test_run_hspice_executes_xyce_xdm_and_writes_two_stage_artifacts(tmp_path: Path, monkeypatch):
    from agent_spice.backend.base import BackendResult
    from agent_spice.backend.xyce import XyceXdmRunResult

    deck = tmp_path / "legacy.sp"
    deck.write_text(".probe tran v(vdd)\n.tran 1p 1n\n.end\n", encoding="utf-8")
    recorded: dict[str, Path] = {}

    def fake_run(self, hspice_path: Path, xyce_path: Path, cwd: Path):
        recorded["hspice_path"] = hspice_path
        recorded["xyce_path"] = xyce_path
        recorded["cwd"] = cwd
        xyce_path.write_text(".end\n", encoding="utf-8")
        (cwd / "xdm.stdout.log").write_text("xdm ok", encoding="utf-8")
        (cwd / "xdm.stderr.log").write_text("", encoding="utf-8")
        (cwd / "xyce.stdout.log").write_text("xyce ok", encoding="utf-8")
        (cwd / "xyce.stderr.log").write_text("", encoding="utf-8")
        return XyceXdmRunResult(
            xdm=BackendResult(0, "xdm ok", ""),
            xyce=BackendResult(0, "xyce ok", ""),
        )

    monkeypatch.setattr("agent_spice.backend.xyce.XyceBackend.run_hspice_via_xdm", fake_run)

    exit_code = run_hspice(deck, backend_name="xyce-xdm", output_root=tmp_path / "runs", execute=True)

    run_dir = tmp_path / "runs" / "legacy" / "legacy__base"
    assert exit_code == 0
    assert recorded["hspice_path"] == run_dir / "case.sp"
    assert recorded["xyce_path"] == run_dir / "case.cir"
    assert recorded["cwd"] == run_dir
    assert ".probe tran v(vdd)" in (run_dir / "case.sp").read_text(encoding="utf-8")
    assert (run_dir / "case.cir").read_text(encoding="utf-8") == ".end\n"
    summary = json.loads((run_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["backend"] == "xyce-xdm"
    assert summary["ok"] is True
    assert summary["stages"]["xdm"]["returncode"] == 0
    assert summary["stages"]["xyce"]["returncode"] == 0
```

- [ ] **Step 2: Verify test fails**

Run:

```powershell
python -m pytest tests/test_cli_run_hspice.py::test_run_hspice_executes_xyce_xdm_and_writes_two_stage_artifacts -v
```

Expected: fails because `xyce-xdm` is not accepted and no `case.sp`/summary is written.

- [ ] **Step 3: Implement CLI path**

Update CLI choices, add a `xyce-xdm` branch, write `case.sp` before execution, call `XyceBackend.run_hspice_via_xdm(case.sp, case.cir, cwd=run_dir)`, and write summary JSON with `backend`, `ok`, and per-stage return codes.

- [ ] **Step 4: Verify CLI tests pass**

Run:

```powershell
python -m pytest tests/test_cli_run_hspice.py -v
```

Expected: all CLI tests pass.

### Task 3: Manifest Backend Support and Docs

**Files:**
- Modify: `src/agent_spice/project.py`
- Modify: `README.md`
- Test: `tests/test_project_manifest.py`

- [ ] **Step 1: Write failing manifest test**

Add a test that loads a manifest using `xyce-xdm` and expects it to be accepted.

```python
def test_manifest_accepts_xyce_xdm_backend():
    manifest = ProjectManifest.from_mapping({"name": "demo_pdn", "backend": "xyce-xdm"})

    assert manifest.backend == "xyce-xdm"
```

- [ ] **Step 2: Verify test fails**

Run:

```powershell
python -m pytest tests/test_project_manifest.py::test_manifest_accepts_xyce_xdm_backend -v
```

Expected: fails because `xyce-xdm` is not in `VALID_BACKENDS`.

- [ ] **Step 3: Implement manifest and README update**

Add `xyce-xdm` to `VALID_BACKENDS`. Update README validation instructions to show the new command and expected artifacts.

- [ ] **Step 4: Verify focused and full tests**

Run:

```powershell
python -m pytest -v
git diff --check
```

Expected: all tests pass and whitespace check is clean.

### Task 4: Local Solver Smoke

**Files:**
- No production edits expected.

- [ ] **Step 1: Run local smoke**

Run:

```powershell
python -m pytest -v
.\tools\doctor-solvers.ps1 -Smoke
python -m agent_spice.cli run-hspice tests\fixtures\hspice\simple_pi.sp --backend xyce-xdm --output-root runs-m2-xyce-xdm --execute
```

Expected: tests pass, solver doctor smoke passes, and the `xyce-xdm` run creates `case.sp`, `case.cir`, stage logs, and `run_summary.json`.

- [ ] **Step 2: Final review**

Run code review with gpt-5.4 focused on correctness, artifact naming, subprocess handling, and tests. Fix any Critical or Important findings before commit.
