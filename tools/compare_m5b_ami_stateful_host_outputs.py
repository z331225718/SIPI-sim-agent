"""Compare exact example_rx raw ABI lifecycle sequences on retained PyAMI and Rust."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from typing import Any

from compare_m5b_ami_exact_host_outputs import (
    REFERENCE_COMMIT, ROOT, compare_sidecar, external, materialize_pyami_source,
    reference_environment, text_observation, text_observation as observe_text,
    write_fixture,
)
from replay_m5b_ami_authorized_runtime import (
    BIT_TIME, FIXTURE_DOCUMENT, PARAMETERS, SAMPLE_INTERVAL, VALUES, descriptor,
    reject, safe_environment, sha256_bytes, verify_f64_descriptor,
)
from verify_m5b_ami_candidate_bundle import verify as verify_bundle
from verify_m5b_ami_vendor_fixture_preflight import verify as verify_fixture


REQUEST_SCHEMA = "agent-spice.ami-host-request.v2"
RESULT_SCHEMA = "agent-spice.ami-host-result.v1"
REPORT_SCHEMA = "sipi.m5b-ami-stateful-host-output-equivalence-report.v1"
CLOCK_CAPACITY = 8

# Each case runs in a fresh process. The multi-block case is the stateful
# boundary: Init and both GetWave calls share exactly one DLL memory handle.
CASES: tuple[tuple[str, tuple[tuple[float, ...], ...]], ...] = (
    ("init-only", ()),
    ("single-get-wave", ((1.0, -1.0),)),
    ("stateful-two-blocks", ((1.0, -1.0), (0.5, -0.25, 2.0))),
)


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

def sidecar(root, name, values):
    data = struct.pack(f"<{len(values)}d", *values)
    (root / name).write_bytes(data)
    return {"path": name, "sha256": digest(data), "byteLength": len(data), "elementCount": len(values), "encoding": "f64le", "endianness": "little"}

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
    root, dll, call_path, output = map(Path, sys.argv[1:5])
    call = json.loads(call_path.read_text(encoding="utf-8"))
    params = call["parametersUtf8"].encode("utf-8")
    model = AMIModel(str(dll))
    init, get_wave, close = model._amiInit, model._amiGetWave, model._amiClose
    init.argtypes = [POINTER(c_double), c_long, c_long, c_double, c_double, c_char_p, POINTER(c_char_p), POINTER(c_void_p), POINTER(c_char_p)]
    init.restype = c_long
    get_wave.argtypes = [POINTER(c_double), c_long, POINTER(c_double), POINTER(c_char_p), c_void_p]
    get_wave.restype = c_long
    close.argtypes = [c_void_p]
    close.restype = c_long
    init_values = tuple(call["initValues"])
    init_buffer = (c_double * len(init_values))(*init_values)
    init_params, memory, message = c_char_p(), c_void_p(), c_char_p()
    close_called = False
    try:
        init_status = init(init_buffer, len(init_values), 0, call["sampleIntervalSeconds"], call["bitTimeSeconds"], params, byref(init_params), byref(memory), byref(message))
        if init_status != 1:
            raise ValueError(f"AMI_Init status {init_status}")
        init_parameters_out, init_message = text(init_params), text(message)
        waves = []
        for index, values in enumerate(call["getWaveValues"]):
            wave = (c_double * len(values))(*values)
            clock_buffer = (c_double * call["clockCapacity"])(*([-1.0] * call["clockCapacity"]))
            parameters_out = c_char_p()
            status = get_wave(wave, len(values), clock_buffer, byref(parameters_out), memory)
            if status != 1:
                raise ValueError(f"AMI_GetWave[{index}] status {status}")
            waves.append({"status": int(status), "parametersOut": text(parameters_out), "waveform": sidecar(root, f"reference-wave-{index}.f64le", tuple(wave)), "clockTimes": sidecar(root, f"reference-clocks-{index}.f64le", tuple(clocks(clock_buffer)))})
        close_status = close(memory)
        close_called = True
        memory = c_void_p()
        if close_status != 1:
            raise ValueError(f"AMI_Close status {close_status}")
        result = {"initStatus": int(init_status), "closeStatus": int(close_status), "parametersInUtf8": call["parametersUtf8"], "initParametersOut": init_parameters_out, "initMessage": init_message, "initImpulse": sidecar(root, "reference-init.f64le", tuple(init_buffer)), "waves": waves, "clockCapacity": call["clockCapacity"], "clockTerminator": -1.0}
        output.write_text(json.dumps(result, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    finally:
        if memory.value and not close_called:
            status = close(memory)
            if status != 1:
                raise ValueError(f"AMI_Close cleanup status {status}")

if __name__ == "__main__":
    main()
'''


def f64_file(path: Path, values: tuple[float, ...]) -> dict[str, Any]:
    payload = struct.pack(f"<{len(values)}d", *values)
    path.write_bytes(payload)
    return descriptor(path, element_count=len(values))


def require_candidate_capability(bundle: dict[str, Any]) -> None:
    capability = bundle["manifest"]["executable"]["buildInfo"].get("candidateCapabilities", {}).get("amiHostCandidate")
    reject(isinstance(capability, dict), "candidate lifecycle capability missing")
    reject(capability.get("lifecycleRequestSchema") == REQUEST_SCHEMA, "candidate lifecycle request schema")


def request_for_case(work: Path, model: dict[str, Any], name: str, waves: tuple[tuple[float, ...], ...]) -> tuple[Path, bytes, dict[str, Any]]:
    init = f64_file(work / f"{name}-init.f64le", VALUES)
    inputs = []
    for index, values in enumerate(waves):
        inputs.append({"waveform": f64_file(work / f"{name}-wave-{index}.f64le", values), "clockCapacity": CLOCK_CAPACITY})
    document: dict[str, Any] = {
        "schema": REQUEST_SCHEMA,
        "mode": "init" if not inputs else "init-get-wave-sequence",
        "model": model,
        "expectedMetadata": {"amiVersion": "5.1", "initReturnsImpulse": True, "getWaveExists": True},
        "sampleIntervalSeconds": SAMPLE_INTERVAL,
        "bitTimeSeconds": BIT_TIME,
        "amiParametersIn": PARAMETERS,
        "initImpulse": init,
    }
    if inputs:
        document["getWaves"] = inputs
    payload = (json.dumps(document, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("ascii")
    path = work / f"{name}-candidate-request.json"
    path.write_bytes(payload)
    return path, payload, {"init": init, "waves": inputs}


def verify_candidate_case(result: dict[str, Any], output: Path, request_sha256: str, model: dict[str, Any], wave_count: int) -> list[dict[str, Any]]:
    reject(result.get("schema") == RESULT_SCHEMA and result.get("requestSha256") == request_sha256, "candidate result identity")
    lifecycle = result.get("lifecycle")
    reject(isinstance(lifecycle, dict) and lifecycle.get("initSucceeded") is True and lifecycle.get("closeSucceeded") is True, "candidate Init/Close lifecycle")
    expected_attempted = wave_count > 0
    reject(lifecycle.get("getWaveAttempted") is expected_attempted, "candidate GetWave lifecycle")
    if wave_count:
        reject(result.get("mode") == "init-get-wave-sequence" and lifecycle.get("getWaveCallCount") == wave_count, "candidate sequence lifecycle")
        waves = result.get("getWaves")
        reject(isinstance(waves, list) and len(waves) == wave_count and "getWave" not in result, "candidate sequence outputs")
    else:
        reject(result.get("mode") == "init" and "getWaves" not in result and "getWave" not in result, "candidate init-only outputs")
        waves = []
    candidate_model = result.get("model")
    reject(isinstance(candidate_model, dict) and candidate_model == model, "candidate model identity")
    verify_f64_descriptor(result.get("init", {}).get("impulseResponse"), output)
    for wave in waves:
        reject(isinstance(wave, dict), "candidate wave output")
        verify_f64_descriptor(wave.get("waveform"), output)
        verify_f64_descriptor(wave.get("clockTimes"), output)
    return waves


def compare_case(*, work: Path, executable: Path, model: dict[str, Any], pyami_path: Path, reference_python: Path, name: str, waves: tuple[tuple[float, ...], ...], timeout_seconds: float) -> dict[str, Any]:
    request_path, request_bytes, inputs = request_for_case(work, model, name, waves)
    call = {"parametersUtf8": PARAMETERS, "initValues": list(VALUES), "getWaveValues": [list(values) for values in waves], "sampleIntervalSeconds": SAMPLE_INTERVAL, "bitTimeSeconds": BIT_TIME, "clockCapacity": CLOCK_CAPACITY}
    call_path = work / f"{name}-reference-call.json"
    call_path.write_text(json.dumps(call, ensure_ascii=True, sort_keys=True), encoding="utf-8")
    helper = work / "reference-helper.py"
    helper.write_text(REFERENCE_HELPER, encoding="utf-8")
    reference_path = work / f"{name}-reference.json"
    reference_call = subprocess.run([str(reference_python), str(helper), str(work), str(work / "example_rx.dll"), str(call_path), str(reference_path)], cwd=work, env=reference_environment(pyami_path, work), capture_output=True, text=True, timeout=timeout_seconds)
    if reference_call.returncode != 0 or not reference_path.is_file():
        detail = reference_call.stderr.strip() or reference_call.stdout.strip() or "no reference report"
        raise ValueError(f"{name} retained PyAMI invocation: {detail}")
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    reject(reference.get("initStatus") == 1 and reference.get("closeStatus") == 1 and all(wave.get("status") == 1 for wave in reference.get("waves", [])), f"{name} reference lifecycle")
    output = work / f"{name}-candidate-output"
    candidate_call = subprocess.run([str(executable), "ami-host-candidate", "--request", str(request_path), "--output-dir", str(output)], cwd=work, env=safe_environment(), capture_output=True, text=True, timeout=timeout_seconds)
    if candidate_call.returncode != 0 or not (output / "result.json").is_file():
        detail = candidate_call.stderr.strip() or candidate_call.stdout.strip() or "no candidate result"
        raise ValueError(f"{name} candidate invocation: {detail}")
    result = json.loads((output / "result.json").read_text(encoding="utf-8"))
    candidate_waves = verify_candidate_case(result, output, sha256_bytes(request_bytes), model, len(waves))
    outputs = {
        "initImpulse": compare_sidecar(reference["initImpulse"], result["init"]["impulseResponse"], work, output),
        "initParametersOut": text_observation(reference.get("initParametersOut")),
        "initMessage": text_observation(reference.get("initMessage")),
        "waves": [],
    }
    reject(reference.get("initParametersOut") == result["init"].get("parametersOut") and reference.get("initMessage") == result["init"].get("message"), f"{name} init text")
    for index, (left, right) in enumerate(zip(reference["waves"], candidate_waves, strict=True)):
        reject(left.get("parametersOut") == right.get("parametersOut"), f"{name} GetWave[{index}] text")
        outputs["waves"].append({"waveform": compare_sidecar(left["waveform"], right["waveform"], work, output), "clockTimes": compare_sidecar(left["clockTimes"], right["clockTimes"], work, output), "parametersOut": observe_text(left.get("parametersOut"))})
    return {"case": name, "getWaveCallCount": len(waves), "input": inputs, "equivalentOutputs": outputs, "candidateLifecycle": result["lifecycle"]}


def compare(*, bundle_dir: Path, pybert_repo: Path, reference_python: Path, report_path: Path, timeout_seconds: float) -> dict[str, Any]:
    reject(sys.platform == "win32", "Windows x64 stateful host comparison is unsupported on this platform")
    reject(timeout_seconds > 0 and math.isfinite(timeout_seconds), "timeout")
    bundle_dir, pybert_repo, reference_python = bundle_dir.resolve(), pybert_repo.resolve(), reference_python.resolve()
    reject(reference_python.is_file(), "reference Python missing")
    report_path = external(report_path, ROOT, bundle_dir, pybert_repo)
    reject(not report_path.exists(), "report path already exists")
    fixture_document = json.loads(FIXTURE_DOCUMENT.read_text(encoding="utf-8"))
    fixture = verify_fixture(fixture_document, pybert_repo)
    bundle = verify_bundle(bundle_dir, ROOT)
    bundle["manifest"] = json.loads((bundle_dir / "candidate-manifest.json").read_text(encoding="utf-8"))
    require_candidate_capability(bundle)
    executable = bundle_dir / bundle["manifest"]["executable"]["bundlePath"]
    work = Path(tempfile.mkdtemp(prefix="m5b-ami-stateful-host-"))
    try:
        model = write_fixture(pybert_repo, fixture_document, work)
        pyami = materialize_pyami_source(pybert_repo, work)
        cases = [compare_case(work=work, executable=executable, model=model, pyami_path=pyami["pythonPath"], reference_python=reference_python, name=name, waves=waves, timeout_seconds=timeout_seconds) for name, waves in CASES]
        report = {"schema": REPORT_SCHEMA, "accepted": True, "scope": "example_rx exact-fixture stateful raw ABI lifecycle host-output equivalence only", "platform": "windows-x86_64", "fixture": {"sourceCommit": REFERENCE_COMMIT, "assets": fixture["assets"]}, "reference": {"kind": "retained-pyami-raw-abi", "pyamiSource": {"tree": pyami["tree"], "entryCount": pyami["entryCount"], "entryDigestSha256": pyami["entryDigestSha256"]}, "strictStatus": {"init": 1, "getWave": 1, "close": 1}}, "candidate": {"bundleManifestSha256": bundle["manifestSha256"], "executableSha256": bundle["candidateSha256"], "productionResolvable": False, "lifecycleRequestSchema": REQUEST_SCHEMA}, "cases": cases, "nonClaims": ["not general AMI parity", "not AMI Link BER or eye parity", "not a Python high-level pipeline comparison", "not candidate promotion or vendor redistribution", "not Linux or macOS certification"]}
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
        print(f"stateful AMI host-output equivalence rejected: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"accepted": report["accepted"], "reportSchema": report["schema"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
