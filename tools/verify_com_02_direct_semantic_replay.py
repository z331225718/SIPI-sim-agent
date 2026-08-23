"""Verify the COM-02 direct semantic replay contract and evidence shape."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs" / "baselines" / "com-02-direct-port.v1.yaml"


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(manifest_path: Path = DEFAULT_MANIFEST) -> dict[str, Any]:
    try:
        document = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise VerificationError(f"cannot read manifest: {error}") from error
    require(isinstance(document, dict), "manifest must be a mapping")
    require(document.get("schema") == "sipi.com-02-direct-port.v1", "schema drift")
    require(document.get("status") == "direct_port_scoped_semantic_replay_open", "status overclaim")
    scope = document.get("scope")
    require(scope == {
        "work_item": "COM-02",
        "upstream_public_entrypoint": "run_com",
        "target": "lane_local_direct_port_only",
        "product_capability_promoted": False,
        "global_migration_row_closed": False,
        "source_map": "crates/sipi-agent-com-direct/SOURCE-MAP-COM-02.md",
    }, "scope drift")
    require(document.get("audit") == "docs/baselines/audits/2026-08-23-com-02-direct-semantic-replay.md", "audit binding drift")
    source = document.get("source")
    require(isinstance(source, dict), "source missing")
    require(source.get("commit") == "5272ffe74702cd585054d975559b06f8afae7b6e", "commit drift")
    require(source.get("tree") == "7094ab6e84989b218730c52432c70da10261f8ea", "tree drift")
    require(source.get("declared_license") == "MIT", "license drift")
    paths = source.get("source_paths")
    require(isinstance(paths, list) and len(paths) == 21, "reachable source path set drift")
    require(all(item.get("license") == "MIT" for item in paths), "path license drift")
    contract = document.get("contract")
    require(isinstance(contract, dict), "contract missing")
    require(contract.get("s_parameter_fit") == "forbidden", "S-parameter fit policy drift")
    require(contract.get("workflow") == ["load_config", "run_com", "write_artifacts"], "workflow drift")
    require(contract.get("portable_semantic_branches") == ["fd_to_td_json", "mixed_mode_pn_skew", "fext_next_waveform_inputs", "equalization_apply", "tdiln", "search_nonmmse_no_rxffe", "mmse_kkt_search", "fvlms_rxffe_search", "calibration_noise_controller", "workbook_csv_mat_reuse", "legacy_csv_projection"], "portable branch policy drift")
    require(contract.get("external_blocked") == ["plotting_format", "matlab_engine", "proprietary_golden"], "external blocker policy drift")
    oracle = document.get("oracle")
    require(isinstance(oracle, dict), "oracle missing")
    require(oracle.get("replay_count") == 2, "two replay policy drift")
    require(oracle.get("scenario_count") == 10, "portable replay scenario count drift")
    for claim in ("no_product_capability_promotion", "no_global_migration_row_close", "no_numeric_upstream_parity_claim", "no_s_parameter_fitting", "no_matlab_engine_or_proprietary_golden_parity"):
        require(claim in document.get("non_claims", []), f"non-claim missing: {claim}")
    evidence = document.get("evidence")
    if evidence is not None:
        require(isinstance(evidence, dict), "evidence must be a mapping")
        reports = evidence.get("reports", [])
        require(len(reports) == 2, "two evidence reports required")
        parsed = []
        for item in reports:
            path = ROOT / item["path"]
            require(path.is_file(), f"report missing: {path}")
            require(sha256(path) == item["sha256"], f"report hash drift: {path}")
            report = json.loads(path.read_text(encoding="utf-8"))
            require(report.get("mode") == "com-02", "report mode drift")
            require(report.get("replay_count") == 2, "report replay count drift")
            require(report.get("scenario_count") == 10, "report scenario count drift")
            require(report.get("semantic_replays_identical") is True, "semantic replay mismatch")
            require(report.get("replays", [{}])[0].get("scenario_count") == 10, "portable replay scenarios missing")
            parsed.append(report)
        aggregate_path = ROOT / evidence["aggregate"]["path"]
        require(aggregate_path.is_file(), "aggregate report missing")
        require(sha256(aggregate_path) == evidence["aggregate"]["sha256"], "aggregate hash drift")
        aggregate = json.loads(aggregate_path.read_text(encoding="utf-8"))
        require(aggregate.get("fresh_runs") == 2, "aggregate fresh-run count drift")
        require(aggregate.get("scenario_count") == 10, "aggregate scenario count drift")
        require(aggregate.get("semantic_replays_identical") is True, "aggregate semantic mismatch")
    return {"schema": document["schema"], "source_paths": len(paths), "evidence_bound": evidence is not None}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.manifest), sort_keys=True))
    except VerificationError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
