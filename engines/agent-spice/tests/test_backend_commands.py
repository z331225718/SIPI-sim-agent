from pathlib import Path
import subprocess

from agent_spice.backend.base import ProcessBackend
from agent_spice.backend.ngspice import NgspiceBackend
from agent_spice.backend.xyce import XyceBackend


def test_ngspice_command_uses_batch_mode(tmp_path: Path):
    deck = tmp_path / "case.cir"
    deck.write_text(".end\n", encoding="utf-8")

    backend = NgspiceBackend(executable="ngspice")

    assert backend.command_for(deck) == ["ngspice", "-b", str(deck)]


def test_xyce_command_uses_deck_path(tmp_path: Path):
    deck = tmp_path / "case.cir"
    deck.write_text(".end\n", encoding="utf-8")

    backend = XyceBackend(executable="Xyce")

    assert backend.command_for(deck) == ["Xyce", str(deck)]


def test_xyce_xdm_command_converts_hspice_to_xyce(tmp_path: Path):
    source = tmp_path / "legacy.sp"
    output = tmp_path / "converted.cir"

    backend = XyceBackend(xdm_executable="xdm_bdl")

    assert backend.xdm_command_for(source, output) == [
        "xdm_bdl",
        "-s",
        "hspice",
        "-d",
        "xyce",
        "-o",
        str(output),
        str(source),
    ]


class RecordingBackend(ProcessBackend):
    executable = "sim"

    def command_for(self, deck_path: Path) -> list[str]:
        return [self.executable, str(deck_path)]


def test_backend_run_resolves_deck_path_before_changing_cwd(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "runs" / "demo" / "demo__base"
    run_dir.mkdir(parents=True)
    deck = run_dir / "case.cir"
    deck.write_text(".end\n", encoding="utf-8")
    recorded: dict[str, object] = {}

    def fake_run(command, **kwargs):
        recorded["command"] = command
        recorded["cwd"] = kwargs["cwd"]
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.chdir(tmp_path)

    result = RecordingBackend().run(Path("runs/demo/demo__base/case.cir"), cwd=run_dir)

    assert result.ok
    assert recorded["command"] == ["sim", str(deck.resolve())]
    assert recorded["cwd"] == run_dir
