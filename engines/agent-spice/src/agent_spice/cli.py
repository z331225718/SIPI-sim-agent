from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import TYPE_CHECKING

from agent_spice.deck.builder import write_case_artifacts
from agent_spice.hspice.alter import split_alter_cases
from agent_spice.hspice.converter import convert_hspice_deck
from agent_spice.project import prepare_run_directory

if TYPE_CHECKING:
    from agent_spice.backend.xyce import XyceXdmRunResult


def _run_backend(backend_name: str, deck_path: Path, run_dir: Path):
    if backend_name == "ngspice":
        from agent_spice.backend.ngspice import NgspiceBackend

        return NgspiceBackend().run(deck_path, cwd=run_dir)
    if backend_name == "xyce":
        from agent_spice.backend.xyce import XyceBackend

        return XyceBackend().run(deck_path, cwd=run_dir)
    raise ValueError(f"Unsupported backend '{backend_name}'")


def _write_xyce_xdm_summary(run_dir: Path, result: "XyceXdmRunResult") -> None:
    summary = {
        "backend": "xyce-xdm",
        "ok": result.ok,
        "returncode": result.returncode,
        "stages": {
            "xdm": {
                "ok": result.xdm.ok,
                "returncode": result.xdm.returncode,
                "stdout": "xdm.stdout.log",
                "stderr": "xdm.stderr.log",
            },
            "xyce": None
            if result.xyce is None
            else {
                "ok": result.xyce.ok,
                "returncode": result.xyce.returncode,
                "stdout": "xyce.stdout.log",
                "stderr": "xyce.stderr.log",
            },
        },
    }
    (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _stable_source_path(deck_path: Path) -> str:
    if not deck_path.is_absolute():
        return deck_path.as_posix()
    try:
        return deck_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return deck_path.name


def _case_metadata(deck_id: str, case_name: str) -> tuple[str, str | None]:
    suffix = case_name.removeprefix(f"{deck_id}__")
    if suffix == "base":
        return "base", None
    match = re.fullmatch(r"alter_\d{3}(?:_(?P<label>.+))?", suffix)
    if match:
        return "alter", match.group("label")
    return "case", suffix or None


def run_hspice(deck_path: Path, backend_name: str, output_root: Path, execute: bool = False) -> int:
    source = deck_path.read_text(encoding="utf-8")
    deck_id = deck_path.stem
    source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    source_path = _stable_source_path(deck_path)
    cases = split_alter_cases(source, stem=deck_path.stem)
    for case in cases:
        conversion = convert_hspice_deck(case.text, backend=backend_name)
        case_kind, alter_label = _case_metadata(deck_id, case.name)
        conversion.report.set_deck(deck_id=deck_id, source=source_path, sha256=source_hash)
        conversion.report.set_case(name=case.name, kind=case_kind, alter_label=alter_label)
        run_dir = prepare_run_directory(output_root, project_name=deck_id, case_name=case.name)
        artifacts = write_case_artifacts(run_dir, conversion.deck_text, conversion.report)
        hspice_case_path = run_dir / "case.sp"
        if backend_name == "xyce-xdm":
            hspice_case_path.write_text(case.text, encoding="utf-8")
        if execute:
            if backend_name == "xyce-xdm":
                from agent_spice.backend.xyce import XyceBackend

                result = XyceBackend().run_hspice_via_xdm(hspice_case_path, artifacts.deck_path, cwd=run_dir)
                _write_xyce_xdm_summary(run_dir, result)
                if not result.ok:
                    return result.returncode
                continue
            result = _run_backend(backend_name, artifacts.deck_path, run_dir)
            (run_dir / "stdout.log").write_text(result.stdout, encoding="utf-8")
            (run_dir / "stderr.log").write_text(result.stderr, encoding="utf-8")
            if not result.ok:
                return result.returncode
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agent-spice")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run-hspice")
    run_parser.add_argument("deck", type=Path)
    run_parser.add_argument("--backend", choices=["ngspice", "xyce", "xyce-xdm"], default="ngspice")
    run_parser.add_argument("--output-root", type=Path, default=Path("runs"))
    run_parser.add_argument("--execute", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "run-hspice":
        return run_hspice(args.deck, args.backend, args.output_root, args.execute)
    raise ValueError(f"Unsupported command '{args.command}'")


if __name__ == "__main__":
    raise SystemExit(main())
