from agent_spice.hspice.alter import split_alter_cases


def test_split_alter_cases_keeps_base_and_creates_named_cases():
    text = """
.param cdecap=1u
C1 vdd 0 cdecap
.tran 1p 1n
.alter fast
.param cdecap=2u
.alter slow
.param cdecap=500n
.end
"""

    cases = split_alter_cases(text, stem="legacy")

    assert [case.name for case in cases] == ["legacy__base", "legacy__alter_001_fast", "legacy__alter_002_slow"]
    assert ".param cdecap=1u" in cases[0].text
    assert ".param cdecap=2u" in cases[1].text
    assert ".param cdecap=500n" in cases[2].text


def test_split_alter_cases_appends_global_end_to_every_case_once():
    text = """
.param cdecap=1u
C1 vdd 0 cdecap
.tran 1p 1n
.alter fast
.param cdecap=2u
.alter slow
.param cdecap=500n
.end
"""

    cases = split_alter_cases(text, stem="legacy")

    assert [case.name for case in cases] == ["legacy__base", "legacy__alter_001_fast", "legacy__alter_002_slow"]
    for case in cases:
        assert case.text.splitlines().count(".end") == 1
        assert case.text.endswith(".end\n")


def test_split_alter_cases_without_alter_returns_single_base_case():
    text = """
.param cdecap=1u
C1 vdd 0 cdecap
.tran 1p 1n
.end
"""

    cases = split_alter_cases(text, stem="legacy")

    assert len(cases) == 1
    assert cases[0].name == "legacy__base"
    assert cases[0].text == ".param cdecap=1u\nC1 vdd 0 cdecap\n.tran 1p 1n\n.end\n"


def test_split_alter_cases_does_not_add_missing_end():
    text = """
.param cdecap=1u
C1 vdd 0 cdecap
.tran 1p 1n
.alter fast
.param cdecap=2u
.alter slow
.param cdecap=500n
"""

    cases = split_alter_cases(text, stem="legacy")

    assert [case.name for case in cases] == ["legacy__base", "legacy__alter_001_fast", "legacy__alter_002_slow"]
    for case in cases:
        assert ".end" not in case.text.splitlines()
        assert case.text.endswith("\n")
