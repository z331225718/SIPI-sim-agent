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


def test_compat_report_serializes_to_json():
    result = convert_hspice_deck(".end\n", backend="xyce")

    encoded = result.report.to_json()

    assert json.loads(encoded)["backend"] == "xyce"
