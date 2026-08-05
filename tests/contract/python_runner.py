"""Run materialized M1-06 conformance cases through public sipi_contracts APIs."""
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
from sipi_contracts.validation.relations import validate_resource_slice


FIXTURES = ROOT / "fixtures" / "contracts" / "v1"


def _document(case_dir: Path, name: str) -> dict:
    return json.loads((case_dir / name).read_text(encoding="utf-8"))


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
    documents = _document(case_dir, "case.json")["documents"]
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
            run_request = parse_run_request(_document(case_dir, documents["run_request"]))
            backend_request = parse_backend_execution_request(_document(case_dir, documents["backend_request"]))
            backend_result = parse_backend_execution_result(_document(case_dir, documents["backend_result"]), producer=True)
            run_result = parse_run_result(_document(case_dir, documents["run_result"]), producer=True)
            validate_backend_execution_request(run_request, backend_request, documents["selection_hash"])
            validate_backend_execution_result(backend_request, backend_result)
            validate_run_result(run_request, run_result)
            model = None
        elif case["entrypoint"] == "artifact":
            model = parse_artifact_ref(_document(case_dir, documents["subject"]), producer=case["mode"] == "producer")
        elif case["entrypoint"] == "artifact_integrity":
            model = parse_artifact_ref(_document(case_dir, documents["subject"]), producer=case["mode"] == "producer")
            content = (case_dir / documents["content"]).read_bytes()
            if hashlib.sha256(content).hexdigest() != model["sha256"]:
                return {"id": case["id"], "decision": "reject", "phase": "integrity", "code": "hash_mismatch"}
            if len(content) != model["byte_length"]:
                return {"id": case["id"], "decision": "reject", "phase": "integrity", "code": "length_mismatch"}
        elif case["entrypoint"] == "event":
            model = parse_run_event(_document(case_dir, documents["subject"]), producer=case["mode"] == "producer")
        elif case["entrypoint"] == "capabilities":
            model = parse_engine_capabilities(_document(case_dir, documents["subject"]), producer=case["mode"] == "producer")
        elif case["entrypoint"] == "validation_report":
            model = parse_validation_report(_document(case_dir, documents["subject"]), producer=case["mode"] == "producer")
        elif case["entrypoint"] == "resource_slice":
            validate_resource_slice(_document(case_dir, documents["parent"]), _document(case_dir, documents["child"]), _document(case_dir, documents["enforcement"]))
            model = None
        else:
            raise RuntimeError(f"M1-06 case has no Python dispatch: {case['entrypoint']}")
    except ContractViolation as error:
        phase = "schema" if error.code == "schema" else "relation" if case["entrypoint"] == "resource_slice" else "semantic"
        return {"id": case["id"], "decision": "reject", "phase": phase, "code": error.code}
    preserved = all(_pointer(model.to_wire(), pointer) == _pointer(_document(case_dir, documents["subject"]), pointer) for pointer in case["expect"].get("preserve", [])) if model is not None else True
    phase = "relation" if case["entrypoint"] == "selection_chain" else case["expect"]["phase"]
    return {"id": case["id"], "decision": "accept" if preserved else "reject", "phase": phase, "preserved": preserved}


def main() -> int:
    suite = json.loads((FIXTURES / "suite.json").read_text(encoding="utf-8"))
    schema = json.loads((FIXTURES / "suite.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(suite)
    results = [_run(case) for case in suite["cases"]]
    failed = [result for case, result in zip(suite["cases"], results) if result["decision"] != "deferred" and (result["decision"] != case["expect"]["decision"] or result["phase"] != case["expect"]["phase"] or not result.get("preserved", True))]
    print(json.dumps({"runner": "python", "results": results, "failed": failed}, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
