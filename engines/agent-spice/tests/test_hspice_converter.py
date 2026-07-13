import json

from agent_spice.hspice.converter import convert_hspice_deck


def test_convert_for_ngspice_normalizes_inc_and_probe():
    result = convert_hspice_deck(
        ".inc 'models.inc'\n.probe tran v(vdd)\n.option post=2\n.end\n",
        backend="ngspice",
    )

    assert ".include 'models.inc'" in result.deck_text
    assert ".print tran v(vdd)" in result.deck_text
    assert result.report.actions[0]["kind"] == "rewrite"
    assert result.report.actions[-1]["kind"] == "drop_option"


def test_option_postlayout_is_preserved():
    result = convert_hspice_deck(".option POSTLAYOUT=1\n.end\n", backend="ngspice")

    assert ".option POSTLAYOUT=1" in result.deck_text
    assert all(action["kind"] != "drop_option" for action in result.report.actions)


def test_option_post_token_after_other_options_is_dropped():
    result = convert_hspice_deck(
        ".option reltol=1e-3 post=1\n.end\n",
        backend="ngspice",
    )

    assert ".option reltol=1e-3 post=1" not in result.deck_text
    assert result.report.actions[0]["kind"] == "drop_option"


def test_ngspice_rewrites_cadence_current_pwl_repeat_to_behavioral_source():
    result = convert_hspice_deck(
        "Icursig vdd 0 pwl(\n"
        "+ 0ps 1 3500ps 2 6000ps 3\n"
        "+ R=3500ps )\n"
        ".end\n",
        backend="ngspice",
    )

    assert "Bcursig vdd 0 I = pwl(" in result.deck_text
    assert "floor((time - 3500ps) / 2500ps)" in result.deck_text
    assert "R=3500ps" not in result.deck_text
    assert result.report.actions[0]["kind"] == "rewrite_current_pwl_repeat"
    assert result.report.summary["status"] == "auto_converted"
    assert result.report.summary["rewrites"] == 1


def test_ngspice_current_pwl_repeat_rewrite_preserves_multiplicity():
    result = convert_hspice_deck(
        "Icursig vdd 0 pwl(\n"
        "+ 0ps 1 3500ps 2 6000ps 3\n"
        "+ R=3500ps ) M=4\n"
        ".end\n",
        backend="ngspice",
    )

    assert "Bcursig vdd 0 I = (4) * pwl(" in result.deck_text
    assert "M=4" in result.report.actions[0]["target"]


def test_compat_report_serializes_to_json():
    result = convert_hspice_deck(".end\n", backend="xyce")

    encoded = result.report.to_json()

    assert json.loads(encoded)["backend"] == "xyce"


def test_compat_report_includes_audit_outputs_and_summary():
    result = convert_hspice_deck(
        ".include 'models.inc'\n"
        ".lib './corners.lib' tt\n"
        ".probe tran v(vdd)\n"
        ".measure tran droop min v(vdd) from=1n to=5n\n"
        ".fft v(vdd)\n"
        ".end\n",
        backend="ngspice",
    )

    data = json.loads(result.report.to_json())

    assert data["schema_version"] == 1
    assert data["audit"]["directive_counts"][".include"] == 1
    assert data["audit"]["libraries"] == [["./corners.lib", "tt"]]
    assert data["audit"]["unsupported_directives"] == [".fft"]
    assert data["outputs"]["probes"] == ["v(vdd)"]
    assert data["outputs"]["measures"][0]["name"] == "droop"
    assert data["unsupported"] == [{"line": ".fft", "reason": "unsupported_directive"}]
    assert data["summary"]["status"] == "blocked"
    assert data["summary"]["rewrites"] == 1
    assert data["summary"]["unsupported"] == 1
