"""Strict gate for the additive COM workbook/ACCM formal observation bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import yaml
except ImportError as exc:  # pragma: no cover - environment contract
    raise RuntimeError("PyYAML is required for the formal evidence gate") from exc

try:
    from .aggregate_com_workbook_accm_replay_v1 import aggregate
    from .verify_com_workbook_accm_replay_v1 import verify_aggregate
except ImportError:
    from aggregate_com_workbook_accm_replay_v1 import aggregate
    from verify_com_workbook_accm_replay_v1 import verify_aggregate

HEX64 = re.compile(r"^[0-9a-f]{64}$")
RUN_ID = HEX64
REPORT_NAMES = {"run1", "run2"}
AUDIT_SCHEMA = "sipi.com.workbook-accm-replay-audit.v1"
NON_CLAIMS = [
    "no upstream numeric parity",
    "no global or product parity",
    "no release or promotion claim",
    "no S-parameter fit",
    "channel uses one final FD-to-TD impulse",
    "PDB is opaque environment-local debug custody and nonpublish",
]
HARD_RUNS = [
    {"slot": "run1", "path": "docs/baselines/com-workbook-accm-replay-run1.json", "bytes": 3076299, "sha256": "ce2c4545d8455718005d584874b655a544e36e086d8a33788561e3956f72e38f", "run_id": "c4a8b21f73d94d4a9f7e5c2a1b8d604e3f9a7c1d2e6b5f8093a4c7d1e2f6b8a0", "nonce": "5ca58726f0e2a3ed5d0fe1d315d93dad0c1b6b7edaedd176bb74c4670e5a078e", "binary_sha256": "e18fe30d784584d55cd6d9edff2380ada3953c526c0ff02c17dd8bc6e4bc44a9", "pdb_sha256": "6ee7189245a279e1b826b727023295895b25fce61efdb593a48f4d03af76a741"},
    {"slot": "run2", "path": "docs/baselines/com-workbook-accm-replay-run2.json", "bytes": 3076299, "sha256": "09514f59f49ec4d03d02f0e4634bc989aa1034225e86e427de99fe3cfbd58af6", "run_id": "c4e4b8d48f54c5369ed959f19d85c76f9dd3dbfc466f686ab0fbe3fc52371d5f", "nonce": "7eeb1a2de18fcf44c24fd8e761413eead44832ae11da1e7efd1e9e088748fd7f", "binary_sha256": "53ca2966947dd4cb8c8c1b6c7833562cce95af3e3bd4de8eb5e4b2c9e6781a71", "pdb_sha256": "23af58de99abb83685b0a054b3b1c94c4dc1911f24b3bc2e6942300bea869c02"},
]
HARD_AGGREGATE = {"path": "docs/baselines/com-workbook-accm-replay-aggregate.json", "bytes": 18889, "sha256": "805ebf00656a24057cff4ae389369f23eb78faf2b571deb25f1df8ba9c9143a4"}
HARD_ARTIFACTS = [
    {"path": "docs/baselines/com-workbook-accm-replay-run1-metrics-0.json", "bytes": 787, "sha256": "621057554ca63dd9211f89c19be5750f99008acc346a3219cf5389cd195dea65"},
    {"path": "docs/baselines/com-workbook-accm-replay-run1-metrics-1.json", "bytes": 791, "sha256": "23b794400331a3f8fbc2f0207ea22a5176c1ff683362496946f66155d29fd089"},
    {"path": "docs/baselines/com-workbook-accm-replay-run2-metrics-0.json", "bytes": 787, "sha256": "621057554ca63dd9211f89c19be5750f99008acc346a3219cf5389cd195dea65"},
    {"path": "docs/baselines/com-workbook-accm-replay-run2-metrics-1.json", "bytes": 791, "sha256": "23b794400331a3f8fbc2f0207ea22a5176c1ff683362496946f66155d29fd089"},
]
HARD_AUDIT = {"path": "docs/baselines/com-workbook-accm-replay-v4.audit.yaml", "sha256": "47163ec41a37209de7c2168c6f9baf7628cd59160582858f750bd08c8887ad2c"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(message: str) -> None:
    raise ValueError(message)


def safe_repo_path(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str):
        fail(f"{label} must be a string")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in path.parts) or ":" in path.parts[0]:
        fail(f"{label} is not a safe repo-relative path")
    return path


def sha_entry(value: Any, label: str) -> None:
    if not isinstance(value, str) or not HEX64.fullmatch(value):
        fail(f"{label} must be lowercase SHA256")


def exact_keys(value: Any, keys: set[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        fail(f"{label} key set drift")


def physical(root: Path, item: dict[str, Any], label: str) -> Path:
    if not isinstance(item, dict) or not isinstance(item.get("path"), str):
        fail(f"{label} physical entry malformed")
    relative = safe_repo_path(item["path"], f"{label}.path")
    path = (root / Path(*relative.parts)).resolve()
    if root.resolve() not in path.parents and path != root.resolve():
        fail(f"{label} escapes repository")
    if not path.is_file() or path.is_symlink():
        fail(f"{label} is missing or non-regular")
    if not isinstance(item.get("bytes"), int) or isinstance(item["bytes"], bool) or item["bytes"] != path.stat().st_size:
        fail(f"{label} byte count drift")
    sha_entry(item.get("sha256"), f"{label}.sha256")
    if item["sha256"] != digest(path):
        fail(f"{label} hash drift")
    return path


def git_output(repo: Path, *args: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.STDOUT, timeout=60).decode("ascii").strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        fail(f"Git provenance command failed: {exc}")


def git_archive_identity(repo: Path, commit: str) -> tuple[int, str]:
    try:
        payload = subprocess.check_output(["git", "-C", str(repo), "-c", "core.autocrlf=false", "archive", "--format=tar", commit], timeout=120)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        fail(f"Git archive failed: {exc}")
    return len(payload), hashlib.sha256(payload).hexdigest()


def verify_git_anchors(repo_root: Path, upstream_repo: Path, data: dict[str, Any]) -> None:
    prep = data["prep"]; candidate = data["candidate"]; upstream = data["upstream"]
    if git_output(repo_root, "rev-parse", prep["commit"]) != prep["commit"] or git_output(repo_root, "rev-parse", f"{prep['commit']}^{{tree}}") != prep["tree"]:
        fail("prep Git commit/tree mismatch")
    if git_output(repo_root, "rev-parse", candidate["commit"]) != candidate["commit"] or git_output(repo_root, "rev-parse", f"{candidate['commit']}^{{tree}}") != candidate["tree"]:
        fail("candidate Git commit/tree mismatch")
    if git_archive_identity(repo_root, prep["commit"]) != (prep["archive"]["bytes"], prep["archive"]["sha256"]):
        fail("prep archive physical identity mismatch")
    if git_archive_identity(repo_root, candidate["commit"]) != (candidate["archive_bytes"], candidate["archive_sha256"]):
        fail("candidate archive physical identity mismatch")
    for role, item in data["tools"].items():
        if git_output(repo_root, "rev-parse", f"{prep['commit']}:{item['path']}") != item["git_blob_sha1"]:
            fail(f"prep tool Git blob mismatch: {role}")
        if digest((repo_root / Path(*safe_repo_path(item["path"], role).parts)).resolve()) != item["sha256"]:
            fail(f"prep tool worktree bytes mismatch: {role}")
    if git_output(upstream_repo, "rev-parse", upstream["commit"]) != upstream["commit"] or git_output(upstream_repo, "rev-parse", f"{upstream['commit']}^{{tree}}") != upstream["tree"]:
        fail("upstream Git commit/tree mismatch")
    for key in ("workbook", "s4p"):
        item = upstream[key]
        try:
            payload = subprocess.check_output(["git", "-C", str(upstream_repo), "show", f"{upstream['commit']}:{item['path']}"], timeout=60)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            fail(f"upstream fixture Git object failed: {exc}")
        if len(payload) != item["bytes"] or hashlib.sha256(payload).hexdigest() != item["sha256"] or git_output(upstream_repo, "rev-parse", f"{upstream['commit']}:{item['path']}") != item["blob"]:
            fail(f"upstream fixture anchor mismatch: {key}")


def verify_hard_payload_graph(root: Path, data: dict[str, Any], audit: dict[str, Any], report_paths: list[Path]) -> None:
    if data["runs"] != [{"slot": item["slot"], "report": {"path": item["path"], "bytes": item["bytes"], "sha256": item["sha256"], "run_id": item["run_id"], "nonce": item["nonce"]}, "binary_sha256": item["binary_sha256"], "pdb_sha256": item["pdb_sha256"]} for item in HARD_RUNS]:
        fail("hard report manifest anchor drift")
    if data["aggregate"] != {**HARD_AGGREGATE, "status": "numeric_observation"}:
        fail("hard aggregate anchor drift")
    if data["audit"] != HARD_AUDIT["path"] or data["audit_sha256"] != HARD_AUDIT["sha256"]:
        fail("hard audit anchor drift")
    if data["artifacts"] != HARD_ARTIFACTS:
        fail("hard sidecar artifact anchor drift")
    actual_artifacts: list[dict[str, Any]] = []
    report_values = []
    for index, path in enumerate(report_paths):
        value = json.loads(path.read_text(encoding="utf-8")); report_values.append(value)
        if value["run_id"] != HARD_RUNS[index]["run_id"] or value["nonce"] != HARD_RUNS[index]["nonce"] or value["candidate"]["binary"]["sha256"] != HARD_RUNS[index]["binary_sha256"] or value["candidate"]["binary_custody"]["post"]["pdb"]["sha256"] != HARD_RUNS[index]["pdb_sha256"]:
            fail("hard report payload identity drift")
        for run_index, run in enumerate(value["runs"]):
            artifact = run["artifact"]
            relative = f"docs/baselines/{artifact['path']}"
            actual_artifacts.append({"path": relative, "bytes": artifact["bytes"], "sha256": artifact["sha256"]})
            if artifact["raw_bytes"] <= 0 or not HEX64.fullmatch(artifact["raw_sha256"]):
                fail("artifact raw receipt drift")
            sidecar = json.loads((root / Path(*safe_repo_path(relative, "sidecar").parts)).read_text(encoding="utf-8"))
            for case in sidecar["cases"]:
                exact_keys(case, {"ac_cm_rms", "case_id", "case_index", "metrics", "package_case_index"}, "sidecar case")
                key = str(case["case_index"])
                if case["ac_cm_rms"] != run["control_vector"][case["case_index"]] or case["package_case_index"] != case["case_index"] or case["metrics"] != run["final_metrics"][key]:
                    fail("sidecar metrics do not derive from report")
            if artifact["case_metrics"] != run["final_metrics"]:
                fail("report and sidecar metric graph drift")
    if actual_artifacts != HARD_ARTIFACTS:
        fail("report artifact substitution or ordering drift")
    audit_result = audit["result"]
    zero = report_values[0]["runs"][0]["final_metrics"]["1"]
    nonzero = report_values[0]["runs"][1]["final_metrics"]["1"]
    if audit_result["case1_zero"] != zero or audit_result["case1_nonzero"] != nonzero or audit_result["case1_change_observed"] is not True:
        fail("audit metrics are not mechanically derived")


def validate_manifest_data(data: dict[str, Any], manifest_path: Path, repo_root: Path, cargo_home: Path | None = None, upstream_repo: Path | None = None) -> dict[str, Any]:
    exact_keys(data, {"schema", "mode", "status", "matched", "acceptance", "non_claims", "prep", "candidate", "upstream", "tools", "fixed_inputs", "runs", "aggregate", "artifacts", "audit", "audit_sha256", "formal_gate"}, "manifest")
    if data.get("schema") != "sipi.com.workbook-accm-replay-evidence-manifest.v1":
        fail("formal manifest schema drift")
    if data.get("mode") != "bounded_observation" or data.get("status") != "numeric_observation" or data.get("matched") is not False or data.get("acceptance") is not False:
        fail("formal promotion gate drift")
    if data.get("non_claims") != NON_CLAIMS:
        fail("formal non-claims drift")
    prep = data.get("prep")
    exact_keys(prep, {"commit", "tree", "archive"}, "prep")
    exact_keys(prep.get("archive"), {"command", "bytes", "sha256"}, "prep archive")
    if not isinstance(prep, dict) or prep.get("commit") == "HEAD" or not re.fullmatch(r"[0-9a-f]{40}", str(prep.get("commit", ""))) or not re.fullmatch(r"[0-9a-f]{40}", str(prep.get("tree", ""))):
        fail("prep identity drift")
    if "HEAD" in str(prep["archive"].get("command", "")) or prep["archive"].get("command") != "git -c core.autocrlf=false archive --format=tar 6449a014e42ae8d449a330dd788bb134f4261691" or prep["archive"].get("bytes") != 44677120:
        fail("prep archive binding drift")
    sha_entry(prep["archive"].get("sha256"), "prep archive sha")
    if prep["archive"]["sha256"] != "c419d20d245ed53344047230197fb561c8567bc74f83d4aa7ddadf5528269de4":
        fail("prep archive hash anchor drift")
    candidate = data.get("candidate", {})
    upstream = data.get("upstream", {})
    exact_keys(candidate, {"commit", "tree", "archive_sha256", "archive_bytes"}, "candidate")
    exact_keys(upstream, {"commit", "tree", "runtime", "workbook", "s4p"}, "upstream")
    if candidate.get("commit") != "2e18a6a27cf8abc0555e24e0346a54c4ea577baf" or candidate.get("tree") != "bfdc3e0ddd9bc76737528011e6dddc94c728f059":
        fail("candidate identity drift")
    if candidate.get("archive_bytes") != 44615680 or candidate.get("archive_sha256") != "67b071cf9302d932ed2b974db3c7d82cb1e70c4b7f0dac276d788b88f1a64993":
        fail("candidate archive anchor drift")
    if upstream.get("commit") != "5272ffe74702cd585054d975559b06f8afae7b6e" or upstream.get("tree") != "7094ab6e84989b218730c52432c70da10261f8ea" or upstream.get("runtime") != "not_executed_external_only":
        fail("upstream identity drift")
    exact_keys(upstream["workbook"], {"path", "blob", "bytes", "sha256"}, "upstream workbook")
    exact_keys(upstream["s4p"], {"path", "blob", "bytes", "sha256"}, "upstream s4p")
    if upstream["workbook"] != {"path": "matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120F_C2C_08_17_2022.xlsx", "blob": "22b633b6092b4b0de0ca89273515329b362eabae", "bytes": 67087, "sha256": "e676b3fb3cb3048f80c98deaa8faca1d03c13daa216c6259de26885e715ca925"} or upstream["s4p"] != {"path": "fixtures/synthetic/kappa_asymmetric_reflective_10db_at_26p56ghz.s4p", "blob": "a1fe8618043b31f63dfb24454ac1d296000010c0", "bytes": 6457063, "sha256": "3a563543ba664fcc04c1ac5603ad305cb0b1d110c3d9020727444b1c3fd2d0ec"}:
        fail("upstream fixture anchor drift")
    fixed = data.get("fixed_inputs", {})
    exact_keys(fixed, {"cargo_home", "cargo_inventory", "controls", "typed_pe"}, "fixed inputs")
    cargo = fixed.get("cargo_home")
    if cargo != {"role": "fixed_external_cargo_home", "basename": "sipi-cargo-home-v1", "path_redacted": True}:
        fail("cargo home privacy binding drift")
    inventory = fixed.get("cargo_inventory", {})
    if inventory != {"count": 7727, "total_bytes": 234108979, "sha256": "d841c89ca7eef7018c6be0bf622cb55df079bd3cc39e7d15b9d802dd7f694c3f"}:
        fail("cargo inventory anchor drift")
    pe = fixed.get("typed_pe", {})
    exact_keys(pe, {"canonical_sha256", "machine", "optional_magic", "codeview_rva", "codeview_raw_pointer", "codeview_bytes", "debug_directory_raw_pointer", "normalization_map"}, "typed PE")
    if pe.get("canonical_sha256") != "d6b133d9ca509c19c7ee112634d534b7d8b1c6e9d579255ff22de0ee46c56e87" or pe.get("machine") != 34404 or pe.get("optional_magic") != 523 or pe.get("codeview_rva") != 5893908 or pe.get("codeview_raw_pointer") != 5888788 or pe.get("codeview_bytes") != 48 or pe.get("debug_directory_raw_pointer") != 5888732:
        fail("typed PE anchor drift")
    if pe.get("normalization_map") != [{"role": "coff_timestamp", "offset": 128, "bytes": 4}, {"role": "debug_timestamp", "offset": 5888736, "bytes": 4}, {"role": "rsds_guid", "offset": 5888792, "bytes": 16}, {"role": "debug_timestamp", "offset": 5888764, "bytes": 4}, {"role": "pe_checksum", "offset": 208, "bytes": 4}]:
        fail("typed PE normalization drift")
    controls = fixed["controls"]
    exact_keys(controls, {"vectors", "no_sparam_fit", "channel_policy"}, "fixed controls")
    if controls != {"vectors": [[0.0, 0.0], [0.0, 0.001]], "no_sparam_fit": True, "channel_policy": "single_fd_to_td_impulse"}:
        fail("typed controls drift")
    tools = data.get("tools", {})
    exact_keys(tools, {"runner", "aggregate", "verifier", "tests"}, "prep tools")
    for role in ("runner", "aggregate", "verifier", "tests"):
        item = tools.get(role)
        exact_keys(item, {"path", "bytes", "git_blob_sha1", "sha256"}, f"tool.{role}")
        if not re.fullmatch(r"[0-9a-f]{40}", str(item["git_blob_sha1"])):
            fail(f"tool.{role} Git blob drift")
        physical(repo_root, item, f"tool.{role}")
    gate = data.get("formal_gate", {})
    exact_keys(gate, {"verifier", "tests"}, "formal gate")
    for role in ("verifier", "tests"):
        exact_keys(gate.get(role), {"path", "bytes", "sha256"}, f"formal gate.{role}")
        physical(repo_root, gate.get(role), f"formal_gate.{role}")
    audit_item = data.get("audit")
    audit_path = safe_repo_path(audit_item, "audit")
    audit_file = (repo_root / Path(*audit_path.parts)).resolve()
    if not audit_file.is_file() or audit_file.is_symlink():
        fail("audit missing")
    if not isinstance(data.get("audit_sha256"), str) or data["audit_sha256"] != digest(audit_file):
        fail("audit physical hash drift")
    audit = yaml.safe_load(audit_file.read_text(encoding="utf-8"))
    exact_keys(audit, {"schema", "manifest", "evidence", "result", "provenance", "claims", "non_claims", "validation"}, "audit")
    if audit.get("schema") != AUDIT_SCHEMA or audit.get("manifest") != {"path": manifest_path.relative_to(repo_root).as_posix(), "schema": data["schema"]}:
        fail("audit manifest binding drift")
    audit_evidence = audit.get("evidence", {})
    exact_keys(audit_evidence, {"reports", "aggregate", "report_run_ids", "report_nonces"}, "audit evidence")
    reports = data.get("runs")
    if not isinstance(reports, list) or len(reports) != 2 or [item.get("slot") for item in reports] != ["run1", "run2"]:
        fail("run slots drift")
    seen_ids: set[str] = set()
    seen_nonces: set[str] = set()
    report_paths: list[Path] = []
    for item in reports:
        if not isinstance(item, dict) or item.get("slot") not in REPORT_NAMES:
            fail("run entry malformed")
        exact_keys(item, {"slot", "report", "binary_sha256", "pdb_sha256"}, f"{item.get('slot', 'run')}")
        report_meta = item.get("report")
        exact_keys(report_meta, {"path", "bytes", "sha256", "run_id", "nonce"}, f"{item.get('slot', 'run')}.report")
        if not isinstance(report_meta, dict) or not RUN_ID.fullmatch(str(report_meta.get("run_id", ""))) or report_meta["run_id"] in seen_ids:
            fail("run id drift")
        sha_entry(report_meta.get("nonce"), "run nonce")
        if report_meta["nonce"] in seen_nonces:
            fail("nonce drift")
        seen_ids.add(report_meta["run_id"]); seen_nonces.add(report_meta["nonce"])
        report_path = physical(repo_root, report_meta, f"{item['slot']}.report")
        report_value = json.loads(report_path.read_text(encoding="utf-8"))
        if report_value["candidate"]["binary"]["sha256"] != item["binary_sha256"] or report_value["candidate"]["binary_custody"]["post"]["pdb"]["sha256"] != item["pdb_sha256"]:
            fail(f"{item['slot']} binary custody cross-bind drift")
        report_paths.append(report_path)
    exact_keys(data.get("aggregate"), {"path", "bytes", "sha256", "status"}, "aggregate")
    aggregate_path = physical(repo_root, data.get("aggregate"), "aggregate")
    if data["aggregate"]["status"] != "numeric_observation":
        fail("aggregate status promotion")
    artifacts = data.get("artifacts", [])
    if not isinstance(artifacts, list):
        fail("metrics artifact list malformed")
    artifact_paths = []
    for item in artifacts:
        exact_keys(item, {"path", "bytes", "sha256"}, "metrics artifact")
        artifact_paths.append(physical(repo_root, item, "metrics artifact"))
    if len(artifact_paths) != 4 or len({str(item) for item in artifact_paths}) != 4:
        fail("metrics artifact set drift")
    audit_reports = audit_evidence.get("reports", [])
    if len(audit_reports) != 2:
        fail("audit report count drift")
    for index, entry in enumerate(audit_reports):
        exact_keys(entry, {"slot", "path", "sha256"}, "audit report")
        if entry["slot"] != reports[index]["slot"] or entry["path"] != reports[index]["report"]["path"] or entry["sha256"] != reports[index]["report"]["sha256"]:
            fail("audit report binding drift")
    if audit_evidence["report_run_ids"] != [item["report"]["run_id"] for item in reports] or audit_evidence["report_nonces"] != [item["report"]["nonce"] for item in reports]:
        fail("audit run identity drift")
    exact_keys(audit_evidence["aggregate"], {"path", "sha256"}, "audit aggregate")
    if audit_evidence["aggregate"] != {"path": data["aggregate"]["path"], "sha256": data["aggregate"]["sha256"]}:
        fail("audit aggregate binding drift")
    if [entry.get("path") for entry in audit_reports] != [item["report"]["path"] for item in reports]:
        fail("audit report slots drift")
    if audit_evidence.get("aggregate", {}).get("path") != data["aggregate"]["path"]:
        fail("audit aggregate path drift")
    # Composition: strict report schemas plus a fresh mechanical aggregate.
    verify_aggregate(report_paths[0], report_paths[1], aggregate_path, cargo_home)
    with tempfile.TemporaryDirectory() as directory:
        expected = aggregate(report_paths[0], report_paths[1], Path(directory) / "aggregate.json", cargo_home)
    actual = json.loads(aggregate_path.read_text(encoding="utf-8"))
    if actual != expected:
        fail("aggregate is not mechanically regenerated")
    exact_keys(audit["result"], {"run_status", "aggregate_status", "matched", "acceptance", "case1_change_observed", "case1_zero", "case1_nonzero"}, "audit result")
    if audit["result"] != {"run_status": ["matched", "matched"], "aggregate_status": "numeric_observation", "matched": False, "acceptance": False, "case1_change_observed": True, "case1_zero": {"FOM_dB": -5.923929842338543, "COM_dB": -16.920553507287572, "sigma_N_V": 0.0005459541505382412}, "case1_nonzero": {"FOM_dB": -5.924024023908052, "COM_dB": -16.920553507287572, "sigma_N_V": 0.0005459801246444031}}:
        fail("audit result or metric drift")
    exact_keys(audit["provenance"], {"prep_commit", "candidate_commit", "upstream_commit", "cargo_inventory_sha256", "pe_canonical_sha256"}, "audit provenance")
    if audit["provenance"] != {"prep_commit": data["prep"]["commit"], "candidate_commit": data["candidate"]["commit"], "upstream_commit": data["upstream"]["commit"], "cargo_inventory_sha256": data["fixed_inputs"]["cargo_inventory"]["sha256"], "pe_canonical_sha256": data["fixed_inputs"]["typed_pe"]["canonical_sha256"]}:
        fail("audit provenance drift")
    if audit["claims"] != ["bounded clean-archive candidate observation only", "pinned workbook and S4P bytes were materialized from upstream Git objects", "no S-parameter fit; final channel conversion is one FD-to-TD impulse"] or audit["non_claims"] != ["no upstream numeric parity", "no global or product parity", "no release or promotion", "PDB is opaque environment-local debug custody and nonpublish"]:
        fail("audit claims promotion")
    exact_keys(audit["validation"], {"strict_verifier", "aggregate_verifier", "focused_tests", "py_compile", "diff_check"}, "audit validation")
    if audit["validation"] != {"strict_verifier": "passed_with_fixed_cargo_home", "aggregate_verifier": "passed_with_fixed_cargo_home", "focused_tests": "60_pass", "py_compile": "passed", "diff_check": "passed"}:
        fail("audit validation drift")
    verify_hard_payload_graph(repo_root, data, audit, report_paths)
    if cargo_home is not None and upstream_repo is not None:
        verify_git_anchors(repo_root, upstream_repo, data)
    return data


def verify_formal_evidence(manifest_path: Path, repo_root: Path | None = None, cargo_home: Path | None = None, upstream_repo: Path | None = None) -> dict[str, Any]:
    root = (repo_root or manifest_path.parents[2]).resolve()
    manifest_path = manifest_path.resolve()
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    result = validate_manifest_data(data, manifest_path, root, cargo_home, upstream_repo)
    if cargo_home is not None:
        if cargo_home.resolve() != Path("C:/sipi-cargo-home-v1").resolve():
            fail("cargo home must be the fixed external directory")
    elif upstream_repo is not None:
        fail("formal CLI requires --cargo-home")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--cargo-home", type=Path, required=True)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    args = parser.parse_args()
    verify_formal_evidence(args.manifest, args.repo, args.cargo_home, args.upstream_repo)
    print("formal evidence verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
