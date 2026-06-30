from agent_spice.hspice.measure import normalize_outputs


def test_normalize_measure_and_print():
    text = """
.probe tran v(vdd) i(vsrc)
.print tran v(load)
.measure tran droop min v(load) from=1n to=10n
"""

    outputs = normalize_outputs(text)

    assert outputs.probes == ["v(vdd)", "i(vsrc)", "v(load)"]
    assert outputs.measures[0]["analysis"] == "tran"
    assert outputs.measures[0]["name"] == "droop"
    assert outputs.measures[0]["operation"] == "min"
    assert outputs.measures[0]["target"] == "v(load)"
