# HSPICE-Compatible PI MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable Agent-Spice MVP: HSPICE legacy deck ingestion, compatibility reporting, case expansion, backend execution abstraction, and minimal PI inputs for S-parameters and CPM-lite.

**Architecture:** Implement a Python package with small modules: `hspice` owns legacy deck compatibility, `backend` owns ngspice/Xyce process execution, `deck` owns generated simulation decks, `sparam` owns Touchstone metadata/fitting entry points, and `cpm` owns current-source expansion. The first CLI path is `agent-spice run-hspice legacy.sp --backend ngspice|xyce`, with every run producing a compatibility report and reproducible case directory.

**Tech Stack:** Python 3.11+, pytest, PyYAML, scikit-rf, NumPy, ngspice CLI/libngspice later, Xyce CLI/XDM later.

---

## Scope

This plan implements the M1 MVP slice from `docs/pi-spice-simulator-spec.md`. It does not implement recursive convolution, GUI, full Synopsys HSPICE parity, or production-grade MOR. It creates the framework needed to run internal HSPICE PI decks and to add deeper S-parameter/CPM behavior safely.

## File Structure

- Create `pyproject.toml`: package metadata, dependencies, CLI entry point, pytest config.
- Create `src/agent_spice/__init__.py`: package version.
- Create `src/agent_spice/cli.py`: command-line entry points.
- Create `src/agent_spice/project.py`: project manifest parsing and output-directory layout.
- Create `src/agent_spice/hspice/audit.py`: HSPICE lexical scan, include/lib dependency discovery, syntax coverage.
- Create `src/agent_spice/hspice/alter.py`: `.alter` expansion into deterministic run cases.
- Create `src/agent_spice/hspice/measure.py`: `.measure/.probe/.print` normalization.
- Create `src/agent_spice/hspice/converter.py`: backend-specific HSPICE compatibility conversion.
- Create `src/agent_spice/hspice/manifest.py`: compatibility report dataclasses and JSON writer.
- Create `src/agent_spice/backend/base.py`: backend protocol, run result, external process helper.
- Create `src/agent_spice/backend/ngspice.py`: ngspice CLI backend.
- Create `src/agent_spice/backend/xyce.py`: Xyce CLI backend and XDM command construction.
- Create `src/agent_spice/deck/builder.py`: generated deck and case directory writer.
- Create `src/agent_spice/sparam/io.py`: Touchstone metadata loader.
- Create `src/agent_spice/sparam/fitting.py`: scikit-rf VectorFitting wrapper.
- Create `src/agent_spice/cpm/io.py`: CPM-lite JSON loader.
- Create `src/agent_spice/cpm/waveform.py`: PWL current-source renderer.
- Create `tests/fixtures/hspice/simple_pi.sp`: tiny HSPICE PI fixture.
- Create `tests/fixtures/hspice/alter_pi.sp`: `.alter` fixture.
- Create `tests/fixtures/cpm/chiplet_demo.json`: CPM-lite fixture.
- Create focused pytest files under `tests/`.

## Task 1: Package Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `src/agent_spice/__init__.py`
- Create: `tests/test_import.py`

- [ ] **Step 1: Write the failing import test**

```python
# tests/test_import.py
import agent_spice


def test_package_version_is_exposed():
    assert agent_spice.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_import.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'agent_spice'`.

- [ ] **Step 3: Add package metadata**

```toml
# pyproject.toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "agent-spice"
version = "0.1.0"
description = "PI simulation middleware with HSPICE deck compatibility"
requires-python = ">=3.11"
dependencies = [
  "numpy>=1.26",
  "pyyaml>=6.0",
  "scikit-rf>=1.6",
]

[project.scripts]
agent-spice = "agent_spice.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 4: Add package init**

```python
# src/agent_spice/__init__.py
__version__ = "0.1.0"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_import.py -v`

Expected: PASS with `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/agent_spice/__init__.py tests/test_import.py
git commit -m "chore: scaffold agent-spice package"
```

## Task 2: Project Manifest And Run Layout

**Files:**
- Create: `src/agent_spice/project.py`
- Create: `tests/test_project_manifest.py`

- [ ] **Step 1: Write failing manifest tests**

```python
# tests/test_project_manifest.py
from pathlib import Path

from agent_spice.project import ProjectManifest, prepare_run_directory


def test_manifest_loads_hspice_entry(tmp_path: Path):
    manifest_path = tmp_path / "project.yaml"
    manifest_path.write_text(
        """
name: demo_pdn
inputs:
  hspice_deck: legacy/top.sp
backend: ngspice
outputs:
  root: out
""".strip(),
        encoding="utf-8",
    )

    manifest = ProjectManifest.from_yaml(manifest_path)

    assert manifest.name == "demo_pdn"
    assert manifest.hspice_deck == Path("legacy/top.sp")
    assert manifest.backend == "ngspice"
    assert manifest.output_root == Path("out")


def test_prepare_run_directory_is_deterministic(tmp_path: Path):
    run_dir = prepare_run_directory(tmp_path, project_name="demo_pdn", case_name="base")

    assert run_dir == tmp_path / "demo_pdn" / "base"
    assert run_dir.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_project_manifest.py -v`

Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `agent_spice.project`.

- [ ] **Step 3: Implement manifest parsing**

```python
# src/agent_spice/project.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


VALID_BACKENDS = {"ngspice", "xyce"}


@dataclass(frozen=True)
class ProjectManifest:
    name: str
    hspice_deck: Path | None
    backend: str
    output_root: Path

    @classmethod
    def from_yaml(cls, path: Path) -> "ProjectManifest":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Manifest {path} must contain a mapping")
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "ProjectManifest":
        name = str(data["name"])
        backend = str(data.get("backend", "ngspice")).lower()
        if backend not in VALID_BACKENDS:
            raise ValueError(f"Unsupported backend '{backend}'. Expected one of {sorted(VALID_BACKENDS)}")
        inputs = data.get("inputs", {})
        outputs = data.get("outputs", {})
        hspice_deck = inputs.get("hspice_deck")
        return cls(
            name=name,
            hspice_deck=Path(hspice_deck) if hspice_deck else None,
            backend=backend,
            output_root=Path(outputs.get("root", "runs")),
        )


def prepare_run_directory(root: Path, project_name: str, case_name: str) -> Path:
    run_dir = root / project_name / case_name
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_project_manifest.py -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/agent_spice/project.py tests/test_project_manifest.py
git commit -m "feat: add project manifest parsing"
```

## Task 3: HSPICE Audit Scanner

**Files:**
- Create: `src/agent_spice/hspice/__init__.py`
- Create: `src/agent_spice/hspice/audit.py`
- Create: `tests/test_hspice_audit.py`

- [ ] **Step 1: Write failing audit tests**

```python
# tests/test_hspice_audit.py
from agent_spice.hspice.audit import audit_deck


def test_audit_detects_directives_and_includes():
    text = """
* demo PI deck
.include 'models/decap.inc'
.lib './corners.lib' tt
.param vdd=0.8
V1 vdd 0 0.8
R1 vdd load 10m
.tran 1p 10n
.measure tran droop min v(load) from=1n to=10n
.end
"""

    report = audit_deck(text)

    assert report.directive_counts[".include"] == 1
    assert report.directive_counts[".lib"] == 1
    assert report.directive_counts[".measure"] == 1
    assert report.includes == ["models/decap.inc"]
    assert report.libraries == [("./corners.lib", "tt")]
    assert report.unsupported_directives == []


def test_audit_reports_unsupported_directive():
    report = audit_deck(".fft v(out)\n.end\n")

    assert report.unsupported_directives == [".fft"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_hspice_audit.py -v`

Expected: FAIL with missing `agent_spice.hspice.audit`.

- [ ] **Step 3: Implement HSPICE audit**

```python
# src/agent_spice/hspice/__init__.py
"""HSPICE compatibility helpers."""
```

```python
# src/agent_spice/hspice/audit.py
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import shlex


SUPPORTED_DIRECTIVES = {
    ".ac",
    ".alter",
    ".dc",
    ".endl",
    ".end",
    ".ends",
    ".global",
    ".inc",
    ".include",
    ".lib",
    ".measure",
    ".meas",
    ".op",
    ".option",
    ".param",
    ".print",
    ".probe",
    ".subckt",
    ".temp",
    ".tran",
}


@dataclass(frozen=True)
class AuditReport:
    directive_counts: dict[str, int]
    includes: list[str]
    libraries: list[tuple[str, str | None]]
    unsupported_directives: list[str]


def _logical_lines(text: str) -> list[str]:
    lines: list[str] = []
    current = ""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("*"):
            continue
        if stripped.startswith("+"):
            current = f"{current} {stripped[1:].strip()}"
            continue
        if current:
            lines.append(current)
        current = stripped
    if current:
        lines.append(current)
    return lines


def _tokens(line: str) -> list[str]:
    return shlex.split(line, comments=False, posix=False)


def _clean_path(token: str) -> str:
    return token.strip("\"'")


def audit_deck(text: str) -> AuditReport:
    counts: Counter[str] = Counter()
    includes: list[str] = []
    libraries: list[tuple[str, str | None]] = []
    unsupported: list[str] = []
    for line in _logical_lines(text):
        if not line.startswith("."):
            continue
        tokens = _tokens(line)
        directive = tokens[0].lower()
        counts[directive] += 1
        if directive in {".include", ".inc"} and len(tokens) >= 2:
            includes.append(_clean_path(tokens[1]))
        if directive == ".lib" and len(tokens) >= 2:
            section = _clean_path(tokens[2]) if len(tokens) >= 3 else None
            libraries.append((_clean_path(tokens[1]), section))
        if directive not in SUPPORTED_DIRECTIVES:
            unsupported.append(directive)
    return AuditReport(
        directive_counts=dict(counts),
        includes=includes,
        libraries=libraries,
        unsupported_directives=unsupported,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_hspice_audit.py -v`

Expected: PASS with `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/agent_spice/hspice/__init__.py src/agent_spice/hspice/audit.py tests/test_hspice_audit.py
git commit -m "feat: audit hspice deck syntax"
```

## Task 4: `.alter` Case Expansion

**Files:**
- Create: `src/agent_spice/hspice/alter.py`
- Create: `tests/test_hspice_alter.py`

- [ ] **Step 1: Write failing alter tests**

```python
# tests/test_hspice_alter.py
from agent_spice.hspice.alter import split_alter_cases


def test_split_alter_cases_keeps_base_and_creates_named_cases():
    text = """
.param cdecap=1u
C1 vdd 0 cdecap
.tran 1p 1n
.alter fast
.param cdecap=2u
.alter slow
.param cdecap=500n
.end
"""

    cases = split_alter_cases(text, stem="legacy")

    assert [case.name for case in cases] == ["legacy__base", "legacy__alter_001_fast", "legacy__alter_002_slow"]
    assert ".param cdecap=1u" in cases[0].text
    assert ".param cdecap=2u" in cases[1].text
    assert ".param cdecap=500n" in cases[2].text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_hspice_alter.py -v`

Expected: FAIL with missing `agent_spice.hspice.alter`.

- [ ] **Step 3: Implement alter splitting**

```python
# src/agent_spice/hspice/alter.py
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class HspiceCase:
    name: str
    text: str


def _case_suffix(header: str, index: int) -> str:
    parts = header.split(maxsplit=1)
    if len(parts) == 1:
        return f"alter_{index:03d}"
    label = re.sub(r"[^a-zA-Z0-9_]+", "_", parts[1].strip()).strip("_").lower()
    return f"alter_{index:03d}_{label}" if label else f"alter_{index:03d}"


def split_alter_cases(text: str, stem: str) -> list[HspiceCase]:
    lines = text.splitlines()
    base: list[str] = []
    alters: list[tuple[str, list[str]]] = []
    current_header: str | None = None
    current_lines: list[str] = []
    for line in lines:
        if line.strip().lower().startswith(".alter"):
            if current_header is not None:
                alters.append((current_header, current_lines))
            current_header = line.strip()
            current_lines = []
            continue
        if current_header is None:
            base.append(line)
        else:
            current_lines.append(line)
    if current_header is not None:
        alters.append((current_header, current_lines))

    base_text = "\n".join(base).strip() + "\n"
    cases = [HspiceCase(name=f"{stem}__base", text=base_text)]
    for index, (header, body) in enumerate(alters, start=1):
        suffix = _case_suffix(header, index)
        case_text = base_text.rstrip() + "\n" + "\n".join(body).strip() + "\n"
        cases.append(HspiceCase(name=f"{stem}__{suffix}", text=case_text))
    return cases
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_hspice_alter.py -v`

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/agent_spice/hspice/alter.py tests/test_hspice_alter.py
git commit -m "feat: expand hspice alter cases"
```

## Task 5: Measurement And Probe Normalization

**Files:**
- Create: `src/agent_spice/hspice/measure.py`
- Create: `tests/test_hspice_measure.py`

- [ ] **Step 1: Write failing measurement tests**

```python
# tests/test_hspice_measure.py
from agent_spice.hspice.measure import normalize_outputs


def test_normalize_measure_and_print():
    text = """
.probe tran v(vdd) i(vsrc)
.print tran v(load)
.measure tran droop min v(load) from=1n to=10n
"""

    outputs = normalize_outputs(text)

    assert outputs.probes == ["v(vdd)", "i(vsrc)", "v(load)"]
    assert outputs.measures[0]["analysis"] == "tran"
    assert outputs.measures[0]["name"] == "droop"
    assert outputs.measures[0]["operation"] == "min"
    assert outputs.measures[0]["target"] == "v(load)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_hspice_measure.py -v`

Expected: FAIL with missing `agent_spice.hspice.measure`.

- [ ] **Step 3: Implement output normalization**

```python
# src/agent_spice/hspice/measure.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutputRequest:
    probes: list[str]
    measures: list[dict[str, str]]


def normalize_outputs(text: str) -> OutputRequest:
    probes: list[str] = []
    measures: list[dict[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        parts = line.split()
        directive = parts[0].lower()
        if directive in {".probe", ".print"} and len(parts) >= 3:
            probes.extend(parts[2:])
        if directive in {".measure", ".meas"} and len(parts) >= 5:
            measures.append(
                {
                    "analysis": parts[1].lower(),
                    "name": parts[2],
                    "operation": parts[3].lower(),
                    "target": parts[4],
                    "raw": line,
                }
            )
    return OutputRequest(probes=probes, measures=measures)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_hspice_measure.py -v`

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/agent_spice/hspice/measure.py tests/test_hspice_measure.py
git commit -m "feat: normalize hspice output requests"
```

## Task 6: Compatibility Report And Converter

**Files:**
- Create: `src/agent_spice/hspice/manifest.py`
- Create: `src/agent_spice/hspice/converter.py`
- Create: `tests/test_hspice_converter.py`

- [ ] **Step 1: Write failing converter tests**

```python
# tests/test_hspice_converter.py
import json

from agent_spice.hspice.converter import convert_hspice_deck


def test_convert_for_ngspice_normalizes_inc_and_probe():
    result = convert_hspice_deck(
        ".inc 'models.inc'\n.probe tran v(vdd)\n.option post=2\n.end\n",
        backend="ngspice",
    )

    assert ".include 'models.inc'" in result.deck_text
    assert ".print tran v(vdd)" in result.deck_text
    assert result.report.actions[0]["kind"] == "rewrite"
    assert result.report.actions[-1]["kind"] == "drop_option"


def test_compat_report_serializes_to_json():
    result = convert_hspice_deck(".end\n", backend="xyce")

    encoded = result.report.to_json()

    assert json.loads(encoded)["backend"] == "xyce"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_hspice_converter.py -v`

Expected: FAIL with missing converter module.

- [ ] **Step 3: Implement compatibility manifest**

```python
# src/agent_spice/hspice/manifest.py
from __future__ import annotations

from dataclasses import dataclass, field
import json


@dataclass
class CompatReport:
    backend: str
    actions: list[dict[str, str]] = field(default_factory=list)
    unsupported: list[dict[str, str]] = field(default_factory=list)

    def add_action(self, kind: str, source: str, target: str = "") -> None:
        self.actions.append({"kind": kind, "source": source, "target": target})

    def add_unsupported(self, line: str, reason: str) -> None:
        self.unsupported.append({"line": line, "reason": reason})

    def to_json(self) -> str:
        return json.dumps(
            {"backend": self.backend, "actions": self.actions, "unsupported": self.unsupported},
            ensure_ascii=False,
            indent=2,
        )
```

- [ ] **Step 4: Implement converter**

```python
# src/agent_spice/hspice/converter.py
from __future__ import annotations

from dataclasses import dataclass

from agent_spice.hspice.manifest import CompatReport


@dataclass(frozen=True)
class ConversionResult:
    deck_text: str
    report: CompatReport


def convert_hspice_deck(text: str, backend: str) -> ConversionResult:
    report = CompatReport(backend=backend)
    output: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        lower = stripped.lower()
        if lower.startswith(".inc "):
            converted = ".include " + stripped.split(maxsplit=1)[1]
            output.append(converted)
            report.add_action("rewrite", stripped, converted)
            continue
        if lower.startswith(".probe "):
            converted = ".print " + stripped.split(maxsplit=1)[1]
            output.append(converted)
            report.add_action("rewrite", stripped, converted)
            continue
        if lower.startswith(".option ") and "post" in lower:
            report.add_action("drop_option", stripped, "")
            continue
        output.append(raw)
    return ConversionResult(deck_text="\n".join(output).strip() + "\n", report=report)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_hspice_converter.py -v`

Expected: PASS with `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/agent_spice/hspice/manifest.py src/agent_spice/hspice/converter.py tests/test_hspice_converter.py
git commit -m "feat: convert hspice deck subset"
```

## Task 7: Backend Process Abstraction

**Files:**
- Create: `src/agent_spice/backend/__init__.py`
- Create: `src/agent_spice/backend/base.py`
- Create: `src/agent_spice/backend/ngspice.py`
- Create: `src/agent_spice/backend/xyce.py`
- Create: `tests/test_backend_commands.py`

- [ ] **Step 1: Write failing backend command tests**

```python
# tests/test_backend_commands.py
from pathlib import Path

from agent_spice.backend.ngspice import NgspiceBackend
from agent_spice.backend.xyce import XyceBackend


def test_ngspice_command_uses_batch_mode(tmp_path: Path):
    deck = tmp_path / "case.cir"
    deck.write_text(".end\n", encoding="utf-8")

    backend = NgspiceBackend(executable="ngspice")

    assert backend.command_for(deck) == ["ngspice", "-b", str(deck)]


def test_xyce_command_uses_deck_path(tmp_path: Path):
    deck = tmp_path / "case.cir"
    deck.write_text(".end\n", encoding="utf-8")

    backend = XyceBackend(executable="Xyce")

    assert backend.command_for(deck) == ["Xyce", str(deck)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_backend_commands.py -v`

Expected: FAIL with missing backend modules.

- [ ] **Step 3: Implement backend base**

```python
# src/agent_spice/backend/__init__.py
"""Simulation backend adapters."""
```

```python
# src/agent_spice/backend/base.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class BackendResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class ProcessBackend:
    executable: str

    def command_for(self, deck_path: Path) -> list[str]:
        raise NotImplementedError

    def run(self, deck_path: Path, cwd: Path | None = None) -> BackendResult:
        completed = subprocess.run(
            self.command_for(deck_path),
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        return BackendResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
```

- [ ] **Step 4: Implement backend commands**

```python
# src/agent_spice/backend/ngspice.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_spice.backend.base import ProcessBackend


@dataclass(frozen=True)
class NgspiceBackend(ProcessBackend):
    executable: str = "ngspice"

    def command_for(self, deck_path: Path) -> list[str]:
        return [self.executable, "-b", str(deck_path)]
```

```python
# src/agent_spice/backend/xyce.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_spice.backend.base import ProcessBackend


@dataclass(frozen=True)
class XyceBackend(ProcessBackend):
    executable: str = "Xyce"
    xdm_executable: str = "xdm_bdl"

    def command_for(self, deck_path: Path) -> list[str]:
        return [self.executable, str(deck_path)]

    def xdm_command_for(self, hspice_path: Path, output_path: Path) -> list[str]:
        return [self.xdm_executable, "-s", "hspice", "-d", "xyce", "-o", str(output_path), str(hspice_path)]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_backend_commands.py -v`

Expected: PASS with `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/agent_spice/backend tests/test_backend_commands.py
git commit -m "feat: add simulator backend command adapters"
```

## Task 8: Deck Builder And Case Artifacts

**Files:**
- Create: `src/agent_spice/deck/__init__.py`
- Create: `src/agent_spice/deck/builder.py`
- Create: `tests/test_deck_builder.py`

- [ ] **Step 1: Write failing deck builder tests**

```python
# tests/test_deck_builder.py
from pathlib import Path

from agent_spice.deck.builder import write_case_artifacts
from agent_spice.hspice.manifest import CompatReport


def test_write_case_artifacts_creates_deck_and_report(tmp_path: Path):
    report = CompatReport(backend="ngspice")

    paths = write_case_artifacts(
        run_dir=tmp_path,
        deck_text=".tran 1p 1n\n.end\n",
        compat_report=report,
    )

    assert paths.deck_path.read_text(encoding="utf-8") == ".tran 1p 1n\n.end\n"
    assert paths.compat_report_path.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_deck_builder.py -v`

Expected: FAIL with missing deck builder module.

- [ ] **Step 3: Implement artifact writer**

```python
# src/agent_spice/deck/__init__.py
"""Deck generation and artifact writers."""
```

```python
# src/agent_spice/deck/builder.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_spice.hspice.manifest import CompatReport


@dataclass(frozen=True)
class CaseArtifacts:
    deck_path: Path
    compat_report_path: Path


def write_case_artifacts(run_dir: Path, deck_text: str, compat_report: CompatReport) -> CaseArtifacts:
    run_dir.mkdir(parents=True, exist_ok=True)
    deck_path = run_dir / "case.cir"
    report_path = run_dir / "compat_report.json"
    deck_path.write_text(deck_text, encoding="utf-8")
    report_path.write_text(compat_report.to_json() + "\n", encoding="utf-8")
    return CaseArtifacts(deck_path=deck_path, compat_report_path=report_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_deck_builder.py -v`

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/agent_spice/deck tests/test_deck_builder.py
git commit -m "feat: write simulation case artifacts"
```

## Task 9: `run-hspice` CLI

**Files:**
- Create: `src/agent_spice/cli.py`
- Create: `tests/test_cli_run_hspice.py`

- [ ] **Step 1: Write failing CLI tests**

```python
# tests/test_cli_run_hspice.py
from pathlib import Path

from agent_spice.cli import run_hspice


def test_run_hspice_writes_cases_without_executing(tmp_path: Path):
    deck = tmp_path / "legacy.sp"
    deck.write_text(".probe tran v(vdd)\n.tran 1p 1n\n.end\n", encoding="utf-8")

    exit_code = run_hspice(
        deck_path=deck,
        backend_name="ngspice",
        output_root=tmp_path / "runs",
        execute=False,
    )

    case_deck = tmp_path / "runs" / "legacy" / "legacy__base" / "case.cir"
    report = tmp_path / "runs" / "legacy" / "legacy__base" / "compat_report.json"
    assert exit_code == 0
    assert ".print tran v(vdd)" in case_deck.read_text(encoding="utf-8")
    assert report.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli_run_hspice.py -v`

Expected: FAIL with missing `agent_spice.cli`.

- [ ] **Step 3: Implement CLI function and argparse entry**

```python
# src/agent_spice/cli.py
from __future__ import annotations

import argparse
from pathlib import Path

from agent_spice.deck.builder import write_case_artifacts
from agent_spice.hspice.alter import split_alter_cases
from agent_spice.hspice.converter import convert_hspice_deck
from agent_spice.project import prepare_run_directory


def run_hspice(deck_path: Path, backend_name: str, output_root: Path, execute: bool) -> int:
    source = deck_path.read_text(encoding="utf-8")
    cases = split_alter_cases(source, stem=deck_path.stem)
    for case in cases:
        conversion = convert_hspice_deck(case.text, backend=backend_name)
        run_dir = prepare_run_directory(output_root, project_name=deck_path.stem, case_name=case.name)
        artifacts = write_case_artifacts(run_dir, conversion.deck_text, conversion.report)
        if execute:
            if backend_name == "ngspice":
                from agent_spice.backend.ngspice import NgspiceBackend

                result = NgspiceBackend().run(artifacts.deck_path, cwd=run_dir)
            elif backend_name == "xyce":
                from agent_spice.backend.xyce import XyceBackend

                result = XyceBackend().run(artifacts.deck_path, cwd=run_dir)
            else:
                raise ValueError(f"Unsupported backend '{backend_name}'")
            (run_dir / "stdout.log").write_text(result.stdout, encoding="utf-8")
            (run_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")
            if not result.ok:
                return result.returncode
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-spice")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run-hspice")
    run_parser.add_argument("deck", type=Path)
    run_parser.add_argument("--backend", choices=["ngspice", "xyce"], default="ngspice")
    run_parser.add_argument("--output-root", type=Path, default=Path("runs"))
    run_parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "run-hspice":
        return run_hspice(args.deck, args.backend, args.output_root, args.execute)
    raise ValueError(f"Unsupported command '{args.command}'")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli_run_hspice.py -v`

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/agent_spice/cli.py tests/test_cli_run_hspice.py
git commit -m "feat: add hspice deck cli flow"
```

## Task 10: Touchstone Metadata Loader

**Files:**
- Create: `src/agent_spice/sparam/__init__.py`
- Create: `src/agent_spice/sparam/io.py`
- Create: `tests/test_sparam_io.py`

- [ ] **Step 1: Write failing Touchstone metadata tests**

```python
# tests/test_sparam_io.py
from pathlib import Path

from agent_spice.sparam.io import load_touchstone_metadata


def test_load_touchstone_metadata_for_s2p(tmp_path: Path):
    s2p = tmp_path / "line.s2p"
    s2p.write_text(
        "\n".join(
            [
                "# Hz S RI R 50",
                "1e6 0 0 1 0 1 0 0 0",
                "2e6 0 0 1 0 1 0 0 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    metadata = load_touchstone_metadata(s2p)

    assert metadata.ports == 2
    assert metadata.frequency_points == 2
    assert metadata.reference_impedance == [50.0, 50.0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sparam_io.py -v`

Expected: FAIL with missing `agent_spice.sparam.io`.

- [ ] **Step 3: Implement Touchstone metadata loader**

```python
# src/agent_spice/sparam/__init__.py
"""S-parameter processing helpers."""
```

```python
# src/agent_spice/sparam/io.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import skrf as rf


@dataclass(frozen=True)
class TouchstoneMetadata:
    ports: int
    frequency_points: int
    reference_impedance: list[float]


def load_touchstone_metadata(path: Path) -> TouchstoneMetadata:
    network = rf.Network(str(path))
    z0 = network.z0[0]
    return TouchstoneMetadata(
        ports=network.nports,
        frequency_points=len(network.f),
        reference_impedance=[float(value.real) for value in z0],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sparam_io.py -v`

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/agent_spice/sparam tests/test_sparam_io.py
git commit -m "feat: load touchstone metadata"
```

## Task 11: scikit-rf Vector Fitting Wrapper

**Files:**
- Create: `src/agent_spice/sparam/fitting.py`
- Create: `tests/test_sparam_fitting.py`

- [ ] **Step 1: Write failing fitting wrapper tests with monkeypatch**

```python
# tests/test_sparam_fitting.py
from pathlib import Path

from agent_spice.sparam.fitting import fit_touchstone_to_spice


class FakeVectorFitting:
    def __init__(self, network):
        self.network = network

    def auto_fit(self):
        return None

    def passivity_enforce(self):
        return None

    def write_spice_subcircuit_s(self, filename):
        Path(filename).write_text(".subckt fitted 1 2\n.ends fitted\n", encoding="utf-8")


class FakeNetwork:
    def __init__(self, path):
        self.path = path


def test_fit_touchstone_to_spice_calls_export(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting.rf, "VectorFitting", FakeVectorFitting)
    output = tmp_path / "model.sp"

    result = fit_touchstone_to_spice(tmp_path / "line.s2p", output)

    assert result == output
    assert ".subckt fitted" in output.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_sparam_fitting.py -v`

Expected: FAIL with missing `agent_spice.sparam.fitting`.

- [ ] **Step 3: Implement fitting wrapper**

```python
# src/agent_spice/sparam/fitting.py
from __future__ import annotations

from pathlib import Path

import skrf as rf


def fit_touchstone_to_spice(touchstone_path: Path, output_path: Path) -> Path:
    network = rf.Network(str(touchstone_path))
    vector_fit = rf.VectorFitting(network)
    vector_fit.auto_fit()
    vector_fit.passivity_enforce()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    vector_fit.write_spice_subcircuit_s(str(output_path))
    return output_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_sparam_fitting.py -v`

Expected: PASS with `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add src/agent_spice/sparam/fitting.py tests/test_sparam_fitting.py
git commit -m "feat: wrap scikit-rf vector fitting export"
```

## Task 12: CPM-lite Loader And PWL Renderer

**Files:**
- Create: `src/agent_spice/cpm/__init__.py`
- Create: `src/agent_spice/cpm/io.py`
- Create: `src/agent_spice/cpm/waveform.py`
- Create: `tests/test_cpm_lite.py`

- [ ] **Step 1: Write failing CPM-lite tests**

```python
# tests/test_cpm_lite.py
from pathlib import Path

from agent_spice.cpm.io import load_cpm_lite
from agent_spice.cpm.waveform import render_pwl_sources


def test_load_cpm_lite_and_render_pwl(tmp_path: Path):
    path = tmp_path / "chip.json"
    path.write_text(
        """
{
  "model": "demo_chip",
  "bumps": [
    {"name": "VDD_A1", "node": "vdd_a1", "return_node": "vss", "waveform": [[0.0, 0.01], [1e-9, 0.05]]}
  ]
}
""".strip(),
        encoding="utf-8",
    )

    model = load_cpm_lite(path)
    deck = render_pwl_sources(model)

    assert model.model == "demo_chip"
    assert "I_VDD_A1 vdd_a1 vss PWL(0.0 0.01 1e-09 0.05)" in deck
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cpm_lite.py -v`

Expected: FAIL with missing `agent_spice.cpm`.

- [ ] **Step 3: Implement CPM-lite loader**

```python
# src/agent_spice/cpm/__init__.py
"""CPM-lite current signature support."""
```

```python
# src/agent_spice/cpm/io.py
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class CpmBump:
    name: str
    node: str
    return_node: str
    waveform: list[tuple[float, float]]


@dataclass(frozen=True)
class CpmLiteModel:
    model: str
    bumps: list[CpmBump]


def load_cpm_lite(path: Path) -> CpmLiteModel:
    data = json.loads(path.read_text(encoding="utf-8"))
    bumps = [
        CpmBump(
            name=item["name"],
            node=item["node"],
            return_node=item.get("return_node", "0"),
            waveform=[(float(t), float(i)) for t, i in item["waveform"]],
        )
        for item in data["bumps"]
    ]
    return CpmLiteModel(model=data["model"], bumps=bumps)
```

- [ ] **Step 4: Implement PWL renderer**

```python
# src/agent_spice/cpm/waveform.py
from __future__ import annotations

from agent_spice.cpm.io import CpmLiteModel


def render_pwl_sources(model: CpmLiteModel) -> str:
    lines: list[str] = []
    for bump in model.bumps:
        points = " ".join(f"{time} {current}" for time, current in bump.waveform)
        lines.append(f"I_{bump.name} {bump.node} {bump.return_node} PWL({points})")
    return "\n".join(lines) + "\n"
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_cpm_lite.py -v`

Expected: PASS with `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/agent_spice/cpm tests/test_cpm_lite.py
git commit -m "feat: load cpm lite current signatures"
```

## Task 13: Legacy Fixtures And Smoke Regression

**Files:**
- Create: `tests/fixtures/hspice/simple_pi.sp`
- Create: `tests/fixtures/hspice/alter_pi.sp`
- Create: `tests/fixtures/cpm/chiplet_demo.json`
- Create: `tests/test_smoke_fixtures.py`

- [ ] **Step 1: Add HSPICE and CPM fixtures**

```spice
* tests/fixtures/hspice/simple_pi.sp
.param vnom=0.8
VVRM vdd 0 vnom
RPDN vdd load 10m
CDECAP load 0 1u
ILOAD load 0 PWL(0 0.01 1n 0.1 5n 0.1)
.probe tran v(load)
.measure tran min_vdd min v(load) from=1n to=5n
.tran 1p 5n
.end
```

```spice
* tests/fixtures/hspice/alter_pi.sp
.param cdecap=1u
VVRM vdd 0 0.8
RPDN vdd load 10m
CDECAP load 0 cdecap
ILOAD load 0 PWL(0 0.01 1n 0.1 5n 0.1)
.probe tran v(load)
.tran 1p 5n
.alter high_decap
.param cdecap=2u
.alter low_decap
.param cdecap=500n
.end
```

```json
{
  "model": "chiplet_demo",
  "bumps": [
    {"name": "VDD_A1", "node": "load", "return_node": "0", "waveform": [[0.0, 0.01], [1e-9, 0.1]]}
  ]
}
```

- [ ] **Step 2: Write smoke tests**

```python
# tests/test_smoke_fixtures.py
from pathlib import Path

from agent_spice.cli import run_hspice


def test_simple_pi_fixture_converts(tmp_path: Path):
    deck = Path("tests/fixtures/hspice/simple_pi.sp")

    exit_code = run_hspice(deck, backend_name="ngspice", output_root=tmp_path, execute=False)

    assert exit_code == 0
    assert (tmp_path / "simple_pi" / "simple_pi__base" / "case.cir").exists()


def test_alter_fixture_creates_three_cases(tmp_path: Path):
    deck = Path("tests/fixtures/hspice/alter_pi.sp")

    exit_code = run_hspice(deck, backend_name="ngspice", output_root=tmp_path, execute=False)

    assert exit_code == 0
    assert (tmp_path / "alter_pi" / "alter_pi__base" / "case.cir").exists()
    assert (tmp_path / "alter_pi" / "alter_pi__alter_001_high_decap" / "case.cir").exists()
    assert (tmp_path / "alter_pi" / "alter_pi__alter_002_low_decap" / "case.cir").exists()
```

- [ ] **Step 3: Run smoke tests**

Run: `python -m pytest tests/test_smoke_fixtures.py -v`

Expected: PASS with `2 passed`.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures tests/test_smoke_fixtures.py
git commit -m "test: add legacy hspice smoke fixtures"
```

## Task 14: Full Test Gate And Documentation Update

**Files:**
- Modify: `docs/pi-spice-simulator-spec.md`
- Create: `docs/m1-compatibility-matrix.md`

- [ ] **Step 1: Add compatibility matrix document**

```markdown
# M1 HSPICE Compatibility Matrix

| Feature | Status | Test Coverage |
|---|---|---|
| `.include` / `.inc` | supported | `tests/test_hspice_converter.py` |
| `.lib` discovery | audited | `tests/test_hspice_audit.py` |
| `.param` passthrough | supported | `tests/fixtures/hspice/simple_pi.sp` |
| `.alter` expansion | supported | `tests/test_hspice_alter.py` |
| `.probe` to `.print` | supported | `tests/test_hspice_converter.py` |
| `.measure` normalization | supported | `tests/test_hspice_measure.py` |
| XDM invocation command | command construction supported | `tests/test_backend_commands.py` |
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest -v`

Expected: PASS with all tests passing.

- [ ] **Step 3: Run CLI smoke command**

Run: `python -m agent_spice.cli run-hspice tests/fixtures/hspice/simple_pi.sp --backend ngspice --output-root runs-smoke`

Expected: exit code 0 and file `runs-smoke/simple_pi/simple_pi__base/case.cir` exists.

- [ ] **Step 4: Commit**

```bash
git add docs/m1-compatibility-matrix.md docs/pi-spice-simulator-spec.md
git commit -m "docs: record m1 compatibility coverage"
```

## Self-Review

- Spec coverage: This plan covers HSPICE audit, conversion, `.alter`, `.measure`, backend abstraction, deck writing, CLI, Touchstone metadata/fitting entry points, CPM-lite, fixtures, and compatibility matrix. It intentionally leaves full S-parameter passivity policy, MOR, real ngspice/libngspice callbacks, Xyce MPI orchestration, and recursive convolution for later plans.
- Placeholder scan: No task depends on an undefined module without first creating it. Unsupported feature handling is implemented as compatibility report data, not silent omission.
- Type consistency: `CompatReport`, `ConversionResult`, `HspiceCase`, `ProjectManifest`, and backend APIs are introduced before later tasks consume them.

