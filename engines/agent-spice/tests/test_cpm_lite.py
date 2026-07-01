from pathlib import Path

from agent_spice.cpm.io import load_cpm_lite
from agent_spice.cpm.waveform import render_pwl_sources


def test_load_cpm_lite_and_render_pwl(tmp_path: Path):
    path = tmp_path / "chip.json"
    path.write_text(
        """
{
  "model": "demo_chip",
  "bumps": [
    {"name": "VDD_A1", "node": "vdd_a1", "return_node": "vss", "waveform": [[0.0, 0.01], [1e-9, 0.05]]}
  ]
}
""".strip(),
        encoding="utf-8",
    )

    model = load_cpm_lite(path)
    deck = render_pwl_sources(model)

    assert model.model == "demo_chip"
    assert model.bumps[0].waveform == [(0.0, 0.01), (1e-09, 0.05)]
    assert "I_VDD_A1 vdd_a1 vss PWL(0.0 0.01 1e-09 0.05)" in deck


def test_cpm_fixture_loads_and_renders():
    model = load_cpm_lite(Path("tests/fixtures/cpm/chiplet_demo.json"))
    deck = render_pwl_sources(model)

    assert model.model == "chiplet_demo"
    assert "I_VDD_A1 load 0 PWL(0.0 0.01 1e-09 0.1)" in deck
