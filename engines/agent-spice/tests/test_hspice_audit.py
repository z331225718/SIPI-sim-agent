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


def test_audit_ignores_hspice_dollar_comments_and_preserves_quoted_dollars():
    report = audit_deck(
        "$ .fft v(out)\n"
        ".include 'models/load$rev.inc' $ include comment\n"
        ".lib './corners$2026.lib' tt $ library comment\n"
        ".tran 1p 10n $ analysis comment\n"
        ".end\n"
    )

    assert report.includes == ["models/load$rev.inc"]
    assert report.libraries == [("./corners$2026.lib", "tt")]
    assert report.unsupported_directives == []


def test_audit_accepts_native_hspice_conditionals_and_options_alias():
    report = audit_deck(
        ".if (mode = 1)\n"
        ".options post=2\n"
        ".elseif (mode = 2)\n"
        ".else\n"
        ".endif\n"
        ".end\n"
    )

    assert report.unsupported_directives == []
