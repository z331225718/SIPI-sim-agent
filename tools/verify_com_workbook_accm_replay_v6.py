"""Fail-closed verifier for the v6 current-candidate COM replay record."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/baselines/com-workbook-accm-replay-v6.manifest.yaml"
HEX = set("0123456789abcdef")


class VerificationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    def duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise VerificationError("duplicate JSON key")
            result[key] = value
        return result
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=duplicates)
    require(isinstance(value, dict), "JSON root must be an object")
    return value


def bound_file(root: Path, item: dict[str, Any]) -> Path:
    require(set(item) >= {"path", "bytes", "sha256"}, "file binding schema")
    relative = item["path"]
    require(isinstance(relative, str) and relative.startswith("docs/") and ".." not in relative and "\\" not in relative, "unsafe file path")
    path = root / relative
    require(path.is_file() and path.stat().st_size == item["bytes"] and digest(path) == item["sha256"], "bound file digest")
    return path


def validate(path: Path = DEFAULT, *, root: Path = ROOT) -> dict[str, Any]:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    require(isinstance(document, dict), "manifest root")
    require(document.get("schema") == "sipi.com.workbook-accm-replay.v6.formal", "manifest schema")
    require(document.get("status") == "scoped_numeric_parity_observed", "manifest status")
    require(document.get("claims", {}).get("acceptance") is False, "acceptance claim")
    candidate, upstream = document.get("candidate"), document.get("upstream")
    require(isinstance(candidate, dict) and isinstance(upstream, dict), "source bindings")
    runs = document.get("runs")
    require(isinstance(runs, list) and len(runs) == 2, "run count")
    reports = [read_json(bound_file(root, item)) for item in runs]
    require(len({item["run_id"] for item in runs}) == 2 and len({item["nonce"] for item in runs}) == 2, "fresh identities")
    for item, report in zip(runs, reports):
        require(report.get("schema") == "sipi.com.workbook-accm-replay.v6.diagnostic", "report schema")
        require(report.get("status") == document["status"] and report.get("matched") is True and report.get("acceptance") is False and report.get("blockers") == [], "report status")
        for observed, expected in ((report.get("candidate"), candidate), (report.get("upstream"), upstream)):
            require(isinstance(observed, dict), "report source shape")
            archive = observed.get("archive")
            require(
                observed.get("commit") == expected.get("commit")
                and observed.get("tree") == expected.get("tree")
                and isinstance(archive, dict)
                and archive.get("bytes") == expected.get("archive_bytes")
                and archive.get("sha256") == expected.get("archive_sha256"),
                "report source binding",
            )
        require(report.get("run_id") == item["run_id"] and report.get("nonce") == item["nonce"], "report identity")
        for control in report.get("controls", []):
            for comparison in control.get("comparison", []):
                require(comparison.get("numeric_within_tolerance") is True, "numeric comparison")
                require(comparison.get("port_order_public_result") == "not_exposed_by_upstream", "port order claim")
                require(comparison.get("dfe", {}).get("candidate_published") is True, "candidate DFE")
    aggregate_item = document.get("aggregate")
    require(isinstance(aggregate_item, dict), "aggregate binding")
    aggregate = read_json(bound_file(root, aggregate_item))
    require(aggregate.get("schema") == "sipi.com.workbook-accm-replay.v6.aggregate" and aggregate.get("status") == document["status"] and aggregate.get("matched") is True and aggregate.get("acceptance") is False and aggregate.get("blockers") == [], "aggregate status")
    require(aggregate.get("candidate") == reports[0].get("candidate") and aggregate.get("upstream") == reports[0].get("upstream"), "aggregate source binding")
    require({item.get("run_id") for item in aggregate.get("runs", [])} == {item["run_id"] for item in runs}, "aggregate runs")
    harness = document.get("harness")
    require(isinstance(harness, dict), "harness binding")
    for item in (harness.get("runner"), harness.get("aggregate")):
        require(isinstance(item, dict) and isinstance(item.get("path"), str) and isinstance(item.get("sha256"), str), "harness item")
        target = root / item["path"]
        require(target.is_file() and digest(target) == item["sha256"], "harness digest")
    return {"valid": True, "status": document["status"], "runs": len(runs)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT)
    args = parser.parse_args()
    print(json.dumps(validate(args.manifest), sort_keys=True))
