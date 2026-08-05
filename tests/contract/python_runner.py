"""Run materialized M1-06 conformance cases through sipi_contracts bindings."""
from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))

from jsonschema import Draft202012Validator
from sipi_contracts import (
    ContractViolation,
    parse_artifact_ref,
    parse_backend_execution_request,
    parse_backend_execution_result,
    parse_engine_capabilities,
    parse_run_event,
    parse_run_request,
    parse_run_result,
    parse_validation_report,
    validate_backend_execution_request,
    validate_backend_execution_result,
    validate_run_result,
)
from sipi_contracts.models import parse_capability_baseline
from sipi_contracts.validation.relations import validate_resource_slice
from sipi_contracts.validation.registry import validate_wire


FIXTURES = ROOT / "fixtures" / "contracts" / "v1"


class FixtureViolation(RuntimeError):
    """A test-suite integrity failure, not a public contract validation error."""


def _document(case_dir: Path, name: str) -> dict:
    path = (case_dir / name).resolve()
    try:
        path.relative_to(FIXTURES.resolve())
    except ValueError as error:
        raise FixtureViolation("fixture_path_escape") from error
    return json.loads(path.read_text(encoding="utf-8"))


def _content(case_dir: Path, name: str) -> bytes:
    path = (case_dir / name).resolve()
    try:
        path.relative_to(FIXTURES)
    except ValueError as error:
        raise FixtureViolation("fixture_path_escape") from error
    return path.read_bytes()


def artifact_integrity_error(case_dir: Path, documents: dict, artifact) -> str | None:
    content = _content(case_dir, documents["content"])
    if hashlib.sha256(content).hexdigest() != artifact["sha256"]:
        return "hash_mismatch"
    if len(content) != artifact["byte_length"]:
        return "length_mismatch"
    return None


def _pointer(value: object, pointer: str) -> object:
    current = value
    for token in pointer.removeprefix("/").split("/"):
        if not token:
            continue
        token = token.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]  # type: ignore[index]
    return current


def _run(case: dict) -> dict:
    if "python" not in case["required_languages"]:
        return {"id": case["id"], "decision": "not_required", "phase": "not_required"}
    if "deferred_to" in case:
        return {"id": case["id"], "decision": "deferred", "phase": case["deferred_to"]}
    case_dir = FIXTURES / case["path"]
    case_data = _document(case_dir, "case.json")
    documents = case_data["documents"]
    try:
        if case["entrypoint"] == "run_request":
            model = parse_run_request(_document(case_dir, documents["subject"]))
        elif case["entrypoint"] == "run_result":
            model = parse_run_result(_document(case_dir, documents["subject"]), producer=case["mode"] == "producer")
        elif case["entrypoint"] == "backend_request":
            model = parse_backend_execution_request(_document(case_dir, documents["subject"]))
        elif case["entrypoint"] == "backend_result":
            model = parse_backend_execution_result(_document(case_dir, documents["subject"]), producer=case["mode"] == "producer")
        elif case["entrypoint"] == "selection_chain":
            run_request_wire = _document(case_dir, documents["run_request"])
            backend_request_wire = _document(case_dir, documents["backend_request"])
            backend_result_wire = _document(case_dir, documents["backend_result"])
            run_result_wire = _document(case_dir, documents["run_result"])
            for schema_name, document in (
                ("run-request.v1.schema.json", run_request_wire),
                ("backend-execution-request.v1.schema.json", backend_request_wire),
                ("backend-execution-result.v1.schema.json", backend_result_wire),
                ("run-result.v1.schema.json", run_result_wire),
            ):
                validate_wire(schema_name, document)
            if run_request_wire["backend_selection"]["mode"] != "strict":
                raise FixtureViolation("fixture_configuration")
            run_request = parse_run_request(run_request_wire)
            backend_request = parse_backend_execution_request(backend_request_wire)
            backend_result = parse_backend_execution_result(backend_result_wire, producer=False)
            run_result = parse_run_result(run_result_wire, producer=False)
            validate_backend_execution_request(run_request, backend_request, case_data["parameters"]["selection_hash"])
            validate_backend_execution_result(backend_request, backend_result)
            validate_run_result(run_request, run_result)
            if not any(item["backend_execution_id"] == backend_result["backend_execution_id"] for item in run_result["backend_executions"]):
                raise ContractViolation("sipi.run-result.v1", "identity", "/backend_executions", "backend result summary mismatch")
            model = None
        elif case["entrypoint"] == "artifact":
            model = parse_artifact_ref(_document(case_dir, documents["subject"]), producer=case["mode"] == "producer")
        elif case["entrypoint"] == "artifact_integrity":
            model = parse_artifact_ref(_document(case_dir, documents["subject"]), producer=case["mode"] == "producer")
            if code := artifact_integrity_error(case_dir, documents, model):
                return {"id": case["id"], "decision": "reject", "phase": "integrity", "code": code}
        elif case["entrypoint"] == "event":
            model = parse_run_event(_document(case_dir, documents["subject"]), producer=case["mode"] == "producer")
        elif case["entrypoint"] == "capabilities":
            model = parse_engine_capabilities(_document(case_dir, documents["subject"]), producer=case["mode"] == "producer")
        elif case["entrypoint"] == "capabilities_baseline":
            model = parse_capability_baseline(_document(case_dir, documents["subject"]))
        elif case["entrypoint"] == "validation_report":
            model = parse_validation_report(_document(case_dir, documents["subject"]), producer=case["mode"] == "producer")
        elif case["entrypoint"] == "resource_slice":
            validate_resource_slice(_document(case_dir, documents["parent"]), _document(case_dir, documents["child"]), _document(case_dir, documents["enforcement"]))
            model = None
        else:
            raise RuntimeError(f"M1-06 case has no Python dispatch: {case['entrypoint']}")
    except FixtureViolation as error:
        return {"id": case["id"], "decision": "reject", "phase": "integrity", "code": str(error)}
    except ContractViolation as error:
        if error.code == "schema":
            phase = "schema"
        elif case["entrypoint"] == "resource_slice":
            phase = "relation"
        elif case["entrypoint"] == "selection_chain" and error.code in {"identity", "selection", "selection_hash", "orchestration"}:
            phase = "relation"
        else:
            phase = "semantic"
        return {"id": case["id"], "decision": "reject", "phase": phase, "code": error.code}
    preserved = all(_pointer(model.to_wire(), pointer) == _pointer(_document(case_dir, documents["subject"]), pointer) for pointer in case["expect"].get("preserve", [])) if model is not None else True
    phase = "relation" if case["entrypoint"] == "selection_chain" else case["expect"]["phase"]
    return {"id": case["id"], "decision": "accept" if preserved else "reject", "phase": phase, "preserved": preserved}


def main() -> int:
    suite = json.loads((FIXTURES / "suite.json").read_text(encoding="utf-8"))
    schema = json.loads((FIXTURES / "suite.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(suite)
    cases = [case for case in suite["cases"] if case.get("runner", "local") == "local"]
    results = [_run(case) for case in cases]
    failed = [result for case, result in zip(cases, results) if result["decision"] != "deferred" and (result["decision"] != case["expect"]["decision"] or result["phase"] != case["expect"]["phase"] or not result.get("preserved", True))]
    print(json.dumps({"runner": "python", "results": results, "failed": failed}, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
