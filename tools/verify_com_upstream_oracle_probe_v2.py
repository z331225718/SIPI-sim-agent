"""Fail-closed verifier for pinned upstream runtime probe evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
HEX64 = re.compile(r"^[0-9a-f]{64}$")
BOUND_FILES = (
    "tools/run_com_upstream_oracle_probe_v2.py",
    "tools/aggregate_com_upstream_oracle_probe_v2.py",
    "tools/verify_com_upstream_oracle_probe_v2.py",
    "tools/test_verify_com_upstream_oracle_probe_v2.py",
    "docs/baselines/audits/2026-08-23-com-upstream-runtime-oracle-v2.md",
)
UPSTREAM = {
    "commit": "5272ffe74702cd585054d975559b06f8afae7b6e",
    "tree": "7094ab6e84989b218730c52432c70da10261f8ea",
    "archive_sha256": "a7bbe0e019d5ce4d7b47246b6f0daccdd3cfc8f27a471b03eb50e8c751082ccf",
    "declared_license": "MIT",
    "materialization": "git archive at immutable commit",
    "observation_scope": "upstream_only",
    "runtime_executed": True,
}


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def has_absolute(value: object) -> bool:
    if isinstance(value, dict):
        return any(has_absolute(k) or has_absolute(v) for k, v in value.items())
    if isinstance(value, list):
        return any(has_absolute(v) for v in value)
    return isinstance(value, str) and bool(re.search(r"(?:^[A-Za-z]:[\\/])|(?:^/)|(?:\\\\)", value))


def verify(aggregate_path: Path, mode: str) -> dict[str, Any]:
    aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
    require(not has_absolute(aggregate), "absolute path leaked into aggregate")
    require(aggregate.get("schema") == "sipi.com-upstream-runtime-oracle-aggregate.v2", "schema drift")
    require(aggregate.get("mode") == mode, "mode drift")
    require(aggregate.get("status") == "portable_numeric_observed_full_entrypoint_blocked", "status overclaim or drift")
    require(aggregate.get("fresh_runs") == 2, "fresh run count drift")
    require(aggregate.get("upstream") == UPSTREAM, "upstream identity drift")
    binding = aggregate.get("execution_binding", {})
    require(binding.get("entrypoint_timeout_seconds") == 15, "timeout gate drift")
    require(binding.get("toolchain", {}).get("path_redacted") is True, "toolchain redaction drift")
    require(binding.get("fixtures", {}).get("paths_relative_to_archive") is True, "fixture containment drift")
    require(binding.get("scripts", {}).get("path_redacted") is True, "script path redaction drift")
    for relative in BOUND_FILES:
        item = binding.get("scripts", {}).get("files", {}).get(relative, {})
        require(item.get("path") == relative, f"binding path drift: {relative}")
        require(sha256(ROOT / relative) == item.get("sha256"), f"binding hash drift: {relative}")
    toolchain = binding.get("toolchain", {})
    for role in ("python", "uv"):
        identity = toolchain.get(role)
        require(isinstance(identity, dict), f"{role} identity missing")
        require(identity.get("role") == role and not has_absolute(identity), f"{role} identity path drift")
        require(identity.get("path_redacted") is True and identity.get("version_exit_code") == 0, f"{role} identity drift")
        require(HEX64.fullmatch(identity.get("file_sha256", "")), f"{role} file hash drift")
        require(HEX64.fullmatch(identity.get("version_output_sha256", "")), f"{role} version hash drift")
    require(toolchain.get("uv_available") is True, "uv availability drift")
    package = binding.get("package", {})
    require(package.get("package") == "agent_com" and package.get("file_count", 0) > 0, "package identity drift")
    require(HEX64.fullmatch(package.get("tree_sha256", "")), "package tree hash drift")
    fixtures = binding.get("fixtures", {})
    require(len(fixtures.get("inputs", [])) == 2, "fixture count drift")
    require(all(item.get("path") in {"matlab_src/config_com_ieee8023_93a=3ck_SA_120g_C2M_tp1a_08_17_2022.xlsx", "fixtures/synthetic/thru_10db_at_26p56ghz.s4p"} and HEX64.fullmatch(item.get("sha256", "")) for item in fixtures["inputs"]), "fixture identity drift")
    reports = aggregate.get("reports")
    require(isinstance(reports, list) and len(reports) == 2, "report bindings missing")
    parsed = []
    for item in reports:
        path = ROOT / item["path"]
        require(path.is_file(), "report missing")
        require(sha256(path) == item["sha256"], "report SHA drift")
        report = json.loads(path.read_text(encoding="utf-8"))
        require(not has_absolute(report), "absolute path leaked into report")
        require(report.get("schema") == "sipi.com-upstream-runtime-oracle.v2", "report schema drift")
        require(report.get("mode") == mode, "report mode drift")
        require(report.get("upstream") == UPSTREAM, "report upstream drift")
        require(report.get("upstream", {}).get("observation_scope") == "upstream_only", "observation scope drift")
        require(report.get("upstream", {}).get("runtime_executed") is True, "runtime execution drift")
        require(HEX64.fullmatch(report.get("fresh_run_nonce", "")), "nonce drift")
        require(report.get("portable_leaf", {}).get("status") == "numeric_payload_observed", "portable payload missing")
        entrypoint = report.get("entrypoint", {})
        require(entrypoint.get("status") == "blocked", "full entrypoint was not fail-closed")
        require(entrypoint.get("reason") == "entrypoint_timeout", "entrypoint blocker drift")
        require(entrypoint.get("entrypoint") == "agent_com.api.run_com", "entrypoint identity drift")
        require(entrypoint.get("timeout_seconds") == 15, "entrypoint timeout drift")
        require(report.get("parity", {}).get("candidate_rust_parity_claim") is False, "candidate parity overclaim")
        require(report.get("execution_binding") == binding, "report execution binding drift")
        parsed.append(report)
    require(parsed[0]["run_id"] != parsed[1]["run_id"], "run IDs are not distinct")
    require(parsed[0]["fresh_run_nonce"] != parsed[1]["fresh_run_nonce"], "nonces are not distinct")
    require(parsed[0]["portable_leaf"]["payload"] == parsed[1]["portable_leaf"]["payload"], "numeric leaf payload drift")
    require(aggregate.get("portable_leaf_numeric_payload") == parsed[0]["portable_leaf"]["payload"], "aggregate payload drift")
    require(aggregate.get("portable_payload_identical") is True, "aggregate equality drift")
    require(aggregate.get("execution_binding") == binding, "aggregate execution binding drift")
    expected_reports = [
        {"path": item["path"], "sha256": item["sha256"], "run_id": parsed[index].get("run_id"), "fresh_run_nonce": parsed[index].get("fresh_run_nonce")}
        for index, item in enumerate(reports)
    ]
    require(aggregate.get("reports") == expected_reports, "aggregate report cross-binding drift")
    return {"schema": aggregate["schema"], "mode": mode, "fresh_runs": 2, "full_run_numeric_parity": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("com-02", "com-04"), required=True)
    parser.add_argument("--aggregate", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.aggregate, args.mode), sort_keys=True))
    except (OSError, KeyError, TypeError, json.JSONDecodeError, VerificationError) as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
