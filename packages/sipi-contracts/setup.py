from __future__ import annotations

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist


class BuildContracts(build_py):
    """Bundle the repository's schema source of truth without duplicating it in Git."""

    def run(self) -> None:
        super().run()
        source = Path(__file__).resolve().parents[2] / "schemas"
        if not source.is_dir():
            source = Path(__file__).resolve().parent / "src" / "sipi_contracts" / "_schemas"
        target = Path(self.build_lib) / "sipi_contracts" / "_schemas"
        shutil.copytree(source, target, dirs_exist_ok=True)


class SourceContracts(sdist):
    """Put a byte-for-byte schema snapshot in the source distribution."""

    def run(self) -> None:
        source = Path(__file__).resolve().parents[2] / "schemas"
        target = Path(__file__).resolve().parent / "src" / "sipi_contracts" / "_schemas"
        shutil.copytree(source, target, dirs_exist_ok=True)
        super().run()


setup(cmdclass={"build_py": BuildContracts, "sdist": SourceContracts})
