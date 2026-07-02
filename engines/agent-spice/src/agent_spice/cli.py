from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import TYPE_CHECKING, Any

from agent_spice.deck.builder import write_case_artifacts
from agent_spice.hspice.alter import split_alter_cases
from agent_spice.hspice.converter import convert_hspice_deck
from agent_spice.project import prepare_run_directory
from agent_spice.sparam.fitting import SParamFitConfig, fit_touchstone_to_spice

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


def _quality_gate_failure(result: Any, allow_warnings: bool) -> str | None:
    quality_report = getattr(result, "quality_report", None)
    if quality_report is None:
        return "quality gate unavailable: fit result did not include a quality report"
    status = getattr(quality_report, "status", None)
    if status == "PASS":
        return None
    if status == "WARN" and allow_warnings:
        return None

    blocking_reasons = list(getattr(quality_report, "blocking_reasons", []) or [])
    warnings = list(getattr(quality_report, "warnings", []) or [])
    reasons = blocking_reasons if status == "FAIL" else warnings
    if not reasons:
        reasons = blocking_reasons + warnings
    reason_text = ", ".join(reasons) if reasons else str(status or "unknown")
    return f"quality gate failed: status={status or 'unknown'}, reasons={reason_text}"


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

    fit_parser = subparsers.add_parser("fit-sparam")
    fit_parser.add_argument("touchstone", type=Path)
    fit_parser.add_argument("--output", type=Path, required=True)
    fit_parser.add_argument("--report", type=Path)
    fit_parser.add_argument("--html-report", type=Path)
    fit_parser.add_argument("--log", type=Path)
    fit_parser.add_argument("--mode", choices=["auto", "manual"], default="auto")
    fit_parser.add_argument("--n-poles-real", type=int, default=2)
    fit_parser.add_argument("--n-poles-cmplx", type=int, default=2)
    fit_parser.add_argument("--n-poles-init-real", type=int, default=3)
    fit_parser.add_argument("--n-poles-init-cmplx", type=int, default=3)
    fit_parser.add_argument("--n-poles-add", type=int, default=3)
    fit_parser.add_argument("--iters-start", type=int, default=3)
    fit_parser.add_argument("--iters-inter", type=int, default=3)
    fit_parser.add_argument("--iters-final", type=int, default=5)
    fit_parser.add_argument("--model-order-max", type=int, default=100)
    fit_parser.add_argument("--target-error", type=float, default=0.01)
    fit_parser.add_argument("--alpha", type=float, default=0.03)
    fit_parser.add_argument("--gamma", type=float, default=0.03)
    fit_parser.add_argument("--nu-samples", type=float, default=1.0)
    fit_parser.add_argument("--fit-max-iterations", type=int)
    fit_parser.add_argument("--passivity-samples", type=int, default=200)
    fit_parser.add_argument("--passivity-f-max", type=float)
    fit_parser.add_argument("--no-preserve-dc", action="store_true")
    fit_parser.add_argument("--fit-frequency-stride", type=int, default=1)
    fit_parser.add_argument("--fit-max-frequency-points", type=int)
    fit_parser.add_argument("--fit-f-min", type=float)
    fit_parser.add_argument("--fit-f-max", type=float)
    fit_parser.add_argument("--skip-passivity-enforce", action="store_true")
    fit_parser.add_argument("--quality-profile", choices=["explore", "signoff"], default="explore")
    fit_parser.add_argument("--fail-on-quality", action="store_true")
    fit_parser.add_argument("--max-comparison-rms-error", type=float, default=0.05)
    fit_parser.add_argument("--max-passivity-epsilon", type=float, default=1e-6)
    fit_parser.add_argument("--require-dc", action="store_true")
    fit_parser.add_argument("--allow-quality-warnings", action="store_true")
    fit_parser.add_argument("--subckt-name", default="s_equivalent")

    args = parser.parse_args(argv)
    if args.command == "run-hspice":
        return run_hspice(args.deck, args.backend, args.output_root, args.execute)
    if args.command == "fit-sparam":
        config = SParamFitConfig(
            mode=args.mode,
            n_poles_real=args.n_poles_real,
            n_poles_cmplx=args.n_poles_cmplx,
            n_poles_init_real=args.n_poles_init_real,
            n_poles_init_cmplx=args.n_poles_init_cmplx,
            n_poles_add=args.n_poles_add,
            iters_start=args.iters_start,
            iters_inter=args.iters_inter,
            iters_final=args.iters_final,
            model_order_max=args.model_order_max,
            target_error=args.target_error,
            alpha=args.alpha,
            gamma=args.gamma,
            nu_samples=args.nu_samples,
            max_iterations=args.fit_max_iterations,
            enforce_passivity=not args.skip_passivity_enforce,
            passivity_samples=args.passivity_samples,
            passivity_f_max=args.passivity_f_max,
            preserve_dc=not args.no_preserve_dc,
            fit_frequency_stride=args.fit_frequency_stride,
            fit_max_frequency_points=args.fit_max_frequency_points,
            fit_f_min=args.fit_f_min,
            fit_f_max=args.fit_f_max,
            quality_profile=args.quality_profile,
            max_comparison_rms_error=args.max_comparison_rms_error,
            max_passivity_epsilon=args.max_passivity_epsilon,
            require_dc=args.require_dc,
            subckt_name=args.subckt_name,
        )
        report_path = args.report or (args.output.parent / "fit_report.json")
        html_report_path = args.html_report or (args.output.parent / "fit_report.html")
        try:
            result = fit_touchstone_to_spice(
                args.touchstone,
                args.output,
                config=config,
                report_path=report_path,
                html_report_path=html_report_path,
                log_path=args.log,
            )
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        if args.fail_on_quality:
            failure = _quality_gate_failure(result, allow_warnings=args.allow_quality_warnings)
            if failure is not None:
                print(f"error: {failure}", file=sys.stderr)
                return 1
        return 0
    raise ValueError(f"Unsupported command '{args.command}'")


if __name__ == "__main__":
    raise SystemExit(main())
