import argparse
import json
from pathlib import Path
import subprocess
import hashlib
import tempfile
import yaml

try:
    from .aggregate_com_02_04_result_surface import CANDIDATE, PREP, PREP_BLOBS, PREP_PARENT, RUNS, SEMANTIC_ANCHORS, UPSTREAM, finite_tree, load_report, verify_git
except ImportError:
    from aggregate_com_02_04_result_surface import CANDIDATE, PREP, PREP_BLOBS, PREP_PARENT, RUNS, SEMANTIC_ANCHORS, UPSTREAM, finite_tree, load_report, verify_git

class VerificationError(RuntimeError): pass
GATE_FILES = {
    "tools/aggregate_com_02_04_result_surface.py",
    "tools/verify_com_02_04_result_surface_gate.py",
    "tools/test_verify_com_02_04_result_surface_gate.py",
}
FORMAL_FILES = {
    "docs/baselines/com-02-04-result-surface-formal.v1.yaml",
    "docs/baselines/com-02-04-result-surface-formal-aggregate.v1.json",
    "docs/baselines/audits/2026-08-29-com-02-04-result-surface-formal.md",
    "docs/baselines/com-02-result-surface-formal-run1.v1.json",
    "docs/baselines/com-02-result-surface-formal-run2.v1.json",
    "docs/baselines/com-04-result-surface-formal-run1.v1.json",
    "docs/baselines/com-04-result-surface-formal-run2.v1.json",
}

def command(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if result.returncode: raise VerificationError("git custody command failed")
    return result.stdout.strip()

def verify_gate_commit(repo: Path, gate_commit: str, expected_parent: str = PREP_PARENT[0]):
    parents = command(repo, "show", "-s", "--format=%P", gate_commit).split()
    if parents != [expected_parent]: raise VerificationError("gate must be direct child of prep")
    changes = command(repo, "diff-tree", "--no-commit-id", "--name-status", "-r", expected_parent, gate_commit).splitlines()
    if set(changes) != {f"A\t{path}" for path in GATE_FILES}: raise VerificationError("gate exact-three introduction drift")
    for path in GATE_FILES:
        entry = command(repo, "ls-tree", gate_commit, "--", path).split()
        if entry[:2] != ["100644", "blob"]: raise VerificationError("gate object mode/type drift")
        raw = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", entry[2]], capture_output=True, check=True).stdout
        if len(raw) > 512 * 1024 or raw != (repo / path).read_bytes(): raise VerificationError("gate raw/live drift")
    for path in FORMAL_FILES:
        result = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{gate_commit}:{path}"], capture_output=True)
        if result.returncode == 0: raise VerificationError("formal record present in gate commit")
    return True

def verify_record_commit(repo: Path, record_commit: str, gate_commit: str):
    if command(repo, "show", "-s", "--format=%P", record_commit).split() != [gate_commit]:
        raise VerificationError("record must be direct child of gate")
    changes = command(repo, "diff-tree", "--no-commit-id", "--name-status", "-r", gate_commit, record_commit).splitlines()
    if set(changes) != {f"A\t{path}" for path in FORMAL_FILES}:
        raise VerificationError("record exact-doc custody drift")
    for path in FORMAL_FILES:
        entry = command(repo, "ls-tree", record_commit, "--", path).split()
        if entry[:2] != ["100644", "blob"]:
            raise VerificationError("record object drift")
        raw = subprocess.run(["git", "-C", str(repo), "cat-file", "blob", entry[2]], capture_output=True, check=True).stdout
        if len(raw) > 4 * 1024 * 1024 or raw != (repo / path).read_bytes():
            raise VerificationError("record raw/live drift")
    if command(repo, "status", "--porcelain=v1", "--untracked-files=all"):
        raise VerificationError("record custody requires clean repository")
    return True

def file_sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def expected_audit(manifest):
    lines = ["# COM-02/04 formal result-surface record", "", f"GATE_COMMIT: {manifest['gate']['commit']}", "FORMAL_STATUS: passed_scoped"]
    lines.extend(f"REPORT: {item['path']} {item['sha256']}" for item in manifest["reports"])
    lines.extend((f"AGGREGATE: {manifest['aggregate']['path']} {manifest['aggregate']['sha256']}", "NO_UPSTREAM_NUMERIC_PARITY", "NO_PORT_ORDER_RESULT_WIRE", "COORDINATION_LABELS_ARE_NOT_EXECUTION_IDENTITY", ""))
    return "\n".join(lines)

class StrictLoader(yaml.SafeLoader): pass
def strict_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result: raise VerificationError("duplicate YAML key")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result
StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, strict_mapping)

def verify_record_documents(root: Path, gate_commit: str, upstream_repo: Path, provenance_repo: Path | None = None):
    provenance_repo = root if provenance_repo is None else provenance_repo
    manifest_path = root / "docs/baselines/com-02-04-result-surface-formal.v1.yaml"
    manifest = yaml.load(manifest_path.read_text(encoding="utf-8"), Loader=StrictLoader)
    finite_tree(manifest)
    if set(manifest) != {"schema", "status", "gate", "reports", "aggregate", "audit", "claims", "semantic_anchors"} or manifest["schema"] != "sipi.com-02-04.result-surface-formal.v1" or manifest["semantic_anchors"] != SEMANTIC_ANCHORS:
        raise VerificationError("manifest schema drift")
    gate = manifest["gate"]
    if set(gate) != {"commit", "tree", "tools"} or gate["commit"] != gate_commit or gate["tree"] != command(root, "show", "-s", "--format=%T", gate_commit):
        raise VerificationError("manifest gate commit drift")
    if type(gate["tools"]) is not list or [item.get("path") for item in gate["tools"]] != sorted(GATE_FILES):
        raise VerificationError("manifest gate tool order drift")
    for item in gate["tools"]:
        if set(item) != {"path", "blob", "bytes", "sha256"}:
            raise VerificationError("manifest gate receipt schema drift")
        entry = command(root, "ls-tree", gate_commit, "--", item["path"]).split()
        raw = subprocess.run(["git", "-C", str(root), "cat-file", "blob", entry[2]], capture_output=True, check=True).stdout
        if item != {"path": item["path"], "blob": entry[2], "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}:
            raise VerificationError("manifest gate receipt drift")
    expected_claims = {"prep_source_inventory": True, "fresh_nonce": True, "coordination_labels_are_not_execution_identity": True, "full_report_hashes": True, "upstream_numeric_parity": False, "port_order_result_wire": False}
    if manifest["status"] != "passed_scoped" or manifest["claims"] != expected_claims:
        raise VerificationError("manifest claims drift")
    if len(manifest["reports"]) != 4:
        raise VerificationError("manifest report count drift")
    reports = []
    expected_paths = [
        "docs/baselines/com-02-result-surface-formal-run1.v1.json", "docs/baselines/com-02-result-surface-formal-run2.v1.json",
        "docs/baselines/com-04-result-surface-formal-run1.v1.json", "docs/baselines/com-04-result-surface-formal-run2.v1.json",
    ]
    for binding, expected_path, (_, index, label, coordination) in zip(manifest["reports"], expected_paths, RUNS):
        if set(binding) != {"path", "sha256", "record_label", "coordination_label_sha256"} or binding["record_label"] != label or binding["coordination_label_sha256"] != coordination:
            raise VerificationError("manifest report binding drift")
        if binding["path"] != expected_path:
            raise VerificationError("manifest report path/order drift")
        path = root / binding["path"]
        if file_sha(path) != binding["sha256"]:
            raise VerificationError("report hash drift")
        reports.append(load_report(path))
    aggregate_binding = manifest["aggregate"]
    audit_binding = manifest["audit"]
    if aggregate_binding.get("path") != "docs/baselines/com-02-04-result-surface-formal-aggregate.v1.json" or audit_binding.get("path") != "docs/baselines/audits/2026-08-29-com-02-04-result-surface-formal.md":
        raise VerificationError("manifest fixed path drift")
    for binding in (aggregate_binding, audit_binding):
        if set(binding) != {"path", "sha256"} or file_sha(root / binding["path"]) != binding["sha256"]:
            raise VerificationError("reciprocal binding drift")
    aggregate = load_report(root / aggregate_binding["path"])
    if set(aggregate) != {"schema", "status", "formal_runs", "candidate", "prep", "upstream", "claims", "semantic_anchors"} or aggregate["schema"] != "sipi.com-02-04.result-surface-formal-aggregate.v1" or aggregate["semantic_anchors"] != SEMANTIC_ANCHORS:
        raise VerificationError("aggregate schema drift")
    if aggregate["claims"] != expected_claims or aggregate["status"] != "passed_scoped":
        raise VerificationError("aggregate claims drift")
    if [item["report_sha256"] for item in aggregate["formal_runs"]] != [item["sha256"] for item in manifest["reports"]]:
        raise VerificationError("aggregate/report reciprocity drift")
    with tempfile.TemporaryDirectory() as directory:
        regenerated = Path(directory) / "aggregate.json"
        command_line = [
            "python", str(root / "tools/aggregate_com_02_04_result_surface.py"), "--repo", str(provenance_repo),
            "--upstream-repo", str(upstream_repo),
        ]
        for binding in manifest["reports"]:
            command_line.extend(["--report", str(root / binding["path"])])
        command_line.extend(["--output", str(regenerated)])
        result = subprocess.run(command_line, capture_output=True, timeout=60, check=False)
        if result.returncode or regenerated.read_bytes() != (root / aggregate_binding["path"]).read_bytes():
            raise VerificationError("aggregate mechanical regeneration drift")
    audit = (root / audit_binding["path"]).read_text(encoding="utf-8")
    if audit != expected_audit(manifest):
        raise VerificationError("formal audit exact text drift")
    return True

def verify_coordination(runs=RUNS):
    if len(runs) != 4 or [item[:2] for item in runs] != [("com-02", 1), ("com-02", 2), ("com-04", 1), ("com-04", 2)]:
        raise VerificationError("run coordination drift")
    labels = [item[2] for item in runs]; coordination = [item[3] for item in runs]
    if len(set(labels)) != 4 or len(set(coordination)) != 4 or any(len(value) != 64 for value in coordination):
        raise VerificationError("record-label coordination drift")
    if PREP != ("90dea971a1661cf6ae0b7f71aab12b84f6eb241c", "e7eb1134f0061e586f117058d25a5298e2d7d799") or len(PREP_BLOBS) != 4:
        raise VerificationError("prep gate drift")
    if CANDIDATE[2:] != ("3098bb432d8c00c4c65c058cf0f325172112de6c24fb5e55127688d8e147d990", 54_650_880):
        raise VerificationError("candidate gate drift")
    if UPSTREAM[2] != "5f3f17e19edc07cf6498c9bfea20b8691082e2c05364b4462bc54df8549d0a04":
        raise VerificationError("upstream gate drift")
    return {"schema": "sipi.com-02-04.result-surface-gate.v1", "status": "ready_for_record_replay", "record_labels": labels, "coordination_label_sha256": coordination, "coordination_labels_are_not_execution_identity": True}

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--repo", type=Path, required=True); parser.add_argument("--upstream-repo", type=Path, required=True); parser.add_argument("--gate-commit", required=True); parser.add_argument("--record-commit")
    args = parser.parse_args()
    try:
        verify_git(args.repo, args.upstream_repo); verify_gate_commit(args.repo, args.gate_commit)
        if args.record_commit:
            verify_record_commit(args.repo, args.record_commit, args.gate_commit)
            verify_record_documents(args.repo, args.gate_commit, args.upstream_repo)
        elif any((args.repo / path).exists() for path in FORMAL_FILES):
            raise VerificationError("formal records must be absent at gate stage")
        print(json.dumps(verify_coordination(), sort_keys=True))
    except (OSError, RuntimeError) as error: parser.error(str(error))
    return 0

if __name__ == "__main__": raise SystemExit(main())
