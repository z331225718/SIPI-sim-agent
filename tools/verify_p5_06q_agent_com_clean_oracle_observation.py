"""Verify the additive P5-06q clean Agent-COM observation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "baselines" / "p5-06q-agent-com-clean-oracle-observation.v1.yaml"
AUDIT = ROOT / "docs" / "baselines" / "audits" / "2026-08-21-p5-06q-agent-com-clean-oracle-observation.md"
SCHEMA = "sipi.p5-06q.agent-com-clean-oracle-observation.v1"
AUDIT_BINDING = {
    "path": "docs/baselines/audits/2026-08-21-p5-06q-agent-com-clean-oracle-observation.md",
    "sha256": "76ac8cdcb38e56d72b30f68045e6af9247d668a5574c79bb3981f1502be248c6",
}
COMMIT = "5272ffe74702cd585054d975559b06f8afae7b6e"
TREE = "7094ab6e84989b218730c52432c70da10261f8ea"
OBJECTS = [
    ("src/agent_com/api.py", "3e7808982a63123f2bac65a86f3abb627c287be1", 21445, "b7527f60d55b6f73fb449bc2472f957a6bc2a9ecf1d7bc8808756bf7fba39570"),
    ("src/agent_com/_orchestration.py", "5d260a0aab941f1a1955fe3abef36d85a56034c0", 90877, "069a5c08f9da6ad5b5be5648723eb05b0e3de8cf0dcb1ae7f54e23df7ab0db69"),
    ("src/agent_com/metrics/tdiln.py", "53aacf1c15b57cf314f0e7db5148884bf7afe3c2", 7068, "d0465246f6fd5d22d5978f5cdf2a78f7fccdfbfdd7ad0676092b4494d3698873"),
    ("src/agent_com/config/consumption.py", "50fc02d837a67f3b503a73672ec4fbcc40d39b73", 210466, "c6202e42b5e5ccb7fa1f78c780b9ecf031af5400b35cd23f20ef7348207d28a7"),
    ("src/agent_com/config/materialize.py", "a8856f91fe9208738446f539aa52ade2ea2c0bcf", 19030, "42f85e3cd5df74158acc10b9388f663419740b374756cdbd8332f052063d265c"),
    ("src/agent_com/config/excel.py", "1cce4365b64f3bb0ef1f7617107d2df4c929afc7", 12218, "2886e9986b9c3a7c1fbdc6179878679ae26bb92f511c6b0689644f9a6c053c4d"),
    ("src/agent_com/models.py", "92167e385db50c76a9999c2df5118d46951b8243", 6994, "e97bd1c67fbf53f940e45fb94905e6bd5e924b164a3eecf1548a652ba0f327af"),
    ("schemas/r480-capability-envelope-v1.yaml", "69aeffa675341733277ccaf19a8e878cb716a315", 9636, "9b3329e25559e595187ae1a0530785d5a8dbbdc02a035eeb44326aa91ee34b73"),
    ("schemas/legacy-output-r480.json", "7980dcffb5a88557b8cb2e8107fae06355c91169", 2121, "aa74317a43a7152c7ed3937a04093e6c84d5583652ca4d9af2ac0fed98ad9ea6"),
]
LICENSE_OBJECTS = [
    ("LICENSE", "55aac2e4f8c36a978d315efb02815972579b8293", 1067, "d0807e4df734f0fadc658f4ea3be7bfe4b81c3e85a2b053b069a23189c6034c2"),
    ("LICENSE-MANIFEST.md", "07cf6a6a59f7d06c18b242af4f6c359c7ea68686", 5911, "48f3e22c2b1a0ec558f28fb56ed41e3b76eb6c6192cddf3dea8a0adc5493ec65"),
]
ABSOLUTE = re.compile(r"(?:^|[^A-Za-z0-9])[A-Za-z]:[\\/]|(?:^|[^A-Za-z0-9])/(?:home|Users|private|tmp|mnt)/")


class ObservationError(RuntimeError):
    """Raised when the pinned observation shape is not exact."""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ObservationError(reason)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _walk(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from _walk(key)
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _load(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "document_not_mapping")
    return value


def _git(source_root: Path, *args: str, binary: bool = False) -> str | bytes:
    result = subprocess.run(["git", "-C", str(source_root), *args], capture_output=True, check=False)
    _require(result.returncode == 0, "git_object_lookup_failed")
    return result.stdout if binary else result.stdout.decode("ascii").strip()


def _verify_objects(source_root: Path) -> None:
    _require(source_root.is_dir(), "source_root_invalid")
    _require(_git(source_root, "rev-parse", f"{COMMIT}^{{commit}}") == COMMIT, "commit_mismatch")
    _require(_git(source_root, "rev-parse", f"{COMMIT}^{{tree}}") == TREE, "tree_mismatch")
    for path, oid, byte_count, digest in [*OBJECTS, *LICENSE_OBJECTS]:
        ref = f"{COMMIT}:{path}"
        _require(_git(source_root, "rev-parse", ref) == oid, f"blob_mismatch:{path}")
        payload = _git(source_root, "cat-file", "blob", ref, binary=True)
        assert isinstance(payload, bytes)
        _require(len(payload) == byte_count, f"byte_count_mismatch:{path}")
        _require(hashlib.sha256(payload).hexdigest() == digest, f"content_hash_mismatch:{path}")


def validate_document(document: dict[str, Any] | None = None, source_root: Path | str | None = None) -> dict[str, Any]:
    document = _load(EVIDENCE) if document is None else document
    _require(document.get("schema") == SCHEMA, "schema_invalid")
    _require(document.get("status") == "blocked_missing_td_iln_scalar_and_compare_contract", "status_invalid")
    _require(document.get("authority") == "pinned_external_observation_only", "authority_invalid")
    _require(document.get("invocation", {}).get("commit") == COMMIT, "invocation_commit_invalid")
    _require(document.get("invocation", {}).get("tree") == TREE, "invocation_tree_invalid")
    _require(document.get("invocation", {}).get("profile") == "r480", "profile_invalid")
    _require(document.get("invocation", {}).get("diagnostics") is False, "diagnostics_must_be_false")
    _require(
        document.get("invocation", {}).get("entrypoint")
        == {
            "load_config": "load_config(config_path, overrides={'COMPUTE_TDILN': 1})",
            "run": "run_com(config=loaded, channels=ChannelSet(thru), options=RunOptions(loaded.profile, diagnostics=False))",
        },
        "entrypoint_invalid",
    )
    _require(
        document.get("inputs", {}).get("workbook")
        == {
            "path": "matlab_src/config_sheets_100G/config_com_ieee8023_93a=3ck_SA_120F_C2C_08_17_2022.xlsx",
            "bytes": 67087,
            "sha256": "e676b3fb3cb3048f80c98deaa8faca1d03c13daa216c6259de26885e715ca925",
        },
        "workbook_binding_invalid",
    )
    _require(
        document.get("inputs", {}).get("channels")
        == [
            {
                "role": "THRU",
                "path": "fixtures/synthetic/thru_10db_at_26p56ghz.s4p",
                "bytes": 6425196,
                "sha256": "b14a92e7f844608aaee5b4cbd3dfda08d7af48bfedb4526043a0733b8823e584",
            }
        ],
        "channel_binding_invalid",
    )
    _require(document.get("runs", {}).get("count") == 2, "run_count_invalid")
    _require(document.get("runs", {}).get("case_count") == 2, "case_count_invalid")
    payloads = document.get("runs", {}).get("payloads", [])
    _require(len(payloads) == 2, "payload_count_invalid")
    _require({item.get("bytes") for item in payloads} == {51793}, "payload_bytes_invalid")
    _require({item.get("sha256") for item in payloads} == {"2aa43d7487d7481a9d4463d7e69e7a397cc5bf30efcfad6cb0239d43f7dfae54"}, "payload_hash_invalid")
    cases = document.get("runs", {}).get("cases", [])
    _require([item.get("case_index") for item in cases] == [0, 1], "case_order_invalid")
    _require(cases[0].get("COM_dB") == 6.680468404393122, "case0_com_invalid")
    _require(cases[1].get("COM_dB") == 6.8626430506219, "case1_com_invalid")
    for case in cases:
        _require(
            all(case.get(key) in ("Infinity", float("inf")) for key in ("ERL_dB", "ERL11_dB", "ERL22_dB")),
            "erl_observation_invalid",
        )
    _require(document.get("runs", {}).get("missing_scalar_fields") == ["TD_ILN_dB", "TD_ILN"], "td_iln_missing_surface_invalid")
    non_sub = document.get("runs", {}).get("observed_non_substitutes", {})
    _require(non_sub.get("FOM_TDILN", {}).get("allowed_as_TD_ILN_dB") is False, "fom_alias_guard_invalid")
    _require(non_sub.get("ICN_mV", {}).get("allowed_as_TD_ILN_dB") is False, "icn_alias_guard_invalid")
    _require(non_sub.get("iln_vector", {}).get("allowed_as_TD_ILN_dB") is False, "iln_alias_guard_invalid")
    required = document.get("required_metrics", [])
    _require(
        required
        == [
            {"id": "COM_dB", "source_fields": ["COM_dB"], "unit": "dB", "status": "observed_scalar"},
            {"id": "ERL_dB", "source_fields": ["ERL"], "unit": "dB", "status": "observed_nonfinite_in_both_cases"},
            {"id": "TD_ILN_dB", "source_fields": ["TD_ILN"], "unit": "dB", "status": "missing_scalar"},
        ],
        "required_metric_surface_invalid",
    )
    tolerance = document.get("comparison_boundary", {}).get("owner_absolute_tolerance_db")
    _require(tolerance == {"COM_dB": 0.1, "ERL_dB": 0.1, "TD_ILN_dB": 0.1}, "owner_tolerance_invalid")
    _require(document.get("comparison_boundary", {}).get("checkpoint_policy") == "strict_same_checkpoint_no_alignment", "checkpoint_policy_invalid")
    _require(document.get("comparison_boundary", {}).get("alignment_or_interpolation") is False, "alignment_policy_invalid")
    allowlist = document.get("licensing", {}).get("allowlist", [])
    _require(
        [(item.get("path"), item.get("git_blob"), item.get("bytes"), item.get("sha256")) for item in allowlist]
        == OBJECTS,
        "allowlist_invalid",
    )
    _require(
        document.get("licensing", {}).get("root_license")
        == {
            "path": "LICENSE",
            "kind": "MIT",
            "git_blob": LICENSE_OBJECTS[0][1],
            "bytes": LICENSE_OBJECTS[0][2],
            "sha256": LICENSE_OBJECTS[0][3],
        },
        "root_license_invalid",
    )
    _require(
        document.get("licensing", {}).get("manifest")
        == {
            "path": "LICENSE-MANIFEST.md",
            "git_blob": LICENSE_OBJECTS[1][1],
            "bytes": LICENSE_OBJECTS[1][2],
            "sha256": LICENSE_OBJECTS[1][3],
        },
        "license_manifest_invalid",
    )
    _require(document.get("audit") == AUDIT_BINDING, "audit_binding_invalid")
    _require(AUDIT.is_file(), "audit_missing")
    _require(_sha256(AUDIT) == AUDIT_BINDING["sha256"], "audit_hash_invalid")
    _require(not any(ABSOLUTE.search(value) for value in _walk(document)), "absolute_path_in_document")
    _require(not ABSOLUTE.search(AUDIT.read_text(encoding="utf-8")), "absolute_path_in_audit")
    if source_root is not None:
        _verify_objects(Path(source_root))
    return {"schema": SCHEMA, "valid": True, "source_object_checked": source_root is not None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(validate_document(source_root=args.source_root), sort_keys=True))
        return 0
    except (OSError, UnicodeError, yaml.YAMLError, ObservationError) as error:
        print(json.dumps({"schema": SCHEMA, "valid": False, "reason": str(error)}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
