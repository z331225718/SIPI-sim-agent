"""Strict successor gate for the owner exclusion of AS-03 and AS-04."""

from __future__ import annotations

import hashlib
import math
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs/baselines/upstream-integration-ledger.v15.yaml"
INVENTORY = ROOT / "docs/baselines/upstream-migration-inventory.v2.yaml"
RECORD = ROOT / "docs/baselines/as03-as04-owner-exclusion.v1.yaml"
AUDIT = ROOT / "docs/baselines/audits/2026-09-02-as03-as04-owner-exclusion.md"
VERIFIER = ROOT / "tools/verify_as03_as04_owner_exclusion.py"
MUTATIONS = ROOT / "tools/test_verify_as03_as04_owner_exclusion.py"
PLAN = ROOT / "PLAN.md"
LEDGER_PREDECESSOR = ROOT / "docs/baselines/upstream-integration-ledger.v14.yaml"
INVENTORY_PREDECESSOR = ROOT / "docs/baselines/upstream-migration-inventory.v1.yaml"

LEDGER_SCHEMA = "sipi.upstream-integration-ledger.v15"
INVENTORY_SCHEMA = "sipi.upstream-migration-inventory.v2"
OWNER_SCHEMA = "sipi.upstream-owner-exclusion.v1"
LEDGER_PREDECESSOR_SHA = "263ab532e36959ae4d2a2b03a5da7896debd823e11680f84fceef142ee6aef63"
INVENTORY_PREDECESSOR_SHA = "1d1a3fc2e43be26884554ca8a1d94217ade6142c0e1ae92a686eaba9b6ca5a86"
PLAN_SHA = "9f4db9b49a7b24bba6c0b09837ddb849665def66438dc3a60fd2b664c6db4225"
OWNER_RECORD_SHA = "0c304947a0390fc37b3ce27c1b56d4bca800813d70f82e91e85e114ea776b22e"
AUDIT_SHA = "25f8b0f72fdf1321317cb421f6852083c6f1856e2aa529f878f58ce3e3c6539d"
VERIFIER_SHA = "df41a6f2a1d8694dc69b2202daa62fc4f2360a2e623e0c485073fe40a40511b8"
MUTATION_SHA = "b0c6b80618e53c1214fbad21ff8ceedf9402f7920e54fbaa7983a89eeba1e9bb"

CANDIDATE = {
    "commit": "ad797d8c6421c51b9607a2624cf4572c9c8b0b50",
    "tree": "d305cbfd27960926c969db9abbaeac81d8b1e988",
    "archive_sha256": "149c1162f8ba697a7d9509cb0950afff3fdad8c5977af051c6bd279b29cd1b30",
    "archive_bytes": 62822400,
    "materialization": "clean_git_archive",
    "autocrlf": True,
    "worktree_overlay": False,
}

AS03_EVIDENCE = {
    "path": "docs/baselines/as-03-power-wave-solve-replay.v1.yaml",
    "sha256": "6f75c64caa30e2b49b1fc4851ddc5a9f8601687ae8028c11686cfc9da1e9ffa1",
}
AS04_EVIDENCE = {
    "path": "docs/baselines/as-04-tune-yparam-tran-direct-port.v2.yaml",
    "sha256": "3e42e662be21b1814f0b37fb915a66441d0af2bcc0ab7ddd1ca77d1fac4883c8",
}


class ExclusionError(RuntimeError):
    """Raised when the owner-exclusion successor is not exact."""


class StrictLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate mapping keys."""


def _strict_mapping(loader: StrictLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ExclusionError("duplicate_yaml_key")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _strict_mapping)


def _finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ExclusionError("nonfinite_yaml_value")
    if isinstance(value, dict):
        for key, child in value.items():
            if type(key) is not str:
                raise ExclusionError("non_string_yaml_key")
            _finite(child)
    elif isinstance(value, list):
        for child in value:
            _finite(child)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=StrictLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise ExclusionError(f"yaml_invalid:{path.name}") from error
    if not isinstance(value, dict):
        raise ExclusionError(f"yaml_not_mapping:{path.name}")
    _finite(value)
    return value


def _exact(actual: Any, expected: Any, label: str) -> None:
    if type(actual) is not type(expected):
        raise ExclusionError(f"{label}:type")
    if isinstance(expected, dict):
        if set(actual) != set(expected):
            raise ExclusionError(f"{label}:keys")
        for key in expected:
            _exact(actual[key], expected[key], f"{label}:{key}")
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ExclusionError(f"{label}:length")
        for index, item in enumerate(expected):
            _exact(actual[index], item, f"{label}:{index}")
    elif actual != expected:
        raise ExclusionError(f"{label}:value")


def _raw_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalised_sha(path: Path) -> str:
    data = path.read_bytes()
    if path.resolve() == VERIFIER.resolve():
        for name in (
            "PLAN_SHA",
            "OWNER_RECORD_SHA",
            "AUDIT_SHA",
            "VERIFIER_SHA",
            "MUTATION_SHA",
        ):
            data = re.sub(
                rb"%b = \"[0-9a-f]{64}\"" % name.encode("ascii"),
                name.encode("ascii") + b' = "<bound>"',
                data,
                count=1,
            )
    return hashlib.sha256(data).hexdigest()


def _is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _safe_relative(path: object, root: Path = ROOT) -> bool:
    if type(path) is not str or not path or path.startswith(("/", "\\")):
        return False
    if re.match(r"^[A-Za-z]:", path) or "\\" in path or ".." in path.split("/"):
        return False
    try:
        root_resolved = root.resolve(strict=True)
        lexical = root / path
        target = lexical.resolve(strict=True)
        target.relative_to(root_resolved)
        current = root
        for component in lexical.relative_to(root).parts:
            current /= component
            info = current.lstat()
            if current.is_symlink() or _is_reparse(info):
                return False
        info = target.lstat()
        return stat.S_ISREG(info.st_mode) and getattr(info, "st_nlink", 1) == 1
    except (OSError, RuntimeError, ValueError):
        return False


def _bind(path: object, expected_sha: object, label: str, root: Path = ROOT) -> None:
    if type(expected_sha) is not str or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise ExclusionError(f"{label}:hash_shape")
    if not _safe_relative(path, root):
        raise ExclusionError(f"{label}:unsafe_path")
    target = root / path
    if _raw_sha(target) != expected_sha:
        raise ExclusionError(f"{label}:hash_drift")


def _bind_normalised(path: object, expected_sha: object, label: str) -> None:
    if type(expected_sha) is not str or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise ExclusionError(f"{label}:hash_shape")
    if not _safe_relative(path):
        raise ExclusionError(f"{label}:unsafe_path")
    if _normalised_sha(ROOT / path) != expected_sha:
        raise ExclusionError(f"{label}:hash_drift")


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    for key in tuple(env):
        if key.startswith("GIT_CONFIG_") or key in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"}:
            env.pop(key, None)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    return env


def _git(*arguments: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(
        ["git", "-c", "core.autocrlf=true", *arguments],
        cwd=ROOT,
        env=_git_env(),
        capture_output=True,
        timeout=90,
        check=False,
    )
    if result.returncode:
        raise ExclusionError("git_custody")
    return result.stdout if binary else result.stdout.decode("utf-8", errors="strict").strip()


def _row(document: dict[str, Any], row_id: str) -> dict[str, Any]:
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise ExclusionError("rows_shape")
    matches = [item for item in rows if isinstance(item, dict) and item.get("id") == row_id]
    if len(matches) != 1:
        raise ExclusionError(f"row_missing:{row_id}")
    return matches[0]


def _owner_record_expected() -> dict[str, Any]:
    return {
        "schema": OWNER_SCHEMA,
        "status": "owner_decided_historical_quarantine",
        "decision": {
            "disposition": "excluded_by_owner",
            "historical_quarantine_not_product_reachable": True,
            "parity_claim": "none",
            "release_claim": "none",
            "product_capability_claim": "none",
            "acceptance": False,
            "reason": "legacy_yfit_workflows_are_not_accepted_for_product_integration",
            "production_change": "none",
        },
        "scope": {
            "repository": "agent_spice",
            "rows": ["AS-03", "AS-04"],
            "public_entrypoints": ["fit-yparam", "tune-yparam-tran"],
            "excluded_routes_fail_closed": True,
            "no_new_domain_feature": True,
        },
        "candidate": CANDIDATE,
        "historical_evidence": {
            "AS-03": {**AS03_EVIDENCE, "disposition": "preserved_immutable_historical_only"},
            "AS-04": {**AS04_EVIDENCE, "disposition": "preserved_immutable_historical_only"},
        },
        "predecessors": {
            "ledger": {
                "path": "docs/baselines/upstream-integration-ledger.v14.yaml",
                "sha256": LEDGER_PREDECESSOR_SHA,
            },
            "inventory": {
                "path": "docs/baselines/upstream-migration-inventory.v1.yaml",
                "sha256": INVENTORY_PREDECESSOR_SHA,
            },
        },
        "successors": {
            "ledger": "docs/baselines/upstream-integration-ledger.v15.yaml",
            "inventory": "docs/baselines/upstream-migration-inventory.v2.yaml",
        },
        "invariants": {
            "AS-01": "unchanged",
            "AS-02": "unchanged",
            "AS-05": "unchanged",
            "AS-06": "unchanged",
            "s_parameter_fit": "forbidden",
            "channel_policy": "one_final_fd_to_td_impulse",
            "release_ready": False,
            "product_capability_promoted": False,
            "numerical_policy_changed": False,
        },
        "harness": {
            "verifier": {"path": "tools/verify_as03_as04_owner_exclusion.py", "sha256": _normalised_sha(VERIFIER)},
            "mutation_tests": {"path": "tools/test_verify_as03_as04_owner_exclusion.py", "sha256": _raw_sha(MUTATIONS)},
        },
    }


def _expected_ledger_row(row_id: str, predecessor: dict[str, Any]) -> dict[str, Any]:
    evidence = AS03_EVIDENCE if row_id == "AS-03" else AS04_EVIDENCE
    if row_id == "AS-03":
        reason = "legacy_yfit_not_accepted_for_product_integration"
    else:
        reason = "legacy_yfit_tran_not_accepted_for_product_integration"
    return {
        "id": row_id,
        "repo": "agent_spice",
        "public_entrypoint": "fit-yparam" if row_id == "AS-03" else "tune-yparam-tran",
        "integration_disposition": "excluded_fail_closed",
        "runtime_availability": "unavailable",
        "parity_evidence": "historical_only",
        "release_state": "excluded_no_release",
        "evidence": evidence,
        "current_observation": {
            "status": "excluded_by_owner",
            "owner_reason": reason,
            "historical_quarantine_not_product_reachable": True,
            "historical_evidence_preserved": True,
            "parity_claim": "none",
            "acceptance": False,
            "product_capability_promoted": False,
            "release_ready": False,
            "no_s_parameter_fit": True,
            "channel_policy": "one_final_fd_to_td_impulse",
        },
        "non_claims": [
            "excluded_by_owner",
            "historical_quarantine_not_product_reachable",
            "historical_only",
            "no_parity_claim",
            "no_global_parity",
            "no_product_capability_promotion",
            "no_release",
            "no_s_parameter_fit",
            "one_final_fd_to_td_impulse",
        ],
    }


def _expected_inventory_entry(row_id: str) -> dict[str, Any]:
    return {
        "id": row_id,
        "repo": "agent_spice",
        "public_entrypoint": "fit-yparam" if row_id == "AS-03" else "tune-yparam-tran",
        "source_path": "src/agent_spice/cli.py",
        "target_crates": ["sipi-touchstone", "sipi-channel"] if row_id == "AS-03" else ["sipi-channel", "sipi-tran"],
        "adapter_status": "integrated_external_cli_route",
        "rust_replacement_status": "excluded_by_owner",
        "reachable_inventory": "historical_quarantine_not_product_reachable",
        "license_review": "external_runtime_boundary_bound_direct_port_not_started",
        "oracle_corpus": "pending",
        "parity_status": "not_evaluated",
        "completion": "excluded_by_owner",
    }


def _validate_owner_record(owner: dict[str, Any]) -> None:
    _exact(owner, _owner_record_expected(), "owner_record")
    _validate_candidate(CANDIDATE, "owner:candidate")
    _bind(owner["historical_evidence"]["AS-03"]["path"], AS03_EVIDENCE["sha256"], "historical:AS-03")
    _bind(owner["historical_evidence"]["AS-04"]["path"], AS04_EVIDENCE["sha256"], "historical:AS-04")
    _bind(owner["predecessors"]["ledger"]["path"], LEDGER_PREDECESSOR_SHA, "predecessor:ledger")
    _bind(owner["predecessors"]["inventory"]["path"], INVENTORY_PREDECESSOR_SHA, "predecessor:inventory")
    _exact(owner["harness"]["verifier"]["sha256"], _normalised_sha(VERIFIER), "owner:harness:verifier")
    _exact(owner["harness"]["mutation_tests"]["sha256"], _raw_sha(MUTATIONS), "owner:harness:mutations")


def _validate_ledger(ledger: dict[str, Any], predecessor: dict[str, Any], owner: dict[str, Any]) -> None:
    expected_top = set(predecessor) | {"owner_exclusion"}
    if set(ledger) != expected_top:
        raise ExclusionError("ledger:top_keys")
    _exact(ledger["schema"], LEDGER_SCHEMA, "ledger:schema")
    _exact(ledger["status"], predecessor["status"], "ledger:status")
    _exact(
        ledger["successor"],
        {
            "predecessor": "docs/baselines/upstream-integration-ledger.v14.yaml",
            "predecessor_sha256": LEDGER_PREDECESSOR_SHA,
            "reason": "additive v15 owner-disposition successor; v1-v14 remain immutable historical ledgers",
        },
        "ledger:successor",
    )
    _exact(ledger["candidate"], CANDIDATE, "ledger:candidate")
    for key in ("policy", "allowed_values", "source_authority", "change_commits", "current_sources", "formal_records"):
        _exact(ledger[key], predecessor[key], f"ledger:preserved:{key}")
    _exact(
        ledger["owner_exclusion"],
        {
            "record": {"path": "docs/baselines/as03-as04-owner-exclusion.v1.yaml", "sha256": OWNER_RECORD_SHA},
            "audit": {"path": "docs/baselines/audits/2026-09-02-as03-as04-owner-exclusion.md", "sha256": AUDIT_SHA},
        },
        "ledger:owner_exclusion",
    )
    if type(ledger["rows"]) is not list or len(ledger["rows"]) != 15:
        raise ExclusionError("ledger:rows")
    for current, old in zip(ledger["rows"], predecessor["rows"]):
        row_id = current.get("id") if isinstance(current, dict) else None
        if row_id in {"AS-03", "AS-04"}:
            _exact(current, _expected_ledger_row(row_id, predecessor), f"ledger:row:{row_id}")
        else:
            _exact(current, old, f"ledger:row_preserved:{row_id}")
    _exact(
        ledger["summary"],
        {"rows": 15, "direct_rust_port": 9, "retained_external_runtime": 2, "external_asset": 0, "oracle_only": 0, "excluded_fail_closed": 4, "release_ready": 0},
        "ledger:summary",
    )
    _exact(ledger["plan"], {"path": "PLAN.md", "sha256": PLAN_SHA}, "ledger:plan")
    _exact(ledger["audit"], {"path": "docs/baselines/audits/2026-09-02-as03-as04-owner-exclusion.md", "sha256": AUDIT_SHA}, "ledger:audit")
    _exact(
        ledger["harness"],
        {
            "verifier": {"path": "tools/verify_as03_as04_owner_exclusion.py", "sha256": VERIFIER_SHA},
            "mutation_tests": {"path": "tools/test_verify_as03_as04_owner_exclusion.py", "sha256": MUTATION_SHA},
        },
        "ledger:harness",
    )
    _bind(ledger["plan"]["path"], PLAN_SHA, "ledger:plan_file")
    _bind(ledger["audit"]["path"], AUDIT_SHA, "ledger:audit_file")
    _bind(ledger["owner_exclusion"]["record"]["path"], OWNER_RECORD_SHA, "ledger:owner_record")
    _bind(ledger["owner_exclusion"]["audit"]["path"], AUDIT_SHA, "ledger:owner_audit")
    _bind_normalised(ledger["harness"]["verifier"]["path"], VERIFIER_SHA, "ledger:verifier")
    _bind(ledger["harness"]["mutation_tests"]["path"], MUTATION_SHA, "ledger:mutations")
    _bind(AS03_EVIDENCE["path"], AS03_EVIDENCE["sha256"], "ledger:historical:AS-03")
    _bind(AS04_EVIDENCE["path"], AS04_EVIDENCE["sha256"], "ledger:historical:AS-04")
    _validate_candidate(CANDIDATE, "ledger:candidate")
    _exact(owner, _owner_record_expected(), "ledger:owner_record_shape")


def _validate_inventory(inventory: dict[str, Any], predecessor: dict[str, Any]) -> None:
    expected_top = set(predecessor) | {"successor", "candidate", "reachable_inventory_states", "owner_exclusion", "plan"}
    if set(inventory) != expected_top:
        raise ExclusionError("inventory:top_keys")
    _exact(inventory["schema"], INVENTORY_SCHEMA, "inventory:schema")
    for key in ("status", "policy", "adr", "feature_policy", "completion_states", "integration_evidence", "source_repositories", "accounted_not_initial_numeric_completion"):
        _exact(inventory[key], predecessor[key], f"inventory:preserved:{key}")
    _exact(inventory["successor"], {"predecessor": "docs/baselines/upstream-migration-inventory.v1.yaml", "predecessor_sha256": INVENTORY_PREDECESSOR_SHA, "reason": "additive v2 owner-disposition successor; v1 remains immutable historical inventory"}, "inventory:successor")
    _exact(inventory["candidate"], CANDIDATE, "inventory:candidate")
    _exact(inventory["reachable_inventory_states"], ["pinned_reachable_inventory_bound", "historical_quarantine_not_product_reachable"], "inventory:reachable_states")
    _exact(inventory["owner_exclusion"], {"record": {"path": "docs/baselines/as03-as04-owner-exclusion.v1.yaml", "sha256": OWNER_RECORD_SHA}, "audit": {"path": "docs/baselines/audits/2026-09-02-as03-as04-owner-exclusion.md", "sha256": AUDIT_SHA}}, "inventory:owner_exclusion")
    _exact(inventory["plan"], {"path": "PLAN.md", "sha256": PLAN_SHA}, "inventory:plan")
    if type(inventory["entries"]) is not list or len(inventory["entries"]) != 15:
        raise ExclusionError("inventory:entries")
    for current, old in zip(inventory["entries"], predecessor["entries"]):
        row_id = current.get("id") if isinstance(current, dict) else None
        if row_id in {"AS-03", "AS-04"}:
            _exact(current, _expected_inventory_entry(row_id), f"inventory:entry:{row_id}")
        else:
            _exact(current, old, f"inventory:entry_preserved:{row_id}")
    _exact(inventory["summary"], {"migration_rows": 15, "external_adapter_routes_integrated": 15, "open": 13, "complete": 2, "new_feature_freeze": True}, "inventory:summary")
    _bind(inventory["integration_evidence"]["path"], inventory["integration_evidence"]["sha256"], "inventory:integration_evidence")
    _bind(inventory["plan"]["path"], PLAN_SHA, "inventory:plan_file")
    _bind(inventory["owner_exclusion"]["record"]["path"], OWNER_RECORD_SHA, "inventory:owner_record")
    _bind(inventory["owner_exclusion"]["audit"]["path"], AUDIT_SHA, "inventory:owner_audit")
    _validate_candidate(CANDIDATE, "inventory:candidate")


def _validate_candidate(candidate: dict[str, Any], label: str) -> None:
    _exact(candidate, CANDIDATE, label)
    if _git("show", "-s", "--format=%T", candidate["commit"]) != candidate["tree"]:
        raise ExclusionError(f"{label}:tree")
    archive = _git("archive", "--format=tar", candidate["commit"], binary=True)
    if len(archive) != candidate["archive_bytes"] or hashlib.sha256(archive).hexdigest() != candidate["archive_sha256"]:
        raise ExclusionError(f"{label}:archive")


def _validate_audit_text(text: str) -> None:
    for marker in (
        "AS-03/AS-04 owner exclusion audit",
        "excluded_by_owner",
        "historical_quarantine_not_product_reachable",
        "fit-yparam",
        "tune-yparam-tran",
        "ad797d8c6421c51b9607a2624cf4572c9c8b0b50",
        "d305cbfd27960926c969db9abbaeac81d8b1e988",
        "149c1162f8ba697a7d9509cb0950afff3fdad8c5977af051c6bd279b29cd1b30",
        "62,822,400",
        "parity, acceptance, product capability, or release readiness",
        "v14",
        "v1",
        "AS-01",
        "AS-02",
        "AS-05",
        "AS-06",
        "Xyce/XDM",
        "fail-closed",
        "governance disposition only",
    ):
        if marker not in text:
            raise ExclusionError(f"audit_marker:{marker}")


def _validate_audit() -> None:
    _validate_audit_text(AUDIT.read_text(encoding="utf-8"))


def validate(root: Path = ROOT) -> dict[str, Any]:
    if root.resolve() != ROOT.resolve():
        raise ExclusionError("alternate_root_not_supported")
    predecessor_ledger = _load(LEDGER_PREDECESSOR)
    predecessor_inventory = _load(INVENTORY_PREDECESSOR)
    owner = _load(RECORD)
    ledger = _load(LEDGER)
    inventory = _load(INVENTORY)
    if _raw_sha(LEDGER_PREDECESSOR) != LEDGER_PREDECESSOR_SHA:
        raise ExclusionError("ledger_predecessor_hash")
    if _raw_sha(INVENTORY_PREDECESSOR) != INVENTORY_PREDECESSOR_SHA:
        raise ExclusionError("inventory_predecessor_hash")
    if _raw_sha(PLAN) != PLAN_SHA:
        raise ExclusionError("plan_hash")
    if _raw_sha(RECORD) != OWNER_RECORD_SHA:
        raise ExclusionError("owner_record_hash")
    if _raw_sha(AUDIT) != AUDIT_SHA:
        raise ExclusionError("audit_hash")
    if _normalised_sha(VERIFIER) != VERIFIER_SHA:
        raise ExclusionError("verifier_hash")
    if _raw_sha(MUTATIONS) != MUTATION_SHA:
        raise ExclusionError("mutation_hash")
    _validate_owner_record(owner)
    _validate_ledger(ledger, predecessor_ledger, owner)
    _validate_inventory(inventory, predecessor_inventory)
    _validate_audit()
    return {
        "valid": True,
        "excluded_rows": ["AS-03", "AS-04"],
        "historical_quarantine_not_product_reachable": True,
        "parity_claim": "none",
        "release_ready": False,
        "product_capability_promoted": False,
        "unchanged_rows": ["AS-01", "AS-02", "AS-05", "AS-06"],
    }


if __name__ == "__main__":
    print(validate())
