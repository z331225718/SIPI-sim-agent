"""Replay an authorized external RFM receive waveform into the product receiver.

This is an oracle-only gate.  It materializes no vendor or PyBERT bytes in the
product tree, never invokes the SIPI CLI, and does not compare against a
retained receiver.  Its sole positive conclusion is a hash-verified handoff
from an external receive-voltage waveform to the product receiver boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import yaml

from verify_channel_rfm_receiver_reference_bits_preflight import RFM, SOURCE, verify as verify_bits


ROOT = Path(__file__).resolve().parents[1]
PROFILE = "channel-rfm-block-2-current-drive-v1"
ENGINE_SHA256 = "111ff6e1a1a8f7f39782a355722c56f4d8e7392bff6d389445ba87dee73928dc"
WAVEFORM_BYTES = 1024 * 8
BITS_SHA256 = "aebf405592dd2d2a2e5b4a256e4a7167b6189b5272cd5cbced17a8ba139c2616"
RUSTUP = Path.home() / ".cargo" / "bin" / "rustup.exe"
RUST_TOOLCHAIN = "1.97.0-x86_64-pc-windows-msvc"
RUNNER_TARGET = "receiver_observer_runner"
POLICY = ROOT / "docs/baselines/channel-rfm-receiver-handoff-replay.v1.yaml"

# This program is intentionally an external observer.  It only uses the
# existing current-domain RFM boundary to produce the external voltage sample
# sidecar.  It does not import a retained receiver or infer the bit sequence.
OBSERVER_PROGRAM = r'''
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

source_root, executable, rfm, waveform_path, bits_path = map(Path, sys.argv[1:])
sys.path.insert(0, str(source_root))
from pybert.engine.agent_spice_channel import (
    AgentSpiceChannelRunner,
    AgentSpiceCurrentDrive,
    AgentSpiceRfmRequest,
    current_driven_voltage_response,
)

samples, dt, nspui = 1024, 1.0e-12, 8
currents = np.where(
    (np.arange(samples) // nspui) % 2 == 0, 0.05, -0.05
).astype(np.float64)[None, :]
response = AgentSpiceChannelRunner().run(AgentSpiceRfmRequest(
    executable=executable.resolve(), rfm_path=rfm.resolve(), fft_size=samples,
    dt_seconds=dt, input_ports=(1,), output_ports=(2,), timeout_seconds=60.0,
))
voltage = current_driven_voltage_response(
    response,
    AgentSpiceCurrentDrive(input_currents_a=currents, current_to_voltage_sign=-1),
)
waveform = np.ascontiguousarray(voltage.voltage_waveforms_v[0], dtype="<f8")
if waveform.shape != (samples,) or not np.isfinite(waveform).all():
    raise ValueError("external receive waveform is not finite f64[1024]")
bits = bytes(1 if index % 2 == 0 else 0 for index in range(128))
Path(waveform_path).write_bytes(waveform.tobytes())
Path(bits_path).write_bytes(bits)
metadata = response.metadata
result = {
    "schema": "sipi.channel.rfm-observer-sidecars.v1",
    "response": {
        "schema": metadata.get("schema"),
        "fft_size": metadata.get("fftSize"),
        "frequency_bins": metadata.get("frequencyBins"),
        "sample_interval_seconds": metadata.get("dtS"),
        "input_ports": metadata.get("inputPorts"),
        "output_ports": metadata.get("outputPorts"),
        "producer_executable_sha256": metadata.get("producer", {}).get("executableSha256"),
        "producer_rfm_sha256": metadata.get("producer", {}).get("rfmSha256"),
    },
    "current_sha256": hashlib.sha256(np.ascontiguousarray(currents, dtype="<f8").tobytes()).hexdigest(),
    "waveform_sha256": hashlib.sha256(waveform.tobytes()).hexdigest(),
    "reference_bits_sha256": hashlib.sha256(bits).hexdigest(),
}
print(json.dumps(result, sort_keys=True, separators=(",", ":")))
'''


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(directory: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(directory), *args], text=True, stderr=subprocess.PIPE
    ).strip()


def _show(directory: Path, commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(directory), "show", f"{commit}:{path}"])


def _require_new_external_path(path: Path, label: str) -> Path:
    resolved = path.resolve()
    if resolved.exists():
        raise ValueError(f"{label} path must not already exist")
    if resolved.is_relative_to(ROOT):
        raise ValueError(f"{label} must be outside the SIPI worktree")
    return resolved


def _read_engine_build_info(executable: Path) -> dict:
    if not executable.is_file() or _sha256_file(executable) != ENGINE_SHA256:
        raise ValueError("engine executable does not match the locked SHA-256")
    payload = json.loads(
        subprocess.check_output([str(executable), "build-info", "--json"], text=True)
    )
    required = {"schema", "crateName", "profile", "target"}
    if not isinstance(payload, dict) or not required <= set(payload):
        raise ValueError("engine build-info is incomplete")
    if (
        payload["schema"] != "agent-spice.build-info.v1"
        or payload["crateName"] != "agent-spice-sim"
        or payload["profile"] != "release"
        or payload["target"] != "x86_64-pc-windows-msvc"
    ):
        raise ValueError("engine build-info does not identify the locked Windows release CLI")
    return payload


def _load_policy(path: Path = POLICY) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    expected_keys = {
        "schema", "status", "profile_id", "authorization_ref", "reference_bits_attestation_ref",
        "observer", "rfm", "engine", "handoff", "product_runner", "required_replays", "non_claims",
    }
    if not isinstance(document, dict) or set(document) != expected_keys:
        raise ValueError("handoff replay policy is incomplete")
    expected_observer = {
        "source_commit": SOURCE["commit"], "source_path": SOURCE["path"],
        "source_blob": SOURCE["git_blob"], "source_sha256": SOURCE["content_sha256"],
    }
    expected_rfm = {
        "commit": RFM["commit"], "path": RFM["path"], "blob": RFM["git_blob"],
        "sha256": RFM["content_sha256"],
    }
    expected_handoff = {
        "waveform_encoding": "f64le", "waveform_units": "V", "waveform_count": 1024,
        "start_seconds": 0.0, "sample_interval_seconds": 1.0e-12,
        "reference_bit_encoding": "one-byte-per-bit-0-or-1", "reference_bit_count": 128,
        "input_port": 1, "output_port": 2, "current_to_voltage_sign": -1,
        "transformations": "forbidden",
    }
    if (
        document["schema"] != "sipi.channel.rfm-receiver-handoff-replay-policy.v1"
        or document["status"] != "external_replay_pending_execution"
        or document["profile_id"] != PROFILE
        or document["observer"] != expected_observer
        or document["rfm"] != expected_rfm
        or document["engine"] != {"sha256": ENGINE_SHA256, "platform": "windows-x86_64"}
        or document["handoff"] != expected_handoff
        or document["product_runner"] != {"target": RUNNER_TARGET, "invocation": "ignored_test_only", "stable_cli_or_ffi": "forbidden"}
        or document["required_replays"] != 2
        or not isinstance(document["non_claims"], list)
        or not all(isinstance(value, str) and value for value in document["non_claims"])
    ):
        raise ValueError("handoff replay policy identity drifted")
    return document


def _verify_product_tree() -> dict:
    if _run(ROOT, "diff", "--quiet", "--", "Cargo.lock", "crates/sipi-link", "crates/sipi-contracts"):
        raise AssertionError("git diff --quiet unexpectedly emitted output")
    # check_output raises on any nonzero status, preserving the fail-closed rule
    return {
        "commit": _run(ROOT, "rev-parse", "HEAD"),
        "tree": _run(ROOT, "rev-parse", "HEAD^{tree}"),
        "cargo_lock_sha256": _sha256_file(ROOT / "Cargo.lock"),
        "runner_source_sha256": _sha256_file(ROOT / "crates/sipi-link/tests/receiver_observer_runner.rs"),
    }


def _validate_observer_sidecars(
    *, directory: Path, waveform_path: Path, bits_path: Path, metadata: object
) -> dict:
    expected_keys = {"schema", "response", "current_sha256", "waveform_sha256", "reference_bits_sha256"}
    if not isinstance(metadata, dict) or set(metadata) != expected_keys:
        raise ValueError("external observer emitted an unsafe manifest")
    expected_response = {
        "schema": "agent-spice.rfm-response.v1",
        "fft_size": 1024,
        "frequency_bins": 513,
        "sample_interval_seconds": 1.0e-12,
        "input_ports": [1],
        "output_ports": [2],
        "producer_executable_sha256": ENGINE_SHA256,
        "producer_rfm_sha256": RFM["content_sha256"],
    }
    if metadata["schema"] != "sipi.channel.rfm-observer-sidecars.v1" or metadata["response"] != expected_response:
        raise ValueError("external RFM response metadata did not match the frozen request")
    if (
        not waveform_path.is_relative_to(directory)
        or not bits_path.is_relative_to(directory)
        or not waveform_path.is_file()
        or waveform_path.stat().st_size != WAVEFORM_BYTES
        or _sha256_file(waveform_path) != metadata["waveform_sha256"]
        or not bits_path.is_file()
        or bits_path.stat().st_size != 128
        or _sha256_file(bits_path) != metadata["reference_bits_sha256"]
        or metadata["reference_bits_sha256"] != BITS_SHA256
    ):
        raise ValueError("external observer sidecar identity mismatch")
    return metadata


def _run_observer(
    *, pybert_repo: Path, python: Path, executable: Path, directory: Path
) -> tuple[Path, Path, dict]:
    rfm_path = directory / "block_2.rfm"
    waveform_path = directory / "receiver-waveform.f64le"
    bits_path = directory / "reference-bits.bin"
    rfm = _show(pybert_repo, RFM["commit"], RFM["path"])
    if hashlib.sha256(rfm).hexdigest() != RFM["content_sha256"]:
        raise ValueError("materialized RFM object drifted")
    rfm_path.write_bytes(rfm)
    completed = subprocess.run(
        [
            str(python), "-I", "-c", OBSERVER_PROGRAM, str(pybert_repo / "src"),
            str(executable), str(rfm_path), str(waveform_path), str(bits_path),
        ],
        cwd=directory,
        text=True,
        capture_output=True,
        check=False,
        timeout=90.0,
    )
    if completed.returncode != 0:
        raise ValueError("external RFM observer process failed")
    try:
        metadata = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("external observer did not emit exactly one JSON record") from error
    return waveform_path, bits_path, _validate_observer_sidecars(
        directory=directory, waveform_path=waveform_path, bits_path=bits_path, metadata=metadata
    )


def _build_runner(target_root: Path) -> Path:
    if not RUSTUP.is_file():
        raise ValueError("pinned rustup executable is unavailable")
    command = [
        str(RUSTUP), "run", RUST_TOOLCHAIN, "cargo", "test", "--locked", "-p", "sipi-link",
        "--test", RUNNER_TARGET, "--no-run", "--message-format=json",
    ]
    environment = {**os.environ, "CARGO_TARGET_DIR": str(target_root)}
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, env=environment, check=False)
    if completed.returncode != 0:
        raise ValueError("test-only product receiver runner did not build")
    executable: Path | None = None
    for line in completed.stdout.splitlines():
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        target = message.get("target")
        if isinstance(target, dict) and target.get("name") == RUNNER_TARGET and message.get("executable"):
            executable = Path(message["executable"])
    if executable is None or not executable.is_file() or not executable.resolve().is_relative_to(target_root.resolve()):
        raise ValueError("Cargo did not produce a contained receiver runner")
    return executable


def _run_product_runner(*, executable: Path, root: Path, waveform: Path, bits: Path) -> tuple[Path, dict]:
    result = root / "product-receiver-result.json"
    environment = {
        **os.environ,
        "SIPI_RECEIVER_HANDOFF_ROOT": str(root),
        "SIPI_RECEIVER_HANDOFF_WAVEFORM": str(waveform),
        "SIPI_RECEIVER_HANDOFF_BITS": str(bits),
        "SIPI_RECEIVER_HANDOFF_OUTPUT": str(result),
    }
    completed = subprocess.run(
        [str(executable), "--ignored", "--exact", "validate_receiver_input", "--nocapture"],
        cwd=root,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
        timeout=60.0,
    )
    if completed.returncode != 0 or not result.is_file():
        raise ValueError("test-only product receiver runner rejected the handoff")
    try:
        payload = json.loads(result.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("product runner result is not valid JSON") from error
    expected = {"schema", "sampleCount", "sampleIntervalSeconds", "samplesPerUi", "referenceBitCount"}
    if (
        not isinstance(payload, dict)
        or set(payload) != expected
        or payload["schema"] != "sipi.receiver-input-observer-runner.v1"
        or payload["sampleCount"] != 1024
        or payload["sampleIntervalSeconds"] != 1.0e-12
        or payload["samplesPerUi"] != 8
        or payload["referenceBitCount"] != 128
    ):
        raise ValueError("product runner result violates the receiver boundary")
    return result, payload


def replay(*, pybert_repo: Path, python: Path, executable: Path, report: Path) -> dict:
    if os.name != "nt":
        raise ValueError("RFM receiver handoff replay is Windows-only")
    report = _require_new_external_path(report, "report")
    if not python.is_file():
        raise ValueError("observer Python executable is unavailable")
    _load_policy()
    bits_attestation = verify_bits(pybert_repo)
    product = _verify_product_tree()
    engine_info = _read_engine_build_info(executable)
    with tempfile.TemporaryDirectory(prefix="sipi-rfm-receiver-handoff-") as temporary:
        root = Path(temporary)
        first_root, second_root = root / "first", root / "second"
        first_root.mkdir()
        second_root.mkdir()
        first_waveform, first_bits, first_manifest = _run_observer(
            pybert_repo=pybert_repo, python=python, executable=executable, directory=first_root
        )
        second_waveform, second_bits, second_manifest = _run_observer(
            pybert_repo=pybert_repo, python=python, executable=executable, directory=second_root
        )
        if first_manifest["waveform_sha256"] != second_manifest["waveform_sha256"] or first_manifest["reference_bits_sha256"] != second_manifest["reference_bits_sha256"]:
            raise ValueError("fresh external RFM replay was not deterministic")
        runner = _build_runner(root / "cargo-target")
        product_result, product_output = _run_product_runner(
            executable=runner, root=first_root, waveform=first_waveform, bits=first_bits
        )
        product.update({"runner_binary_sha256": _sha256_file(runner), "runner_result_sha256": _sha256_file(product_result)})
    result = {
        "schema": "sipi.channel.rfm-receiver-handoff-replay.v1",
        "profile_id": PROFILE,
        "status": "handoff_accepted_pending_receiver_execution_and_charter_equivalence",
        "source": {key: SOURCE[key] for key in ("commit", "tree", "path", "git_blob", "content_sha256")},
        "rfm": RFM,
        "engine": {"sha256": ENGINE_SHA256, "build_info": engine_info},
        "external_handoff": {
            "units": "V",
            "start_seconds": 0.0,
            "sample_interval_seconds": 1.0e-12,
            "sample_count": 1024,
            "current_to_voltage_sign": -1,
            "input_port": 1,
            "output_port": 2,
            "current_sha256": first_manifest["current_sha256"],
            "waveform_sha256": first_manifest["waveform_sha256"],
            "fresh_replay_waveform_sha256": second_manifest["waveform_sha256"],
            "reference_bits_sha256": first_manifest["reference_bits_sha256"],
            "fresh_replay_reference_bits_sha256": second_manifest["reference_bits_sha256"],
        },
        "product_runner": product,
        "product_input_boundary": {
            "schema": product_output["schema"],
            "sample_count": product_output["sampleCount"],
            "sample_interval_seconds": product_output["sampleIntervalSeconds"],
            "samples_per_ui": product_output["samplesPerUi"],
            "reference_bit_count": product_output["referenceBitCount"],
        },
        "non_claims": [
            "no retained receiver comparison",
            "no fixed-receiver execution or charter-scoped receiver equivalence conclusion",
            "no general RFM, Link, DFE, CDR, or BER parity conclusion",
            "no product CLI, Python, external engine, or fixture route",
        ],
    }
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pybert-repo", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = replay(
            pybert_repo=args.pybert_repo.resolve(),
            python=args.python.resolve(),
            executable=args.engine.resolve(),
            report=args.report,
        )
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}))
        return 2
    print(json.dumps({"status": result["status"], "waveform_sha256": result["external_handoff"]["waveform_sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
