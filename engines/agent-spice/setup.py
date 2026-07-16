from __future__ import annotations

import os
from pathlib import Path
import platform
import sys

from setuptools import setup
from wheel.bdist_wheel import bdist_wheel


platform_tag = os.environ.get("AGENT_SPICE_WHEEL_PLATFORM_TAG")
runtime_identifier = os.environ.get("AGENT_SPICE_WHEEL_RID")
if not platform_tag and not runtime_identifier and sys.platform.startswith("win"):
    architecture = {
        "amd64": ("win-x64", "win_amd64"),
        "x86_64": ("win-x64", "win_amd64"),
        "arm64": ("win-arm64", "win_arm64"),
        "aarch64": ("win-arm64", "win_arm64"),
    }.get(platform.machine().lower())
    if architecture:
        executable = "agent-spice-sim.exe" if sys.platform.startswith("win") else "agent-spice-sim"
        candidate = Path("src/agent_spice/lib/native") / architecture[0] / executable
        if candidate.is_file():
            runtime_identifier, platform_tag = architecture


class AgentSpicePlatformWheel(bdist_wheel):
    def finalize_options(self) -> None:
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self) -> tuple[str, str, str]:
        if not platform_tag:
            return super().get_tag()
        return "py3", "none", platform_tag


package_data = ["lib/ngspice/*.cm", "lib/ngspice/*.txt"]
if platform_tag and runtime_identifier:
    native_executable = (
        "agent-spice-sim.exe"
        if runtime_identifier.startswith("win-")
        else "agent-spice-sim"
    )
    package_data.append(f"lib/native/{runtime_identifier}/{native_executable}")

setup(
    package_data={"agent_spice": package_data},
    include_package_data=False,
    cmdclass={"bdist_wheel": AgentSpicePlatformWheel} if platform_tag else {},
)
