import json
from pathlib import Path


def test_compare_sparam_bands_cli_writes_json_and_csv(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    calls = []

    def fake_compare(raw, models, *, output, csv=None, html=None):
        calls.append((raw, models, output, csv, html))
        payload = {
            "raw": str(raw),
            "models": {
                "idem": {
                    "path": "idem.s30p",
                    "bands": {
                        "low_dc_to_1mhz": {
                            "frequency_point_count": 2,
                            "s_mean_rms_error": 0.1,
                            "s_relative_rms_error": 0.2,
                            "diagonal_z_log_magnitude_rms_error": 0.3,
                        }
                    },
                }
            },
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload), encoding="utf-8")
        if csv is not None:
            csv.write_text("model,band,s_mean_rms_error\nidem,low_dc_to_1mhz,0.1\n", encoding="utf-8")
        if html is not None:
            html.write_text("<html></html>", encoding="utf-8")
        return payload

    monkeypatch.setattr(cli, "run_touchstone_banded_comparison", fake_compare)

    output = tmp_path / "bands.json"
    csv_path = tmp_path / "bands.csv"
    html_path = tmp_path / "bands.html"
    exit_code = cli.main(
        [
            "compare-sparam-bands",
            str(tmp_path / "raw.s30p"),
            "--model",
            f"idem={tmp_path / 'idem.s30p'}",
            "--output",
            str(output),
            "--csv",
            str(csv_path),
            "--html",
            str(html_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls[0][0] == tmp_path / "raw.s30p"
    assert calls[0][1] == {"idem": tmp_path / "idem.s30p"}
    assert output.exists()
    assert csv_path.exists()
    assert html_path.exists()
    assert "compare-sparam-bands models=1 output=" in captured.out


def test_compare_sparam_bands_cli_rejects_model_without_label(tmp_path: Path, capsys):
    from agent_spice.cli import main

    exit_code = main(
        [
            "compare-sparam-bands",
            str(tmp_path / "raw.s30p"),
            "--model",
            str(tmp_path / "idem.s30p"),
            "--output",
            str(tmp_path / "bands.json"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "expected --model LABEL=PATH" in captured.err
