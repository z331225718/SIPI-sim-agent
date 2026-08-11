"""External-only agreement gate for the delegated receiver phase policy."""

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

import evaluate_fixed_receiver_delegated_policy as evaluator
import replay_channel_rfm_receiver_handoff as handoff


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs/baselines/channel-rfm-receiver-delegated-policy-compare.v1.yaml"
AMENDMENT = ROOT / "docs/baselines/channel-rfm-receiver-delegated-phase-amendment.v1.yaml"
PROFILE = handoff.PROFILE
ABSOLUTE_TOLERANCE_VOLTS = 1.0e-9
RELATIVE_TOLERANCE = 1.0e-6
RESULT_SCHEMA = "sipi.receiver-delegated-policy-observer-runner.v1"


def _sha256_file(path: Path) -> str:
    return handoff._sha256_file(path)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _load_policy() -> dict:
    document = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    expected = {
        "schema", "status", "profile_id", "handoff_policy_ref", "amendment_ref", "evaluator",
        "product_runner", "required_replays", "continuous_tolerance", "non_claims",
    }
    if (
        not isinstance(document, dict)
        or set(document) != expected
        or document["schema"] != "sipi.channel.rfm-receiver-delegated-policy-compare-policy.v1"
        or document["status"] != "external_compare_pending_execution"
        or document["profile_id"] != PROFILE
        or document["handoff_policy_ref"] != "docs/baselines/channel-rfm-receiver-handoff-replay.v1.yaml"
        or document["amendment_ref"] != "docs/baselines/channel-rfm-receiver-delegated-phase-amendment.v1.yaml"
        or document["evaluator"] != {"path": "tools/evaluate_fixed_receiver_delegated_policy.py", "schema": evaluator.SCHEMA}
        or document["product_runner"] != {"target": handoff.RUNNER_TARGET, "invocation": "ignored_test_only", "test": "replay_receiver_delegated_policy_input", "stable_cli_or_ffi": "forbidden"}
        or document["required_replays"] != 2
        or document["continuous_tolerance"] != {"absolute_volts": ABSOLUTE_TOLERANCE_VOLTS, "relative": RELATIVE_TOLERANCE}
        or not isinstance(document["non_claims"], list)
        or not all(isinstance(value, str) and value for value in document["non_claims"])
    ):
        raise ValueError("delegated receiver compare policy identity drifted")
    handoff._load_policy(ROOT / document["handoff_policy_ref"])
    if not AMENDMENT.is_file():
        raise ValueError("delegated phase amendment is unavailable")
    return document


def _read_result(path: Path, expected_schema: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("receiver result sidecar is invalid") from error
    if not isinstance(payload, dict) or payload.get("schema") != expected_schema:
        raise ValueError("receiver result schema mismatched")
    if payload.get("status") == "rejected":
        if set(payload) != {"schema", "status", "reason"} or not isinstance(payload["reason"], str):
            raise ValueError("receiver rejection sidecar is malformed")
        return payload
    expected = {
        "schema", "status", "phase", "phaseSelection", "cdrLockState", "centerVolts",
        "amplitudeVolts", "frozenTaps", "decisions", "errorCount", "berNumerator", "berDenominator",
    }
    if set(payload) != expected or payload.get("status") != "accepted":
        raise ValueError("receiver acceptance sidecar is malformed")
    if (
        not isinstance(payload["phase"], int)
        or not 0 <= payload["phase"] < 8
        or (payload["phaseSelection"], payload["cdrLockState"])
        not in {("unique_locked", "locked"), ("delegated_ambiguous_tie_break", "policy_selected_not_locked")}
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


def _run_evaluator(python: Path, root: Path, waveform: Path, bits: Path) -> tuple[Path, dict]:
    result = root / "delegated-evaluator-result.json"
    completed = subprocess.run(
        [str(python), "-I", str(ROOT / "tools/evaluate_fixed_receiver_delegated_policy.py"), "--waveform", str(waveform), "--bits", str(bits), "--result", str(result)],
        cwd=root, text=True, capture_output=True, check=False, timeout=60.0,
    )
    payload = _read_result(result, evaluator.SCHEMA)
    if completed.returncode not in (0, 2) or (completed.returncode == 0) != (payload["status"] == "accepted"):
        raise ValueError("delegated evaluator process status drifted")
    return result, payload


def _run_product(executable: Path, root: Path, waveform: Path, bits: Path) -> tuple[Path, dict]:
    result = root / "delegated-product-result.json"
    environment = {**os.environ, "SIPI_RECEIVER_HANDOFF_ROOT": str(root), "SIPI_RECEIVER_HANDOFF_WAVEFORM": str(waveform), "SIPI_RECEIVER_HANDOFF_BITS": str(bits), "SIPI_RECEIVER_HANDOFF_OUTPUT": str(result)}
    completed = subprocess.run(
        [str(executable), "--ignored", "--exact", "replay_receiver_delegated_policy_input", "--nocapture"],
        cwd=root, text=True, capture_output=True, env=environment, check=False, timeout=60.0,
    )
    if completed.returncode != 0:
        raise ValueError("delegated product receiver runner failed")
    return result, _read_result(result, RESULT_SCHEMA)


def _continuous(evaluator_result: dict, product_result: dict) -> dict:
    fields = [("center_volts", evaluator_result["centerVolts"], product_result["centerVolts"]), ("amplitude_volts", evaluator_result["amplitudeVolts"], product_result["amplitudeVolts"])]
    fields.extend((f"tap_{index}", evaluator_result["frozenTaps"][index], product_result["frozenTaps"][index]) for index in range(5))
    result = []
    for label, expected, actual in fields:
        absolute = abs(actual - expected)
        scale = max(abs(expected), abs(actual))
        allowed = ABSOLUTE_TOLERANCE_VOLTS + RELATIVE_TOLERANCE * scale
        result.append({"field": label, "max_abs": absolute, "max_rel": absolute / scale if scale else 0.0, "allowed": allowed, "passed": absolute <= allowed})
    return {"passed": all(item["passed"] for item in result), "fields": result}


def compare_pair(evaluator_result: dict, product_result: dict) -> dict:
    if evaluator_result["status"] != "accepted" or product_result["status"] != "accepted":
        return {"status": "receiver_rejected", "evaluator": evaluator_result, "product": product_result}
    discrete = {key: evaluator_result[key] == product_result[key] for key in ("phase", "phaseSelection", "cdrLockState", "errorCount", "berNumerator", "berDenominator")}
    discrete["decisions_sha256"] = _sha256_text(evaluator_result["decisions"]) == _sha256_text(product_result["decisions"])
    continuous = _continuous(evaluator_result, product_result)
    return {"status": "accepted" if all(discrete.values()) and continuous["passed"] else "comparison_failed", "discrete": discrete, "decisions_sha256": _sha256_text(evaluator_result["decisions"]), "continuous": continuous}


def compare(*, pybert_repo: Path, python: Path, engine: Path, report: Path) -> dict:
    if os.name != "nt":
        raise ValueError("delegated receiver compare is Windows-only")
    report = handoff._require_new_external_path(report, "report")
    policy = _load_policy()
    if not python.is_file():
        raise ValueError("observer Python executable is unavailable")
    handoff.verify_bits(pybert_repo)
    product = handoff._verify_product_tree()
    engine_info = handoff._read_engine_build_info(engine)
    with tempfile.TemporaryDirectory(prefix="sipi-rfm-delegated-policy-") as temporary:
        root = Path(temporary)
        roots = [root / "first", root / "second"]
        for replay_root in roots:
            replay_root.mkdir()
        observed = [(*handoff._run_observer(pybert_repo=pybert_repo, python=python, executable=engine, directory=replay_root), replay_root) for replay_root in roots]
        manifests = [entry[2] for entry in observed]
        if any(item["waveform_sha256"] != manifests[0]["waveform_sha256"] or item["reference_bits_sha256"] != manifests[0]["reference_bits_sha256"] for item in manifests[1:]):
            raise ValueError("fresh external RFM replay was not deterministic")
        runner = handoff._build_runner(root / "cargo-target")
        product["runner_binary_sha256"] = _sha256_file(runner)
        replays = []
        for number, (waveform, bits, manifest, replay_root) in enumerate(observed, start=1):
            evaluator_path, evaluator_result = _run_evaluator(python, replay_root, waveform, bits)
            product_path, product_result = _run_product(runner, replay_root, waveform, bits)
            replays.append({"replay": number, "external_handoff": {key: manifest[key] for key in ("waveform_sha256", "reference_bits_sha256", "current_sha256")}, "evaluator_result_sha256": _sha256_file(evaluator_path), "product_result_sha256": _sha256_file(product_path), "comparison": compare_pair(evaluator_result, product_result)})
    status = "delegated_policy_semantic_agreement_observed" if all(item["comparison"]["status"] == "accepted" for item in replays) else "delegated_policy_agreement_failed"
    result = {"schema": "sipi.channel.rfm-receiver-delegated-policy-compare.v1", "profile_id": PROFILE, "status": status, "policy_sha256": _sha256_file(POLICY), "amendment_sha256": _sha256_file(AMENDMENT), "source": {key: handoff.SOURCE[key] for key in ("commit", "tree", "path", "git_blob", "content_sha256")}, "rfm": handoff.RFM, "engine": {"sha256": handoff.ENGINE_SHA256, "build_info": engine_info}, "product_runner": product, "evaluator": {"source_sha256": _sha256_file(ROOT / "tools/evaluate_fixed_receiver_delegated_policy.py"), "schema": evaluator.SCHEMA}, "replays": replays, "non_claims": policy["non_claims"]}
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
        result = compare(pybert_repo=args.pybert_repo.resolve(), python=args.python.resolve(), engine=args.engine.resolve(), report=args.report)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}))
        return 2
    print(json.dumps({"status": result["status"]}))
    return 0 if result["status"] == "delegated_policy_semantic_agreement_observed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
