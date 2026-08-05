"""Run the pinned agent-com ProgressEvent probe without COM numerical work."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "schemas" / "authority.v1.yaml"
UV = "uv"
LOCKED_PYTHON = Path.home() / "AppData" / "Roaming" / "uv" / "python" / "cpython-3.12.13-windows-x86_64-none" / "python.exe"
LOCKED_VERSION = (3, 12, 13)


def _output(command: list[str], *, cwd: Path, environment: dict[str, str]) -> str:
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=True,
    ).stdout.strip()


def _repository(authority: dict) -> tuple[dict, dict]:
    source = next(
        contract["source_of_truth"]
        for contract in authority["external_contracts"]
        if contract["identifier"] == {"kind": "embedded_type", "value": "agent-com ProgressEvent"}
    )
    snapshot = json.loads((ROOT / authority["source_snapshot_ref"]).read_text(encoding="utf-8"))
    repository = next(item for item in snapshot["repositories"] if item["id"] == source["repository"])
    return source, repository


def _assert_pinned_source(repository: dict) -> None:
    root = Path(repository["path"])
    environment = dict(os.environ)
    if _output(["git", "rev-parse", "HEAD"], cwd=root, environment=environment) != repository["head"]:
        raise RuntimeError("agent_com_head_mismatch")
    if _output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, environment=environment) != repository["tree"]:
        raise RuntimeError("agent_com_tree_mismatch")
    if _output(["git", "status", "--porcelain"], cwd=root, environment=environment):
        raise RuntimeError("agent_com_repository_dirty")
    lock_path = root / "uv.lock"
    expected_lock = next(item["sha256"] for item in repository["lockfiles"] if item["path"] == "uv.lock")
    if hashlib.sha256(lock_path.read_bytes()).hexdigest().lower() != expected_lock.lower():
        raise RuntimeError("agent_com_lock_hash_mismatch")


def _probe_script(path: Path) -> None:
    path.write_text(
        """
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

import agent_com.cli as cli
import agent_com.models as models
import agent_com.runtime as runtime

source_root = Path(sys.argv[1]).resolve()
if sys.version_info[:3] != (3, 12, 13):
    raise RuntimeError(f\"agent_com_python_version_mismatch:{sys.version}\")
for module in (cli, models, runtime):
    if source_root not in Path(module.__file__).resolve().parents:
        raise RuntimeError(f\"agent_com_import_outside_snapshot:{module.__name__}\")

with tempfile.TemporaryDirectory(prefix=\"sipi-agent-com-progress-\") as temporary:
    progress_path = Path(temporary) / \"progress.jsonl\"
    captured = []
    with cli._ProgressReporter(None, progress_path, heartbeat_s=3600.0) as reporter:
        def callback(event: models.ProgressEvent) -> None:
            captured.append(event)
            reporter.record_event(event)

        runtime.RunProgressEmitter(callback).emit(
            \"search_progress\",
            package_case_index=0,
            grid_total=8,
            grid_seen=1,
            evaluate_entered=1,
        )
    lines = progress_path.read_text(encoding=\"utf-8\").splitlines()
    if len(captured) != 1 or len(lines) != 1:
        raise RuntimeError(\"agent_com_progress_producer_incomplete\")
    payload = lines[0].encode(\"utf-8\")
    document = json.loads(lines[0])
    consumed = models.ProgressEvent(**document)
    if consumed != captured[0]:
        raise RuntimeError(\"agent_com_progress_consumer_mismatch\")
    incompatible = dict(document)
    incompatible[\"schema_version\"] = 2
    incompatible_payload = json.dumps(incompatible, ensure_ascii=False, sort_keys=True, separators=(\",\", \":\")).encode(\"utf-8\")
    try:
        models.ProgressEvent(**json.loads(incompatible_payload))
    except ValueError:
        consumer_reject = True
    else:
        consumer_reject = False

print(json.dumps({\"runner\": \"agent_com_python\", \"python_version\": \".\".join(map(str, sys.version_info[:3])), \"results\": [
    {\"probe\": \"progress_event.producer_jsonl\", \"decision\": \"accept\", \"phase\": \"schema\", \"base_payload_sha256\": hashlib.sha256(payload).hexdigest(), \"consumed_payload_sha256\": hashlib.sha256(payload).hexdigest()},
    {\"probe\": \"progress_event.consumer_deserializes\", \"decision\": \"accept\", \"phase\": \"schema\", \"base_payload_sha256\": hashlib.sha256(payload).hexdigest(), \"consumed_payload_sha256\": hashlib.sha256(payload).hexdigest()},
    {\"probe\": \"progress_event.consumer.schema_rejects\", \"decision\": \"reject\" if consumer_reject else \"accept\", \"phase\": \"schema\", \"code\": \"schema\", \"base_payload_sha256\": hashlib.sha256(payload).hexdigest(), \"consumed_payload_sha256\": hashlib.sha256(incompatible_payload).hexdigest(), \"derived_from\": \"progress_event.producer_jsonl\"},
]}, sort_keys=True))
""".lstrip(),
        encoding="utf-8",
    )


def main() -> int:
    if not LOCKED_PYTHON.is_file() or sys.version_info[:3] != LOCKED_VERSION:
        raise RuntimeError("agent_com_outer_python_mismatch")
    authority = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    _, repository = _repository(authority)
    root = Path(repository["path"])
    _assert_pinned_source(repository)
    with tempfile.TemporaryDirectory(prefix="sipi-agent-com-contract-") as temporary:
        scratch = Path(temporary)
        probe = scratch / "probe.py"
        _probe_script(probe)
        environment = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(scratch / ".venv"), "UV_CACHE_DIR": str(scratch / "uv-cache"), "PYTHONDONTWRITEBYTECODE": "1"}
        tests = [
            "tests/test_runtime.py::test_progress_events_are_immutable_and_callback_failures_are_isolated",
            "tests/test_cli.py::test_progress_reporter_writes_structured_search_events",
        ]
        canary = _output([UV, "run", "--locked", "--extra", "test", "--python", str(LOCKED_PYTHON), "python", "-B", "-m", "pytest", "-p", "no:cacheprovider", "--basetemp", str(scratch / "pytest-temp"), *tests], cwd=root, environment=environment)
        if "2 passed" not in canary:
            raise RuntimeError("agent_com_canary_not_executed")
        output = _output([UV, "run", "--locked", "--python", str(LOCKED_PYTHON), "python", "-B", str(probe), str(root)], cwd=root, environment=environment)
    _assert_pinned_source(repository)
    result = json.loads(output.splitlines()[-1])
    result["observed_source_snapshot"] = {"repository": repository["id"], "revision": repository["head"], "tree": repository["tree"]}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
