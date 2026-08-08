from __future__ import annotations

import hashlib
import base64
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_adapters import PyBertNativeAdapter, execute_backend
from sipi_contracts import parse_backend_execution_request, parse_engine_lock, parse_run_request
from sipi_runtime import EngineRegistry, plan_backend_executions

BASE_FILES = {
    "fixture_engine/__init__.py": (
        "import argparse, json, sys\n"
        "from pathlib import Path\n"
        "def main():\n"
        "    argv = sys.argv[1:]\n"
        "    if argv and argv[0] == 'sim-native':\n"
        "        argv = argv[1:]\n"
        "    parser = argparse.ArgumentParser()\n"
        "    parser.add_argument('input_file')\n"
        "    parser.add_argument('--output-dir', required=True)\n"
        "    args = parser.parse_args(argv)\n"
        "    out = Path(args.output_dir)\n"
        "    out.mkdir(parents=True, exist_ok=True)\n"
        "    sim = json.loads(Path(args.input_file).read_text(encoding='utf-8'))\n"
        "    (out / 'meta.json').write_text(json.dumps({'schema': 'pybert.native-cli-result.v1', 'effective_input': sim, 'arrays_file': 'arrays.npz'}))\n"
        "    (out / 'arrays.npz').write_bytes(b'wheel-npz')\n"
        "    return 0\n"
    ).encode("utf-8"),
    "fixture_engine-0.1.0.dist-info/METADATA": b"Metadata-Version: 2.1\nName: fixture-engine\nVersion: 0.1.0\n",
    "fixture_engine-0.1.0.dist-info/WHEEL": b"Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    "fixture_engine-0.1.0.dist-info/entry_points.txt": b"[console_scripts]\nfixture-engine = fixture_engine:main\n",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wheel_files(*, engine_source: bytes | None = None) -> dict[str, bytes]:
    files = dict(BASE_FILES)
    if engine_source is not None:
        files["fixture_engine/__init__.py"] = engine_source
    lines = []
    for name, data in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        lines.append(f"{name},sha256={digest},{len(data)}")
    record_name = "fixture_engine-0.1.0.dist-info/RECORD"
    lines.append(f"{record_name},,")
    files[record_name] = ("\n".join(lines) + "\n").encode()
    return files


def build_wheel(root: Path, *, files: dict[str, bytes] | None = None) -> Path:
    wheel = root / "bundles" / "fixture_engine-0.1.0-py3-none-any.whl"
    wheel.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(wheel, "w") as archive:
        for name, data in (files if files is not None else wheel_files()).items():
            archive.writestr(name, data)
    return wheel


def engine_entry(root: Path, *, console_script: str | None = "fixture-engine", files: dict[str, bytes] | None = None) -> dict:
    files = files if files is not None else wheel_files()
    wheel = build_wheel(root, files=files)
    manifest_files = [
        {
            "relative_path": name,
            "role": "entrypoint" if name == "fixture_engine/__init__.py" else ("library" if name.endswith(".py") else "data"),
            "sha256": sha256_bytes(data),
            "byte_length": len(data),
        }
        for name, data in files.items()
    ]
    extensions = {"sipi.m2.console-script": console_script} if console_script else {}
    return {
        "instance_id": "pybert-rust-wheel",
        "engine_family": "pybert",
        "version": "0.1.0",
        "source_commit": "0" * 40,
        "bundle": {"kind": "local_path", "path": "bundles/fixture_engine-0.1.0-py3-none-any.whl", "sha256": sha256(wheel)},
        "protocol": {"request_schema": "sipi.backend-execution-request.v1", "result_schema": "sipi.backend-execution-result.v1"},
        "capabilities": {"schema": "sipi.engine-capabilities.v1", "sha256": "1" * 64},
        "runtime": {"kind": "python", "os": "windows", "architecture": "x86_64", "python_abi": "cp312", "rust_target": None},
        "dependency_lock_sha256": "2" * 64,
        "license_provenance": {"distribution_status": "authorized_public", "manifest_sha256": "3" * 64},
        "bundle_manifest": {"entrypoint": "fixture_engine/__init__.py", "files": manifest_files},
        "extensions": extensions,
    }


def backend_request(**changes):
    value = {
        "schema": "sipi.backend-execution-request.v1",
        "run_id": "run-1",
        "analysis_id": "analysis-1",
        "attempt_id": "attempt-1",
        "backend_execution_id": "backend-1",
        "role": "reference",
        "engine_instance_id": "pybert-rust-wheel",
        "bundle_hash": "sha256:bundle",
        "operation": "link.simulate.v1",
        "payload_schema": "pybert.simulation.v1",
        "payload": {"simulation_input": {"schema": "pybert.simulation.v1", "source": "fixture"}},
        "bound_inputs": {},
        "resource_limits": {"enforcement": "monitor", "wall_time_s": None, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None},
        "artifact_policy": {},
        "randomness": {},
        "selection_hash": "sha256:selection",
    }
    value.update(changes)
    return parse_backend_execution_request(value)


class WheelExecutionTests(unittest.TestCase):
    def test_wheel_execution_runs_in_isolated_venv_and_hands_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifact_root = root / "artifacts"
            result = execute_backend(
                backend_request(),
                engine_entry(root),
                root,
                builder=PyBertNativeAdapter(),
                artifact_root=artifact_root,
            )
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["domain_result_schema"], "pybert.native-cli-result.v1")
            self.assertEqual(result["domain_result"]["effective_input"]["schema"], "pybert.simulation.v1")
            refs = {item["relative_path"]: item for item in result["artifacts"]}
            self.assertEqual(set(refs), {"out/meta.json", "out/arrays.npz"})
            for relative, ref in refs.items():
                stored = artifact_root / relative
                self.assertTrue(stored.is_file())
                self.assertEqual(sha256(stored), ref["sha256"])

    def test_wheel_without_console_script_is_unsupported_capability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = execute_backend(backend_request(), engine_entry(root, console_script=None), root, builder=PyBertNativeAdapter())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "UnsupportedCapability")
        self.assertIn("console-script", result["error"]["message"])

    def test_missing_console_script_after_install_is_unsupported_capability(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = execute_backend(backend_request(), engine_entry(root, console_script="missing-script"), root, builder=PyBertNativeAdapter())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "UnsupportedCapability")
        self.assertIn("console script missing", result["error"]["message"])

    def test_wheel_install_failure_is_unsupported_capability(self) -> None:
        no_record = {name: data for name, data in BASE_FILES.items()}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = execute_backend(backend_request(), engine_entry(root, files=no_record), root, builder=PyBertNativeAdapter())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "UnsupportedCapability")
        self.assertIn("wheel install failed", result["error"]["message"])

    def test_missing_third_party_dependency_is_engine_failure(self) -> None:
        source = (
            "import argparse, json, sys\n"
            "import missing_third_party_dep\n"  # noqa: F401
            "from pathlib import Path\n"
            "def main():\n"
            "    return 1\n"
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = execute_backend(backend_request(), engine_entry(root, files=wheel_files(engine_source=source)), root, builder=PyBertNativeAdapter())
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["error"]["category"], "ExternalModelFailure")

    def test_wheel_execution_through_platform_loop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = engine_entry(root)
            lock = {"schema": "sipi.engine-lock.v1", "engines": [entry], "operation_defaults": {}, "extensions": {}}
            (root / "engine.lock").write_text(json.dumps(lock), encoding="utf-8")
            registry = EngineRegistry(parse_engine_lock(lock))
            run_request = parse_run_request(
                {
                    "schema": "sipi.run-request.v1",
                    "run_id": "run-1",
                    "project_id": "project-1",
                    "analysis_id": "analysis-1",
                    "attempt_id": "attempt-1",
                    "operation": "link.simulate.v1",
                    "payload_schema": "pybert.simulation.v1",
                    "payload": {"simulation_input": {"schema": "pybert.simulation.v1", "source": "fixture"}},
                    "backend_selection": {"mode": "strict", "instance": "pybert-rust-wheel"},
                    "resource_limits": {"enforcement": "monitor", "wall_time_s": None, "cpu_time_s": None, "memory_bytes": None, "process_count": None, "artifact_bytes": None},
                    "randomness": {},
                    "artifact_policy": {},
                    "extensions": {},
                }
            )
            plans = plan_backend_executions(run_request, registry)
            result = execute_backend(
                plans[0].request,
                plans[0].engine_entry,
                root,
                builder=PyBertNativeAdapter(),
                capabilities=PyBertNativeAdapter.capability_entries(),
                artifact_root=root / "artifacts",
            )
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["domain_result"]["effective_input"]["source"], "fixture")

    def test_managed_dependency_wheel_is_installed_into_the_same_venv(self) -> None:
        """A bundle_manifest role=dependency wheel is installed beside the primary
        wheel and importable from the engine process (managed dependency lock)."""
        dep_files = {
            "fixture_dep/__init__.py": (
                "VALUE = 42\n"
            ).encode("utf-8"),
            "fixture_dep-0.1.0.dist-info/METADATA": b"Metadata-Version: 2.1\nName: fixture-dep\nVersion: 0.1.0\n",
            "fixture_dep-0.1.0.dist-info/WHEEL": b"Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            "fixture_dep-0.1.0.dist-info/RECORD": b"fixture_dep/__init__.py,,\nfixture_dep-0.1.0.dist-info/METADATA,,\nfixture_dep-0.1.0.dist-info/WHEEL,,\nfixture_dep-0.1.0.dist-info/RECORD,,\n",
        }
        engine_source = (
            "import argparse, json, sys\n"
            "from pathlib import Path\n"
            "def main():\n"
            "    from fixture_dep import VALUE\n"
            "    argv = sys.argv[1:]\n"
            "    if argv and argv[0] == 'sim-native':\n"
            "        argv = argv[1:]\n"
            "    parser = argparse.ArgumentParser()\n"
            "    parser.add_argument('input_file')\n"
            "    parser.add_argument('--output-dir', required=True)\n"
            "    args = parser.parse_args(argv)\n"
            "    out = Path(args.output_dir)\n"
            "    out.mkdir(parents=True, exist_ok=True)\n"
            "    sim = json.loads(Path(args.input_file).read_text(encoding='utf-8'))\n"
            "    sim['dep_value'] = VALUE\n"
            "    (out / 'meta.json').write_text(json.dumps({'schema': 'pybert.native-cli-result.v1', 'effective_input': sim, 'arrays_file': 'arrays.npz'}))\n"
            "    (out / 'arrays.npz').write_bytes(b'wheel-npz')\n"
            "    return 0\n"
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dep_wheel = root / "bundles" / "fixture_dep-0.1.0-py3-none-any.whl"
            dep_wheel.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(dep_wheel, "w") as archive:
                for name, data in dep_files.items():
                    archive.writestr(name, data)
            entry = engine_entry(root, files=wheel_files(engine_source=engine_source))
            manifest_files = entry["bundle_manifest"]["files"]
            manifest_files.append(
                {
                    "relative_path": "bundles/fixture_dep-0.1.0-py3-none-any.whl",
                    "role": "dependency",
                    "sha256": sha256(dep_wheel),
                    "byte_length": dep_wheel.stat().st_size,
                }
            )
            result = execute_backend(
                backend_request(),
                entry,
                root,
                builder=PyBertNativeAdapter(),
                artifact_root=root / "artifacts",
            )
            self.assertEqual(result["status"], "succeeded")
            self.assertEqual(result["domain_result"]["effective_input"]["dep_value"], 42)

    def test_managed_dependency_wheel_hash_mismatch_fails_closed(self) -> None:
        """A dependency wheel whose pinned hash does not match the actual file is
        rejected before any engine process is started."""
        dep_files = {
            "fixture_dep/__init__.py": b"VALUE = 1\n",
            "fixture_dep-0.1.0.dist-info/METADATA": b"Metadata-Version: 2.1\nName: fixture-dep\nVersion: 0.1.0\n",
            "fixture_dep-0.1.0.dist-info/WHEEL": b"Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
            "fixture_dep-0.1.0.dist-info/RECORD": b"fixture_dep/__init__.py,,\nfixture_dep-0.1.0.dist-info/METADATA,,\nfixture_dep-0.1.0.dist-info/WHEEL,,\nfixture_dep-0.1.0.dist-info/RECORD,,\n",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dep_wheel = root / "bundles" / "fixture_dep-0.1.0-py3-none-any.whl"
            dep_wheel.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(dep_wheel, "w") as archive:
                for name, data in dep_files.items():
                    archive.writestr(name, data)
            entry = engine_entry(root)
            manifest_files = entry["bundle_manifest"]["files"]
            manifest_files.append(
                {
                    "relative_path": "bundles/fixture_dep-0.1.0-py3-none-any.whl",
                    "role": "dependency",
                    "sha256": "f" * 64,
                    "byte_length": dep_wheel.stat().st_size,
                }
            )
            result = execute_backend(backend_request(), entry, root, builder=PyBertNativeAdapter())
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"]["category"], "EngineUnavailable")
            self.assertIn("dependency wheel hash mismatch", result["error"]["message"])

    def test_malformed_pip_dependencies_extension_is_unsupported_capability(self) -> None:
        """A non-list sipi.m2.pip-dependencies extension fails closed."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = engine_entry(root)
            entry["extensions"] = {"sipi.m2.console-script": "fixture-engine", "sipi.m2.pip-dependencies": "not-a-list"}
            result = execute_backend(backend_request(), entry, root, builder=PyBertNativeAdapter())
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["error"]["category"], "UnsupportedCapability")
            self.assertIn("pip-dependencies", result["error"]["message"])


if __name__ == "__main__":
    unittest.main()
