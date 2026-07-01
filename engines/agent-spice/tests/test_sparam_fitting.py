from pathlib import Path

from agent_spice.sparam.fitting import fit_touchstone_to_spice


class FakeVectorFitting:
    instances: list["FakeVectorFitting"] = []

    def __init__(self, network):
        self.network = network
        self.calls: list[str] = []
        self.instances.append(self)

    def auto_fit(self):
        self.calls.append("auto_fit")
        return None

    def passivity_enforce(self):
        self.calls.append("passivity_enforce")
        return None

    def write_spice_subcircuit_s(self, filename):
        self.calls.append("write_spice_subcircuit_s")
        Path(filename).write_text(".subckt fitted 1 2\n.ends fitted\n", encoding="utf-8")


class FakeNetwork:
    def __init__(self, path):
        self.path = path


def test_fit_touchstone_to_spice_calls_export(tmp_path: Path, monkeypatch):
    import agent_spice.sparam.fitting as fitting

    FakeVectorFitting.instances.clear()
    monkeypatch.setattr(fitting.rf, "Network", FakeNetwork)
    monkeypatch.setattr(fitting, "VectorFitting", FakeVectorFitting)
    output = tmp_path / "model.sp"

    result = fit_touchstone_to_spice(tmp_path / "line.s2p", output)

    assert result == output
    assert len(FakeVectorFitting.instances) == 1
    assert FakeVectorFitting.instances[0].calls == [
        "auto_fit",
        "passivity_enforce",
        "write_spice_subcircuit_s",
    ]
    assert ".subckt fitted" in output.read_text(encoding="utf-8")
