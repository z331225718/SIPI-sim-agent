"""Strict additive verifier for upstream integration ledger v14."""

from __future__ import annotations

import copy
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
LEDGER = ROOT / "docs/baselines/upstream-integration-ledger.v14.yaml"
PREDECESSOR = ROOT / "docs/baselines/upstream-integration-ledger.v13.yaml"
PREDECESSOR_SHA = "37f62bc82cb20da36c96485e335e63e50e47e42166077ccd35ad6de2a7cd76a6"
CANDIDATE = {"commit": "beb5b764f471ec4c9cda81dc233ac1a3d984669e", "tree": "18ff08dee5b7a11da3120b7542354b0709f19275", "archive_sha256": "b97253c6338603306f9a405c5b1e02d1df73ac17d16260ab27ddb7569426b3f5", "archive_bytes": 56391680, "materialization": "clean_git_archive", "autocrlf": True, "worktree_overlay": False}
PLAN = {"path": "PLAN.md", "sha256": "25d15b3a7b4c271585efc3318b728ff2b623a0a5d9c1b4069b9b001408d0cb6a"}
AUDIT = {"path": "docs/baselines/audits/2026-08-29-upstream-integration-ledger-v14.md", "sha256": "6aff0cf3f16dcc256983bcd4542069a39c1865c3cafc021b576b0b99c1ef40ee"}
VERIFIER_SHA = "0b9bfe0ca73d7e24a340e77bff5bbc250d8a262859c7dd6cd97d9bfff7a81c7f"
MUTATION_SHA = "6e71ec7672bc0c6fe6f24a6998f16ab3a42d263076fd463c172b3948368818c2"

FORMAL = {
    "as06": {"manifest": {"path": "docs/baselines/as-06-ngspice-result-parity.v2.yaml", "sha256": "327a1690755dbde76698a9aa7f8cb9705bf1f1902b5161185fb2bfaf210ae0b9"}, "audit": {"path": "docs/baselines/audits/2026-08-29-as-06-ngspice-result-parity-v2.md", "sha256": "a025727ecec1ac7479cbb2260df10a1c538e6d389ae08cd1c1dc973562cf7bfb"}, "gate": {"commit": "591a2563179713a97a7b2346597a986f42bb1af9", "tree": "0d6c50580cd7acd5321768f98e04776677882db0"}, "record": {"commit": "1e2f1be2d9be730ca38cf21ce8393de02c295f6a", "tree": "2bd39e64b193e79cd0a57eea0d33e06bbe54f383"}},
    "com02_04": {"manifest": {"path": "docs/baselines/com-02-04-result-surface-formal.v1.yaml", "sha256": "74a3dba2a02f31306db776a9ceb31acb19ad0b9eb668fdb9fe5cf8da88cab951"}, "audit": {"path": "docs/baselines/audits/2026-08-29-com-02-04-result-surface-formal.md", "sha256": "7f4cc983f9e8a2a0e441176bed180a39837e3541986cc35494c1e009ea66e495"}, "gate": {"commit": "e5d9bfe5fa946ee88b9eb06df1db3b574dd43c05", "tree": "2906da5e5c7d6169ba1f01493e2d6a3231595aac"}, "record": {"commit": "2dea3bbe6039224704f1e07aebc3ebd6c178abed", "tree": "2d680777f93c86373104c9b294cc833e28ea1cba"}},
    "pb01_02": {"manifest": {"path": "docs/baselines/pb-01-02-candidate-matrix-formal.v1.yaml", "sha256": "1046da4884fa2cd533ee9ecf119500177e378dfaec33d2afd94c2ce05184b297"}, "audit": {"path": "docs/baselines/audits/2026-08-29-pb-01-02-candidate-matrix-formal.md", "sha256": "508cb84aeabc3999d67baec832a593e9a1ef163b48a32622bd98117e8b548a5f"}, "gate": {"commit": "b738e983a430f98b04da066f3e9c42b8f3ee58e6", "tree": "2abea453b906e2efdbfcbae99f0ccc98893ce83c"}, "record": {"commit": CANDIDATE["commit"], "tree": CANDIDATE["tree"]}},
}

class LedgerError(RuntimeError): pass

class StrictLoader(yaml.SafeLoader): pass
def strict_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result: raise LedgerError("duplicate key")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result
StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, strict_mapping)

def finite(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value): raise LedgerError("nonfinite")
    if isinstance(value, dict):
        for key, child in value.items():
            if type(key) is not str: raise LedgerError("non-string key")
            finite(child)
    elif isinstance(value, list):
        for child in value: finite(child)

def sha(path: Path, root: Path = ROOT) -> str:
    data = path.read_bytes()
    if path.resolve() == (root / "tools/verify_upstream_integration_ledger_v14.py").resolve():
        data = re.sub(rb'VERIFIER_SHA = "[0-9a-f]{64}"', b'VERIFIER_SHA = "<self>"', data, count=1)
        data = re.sub(rb'MUTATION_SHA = "[0-9a-f]{64}"', b'MUTATION_SHA = "<mutation>"', data, count=1)
    if path.resolve() == (root / "tools/test_verify_upstream_integration_ledger_v14.py").resolve():
        data = re.sub(rb'EXPECTED_VERIFIER_SHA = "[0-9a-f]{64}"', b'EXPECTED_VERIFIER_SHA = "<verifier>"', data, count=1)
    return hashlib.sha256(data).hexdigest()

def exact(actual: Any, expected: Any, label: str) -> None:
    if type(actual) is not type(expected): raise LedgerError(label + ":type")
    if isinstance(expected, dict):
        if set(actual) != set(expected): raise LedgerError(label + ":keys")
        for key in expected: exact(actual[key], expected[key], label + ":" + str(key))
    elif isinstance(expected, list):
        if len(actual) != len(expected): raise LedgerError(label + ":length")
        for index, item in enumerate(expected): exact(actual[index], item, label + f":{index}")
    elif actual != expected: raise LedgerError(label + ":value")

def row(document: dict, row_id: str) -> dict:
    return next(item for item in document["rows"] if item["id"] == row_id)

def expected_document() -> dict:
    if hashlib.sha256(PREDECESSOR.read_bytes()).hexdigest() != PREDECESSOR_SHA: raise LedgerError("predecessor")
    document = yaml.load(PREDECESSOR.read_text(encoding="utf-8"), Loader=StrictLoader)
    finite(document)
    document["schema"] = "sipi.upstream-integration-ledger.v14"
    document["successor"] = {"predecessor": "docs/baselines/upstream-integration-ledger.v13.yaml", "predecessor_sha256": PREDECESSOR_SHA, "reason": "additive v14 successor; v1-v13 remain immutable historical ledgers"}
    document["candidate"] = CANDIDATE
    document["formal_records"] = FORMAL
    document["change_commits"].update({"as06_scoped_external_record": FORMAL["as06"]["record"]["commit"], "com02_04_result_surface_record": FORMAL["com02_04"]["record"]["commit"], "pb01_02_candidate_matrix_record": FORMAL["pb01_02"]["record"]["commit"]})
    document["current_sources"].update({"as06_formal": FORMAL["as06"]["manifest"], "com02_04_formal": FORMAL["com02_04"]["manifest"], "pb01_02_formal": FORMAL["pb01_02"]["manifest"]})
    observations = {
        "AS-06": {"formal_record": "as06", "status": "passed_scoped_external_observation", "external_solver_observed": True, "solver_correctness": False, "acceptance": False, "release_ready": False, "s_parameter_fit": False, "as05_xyce_xdm": False},
        "COM-02": {"formal_record": "com02_04", "status": "passed_scoped", "dfe_winner_taps_published": True, "configured_port_order_execution_observed": True, "upstream_numeric_parity": False, "port_order_result_wire": False, "acceptance": False, "release_ready": False, "channel_policy": "one_final_fd_to_td_impulse"},
        "COM-04": {"formal_record": "com02_04", "status": "passed_scoped", "dfe_winner_taps_published": True, "configured_port_order_execution_observed": True, "upstream_numeric_parity": False, "port_order_result_wire": False, "acceptance": False, "release_ready": False, "channel_policy": "one_final_fd_to_td_impulse"},
        "PB-01": {"formal_record": "pb01_02", "status": "blocked_scoped", "duobinary_selected_array_parity": True, "scope": "selected_arrays_only", "whole_payload_parity": False, "acceptance": False, "release_ready": False},
        "PB-02": {"formal_record": "pb01_02", "status": "blocked", "blocker_count": 13, "complete_typed_output_parity": False, "acceptance": False, "release_ready": False},
    }
    nonclaims = {
        "AS-06": ["scoped_external_observation_only", "no_solver_correctness", "no_acceptance", "no_release", "no_s_parameter_fit", "no_as05_xyce_xdm"],
        "COM-02": ["scoped_result_surface_only", "no_upstream_numeric_parity", "no_port_order_result_wire", "no_acceptance", "no_release", "no_s_parameter_fit", "one_final_fd_to_td_impulse"],
        "COM-04": ["scoped_result_surface_only", "no_upstream_numeric_parity", "no_port_order_result_wire", "no_acceptance", "no_release", "no_s_parameter_fit", "one_final_fd_to_td_impulse"],
        "PB-01": ["duobinary_selected_arrays_only", "no_whole_payload_parity", "no_acceptance", "no_release"],
        "PB-02": ["thirteen_blockers_open", "complete_typed_output_false", "no_acceptance", "no_release"],
    }
    for row_id, observation in observations.items():
        item = row(document, row_id); item["evidence"] = FORMAL[observation["formal_record"]]["manifest"]; item["current_observation"] = observation; item["non_claims"] = nonclaims[row_id]
        if row_id in ("COM-02", "COM-04"): item["parity_evidence"] = "scoped_observation"
    document["plan"] = PLAN; document["audit"] = AUDIT
    document["harness"] = {"verifier": {"path": "tools/verify_upstream_integration_ledger_v14.py", "sha256": VERIFIER_SHA}, "mutation_tests": {"path": "tools/test_verify_upstream_integration_ledger_v14.py", "sha256": MUTATION_SHA}}
    return document

def is_reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))

def safe(path: object, root: Path = ROOT) -> bool:
    if type(path) is not str or not path or path.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", path) or "\\" in path or ".." in path.split("/"): return False
    try:
        resolved_root = root.resolve(strict=True); lexical = root / path; target = lexical.resolve(strict=True); target.relative_to(resolved_root)
        current = root
        for component in lexical.relative_to(root).parts:
            current /= component; info = current.lstat()
            if current.is_symlink() or is_reparse(info): return False
        info = target.lstat()
        return stat.S_ISREG(info.st_mode) and getattr(info, "st_nlink", 1) == 1
    except (OSError, RuntimeError, ValueError): return False

def bind(binding: dict, root: Path) -> None:
    path = binding["path"]
    if set(binding) != {"path", "sha256"} or not safe(path, root): raise LedgerError("unsafe path")
    target = root / path
    if not target.is_file() or sha(target, root) != binding["sha256"]: raise LedgerError("binding:" + path)

def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=30, check=False)
    if result.returncode: raise LedgerError("git custody")
    return result.stdout

def validate(document: dict, root: Path = ROOT) -> dict:
    finite(document)
    exact(document, expected_document(), "ledger")
    if len(document["rows"]) != 15 or document["summary"]["rows"] != 15 or document["summary"]["release_ready"] != 0: raise LedgerError("summary")
    if any(item["release_state"] not in ("open_no_release", "scoped_only_no_release", "excluded_no_release") for item in document["rows"]): raise LedgerError("promotion")
    if document["policy"]["s_parameter_fit"] != "forbidden" or document["policy"]["channel_policy"] != "one_final_fd_to_td_impulse": raise LedgerError("policy")
    as05 = row(document, "AS-05")["current_observation"]
    if as05["owner_decision"] != "owner_excluded_not_required" or as05["xyce_xdm_extension"] != "no_xyce_xdm_extension": raise LedgerError("as05")
    for record in document["formal_records"].values():
        bind(record["manifest"], root); bind(record["audit"], root)
        for section in ("gate", "record"):
            if git(root, "show", "-s", "--format=%T", record[section]["commit"]).decode().strip() != record[section]["tree"]: raise LedgerError("formal tree")
        if git(root, "show", "-s", "--format=%P", record["record"]["commit"]).decode().strip() != record["gate"]["commit"]: raise LedgerError("formal parent")
    if git(root, "show", "-s", "--format=%T", CANDIDATE["commit"]).decode().strip() != CANDIDATE["tree"]: raise LedgerError("candidate tree")
    archive = git(root, "archive", "--format=tar", CANDIDATE["commit"])
    if len(archive) != CANDIDATE["archive_bytes"] or hashlib.sha256(archive).hexdigest() != CANDIDATE["archive_sha256"]: raise LedgerError("candidate archive")
    bind(document["plan"], root); bind(document["audit"], root); bind(document["harness"]["verifier"], root); bind(document["harness"]["mutation_tests"], root)
    audit_text = (root / AUDIT["path"]).read_text(encoding="utf-8")
    for key, record in FORMAL.items():
        marker = f"RECIPROCAL {key.upper()} {record['gate']['commit']} {record['record']['commit']} {record['manifest']['sha256']}"
        if audit_text.count(marker) != 1: raise LedgerError("audit reciprocal:" + key)
    return {"valid": True, "rows": 15, "release_ready": 0}

def load() -> dict:
    document = yaml.load(LEDGER.read_text(encoding="utf-8"), Loader=StrictLoader); finite(document); return document
def main() -> int:
    print(validate(load()))
    return 0
if __name__ == "__main__": raise SystemExit(main())
