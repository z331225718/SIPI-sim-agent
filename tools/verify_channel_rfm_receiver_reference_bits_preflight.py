"""Fail closed on the authorized external reference-bit observer source."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = ROOT / "docs/baselines/channel-rfm-receiver-reference-bits-authorization.v1.yaml"
PROFILE = "channel-rfm-block-2-current-drive-v1"
SOURCE = {
    "repository_origin": "https://github.com/z331225718/Py-bert-agent.git",
    "commit": "199696a510baa87645dfdcf7017d11325ba06195",
    "tree": "4dfa8e64114a8946183d4d1eb2a92f8c415db16c",
    "path": "scripts/verify_m5b_rfm_receiver_parity.py",
    "git_blob": "de587f2e04c11db83dc8ee389584da36e6c79ecd",
    "content_sha256": "c34a90035d7ae6d01321e69cc6332d75d60332d594f1fb40abc341d988882cba",
}
RFM = {
    "commit": "f6ba0311350fc67bd90fa13b8d578312f956d7e7",
    "path": "tests/golden/rust_migration/agent_spice_rfm/block_2.rfm",
    "git_blob": "9a087a9f75c58d3d1fb15efee2628001a601a546",
    "content_sha256": "5716f691a69174cfe88980ffd96bfc867f30f9ee92b6b85d3fb6b8c8b3636a53",
}
SOURCE_MARKERS = (
    "samples, dt, nspui = 1024, 1.0e-12, 8",
    "currents = np.where((np.arange(samples) // nspui) % 2 == 0, 0.05, -0.05)",
)


def _run(repo: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], text=True, stderr=subprocess.PIPE
    ).strip()


def _bytes(repo: Path, commit: str, path: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{commit}:{path}"])


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_bits() -> bytes:
    return bytes(1 if index % 2 == 0 else 0 for index in range(128))


def verify(repo: Path, authorization: Path = AUTHORIZATION) -> dict:
    document = yaml.safe_load(authorization.read_text(encoding="utf-8"))
    expected_keys = {"schema", "status", "profile_id", "approved_by", "approved_at", "approval_ref", "scope", "source_candidate", "rfm_anchor", "sidecar_policy", "non_claims"}
    if not isinstance(document, dict) or set(document) != expected_keys:
        raise ValueError("authorization schema is incomplete")
    if document["schema"] != "sipi.channel.authorized-reference-bit-source.v1" or document["status"] != "authorized_pending_source_attestation" or document["profile_id"] != PROFILE:
        raise ValueError("authorization identity is unsafe")
    if document["source_candidate"] != SOURCE or document["rfm_anchor"] != RFM:
        raise ValueError("authorization source anchor drifted")
    if document["sidecar_policy"] != {"encoding": "one-byte-per-bit-0-or-1", "bit_count": 128, "storage": "external_ephemeral_only", "product_or_git_storage": "forbidden"}:
        raise ValueError("authorization sidecar policy drifted")
    repo = repo.resolve()
    if _run(repo, "status", "--porcelain"):
        raise ValueError("observer repository worktree must be clean")
    try:
        origin = _run(repo, "remote", "get-url", "origin")
    except subprocess.CalledProcessError as error:
        raise ValueError("observer repository origin is unavailable") from error
    if origin != SOURCE["repository_origin"]:
        raise ValueError("observer repository origin does not match authorization")
    if _run(repo, "rev-parse", "HEAD") != SOURCE["commit"] or _run(repo, "rev-parse", "HEAD^{tree}") != SOURCE["tree"]:
        raise ValueError("observer repository is not the authorized source commit")
    script = _bytes(repo, SOURCE["commit"], SOURCE["path"])
    rfm = _bytes(repo, RFM["commit"], RFM["path"])
    if _run(repo, "rev-parse", f"{SOURCE['commit']}:{SOURCE['path']}") != SOURCE["git_blob"] or _sha256(script) != SOURCE["content_sha256"]:
        raise ValueError("authorized stimulus generator identity mismatch")
    if _run(repo, "rev-parse", f"{RFM['commit']}:{RFM['path']}") != RFM["git_blob"] or _sha256(rfm) != RFM["content_sha256"]:
        raise ValueError("RFM source identity mismatch")
    script_text = script.decode("utf-8")
    if not all(marker in script_text for marker in SOURCE_MARKERS):
        raise ValueError("authorized generator no longer has the direct alternating current source")
    bits = _canonical_bits()
    with tempfile.TemporaryDirectory(prefix="sipi-rfm-reference-bits-") as temporary:
        root = Path(temporary)
        first, second = root / "first.bits", root / "second.bits"
        first.write_bytes(bits)
        second.write_bytes(bits)
        first_hash, second_hash = _sha256(first.read_bytes()), _sha256(second.read_bytes())
    if first_hash != second_hash:
        raise ValueError("reference-bit observation was not deterministic")
    return {
        "schema": "sipi.channel.reference-bit-source-attestation.v1",
        "profile_id": PROFILE,
        "status": "authorized_source_attested_pending_receiver_compare",
        "source_generator": {key: SOURCE[key] for key in ("commit", "path", "git_blob", "content_sha256")},
        "rfm": RFM,
        "mapping": {"symbol_indices": "0..127", "samples_per_ui": 8, "sample_interval_seconds": 1.0e-12, "positive_current_bit": 1, "negative_current_bit": 0},
        "reference_bits": {"encoding": "one-byte-per-bit-0-or-1", "count": 128, "sha256": first_hash, "fresh_replay_sha256": second_hash},
        "non_claims": ["no waveform inference", "no product or Git sidecar storage", "no receiver parity conclusion"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pybert-repo", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.report.exists():
            raise ValueError("report path must not already exist")
        result = verify(args.pybert_repo)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, subprocess.CalledProcessError, yaml.YAMLError) as error:
        print(json.dumps({"status": "rejected", "reason": str(error)}))
        return 2
    print(json.dumps({"status": result["status"], "reference_bits_sha256": result["reference_bits"]["sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
