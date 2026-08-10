"""Compare the independent receiver charter evaluator with the product receiver.

This external-only gate replays the authorized RFM observer twice, then drives
the same temporary sidecars through two independent receiver implementations.
It records hashes and metrics only; no external arrays or fixture bytes become
product inputs, test fixtures, or Git artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

import yaml

import evaluate_fixed_receiver_charter as evaluator
import replay_channel_rfm_receiver_handoff as handoff


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/baselines/channel-rfm-receiver-charter-compare.v1.yaml"
PROFILE = handoff.PROFILE
EVALUATOR = ROOT / "tools/evaluate_fixed_receiver_charter.py"
ABSOLUTE_TOLERANCE_VOLTS = 1.0e-9
RELATIVE_TOLERANCE = 1.0e-6


def _sha256_file(path: Path) -> str:
    return handoff._sha256_file(path)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _require_new_external_path(path: Path, label: str) -> Path:
    return handoff._require_new_external_path(path, label)


def _load_policy(path: Path = POLICY) -> dict:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    expected = {
        "schema", "status", "profile_id", "handoff_policy_ref", "charter", "evaluator",
        "product_runner", "required_replays", "continuous_tolerance", "non_claims",
    }
    expected_charter = {
        "primary_spec_ref": "docs/clean-room/specs/p3b-approved-fixed-receiver.v1.md",
        "erasure_amendment_ref": "docs/clean-room/specs/p3b-approved-fixed-receiver-erasure-amendment.v1.md",
        "evaluator_spec_ref": "docs/clean-room/specs/p3b-receiver-charter-evaluator.v1.md",
    }
    if (
        not isinstance(document, dict)
        or set(document) != expected
        or document["schema"] != "sipi.channel.rfm-receiver-charter-compare-policy.v1"
        or document["status"] != "external_compare_pending_execution"
        or document["profile_id"] != PROFILE
        or document["handoff_policy_ref"] != "docs/baselines/channel-rfm-receiver-handoff-replay.v1.yaml"
        or document["charter"] != expected_charter
        or document["evaluator"] != {
            "path": "tools/evaluate_fixed_receiver_charter.py",
            "schema": evaluator.SCHEMA,
        }
        or document["product_runner"] != {
            "target": handoff.RUNNER_TARGET,
            "invocation": "ignored_test_only",
            "stable_cli_or_ffi": "forbidden",
        }
        or document["required_replays"] != 2
        or document["continuous_tolerance"] != {
            "absolute_volts": ABSOLUTE_TOLERANCE_VOLTS,
            "relative": RELATIVE_TOLERANCE,
        }
        or not isinstance(document["non_claims"], list)
        or not all(isinstance(value, str) and value for value in document["non_claims"])
    ):
        raise ValueError("receiver charter compare policy identity drifted")
    handoff._load_policy(ROOT / document["handoff_policy_ref"])
    return document


def _read_result(path: Path, expected_schema: str) -> dict:
    if not path.is_file():
        raise ValueError("receiver result sidecar is missing")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("receiver result sidecar is invalid JSON") from error
    if not isinstance(payload, dict) or payload.get("schema") != expected_schema:
        raise ValueError("receiver result schema mismatched")
    if payload.get("status") == "rejected":
        if set(payload) != {"schema", "status", "reason"} or not isinstance(payload["reason"], str):
            raise ValueError("receiver rejection sidecar is malformed")
        return payload
    accepted_keys = {
        "schema", "status", "phase", "locked", "centerVolts", "amplitudeVolts", "frozenTaps",
        "decisions", "errorCount", "berNumerator", "berDenominator",
    }
    if set(payload) != accepted_keys or payload.get("status") != "accepted":
        raise ValueError("receiver acceptance sidecar is malformed")
    if (
        not isinstance(payload["phase"], int)
        or not 0 <= payload["phase"] < 8
        or payload["locked"] is not True
        or not isinstance(payload["decisions"], str)
        or len(payload["decisions"]) != 96
        or set(payload["decisions"]) - {"+", "-", "0"}
        or not isinstance(payload["errorCount"], int)
        or payload["errorCount"] < 0
        or payload["berNumerator"] != payload["errorCount"]
        or payload["berDenominator"] != 96
        or not isinstance(payload["frozenTaps"], list)
        or len(payload["frozenTaps"]) != 5
    ):
        raise ValueError("receiver acceptance result shape is invalid")
    continuous = [payload["centerVolts"], payload["amplitudeVolts"], *payload["frozenTaps"]]
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in continuous):
        raise ValueError("receiver acceptance result contains non-finite values")
    return payload


def _run_evaluator(*, python: Path, root: Path, waveform: Path, bits: Path) -> tuple[Path, dict]:
    result = root / "evaluator-result.json"
    completed = subprocess.run(
        [str(python), "-I", str(EVALUATOR), "--waveform", str(waveform), "--bits", str(bits), "--result", str(result)],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        timeout=60.0,
    )
    if completed.returncode not in (0, 2):
        raise ValueError("independent charter evaluator process failed")
    payload = _read_result(result, evaluator.SCHEMA)
    if (completed.returncode == 0) != (payload["status"] == "accepted"):
        raise ValueError("independent charter evaluator exit status drifted")
    return result, payload


def _run_product_receiver(*, executable: Path, root: Path, waveform: Path, bits: Path) -> tuple[Path, dict]:
    result = root / "product-receiver-result.json"
    environment = {
        **os.environ,
        "SIPI_RECEIVER_HANDOFF_ROOT": str(root),
        "SIPI_RECEIVER_HANDOFF_WAVEFORM": str(waveform),
        "SIPI_RECEIVER_HANDOFF_BITS": str(bits),
        "SIPI_RECEIVER_HANDOFF_OUTPUT": str(result),
    }
    completed = subprocess.run(
        [str(executable), "--ignored", "--exact", "replay_receiver_input", "--nocapture"],
        cwd=root,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
        timeout=60.0,
    )
    if completed.returncode != 0:
        raise ValueError("test-only product receiver runner failed")
    return result, _read_result(result, "sipi.receiver-observer-runner.v1")


def _continuous_metrics(evaluator_result: dict, product_result: dict) -> dict:
    pairs = [
        ("center_volts", evaluator_result["centerVolts"], product_result["centerVolts"]),
        ("amplitude_volts", evaluator_result["amplitudeVolts"], product_result["amplitudeVolts"]),
        *[
            (f"tap_{index}", evaluator_result["frozenTaps"][index], product_result["frozenTaps"][index])
            for index in range(5)
        ],
    ]
    metrics = []
    for label, expected, actual in pairs:
        absolute = abs(actual - expected)
        relative = absolute / max(abs(actual), abs(expected)) if max(abs(actual), abs(expected)) else 0.0
        allowed = ABSOLUTE_TOLERANCE_VOLTS + RELATIVE_TOLERANCE * max(abs(actual), abs(expected))
        metrics.append({"field": label, "max_abs": absolute, "max_rel": relative, "allowed": allowed, "passed": absolute <= allowed})
    return {"passed": all(metric["passed"] for metric in metrics), "fields": metrics}


def compare_result_pair(evaluator_result: dict, product_result: dict) -> dict:
    if evaluator_result["status"] != "accepted" or product_result["status"] != "accepted":
        return {
            "status": "receiver_rejected",
            "evaluator": {"status": evaluator_result["status"], "reason": evaluator_result.get("reason")},
            "product": {"status": product_result["status"], "reason": product_result.get("reason")},
        }
    discrete = {
        "phase": evaluator_result["phase"] == product_result["phase"],
        "locked": evaluator_result["locked"] == product_result["locked"],
        "decisions_sha256": _sha256_text(evaluator_result["decisions"]) == _sha256_text(product_result["decisions"]),
        "error_count": evaluator_result["errorCount"] == product_result["errorCount"],
        "ber_numerator": evaluator_result["berNumerator"] == product_result["berNumerator"],
        "ber_denominator": evaluator_result["berDenominator"] == product_result["berDenominator"],
    }
    continuous = _continuous_metrics(evaluator_result, product_result)
    return {
        "status": "accepted" if all(discrete.values()) and continuous["passed"] else "comparison_failed",
        "discrete": discrete,
        "evaluator_decisions_sha256": _sha256_text(evaluator_result["decisions"]),
        "product_decisions_sha256": _sha256_text(product_result["decisions"]),
        "continuous": continuous,
    }


def _result_summary(path: Path, payload: dict) -> dict:
    summary = {"result_sha256": _sha256_file(path), "status": payload["status"]}
    if payload["status"] == "rejected":
        summary["reason"] = payload["reason"]
    return summary


def compare(*, pybert_repo: Path, python: Path, executable: Path, report: Path) -> dict:
    if os.name != "nt":
        raise ValueError("RFM receiver charter compare is Windows-only")
    report = _require_new_external_path(report, "report")
    if not python.is_file():
        raise ValueError("observer Python executable is unavailable")
    policy = _load_policy()
    bits_attestation = handoff.verify_bits(pybert_repo)
    product = handoff._verify_product_tree()
    engine_info = handoff._read_engine_build_info(executable)
    with tempfile.TemporaryDirectory(prefix="sipi-rfm-receiver-compare-") as temporary:
        root = Path(temporary)
        replay_roots = [root / "first", root / "second"]
        for replay_root in replay_roots:
            replay_root.mkdir()
        observed = [
            (*handoff._run_observer(pybert_repo=pybert_repo, python=python, executable=executable, directory=replay_root), replay_root)
            for replay_root in replay_roots
        ]
        manifests = [entry[2] for entry in observed]
        if any(
            manifest["waveform_sha256"] != manifests[0]["waveform_sha256"]
            or manifest["reference_bits_sha256"] != manifests[0]["reference_bits_sha256"]
            for manifest in manifests[1:]
        ):
            raise ValueError("fresh external RFM replay was not deterministic")
        runner = handoff._build_runner(root / "cargo-target")
        product["runner_binary_sha256"] = _sha256_file(runner)
        replays = []
        for index, (waveform, bits, manifest, replay_root) in enumerate(observed, start=1):
            evaluator_path, evaluator_result = _run_evaluator(
                python=python, root=replay_root, waveform=waveform, bits=bits
            )
            product_path, product_result = _run_product_receiver(
                executable=runner, root=replay_root, waveform=waveform, bits=bits
            )
            replays.append({
                "replay": index,
                "external_handoff": {
                    "waveform_sha256": manifest["waveform_sha256"],
                    "reference_bits_sha256": manifest["reference_bits_sha256"],
                    "current_sha256": manifest["current_sha256"],
                },
                "evaluator": _result_summary(evaluator_path, evaluator_result),
                "product": _result_summary(product_path, product_result),
                "comparison": compare_result_pair(evaluator_result, product_result),
            })
    comparison_statuses = [entry["comparison"]["status"] for entry in replays]
    if all(status == "accepted" for status in comparison_statuses):
        status = "accepted_charter_equivalence_observed"
    elif any(status == "receiver_rejected" for status in comparison_statuses):
        status = "receiver_rejected"
    else:
        status = "comparison_failed"
    result = {
        "schema": "sipi.channel.rfm-receiver-charter-compare.v1",
        "profile_id": PROFILE,
        "status": status,
        "policy_sha256": _sha256_file(POLICY),
        "source": {key: handoff.SOURCE[key] for key in ("commit", "tree", "path", "git_blob", "content_sha256")},
        "rfm": handoff.RFM,
        "engine": {"sha256": handoff.ENGINE_SHA256, "build_info": engine_info},
        "reference_bits_attestation": bits_attestation,
        "product_runner": product,
        "evaluator": {"source_sha256": _sha256_file(EVALUATOR), "schema": evaluator.SCHEMA},
        "replays": replays,
        "non_claims": policy["non_claims"],
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
        result = compare(
            pybert_repo=args.pybert_repo.resolve(), python=args.python.resolve(),
            executable=args.engine.resolve(), report=args.report,
        )
    except (OSError, ValueError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}))
        return 2
    print(json.dumps({"status": result["status"]}))
    return 0 if result["status"] == "accepted_charter_equivalence_observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
