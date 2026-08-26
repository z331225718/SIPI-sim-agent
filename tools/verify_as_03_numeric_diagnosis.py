"""Verify the immutable AS-03 physical numeric checkpoint and integrity gate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import struct
import subprocess
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import yaml

try:
    import aggregate_as_03_numeric_checkpoint as checkpoint_aggregate
    import run_as_03_numeric_checkpoint as checkpoint_runner
except ModuleNotFoundError:
    from tools import aggregate_as_03_numeric_checkpoint as checkpoint_aggregate
    from tools import run_as_03_numeric_checkpoint as checkpoint_runner


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_UPSTREAM = ROOT.parent / "agent-spice"
MANIFEST = ROOT / "docs/baselines/as-03-fit-yparam-numeric-diagnosis.v1.yaml"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
TOP_KEYS = {"schema", "status", "parity_claim", "numeric_parity", "integrity_gate", "trust", "scope", "source", "physical_checkpoint", "evidence", "audit", "blockers", "non_claims"}
BLOCKERS = ["s_to_y_operation_order_divergence_before_fit", "residue_least_squares_solver_is_faer_qr_not_numpy_lstsq", "exact_cross_runtime_float_parity_requires_numpy_lapack_or_a_new_solver"]
NON_CLAIMS = ["no_external_trust_root", "no_global_numeric_parity", "no_acceptance_tolerance", "no_si_channel_s_parameter_fit", "no_as05_xyce_xdm", "no_product_or_release_promotion"]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def exact_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return set(left) == set(right) and all(exact_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(exact_equal(a, b) for a, b in zip(left, right, strict=True))
    return bool(left == right)


def _has_absolute(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_has_absolute(key) or _has_absolute(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_absolute(item) for item in value)
    return isinstance(value, str) and bool(re.search(r"(?:^[A-Za-z]:[\\/]|^//|^/)", value))


def _safe_relative(raw: Any) -> Path | None:
    if type(raw) is not str or not raw or "\0" in raw:
        return None
    host, posix, windows = Path(raw), PurePosixPath(raw), PureWindowsPath(raw)
    if host.is_absolute() or host.anchor or posix.is_absolute() or posix.anchor or windows.is_absolute() or windows.anchor or windows.drive or raw.startswith(("/", "\\")):
        return None
    parts = [part for part in re.split(r"[\\/]", raw) if part not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return Path(*parts)


def _has_reparse(path: Path) -> bool:
    current = path.absolute()
    while True:
        try:
            info = current.lstat()
        except FileNotFoundError:
            info = None
        if info is not None and (stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)):
            return True
        if current.parent == current:
            return False
        current = current.parent


def _physical_file(raw: Any, prefix: tuple[str, ...]) -> Path | None:
    relative = _safe_relative(raw)
    if relative is None or relative.parts[:len(prefix)] != prefix:
        return None
    try:
        root = ROOT.resolve(strict=True)
        path = (ROOT / relative).resolve(strict=True)
        info = path.stat()
    except OSError:
        return None
    if root not in path.parents or _has_reparse(ROOT / relative) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        return None
    return path


def _repo(path: Path) -> Path | None:
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return None
    return resolved if resolved.is_dir() and not _has_reparse(path) and (resolved / ".git").exists() else None


def _git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    env = dict(os.environ)
    for key in tuple(env):
        if key in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"} or key.startswith("GIT_CONFIG_"):
            env.pop(key, None)
    result = checkpoint_runner._bounded_process(
        ["git", "-c", "core.autocrlf=false", "-C", str(repo), *args],
        cwd=repo, env=env, timeout=300,
        stdout_limit=160 * 1024 * 1024 if binary else 1024 * 1024,
        stderr_limit=4 * 1024 * 1024,
    )
    if result.returncode != 0:
        raise RuntimeError("Git object lookup failed")
    return result.stdout if binary else result.stdout.decode("ascii").strip()


def _validate_source(repository: Path, source: dict[str, Any]) -> bool:
    try:
        commit, tree, files = source["commit"], source["tree"], source["files"]
        if type(commit) is not str or type(tree) is not str or not HEX40.fullmatch(commit) or not HEX40.fullmatch(tree) or str(_git(repository, "rev-parse", f"{commit}^{{tree}}")) != tree or type(files) is not list:
            return False
        for item in files:
            if type(item) is not dict or set(item) != {"path", "git_blob", "bytes", "sha256"} or type(item["bytes"]) is not int or type(item["git_blob"]) is not str or type(item["sha256"]) is not str:
                return False
            relative = _safe_relative(item["path"])
            if relative is None:
                return False
            blob = str(_git(repository, "rev-parse", f"{commit}:{relative.as_posix()}"))
            content = _git(repository, "cat-file", "blob", blob, binary=True)
            if not isinstance(content, bytes) or blob != item["git_blob"] or len(content) != item["bytes"] or _sha(content) != item["sha256"]:
                return False
        archive = _git(repository, "archive", "--format=tar", commit, binary=True)
        return isinstance(archive, bytes) and exact_equal(source["archive"], {"bytes": len(archive), "sha256": _sha(archive)})
    except (KeyError, OSError, RuntimeError, subprocess.SubprocessError):
        return False


def _checkpoint_digest(checkpoint: dict[str, Any]) -> tuple[str, str] | None:
    try:
        if set(checkpoint) != {"schema", "frequency_hz", "sample_index", "ports", "condition", "matrix", "parser_receipt", "physical_f64_le_sha256", "normalized_sha256", "parser_receipt_sha256"} or checkpoint["schema"] != "sipi.as-03-s-to-y-checkpoint.v1" or type(checkpoint["frequency_hz"]) is not int or type(checkpoint["sample_index"]) is not int or type(checkpoint["ports"]) is not int or type(checkpoint["condition"]) is not str or type(checkpoint["matrix"]) is not list or len(checkpoint["matrix"]) != 4:
            return None
        raw = bytearray()
        for cell in checkpoint["matrix"]:
            if type(cell) is not dict or set(cell) != {"re", "im", "re_bits", "im_bits"} or any(type(cell[key]) is not str for key in cell):
                return None
            for name in ("re_bits", "im_bits"):
                if re.fullmatch(r"[0-9a-f]{16}", cell[name]) is None:
                    return None
                raw.extend(int(cell[name], 16).to_bytes(8, "little"))
        receipt = checkpoint["parser_receipt"]
        normalized = {"frequency_hz": checkpoint["frequency_hz"], "sample_index": checkpoint["sample_index"], "ports": checkpoint["ports"], "matrix": checkpoint["matrix"], "parser_receipt": receipt}
        if _sha(_canonical(receipt)) != checkpoint["parser_receipt_sha256"]:
            return None
        return _sha(bytes(raw)), _sha(_canonical(normalized))
    except (KeyError, TypeError, ValueError):
        return None


def _rendered_sha(value: Any) -> str:
    return _sha((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


EXPECTED_FIRST = {"row": 0, "column": 0, "component": "re", "candidate": "0.08628781899500133", "upstream": "0.08628781899500129", "delta": "4.163336342344337e-17", "delta_bits": "3c88000000000000"}
EXPECTED_MAX = {"row": 1, "column": 1, "component": "re", "candidate": "0.08628781899500135", "upstream": "0.08628781899500129", "delta": "5.551115123125783e-17", "delta_bits": "3c90000000000000"}
EXPECTED_CHECKPOINTS = {
    "candidate": {
        "physical_f64_le_sha256": "ff0167b944a031045b75d38221425586e727cd303c14a625db1b5b9ffc1e2e52",
        "normalized_sha256": "1889b0dba461fecac519bdd8b0be508c6a64e609848d668be0c065e2f3f586c5",
        "matrix": [
            {"re": "0.08628781899500133", "im": "0.00000000000000000", "re_bits": "3fb616f560a06f4d", "im_bits": "0000000000000000"},
            {"re": "-0.08418837148118918", "im": "0.00000000000000000", "re_bits": "bfb58d5e7e3717c8", "im_bits": "0000000000000000"},
            {"re": "-0.08418837148118918", "im": "0.00000000000000000", "re_bits": "bfb58d5e7e3717c8", "im_bits": "0000000000000000"},
            {"re": "0.08628781899500135", "im": "0.00000000000000000", "re_bits": "3fb616f560a06f4e", "im_bits": "0000000000000000"},
        ],
    },
    "upstream": {
        "physical_f64_le_sha256": "fb08388ada1ac60945b5c91fc9a0833367bfb0963d01b3d59a100ce6d9d7e55e",
        "normalized_sha256": "fd64c9b013b14ddb744f835901a5da2c44824ff51e01df43ecb4953a4f941951",
        "matrix": [
            {"re": "0.08628781899500129", "im": "0.00000000000000000", "re_bits": "3fb616f560a06f4a", "im_bits": "0000000000000000"},
            {"re": "-0.08418837148118914", "im": "0.00000000000000000", "re_bits": "bfb58d5e7e3717c5", "im_bits": "0000000000000000"},
            {"re": "-0.08418837148118914", "im": "0.00000000000000000", "re_bits": "bfb58d5e7e3717c5", "im_bits": "0000000000000000"},
            {"re": "0.08628781899500129", "im": "0.00000000000000000", "re_bits": "3fb616f560a06f4a", "im_bits": "0000000000000000"},
        ],
    },
}
EXPECTED_RECEIPT = {
    "fixture_sha256": "4da06c257a0f0108e4391d65f894b6bb0d62a24a8f00f82f0f0734e061f5de70",
    "fixture_bytes": 137,
    "frequency_points": 4,
    "frequency_hz": 1_000_000,
    "ports": 2,
    "reference_impedance_bits": "4049000000000000",
    "sample_matrix": [
        {"re_bits": "3f847ae147ae147b", "im_bits": "0000000000000000"},
        {"re_bits": "3fe999999999999a", "im_bits": "0000000000000000"},
        {"re_bits": "3fe999999999999a", "im_bits": "0000000000000000"},
        {"re_bits": "3f847ae147ae147b", "im_bits": "0000000000000000"},
    ],
}


def _derive_comparison(candidate: dict[str, Any], upstream: dict[str, Any]) -> dict[str, Any] | None:
    try:
        differences: list[dict[str, Any]] = []
        ports = candidate["ports"]
        if type(ports) is not int or ports != upstream["ports"] or not exact_equal(candidate["parser_receipt"], upstream["parser_receipt"]):
            return None
        for index, (left, right) in enumerate(zip(candidate["matrix"], upstream["matrix"], strict=True)):
            for component in ("re", "im"):
                if left[f"{component}_bits"] != right[f"{component}_bits"]:
                    a = struct.unpack(">d", bytes.fromhex(left[f"{component}_bits"]))[0]
                    b = struct.unpack(">d", bytes.fromhex(right[f"{component}_bits"]))[0]
                    delta = a - b
                    differences.append({"row": index // ports, "column": index % ports, "component": component, "candidate": left[component], "upstream": right[component], "delta": repr(delta), "delta_bits": struct.pack(">d", delta).hex()})
        if not differences:
            return None
        maximum = max(differences, key=lambda item: abs(struct.unpack(">d", bytes.fromhex(item["delta_bits"]))[0]))
        return {"first_lexicographic_difference": differences[0], "max_abs_difference": maximum, "differing_components": len(differences)}
    except (KeyError, TypeError, ValueError, struct.error):
        return None


def _derive_anchor(report: dict[str, Any], comparison: dict[str, Any]) -> str | None:
    try:
        checkpoint = report["checkpoint"]
        payload = {
            "fixture_receipt": report["fixture"]["parsed_receipt"],
            "candidate_commit": report["candidate"]["commit"],
            "candidate_tree": report["candidate"]["tree"],
            "upstream_commit": report["upstream"]["commit"],
            "upstream_tree": report["upstream"]["tree"],
            "candidate_physical": checkpoint["candidate"]["physical_f64_le_sha256"],
            "candidate_normalized": checkpoint["candidate"]["normalized_sha256"],
            "upstream_physical": checkpoint["upstream"]["physical_f64_le_sha256"],
            "upstream_normalized": checkpoint["upstream"]["normalized_sha256"],
            "comparison": comparison,
        }
        return _sha(_canonical(payload))
    except (KeyError, TypeError):
        return None


def verify(document: dict[str, Any] | None = None, *, candidate_repo: Path = ROOT, upstream_repo: Path = DEFAULT_UPSTREAM, physical_overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    blockers: list[str] = []
    try:
        if document is None:
            document = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return {"valid": False, "blockers": ["manifest malformed"]}
    if type(document) is not dict or set(document) != TOP_KEYS or _has_absolute(document):
        return {"valid": False, "blockers": ["manifest exact graph/path"]}
    expected_header = {"schema": "sipi.as-03-fit-yparam-numeric-diagnosis.v2", "status": "blocked_numeric_semantics", "parity_claim": False, "numeric_parity": False, "integrity_gate": "passed", "trust": {"scope": "integrity_only", "external_trust_root": False, "reciprocal_execution_anchor": True}}
    if not exact_equal({key: document.get(key) for key in expected_header}, expected_header): blockers.append("manifest header/trust")
    expected_scope = {"workflow": "fit-yparam", "y_parameter_fit": True, "si_s_parameter_fit": False, "as05_xyce_xdm": False, "fixture": {"kind": "fixed_touchstone_line_s2p_v1", "sha256": "4da06c257a0f0108e4391d65f894b6bb0d62a24a8f00f82f0f0734e061f5de70", "bytes": 137, "frequency_points": 4}}
    if not exact_equal(document.get("scope"), expected_scope): blockers.append("scope exact graph")
    if not exact_equal(document.get("blockers"), BLOCKERS) or not exact_equal(document.get("non_claims"), NON_CLAIMS): blockers.append("blockers/non-claims")
    evidence = document.get("evidence")
    if type(evidence) is not dict or set(evidence) != {"runner", "aggregator", "verifier", "mutation_test", "reports", "aggregate", "report_runs"} or type(evidence.get("report_runs")) is not int or evidence.get("report_runs") != 2 or type(evidence.get("reports")) is not list or len(evidence["reports"]) != 2:
        blockers.append("evidence exact graph")
        evidence = {}
    loaded: dict[str, Any] = {}
    for name, prefix in (("runner", ("tools",)), ("aggregator", ("tools",)), ("verifier", ("tools",)), ("mutation_test", ("tools",)), ("aggregate", ("docs", "baselines"))):
        item = evidence.get(name)
        path = _physical_file(item.get("path"), prefix) if type(item) is dict and set(item) == {"path", "sha256"} and type(item.get("sha256")) is str and HEX64.fullmatch(item["sha256"]) else None
        override_present = bool(physical_overrides and type(item) is dict and item.get("path") in physical_overrides)
        if path is None:
            blockers.append(f"physical binding:{name}")
        elif name == "aggregate":
            try:
                value = (physical_overrides or {}).get(item["path"], json.loads(path.read_text(encoding="utf-8")))
                if _rendered_sha(value) != item["sha256"]:
                    blockers.append("aggregate full graph hash")
                if not override_present and _sha(path.read_bytes()) != item["sha256"]:
                    blockers.append("physical binding:aggregate")
                loaded[name] = value
            except (UnicodeDecodeError, json.JSONDecodeError): blockers.append("aggregate malformed")
        elif _sha(path.read_bytes()) != item["sha256"]:
            blockers.append(f"physical binding:{name}")
    for index, item in enumerate(evidence.get("reports", [])):
        path = _physical_file(item.get("path"), ("docs", "baselines")) if type(item) is dict and set(item) == {"path", "sha256"} and type(item.get("sha256")) is str and HEX64.fullmatch(item["sha256"]) else None
        if path is None:
            blockers.append(f"report path:{index}"); continue
        try: value = (physical_overrides or {}).get(item["path"], json.loads(path.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError): blockers.append(f"report malformed:{index}"); continue
        override_present = bool(physical_overrides and item["path"] in physical_overrides)
        if _rendered_sha(value) != item["sha256"] or (not override_present and _sha(path.read_bytes()) != item["sha256"]):
            blockers.append(f"report full graph hash:{index}")
        loaded[f"report{index}"] = value
    aggregate = loaded.get("aggregate")
    reports = [loaded.get("report0"), loaded.get("report1")]
    if type(aggregate) is not dict or any(type(item) is not dict for item in reports):
        blockers.append("physical graph unavailable")
    else:
        for index, report in enumerate(reports):
            for error in checkpoint_aggregate.validate_report(report):
                blockers.append(f"report exact graph:{index}:{error}")
        refs = evidence.get("reports", [])
        if len(refs) == 2:
            try:
                regenerated = checkpoint_aggregate.build_aggregate(reports[0], reports[1], refs[0], refs[1])
            except RuntimeError as error:
                blockers.append(f"aggregate regeneration:{error}")
            else:
                aggregate_bytes = (json.dumps(aggregate, indent=2, sort_keys=True) + "\n").encode("utf-8")
                regenerated_bytes = (json.dumps(regenerated, indent=2, sort_keys=True) + "\n").encode("utf-8")
                if aggregate_bytes != regenerated_bytes:
                    blockers.append("aggregate bit-exact regeneration")
        expected_gate = {"schema": "sipi.as-03-numeric-physical-checkpoint-aggregate.v1", "status": "blocked_numeric_semantics", "integrity_gate": "passed", "parity_claim": False, "numeric_parity": False, "report_runs": 2}
        if set(aggregate) != checkpoint_aggregate.AGGREGATE_KEYS:
            blockers.append("aggregate exact top-level keys")
        if not exact_equal({key: aggregate.get(key) for key in expected_gate}, expected_gate): blockers.append("aggregate exact gate")
        for index, report in enumerate(reports):
            report_gate = {"schema": "sipi.as-03-numeric-physical-checkpoint.v1", "status": "blocked_numeric_semantics", "integrity_gate": "passed", "parity_claim": False, "numeric_parity": False}
            if not exact_equal({key: report.get(key) for key in report_gate}, report_gate): blockers.append(f"report exact gate:{index}")
            for side in ("candidate", "upstream"):
                checkpoint = report.get("checkpoint", {}).get(side)
                digests = _checkpoint_digest(checkpoint) if type(checkpoint) is dict else None
                if digests is None or digests != (checkpoint["physical_f64_le_sha256"], checkpoint["normalized_sha256"]): blockers.append(f"checkpoint digest:{index}:{side}")
                expected = EXPECTED_CHECKPOINTS[side]
                if digests != (expected["physical_f64_le_sha256"], expected["normalized_sha256"]) or not exact_equal(checkpoint.get("matrix") if type(checkpoint) is dict else None, expected["matrix"]):
                    blockers.append(f"expected complete matrix digest/raw representation:{index}:{side}")
            checkpoint = report.get("checkpoint", {})
            derived = _derive_comparison(checkpoint.get("candidate", {}), checkpoint.get("upstream", {})) if type(checkpoint) is dict else None
            if derived is None or not exact_equal(derived, checkpoint.get("comparison")):
                blockers.append(f"comparison recomputation:{index}")
            elif not exact_equal(derived["first_lexicographic_difference"], EXPECTED_FIRST) or not exact_equal(derived["max_abs_difference"], EXPECTED_MAX) or type(derived["differing_components"]) is not int or derived["differing_components"] != 4:
                blockers.append(f"physical residual anchor:{index}")
            derived_anchor = _derive_anchor(report, derived) if derived is not None else None
            if derived_anchor is None or derived_anchor != checkpoint.get("reciprocal_anchor_sha256"):
                blockers.append(f"reciprocal execution anchor recomputation:{index}")
            receipt = report.get("fixture", {}).get("parsed_receipt")
            if not exact_equal(receipt, checkpoint.get("candidate", {}).get("parser_receipt")) or not exact_equal(receipt, checkpoint.get("upstream", {}).get("parser_receipt")):
                blockers.append(f"fixture parser receipt cross-check:{index}")
            if not exact_equal(receipt, EXPECTED_RECEIPT):
                blockers.append(f"fixed fixture parser receipt:{index}")
        aggregate_source = {
            side: {
                "commit": aggregate.get(side, {}).get("commit"),
                "tree": aggregate.get(side, {}).get("tree"),
                "archive": aggregate.get(side, {}).get("archive"),
                "files": aggregate.get(side, {}).get("sources"),
            }
            for side in ("candidate", "upstream")
        }
        if not exact_equal(document.get("source"), aggregate_source): blockers.append("manifest/source/aggregate graph")
        checkpoint = aggregate.get("checkpoint", {})
        physical_projection = {"frequency_hz": checkpoint.get("candidate", {}).get("frequency_hz"), "sample_index": checkpoint.get("candidate", {}).get("sample_index"), "ports": checkpoint.get("candidate", {}).get("ports"), "candidate_physical_f64_le_sha256": checkpoint.get("candidate", {}).get("physical_f64_le_sha256"), "candidate_normalized_sha256": checkpoint.get("candidate", {}).get("normalized_sha256"), "upstream_physical_f64_le_sha256": checkpoint.get("upstream", {}).get("physical_f64_le_sha256"), "upstream_normalized_sha256": checkpoint.get("upstream", {}).get("normalized_sha256"), "parser_receipt_sha256": checkpoint.get("candidate", {}).get("parser_receipt_sha256"), "reciprocal_anchor_sha256": checkpoint.get("reciprocal_anchor_sha256"), "first_lexicographic_difference": checkpoint.get("comparison", {}).get("first_lexicographic_difference"), "max_abs_difference": checkpoint.get("comparison", {}).get("max_abs_difference")}
        if not exact_equal(document.get("physical_checkpoint"), physical_projection): blockers.append("physical checkpoint projection")
        for key in ("trust", "fixture", "candidate", "upstream", "checkpoint", "blockers", "non_claims"):
            report_value = reports[0].get(key)
            if key in {"candidate", "upstream"}: report_value = {name: report_value[name] for name in aggregate[key]}
            if not exact_equal(aggregate.get(key), report_value): blockers.append(f"aggregate/report reciprocal graph:{key}")
        if type(aggregate.get("reports")) is not list or len(aggregate["reports"]) != 2:
            blockers.append("aggregate report list")
        else:
            for index, item in enumerate(aggregate["reports"]):
                expected_item = {"path": evidence["reports"][index]["path"], "sha256": evidence["reports"][index]["sha256"], "run_id": reports[index].get("run_id"), "fresh_run_nonce": reports[index].get("fresh_run_nonce")}
                if not exact_equal(item, expected_item): blockers.append(f"aggregate report binding:{index}")
    candidate = _repo(candidate_repo); upstream = _repo(upstream_repo)
    source = document.get("source", {})
    if candidate is None or type(source.get("candidate")) is not dict or not _validate_source(candidate, source["candidate"]): blockers.append("candidate Git-object/archive custody")
    if upstream is None or type(source.get("upstream")) is not dict or not _validate_source(upstream, source["upstream"]): blockers.append("upstream Git-object/archive custody")
    audit = document.get("audit")
    audit_path = _physical_file(audit.get("path"), ("docs", "baselines", "audits")) if type(audit) is dict and set(audit) == {"path", "sha256"} and type(audit.get("sha256")) is str and HEX64.fullmatch(audit["sha256"]) else None
    if audit_path is None or _sha(audit_path.read_bytes()) != audit["sha256"]: blockers.append("audit binding")
    else:
        text = audit_path.read_text(encoding="utf-8")
        for anchor in ("integrity-only", "4.163336342344337e-17", "5.551115123125783e-17", "no independent external trust root", "recursive exact-type equality", "git rev-parse COMMIT:path"):
            if anchor not in text: blockers.append(f"audit anchor:{anchor}")
    return {"valid": not blockers, "blockers": blockers}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-repo", type=Path, default=ROOT)
    parser.add_argument("--upstream-repo", type=Path, default=DEFAULT_UPSTREAM)
    args = parser.parse_args()
    result = verify(candidate_repo=args.candidate_repo, upstream_repo=args.upstream_repo)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
