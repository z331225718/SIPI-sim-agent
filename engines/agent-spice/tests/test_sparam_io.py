from pathlib import Path

from agent_spice.sparam.io import load_touchstone_metadata


def test_load_touchstone_metadata_for_s2p(tmp_path: Path):
    s2p = tmp_path / "line.s2p"
    s2p.write_text(
        "\n".join(
            [
                "# Hz S RI R 50",
                "1e6 0 0 1 0 1 0 0 0",
                "2e6 0 0 1 0 1 0 0 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    metadata = load_touchstone_metadata(s2p)

    assert metadata.ports == 2
    assert metadata.frequency_points == 2
    assert metadata.reference_impedance == [50.0, 50.0]
    assert metadata.reference_impedance_by_frequency == [[50.0, 50.0], [50.0, 50.0]]


def test_load_touchstone_metadata_uses_fast_path_for_simple_touchstone(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.io as io

    s3p = tmp_path / "line.s3p"
    s3p.write_text(
        "\n".join(
            [
                "! comment",
                "# Hz S RI R 0.1",
                "1e6 0 0 0 0 0 0",
                "0 0 0 0 0 0",
                "0 0 0 0 0 0",
                "2e6 0 0 0 0 0 0",
                "0 0 0 0 0 0",
                "0 0 0 0 0 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fail_if_called(path):
        raise AssertionError(f"rf.Network should not be called for simple metadata: {path}")

    monkeypatch.setattr(io.rf, "Network", fail_if_called)

    metadata = load_touchstone_metadata(s3p)

    assert metadata.ports == 3
    assert metadata.frequency_points == 2
    assert metadata.reference_impedance == [0.1, 0.1, 0.1]
    assert metadata.reference_impedance_by_frequency == [[0.1, 0.1, 0.1], [0.1, 0.1, 0.1]]


class FakeNetwork:
    nports = 2
    f = [1e6, 2e6]
    z0 = [
        [50 + 0j, 51 + 0j],
        [55 + 0j, 56 + 0j],
    ]

    def __init__(self, path):
        self.path = path


def test_load_touchstone_metadata_preserves_frequency_dependent_z0(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.io as io

    monkeypatch.setattr(io.rf, "Network", FakeNetwork)

    metadata = load_touchstone_metadata(tmp_path / "line.s2p")

    assert metadata.reference_impedance == [50.0, 51.0]
    assert metadata.reference_impedance_by_frequency == [[50.0, 51.0], [55.0, 56.0]]
