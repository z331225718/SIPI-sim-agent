# M2 Corpus Golden Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add deterministic HSPICE corpus golden reports by enriching `compat_report.json` and adding synthetic-real corpus fixtures.

**Architecture:** Keep `run-hspice` as the single artifact generator. Extend `CompatReport` with stable metadata, audit, normalized outputs, and summary fields, then use pytest corpus tests to compare generated reports and selected converted decks against checked-in golden files.

**Tech Stack:** Python dataclasses, `hashlib`, `json`, `pathlib.Path`, PyYAML in tests, pytest, existing `agent_spice.hspice` modules.

---

## File Structure

- Modify `src/agent_spice/hspice/manifest.py`: enrich `CompatReport` schema while keeping existing fields.
- Modify `src/agent_spice/hspice/converter.py`: attach audit/output data and unsupported directive summaries.
- Modify `src/agent_spice/cli.py`: populate deck and case metadata before writing reports.
- Modify `tests/test_hspice_converter.py`: test enriched report serialization.
- Modify `tests/test_cli_run_hspice.py`: test deck/case metadata on base and alter cases.
- Create `tests/test_hspice_corpus_golden.py`: run corpus fixtures and compare generated artifacts to golden files.
- Create `tests/fixtures/hspice/corpus/*`: synthetic-real deck corpus, metadata, dependencies, and golden outputs.
- Modify `README.md`: document the corpus/golden verification command.

### Task 1: Enriched Compat Report Schema

**Files:**
- Modify: `src/agent_spice/hspice/manifest.py`
- Modify: `src/agent_spice/hspice/converter.py`
- Test: `tests/test_hspice_converter.py`

- [ ] **Step 1: Write failing report schema test**

Add a converter test that expects `schema_version`, `audit`, `outputs`, and summary status.

```python
def test_compat_report_includes_audit_outputs_and_summary():
    result = convert_hspice_deck(
        ".include 'models.inc'\n"
        ".lib './corners.lib' tt\n"
        ".probe tran v(vdd)\n"
        ".measure tran droop min v(vdd) from=1n to=5n\n"
        ".fft v(vdd)\n"
        ".end\n",
        backend="ngspice",
    )

    data = json.loads(result.report.to_json())

    assert data["schema_version"] == 1
    assert data["audit"]["directive_counts"][".include"] == 1
    assert data["audit"]["libraries"] == [["./corners.lib", "tt"]]
    assert data["audit"]["unsupported_directives"] == [".fft"]
    assert data["outputs"]["probes"] == ["v(vdd)"]
    assert data["outputs"]["measures"][0]["name"] == "droop"
    assert data["unsupported"] == [{"line": ".fft", "reason": "unsupported_directive"}]
    assert data["summary"]["status"] == "blocked"
    assert data["summary"]["rewrites"] == 1
    assert data["summary"]["unsupported"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
python -m pytest tests/test_hspice_converter.py::test_compat_report_includes_audit_outputs_and_summary -v
```

Expected: FAIL because `CompatReport` does not expose the new fields.

- [ ] **Step 3: Implement minimal schema**

Add fields and methods in `CompatReport`:

```python
schema_version: int = 1
deck: dict[str, str] = field(default_factory=dict)
case: dict[str, str | None] = field(default_factory=dict)
audit: dict[str, object] = field(default_factory=dict)
outputs: dict[str, object] = field(default_factory=dict)
summary: dict[str, object] = field(default_factory=dict)
```

In `convert_hspice_deck()`, call `audit_deck(text)` and `normalize_outputs(text)`, attach those results to the report, add unsupported directives, and finalize summary.

- [ ] **Step 4: Verify converter tests pass**

Run:

```powershell
python -m pytest tests/test_hspice_converter.py tests/test_hspice_audit.py tests/test_hspice_measure.py -v
```

Expected: PASS.

### Task 2: CLI Deck and Case Metadata

**Files:**
- Modify: `src/agent_spice/cli.py`
- Test: `tests/test_cli_run_hspice.py`

- [ ] **Step 1: Write failing CLI metadata tests**

Add tests for base and alter report metadata.

```python
def test_run_hspice_report_includes_deck_and_case_metadata(tmp_path: Path):
    deck = tmp_path / "legacy.sp"
    deck.write_text(".probe tran v(vdd)\n.tran 1p 1n\n.end\n", encoding="utf-8")

    exit_code = run_hspice(deck, backend_name="ngspice", output_root=tmp_path / "runs", execute=False)

    report = json.loads((tmp_path / "runs" / "legacy" / "legacy__base" / "compat_report.json").read_text())
    assert exit_code == 0
    assert report["deck"]["id"] == "legacy"
    assert report["deck"]["source"] == "legacy.sp"
    assert len(report["deck"]["sha256"]) == 64
    assert report["case"] == {"name": "legacy__base", "kind": "base", "alter_label": None}
```

```python
def test_run_hspice_report_marks_alter_cases(tmp_path: Path):
    deck = tmp_path / "legacy.sp"
    deck.write_text(
        ".param cdecap=1u\n"
        ".alter high_decap\n"
        ".param cdecap=2u\n"
        ".end\n",
        encoding="utf-8",
    )

    exit_code = run_hspice(deck, backend_name="ngspice", output_root=tmp_path / "runs", execute=False)

    report = json.loads(
        (tmp_path / "runs" / "legacy" / "legacy__alter_001_high_decap" / "compat_report.json").read_text()
    )
    assert exit_code == 0
    assert report["case"] == {
        "name": "legacy__alter_001_high_decap",
        "kind": "alter",
        "alter_label": "high_decap",
    }
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_cli_run_hspice.py::test_run_hspice_report_includes_deck_and_case_metadata tests/test_cli_run_hspice.py::test_run_hspice_report_marks_alter_cases -v
```

Expected: FAIL because `run_hspice()` does not set deck/case metadata.

- [ ] **Step 3: Implement metadata population**

In `run_hspice()`, compute SHA-256 of the original deck text, set `deck.id`, stable source path, and per-case metadata before `write_case_artifacts()`.

- [ ] **Step 4: Verify CLI tests pass**

Run:

```powershell
python -m pytest tests/test_cli_run_hspice.py -v
```

Expected: PASS.

### Task 3: Corpus Fixtures and Golden Tests

**Files:**
- Create: `tests/test_hspice_corpus_golden.py`
- Create: `tests/fixtures/hspice/corpus/vrm_decap_pdn/*`
- Create: `tests/fixtures/hspice/corpus/alter_corners/*`
- Create: `tests/fixtures/hspice/corpus/include_lib_subckt/*`
- Create: `tests/fixtures/hspice/corpus/measure_outputs/*`

- [ ] **Step 1: Create corpus fixtures and failing golden test**

Create four corpus folders, each with `<id>.sp`, `case.yaml`, dependencies if needed, and golden files under `golden/ngspice/<case>/`.

Add this test:

```python
from pathlib import Path
import filecmp

import pytest
import yaml

from agent_spice.cli import run_hspice


CORPUS_ROOT = Path("tests/fixtures/hspice/corpus")


def corpus_cases() -> list[Path]:
    return sorted(path for path in CORPUS_ROOT.iterdir() if (path / "case.yaml").exists())


@pytest.mark.parametrize("case_dir", corpus_cases(), ids=lambda path: path.name)
def test_hspice_corpus_matches_golden_reports_and_decks(case_dir: Path, tmp_path: Path):
    meta = yaml.safe_load((case_dir / "case.yaml").read_text(encoding="utf-8"))
    deck = case_dir / meta["top"]
    backend = "ngspice"

    exit_code = run_hspice(deck, backend_name=backend, output_root=tmp_path / "runs", execute=False)

    assert exit_code == 0
    for case_name in meta["expected_cases"]:
        generated_dir = tmp_path / "runs" / meta["id"] / case_name
        golden_dir = case_dir / "golden" / backend / case_name
        assert (generated_dir / "compat_report.json").read_text(encoding="utf-8") == (
            golden_dir / "compat_report.json"
        ).read_text(encoding="utf-8")
        golden_deck = golden_dir / "case.cir"
        if golden_deck.exists():
            assert filecmp.cmp(generated_dir / "case.cir", golden_deck, shallow=False)
```

- [ ] **Step 2: Run corpus test to verify it fails**

Run:

```powershell
python -m pytest tests/test_hspice_corpus_golden.py -v
```

Expected: FAIL before schema/metadata/golden output align.

- [ ] **Step 3: Align golden files**

After Tasks 1 and 2 pass, generate reports in a temp run, copy deterministic `compat_report.json` and selected `case.cir` outputs into the corpus golden directories, and review them manually.

- [ ] **Step 4: Verify corpus test passes**

Run:

```powershell
python -m pytest tests/test_hspice_corpus_golden.py -v
```

Expected: PASS.

### Task 4: README and Final Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**

Add a corpus verification section:

```powershell
python -m pytest tests/test_hspice_corpus_golden.py -v
```

- [ ] **Step 2: Run final verification**

Run:

```powershell
python -m pytest -v
git diff --check
.\tools\doctor-solvers.ps1 -Smoke
python -m agent_spice.cli run-hspice tests\fixtures\hspice\simple_pi.sp --backend xyce-xdm --output-root runs-m2-corpus-verify --execute
```

Expected: all commands exit 0.

- [ ] **Step 3: Request gpt-5.4 review**

Review focus:

- report schema stability;
- path/hash determinism;
- golden fixture maintainability;
- no regression in M2-A `xyce-xdm`.

Fix Critical and Important findings before commit and push.
