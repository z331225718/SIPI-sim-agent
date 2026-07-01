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
    output_dir = tmp_path / "xdm-out"

    backend = XyceBackend(xdm_executable="xdm_bdl")

    assert backend.xdm_command_for(source, output_dir) == [
        "xdm_bdl",
        "-s",
        "hspice",
        "-d",
        str(output_dir),
        "-o",
        "xyce",
        str(source),
    ]


def test_xyce_xdm_run_writes_stage_logs_and_copies_generated_deck(tmp_path: Path, monkeypatch):
    source = tmp_path / "case.sp"
    output = tmp_path / "case.cir"
    source.write_text(".end\n", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0] == "xdm_bdl":
            generated_dir = tmp_path / "xdm-out"
            generated_dir.mkdir(exist_ok=True)
            (generated_dir / "case.sp").write_text(".end\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="xdm ok", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="xyce ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    backend = XyceBackend(executable="Xyce", xdm_executable="xdm_bdl")

    result = backend.run_hspice_via_xdm(source, output, cwd=tmp_path)

    assert result.ok
    assert result.xdm.ok
    assert result.xyce is not None
    assert result.xyce.ok
    assert commands == [
        ["xdm_bdl", "-s", "hspice", "-d", str(tmp_path / "xdm-out"), "-o", "xyce", str(source.resolve())],
        ["Xyce", str(output.resolve())],
    ]
    assert (tmp_path / "xdm.stdout.log").read_text(encoding="utf-8") == "xdm ok"
    assert (tmp_path / "xdm.stderr.log").read_text(encoding="utf-8") == ""
    assert (tmp_path / "xyce.stdout.log").read_text(encoding="utf-8") == "xyce ok"
    assert (tmp_path / "xyce.stderr.log").read_text(encoding="utf-8") == ""
    assert output.read_text(encoding="utf-8") == ".end\n"


def test_xyce_xdm_run_stops_when_xdm_fails(tmp_path: Path, monkeypatch):
    source = tmp_path / "case.sp"
    output = tmp_path / "case.cir"
    source.write_text(".end\n", encoding="utf-8")
    (tmp_path / "xyce.stdout.log").write_text("old xyce stdout", encoding="utf-8")
    (tmp_path / "xyce.stderr.log").write_text("old xyce stderr", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 7, stdout="", stderr="xdm failed")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = XyceBackend().run_hspice_via_xdm(source, output, cwd=tmp_path)

    assert not result.ok
    assert result.returncode == 7
    assert result.xyce is None
    assert len(commands) == 1
    assert not output.exists()
    assert not (tmp_path / "xyce.stdout.log").exists()
    assert not (tmp_path / "xyce.stderr.log").exists()


def test_xyce_xdm_run_uses_absolute_xdm_output_dir_for_relative_cwd(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cwd = Path("runs") / "demo"
    cwd.mkdir(parents=True)
    source = cwd / "case.sp"
    output = cwd / "case.cir"
    source.write_text(".end\n", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0] == "xdm_bdl":
            generated_dir = Path(command[4])
            generated_dir.mkdir(parents=True, exist_ok=True)
            (generated_dir / "case.sp").write_text(".end\n", encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout="xdm ok", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="xyce ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = XyceBackend().run_hspice_via_xdm(source, output, cwd=cwd)

    assert result.ok
    assert commands[0][4] == str((tmp_path / "runs" / "demo" / "xdm-out").resolve())


def test_xyce_xdm_run_does_not_reuse_stale_xdm_output(tmp_path: Path, monkeypatch):
    source = tmp_path / "case.sp"
    output = tmp_path / "case.cir"
    source.write_text(".end\n", encoding="utf-8")
    xdm_dir = tmp_path / "xdm-out"
    xdm_dir.mkdir()
    (xdm_dir / "case.sp").write_text("stale\n", encoding="utf-8")
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="xdm ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = XyceBackend().run_hspice_via_xdm(source, output, cwd=tmp_path)

    assert not result.ok
    assert result.xyce is None
    assert len(commands) == 1
    assert not output.exists()
    assert "XDM did not create expected output" in (tmp_path / "xdm.stderr.log").read_text(encoding="utf-8")


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
