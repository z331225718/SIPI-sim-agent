"""Replay the authorized exact-fixture AMI candidate lifecycle on Windows only."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from typing import Any

from verify_m5b_ami_candidate_bundle import verify as verify_bundle
from verify_m5b_ami_vendor_fixture_preflight import blob, verify as verify_fixture


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DOCUMENT = ROOT / "docs/baselines/m5b-ami-vendor-fixture-preflight.v1.json"
REQUEST_SCHEMA = "agent-spice.ami-host-request.v1"
RESULT_SCHEMA = "agent-spice.ami-host-result.v1"
REPORT_SCHEMA = "sipi.m5b-ami-authorized-runtime-replay-report.v1"
PARAMETERS = "(example_rx)"
SAMPLE_INTERVAL = 1e-12
BIT_TIME = 1e-10
VALUES = (1.0, -1.0)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value: object) -> str:
    return sha256_bytes(json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii"))


def reject(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def external(path: Path, *forbidden: Path) -> Path:
    resolved = path.resolve()
    for root in forbidden:
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            continue
        raise ValueError(f"path must stay outside source and bundle trees: {resolved}")
    return resolved


def descriptor(path: Path, *, element_count: int | None = None) -> dict[str, Any]:
    data = path.read_bytes()
    result: dict[str, Any] = {"path": path.name, "sha256": sha256_bytes(data), "byteLength": len(data)}
    if element_count is not None:
        reject(len(data) == element_count * 8, "f64 sidecar size")
        result.update({"elementCount": element_count, "encoding": "f64le", "endianness": "little"})
    return result


def write_f64(path: Path, values: tuple[float, ...]) -> dict[str, Any]:
    path.write_bytes(struct.pack(f"<{len(values)}d", *values))
    return descriptor(path, element_count=len(values))


def request_document(model: dict[str, dict[str, Any]], init: dict[str, Any], wave: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": REQUEST_SCHEMA,
        "mode": "init-get-wave",
        "model": model,
        "expectedMetadata": {"amiVersion": "5.1", "initReturnsImpulse": True, "getWaveExists": True},
        "sampleIntervalSeconds": SAMPLE_INTERVAL,
        "bitTimeSeconds": BIT_TIME,
        "amiParametersIn": PARAMETERS,
        "initImpulse": init,
        "getWave": {"waveform": wave, "clockCapacity": 8},
    }


def contained_file(directory: Path, name: str) -> Path:
    reject(isinstance(name, str) and Path(name).name == name and name not in {"", ".", ".."}, "sidecar basename")
    path = (directory / name).resolve()
    try:
        path.relative_to(directory.resolve())
    except ValueError as error:
        raise ValueError("sidecar containment") from error
    reject(path.is_file(), "sidecar missing")
    return path


def verify_f64_descriptor(value: object, output: Path, expected_count: int | None = None) -> dict[str, Any]:
    reject(isinstance(value, dict), "f64 descriptor")
    path = contained_file(output, value.get("path"))
    data = path.read_bytes()
    count = value.get("elementCount")
    reject(isinstance(count, int) and not isinstance(count, bool) and count >= 0, "f64 element count")
    if expected_count is not None:
        reject(count == expected_count, "f64 element count mismatch")
    reject(value.get("byteLength") == len(data) == count * 8, "f64 byte length")
    reject(value.get("sha256") == sha256_bytes(data), "f64 hash")
    reject(value.get("encoding") == "f64le" and value.get("endianness") == "little", "f64 encoding")
    if count:
        reject(all(math.isfinite(number) for number in struct.unpack(f"<{count}d", data)), "f64 finite")
    return {"sha256": value["sha256"], "elementCount": count, "byteLength": len(data)}


def verify_result(
    result: object,
    *,
    request_sha256: str,
    bundle: dict[str, Any],
    model: dict[str, dict[str, Any]],
    output: Path,
) -> dict[str, Any]:
    reject(isinstance(result, dict), "result JSON object")
    reject(result.get("schema") == RESULT_SCHEMA and result.get("mode") == "init-get-wave", "result schema or mode")
    reject(result.get("requestSha256") == request_sha256, "request echo")
    candidate = result.get("candidate")
    reject(isinstance(candidate, dict) and candidate.get("mode") == "rust-host-candidate", "candidate mode")
    reject(candidate.get("platform") == "windows-x86_64", "candidate platform")
    reject(candidate.get("executableSha256") == bundle["candidateSha256"], "candidate identity")
    expected_capability = bundle["manifest"]["executable"]["buildInfo"]["candidateCapabilities"]["amiHostCandidate"]
    actual_capability = candidate.get("buildInfo", {}).get("candidateCapabilities", {}).get("amiHostCandidate")
    reject(actual_capability == expected_capability, "candidate capability echo")
    reject(result.get("model") == model, "model identity")
    reject(result.get("metadata") == {"amiVersion": "5.1", "initReturnsImpulse": True, "getWaveExists": True}, "metadata")
    reject(result.get("lifecycle") == {"initSucceeded": True, "getWaveAttempted": True, "closeSucceeded": True}, "lifecycle")
    init = result.get("init")
    get_wave = result.get("getWave")
    reject(isinstance(init, dict) and isinstance(get_wave, dict), "missing ABI result")
    init_sidecar = verify_f64_descriptor(init.get("impulseResponse"), output, expected_count=len(VALUES))
    waveform_sidecar = verify_f64_descriptor(get_wave.get("waveform"), output, expected_count=len(VALUES))
    clock_sidecar = verify_f64_descriptor(get_wave.get("clockTimes"), output, expected_count=0)
    expected_files = {"result.json", "init-impulse-response.f64le", "get-wave-response.f64le", "clock-times.f64le"}
    actual_files = {path.name for path in output.iterdir() if path.is_file()}
    reject(actual_files == expected_files and all(path.is_file() for path in output.iterdir()), "partial or unexpected output")
    return {"initImpulse": init_sidecar, "getWaveform": waveform_sidecar, "clockTimes": clock_sidecar}


def safe_environment() -> dict[str, str]:
    allow = ("ComSpec", "SystemRoot", "TEMP", "TMP", "WINDIR")
    return {key: os.environ[key] for key in allow if key in os.environ}


def replay(*, bundle_dir: Path, pybert_repo: Path, report_path: Path, timeout_seconds: float) -> dict[str, Any]:
    reject(sys.platform == "win32", "Windows x64 runtime replay is unsupported on this platform")
    reject(timeout_seconds > 0 and math.isfinite(timeout_seconds), "timeout")
    bundle_dir = bundle_dir.resolve()
    pybert_repo = pybert_repo.resolve()
    report_path = external(report_path, ROOT, bundle_dir, pybert_repo)
    reject(not report_path.exists(), "report path already exists")
    fixture_document = json.loads(FIXTURE_DOCUMENT.read_text(encoding="utf-8"))
    fixture = verify_fixture(fixture_document, pybert_repo)
    bundle_report = verify_bundle(bundle_dir, ROOT)
    manifest = json.loads((bundle_dir / "candidate-manifest.json").read_text(encoding="utf-8"))
    bundle_report["manifest"] = manifest
    executable = bundle_dir / manifest["executable"]["bundlePath"]
    work = Path(tempfile.mkdtemp(prefix="m5b-ami-authorized-runtime-"))
    try:
        assets = {asset["kind"]: asset for asset in fixture_document["fixture"]["assets"]}
        names = {"ibs": "example_rx.ibs", "ami": "example_rx.ami", "dll": "example_rx.dll"}
        model: dict[str, dict[str, Any]] = {}
        for kind, name in names.items():
            asset = assets[kind]
            object_id, data = blob(pybert_repo, fixture_document["source"]["commit"], asset["path"])
            reject(object_id == asset["blob"] and len(data) == asset["byteLength"] and sha256_bytes(data) == asset["sha256"], "fixture Git object")
            materialized = work / name
            materialized.write_bytes(data)
            model[{"ibs": "ibis", "ami": "ami", "dll": "dll"}[kind]] = descriptor(materialized)
        init = write_f64(work / "init.f64le", VALUES)
        wave = write_f64(work / "wave.f64le", VALUES)
        request = request_document(model, init, wave)
        request_bytes = (json.dumps(request, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("ascii")
        request_path = work / "request.json"
        request_path.write_bytes(request_bytes)
        output = work / "output"
        completed = subprocess.run(
            [str(executable), "ami-host-candidate", "--request", str(request_path), "--output-dir", str(output)],
            cwd=work, env=safe_environment(), capture_output=True, text=True, timeout=timeout_seconds,
        )
        reject(completed.returncode == 0, "candidate invocation failed")
        result_path = output / "result.json"
        reject(result_path.is_file(), "candidate output missing")
        result_bytes = result_path.read_bytes()
        sidecars = verify_result(
            json.loads(result_bytes), request_sha256=sha256_bytes(request_bytes), bundle=bundle_report,
            model=model, output=output,
        )
        report = {
            "schema": REPORT_SCHEMA,
            "accepted": True,
            "scope": "authorized exact fixture candidate lifecycle replay only",
            "platform": "windows-x86_64",
            "fixture": {"sourceCommit": fixture_document["source"]["commit"], "assets": fixture["assets"]},
            "candidate": {"bundleManifestSha256": bundle_report["manifestSha256"], "executableSha256": bundle_report["candidateSha256"], "productionResolvable": False},
            "request": {"schema": REQUEST_SCHEMA, "sha256": sha256_bytes(request_bytes), "mode": "init-get-wave", "parameters": PARAMETERS},
            "result": {"schema": RESULT_SCHEMA, "sha256": sha256_bytes(result_bytes), "lifecycle": {"initSucceeded": True, "getWaveAttempted": True, "closeSucceeded": True}, "sidecars": sidecars},
            "negativePolicy": {"emptyParameters": "rejected before invocation", "consumableOutput": False},
            "nonClaims": ["not candidate promotion", "not vendor redistribution", "not AMI numerical parity", "not a default or auto route"],
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return report
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--pybert-repo", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    try:
        report = replay(bundle_dir=args.bundle, pybert_repo=args.pybert_repo, report_path=args.report, timeout_seconds=args.timeout_seconds)
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        print(f"authorized AMI runtime replay rejected: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"accepted": report["accepted"], "reportSchema": report["schema"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
