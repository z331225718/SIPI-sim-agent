"""Compare the selected external matched-S21 kernel with the Rust primitive.

This observer-side gate materializes the pinned external Git object only in a
temporary directory. It parses the narrow Touchstone text solely to create a
product binary record, computes the standard DFT observer kernel separately,
and never exposes the source text or either kernel array in its report.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import platform
import struct
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path

from verify_channel_s2p_matched_acceptance import _load, verify_document


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.channel.required-profile-compare.v1"
INPUT_MAGIC = b"SIPICHS1"
OUTPUT_MAGIC = b"SIPICHK1"
PROFILE_ID = "channel-s2p-channel-16ghz-3db-v1"
ENDPOINT_IMAGINARY_TOLERANCE = 1.0e-12


class ComparatorError(RuntimeError):
    """A fail-closed external acceptance-gate error."""


@dataclass(frozen=True)
class Spectrum:
    reference_impedance_ohm: float
    frequency_step_hz: float
    samples: tuple[tuple[complex, complex, complex, complex], ...]


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _array_hash(values: list[float]) -> str:
    return _sha256_bytes(b"".join(struct.pack("<d", value) for value in values))


def _finite(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ComparatorError(f"{label} must be finite")
    return float(value)


def parse_two_port_touchstone_ri(payload: bytes) -> Spectrum:
    """Parse only the observer-side two-port Hz/S/RI/real-Z0 subset."""
    try:
        lines = payload.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise ComparatorError("external Touchstone text is not ASCII") from error
    header: list[str] | None = None
    rows: list[list[str]] = []
    for line in lines:
        content = line.split("!", 1)[0].strip()
        if not content:
            continue
        if content.startswith("#"):
            if header is not None:
                raise ComparatorError("multiple Touchstone option lines are unsupported")
            header = content[1:].split()
            continue
        rows.append(content.split())
    if header != ["Hz", "S", "RI", "R", "50.0"]:
        raise ComparatorError("Touchstone option line is outside the matched v1 subset")
    if len(rows) < 2 or any(len(row) != 9 for row in rows):
        raise ComparatorError("Touchstone two-port rows are malformed")
    parsed: list[tuple[float, tuple[complex, complex, complex, complex]]] = []
    for index, row in enumerate(rows):
        try:
            values = [_finite(float(token), f"Touchstone value[{index}]") for token in row]
        except ValueError as error:
            raise ComparatorError("Touchstone numeric token is invalid") from error
        # Touchstone two-port order is S11, S21, S12, S22. Product order is
        # row-major S11, S12, S21, S22, with no numerical transformation.
        parsed.append((values[0], (complex(values[1], values[2]), complex(values[5], values[6]), complex(values[3], values[4]), complex(values[7], values[8]))))
    if parsed[0][0] != 0.0:
        raise ComparatorError("matched v1 requires a DC Touchstone sample")
    step = parsed[1][0] - parsed[0][0]
    if not math.isfinite(step) or step <= 0.0:
        raise ComparatorError("Touchstone frequency grid is not strictly increasing")
    for index, (frequency, _) in enumerate(parsed):
        if abs(frequency - index * step) > 1.0e-9 * max(1.0, abs(frequency)):
            raise ComparatorError("Touchstone frequency grid is not uniform and indexed")
    return Spectrum(50.0, step, tuple(sample for _, sample in parsed))


def encode_product_spectrum(spectrum: Spectrum) -> bytes:
    result = bytearray(INPUT_MAGIC)
    result.extend(struct.pack("<Qdd", len(spectrum.samples), spectrum.reference_impedance_ohm, spectrum.frequency_step_hz))
    for sample in spectrum.samples:
        for value in sample:
            result.extend(struct.pack("<dd", value.real, value.imag))
    return bytes(result)


def observer_kernel(spectrum: Spectrum) -> tuple[float, list[float]]:
    count = len(spectrum.samples)
    length = 2 * (count - 1)
    values = [sample[2] for sample in spectrum.samples]
    if abs(values[0].imag) > ENDPOINT_IMAGINARY_TOLERANCE or abs(values[-1].imag) > ENDPOINT_IMAGINARY_TOLERANCE:
        raise ComparatorError("observer endpoint imaginary residue exceeds matched v1 policy")
    completed = values + [values[length - index].conjugate() for index in range(count, length)]
    kernel: list[float] = []
    for time_index in range(length):
        value = sum(
            frequency * complex(math.cos(2.0 * math.pi * index * time_index / length), math.sin(2.0 * math.pi * index * time_index / length))
            for index, frequency in enumerate(completed)
        ) / length
        if not math.isfinite(value.real) or not math.isfinite(value.imag):
            raise ComparatorError("observer kernel is non-finite")
        if abs(value.imag) > 1.0e-12 + 1.0e-10 * max(1.0, abs(value.real)):
            raise ComparatorError("observer inverse imaginary residue exceeds matched v1 policy")
        kernel.append(value.real)
    return 1.0 / (length * spectrum.frequency_step_hz), kernel


def parse_product_kernel(payload: bytes) -> tuple[float, list[float]]:
    if payload[:8] != OUTPUT_MAGIC or len(payload) < 24:
        raise ComparatorError("product kernel record magic or header is invalid")
    count, interval = struct.unpack("<Qd", payload[8:24])
    expected = 24 + count * 8
    if len(payload) != expected:
        raise ComparatorError("product kernel record length mismatch")
    values = list(struct.unpack(f"<{count}d", payload[24:]))
    if not math.isfinite(interval) or not all(math.isfinite(value) for value in values):
        raise ComparatorError("product kernel record is non-finite")
    return interval, values


def _compare(expected: list[float], actual: list[float], absolute: float, relative: float) -> dict[str, float | int | bool]:
    if len(expected) != len(actual):
        raise ComparatorError("kernel lengths differ")
    worst_index = 0
    max_abs = -1.0
    max_rel = 0.0
    passed = True
    for index, (left, right) in enumerate(zip(expected, actual, strict=True)):
        if not math.isfinite(left) or not math.isfinite(right):
            raise ComparatorError("kernel comparison received non-finite value")
        difference = abs(left - right)
        scale = max(abs(left), abs(right))
        if difference > absolute + relative * scale:
            passed = False
        if difference > max_abs:
            max_abs = difference
            worst_index = index
        if scale:
            max_rel = max(max_rel, difference / scale)
    return {"passed": passed, "max_absolute_error": max_abs, "max_relative_error": max_rel, "worst_index": worst_index}


def _scrubbed_environment(temp_root: Path) -> dict[str, str]:
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise ComparatorError("SystemRoot is required for the Windows acceptance gate")
    system32 = str(Path(system_root) / "System32")
    return {"ComSpec": os.environ.get("ComSpec", str(Path(system32) / "cmd.exe")), "LANG": "C", "PATH": system32, "SystemRoot": system_root, "TEMP": str(temp_root), "TMP": str(temp_root)}


def _git_bytes(source_root: Path, source: dict) -> bytes:
    completed = subprocess.run(["git", "-C", str(source_root), "cat-file", "blob", f"{source['commit']}:{source['path']}"], capture_output=True)
    if completed.returncode != 0:
        raise ComparatorError("external source Git object is unavailable")
    if _sha256_bytes(completed.stdout) != source["content_sha256"]:
        raise ComparatorError("external source Git bytes do not match the pinned hash")
    return completed.stdout


def _safe_archive_member(name: str) -> bool:
    candidate = Path(name)
    return bool(name) and not candidate.is_absolute() and ".." not in candidate.parts


def _materialize_product_runner(product_root: Path, product_commit: str, temp_root: Path) -> tuple[Path, dict[str, object]]:
    status = subprocess.run(["git", "-C", str(product_root), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True)
    if status.returncode != 0:
        raise ComparatorError("product source Git status is unavailable")
    archive = subprocess.run(["git", "-C", str(product_root), "archive", "--format=tar", product_commit], capture_output=True)
    if archive.returncode != 0:
        raise ComparatorError("product commit cannot be materialized")
    tree = subprocess.run(["git", "-C", str(product_root), "rev-parse", f"{product_commit}^{{tree}}"], check=True, capture_output=True, text=True).stdout.strip()
    source = temp_root / "product-source"
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as document:
        members = document.getmembers()
        if any(
            not (member.isfile() or member.isdir()) or not _safe_archive_member(member.name)
            for member in members
        ):
            raise ComparatorError("product Git archive has an unsafe member")
        document.extractall(source, members)
    cargo = os.environ.get("CARGO", "cargo")
    target = temp_root / "product-target"
    environment = dict(os.environ)
    environment.update({"CARGO_TARGET_DIR": str(target), "CARGO_INCREMENTAL": "0", "CARGO_NET_OFFLINE": "true"})
    completed = subprocess.run([cargo, "build", "--manifest-path", str(source / "Cargo.toml"), "-p", "sipi-channel", "--bin", "sipi-channel-kernel-runner", "--release", "--locked"], cwd=source, env=environment, capture_output=True, text=True, encoding="utf-8", errors="strict")
    runner = target / "release" / "sipi-channel-kernel-runner.exe"
    if completed.returncode != 0 or not runner.is_file():
        raise ComparatorError("product runner clean build failed")
    return runner, {"source_commit": product_commit, "source_tree": tree, "cargo_lock_sha256": _sha256_file(source / "Cargo.lock"), "runner_sha256": _sha256_file(runner), "runner_bytes": runner.stat().st_size, "cargo_version": subprocess.run([cargo, "--version"], check=True, capture_output=True, text=True).stdout.strip()}


def compare(contract_path: Path, source_root: Path, product_root: Path, product_commit: str) -> dict:
    contract = _load(contract_path)
    policy = verify_document(contract, source_root)
    if not policy["valid"] or not policy["acceptance_ready"]:
        raise ComparatorError("matched acceptance policy is invalid")
    if platform.system() != "Windows" or platform.machine().lower() not in {"amd64", "x86_64"}:
        raise ComparatorError("this acceptance gate supports Windows x86_64 only")
    if len(product_commit) != 40 or any(character not in "0123456789abcdef" for character in product_commit):
        raise ComparatorError("product commit must be a full lowercase SHA-1")
    source_bytes = _git_bytes(source_root, contract["source"])
    spectrum = parse_two_port_touchstone_ri(source_bytes)
    if len(spectrum.samples) != 201 or spectrum.frequency_step_hz != 100_000_000.0 or spectrum.reference_impedance_ohm != 50.0:
        raise ComparatorError("external spectrum does not match the frozen matched v1 structure")
    first_dt, first_kernel = observer_kernel(spectrum)
    second_dt, second_kernel = observer_kernel(spectrum)
    if first_dt != second_dt or _array_hash(first_kernel) != _array_hash(second_kernel):
        raise ComparatorError("oracle_nondeterministic")
    product_input = encode_product_spectrum(spectrum)
    with tempfile.TemporaryDirectory(prefix="sipi-channel-s2p-") as directory:
        temp_root = Path(directory)
        product_runner, runner_identity = _materialize_product_runner(product_root, product_commit, temp_root)
        input_path = temp_root / "spectrum.bin"
        output_path = temp_root / "kernel.bin"
        input_path.write_bytes(product_input)
        completed = subprocess.run([str(product_runner), str(input_path), str(output_path)], cwd=temp_root, env=_scrubbed_environment(temp_root), capture_output=True, text=True, encoding="utf-8", errors="strict")
        if completed.returncode != 0 or not output_path.is_file():
            raise ComparatorError("product runner failed to publish a kernel")
        product_dt, product_kernel = parse_product_kernel(output_path.read_bytes())
    expected_dt = contract["acceptance"]["dft"]["sample_interval_seconds"]
    if abs(first_dt - expected_dt) > 1.0e-18 + 1.0e-12 * abs(expected_dt) or abs(product_dt - expected_dt) > 1.0e-18 + 1.0e-12 * abs(expected_dt):
        raise ComparatorError("kernel sample interval mismatches the frozen policy")
    comparison = _compare(first_kernel, product_kernel, contract["acceptance"]["kernel_compare"]["absolute_tolerance_v_per_v"], contract["acceptance"]["kernel_compare"]["relative_tolerance"])
    return {
        "schema": SCHEMA,
        "profile_id": PROFILE_ID,
        "status": "passed" if comparison["passed"] else "rejected",
        "accepted": bool(comparison["passed"]),
        "policy_sha256": _sha256_file(contract_path),
        "source": {key: contract["source"][key] for key in ("canonical_origin", "commit", "tree", "path", "git_blob", "content_sha256", "redistribution")},
        "observer": {"implementation": "standard_dft_observer_v1", "fresh_run_kernel_sha256_f64le": _array_hash(first_kernel), "fft_length": len(first_kernel), "sample_interval_seconds": first_dt},
        "product_input": {"schema": "sipi.channel.matched-spectrum-binary.v1", "sha256": _sha256_bytes(product_input), "one_sided_sample_count": len(spectrum.samples), "frequency_step_hz": spectrum.frequency_step_hz, "reference_impedance_ohm": spectrum.reference_impedance_ohm},
        "product": {**runner_identity, "runner": "sipi-channel-kernel-runner", "kernel_sha256_f64le": _array_hash(product_kernel), "fft_length": len(product_kernel), "sample_interval_seconds": product_dt},
        "comparison": {**comparison, "absolute_tolerance": contract["acceptance"]["kernel_compare"]["absolute_tolerance_v_per_v"], "relative_tolerance": contract["acceptance"]["kernel_compare"]["relative_tolerance"]},
        "non_claims": ["This gate compares only the frozen matched-S21 discrete V/V kernel.", "It does not establish public Touchstone support, reflection handling, Link/eye/BER parity, or a default route.", "The report retains hashes and metrics only; it retains no external asset or kernel array."],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=ROOT / "docs" / "baselines" / "channel-s2p-matched-acceptance.v1.yaml")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--product-root", type=Path, required=True)
    parser.add_argument("--product-commit", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = compare(args.contract, args.source_root, args.product_root, args.product_commit)
    except (ComparatorError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        report = {"schema": SCHEMA, "profile_id": PROFILE_ID, "status": "rejected", "accepted": False, "blockers": [str(error)]}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, "status": report["status"], "accepted": report["accepted"]}, sort_keys=True))
    return 0 if report["accepted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
