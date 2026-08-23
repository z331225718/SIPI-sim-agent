"""Run one bounded two-replay AS-02..AS-06 direct-port corpus.

The temporary corpus is synthetic and only exercises the Rust direct leaf;
it is not an upstream numerical oracle.  Absolute run roots are normalized
before hashing so two independent executions can be compared honestly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "2cc92316c2fb89a159f18fcb1ff2ba249f0e22f5"
TREE = "b6bde97128030d6cea0d68b2f0a35d807be8c402"
RUN_TIMEOUT_SECONDS = 60
CORPUS = {
    "AS-02": [
        "two_block_ordered_intersection",
        "priority_band_refit",
        "malformed_manifest",
        "zero_forward_transmission",
    ],
    "AS-03": [
        "well_conditioned_two_port",
        "nport_exact_html",
        "ill_conditioned_i_plus_s",
        "unsupported_exact_rfm",
    ],
    "AS-04": [
        "valid_nelder_mead_external_stub",
        "invalid_csv",
        "duplicate_rfm_token",
        "missing_hspice_measure",
        "external_hspice_blocker",
    ],
    "AS-05": [
        "alter_case_preparation",
        "ngspice_conversion_and_dependencies",
        "s_element_preflight",
        "unsupported_directive_block",
        "external_backend_required",
    ],
    "AS-06": [
        "one_port_real_pole",
        "response_union_poles",
        "nested_dependency_staging",
        "terminal_end_star_comment",
        "nonzero_delay_rejection",
        "missing_response_block",
    ],
}


def _cargo() -> str:
    return os.environ.get("CARGO") or shutil.which("cargo") or str(Path.home() / ".cargo" / "bin" / "cargo.exe")


def _write_common(root: Path) -> dict[str, Path]:
    s2p = root / "line.s2p"
    s2p.write_text(
        "# Hz S RI R 50\n"
        "1e6 0.01 0 0.8 0 0.8 0 0.01 0\n"
        "1e7 0.01 0 0.79 0 0.79 0 0.01 0\n"
        "1e8 0.01 0 0.7 0 0.7 0 0.01 0\n"
        "1e9 0.01 0 0.4 0 0.4 0 0.01 0\n",
        encoding="ascii",
    )
    return {"s2p": s2p}


def _write_rfm(root: Path, nports: int = 1, *, delay: str = "0", omit_last: bool = False) -> Path:
    path = root / "model.rfm"
    lines = ["VERSION 200600", f"NPORT {nports}", "MATRIX_TYPE S", "Z0 50"]
    for row in range(1, nports + 1):
        for column in range(1, nports + 1):
            if omit_last and row == nports and column == nports:
                continue
            if nports == 2:
                real_count = 1 if (row + column) % 2 == 0 else 2
                real_rows = ["1 0.01"] + (["2 0.005"] if real_count == 2 else [])
                lines.extend([f"BEGIN {row} {column}", "CONST 0", "C 0", f"DELAY {delay}", f"BEGIN_REAL {real_count}", *real_rows, "BEGIN_COMPLEX 0", "END"])
            else:
                lines.extend([f"BEGIN {row} {column}", "CONST 0", "C 0", f"DELAY {delay}", "BEGIN_REAL 1", "1 0.01", "BEGIN_COMPLEX 0", "END"])
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path


def _write_touchstone(root: Path, name: str, *, zero_forward: bool = False, ill_conditioned: bool = False) -> Path:
    path = root / name
    if ill_conditioned:
        rows = (
            "1e6 -1 0 0 0 0 0 -1 0\n"
            "1e7 -1 0 0 0 0 0 -1 0\n"
        )
    elif zero_forward:
        rows = (
            "1e6 0.01 0 0 0 0.8 0 0 0\n"
            "1e7 0.01 0 0 0 0.79 0 0 0\n"
            "1e8 0.01 0 0 0 0.7 0 0 0\n"
            "1e9 0.01 0 0 0 0.4 0 0 0\n"
        )
    else:
        rows = (
            "1e6 0.01 0 0.8 0 0.8 0 0.01 0\n"
            "1e7 0.01 0 0.79 0 0.79 0 0.01 0\n"
            "1e8 0.01 0 0.7 0 0.7 0 0.01 0\n"
            "1e9 0.01 0 0.4 0 0.4 0 0.01 0\n"
        )
    path.write_text("# Hz S RI R 50\n" + rows, encoding="ascii")
    return path


def _write_nport_touchstone(root: Path, name: str, ports: int) -> Path:
    values = " ".join("0" for _ in range(2 * ports * ports))
    path = root / name
    path.write_text(f"# GHz S RI R 50\n0.1 {values}\n1.0 {values}\n", encoding="ascii")
    return path


def _hspice_stub(root: Path, *, emit_measure: bool) -> Path:
    path = root / "fake_hspice.cmd"
    measure = "echo rms = 1.0e-3>>%~3.lis" if emit_measure else "echo listing>>%~3.lis"
    path.write_text(f"@echo off\n{measure}\nexit /b 0\n", encoding="ascii")
    return path


def _prepare_case(row: str, case_id: str, root: Path) -> tuple[list[str], str, int]:
    common = _write_common(root)
    if row == "AS-02":
        if case_id in {"two_block_ordered_intersection", "priority_band_refit"}:
            touchstone = common["s2p"]
        elif case_id == "malformed_manifest":
            manifest = root / "cascade.json"
            manifest.write_text(json.dumps({"version": 2}), encoding="utf-8")
            return [str(manifest), "--output-root", str(root / "out")], "sipi-agent-spice-fit-sparam-cascade", 2
        else:
            touchstone = _write_touchstone(root, "zero.s2p", zero_forward=True)
        manifest = root / "cascade.json"
        manifest.write_text(json.dumps({"version": 1, "blocks": [{"name": "a", "touchstone": touchstone.name}, {"name": "b", "touchstone": touchstone.name}], "cascade": ["a", "b"]}), encoding="utf-8")
        args = [str(manifest), "--output-root", str(root / "out"), "--rms-target", "1", "--max-order", "1", "--min-order", "1", "--max-order-step", "1", "--cascade-samples", "8"]
        if case_id == "priority_band_refit":
            args.extend(["--priority-band", "1e6:1e9:1", "--priority-band-fit-only", "--cascade-rms-target", "1", "--cascade-refit-max-iterations", "1"])
        return args, "sipi-agent-spice-fit-sparam-cascade", 0 if case_id in {"two_block_ordered_intersection", "priority_band_refit"} else 2
    if row == "AS-03":
        if case_id == "well_conditioned_two_port":
            touchstone = common["s2p"]
            expected = 0
        elif case_id == "nport_exact_html":
            touchstone = _write_nport_touchstone(root, "network.s3p", 3)
            expected = 0
        elif case_id == "ill_conditioned_i_plus_s":
            touchstone = _write_touchstone(root, "ill.s2p", ill_conditioned=True)
            expected = 2
        else:
            touchstone = common["s2p"]
            expected = 2
        args = [str(touchstone), "--output", str(root / "out.y.sp"), "--report", str(root / "out.y.json"), "--derived-s-touchstone", str(root / "out.s2p"), "--max-order", "1", "--n-poles-real", "1", "--n-poles-cmplx", "0", "--fit-iterations", "2", "--max-y-rms-siemens", "100", "--passivity", "off"]
        if case_id == "unsupported_exact_rfm":
            args.extend(["--exact-s-rfm", str(root / "out.rfm")])
        elif case_id == "nport_exact_html":
            args.extend(["--no-fit-proportional", "--html-report", str(root / "out.html"), "--exact-s-rfm", str(root / "out.rfm"), "--exact-s-touchstone", str(root / "out.exact.s3p")])
        return args, "sipi-agent-spice-fit-yparam", expected
    if row == "AS-04":
        rfm = _write_rfm(root, nports=2)
        deck = root / "signoff.sp"
        deck.write_text("Xrfm p1 p2 model.rfm\n.end\n", encoding="ascii")
        args = [str(common["s2p"]), str(rfm), str(deck), "--output-rfm", str(root / "out.rfm"), "--work-dir", str(root / "work"), "--rfm-token", "model.rfm", "--rms-measure", "rms", "--residual-poles", "1,2", "--band-boundaries", "1.5", "--hspice-bin", "sipi-no-such-hspice"]
        # Actual HSPICE execution is deliberately fail-closed until the
        # caller supplies an attested executable identity.  Keep the valid
        # optimizer corpus as an external-custody observation, not a fake
        # solver parity claim.
        expected = 2
        if case_id == "valid_nelder_mead_external_stub":
            args[args.index("--hspice-bin") + 1] = str(_hspice_stub(root, emit_measure=True))
        elif case_id == "invalid_csv":
            args[args.index("--residual-poles") + 1] = "1,not-a-number"
        elif case_id == "duplicate_rfm_token":
            deck.write_text("Xrfm p1 p2 model.rfm\nXrfm2 p1 p2 model.rfm\n.end\n", encoding="ascii")
        elif case_id == "missing_hspice_measure":
            args[args.index("--hspice-bin") + 1] = str(_hspice_stub(root, emit_measure=False))
        return args, "sipi-agent-spice-tune-yparam-tran", expected
    if row == "AS-05":
        deck = root / "deck.sp"
        if case_id == "unsupported_directive_block":
            deck.write_text(".fft v(out)\n.end\n", encoding="ascii")
        elif case_id == "s_element_preflight":
            # The native preflight starts at the upstream default order and
            # therefore needs enough rows for its bounded least-squares basis;
            # keep this fixed corpus case numerically valid instead of making
            # a four-sample deck look like an algorithm failure.
            touchstone = root / "line.s2p"
            rows = "".join(
                f"{1e6 * (index + 1):.6e} 0.01 0 0.2 0 0.2 0 0.01 0\n"
                for index in range(64)
            )
            touchstone.write_text("# Hz S RI R 50\n" + rows, encoding="ascii")
            deck.write_text(
                ".model sw sw(Ron=1 Roff=2)\n"
                "S1 p1 p2 0 TSTONEFILE=line.s2p\n"
                ".endcomment source audit marker\n"
                ".end\n",
                encoding="ascii",
            )
        elif case_id == "ngspice_conversion_and_dependencies":
            (root / "models").mkdir()
            (root / "models" / "top.inc").write_text(".include 'nested.inc'\n.param r=1\n", encoding="ascii")
            (root / "models" / "nested.inc").write_text(".param c=1u\n", encoding="ascii")
            deck.write_text(".inc 'models/top.inc'\n.probe tran v(out)\n.option post=2\n.tran 1p 1n\n.end\n", encoding="ascii")
        else:
            deck.write_text(".param r=1\n.tran 1p 1n\n.alter high\n.param r=2\n.end\n", encoding="ascii")
        backend = "ngspice" if case_id in {"ngspice_conversion_and_dependencies", "s_element_preflight"} else "native"
        args = [str(deck), "--backend", backend, "--output-root", str(root / "out")]
        expected = 1 if case_id in {"unsupported_directive_block", "s_element_preflight"} else 0
        if case_id == "external_backend_required":
            args.extend(["--execute", "--native-engine", str(root / "missing-engine.exe")])
            expected = 2
        return args, "sipi-agent-spice-run-hspice", expected
    if row == "AS-06":
        if case_id == "one_port_real_pole":
            rfm = _write_rfm(root, nports=1)
            expected = 0
        elif case_id == "response_union_poles":
            rfm = _write_rfm(root, nports=2)
            expected = 0
        elif case_id == "nested_dependency_staging":
            rfm = _write_rfm(root, nports=1)
            (root / "models").mkdir()
            (root / "models" / "top.inc").write_text(".include 'nested.inc'\n", encoding="ascii")
            (root / "models" / "nested.inc").write_text("* nested\n", encoding="ascii")
            expected = 0
        elif case_id == "terminal_end_star_comment":
            rfm = _write_rfm(root, nports=1)
            expected = 0
        elif case_id == "nonzero_delay_rejection":
            rfm = _write_rfm(root, nports=1, delay="1")
            expected = 2
        else:
            rfm = _write_rfm(root, nports=2, omit_last=True)
            expected = 2
        deck = root / "deck.sp"
        deck_text = "Xrfm p1 rfm_direct\n.end\n"
        if case_id == "nested_dependency_staging":
            deck_text = ".include 'models/top.inc'\n" + deck_text
        elif case_id == "terminal_end_star_comment":
            deck_text = "Xrfm p1 rfm_direct\n.end*comment preserved\n"
        deck.write_text(deck_text, encoding="ascii")
        return [str(deck), "--rfm", str(rfm), "--backend", "native", "--output-root", str(root / "out")], "sipi-agent-spice-run-rfm", expected
    raise ValueError(f"unsupported row {row}")


def _hash_tree(root: Path) -> tuple[str, list[str]]:
    digest = hashlib.sha256()
    files: list[str] = []
    # Reports serialize Windows paths through JSON, so the backslashes are
    # escaped in the bytes on disk.  Normalize all three representations of
    # the temporary root before comparing independent replays.
    root_tokens = {
        str(root).encode(),
        str(root).replace("\\", "/").encode(),
        str(root).replace("\\", "\\\\").encode(),
    }
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        data = path.read_bytes()
        for token in root_tokens:
            data = data.replace(token, b"<RUN_ROOT>")
        data = data.replace(b"\\", b"/")
        digest.update(relative.encode() + b"\0" + data)
        files.append(relative)
    return digest.hexdigest(), files


def replay(row: str, run_root: Path) -> dict[str, Any]:
    case_results = []
    cases_root = run_root / "cases"
    cases_root.mkdir(parents=True, exist_ok=True)
    for case_id in CORPUS[row]:
        case_root = cases_root / case_id
        case_root.mkdir(parents=True, exist_ok=True)
        args, binary, expected_returncode = _prepare_case(row, case_id, case_root)
        command = [_cargo(), "run", "--quiet", "--manifest-path", str(ROOT / "crates/sipi-agent-spice-direct/Cargo.toml"), "--bin", binary, "--"] + args
        try:
            completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False, timeout=RUN_TIMEOUT_SECONDS)
            returncode = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
        except subprocess.TimeoutExpired as error:
            returncode = 124
            stdout = error.stdout or ""
            stderr = error.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            stderr += f"runner timeout after {RUN_TIMEOUT_SECONDS}s"
        case_results.append({
            "case": case_id,
            "binary": binary,
            "expected_returncode": expected_returncode,
            "returncode": returncode,
            "stdout": stdout[-2048:],
            "stderr": stderr[-2048:],
            "expected_result": returncode == expected_returncode,
        })
    digest, files = _hash_tree(run_root)
    return {
        "binary": "multi-case",
        "binaries": sorted({case["binary"] for case in case_results}),
        "returncode": case_results[0]["returncode"],
        "stdout": "\n".join(f"{case['case']}: {case['stdout']}" for case in case_results)[-4096:],
        "stderr": "\n".join(f"{case['case']}: {case['stderr']}" for case in case_results)[-4096:],
        "cases": case_results,
        "tree_sha256": digest,
        "files": files,
    }


def run(row: str, output: Path | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"sipi-{row.lower()}-") as first, tempfile.TemporaryDirectory(prefix=f"sipi-{row.lower()}-") as second:
        runs = [replay(row, Path(first)), replay(row, Path(second))]
        # Keep independent report payloads distinguishable even when the leaf
        # emits no absolute path in stdout/stderr.  The nonce binds this
        # report to its fresh temporary execution roots without entering the
        # content-addressed artifact hash.
        replay_instance = hashlib.sha256(f"{first}\0{second}".encode("utf-8")).hexdigest()
    payload = {"schema": f"sipi.agent-spice-{row.lower()}-replay.v1", "workflow": row, "upstream": {"commit": COMMIT, "tree": TREE}, "corpus": CORPUS[row], "runs": runs, "replay_instance_sha256": replay_instance, "corpus_expected": all(case.get("expected_result") is True for run_record in runs for case in run_record.get("cases", [])), "binding_status": "unbound_preparation_observation", "content_addressed_replay": False, "immutable_source_binding": False, "parity_status": "open", "numeric_comparison": "not_claimed"}
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("row", choices=["AS-02", "AS-03", "AS-04", "AS-05", "AS-06"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = run(args.row, args.output)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["corpus_expected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
