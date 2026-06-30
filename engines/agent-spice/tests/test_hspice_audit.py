from agent_spice.hspice.audit import audit_deck


def test_audit_detects_directives_and_includes():
    text = """
* demo PI deck
.include 'models/decap.inc'
.lib './corners.lib' tt
.param vdd=0.8
V1 vdd 0 0.8
R1 vdd load 10m
.tran 1p 10n
.measure tran droop min v(load) from=1n to=10n
.end
"""

    report = audit_deck(text)

    assert report.directive_counts[".include"] == 1
    assert report.directive_counts[".lib"] == 1
    assert report.directive_counts[".measure"] == 1
    assert report.includes == ["models/decap.inc"]
    assert report.libraries == [("./corners.lib", "tt")]
    assert report.unsupported_directives == []


def test_audit_reports_unsupported_directive():
    report = audit_deck(".fft v(out)\n.end\n")

    assert report.unsupported_directives == [".fft"]
