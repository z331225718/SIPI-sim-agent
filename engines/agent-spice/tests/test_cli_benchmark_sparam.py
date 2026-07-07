import json
from pathlib import Path

from agent_spice.cli import main


def test_benchmark_sparam_cli_writes_metadata_reports(tmp_path: Path, capsys):
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
    manifest = tmp_path / "cases.yaml"
    manifest.write_text(
        "\n".join(
            [
                "base_dir: .",
                "cases:",
                "  - id: local_2port",
                "    touchstone: line.s2p",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    jsonl_path = tmp_path / "benchmark.jsonl"
    csv_path = tmp_path / "benchmark.csv"

    exit_code = main(
        [
            "benchmark-sparam",
            "--manifest",
            str(manifest),
            "--output",
            str(jsonl_path),
            "--csv",
            str(csv_path),
            "--output-root",
            str(tmp_path / "runs"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "local_2port: completed" in captured.out
    assert json.loads(jsonl_path.read_text(encoding="utf-8"))["ports"] == 2
    assert "local_2port" in csv_path.read_text(encoding="utf-8")


def test_benchmark_sparam_cli_rejects_unknown_case(tmp_path: Path, capsys):
    manifest = tmp_path / "cases.yaml"
    manifest.write_text("cases: []\n", encoding="utf-8")

    exit_code = main(
        [
            "benchmark-sparam",
            "--manifest",
            str(manifest),
            "--case",
            "missing",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Benchmark case id not found: missing" in captured.err


def test_benchmark_sparam_cli_runs_order_sweep(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    manifest = tmp_path / "cases.yaml"
    manifest.write_text(
        "\n".join(
            [
                "base_dir: .",
                "cases:",
                "  - id: local_2port",
                "    touchstone: line.s2p",
                "    fit:",
                "      mode: manual",
                "      enforce_passivity: false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "line.s2p").write_text(
        "# Hz S RI R 50\n1e6 0 0 1 0 1 0 0 0\n2e6 0 0 1 0 1 0 0 0\n",
        encoding="utf-8",
    )
    calls = []

    def fake_run_sparam_benchmarks(
        manifest_path,
        output_root,
        run_fit=False,
        case_ids=None,
        order_sweep=None,
    ):
        calls.append((manifest_path, output_root, run_fit, case_ids, order_sweep))
        return [
            {"case_id": "local_2port/order20", "status": "completed", "quality_status": "PASS"},
            {"case_id": "local_2port/order40", "status": "completed", "quality_status": "WARN"},
        ]

    monkeypatch.setattr(cli, "run_sparam_benchmarks", fake_run_sparam_benchmarks)

    exit_code = main(
        [
            "benchmark-sparam",
            "--manifest",
            str(manifest),
            "--run-fit",
            "--order-sweep",
            "20,40",
            "--output",
            str(tmp_path / "out.jsonl"),
            "--csv",
            str(tmp_path / "out.csv"),
            "--output-root",
            str(tmp_path / "runs"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls[0][2] is True
    assert calls[0][4] == [20, 40]
    assert "local_2port/order20: completed PASS" in captured.out
    assert "local_2port/order40: completed WARN" in captured.out


def test_benchmark_sparam_cli_rejects_order_sweep_without_run_fit(tmp_path: Path, capsys):
    manifest = tmp_path / "cases.yaml"
    manifest.write_text("cases: []\n", encoding="utf-8")

    exit_code = main(
        [
            "benchmark-sparam",
            "--manifest",
            str(manifest),
            "--order-sweep",
            "20,40",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "--order-sweep requires --run-fit" in captured.err
