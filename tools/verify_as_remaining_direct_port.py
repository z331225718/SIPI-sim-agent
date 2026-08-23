"""Verify the AS-02..AS-06 executable direct-port evidence records.

The verifier is intentionally contract-focused.  It checks source identity,
license/copy policy, executable leaf and replay inventory, and the audit hash;
it does not turn an open replay into a numerical parity claim.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
MODULES = {
    "AS-02": "crates/sipi-agent-spice-direct/src/as02_fit_sparam_cascade.rs",
    "AS-03": "crates/sipi-agent-spice-direct/src/as03_fit_yparam.rs",
    "AS-04": "crates/sipi-agent-spice-direct/src/as04_tune_yparam_tran.rs",
    "AS-05": "crates/sipi-agent-spice-direct/src/lib.rs",
    "AS-06": "crates/sipi-agent-spice-direct/src/as06_run_rfm.rs",
}
EXPECTED_STATUS = {
    "AS-02": "implemented_executable_numeric_parity_open",
    "AS-03": "implemented_executable_numeric_parity_open",
    "AS-04": "implemented_control_external_hspice_open",
    "AS-05": "implemented_control_external_solver_open",
    "AS-06": "implemented_executable_external_runtime_open",
}
MARKERS = {
    "AS-02": ("FitSparamCascadeRequest", "fit_sparam_cascade", "cascade_passivity_epsilon"),
    "AS-03": ("FitYparamRequest", "fit_yparam", "conversion_condition_limit"),
    "AS-04": ("TuneYparamTranRequest", "tune_yparam_tran", "replace_token"),
    "AS-05": ("admit_run_hspice", "split_alter_cases", "run_hspice"),
    "AS-06": ("RunRfmRequest", "parse_cadence_rfm", "run_rfm"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(path: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True, text=True).stdout.strip()


def verify(document: dict[str, Any], *, evidence_path: Path, root: Path = ROOT, source: Path | None = None) -> dict[str, Any]:
    blockers: list[str] = []
    schema = str(document.get("schema", ""))
    match = re.fullmatch(r"sipi\.(as-0[2-6])-[a-z0-9-]+-direct-port\.v1", schema)
    if not match:
        blockers.append("schema mismatch")
        workflow = ""
    else:
        workflow = match.group(1).upper()
    expected_status = EXPECTED_STATUS.get(workflow)
    if workflow and document.get("status") != expected_status:
        blockers.append("status drift")
    source_record = document.get("source")
    if not isinstance(source_record, dict):
        blockers.append("source record missing")
    else:
        for key, expected in (("repository", "agent-spice"), ("commit", COMMIT), ("tree", TREE), ("license", "MIT")):
            if source_record.get(key) != expected:
                blockers.append(f"source {key} drift")
        if source_record.get("source_payload_copied_into_sipi") is not False:
            blockers.append("source copy policy drift")
    direct = document.get("direct_port")
    if not isinstance(direct, dict):
        blockers.append("direct-port record missing")
    else:
        module = MODULES.get(workflow)
        if direct.get("crate") != "crates/sipi-agent-spice-direct" or direct.get("module") != module:
            blockers.append("direct-port module identity drift")
        if direct.get("upstream_commit_constant") != COMMIT:
            blockers.append("direct-port commit binding drift")
        if not direct.get("covered_semantics") or not direct.get("unsupported_semantics"):
            blockers.append("covered/unsupported semantics inventory missing")
    replay = document.get("oracle_replay")
    if (
        not isinstance(replay, dict)
        or replay.get("archive_commit") != COMMIT
        or replay.get("replay_count") != 2
        or replay.get("binding_status") != "unbound_preparation_observation"
        or replay.get("content_addressed") is not False
        or replay.get("immutable_source_binding") is not False
        or replay.get("parity_status") in (None, "pass")
    ):
        blockers.append("v1 replay must remain an unbound preparation observation")
    corpus = document.get("differential_corpus")
    if not isinstance(corpus, dict) or corpus.get("status") != "preparation_observation" or not isinstance(corpus.get("cases"), list) or not corpus["cases"]:
        blockers.append("differential corpus missing")
    evidence = document.get("evidence")
    if not isinstance(evidence, dict):
        blockers.append("evidence tool inventory missing")
    else:
        for key in ("runner", "aggregate", "verifier", "mutation_tests"):
            path = evidence.get(key)
            if not isinstance(path, str) or not (root / path).is_file():
                blockers.append(f"evidence {key} missing")
    module_path = root / MODULES.get(workflow, "__missing__")
    if not module_path.is_file():
        blockers.append("direct-port module missing")
    elif workflow:
        code = module_path.read_text(encoding="utf-8")
        for marker in MARKERS[workflow]:
            if marker not in code:
                blockers.append(f"direct-port marker missing: {marker}")
        if COMMIT not in code:
            blockers.append("direct-port source commit constant missing")
    audit = document.get("audit")
    audit_path = root / str(audit.get("path", "__missing__")) if isinstance(audit, dict) else root / "__missing__"
    if not isinstance(audit, dict) or not audit_path.is_file():
        blockers.append("audit record/file missing")
    else:
        expected = str(audit.get("sha256", ""))
        actual = _sha256(audit_path)
        if expected != actual:
            blockers.append("audit hash drift")
    if source is not None:
        try:
            if _git(source, "rev-parse", "HEAD") != COMMIT or _git(source, "rev-parse", "HEAD^{tree}") != TREE:
                blockers.append("source Git identity drift")
        except (OSError, subprocess.CalledProcessError):
            blockers.append("source Git identity unavailable")
    return {"valid": not blockers, "workflow": workflow, "status": document.get("status"), "blockers": blockers}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--source", type=Path)
    args = parser.parse_args()
    path = args.evidence if args.evidence.is_absolute() else ROOT / args.evidence
    result = verify(yaml.safe_load(path.read_text(encoding="utf-8")), evidence_path=path, source=args.source)
    print("valid" if result["valid"] else "blocked")
    for blocker in result["blockers"]:
        print(f"- {blocker}")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
