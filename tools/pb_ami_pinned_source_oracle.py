"""Run the real pinned PyAMI/PyBERT runtime-stage oracle when dependencies exist.

The helper first creates a clean archive of the pinned commit and verifies the
source blobs. It never contains a second implementation of the oracle. A
missing pinned Python dependency is reported as an explicit blocked result.
"""

from __future__ import annotations

import ctypes
import hashlib
import importlib
import importlib.metadata
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


COMMIT = "5bf6d7ea0ace261891aaeb611ffc1c267e160afe"
TREE = "5faef6bdb341d444ad65d82a11c0018b15805e24"
PINNED = Path(os.environ.get("PYBERT_PINNED_ROOT", r"C:\Users\z3312\code\Py-bert-agent"))
FILES = {
    "PyAMI/src/pyibisami/ami/parser.py": (
        "23389fa558291ef2a06dff1c7cb5ebcaa864a0a4",
        "7ab52c1e03893cdd496a4db7672b3213a0d1eec5d2b746a98e9011aa03bf3a7c",
    ),
    "PyAMI/src/pyibisami/ami/parameter.py": (
        "201ed14ef561392d46f385d80e0d3954b0dc67d8",
        "95bc003de3a5abd73bfa32f4b5a1db1c0c7d511c5f8cea11d92a967e54c76908",
    ),
    "PyAMI/src/pyibisami/ami/model.py": (
        "4cfa4ec87aed1f5caece871271aa3a587bcae21f",
        "bf24cff1140e83ec46a8a6c9a5482151cffa90d516dfa056f639893b280e3787",
    ),
    "src/pybert/utility/ibisami.py": (
        "9f1fb3b1496fd192b77207ffcecc4b2478d5f64e",
        "14e1ac37c9673c21bc3bb6c75cf67d1483f658fb6d668b9dd1066693c6613c79",
    ),
    "models/ibisami/example_rx.ami": (
        "26a1b03849a0838284dfde7921926668ad1434e0",
        "6d4038a184cb10af355dbd02b9392258d7e2b3bb9b0cddc211349db66ef80c38",
    ),
}


PROCESS_TIMEOUT = 30


def _run(command: list[str], *, text: bool = True) -> str | bytes:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
    )
    try:
        stdout, stderr = process.communicate(timeout=PROCESS_TIMEOUT)
    except subprocess.TimeoutExpired as error:
        process.kill()
        process.communicate()
        raise RuntimeError(f"process timeout: {command[0]}") from error
    if process.returncode != 0:
        detail = stderr.strip() if isinstance(stderr, str) else stderr[:256]
        raise RuntimeError(f"process failed: {command[0]}: {detail}")
    return stdout


def _git(git_path: Path, *args: str) -> str:
    return str(_run([str(git_path), "-C", str(PINNED), *args])).strip()


def _archive(root: Path, git_path: Path) -> tuple[Path, str]:
    tar_path = root / "pinned.tar"
    _run([
        str(git_path), "-C", str(PINNED), "archive", "--format=tar", COMMIT,
        "PyAMI/src", "src/pybert", "models/ibisami/example_rx.ami",
        "-o", str(tar_path),
    ])
    return tar_path, hashlib.sha256(tar_path.read_bytes()).hexdigest()


def _safe_extract(archive: Path, target: Path) -> None:
    target.mkdir()
    total = 0
    with tarfile.open(archive) as source:
        members = source.getmembers()
        if len(members) > 20_000:
            raise ValueError("archive member cap")
        for member in members:
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                raise ValueError("unsafe archive member")
            if member.size > 64 * 1024 * 1024:
                raise ValueError("archive member size cap")
            total += member.size
            if total > 512 * 1024 * 1024:
                raise ValueError("archive size cap")
            destination = (target / path).resolve()
            if target.resolve() not in destination.parents and destination != target.resolve():
                raise ValueError("archive escape")
        source.extractall(target, filter="data")


def run() -> dict:
    if not PINNED.is_dir():
        return {"status": "blocked_external_python_oracle", "reason": "pinned repository missing"}
    git_executable = shutil.which("git")
    if not git_executable:
        return {"status": "blocked_external_python_oracle", "reason": "git executable missing"}
    try:
        git_path = Path(git_executable).resolve()
        git_pre = _file_identity(git_path)
        git_version = str(_run([str(git_path), "--version"])).strip()
        python_path = Path(sys.executable).resolve()
        python_pre = _file_identity(python_path)
        if _git(git_path, "rev-parse", f"{COMMIT}^{{tree}}") != TREE:
            return {"status": "blocked_external_python_oracle", "reason": "pinned tree mismatch"}
    except (OSError, RuntimeError) as error:
        return {"status": "blocked_external_python_oracle", "reason": f"tool identity failed: {error}"}
    with tempfile.TemporaryDirectory(prefix="pb-pinned-oracle-") as temp:
        root = Path(temp)
        try:
            archive, archive_sha256 = _archive(root, git_path)
        except (OSError, RuntimeError) as error:
            return {"status": "blocked_external_python_oracle", "reason": f"archive failed: {error}"}
        try:
            _safe_extract(archive, root / "archive")
        except (OSError, tarfile.TarError, ValueError) as error:
            return {"status": "blocked_external_python_oracle", "reason": f"archive rejected: {error}"}
        extracted = root / "archive"
        try:
            for path, (blob, sha256) in FILES.items():
                actual_blob = _git(git_path, "rev-parse", f"{COMMIT}:{path}")
                if not (extracted / path).is_file():
                    return {"status": "blocked_external_python_oracle", "reason": f"archive source missing: {path}"}
                # Git attributes may normalize line endings in a clean archive;
                # bind both the immutable Git blob and the exact extracted bytes.
                raw_blob = _run(
                    [str(git_path), "-C", str(PINNED), "cat-file", "-p", f"{COMMIT}:{path}"],
                    text=False,
                )
                if actual_blob != blob or hashlib.sha256(raw_blob).hexdigest() != sha256:
                    return {"status": "blocked_external_python_oracle", "reason": f"source binding mismatch: {path}"}
        except (OSError, RuntimeError) as error:
            return {"status": "blocked_external_python_oracle", "reason": f"source binding failed: {error}"}
        for module_name in list(sys.modules):
            if module_name == "pyibisami" or module_name.startswith("pyibisami.") or module_name == "pybert" or module_name.startswith("pybert."):
                del sys.modules[module_name]
        source_roots = {str((PINNED / "src").resolve()), str((PINNED / "PyAMI").resolve())}
        sys.path[:] = [
            entry
            for entry in sys.path
            if not any(str(Path(entry).resolve()).startswith(root) for root in source_roots)
        ]
        sys.path[:0] = [str(extracted / "PyAMI" / "src"), str(extracted / "src")]
        try:
            parameter = importlib.import_module("pyibisami.ami.parameter")
            ami_parser = importlib.import_module("pyibisami.ami.parser")
            ibisami = importlib.import_module("pybert.utility.ibisami")
            model = importlib.import_module("pyibisami.ami.model")
        except ModuleNotFoundError as error:
            return {
                "status": "blocked_external_python_oracle",
                "reason": f"pinned dependency unavailable: {error.name}",
                "archive_sha256": archive_sha256,
                "archive_bytes": archive.stat().st_size,
                "archive_source_sha256": {
                    path: hashlib.sha256((extracted / path).read_bytes()).hexdigest()
                    for path in FILES
                },
                "python": sys.version,
                "python_executable": str(Path(sys.executable).resolve()),
            }
        source_module_names = {
            "parser": ("PyAMI/src/pyibisami/ami/parser.py", ami_parser),
            "parameter": ("PyAMI/src/pyibisami/ami/parameter.py", parameter),
            "model": ("PyAMI/src/pyibisami/ami/model.py", model),
            "ibisami": ("src/pybert/utility/ibisami.py", ibisami),
        }
        try:
            module_files = _validate_imported_modules(extracted, source_module_names)
        except (OSError, RuntimeError) as error:
            return {"status": "blocked_external_python_oracle", "reason": f"module archive validation failed: {error}"}
        declaration_text = (extracted / "models/ibisami/example_rx.ami").read_text(encoding="utf-8")
        # Exercise the pinned parser/configurator itself. This process is the
        # external oracle, not a second implementation of the materializer.
        config = ami_parser.AMIParamConfigurator(declaration_text)
        if config.ami_parsing_errors:
            return {
                "status": "blocked_external_python_oracle",
                "reason": f"pinned parser warnings/errors: {config.ami_parsing_errors}",
                "archive_sha256": archive_sha256,
                "archive_bytes": archive.stat().st_size,
            }
        # Use the pinned configurator's public Traits setter, not a hand-made
        # parameter dictionary or a direct pvalue mutation.
        config.trait_set(ctle_mode="Manual")
        params = ibisami._ads_style_ami_init_parameters(config)
        initializer = model.AMIModelInitializer(params, info_params={})
        captured = {}
        instance = model.AMIModel.__new__(model.AMIModel)
        instance._ami_mem_handle = 0
        instance._amiGetWave = object()
        instance._amiClose = lambda *_args: 1

        def fake_init(*args):
            captured["bytes"] = ctypes.cast(args[5], ctypes.c_char_p).value
            return 1

        instance._amiInit = fake_init
        instance.initialize(initializer)
        try:
            git_post = _file_identity(git_path)
            python_post = _file_identity(python_path)
        except OSError as error:
            return {"status": "blocked_external_python_oracle", "reason": f"post identity failed: {error}"}
        if git_pre != git_post or python_pre != python_post:
            return {
                "status": "blocked_external_python_oracle",
                "reason": "tool identity drift",
                "git_pre": git_pre,
                "git_post": git_post,
                "python_pre": python_pre,
                "python_post": python_post,
            }
        dependencies = {}
        for name in ("parsec", "numpy", "scipy"):
            if _distribution_present(name):
                dependency_module = importlib.import_module(name)
                dependency_path = Path(dependency_module.__file__).resolve()
                dependencies[name] = {
                    "version": importlib.metadata.version(name),
                    **_file_identity(dependency_path),
                }
        return {
            "status": "passed_external_python_oracle",
            "pinned_commit": COMMIT,
            "pinned_tree": TREE,
            "archive_sha256": archive_sha256,
            "archive_bytes": archive.stat().st_size,
            "process_policy": {"timeout_seconds": PROCESS_TIMEOUT, "timeout_action": "kill_and_reap"},
            "archive_source_sha256": {
                path: hashlib.sha256((extracted / path).read_bytes()).hexdigest()
                for path in FILES
            },
            "python": sys.version,
            "python_executable": str(python_path),
            "python_executable_pre": python_pre,
            "python_executable_post": python_post,
            "git_executable": str(git_path),
            "git_version": git_version,
            "git_executable_pre": git_pre,
            "git_executable_post": git_post,
            "dependencies": dependencies,
            "module_files": module_files,
            "bytes_hex": captured["bytes"].hex(),
            "bytes": captured["bytes"].decode("ascii"),
            "stage_values": params,
    }


def _distribution_present(name: str) -> bool:
    try:
        importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def _file_identity(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "path": str(path.resolve()),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def _validate_imported_modules(
    extracted: Path,
    source_module_names: dict[str, tuple[str, object]],
) -> dict[str, dict[str, object]]:
    archive_root = extracted.resolve()
    module_files = {}
    for name, (relative, module) in source_module_names.items():
        module_file = getattr(module, "__file__", None)
        expected_file = (extracted / relative).resolve()
        if not module_file:
            raise RuntimeError(f"module file missing: {name}")
        actual_file = Path(module_file).resolve()
        if archive_root not in actual_file.parents or actual_file != expected_file:
            raise RuntimeError(f"module archive path mismatch: {name}")
        data = actual_file.read_bytes()
        if data != expected_file.read_bytes():
            raise RuntimeError(f"module bytes drift: {name}")
        blob, raw_sha = FILES[relative]
        module_files[name] = {
            "path": relative,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "module_file": str(actual_file),
            "git_blob": blob,
            "git_source_sha256": raw_sha,
            "archive_present": True,
        }
    return module_files


if __name__ == "__main__":
    print(run())
