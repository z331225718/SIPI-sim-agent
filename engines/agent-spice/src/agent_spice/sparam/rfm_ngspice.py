"""Prepare and run RFM models through the Agent-Spice XSPICE code model."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from typing import Any

import numpy as np

from agent_spice.backend.base import BackendResult
from agent_spice.backend.native import NativeEngineBackend, resolve_native_engine
from agent_spice.backend.ngspice import NgspiceBackend
from agent_spice.hspice.audit import audit_deck
from agent_spice.hspice.converter import convert_hspice_deck
from agent_spice.hspice.results import write_ngspice_waveform_csv
from agent_spice.sparam.artifacts import write_cadence_rfm
from agent_spice.sparam.rfm import RfmModel, parse_cadence_rfm


RFM_CODE_MODEL_ENV = "AGENT_SPICE_RFM_CODE_MODEL"
_SUBCKT_TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.$]*$")
_END_DIRECTIVE = re.compile(r"(?im)^\s*\.end\s*(?:$|\*)")


class RfmNgspiceError(RuntimeError):
    """Raised when a direct-RFM ngspice run cannot be prepared safely."""


class RfmNativeError(RuntimeError):
    """Raised when the project-owned direct-RFM engine returns invalid output."""


@dataclass(frozen=True)
class RfmRunArtifacts:
    run_dir: Path
    deck_path: Path
    source_deck_path: Path
    source_rfm_path: Path
    runtime_rfm_path: Path
    wrapper_path: Path
    manifest_path: Path
    model: RfmModel


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bundled_rfm_code_model() -> Path:
    return Path(__file__).resolve().parents[1] / "lib" / "ngspice" / "rfm.cm"


def resolve_rfm_code_model(explicit: str | Path | None = None) -> Path:
    """Resolve the Windows XSPICE code model without changing global ngspice."""

    configured = explicit if explicit is not None else os.environ.get(RFM_CODE_MODEL_ENV)
    candidate = Path(configured).expanduser() if configured else bundled_rfm_code_model()
    resolved = candidate.resolve()
    if not resolved.is_file():
        source = "--code-model" if explicit is not None else (
            RFM_CODE_MODEL_ENV if configured else "bundled code model"
        )
        raise RfmNgspiceError(f"{source} not found: {resolved}")
    return resolved


def write_xspice_rfm_wrapper(
    model: RfmModel,
    path: str | Path,
    *,
    rfm_filename: str,
    subcircuit_name: str,
) -> Path:
    """Write a common-reference wrapper around one dynamic XSPICE vector port."""

    if not _SUBCKT_TOKEN.fullmatch(subcircuit_name):
        raise RfmNgspiceError(
            "subcircuit name must start with a letter/underscore and contain only SPICE token characters"
        )
    if any(character in rfm_filename for character in ('"', "\n", "\r")):
        raise RfmNgspiceError("runtime RFM filename contains unsupported characters")
    output = Path(path)
    pins = [f"p{index}" for index in range(1, model.nports + 1)]
    vector = " ".join(f"{pin} ref" for pin in pins)
    model_name = re.sub(r"[^A-Za-z0-9_]", "_", subcircuit_name) + "_rfm_model"
    content = "\n".join(
        (
            "* Agent-Spice direct RFM wrapper; this is not an expanded SPICE macro-model.",
            f".subckt {subcircuit_name} {' '.join(pins)} ref",
            f"Arfm %gd[{vector}] {model_name}",
            f'.model {model_name} nport_rfm(rfm_file="{rfm_filename}")',
            f".ends {subcircuit_name}",
            "",
        )
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="ascii")
    return output


def _inject_wrapper(deck_text: str, wrapper_filename: str) -> str:
    directive = f".include '{wrapper_filename}'\n"
    matches = list(_END_DIRECTIVE.finditer(deck_text))
    if not matches:
        return deck_text.rstrip() + "\n" + directive + ".end\n"
    match = matches[-1]
    return deck_text[: match.start()] + directive + deck_text[match.start() :]


def _verification_frequencies(model: RfmModel) -> np.ndarray:
    magnitudes = np.abs(model.poles)
    positive = magnitudes[magnitudes > 0.0] / (2.0 * np.pi)
    if positive.size == 0:
        return np.array([0.0, 1.0])
    low = max(float(np.min(positive)) / 100.0, np.finfo(float).tiny)
    high = max(float(np.max(positive)) * 100.0, low * 10.0)
    return np.concatenate(([0.0], np.geomspace(low, high, 64)))


def _stage_local_dependencies(source_root: Path, run_dir: Path, text: str) -> list[str]:
    """Copy a deck's relative include tree while retaining its directory layout."""

    root = source_root.resolve()
    root_audit = audit_deck(text)
    pending = [
        (root, reference)
        for reference in (
            *root_audit.includes,
            *(item[0] for item in root_audit.libraries),
        )
    ]
    seen: set[Path] = set()
    staged: list[str] = []
    while pending:
        parent, reference = pending.pop()
        referenced = Path(reference)
        if referenced.is_absolute():
            continue
        source = (parent / referenced).resolve()
        if source in seen:
            continue
        seen.add(source)
        try:
            relative = source.relative_to(root)
        except ValueError as exc:
            raise RfmNgspiceError(f"relative include escapes the deck directory: {reference}") from exc
        if not source.is_file():
            raise RfmNgspiceError(f"relative include not found: {source}")
        source_text = source.read_text(encoding="utf-8")
        target = run_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(convert_hspice_deck(source_text, backend="ngspice").deck_text, encoding="utf-8")
        staged.append(relative.as_posix())
        nested = audit_deck(source_text)
        pending.extend((source.parent, item) for item in nested.includes)
        pending.extend((source.parent, item[0]) for item in nested.libraries)
    return sorted(staged)


def prepare_rfm_run(
    deck_path: str | Path,
    rfm_path: str | Path,
    *,
    output_root: str | Path = "runs",
    subcircuit_name: str = "rfm_direct",
) -> RfmRunArtifacts:
    """Stage original inputs plus a losslessly normalized runtime RFM."""

    deck = Path(deck_path).resolve()
    rfm = Path(rfm_path).resolve()
    if not deck.is_file():
        raise RfmNgspiceError(f"input deck not found: {deck}")
    if not rfm.is_file():
        raise RfmNgspiceError(f"input RFM not found: {rfm}")

    model = parse_cadence_rfm(rfm)
    run_dir = Path(output_root).resolve() / deck.stem / "rfm_direct"
    run_dir.mkdir(parents=True, exist_ok=True)
    source_deck = run_dir / "case.source.sp"
    source_rfm = run_dir / "model.input.rfm"
    runtime_rfm = run_dir / "model.runtime.rfm"
    wrapper = run_dir / "rfm_direct_wrapper.sp"
    prepared_deck = run_dir / "case.cir"
    manifest_path = run_dir / "rfm_run_manifest.json"

    shutil.copyfile(deck, source_deck)
    shutil.copyfile(rfm, source_rfm)
    write_cadence_rfm(model, runtime_rfm, z0=model.z0)
    runtime_model = parse_cadence_rfm(runtime_rfm)
    frequencies = _verification_frequencies(model)
    delta = runtime_model.evaluate_s(frequencies) - model.evaluate_s(frequencies)
    reconstruction_rms = float(np.sqrt(np.mean(np.abs(delta) ** 2)))
    reconstruction_max = float(np.max(np.abs(delta)))
    if reconstruction_max > 1e-11:
        raise RfmNgspiceError(
            f"runtime RFM normalization changed the response (max error {reconstruction_max:.3e})"
        )

    write_xspice_rfm_wrapper(
        runtime_model,
        wrapper,
        rfm_filename=runtime_rfm.name,
        subcircuit_name=subcircuit_name,
    )
    source_text = source_deck.read_text(encoding="utf-8")
    dependencies = _stage_local_dependencies(deck.parent, run_dir, source_text)
    injected = _inject_wrapper(source_text, wrapper.name)
    conversion = convert_hspice_deck(injected, backend="ngspice")
    prepared_deck.write_text(conversion.deck_text, encoding="utf-8")

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "execution_path": "xspice-nport-rational",
        "refit_performed": False,
        "reference_mode": "common-reference-pin",
        "subcircuit_name": subcircuit_name,
        "model": {
            "nports": model.nports,
            "z0_ohm": model.z0,
            "stored_poles": int(model.poles.size),
            "effective_order": model.effective_order,
        },
        "inputs": {
            "deck": {"path": source_deck.name, "sha256": _sha256(source_deck)},
            "rfm": {"path": source_rfm.name, "sha256": _sha256(source_rfm)},
        },
        "runtime_rfm": {
            "path": runtime_rfm.name,
            "sha256": _sha256(runtime_rfm),
            "normalization": "shared-pole union with zero residues; no vector fitting",
            "verification_samples": int(frequencies.size),
            "reconstruction_rms": reconstruction_rms,
            "reconstruction_max": reconstruction_max,
        },
        "artifacts": {
            "deck": prepared_deck.name,
            "wrapper": wrapper.name,
            "staged_dependencies": dependencies,
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return RfmRunArtifacts(
        run_dir=run_dir,
        deck_path=prepared_deck,
        source_deck_path=source_deck,
        source_rfm_path=source_rfm,
        runtime_rfm_path=runtime_rfm,
        wrapper_path=wrapper,
        manifest_path=manifest_path,
        model=runtime_model,
    )


def execute_rfm_run(
    artifacts: RfmRunArtifacts,
    *,
    ngspice_executable: str = "ngspice",
    code_model: str | Path | None = None,
) -> BackendResult:
    """Execute a prepared direct-RFM deck and retain all logs and metadata."""

    resolved_model = resolve_rfm_code_model(code_model)
    backend = NgspiceBackend(
        executable=ngspice_executable,
        code_models=(resolved_model,),
    )
    result = backend.run(artifacts.deck_path, cwd=artifacts.run_dir)
    assert isinstance(result, BackendResult)
    if result.ok and "nport_rfm ERROR:" in result.stdout + result.stderr:
        result = BackendResult(returncode=2, stdout=result.stdout, stderr=result.stderr)
    (artifacts.run_dir / "stdout.log").write_text(result.stdout, encoding="utf-8")
    (artifacts.run_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")
    waveform = artifacts.run_dir / "waveform.csv"
    waveform_rows = write_ngspice_waveform_csv(result.stdout, waveform) if result.ok else 0
    summary = {
        "schema_version": 1,
        "backend": "ngspice-xspice-rfm",
        "ok": result.ok,
        "returncode": result.returncode,
        "code_model": {"path": str(resolved_model), "sha256": _sha256(resolved_model)},
        "logs": {"stdout": "stdout.log", "stderr": "stderr.log"},
        "waveform": "waveform.csv" if waveform_rows else None,
        "waveform_rows": waveform_rows,
    }
    (artifacts.run_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def _write_native_waveform(payload: dict[str, Any], path: Path) -> int:
    points = payload.get("points")
    if not isinstance(points, list) or not points:
        return 0
    analysis = str(points[0].get("analysis", ""))
    first_point = points[0]
    count = 0
    if analysis == "ac":
        first = first_point.get("complex", {})
        names = list(first) if isinstance(first, dict) else []
        fieldnames = ["frequency"] + [item for name in names for item in (f"real({name})", f"imag({name})")]
    else:
        first = first_point.get("values", {})
        names = list(first) if isinstance(first, dict) else []
        axis = "time" if analysis == "tran" else "sweep"
        fieldnames = [axis, *names]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for point in points:
            if point.get("analysis") != analysis:
                continue
            if analysis == "ac":
                complex_values = point.get("complex", {})
                row: dict[str, Any] = {"frequency": point.get("x")}
                for name in names:
                    value = complex_values.get(name, {})
                    row[f"real({name})"] = value.get("re")
                    row[f"imag({name})"] = value.get("im")
            else:
                row = {axis: point.get("x"), **point.get("values", {})}
            writer.writerow(row)
            count += 1
    return count


def execute_native_rfm_run(
    artifacts: RfmRunArtifacts,
    *,
    engine_path: str | Path | None = None,
    dotnet_executable: str = "dotnet",
    subcircuit_name: str = "rfm_direct",
) -> BackendResult:
    """Execute a prepared RFM deck without ngspice or the XSPICE code-model DLL."""

    resolved_engine = resolve_native_engine(engine_path)
    result_json = artifacts.run_dir / "native_result.json"
    waveform = artifacts.run_dir / "waveform.csv"
    backend = NativeEngineBackend(
        engine_path=resolved_engine,
        rfm_path=artifacts.runtime_rfm_path,
        rfm_subcircuit=subcircuit_name,
        executable=dotnet_executable,
        output_json_path=result_json,
        waveform_csv_path=waveform,
    )
    result = backend.run(artifacts.deck_path, cwd=artifacts.run_dir)
    waveform_rows = 0
    if result.ok:
        try:
            parsed = json.loads(result.stdout)
            if not isinstance(parsed, dict):
                raise TypeError("top-level native result must be an object")
            waveform_rows = int(parsed.get("waveformRows", 0))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            result = BackendResult(
                returncode=2,
                stdout=result.stdout,
                stderr=result.stderr + f"native result parse failed: {exc}\n",
            )
    (artifacts.run_dir / "stdout.log").write_text(result.stdout, encoding="utf-8")
    (artifacts.run_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")
    summary = {
        "schema_version": 1,
        "backend": "agent-spice-native-rfm",
        "ok": result.ok,
        "returncode": result.returncode,
        "engine": {"path": str(resolved_engine), "sha256": _sha256(resolved_engine)},
        "logs": {"stdout": "stdout.log", "stderr": "stderr.log"},
        "result": result_json.name if result.ok and result_json.is_file() else None,
        "waveform": waveform.name if waveform_rows else None,
        "waveform_rows": waveform_rows,
    }
    (artifacts.run_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result
