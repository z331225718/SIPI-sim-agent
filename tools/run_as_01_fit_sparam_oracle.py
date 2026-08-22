"""Run the pinned two-stage AS-01 fit-sparam differential corpus.

The default mode only emits the frozen scenario plan. ``--execute`` performs
fresh isolated upstream and Rust runs, records exit status and bounded artifact
digests, and never treats a candidate result as parity without an explicit
consumer of the resulting report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Sequence

UPSTREAM_COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
UPSTREAM_TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
REQUIRED_FUTURE_RUNS = 2

FIXTURE_TEXT = """# Hz S RI R 50
0 0 0 0.5 0 0.5 0 0 0
1000000 0 0 0.5 0 0.5 0 0 0
2000000 0 0 0.5 0 0.5 0 0 0
3000000 0 0 0.5 0 0.5 0 0 0
4000000 0 0 0.5 0 0.5 0 0 0
5000000 0 0 0.5 0 0.5 0 0 0
"""


def scenario_documents() -> list[dict[str, Any]]:
    return [
        {"id": "missing_rms_target", "args": ["fit-sparam", "input.s2p"]},
        {
            "id": "full_band_defaults",
            "args": ["fit-sparam", "input.s2p", "--rms-target", "0.001", "--passivity", "off", "--max-order", "1"],
        },
        {
            "id": "priority_band_only",
            "args": ["fit-sparam", "input.s2p", "--priority-band", "0:5e6:0.01", "--passivity", "off", "--max-order", "1"],
        },
        {
            "id": "priority_band_and_full_band",
            "args": ["fit-sparam", "input.s2p", "--priority-band", "0:5e6:0.01:2", "--rms-target", "0.02", "--passivity", "off", "--max-order", "1"],
        },
        {
            "id": "explicit_output_artifact_family",
            "args": ["fit-sparam", "input.s2p", "--output", "out/model.sp", "--rms-target", "0.001", "--passivity", "off", "--max-order", "1"],
        },
        {
            "id": "legacy_passivity_precedence",
            "args": ["fit-sparam", "input.s2p", "--enforce-passivity", "--skip-passivity-check", "--rms-target", "0.001"],
        },
        {
            "id": "passivity_flag_conflict",
            "args": ["fit-sparam", "input.s2p", "--passivity", "off", "--check-passivity", "--rms-target", "0.001"],
        },
        {"id": "invalid_priority_band", "args": ["fit-sparam", "input.s2p", "--priority-band", "2e9:1e9:0.01"]},
        {"id": "invalid_order", "args": ["fit-sparam", "input.s2p", "--rms-target", "0.001", "--min-order", "8", "--max-order", "4"]},
        {"id": "target_failure_and_success", "args": ["fit-sparam", "input.s2p", "--rms-target", "0.001", "--passivity", "off", "--max-order", "1"]},
    ]


def scenario_set_sha256() -> str:
    payload = json.dumps(scenario_documents(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def preparation_plan() -> dict[str, Any]:
    return {
        "schema": "sipi.agent-spice-as-01-oracle-preparation.v2",
        "status": "preparation_only",
        "workflow": "AS-01",
        "upstream": {"commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE},
        "stages": ["upstream_pinned_execution", "rust_candidate_execution"],
        "required_future_runs": REQUIRED_FUTURE_RUNS,
        "scenario_set_sha256": scenario_set_sha256(),
        "scenario_count": len(scenario_documents()),
        "scenarios": scenario_documents(),
        "candidate_binding": "bounded_numeric_fit_sparam_entrypoint",
        "tolerance": "not_claimed_until_two_reports_are_reviewed",
        "reports": [],
    }


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact_inventory(root: Path) -> list[dict[str, Any]]:
    inventory = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            inventory.append({"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})
    return inventory


def report_summary(root: Path) -> list[dict[str, Any]]:
    """Keep only bounded scalar result fields, never full report payloads."""
    summaries = []
    for path in sorted(root.rglob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        values: dict[str, Any] = {}

        def visit(value: Any) -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    if key in {"target_met", "selected_order", "rms_error", "best_rms", "passivity"} and isinstance(child, (bool, int, float, str)):
                        values.setdefault(key, child)
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(document)
        if values:
            summaries.append({"path": path.relative_to(root).as_posix(), "values": values})
    return summaries


def run_command(command: Sequence[str], *, cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    completed = subprocess.run(list(command), cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return {
        "returncode": completed.returncode,
        "stdout_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
        "stderr_sha256": hashlib.sha256(completed.stderr.encode()).hexdigest(),
        "stdout_tail": completed.stdout[-1000:],
        "stderr_tail": completed.stderr[-1000:],
    }


def execute_stage(stage: str, *, agent_spice_root: Path | None, candidate_binary: Path | None, python_executable: str, workspace: Path) -> dict[str, Any]:
    workspace.mkdir(parents=True, exist_ok=True)
    fixture = workspace / "input.s2p"
    fixture.write_text(FIXTURE_TEXT, encoding="ascii", newline="\n")
    reports = []
    for scenario in scenario_documents():
        scenario_dir = workspace / scenario["id"]
        scenario_dir.mkdir()
        scenario_fixture = scenario_dir / "input.s2p"
        scenario_fixture.write_bytes(fixture.read_bytes())
        args = ["input.s2p" if value == "input.s2p" else value for value in scenario["args"]]
        if stage == "upstream_pinned_execution":
            assert agent_spice_root is not None
            command = [python_executable, "-m", "agent_spice.cli", *args]
            env = os.environ.copy()
            env["PYTHONPATH"] = str(agent_spice_root / "src")
        else:
            assert candidate_binary is not None
            command = [str(candidate_binary), *args]
            env = os.environ.copy()
        result = run_command(command, cwd=scenario_dir, env=env)
        result.update({"id": scenario["id"], "args": args, "artifacts": artifact_inventory(scenario_dir), "report_summaries": report_summary(scenario_dir)})
        reports.append(result)
    return {"stage": stage, "fixture_sha256": sha256(fixture), "scenarios": reports}


def execute_runs(*, agent_spice_root: Path | None, candidate_binary: Path | None, python_executable: str, run_count: int) -> dict[str, Any]:
    if run_count < 1:
        raise ValueError("run count must be positive")
    runs = []
    for run_index in range(run_count):
        nonce = secrets.token_hex(32)
        with tempfile.TemporaryDirectory(prefix=f"sipi-as01-{run_index + 1}-") as temporary:
            root = Path(temporary)
            runs.append({
                "run_id": f"{run_index + 1:02d}-{nonce}",
                "nonce": nonce,
                "upstream": execute_stage("upstream_pinned_execution", agent_spice_root=agent_spice_root, candidate_binary=None, python_executable=python_executable, workspace=root / "upstream") if agent_spice_root is not None else None,
                "candidate": execute_stage("rust_candidate_execution", agent_spice_root=None, candidate_binary=candidate_binary, python_executable=python_executable, workspace=root / "candidate") if candidate_binary is not None else None,
            })
    return {"schema": "sipi.agent-spice-as-01-oracle-result.v1", "status": "executed_uncompared", "upstream": {"commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE}, "scenario_set_sha256": scenario_set_sha256(), "runs": runs}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["prepare", "upstream_pinned_execution", "rust_candidate_execution"], default="prepare")
    parser.add_argument("--agent-spice-root", type=Path)
    parser.add_argument("--candidate-binary", type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--runs", type=int, default=REQUIRED_FUTURE_RUNS)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not args.execute:
        plan = preparation_plan()
    else:
        if args.stage == "upstream_pinned_execution" and args.agent_spice_root is None:
            parser.error("--agent-spice-root is required for upstream execution")
        if args.stage == "rust_candidate_execution" and args.candidate_binary is None:
            parser.error("--candidate-binary is required for Rust execution")
        if args.stage == "prepare" and (args.agent_spice_root is None or args.candidate_binary is None):
            parser.error("--execute requires both --agent-spice-root and --candidate-binary")
        plan = execute_runs(agent_spice_root=args.agent_spice_root, candidate_binary=args.candidate_binary, python_executable=args.python, run_count=args.runs)
    encoded = json.dumps(plan, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
