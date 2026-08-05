"""Run the pinned agent-com result-v1 contract probe without artifact writes."""
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
    return subprocess.run(command, cwd=cwd, env=environment, text=True, encoding="utf-8", errors="replace", capture_output=True, check=True).stdout.strip()


def _repository(authority: dict) -> dict:
    source = next(contract["source_of_truth"] for contract in authority["external_contracts"] if contract["identifier"] == {"kind": "legacy_document", "value": "agent-com result v1"})
    snapshot = json.loads((ROOT / authority["source_snapshot_ref"]).read_text(encoding="utf-8"))
    return next(item for item in snapshot["repositories"] if item["id"] == source["repository"])


def _assert_pinned_source(repository: dict) -> None:
    root = Path(repository["path"])
    environment = dict(os.environ)
    if _output(["git", "rev-parse", "HEAD"], cwd=root, environment=environment) != repository["head"]:
        raise RuntimeError("agent_com_head_mismatch")
    if _output(["git", "rev-parse", "HEAD^{tree}"], cwd=root, environment=environment) != repository["tree"]:
        raise RuntimeError("agent_com_tree_mismatch")
    if _output(["git", "status", "--porcelain"], cwd=root, environment=environment):
        raise RuntimeError("agent_com_repository_dirty")
    expected_lock = next(item["sha256"] for item in repository["lockfiles"] if item["path"] == "uv.lock")
    if hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest().lower() != expected_lock.lower():
        raise RuntimeError("agent_com_lock_hash_mismatch")


def _probe_script(path: Path) -> None:
    path.write_text(
        """
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import agent_com.models as models
import agent_com.reporting as reporting
import agent_com.runtime as runtime
from agent_com.errors import ConfigError

source_root = Path(sys.argv[1]).resolve()
if sys.version_info[:3] != (3, 12, 13):
    raise RuntimeError(f\"agent_com_python_version_mismatch:{sys.version}\")
for module in (models, reporting, runtime):
    if source_root not in Path(module.__file__).resolve().parents:
        raise RuntimeError(f\"agent_com_import_outside_snapshot:{module.__name__}\")

profile = models.BehaviorProfile.r480()
provenance = runtime.Provenance(
    source_revision=\"r480\", matlab_source_sha256=\"0\" * 64, config_sha256=\"1\" * 64,
    channel_sha256=((\"THRU\", \"2\" * 64),), profile=profile, python_version=\"3.12.13\", platform=\"windows\",
)
result = models.RunResult(
    \"r480\", profile,
    (models.CaseResult(0, models.ChannelSet(\"synthetic-thru.s4p\"), {\"COM_dB\": 1.2}),),
    provenance, timings=models.TimingSummary({\"pipeline\": 0.0}),
)
arrays = {}
document = reporting._result_payload(result, arrays)
if arrays:
    raise RuntimeError(\"agent_com_result_unexpected_arrays\")
payload = (json.dumps(document, indent=2, sort_keys=True) + \"\\n\").encode(\"utf-8\")
reporting._validate_result_contract(json.loads(payload))
incompatible = dict(document)
incompatible[\"schema_version\"] = 2
incompatible_payload = (json.dumps(incompatible, indent=2, sort_keys=True) + \"\\n\").encode(\"utf-8\")
try:
    reporting._validate_result_contract(json.loads(incompatible_payload))
except ConfigError:
    version_reject = True
else:
    version_reject = False

base_hash = hashlib.sha256(payload).hexdigest()
print(json.dumps({\"runner\": \"agent_com_result_python\", \"python_version\": \".\".join(map(str, sys.version_info[:3])), \"results\": [
    {\"probe\": \"result_v1.producer_json\", \"decision\": \"accept\", \"phase\": \"schema\", \"base_payload_sha256\": base_hash, \"consumed_payload_sha256\": base_hash},
    {\"probe\": \"result_v1.consumer_validates\", \"decision\": \"accept\", \"phase\": \"schema\", \"base_payload_sha256\": base_hash, \"consumed_payload_sha256\": base_hash},
    {\"probe\": \"result_v1.consumer.version_rejects\", \"decision\": \"reject\" if version_reject else \"accept\", \"phase\": \"schema\", \"code\": \"unsupported_schema\", \"base_payload_sha256\": base_hash, \"consumed_payload_sha256\": hashlib.sha256(incompatible_payload).hexdigest(), \"derived_from\": \"result_v1.producer_json\"},
]}, sort_keys=True))
""".lstrip(),
        encoding="utf-8",
    )


def main() -> int:
    if not LOCKED_PYTHON.is_file() or sys.version_info[:3] != LOCKED_VERSION:
        raise RuntimeError("agent_com_outer_python_mismatch")
    repository = _repository(json.loads(AUTHORITY.read_text(encoding="utf-8")))
    root = Path(repository["path"])
    _assert_pinned_source(repository)
    with tempfile.TemporaryDirectory(prefix="sipi-agent-com-result-") as temporary:
        scratch = Path(temporary)
        probe = scratch / "probe.py"
        _probe_script(probe)
        environment = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(scratch / ".venv"), "UV_CACHE_DIR": str(scratch / "uv-cache"), "PYTHONDONTWRITEBYTECODE": "1"}
        output = _output([UV, "run", "--locked", "--python", str(LOCKED_PYTHON), "python", "-B", str(probe), str(root)], cwd=root, environment=environment)
    _assert_pinned_source(repository)
    result = json.loads(output.splitlines()[-1])
    result["observed_source_snapshot"] = {"repository": repository["id"], "revision": repository["head"], "tree": repository["tree"]}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
