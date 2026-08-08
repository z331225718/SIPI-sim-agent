from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import sys

from agent_spice.backend.base import ProcessBackend


NATIVE_ENGINE_ENV = "AGENT_SPICE_NATIVE_ENGINE"


def _native_runtime_identifier(
    system: str | None = None,
    machine: str | None = None,
) -> str | None:
    system = (system or sys.platform).lower()
    machine = (machine or platform.machine()).lower()
    os_name = (
        "win"
        if system.startswith("win")
        else "linux"
        if system.startswith("linux")
        else "osx"
        if system == "darwin"
        else None
    )
    architecture = {
        "amd64": "x64",
        "x86_64": "x64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }.get(machine)
    return f"{os_name}-{architecture}" if os_name and architecture else None


def _native_engine_candidates(
    package_root: Path,
    repository_root: Path,
    runtime_identifier: str | None,
) -> list[Path]:
    windows_runtime = bool(
        runtime_identifier and runtime_identifier.startswith("win-")
    )
    rust_name = "agent-spice-sim.exe" if windows_runtime else "agent-spice-sim"
    aot_name = "AgentSpice.Engine.exe" if windows_runtime else "AgentSpice.Engine"
    workspace_root = repository_root.parents[1]
    candidates = []
    if runtime_identifier is not None:
        candidates.append(package_root / runtime_identifier / rust_name)
    candidates.extend(
        [
            package_root / rust_name,
            workspace_root
            / "native"
            / "crates"
            / "sipi-circuit"
            / "target"
            / "release"
            / rust_name,
        ]
    )
    if runtime_identifier is not None:
        candidates.append(package_root / runtime_identifier / aot_name)
    candidates.extend(
        [
            package_root / "AgentSpice.Engine.dll",
            repository_root
            / "native"
            / "AgentSpice.Engine"
            / "bin"
            / "Release"
            / "net8.0"
            / "AgentSpice.Engine.dll",
        ]
    )
    return candidates


def resolve_native_engine(explicit: str | Path | None = None) -> Path:
    configured = explicit if explicit is not None else os.environ.get(NATIVE_ENGINE_ENV)
    if configured is not None:
        candidate = Path(configured).expanduser()
    else:
        package_root = Path(__file__).resolve().parents[1] / "lib" / "native"
        runtime_identifier = _native_runtime_identifier()
        repository_root = Path(__file__).resolve().parents[3]
        candidates = _native_engine_candidates(
            package_root,
            repository_root,
            runtime_identifier,
        )
        candidate = next((item for item in candidates if item.is_file()), candidates[0])
    resolved = candidate.resolve()
    if not resolved.is_file():
        source = "--native-engine" if explicit is not None else NATIVE_ENGINE_ENV
        raise FileNotFoundError(f"native engine not found: {resolved}; build it or configure {source}")
    return resolved


@dataclass(frozen=True)
class NativeEngineBackend(ProcessBackend):
    """Run the project-owned native engine as an isolated backend process."""

    engine_path: Path
    rfm_path: Path | None = None
    rfm_subcircuit: str = "rfm_direct"
    executable: str = "dotnet"
    output_json_path: Path | None = None
    waveform_csv_path: Path | None = None

    def command_for(self, deck_path: Path) -> list[str]:
        engine = self.engine_path.resolve()
        command = (
            [self.executable, str(engine), str(deck_path.resolve())]
            if engine.suffix.lower() == ".dll"
            else [str(engine), str(deck_path.resolve())]
        )
        if self.rfm_path is not None:
            command.extend(
                ["--rfm", str(self.rfm_path.resolve()), "--rfm-subckt", self.rfm_subcircuit]
            )
        if self.output_json_path is not None:
            command.extend(["--output-json", str(self.output_json_path.resolve())])
        if self.waveform_csv_path is not None:
            command.extend(["--waveform-csv", str(self.waveform_csv_path.resolve())])
        return command
