"""Compare independent Python and Rust M1-06 conformance runner decisions."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from verify_m1_rule_ledger import verify as verify_rule_ledger


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "contracts" / "v1"
RUSTUP = Path.home() / ".cargo" / "bin" / "rustup.exe"
TOOLCHAIN = "1.97.0-x86_64-pc-windows-msvc"
PYTHON = Path.home() / "AppData" / "Roaming" / "uv" / "python" / "cpython-3.12.13-windows-x86_64-none" / "python.exe"
UV = "uv"


def _json_output(command: list[str]) -> dict:
    completed = subprocess.run(command, cwd=ROOT, text=True, encoding="utf-8", errors="replace", capture_output=True, check=True)
    return json.loads(next(line for line in reversed(completed.stdout.splitlines()) if line.startswith("{")))


def _tree_sha256() -> str:
    files = [path for root in (FIXTURES, ROOT / "schemas") for path in root.rglob("*") if path.is_file()]
    files.extend((ROOT / name) for name in ("toolchains.lock", "uv.lock", "tests/contract/rust-consumer/Cargo.lock", "tests/contract/external-probes/pybert-simulation/Cargo.lock"))
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(ROOT).as_posix()):
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _index_results(output: dict, language: str, expected_ids: set[str], failures: list[str]) -> dict[str, dict]:
    results = output.get("results", [])
    ids = [result.get("id") for result in results]
    if len(ids) != len(set(ids)):
        failures.append(f"{language}:duplicate_result_id")
    if set(ids) != expected_ids:
        failures.append(f"{language}:result_set_mismatch")
    return {result["id"]: result for result in results if isinstance(result.get("id"), str)}


def _payload_lineage(probes: dict[str, dict], producer: str, consumer: str, rejection: str) -> bool:
    results = [probes.get(probe, {}) for probe in (producer, consumer, rejection)]
    base_hashes = {result.get("base_payload_sha256") for result in results}
    accepted_hashes = {probes.get(probe, {}).get("consumed_payload_sha256") for probe in (producer, consumer)}
    rejected = probes.get(rejection, {})
    rejected_hash = rejected.get("consumed_payload_sha256")
    hashes = base_hashes | accepted_hashes | {rejected_hash}
    return (
        len(base_hashes) == 1
        and None not in base_hashes
        and len(accepted_hashes) == 1
        and None not in accepted_hashes
        and accepted_hashes == base_hashes
        and rejected.get("derived_from") == producer
        and rejected_hash is not None
        and rejected_hash not in base_hashes
        and all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None for value in hashes)
    )


def _pybert_results(cases: list[dict], failures: list[str]) -> tuple[dict[str, dict], dict]:
    output = _json_output([UV, "run", "--locked", "--python", str(PYTHON), "python", "-B", "tests/contract/run_pybert_simulation_probe.py"])
    if output.get("runner") != "pybert_core_rust":
        failures.append("pybert_core_rust:runner")
    authority = json.loads((ROOT / "schemas" / "authority.v1.yaml").read_text(encoding="utf-8"))
    snapshot = json.loads((ROOT / authority["source_snapshot_ref"]).read_text(encoding="utf-8"))
    repository = next(item for item in snapshot["repositories"] if item["id"] == "py-bert-agent")
    expected_snapshot = {"repository": repository["id"], "revision": repository["head"], "tree": repository["tree"]}
    if output.get("observed_source_snapshot") != expected_snapshot:
        failures.append("pybert_core_rust:source_snapshot")
    results = output.get("results", [])
    probes = {result.get("probe"): result for result in results}
    if len(probes) != len(results) or set(probes) != {case["probe"] for case in cases}:
        failures.append("pybert_core_rust:result_set_mismatch")
    lineage_groups = {
        ("wire_schema_id", "pybert.simulation.v1"): ("producer_serializes", "consumer_deserializes", "consumer_version_rejects"),
        ("embedded_type", "PyBERT RunEventV1"): ("run_event.producer_serializes", "run_event.consumer_deserializes", "run_event.consumer.schema_rejects"),
    }
    by_contract: dict[tuple[str, str], list[dict]] = {}
    for case in cases:
        identifier = case["external_contract"]
        by_contract.setdefault((identifier["kind"], identifier["value"]), []).append(case)
    for identifier, group_cases in by_contract.items():
        lineage = lineage_groups.get(identifier)
        if lineage is None or {case["probe"] for case in group_cases} != set(lineage) or not _payload_lineage(probes, *lineage):
            failures.append(f"pybert_core_rust:{identifier[1]}:payload_hash_lineage")
    return ({case["id"]: {**probes.get(case["probe"], {}), "id": case["id"]} for case in cases}, output.get("observed_source_snapshot", {}))


def _agent_com_results(cases: list[dict], failures: list[str]) -> tuple[dict[str, dict], dict]:
    output = _json_output([str(PYTHON), "-B", "tests/contract/run_agent_com_progress_probe.py"])
    if output.get("runner") != "agent_com_python":
        failures.append("agent_com_python:runner")
    if output.get("python_version") != "3.12.13":
        failures.append("agent_com_python:python_version")
    authority = json.loads((ROOT / "schemas" / "authority.v1.yaml").read_text(encoding="utf-8"))
    snapshot = json.loads((ROOT / authority["source_snapshot_ref"]).read_text(encoding="utf-8"))
    repository = next(item for item in snapshot["repositories"] if item["id"] == "agent-com")
    expected_snapshot = {"repository": repository["id"], "revision": repository["head"], "tree": repository["tree"]}
    if output.get("observed_source_snapshot") != expected_snapshot:
        failures.append("agent_com_python:source_snapshot")
    results = output.get("results", [])
    probes = {result.get("probe"): result for result in results}
    expected_probes = {case["probe"] for case in cases}
    expected_contract = {"kind": "embedded_type", "value": "agent-com ProgressEvent"}
    if any(case.get("external_contract") != expected_contract for case in cases):
        failures.append("agent_com_python:contract_binding")
    if len(probes) != len(results) or set(probes) != expected_probes:
        failures.append("agent_com_python:result_set_mismatch")
    lineage = ("progress_event.producer_jsonl", "progress_event.consumer_deserializes", "progress_event.consumer.schema_rejects")
    if expected_probes != set(lineage) or not _payload_lineage(probes, *lineage):
        failures.append("agent_com_python:progress_event:payload_hash_lineage")
    return ({case["id"]: {**probes.get(case["probe"], {}), "id": case["id"]} for case in cases}, output.get("observed_source_snapshot", {}))


def _agent_com_result_results(cases: list[dict], failures: list[str]) -> tuple[dict[str, dict], dict]:
    output = _json_output([str(PYTHON), "-B", "tests/contract/run_agent_com_result_probe.py"])
    if output.get("runner") != "agent_com_result_python":
        failures.append("agent_com_result_python:runner")
    if output.get("python_version") != "3.12.13":
        failures.append("agent_com_result_python:python_version")
    authority = json.loads((ROOT / "schemas" / "authority.v1.yaml").read_text(encoding="utf-8"))
    snapshot = json.loads((ROOT / authority["source_snapshot_ref"]).read_text(encoding="utf-8"))
    repository = next(item for item in snapshot["repositories"] if item["id"] == "agent-com")
    expected_snapshot = {"repository": repository["id"], "revision": repository["head"], "tree": repository["tree"]}
    if output.get("observed_source_snapshot") != expected_snapshot:
        failures.append("agent_com_result_python:source_snapshot")
    expected_contract = {"kind": "legacy_document", "value": "agent-com result v1"}
    if any(case.get("external_contract") != expected_contract for case in cases):
        failures.append("agent_com_result_python:contract_binding")
    results = output.get("results", [])
    probes = {result.get("probe"): result for result in results}
    lineage = ("result_v1.producer_json", "result_v1.consumer_validates", "result_v1.consumer.version_rejects")
    if len(probes) != len(results) or {case["probe"] for case in cases} != set(lineage) or set(probes) != set(lineage):
        failures.append("agent_com_result_python:result_set_mismatch")
    if not _payload_lineage(probes, *lineage):
        failures.append("agent_com_result_python:payload_hash_lineage")
    return ({case["id"]: {**probes.get(case["probe"], {}), "id": case["id"]} for case in cases}, output.get("observed_source_snapshot", {}))


def main() -> int:
    suite = json.loads((FIXTURES / "suite.json").read_text(encoding="utf-8"))
    if not PYTHON.is_file():
        raise RuntimeError(f"locked Python is unavailable: {PYTHON}")
    case_ids = [case["id"] for case in suite["cases"]]
    if len(case_ids) != len(set(case_ids)):
        raise RuntimeError("suite has duplicate case ids")
    local_cases = [case for case in suite["cases"] if case.get("runner", "local") == "local"]
    python = _json_output([UV, "run", "--locked", "--python", str(PYTHON), "python", "-B", "tests/contract/python_runner.py"])
    rust = _json_output([str(RUSTUP), "run", TOOLCHAIN, "cargo", "run", "--locked", "--quiet", "--manifest-path", "tests/contract/rust-consumer/Cargo.toml", "--", "fixtures/contracts/v1"])
    expected = {case["id"]: case for case in suite["cases"] if "deferred_to" not in case}
    failures = []
    language_results = {name: _index_results(output, name, {case["id"] for case in local_cases}, failures) for name, output in {"python": python, "rust": rust}.items()}
    pybert_cases = [case for case in suite["cases"] if case.get("runner") == "pybert_core_rust"]
    external_snapshots = {}
    if pybert_cases:
        pybert_results, external_snapshots["pybert_core_rust"] = _pybert_results(pybert_cases, failures)
        language_results["rust"].update(pybert_results)
    agent_com_cases = [case for case in suite["cases"] if case.get("runner") == "agent_com_python"]
    if agent_com_cases:
        agent_com_results, external_snapshots["agent_com_python"] = _agent_com_results(agent_com_cases, failures)
        language_results["python"].update(agent_com_results)
    agent_com_result_cases = [case for case in suite["cases"] if case.get("runner") == "agent_com_result_python"]
    if agent_com_result_cases:
        result_cases, external_snapshots["agent_com_result_python"] = _agent_com_result_results(agent_com_result_cases, failures)
        language_results["python"].update(result_cases)
    for case_id, case in expected.items():
        for language in case["required_languages"]:
            result = language_results[language].get(case_id, {})
            requires_preservation = bool(case["expect"].get("preserve"))
            if result.get("decision") != case["expect"]["decision"] or result.get("phase") != case["expect"]["phase"] or ("code" in case["expect"] and result.get("code") != case["expect"]["code"]) or (requires_preservation and result.get("preserved") is not True):
                failures.append(f"{language}:{case_id}")
    ledger = verify_rule_ledger(case_results=language_results)
    failures.extend(ledger["failures"])
    print(json.dumps({"suite": suite["suite"], "status": suite["status"], "fixture_tree_sha256": _tree_sha256(), "ledger": ledger, "external_snapshots": external_snapshots, "failures": failures, "python": language_results["python"], "rust": language_results["rust"]}, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
