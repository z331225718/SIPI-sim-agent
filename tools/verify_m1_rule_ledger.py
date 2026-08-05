"""Verify the M1-06 authority coverage ledger."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures" / "contracts" / "v1"
AUTHORITY = ROOT / "schemas" / "authority.v1.yaml"
LANGUAGE_BINDINGS = {
    "python": "python",
    "rust": "rust",
    "Python": "python",
    "Rust": "rust",
    "planned:PythonCapabilityBaselineV1": "python",
}
STATES = {"covered", "gap", "deferred", "not_applicable"}
DOCUMENT_SCHEMAS = {
    "run_request": "sipi.run-request.v1",
    "backend_request": "sipi.backend-execution-request.v1",
    "backend_result": "sipi.backend-execution-result.v1",
    "run_result": "sipi.run-result.v1",
}


def _local_key(schema_id: str) -> str:
    return f"schema:{schema_id}"


def _external_key(identifier: dict) -> str:
    return f"external:{identifier['kind']}:{identifier['value']}"


def _rule_contract_key(rule: dict) -> str | None:
    if "schema_id" in rule:
        return _local_key(rule["schema_id"])
    external = rule.get("external_contract")
    if isinstance(external, dict) and isinstance(external.get("identifier"), dict):
        return _external_key(external["identifier"])
    return None


def _external_contracts(authority: dict) -> dict[str, dict]:
    return {
        _external_key(contract["identifier"]): contract
        for contract in authority.get("external_contracts", [])
    }


def _authority_obligations(authority: dict) -> set[tuple[str, str, str]]:
    obligations = set()
    for schema in authority["schemas"]:
        if schema["source_of_truth"]["kind"] != "local_json_schema":
            continue
        for obligation, task in schema["conformance"].items():
            if task != "planned:M1-06":
                continue
            for binding in schema["bindings"]:
                language = LANGUAGE_BINDINGS.get(binding)
                if language is None:
                    raise ValueError(f"unknown_binding:{schema['schema_id']}:{binding}")
                obligations.add((_local_key(schema["schema_id"]), obligation, language))
    for contract in authority.get("external_contracts", []):
        for obligation, conformance in contract["conformance"].items():
            if not isinstance(conformance, dict) or conformance.get("task") != "M1-06":
                continue
            for binding in contract["bindings"]:
                language = LANGUAGE_BINDINGS.get(binding)
                if language is None:
                    raise ValueError(f"unknown_binding:{contract['identifier']['value']}:{binding}")
                obligations.add((_external_key(contract["identifier"]), obligation, language))
    return obligations


def _case_document(case: dict, ref: dict, schema_id: str) -> bool:
    if case["entrypoint"] == "selection_chain":
        if DOCUMENT_SCHEMAS.get(ref["document"]) != schema_id:
            return False
        case_path = FIXTURES / case["path"] / "case.json"
        documents = json.loads(case_path.read_text(encoding="utf-8"))["documents"]
        if ref["document"] not in documents:
            return False
        document_path = (case_path.parent / documents[ref["document"]]).resolve()
        return document_path.is_file()
    if ref["document"] != ("pair" if case["entrypoint"] == "resource_slice" else "subject"):
        return False
    return case["schema_id"] == schema_id


def _external_source_matches(rule: dict, authority_contract: dict) -> bool:
    external = rule.get("external_contract", {})
    source = authority_contract["source_of_truth"]
    return (
        external.get("identifier") == authority_contract["identifier"]
        and all(external.get("source_of_truth", {}).get(field) == source[field] for field in ("repository", "path", "symbol"))
    )


def _source_repositories(authority: dict) -> dict[str, dict]:
    reference = authority.get("source_snapshot_ref")
    if not isinstance(reference, str):
        raise ValueError("missing_source_snapshot_ref")
    snapshot_path = (ROOT / reference).resolve()
    try:
        snapshot_path.relative_to(ROOT)
    except ValueError as error:
        raise ValueError("source_snapshot_path_escape") from error
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    repositories = snapshot.get("repositories")
    if not isinstance(repositories, list):
        raise ValueError("invalid_source_snapshot")
    result = {repository.get("id"): repository for repository in repositories if isinstance(repository, dict)}
    if len(result) != len(repositories) or None in result:
        raise ValueError("invalid_source_snapshot_repositories")
    return result


def _snapshot_matches(evidence: dict, authority_contract: dict, repositories: dict[str, dict]) -> bool:
    snapshot = evidence.get("source_snapshot")
    if not isinstance(snapshot, dict):
        return False
    source = authority_contract["source_of_truth"]
    repository = repositories.get(source["repository"])
    if not isinstance(repository, dict):
        return False
    return (
        snapshot.get("repository") == source["repository"]
        and snapshot.get("revision") == repository.get("head")
        and snapshot.get("tree") == repository.get("tree")
    )


def _case_matches_layer(case: dict, rule: dict) -> bool:
    if rule["layer"] == "preservation":
        return case["expect"]["decision"] == "accept" and bool(case["expect"].get("preserve"))
    return case["expect"]["phase"] == rule["layer"]


def verify(*, case_results: dict[str, dict[str, dict]] | None = None) -> dict:
    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    ledger = json.loads((FIXTURES / "rule-ledger.json").read_text(encoding="utf-8"))
    ledger_schema = json.loads((FIXTURES / "rule-ledger.schema.json").read_text(encoding="utf-8"))
    suite = json.loads((FIXTURES / "suite.json").read_text(encoding="utf-8"))
    failures: list[str] = []
    for error in Draft202012Validator(ledger_schema).iter_errors(ledger):
        failures.append(f"ledger:schema:{error.json_path}")
    if ledger.get("schema") != "sipi.conformance-rule-ledger.v1":
        failures.append("ledger:schema")
    if ledger.get("scope") != {"task": "M1-06", "authority_path": "schemas/authority.v1.yaml"}:
        failures.append("ledger:scope")
    if ledger.get("authority_sha256") != hashlib.sha256(AUTHORITY.read_bytes()).hexdigest():
        failures.append("ledger:authority_sha256")
    cases = {case["id"]: case for case in suite["cases"]}
    expected_case_ids = {case_id for case_id, case in cases.items() if "deferred_to" not in case}
    expected_obligations = _authority_obligations(authority)
    external_contracts = _external_contracts(authority)
    source_repositories = _source_repositories(authority)
    rule_ids: set[str] = set()
    evidence_obligations: set[tuple[str, str, str]] = set()
    cited_case_languages: set[tuple[str, str]] = set()
    states_by_obligation: dict[tuple[str, str, str], set[str]] = {}
    accepts_by_obligation: set[tuple[str, str, str]] = set()
    for rule in ledger.get("rules", []):
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or rule_id in rule_ids:
            failures.append(f"ledger:duplicate_rule:{rule_id}")
        rule_ids.add(rule_id)
        contract_key = _rule_contract_key(rule)
        authority_external = external_contracts.get(contract_key)
        if contract_key is None:
            failures.append(f"ledger:missing_contract:{rule_id}")
        elif contract_key.startswith("external:") and authority_external is None:
            failures.append(f"ledger:unknown_external_contract:{rule_id}")
        elif authority_external is not None and not _external_source_matches(rule, authority_external):
            failures.append(f"ledger:external_source_mismatch:{rule_id}")
        for language, evidence in rule.get("evidence", {}).items():
            obligation = (contract_key, rule.get("obligation"), language)
            if language not in {"python", "rust"} or obligation not in expected_obligations:
                failures.append(f"ledger:unexpected_obligation:{rule_id}:{language}")
                continue
            evidence_obligations.add(obligation)
            state = evidence.get("state")
            states_by_obligation.setdefault(obligation, set()).add(state)
            refs = evidence.get("case_refs", [])
            if state not in STATES:
                failures.append(f"ledger:state:{rule_id}:{language}")
            if state == "covered" and (not evidence.get("implementation_refs") or not refs):
                failures.append(f"ledger:covered_evidence:{rule_id}:{language}")
            if authority_external is not None and state == "covered" and not _snapshot_matches(evidence, authority_external, source_repositories):
                failures.append(f"ledger:external_snapshot:{rule_id}:{language}")
            if state != "covered" and refs:
                failures.append(f"ledger:noncovered_cases:{rule_id}:{language}")
            if state == "deferred" and evidence.get("deferred_to") not in {"M1-07", "M1-08"}:
                failures.append(f"ledger:deferred_target:{rule_id}:{language}")
            for ref in refs:
                case = cases.get(ref.get("id"))
                if case is None or "deferred_to" in case:
                    failures.append(f"ledger:case_missing_or_deferred:{rule_id}:{language}:{ref.get('id')}")
                    continue
                case_matches_contract = (
                    _case_document(case, ref, rule["schema_id"])
                    if "schema_id" in rule
                    else case.get("external_contract") == rule["external_contract"]["identifier"]
                )
                if language not in case["required_languages"] or case["mode"] != rule["obligation"] or not case_matches_contract or not _case_matches_layer(case, rule):
                    failures.append(f"ledger:case_mismatch:{rule_id}:{language}:{case['id']}")
                    continue
                cited_case_languages.add((case["id"], language))
                if case["expect"]["decision"] == "accept":
                    accepts_by_obligation.add(obligation)
                if case_results is not None:
                    actual = case_results.get(language, {}).get(case["id"], {})
                    expected = case["expect"]
                    if actual.get("decision") != expected["decision"] or actual.get("phase") != expected["phase"] or ("code" in expected and actual.get("code") != expected["code"]) or (expected.get("preserve") and actual.get("preserved") is not True):
                        failures.append(f"ledger:case_not_passing:{rule_id}:{language}:{case['id']}")
    for obligation in sorted(expected_obligations - evidence_obligations):
        failures.append("ledger:missing_obligation:" + ":".join(obligation))
    for case_id in sorted(expected_case_ids):
        for language in cases[case_id]["required_languages"]:
            if (case_id, language) not in cited_case_languages:
                failures.append(f"ledger:orphan_case_language:{case_id}:{language}")
    matrix = {
        obligation[0].removeprefix("schema:") + ":" + ":".join(obligation[1:]): ("covered" if states == {"covered"} and obligation in accepts_by_obligation else "partial" if "covered" in states else "deferred" if states == {"deferred"} else "gap")
        for obligation, states in sorted(states_by_obligation.items())
    }
    if suite.get("status") == "complete" and any(state != "covered" for state in matrix.values()):
        failures.append("ledger:complete_with_gaps")
    return {
        "scope": ledger.get("scope"),
        "verification_mode": "runner_checked" if case_results is not None else "structure_only",
        "matrix": matrix,
        "failures": failures,
    }


def main() -> int:
    output = verify()
    print(json.dumps(output, sort_keys=True))
    return 1 if output["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
