from pathlib import Path

import pytest

from agent_spice.project import ProjectManifest, prepare_run_directory


def test_manifest_loads_hspice_entry(tmp_path: Path):
    manifest_path = tmp_path / "project.yaml"
    manifest_path.write_text(
        """
name: demo_pdn
inputs:
  hspice_deck: legacy/top.sp
backend: ngspice
outputs:
  root: out
""".strip(),
        encoding="utf-8",
    )

    manifest = ProjectManifest.from_yaml(manifest_path)

    assert manifest.name == "demo_pdn"
    assert manifest.hspice_deck == Path("legacy/top.sp")
    assert manifest.backend == "ngspice"
    assert manifest.output_root == Path("out")


def test_manifest_accepts_xyce_xdm_backend():
    manifest = ProjectManifest.from_mapping({"name": "demo_pdn", "backend": "xyce-xdm"})

    assert manifest.backend == "xyce-xdm"


def test_prepare_run_directory_is_deterministic(tmp_path: Path):
    run_dir = prepare_run_directory(tmp_path, project_name="demo_pdn", case_name="base")

    assert run_dir == tmp_path / "demo_pdn" / "base"
    assert run_dir.exists()


@pytest.mark.parametrize(
    "manifest",
    [
        {},
        {"name": ""},
        {"name": "   "},
        {"name": 123},
    ],
)
def test_manifest_rejects_missing_or_invalid_name(manifest: dict[str, object]):
    with pytest.raises(ValueError, match="name"):
        ProjectManifest.from_mapping(manifest)


@pytest.mark.parametrize(
    ("field", "manifest"),
    [
        ("inputs", {"name": "demo_pdn", "inputs": ["legacy/top.sp"]}),
        ("outputs", {"name": "demo_pdn", "outputs": ["out"]}),
    ],
)
def test_manifest_rejects_non_mapping_inputs_and_outputs(field: str, manifest: dict[str, object]):
    with pytest.raises(ValueError, match=f"Manifest field '{field}' must be a mapping"):
        ProjectManifest.from_mapping(manifest)


def test_manifest_rejects_unsupported_backend():
    with pytest.raises(ValueError, match="Unsupported backend 'spectre'"):
        ProjectManifest.from_mapping({"name": "demo_pdn", "backend": "spectre"})
