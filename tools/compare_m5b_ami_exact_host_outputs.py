"""Compare retained PyAMI and Rust candidate raw ABI outputs for exact example_rx."""
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

from replay_m5b_ami_authorized_runtime import (
    BIT_TIME, FIXTURE_DOCUMENT, PARAMETERS, REQUEST_SCHEMA, RESULT_SCHEMA,
    SAMPLE_INTERVAL, VALUES, descriptor, external, reject, request_document,
    safe_environment, sha256_bytes, verify_f64_descriptor, verify_result,
)
from verify_m5b_ami_candidate_bundle import verify as verify_bundle
from verify_m5b_ami_vendor_fixture_preflight import blob, verify as verify_fixture


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_COMMIT = "f6ba0311350fc67bd90fa13b8d578312f956d7e7"
PYAMI_PREFIX = "PyAMI/src/pyibisami"
REPORT_SCHEMA = "sipi.m5b-ami-exact-host-output-equivalence-report.v1"


REFERENCE_HELPER = r'''
import json, math, struct, sys
from ctypes import POINTER, byref, c_char_p, c_double, c_long, c_void_p
from pathlib import Path
from pyibisami.ami.model import AMIModel

def digest(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()

def text(pointer):
    if not pointer or pointer.value is None:
        return None
    return pointer.value.decode("utf-8", "strict")

def sidecar(path, values):
    data = struct.pack(f"<{len(values)}d", *values)
    Path(path).write_bytes(data)
    return {"path": Path(path).name, "sha256": digest(data), "byteLength": len(data), "elementCount": len(values), "encoding": "f64le", "endianness": "little"}

def clocks(values):
    result = []
    for value in values:
        if value == -1.0:
            return result
        if not math.isfinite(value) or value < 0.0:
            raise ValueError("invalid AMI_GetWave clock")
        result.append(value)
    raise ValueError("AMI_GetWave clock sentinel missing")

def main():
    work, dll, output = map(Path, sys.argv[1:4])
    params = b"(example_rx)"
    init_values = (1.0, -1.0)
    wave_values = (1.0, -1.0)
    model = AMIModel(str(dll))
    init = model._amiInit
    get_wave = model._amiGetWave
    close = model._amiClose
    init.argtypes = [POINTER(c_double), c_long, c_long, c_double, c_double, c_char_p, POINTER(c_char_p), POINTER(c_void_p), POINTER(c_char_p)]
    init.restype = c_long
    get_wave.argtypes = [POINTER(c_double), c_long, POINTER(c_double), POINTER(c_char_p), c_void_p]
    get_wave.restype = c_long
    close.argtypes = [c_void_p]
    close.restype = c_long
    init_buffer = (c_double * len(init_values))(*init_values)
    init_params = c_char_p()
    memory = c_void_p()
    message = c_char_p()
    close_status = None
    try:
        init_status = init(init_buffer, len(init_values), 0, 1e-12, 1e-10, params, byref(init_params), byref(memory), byref(message))
        if init_status != 1:
            raise ValueError(f"AMI_Init status {init_status}")
        wave = (c_double * len(wave_values))(*wave_values)
        clock_buffer = (c_double * 8)(*([-1.0] * 8))
        get_wave_params = c_char_p()
        get_wave_status = get_wave(wave, len(wave_values), clock_buffer, byref(get_wave_params), memory)
        if get_wave_status != 1:
            raise ValueError(f"AMI_GetWave status {get_wave_status}")
        close_status = close(memory)
        memory = c_void_p()
        if close_status != 1:
            raise ValueError(f"AMI_Close status {close_status}")
        normalized_clocks = clocks(tuple(clock_buffer))
        report = {
            "initStatus": int(init_status), "getWaveStatus": int(get_wave_status), "closeStatus": int(close_status),
            "parametersInUtf8": params.decode("utf-8"), "initParametersOut": text(init_params), "initMessage": text(message),
            "getWaveParametersOut": text(get_wave_params), "clockCapacity": 8, "clockTerminator": -1.0,
            "initImpulse": sidecar(work / "reference-init.f64le", tuple(init_buffer)),
            "getWaveform": sidecar(work / "reference-get-wave.f64le", tuple(wave)),
            "clockTimes": sidecar(work / "reference-clock-times.f64le", tuple(normalized_clocks)),
        }
        output.write_text(json.dumps(report, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    finally:
        if memory.value:
            close_status = close(memory)
            memory = c_void_p()
            if close_status != 1:
                raise ValueError(f"AMI_Close status {close_status}")

if __name__ == "__main__":
    main()
'''


def git(repo: Path, *args: str, text: bool = True) -> str | bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=text)


def materialize_pyami_source(repo: Path, work: Path) -> dict[str, Any]:
    tree = git(repo, "rev-parse", f"{REFERENCE_COMMIT}:{PYAMI_PREFIX}").strip()
    raw = git(repo, "ls-tree", "-r", "-z", REFERENCE_COMMIT, PYAMI_PREFIX, text=False)
    entries = []
    source_root = work / "PyAMI" / "src"
    for item in raw.split(b"\0"):
        if not item:
            continue
        header, encoded_path = item.split(b"\t", 1)
        mode, object_type, object_id = header.decode("ascii").split()
        reject(object_type == "blob", "PyAMI source object")
        path = encoded_path.decode("utf-8")
        reject(path.startswith(f"{PYAMI_PREFIX}/"), "PyAMI source prefix")
        relative = path.removeprefix("PyAMI/src/")
        destination = source_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = git(repo, "show", f"{REFERENCE_COMMIT}:{path}", text=False)
        destination.write_bytes(data)
        entries.append({"path": path, "mode": mode, "blob": object_id, "sha256": sha256_bytes(data)})
    reject(entries, "PyAMI source tree empty")
    entries.sort(key=lambda item: item["path"])
    digest = sha256_bytes(json.dumps(entries, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii"))
    return {"tree": tree, "entryCount": len(entries), "entryDigestSha256": digest, "pythonPath": source_root}


def write_fixture(repo: Path, document: dict[str, Any], work: Path) -> dict[str, dict[str, Any]]:
    assets = {asset["kind"]: asset for asset in document["fixture"]["assets"]}
    names = {"ibs": "example_rx.ibs", "ami": "example_rx.ami", "dll": "example_rx.dll"}
    model: dict[str, dict[str, Any]] = {}
    for kind, name in names.items():
        asset = assets[kind]
        object_id, data = blob(repo, REFERENCE_COMMIT, asset["path"])
        reject(object_id == asset["blob"] and len(data) == asset["byteLength"] and sha256_bytes(data) == asset["sha256"], "fixture Git object")
        target = work / name
        target.write_bytes(data)
        model[{"ibs": "ibis", "ami": "ami", "dll": "dll"}[kind]] = descriptor(target)
    return model


def reference_environment(pyami_path: Path, work: Path) -> dict[str, str]:
    environment = safe_environment()
    home = work / "reference-home"
    home.mkdir(exist_ok=True)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONPATH"] = str(pyami_path)
    environment["HOME"] = str(home)
    environment["USERPROFILE"] = str(home)
    environment["APPDATA"] = str(home / "AppData")
    environment["LOCALAPPDATA"] = str(home / "LocalAppData")
    return environment


def text_observation(value: object) -> dict[str, Any]:
    if value is None:
        return {"present": False, "sha256": None, "byteLength": 0}
    reject(isinstance(value, str) and "\0" not in value, "ABI output text")
    encoded = value.encode("utf-8")
    return {"present": True, "sha256": sha256_bytes(encoded), "byteLength": len(encoded)}


def compare_sidecar(reference: object, candidate: object, reference_root: Path, candidate_root: Path) -> dict[str, Any]:
    left = verify_f64_descriptor(reference, reference_root)
    right = verify_f64_descriptor(candidate, candidate_root)
    left_bytes = (reference_root / reference["path"]).read_bytes()
    right_bytes = (candidate_root / candidate["path"]).read_bytes()
    reject(left_bytes == right_bytes, "host output bytes differ")
    reject(left == right, "host output descriptors differ")
    return left


def compare(*, bundle_dir: Path, pybert_repo: Path, reference_python: Path, report_path: Path, timeout_seconds: float) -> dict[str, Any]:
    reject(sys.platform == "win32", "Windows x64 exact-host comparison is unsupported on this platform")
    reject(timeout_seconds > 0 and math.isfinite(timeout_seconds), "timeout")
    bundle_dir, pybert_repo, reference_python = bundle_dir.resolve(), pybert_repo.resolve(), reference_python.resolve()
    reject(reference_python.is_file(), "reference Python missing")
    report_path = external(report_path, ROOT, bundle_dir, pybert_repo)
    reject(not report_path.exists(), "report path already exists")
    fixture_document = json.loads(FIXTURE_DOCUMENT.read_text(encoding="utf-8"))
    fixture = verify_fixture(fixture_document, pybert_repo)
    bundle = verify_bundle(bundle_dir, ROOT)
    manifest = json.loads((bundle_dir / "candidate-manifest.json").read_text(encoding="utf-8"))
    bundle["manifest"] = manifest
    executable = bundle_dir / manifest["executable"]["bundlePath"]
    work = Path(tempfile.mkdtemp(prefix="m5b-ami-exact-host-"))
    try:
        model = write_fixture(pybert_repo, fixture_document, work)
        pyami = materialize_pyami_source(pybert_repo, work)
        helper = work / "reference_helper.py"
        reference_json = work / "reference.json"
        helper.write_text(REFERENCE_HELPER, encoding="utf-8")
        reference_call = subprocess.run(
            [str(reference_python), str(helper), str(work), str(work / "example_rx.dll"), str(reference_json)],
            cwd=work, env=reference_environment(pyami["pythonPath"], work), capture_output=True, text=True, timeout=timeout_seconds,
        )
        reject(reference_call.returncode == 0 and reference_json.is_file(), "retained PyAMI reference invocation failed")
        reference = json.loads(reference_json.read_text(encoding="utf-8"))
        reject({key: reference.get(key) for key in ("initStatus", "getWaveStatus", "closeStatus")} == {"initStatus": 1, "getWaveStatus": 1, "closeStatus": 1}, "reference lifecycle")
        reject(reference.get("parametersInUtf8") == PARAMETERS and reference.get("clockCapacity") == 8 and reference.get("clockTerminator") == -1.0, "reference canonical call")
        init = descriptor(work / "init.f64le", element_count=len(VALUES)) if (work / "init.f64le").is_file() else None
        wave = descriptor(work / "wave.f64le", element_count=len(VALUES)) if (work / "wave.f64le").is_file() else None
        if init is None or wave is None:
            (work / "init.f64le").write_bytes(struct.pack("<2d", *VALUES))
            (work / "wave.f64le").write_bytes(struct.pack("<2d", *VALUES))
            init, wave = descriptor(work / "init.f64le", element_count=2), descriptor(work / "wave.f64le", element_count=2)
        request = request_document(model, init, wave)
        request_bytes = (json.dumps(request, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("ascii")
        request_path = work / "candidate-request.json"
        request_path.write_bytes(request_bytes)
        output = work / "candidate-output"
        candidate_call = subprocess.run(
            [str(executable), "ami-host-candidate", "--request", str(request_path), "--output-dir", str(output)],
            cwd=work, env=safe_environment(), capture_output=True, text=True, timeout=timeout_seconds,
        )
        reject(candidate_call.returncode == 0, "candidate invocation failed")
        result_path = output / "result.json"
        reject(result_path.is_file(), "candidate output missing")
        result = json.loads(result_path.read_text(encoding="utf-8"))
        candidate_sidecars = verify_result(result, request_sha256=sha256_bytes(request_bytes), bundle=bundle, model=model, output=output)
        equivalent = {
            "initImpulse": compare_sidecar(reference["initImpulse"], result["init"]["impulseResponse"], work, output),
            "getWaveform": compare_sidecar(reference["getWaveform"], result["getWave"]["waveform"], work, output),
            "clockTimes": compare_sidecar(reference["clockTimes"], result["getWave"]["clockTimes"], work, output),
        }
        text_fields = {
            "initParametersOut": (reference.get("initParametersOut"), result["init"].get("parametersOut")),
            "initMessage": (reference.get("initMessage"), result["init"].get("message")),
            "getWaveParametersOut": (reference.get("getWaveParametersOut"), result["getWave"].get("parametersOut")),
        }
        text_results = {}
        for name, (left, right) in text_fields.items():
            reject(left == right, f"{name} differs")
            text_results[name] = text_observation(left)
        report = {
            "schema": REPORT_SCHEMA,
            "accepted": True,
            "scope": "example_rx exact-fixture raw ABI-observable host-output equivalence only",
            "platform": "windows-x86_64",
            "fixture": {"sourceCommit": REFERENCE_COMMIT, "assets": fixture["assets"]},
            "reference": {"kind": "retained-pyami-raw-abi", "pyamiSource": {"tree": pyami["tree"], "entryCount": pyami["entryCount"], "entryDigestSha256": pyami["entryDigestSha256"]}, "lifecycle": {"initStatus": 1, "getWaveStatus": 1, "closeStatus": 1}},
            "candidate": {"bundleManifestSha256": bundle["manifestSha256"], "executableSha256": bundle["candidateSha256"], "productionResolvable": False, "lifecycle": result["lifecycle"]},
            "canonicalCall": {"requestSchema": REQUEST_SCHEMA, "parametersUtf8Sha256": sha256_bytes(PARAMETERS.encode("utf-8")), "parametersByteLength": len(PARAMETERS.encode("utf-8")), "initInputSha256": init["sha256"], "getWaveInputSha256": wave["sha256"], "sampleIntervalSeconds": SAMPLE_INTERVAL, "bitTimeSeconds": BIT_TIME, "rowSize": 2, "aggressors": 0, "clockCapacity": 8, "clockTerminator": -1.0},
            "equivalentOutputs": {"sidecars": equivalent, "text": text_results, "candidateSidecars": candidate_sidecars},
            "nonClaims": ["not general AMI parity", "not AMI Link BER or eye parity", "not a Python high-level pipeline comparison", "not candidate promotion or vendor redistribution", "not Linux or macOS certification"],
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
    parser.add_argument("--reference-python", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    try:
        report = compare(bundle_dir=args.bundle, pybert_repo=args.pybert_repo, reference_python=args.reference_python, report_path=args.report, timeout_seconds=args.timeout_seconds)
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        print(f"exact AMI host-output equivalence rejected: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"accepted": report["accepted"], "reportSchema": report["schema"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
