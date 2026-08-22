"""Verify the CLI-only upstream migration route boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tomllib
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/baselines/upstream-cli-integration.v1.yaml"
SCHEMA = "sipi.upstream-cli-integration.v1"
EXPECTED = {
    **{f"AS-{number:02d}": "sipi-agent-spice-adapter" for number in range(1, 7)},
    **{f"PB-{number:02d}": "sipi-pybert-adapter" for number in range(1, 6)},
    **{f"COM-{number:02d}": "sipi-agent-com-adapter" for number in range(1, 5)},
}
EXPECTED_ROUTES = {
    "AS-01": ("upstream.agent-spice.fit-sparam", ["upstream", "agent-spice", "fit-sparam"]),
    "AS-02": ("upstream.agent-spice.fit-sparam-cascade", ["upstream", "agent-spice", "fit-sparam-cascade"]),
    "AS-03": ("upstream.agent-spice.fit-yparam", ["upstream", "agent-spice", "fit-yparam"]),
    "AS-04": ("upstream.agent-spice.tune-yparam-tran", ["upstream", "agent-spice", "tune-yparam-tran"]),
    "AS-05": ("upstream.agent-spice.run-hspice", ["upstream", "agent-spice", "run-hspice"]),
    "AS-06": ("upstream.agent-spice.run-rfm", ["upstream", "agent-spice", "run-rfm"]),
    "PB-01": ("upstream.pybert.sim", ["upstream", "pybert", "sim"]),
    "PB-02": ("upstream.pybert.sim-native", ["upstream", "pybert", "sim-native"]),
    "PB-03": ("upstream.pybert.sim-rust", ["upstream", "pybert", "sim-rust"]),
    "PB-04": ("upstream.pybert.sim-auto", ["upstream", "pybert", "sim-auto"]),
    "PB-05": ("upstream.pybert.sim-compare", ["upstream", "pybert", "sim-compare"]),
    "COM-01": ("upstream.agent-com.config-validate", ["upstream", "agent-com", "config-validate"]),
    "COM-02": ("upstream.agent-com.run", ["upstream", "agent-com", "run"]),
    "COM-03": ("upstream.agent-com.compare", ["upstream", "agent-com", "compare"]),
    "COM-04": ("upstream.agent-com.public-api", ["upstream", "agent-com", "public-api"]),
}
CLI_MAIN = ROOT / "crates/sipi-cli/src/main.rs"
CLI_MODULE = ROOT / "crates/sipi-cli/src/upstream_migration.rs"
CLI_CARGO = ROOT / "crates/sipi-cli/Cargo.toml"
CLI_TEST = ROOT / "crates/sipi-cli/tests/upstream_migration.rs"
EXPECTED_SOURCE_FILES = {
    "crates/sipi-cli/src/main.rs": CLI_MAIN,
    "crates/sipi-cli/src/upstream_migration.rs": CLI_MODULE,
    "crates/sipi-cli/Cargo.toml": CLI_CARGO,
    "crates/sipi-cli/tests/upstream_migration.rs": CLI_TEST,
}


class IntegrationError(RuntimeError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise IntegrationError(reason)


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, UnicodeError) as error:
        raise IntegrationError(f"source_read_failed:{path}") from error


def _manifest_routes(text: str) -> dict[str, list[str]]:
    routes: dict[str, list[str]] = {}
    pattern = re.compile(
        r'CommandDescriptorV1\s*\{\s*id:\s*"([^"]+)",\s*route:\s*&\[([^\]]*)\],',
        re.MULTILINE,
    )
    for match in pattern.finditer(text):
        if match.group(1) in routes:
            raise IntegrationError(f"cli_manifest_duplicate:{match.group(1)}")
        routes[match.group(1)] = re.findall(r'"([^"]+)"', match.group(2))
    return routes


def _verify_test_fixture_isolation(cargo: dict[str, Any]) -> None:
    features = cargo.get("features")
    _require(isinstance(features, dict), "cli_features_invalid")
    _require(features.get("test-support") == [], "test_support_feature_not_empty")

    bins = cargo.get("bin")
    _require(isinstance(bins, list), "cli_bins_invalid")
    fake_bins = [item for item in bins if isinstance(item, dict) and item.get("name") == "sipi-upstream-fake"]
    _require(len(fake_bins) == 1, "fixture_bin_missing_or_duplicate")
    fake = fake_bins[0]
    _require(fake.get("path") == "src/bin/upstream_fake.rs", "fixture_bin_path_invalid")
    _require(fake.get("required-features") == ["test-support"], "fixture_bin_feature_isolation_invalid")

    tests = cargo.get("test")
    _require(isinstance(tests, list), "cli_tests_manifest_invalid")
    upstream_tests = [item for item in tests if isinstance(item, dict) and item.get("name") == "upstream_migration"]
    _require(len(upstream_tests) == 1, "fixture_test_missing_or_duplicate")
    upstream_test = upstream_tests[0]
    _require(upstream_test.get("path") == "tests/upstream_migration.rs", "fixture_test_path_invalid")
    _require(
        upstream_test.get("required-features") == ["test-support"],
        "fixture_test_feature_isolation_invalid",
    )


def _verify_com_compare_semantics(module_text: str, test_text: str) -> None:
    module_markers = (
        '"agent-com.compare" =>',
        "Ok(com_compare_result_json(&result))",
        "fn com_compare_result_json(result: &sipi_agent_com_adapter::CompareResponse)",
        '"matched": result.report.matched',
        '"success": result.exit_code == 0',
        '"code": result.exit_code',
    )
    for marker in module_markers:
        _require(marker in module_text, f"com_typed_mismatch_semantics_missing:{marker}")
    test_markers = (
        "compare_mismatch_is_a_typed_result_not_a_transport_failure",
        'body.contains("\\\"matched\\\":false")',
        'body.contains("\\\"code\\\":3")',
        '!body.contains("external_adapter_nonzero_exit")',
        "compare_protocol_and_upstream_failures_remain_transport_errors",
        '("exit3-no-report", "external_adapter_failure")',
        '("exit4", "external_adapter_nonzero_exit")',
    )
    for marker in test_markers:
        _require(marker in test_text, f"com_typed_mismatch_test_missing:{marker}")


def _verify_source_bindings(evidence: dict[str, Any], root: Path) -> None:
    source_files = evidence.get("source_files")
    _require(isinstance(source_files, list), "source_files_invalid")
    observed: dict[str, str] = {}
    for item in source_files:
        _require(isinstance(item, dict) and set(item) == {"path", "sha256"}, "source_file_shape_invalid")
        path = item["path"]
        _require(path in EXPECTED_SOURCE_FILES and path not in observed, "source_file_path_invalid")
        expected_path = root / path
        _require(expected_path == EXPECTED_SOURCE_FILES[path], "source_file_root_invalid")
        observed[path] = item["sha256"]
        _require(re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) is not None, "source_hash_shape_invalid")
        _require(_sha256(expected_path) == item["sha256"], f"source_hash_drift:{path}")
    _require(set(observed) == set(EXPECTED_SOURCE_FILES), "source_file_set_invalid")

    try:
        cargo = tomllib.loads(CLI_CARGO.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise IntegrationError("cli_cargo_invalid") from error
    _verify_test_fixture_isolation(cargo)
    dependencies = cargo.get("dependencies")
    _require(isinstance(dependencies, dict), "cli_dependencies_invalid")
    _require(cargo.get("package", {}).get("default-run") == "sipi", "cli_default_run_invalid")
    for crate in set(EXPECTED.values()):
        dependency = dependencies.get(crate)
        _require(isinstance(dependency, dict), f"cli_adapter_dependency_missing:{crate}")
        _require(dependency.get("path") == f"../{crate}", f"cli_adapter_dependency_path_invalid:{crate}")

    main_text = CLI_MAIN.read_text(encoding="utf-8")
    observed_routes = _manifest_routes(main_text)
    expected_manifest = {command_id: route for command_id, route in EXPECTED_ROUTES.values()}
    external_manifest = {
        command_id: route
        for command_id, route in observed_routes.items()
        if command_id in expected_manifest
    }
    _require(len(external_manifest) == len(EXPECTED_ROUTES), "cli_manifest_route_count_invalid")
    _require(external_manifest == expected_manifest, "cli_manifest_route_drift")
    module_text = CLI_MODULE.read_text(encoding="utf-8")
    for _, route in EXPECTED_ROUTES.values():
        _require(f'"{route[1]}.{route[2]}"' in module_text, "cli_known_route_drift")
    test_text = CLI_TEST.read_text(encoding="utf-8")
    _verify_com_compare_semantics(module_text, test_text)


def _load(path: Path = EVIDENCE) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise IntegrationError("evidence_invalid") from error
    _require(isinstance(value, dict), "evidence_not_mapping")
    return value


def validate(evidence: dict[str, Any] | None = None, root: Path = ROOT) -> dict[str, Any]:
    evidence = _load() if evidence is None else evidence
    _require(evidence.get("schema") == SCHEMA, "schema_invalid")
    _require(evidence.get("status") == "external_migration_routes_integrated", "status_invalid")
    _require(evidence.get("transport") == "external_migration_adapter", "transport_invalid")
    _require(evidence.get("request_schema") == "sipi.upstream-migration-request.v1", "request_schema_invalid")
    _require(evidence.get("response_schema") == "sipi.upstream-migration-result.v1", "response_schema_invalid")
    freeze = evidence.get("feature_freeze")
    _require(isinstance(freeze, dict), "feature_freeze_invalid")
    _require(freeze.get("new_domain_features_allowed") is False, "new_feature_enabled")
    _require(freeze.get("numerical_semantics_added") is False, "numerical_semantics_added")
    _require(freeze.get("silent_fallback") == "forbidden", "silent_fallback_allowed")

    audit = evidence.get("audit")
    _require(isinstance(audit, dict) and set(audit) == {"path", "sha256"}, "audit_binding_invalid")
    audit_path = root / audit["path"]
    _require(audit["path"] == "docs/baselines/audits/2026-08-22-upstream-cli-integration.md", "audit_path_invalid")
    _require(audit_path.is_file(), "audit_missing")
    _require(re.fullmatch(r"[0-9a-f]{64}", audit["sha256"]) is not None, "audit_hash_shape_invalid")
    _require(_sha256(audit_path) == audit["sha256"], "audit_hash_drift")
    audit_text = " ".join(audit_path.read_text(encoding="utf-8").split())
    for marker in (
        "test-support = []",
        "required-features = [\"test-support\"]",
        "typed comparison result",
        "matched = false",
        "exit.code = 3",
        "protocol failures and other non-zero upstream exits remain transport failures",
    ):
        _require(marker in audit_text, f"audit_semantics_missing:{marker}")
    _verify_source_bindings(evidence, root)

    routes = evidence.get("routes")
    _require(isinstance(routes, list) and len(routes) == 15, "route_count_invalid")
    seen: set[str] = set()
    for route in routes:
        _require(isinstance(route, dict), "route_shape_invalid")
        route_id = route.get("id")
        _require(route_id in EXPECTED and route_id not in seen, "route_id_invalid")
        seen.add(route_id)
        expected_command_id, expected_route = EXPECTED_ROUTES[route_id]
        _require(route.get("command_id") == expected_command_id, f"command_id_drift:{route_id}")
        _require(route.get("route") == expected_route, f"route_drift:{route_id}")
        _require(route.get("adapter_crate") == EXPECTED[route_id], f"adapter_invalid:{route_id}")
        _require(route.get("status") == "route_integrated", f"route_status_invalid:{route_id}")
        _require(isinstance(route.get("route"), list) and route["route"][:1] == ["upstream"], "route_shape_invalid")
    _require(seen == set(EXPECTED), "route_set_invalid")

    scope = evidence.get("scope")
    _require(scope == {
        "product_capability": "not_claimed",
        "numerical_acceptance": "not_evaluated",
        "release_evidence": False,
        "external_payload_publication": "forbidden",
    }, "scope_claim_invalid")
    _require((root / "crates/sipi-cli/src/upstream_migration.rs").is_file(), "cli_module_missing")
    _require((root / "crates/sipi-cli/tests/upstream_migration.rs").is_file(), "cli_tests_missing")
    return {"valid": True, "routes": len(routes), "product_capability": "not_claimed"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        print(json.dumps(validate(), sort_keys=True))
    except IntegrationError as error:
        print(json.dumps({"valid": False, "reason": str(error)}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
