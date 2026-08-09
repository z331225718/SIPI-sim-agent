from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from build_m5b_ami_candidate_bundle import manifest, write_bundle  # noqa: E402
from verify_m5b_ami_candidate_bundle import verify  # noqa: E402


def assert_value_error(operation, expected: str) -> None:
    try:
        operation()
    except ValueError as error:
        assert expected in str(error)
    else:
        raise AssertionError("expected ValueError")


def build_info(_executable: Path) -> dict[str, object]:
    return {
        "schema": "agent-spice.build-info.v1",
        "candidateCapabilities": {
            "amiHostCandidate": {
                "requestSchema": "agent-spice.ami-host-request.v1",
                "resultSchema": "agent-spice.ami-host-result.v1",
                "platform": "windows-x86_64",
                "productionResolvable": False,
            }
        },
    }


def bundle(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    executable = tmp_path / "agent-spice-sim.exe"
    executable.write_bytes(b"candidate executable")
    document = manifest(
        source_root=ROOT,
        agent_spice_root=ROOT.parent / "agent-spice",
        executable=executable,
        system_dlls=["kernel32.dll", "vcruntime140.dll"],
        toolchain="cargo 1.test",
        source_commit="a" * 40,
        build_info_loader=build_info,
    )
    output = tmp_path / "bundle"
    write_bundle(output, document, executable)
    return output


def test_candidate_bundle_is_explicit_and_verifies(tmp_path: Path) -> None:
    report = verify(bundle(tmp_path))
    assert report["accepted"] is True
    assert report["productionResolvable"] is False
    assert report["vendorRuntime"] == "blocked_unknown"


def test_candidate_bundle_verifier_fails_closed(tmp_path: Path) -> None:
    cases = [
        (lambda document: document["executable"].update({"sha256": "0" * 64}), "candidate executable hash"),
        (lambda document: document["protocol"].update({"requestSchema": "wrong"}), "protocol"),
        (lambda document: document["dynamicDependencyClosure"].update({"thirdParty": ["vendor.dll"]}), "third-party dynamic dependency"),
        (lambda document: document["externalVendorAssets"].update({"bundlePolicy": "allowed"}), "vendor policy"),
    ]
    for mutate, expected in cases:
        output = bundle(tmp_path / expected.replace(" ", "-"))
        path = output / "candidate-manifest.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        mutate(document)
        path.write_text(json.dumps(document), encoding="utf-8")
        assert_value_error(lambda: verify(output), expected)


def test_candidate_bundle_rejects_vendor_asset(tmp_path: Path) -> None:
    output = bundle(tmp_path)
    (output / "unreviewed.dll").write_bytes(b"not allowed")
    assert_value_error(lambda: verify(output), "vendor assets")


def test_candidate_manifest_requires_system_only_closure(tmp_path: Path) -> None:
    executable = tmp_path / "candidate.exe"
    executable.write_bytes(b"candidate")
    assert_value_error(
        lambda: manifest(
            source_root=ROOT,
            agent_spice_root=ROOT.parent / "agent-spice",
            executable=executable,
            system_dlls=[],
            toolchain="cargo 1.test",
            source_commit="b" * 40,
            build_info_loader=build_info,
        ),
        "system DLL",
    )


def main() -> None:
    with tempfile.TemporaryDirectory() as name:
        test_candidate_bundle_is_explicit_and_verifies(Path(name))
    with tempfile.TemporaryDirectory() as name:
        test_candidate_bundle_verifier_fails_closed(Path(name))
    with tempfile.TemporaryDirectory() as name:
        test_candidate_bundle_rejects_vendor_asset(Path(name))
    with tempfile.TemporaryDirectory() as name:
        test_candidate_manifest_requires_system_only_closure(Path(name))


if __name__ == "__main__":
    main()
