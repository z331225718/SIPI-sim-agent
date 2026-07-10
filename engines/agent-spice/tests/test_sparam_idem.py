from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from agent_spice.sparam import idem
from agent_spice.sparam.idem import (
    evaluate_local_idem_like_model,
    evaluate_local_idem_like_state_space,
    export_local_idem_like_touchstone,
    export_local_idem_like_state_space,
    IdemAdaptiveFittingOptions,
    IdemCommandResult,
    IdemFittingOptions,
    fit_matrix_with_idem_real_basis,
    fit_s_with_fixed_poles,
    initial_common_poles,
    parse_idem_passivity_stdout,
    parse_idem_accuracy_report,
    relocate_common_poles,
    render_adaptive_fitting_options_xml,
    render_fitting_options_xml,
    run_idem_passivity,
    run_local_idem_like_fit,
    write_adaptive_fitting_options_xml,
)


def _write_s2p(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# GHz S RI R 50",
                "0.001 0 0 1 0 1 0 0 0",
                "5.0 0 0 1 0 1 0 0 0",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_render_fitting_options_xml_sets_initial_iteration_knob():
    xml_text = render_fitting_options_xml(
        IdemFittingOptions(order=32, initial_iterations=1, threads=2, target=1e-4, bandwidth=2.0e9)
    )
    root = ET.fromstring(xml_text)
    namespace = {"f": "OptionsFittingSchema.xsd"}

    assert root.findtext(".//f:order/f:value", namespaces=namespace) == "32"
    assert root.findtext(".//f:iterations/f:initial", namespaces=namespace) == "1"
    assert root.findtext(".//f:threads", namespaces=namespace) == "2"
    assert root.findtext(".//f:accuracy/f:target", namespaces=namespace) == "0.0001"
    assert root.findtext(".//f:bandwidth", namespaces=namespace) == "2000000000"


def test_adaptive_xml_omits_reserved_order_and_bandwidth_and_defaults_enhance_false():
    options = IdemAdaptiveFittingOptions()
    xml_text = render_adaptive_fitting_options_xml(options)
    root = ET.fromstring(xml_text)
    namespace = {"f": "OptionsFittingSchema.xsd"}

    assert root.find(".//f:order", namespaces=namespace) is None
    assert root.find(".//f:bandwidth", namespaces=namespace) is None
    assert root.findtext(".//f:iterations/f:enhancePolesPlacement", namespaces=namespace) == "false"
    assert root.findtext(".//f:iterations/f:initial", namespaces=namespace) == "3"
    assert root.findtext(".//f:errorControl/f:accuracy/f:guaranteed", namespaces=namespace) == "0.1"
    reject_poles = root.find(".//f:outOfBand/f:rejectPoles", namespaces=namespace)
    assert reject_poles is not None
    assert reject_poles.attrib == {"enabled": "false"}
    assert len(reject_poles) == 0
    assert (reject_poles.text or "").strip() == ""
    assert root.find(".//f:outOfBand/f:rejectPoles/f:maxRelativeFrequency", namespaces=namespace) is None


def test_adaptive_xml_golden_contract_matches_official_disabled_defaults():
    xml_text = render_adaptive_fitting_options_xml(IdemAdaptiveFittingOptions())
    root = ET.fromstring(xml_text)
    namespace = {"f": "OptionsFittingSchema.xsd"}
    expected_text = {
        "./f:options/f:iterations/f:initial": "3",
        "./f:options/f:iterations/f:postadding": "1",
        "./f:options/f:iterations/f:final": "1",
        "./f:options/f:iterations/f:enhancePolesPlacement": "false",
        "./f:options/f:errorControl/f:stagnation/f:alpha": "0.05",
        "./f:options/f:errorControl/f:stagnation/f:nBackSteps": "3",
        "./f:options/f:errorControl/f:skimming/f:relativeTolerance": "0.001",
        "./f:options/f:errorControl/f:skimming/f:finalRelativeTolerance": "0.001",
        "./f:options/f:errorControl/f:accuracy/f:guaranteed": "0.1",
        "./f:options/f:splitting/f:splits/f:type": "none",
        "./f:options/f:splitting/f:p4poles/f:type": "all",
        "./f:options/f:splitting/f:p4poles/f:nLargest": "INF",
        "./f:options/f:splitting/f:p4res/f:type": "all",
        "./f:options/f:outOfBand/f:enforceDC": "true",
        "./f:options/f:outOfBand/f:frequencyProportionalTerm": "false",
        "./f:options/f:outOfBand/f:enforceAsymptoticPassivity/f:passivityMargin": "0.001",
        "./f:options/f:outOfBand/f:enforceAsymptoticPassivity/f:relocatePoles": "false",
    }

    assert root.tag == "{OptionsFittingSchema.xsd}fittingTask"
    assert root.attrib == {"version": "1.0"}
    assert root.find("./f:options/f:order", namespaces=namespace) is None
    assert root.find("./f:options/f:bandwidth", namespaces=namespace) is None
    assert root.find("./f:options/f:weights/f:frequency", namespaces=namespace).attrib == {"enabled": "false"}
    assert root.find("./f:options/f:weights/f:responses", namespaces=namespace).attrib == {"enabled": "false"}
    assert root.find("./f:options/f:outOfBand/f:enforceAsymptoticPassivity", namespaces=namespace).attrib == {
        "enabled": "true"
    }
    reject_poles = root.find("./f:options/f:outOfBand/f:rejectPoles", namespaces=namespace)
    assert reject_poles.attrib == {"enabled": "false"}
    assert len(reject_poles) == 0
    assert root.find("./f:options/f:outOfBand/f:rejectPoles/f:maxRelativeFrequency", namespaces=namespace) is None
    for path, text in expected_text.items():
        assert root.findtext(path, namespaces=namespace) == text


def test_adaptive_xml_renders_explicit_enhanced_poles_placement_true():
    xml_text = render_adaptive_fitting_options_xml(IdemAdaptiveFittingOptions(enhance_poles_placement=True))

    assert "<enhancePolesPlacement>true</enhancePolesPlacement>" in xml_text


def test_adaptive_xml_renders_relative_frequency_weights():
    xml_text = render_adaptive_fitting_options_xml(
        IdemAdaptiveFittingOptions(relative_frequency_weight_alpha=1.0, relative_frequency_weight_threshold=1e-8)
    )
    root = ET.fromstring(xml_text)
    namespace = {"f": "OptionsFittingSchema.xsd"}

    assert root.find(".//f:weights/f:frequency[@enabled='true']", namespaces=namespace) is not None
    assert root.findtext(".//f:weights/f:frequency/f:relative/f:alpha", namespaces=namespace) == "1"
    # Real IdEM 2026 parser probe rejects relThreshold and accepts relativeThreshold.
    assert root.findtext(".//f:weights/f:frequency/f:relative/f:relativeThreshold", namespaces=namespace) == "1e-08"
    assert root.find(".//f:weights/f:frequency/f:relative/f:relThreshold", namespaces=namespace) is None
    assert root.find(".//f:weights/f:frequency/f:absolute", namespaces=namespace) is None


def test_adaptive_xml_renders_reject_poles_bandwidth_only_when_enabled():
    xml_text = render_adaptive_fitting_options_xml(
        IdemAdaptiveFittingOptions(reject_poles=True, reject_poles_max_relative_frequency=1.5)
    )
    root = ET.fromstring(xml_text)
    namespace = {"f": "OptionsFittingSchema.xsd"}

    assert root.find(".//f:outOfBand/f:rejectPoles[@enabled='true']", namespaces=namespace) is not None
    assert root.findtext(".//f:outOfBand/f:rejectPoles/f:maxRelativeFrequency", namespaces=namespace) == "1.5"


def test_adaptive_xml_renders_absolute_frequency_weight_points():
    xml_text = render_adaptive_fitting_options_xml(
        IdemAdaptiveFittingOptions(absolute_frequency_weight_points=((0.0, 1.0), (5.0e9, 1e-3)))
    )
    root = ET.fromstring(xml_text)
    namespace = {"f": "OptionsFittingSchema.xsd"}
    points = root.findall(".//f:weights/f:frequency/f:absolute/f:point", namespaces=namespace)

    assert root.find(".//f:weights/f:frequency[@enabled='true']", namespaces=namespace) is not None
    assert [point.text for point in points] == ["0 1", "5000000000 0.001"]
    assert root.find(".//f:weights/f:frequency/f:relative", namespaces=namespace) is None


def test_write_adaptive_fitting_options_xml_returns_path_and_writes_well_formed_xml(tmp_path: Path):
    output = tmp_path / "adaptive" / "fitting_options.fopt.xml"

    written = write_adaptive_fitting_options_xml(IdemAdaptiveFittingOptions(), output)

    assert written == output
    root = ET.fromstring(output.read_text(encoding="utf-8"))
    assert root.tag == "{OptionsFittingSchema.xsd}fittingTask"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"initial_iterations": -1},
        {"postadding_iterations": 0},
        {"final_iterations": False},
        {"enhance_poles_placement": 1},
        {"stagnation_alpha": 0.0},
        {"stagnation_alpha": float("nan")},
        {"stagnation_back_steps": 0},
        {"skimming_tolerance": -1.0},
        {"final_skimming_tolerance": float("inf")},
        {"guaranteed_accuracy": 0.0},
        {"split_type": "puzzle"},
        {"p4poles_type": "largest"},
        {"p4poles_n_largest": "nan"},
        {"p4poles_n_largest": 0},
        {"p4res_type": "column"},
        {"enforce_dc": 1},
        {"asymptotic_passivity_margin": -0.1},
        {"asymptotic_passivity_margin": 1.1},
        {"reject_poles": 0},
        {"reject_poles_max_relative_frequency": 0.0},
        {"relative_frequency_weight_alpha": -1.0},
        {"relative_frequency_weight_threshold": 0.0},
        {"absolute_frequency_weight_points": ((0.0, 1.0),)},
        {"absolute_frequency_weight_points": ((0.0, 1.0), (float("nan"), 1.0))},
        {"absolute_frequency_weight_points": ((0.0, 0.0), (1.0, 1.0))},
        {"absolute_frequency_weight_points": ((False, 1.0), (1.0, 1.0))},
        {"absolute_frequency_weight_points": ((0.0, True), (1.0, 1.0))},
        {
            "relative_frequency_weight_alpha": 1.0,
            "absolute_frequency_weight_points": ((0.0, 1.0), (1.0, 1.0)),
        },
    ],
)
def test_adaptive_options_fail_closed(kwargs):
    with pytest.raises(ValueError):
        IdemAdaptiveFittingOptions(**kwargs)


def test_run_idem_initial_iteration_probe_writes_xml_per_trial(tmp_path: Path, monkeypatch):
    touchstone = tmp_path / "line.s2p"
    _write_s2p(touchstone)
    commands = []

    def fake_run(touchstone_path, model_path, *, options_xml_path=None, idem_bin_dir=None, timeout_seconds=None):
        commands.append((touchstone_path, model_path, options_xml_path))
        model_path.write_text("fake model", encoding="utf-8")
        return IdemCommandResult(
            command=["idemmp_fitting.exe"],
            returncode=1,
            stdout="End of model build\n",
            stderr="",
            elapsed_seconds=0.1,
            peak_memory_mb=12.5,
        )

    monkeypatch.setattr(idem, "run_idem_fitting", fake_run)
    monkeypatch.setattr(
        idem,
        "inspect_idem_model",
        lambda path: {"order": 32, "total_pole_count": 32, "error_history": [0.2], "orders_history": [32]},
    )

    results = idem.run_idem_initial_iteration_probe(touchstone, tmp_path / "runs", order=32, initial_iterations=[0, 3])

    assert [result["initial_iterations"] for result in results] == [0, 3]
    assert [result["status"] for result in results] == ["completed", "completed"]
    assert len(commands) == 2
    xml_text = commands[1][2].read_text(encoding="utf-8")
    assert "<initial>3</initial>" in xml_text
    assert "<bandwidth mode=\"absolute\">5000000000</bandwidth>" in xml_text


def test_run_idem_adaptive_fitting_uses_documented_command_and_timeout(tmp_path: Path, monkeypatch):
    touchstone = tmp_path / "line.s2p"
    model = tmp_path / "out" / "model.mod.h5"
    xml_path = tmp_path / "fitting_options.fopt.xml"
    bin_dir = tmp_path / "bin"
    _write_s2p(touchstone)
    xml_path.write_text("<fittingTask/>", encoding="utf-8")
    calls = []

    def fake_run(command, timeout_seconds=None):
        calls.append((command, timeout_seconds))
        model.write_text("fake model", encoding="utf-8")
        return IdemCommandResult(command, 0, "Results\n", "trace\n", 0.25, 44.0)

    monkeypatch.setattr(idem, "_run_command", fake_run)
    monkeypatch.setattr(idem, "inspect_idem_model", lambda path: {"order": 4, "total_pole_count": 4})

    result = idem.run_idem_adaptive_fitting(
        touchstone,
        model,
        order_min=4,
        order_step=2,
        order_max=100,
        target=1e-3,
        bandwidth_hz=2.0e9,
        threads=8,
        options_xml_path=xml_path,
        idem_bin_dir=bin_dir,
        timeout_seconds=12.0,
    )

    command = [
        str(bin_dir / "idemmp_fitting.exe"),
        "-its",
        str(touchstone),
        "-o",
        str(model),
        "-tol",
        "0.001",
        "-orderMin",
        "4",
        "-orderStep",
        "2",
        "-orderMax",
        "100",
        "-bandwidth",
        "2000000000",
        "-DC",
        "1",
        "-nThreads",
        "8",
        "-xml",
        str(xml_path),
    ]
    assert calls == [(command, 12.0)]
    assert result["status"] == "completed"
    assert result["command"]["command"] == command
    assert result["command"]["stdout"] == "Results\n"
    assert result["command"]["stderr"] == "trace\n"
    assert result["command"]["elapsed_seconds"] == pytest.approx(0.25)
    assert result["touchstone_path"] == str(touchstone)
    assert result["model_path"] == str(model)
    assert result["xml_path"] == str(xml_path)
    assert result["model"] == {"order": 4, "total_pole_count": 4}


def test_run_idem_adaptive_fitting_removes_only_stale_target_model(tmp_path: Path, monkeypatch):
    touchstone = tmp_path / "line.s2p"
    model = tmp_path / "out" / "model.mod.h5"
    sibling = tmp_path / "out" / "keep.mod.h5"
    xml_path = tmp_path / "fitting_options.fopt.xml"
    _write_s2p(touchstone)
    xml_path.write_text("<fittingTask/>", encoding="utf-8")
    model.parent.mkdir()
    model.write_text("stale model", encoding="utf-8")
    sibling.write_text("do not delete", encoding="utf-8")

    def fake_run(command, timeout_seconds=None):
        assert not model.exists()
        assert sibling.read_text(encoding="utf-8") == "do not delete"
        model.write_text("fresh model", encoding="utf-8")
        return IdemCommandResult(command, 0, "Results\n", "", 0.1, None)

    monkeypatch.setattr(idem, "_run_command", fake_run)
    monkeypatch.setattr(idem, "inspect_idem_model", lambda path: {"order": 6})

    result = idem.run_idem_adaptive_fitting(
        touchstone,
        model,
        order_min=4,
        order_step=2,
        order_max=8,
        target=1e-3,
        bandwidth_hz=2.0e9,
        threads=2,
        options_xml_path=xml_path,
        idem_bin_dir=tmp_path,
    )

    assert result["status"] == "completed"
    assert sibling.read_text(encoding="utf-8") == "do not delete"


@pytest.mark.parametrize("create_zero_model", [False, True])
def test_run_idem_adaptive_fitting_fails_without_nonempty_model(tmp_path: Path, monkeypatch, create_zero_model: bool):
    touchstone = tmp_path / "line.s2p"
    model = tmp_path / "model.mod.h5"
    xml_path = tmp_path / "fitting_options.fopt.xml"
    _write_s2p(touchstone)
    xml_path.write_text("<fittingTask/>", encoding="utf-8")

    def fake_run(command, timeout_seconds=None):
        if create_zero_model:
            model.write_bytes(b"")
        return IdemCommandResult(command, 0, "End of model build\n", "", 0.1, None)

    monkeypatch.setattr(idem, "_run_command", fake_run)
    monkeypatch.setattr(idem, "inspect_idem_model", lambda path: pytest.fail("empty or missing model was inspected"))

    result = idem.run_idem_adaptive_fitting(
        touchstone,
        model,
        order_min=4,
        order_step=2,
        order_max=8,
        target=1e-3,
        bandwidth_hz=2.0e9,
        threads=2,
        options_xml_path=xml_path,
        idem_bin_dir=tmp_path,
    )

    assert result["status"] == "failed"
    assert result["model"] == {}


def test_run_idem_adaptive_fitting_fails_on_stdout_error_marker(tmp_path: Path, monkeypatch):
    touchstone = tmp_path / "line.s2p"
    model = tmp_path / "model.mod.h5"
    xml_path = tmp_path / "fitting_options.fopt.xml"
    _write_s2p(touchstone)
    xml_path.write_text("<fittingTask/>", encoding="utf-8")

    def fake_run(command, timeout_seconds=None):
        model.write_text("fake model", encoding="utf-8")
        return IdemCommandResult(command, 0, "Error: failed\nEnd of model build\n", "", 0.1, None)

    monkeypatch.setattr(idem, "_run_command", fake_run)
    monkeypatch.setattr(idem, "inspect_idem_model", lambda path: {"order": 4})

    result = idem.run_idem_adaptive_fitting(
        touchstone,
        model,
        order_min=4,
        order_step=2,
        order_max=8,
        target=1e-3,
        bandwidth_hz=2.0e9,
        threads=2,
        options_xml_path=xml_path,
        idem_bin_dir=tmp_path,
    )

    assert result["status"] == "failed"
    assert result["model"] == {"order": 4}


def test_run_idem_adaptive_fitting_accepts_returncode_one_with_end_marker(tmp_path: Path, monkeypatch):
    touchstone = tmp_path / "line.s2p"
    model = tmp_path / "model.mod.h5"
    xml_path = tmp_path / "fitting_options.fopt.xml"
    _write_s2p(touchstone)
    xml_path.write_text("<fittingTask/>", encoding="utf-8")

    def fake_run(command, timeout_seconds=None):
        model.write_text("fake model", encoding="utf-8")
        return IdemCommandResult(command, 1, "End of model build\n", "", 0.1, None)

    monkeypatch.setattr(idem, "_run_command", fake_run)
    monkeypatch.setattr(idem, "inspect_idem_model", lambda path: {"order": 8})

    result = idem.run_idem_adaptive_fitting(
        touchstone,
        model,
        order_min=4,
        order_step=2,
        order_max=8,
        target=1e-3,
        bandwidth_hz=2.0e9,
        threads=2,
        options_xml_path=xml_path,
        idem_bin_dir=tmp_path,
    )

    assert result["status"] == "completed"
    assert result["command"]["returncode"] == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"order_min": 0},
        {"order_min": True},
        {"order_step": 0},
        {"order_step": False},
        {"order_max": 0},
        {"order_min": 10, "order_step": 2, "order_max": 8},
        {"order_min": 4, "order_step": 3, "order_max": 9},
        {"target": 0.0},
        {"target": float("nan")},
        {"target": True},
        {"bandwidth_hz": 0.0},
        {"bandwidth_hz": float("inf")},
        {"threads": 0},
        {"threads": True},
    ],
)
def test_run_idem_adaptive_fitting_rejects_invalid_order_and_numeric_inputs(tmp_path: Path, overrides):
    touchstone = tmp_path / "line.s2p"
    model = tmp_path / "model.mod.h5"
    xml_path = tmp_path / "fitting_options.fopt.xml"
    _write_s2p(touchstone)
    xml_path.write_text("<fittingTask/>", encoding="utf-8")
    kwargs = {
        "order_min": 4,
        "order_step": 2,
        "order_max": 8,
        "target": 1e-3,
        "bandwidth_hz": 2.0e9,
        "threads": 2,
        "options_xml_path": xml_path,
        "idem_bin_dir": tmp_path,
    }
    kwargs.update(overrides)

    with pytest.raises(ValueError):
        idem.run_idem_adaptive_fitting(touchstone, model, **kwargs)


@pytest.mark.parametrize("missing", ["touchstone", "xml"])
def test_run_idem_adaptive_fitting_requires_existing_input_files(tmp_path: Path, missing: str):
    touchstone = tmp_path / "line.s2p"
    model = tmp_path / "model.mod.h5"
    xml_path = tmp_path / "fitting_options.fopt.xml"
    if missing != "touchstone":
        _write_s2p(touchstone)
    if missing != "xml":
        xml_path.write_text("<fittingTask/>", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        idem.run_idem_adaptive_fitting(
            touchstone,
            model,
            order_min=4,
            order_step=2,
            order_max=8,
            target=1e-3,
            bandwidth_hz=2.0e9,
            threads=2,
            options_xml_path=xml_path,
            idem_bin_dir=tmp_path,
        )


def test_run_idem_adaptive_fitting_propagates_timeout(tmp_path: Path, monkeypatch):
    touchstone = tmp_path / "line.s2p"
    model = tmp_path / "model.mod.h5"
    xml_path = tmp_path / "fitting_options.fopt.xml"
    _write_s2p(touchstone)
    xml_path.write_text("<fittingTask/>", encoding="utf-8")

    def fake_run(command, timeout_seconds=None):
        assert timeout_seconds == 0.01
        raise TimeoutError("timed out")

    monkeypatch.setattr(idem, "_run_command", fake_run)

    with pytest.raises(TimeoutError):
        idem.run_idem_adaptive_fitting(
            touchstone,
            model,
            order_min=4,
            order_step=2,
            order_max=8,
            target=1e-3,
            bandwidth_hz=2.0e9,
            threads=2,
            options_xml_path=xml_path,
            idem_bin_dir=tmp_path,
            timeout_seconds=0.01,
        )


def test_parse_idem_passivity_stdout_extracts_soc_ham_progress():
    stdout = """
--- SOC Iteration no. 1
Maximum Singular Value : 1.00393 @ 1.99796e+09 Hz
 Launching SOCP solver...
--- SOC Iteration no. 2
Maximum Singular Value : 1.00017 @ 1.95352e+09 Hz
 Launching SOCP solver...
--- SOC Iteration no. 3
No passivity violations detected by SOC
--- HAM Iteration no. 1
Finding imaginary eigenvalues in (0, 4.24725e+09)

Found 0 imaginary eigenvalues.
No passivity violations detected by HAM
Model is Passive. End of passivity check
------------------------------------------------------------------------
Results
Passive: YES
"""

    summary = parse_idem_passivity_stdout(stdout)

    assert summary["passive"] is True
    assert summary["soc_iterations"] == 3
    assert summary["ham_iterations"] == 1
    assert summary["ham_imaginary_eigenvalues"] == [0]
    assert summary["max_singular_values"] == [
        {"iteration": 1, "value": 1.00393, "frequency_hz": 1.99796e9},
        {"iteration": 2, "value": 1.00017, "frequency_hz": 1.95352e9},
    ]


def test_parse_idem_accuracy_report_extracts_full_grid_metrics():
    report = """** No. of ports: 91
** No. of samples: 611
** Max Err: 0.0921744123
** RMS Err: 0.001174775322
"""

    parsed = parse_idem_accuracy_report(report)

    assert parsed == {
        "ports": 91,
        "frequency_points": 611,
        "max_error": pytest.approx(0.0921744123),
        "mean_rms": pytest.approx(0.001174775322),
    }


def test_parse_idem_accuracy_report_rejects_missing_rms():
    with pytest.raises(ValueError, match="RMS Err"):
        parse_idem_accuracy_report(
            "** No. of ports: 91\n** No. of samples: 611\n** Max Err: 0.1\n"
        )


def test_run_idem_passivity_treats_passive_stdout_as_completed(tmp_path: Path, monkeypatch):
    model = tmp_path / "model.mod.h5"
    output_model = tmp_path / "model_passive.mod.h5"
    model.write_text("fake", encoding="utf-8")
    calls = []

    def fake_run(command, timeout_seconds=None):
        calls.append(command)
        output_model.write_text("fake passive", encoding="utf-8")
        return IdemCommandResult(
            command=command,
            returncode=1,
            stdout="--- SOC Iteration no. 1\nMaximum Singular Value : 1.01 @ 2e+09 Hz\nResults\nPassive: YES\n",
            stderr="",
            elapsed_seconds=0.2,
            peak_memory_mb=33.0,
        )

    monkeypatch.setattr(idem, "_run_command", fake_run)
    monkeypatch.setattr(idem, "inspect_idem_model", lambda path: {"is_passive": 1})

    result = run_idem_passivity(model, output_model, idem_bin_dir=tmp_path, threads=4, ham_solver=3, preserve_dc=True)

    assert result["status"] == "completed"
    assert result["passivity"]["passive"] is True
    assert result["model"] == {"is_passive": 1}
    assert calls == [
        [
            str(tmp_path / "idemmp_passivity.exe"),
            "-ih5",
            str(model),
            "-o",
            str(output_model),
            "-hamSolver",
            "3",
            "-DC",
            "1",
            "-nThreads",
            "4",
        ]
    ]


def test_run_idem_accuracy_check_uses_documented_command_and_parses_report(tmp_path: Path, monkeypatch):
    touchstone = tmp_path / "line.s2p"
    model = tmp_path / "model.mod.h5"
    report = tmp_path / "accuracy.txt"
    touchstone.write_text("raw", encoding="utf-8")
    model.write_text("model", encoding="utf-8")
    calls = []

    def fake_run(command, timeout_seconds=None):
        calls.append((command, timeout_seconds))
        report.write_text(
            "** No. of ports: 2\n** No. of samples: 5\n"
            "** Max Err: 0.02\n** RMS Err: 0.0009\n",
            encoding="utf-8",
        )
        return IdemCommandResult(command, 1, "End of Accuracy check\nResults\n", "", 0.2, 40.0)

    monkeypatch.setattr(idem, "_run_command", fake_run)

    result = idem.run_idem_accuracy_check(
        touchstone,
        model,
        report,
        idem_bin_dir=tmp_path,
        timeout_seconds=12.0,
    )

    assert result["status"] == "completed"
    assert result["metrics"]["mean_rms"] == pytest.approx(0.0009)
    assert calls == [
        (
            [
                str(tmp_path / "idemmp_checkaccuracy.exe"),
                "-its",
                str(touchstone),
                "-ih5m",
                str(model),
                "-r",
                str(report),
            ],
            12.0,
        )
    ]


def test_run_idem_touchstone_export_uses_type_2_and_accepts_artifact_success(tmp_path: Path, monkeypatch):
    model = tmp_path / "model.mod.h5"
    exported = tmp_path / "model.s2p"
    model.write_text("model", encoding="utf-8")
    calls = []

    def fake_run(command, timeout_seconds=None):
        calls.append(command)
        exported.write_text("# Hz S RI R 50\n", encoding="utf-8")
        return IdemCommandResult(command, 1, "Results\nOutput file: model.s2p\n", "", 0.3, 50.0)

    monkeypatch.setattr(idem, "_run_command", fake_run)

    result = idem.run_idem_touchstone_export(model, exported, idem_bin_dir=tmp_path)

    assert result["status"] == "completed"
    assert calls == [
        [
            str(tmp_path / "idemmp_export.exe"),
            "-ih5",
            str(model),
            "-o",
            str(exported),
            "-type",
            "2",
        ]
    ]


def test_idem_accuracy_and_export_fail_without_required_artifacts(tmp_path: Path, monkeypatch):
    command_result = IdemCommandResult([], 1, "Results\n", "", 0.1, 1.0)
    monkeypatch.setattr(idem, "_run_command", lambda *args, **kwargs: command_result)

    accuracy = idem.run_idem_accuracy_check(
        tmp_path / "line.s2p",
        tmp_path / "model.mod.h5",
        tmp_path / "missing.txt",
        idem_bin_dir=tmp_path,
    )
    export = idem.run_idem_touchstone_export(
        tmp_path / "model.mod.h5",
        tmp_path / "missing.s2p",
        idem_bin_dir=tmp_path,
    )

    assert accuracy["status"] == "failed"
    assert accuracy["metrics"] is None
    assert export["status"] == "failed"


def test_idem_accuracy_and_export_do_not_reuse_stale_artifacts(tmp_path: Path, monkeypatch):
    report = tmp_path / "accuracy.txt"
    exported = tmp_path / "model.s2p"
    report.write_text(
        "** No. of ports: 2\n** No. of samples: 5\n"
        "** Max Err: 0.02\n** RMS Err: 0.0009\n",
        encoding="utf-8",
    )
    exported.write_text("# Hz S RI R 50\n", encoding="utf-8")

    def fake_run(command, timeout_seconds=None):
        assert not report.exists() if "idemmp_checkaccuracy.exe" in command[0] else not exported.exists()
        return IdemCommandResult(command, 2, "failed\n", "error", 0.1, 1.0)

    monkeypatch.setattr(idem, "_run_command", fake_run)

    accuracy = idem.run_idem_accuracy_check(
        tmp_path / "line.s2p",
        tmp_path / "model.mod.h5",
        report,
        idem_bin_dir=tmp_path,
    )
    export = idem.run_idem_touchstone_export(
        tmp_path / "model.mod.h5",
        exported,
        idem_bin_dir=tmp_path,
    )

    assert accuracy["status"] == "failed"
    assert export["status"] == "failed"


def test_decode_idem_split_poles_expands_real_state_space_pairs():
    dtype = [("nr", "<i4"), ("nc", "<i4"), ("p", "O")]
    row = np.array([(1, 2, np.array([-1.0, -2.0, 3.0, -4.0, 5.0]))], dtype=dtype)[0]

    poles = idem._decode_idem_split_poles(row)

    assert poles.tolist() == [
        complex(-1.0, 0.0),
        complex(-2.0, 3.0),
        complex(-2.0, -3.0),
        complex(-4.0, 5.0),
        complex(-4.0, -5.0),
    ]


def test_s_mean_rms_error_matches_idem_port_pair_mean_definition():
    original = np.zeros((2, 3, 3), dtype=complex)
    fitted = np.ones((2, 3, 3), dtype=complex)

    assert np.isclose(idem._s_rms_error(original, fitted), 3.0)
    assert np.isclose(idem._s_mean_rms_error(original, fitted), 1.0)


def test_fit_s_with_fixed_poles_recovers_known_response():
    freqs = np.array([1e6, 2e6, 5e6, 10e6, 20e6], dtype=float)
    poles = np.array([-1e8, -2e8], dtype=complex)
    s = 2j * np.pi * freqs
    values = 0.2 + 3e7 / (s - poles[0]) - 2e7j / (s - poles[1])
    samples = values.reshape(len(freqs), 1, 1)

    result = fit_s_with_fixed_poles(freqs, samples, poles)

    assert result["rank"] == 3
    assert result["condition_number"] > 0.0
    assert np.max(np.abs(result["fitted_s"] - samples)) < 1e-12


def test_fit_matrix_with_idem_real_basis_recovers_conjugate_pair_response():
    freqs = np.array([1e6, 2e6, 5e6, 10e6, 20e6], dtype=float)
    pole_block = {
        "poles_rad_per_s": [-1e8, -2e8, 3e8],
        "real_pole_count": 1,
        "complex_pair_count": 1,
    }
    s = 2j * np.pi * freqs
    pole = -2e8 + 3e8j
    conjugate = -2e8 - 3e8j
    values = 0.2 + 3e7 / (s + 1e8)
    values += 2e7 * (1 / (s - pole) + 1 / (s - conjugate))
    values += -1e7 * 1j * (1 / (s - pole) - 1 / (s - conjugate))
    samples = values.reshape(len(freqs), 1, 1)

    result = fit_matrix_with_idem_real_basis(freqs, samples, pole_block)

    assert result["rank"] == 4
    assert result["condition_number"] > 0.0
    assert np.max(np.abs(result["fitted_values"] - samples)) < 1e-12


def test_pole_block_from_complex_poles_encodes_conjugate_pairs():
    poles = np.array([-1e8 + 0j, -2e8 + 3e8j, -2e8 - 3e8j])

    block = idem._pole_block_from_complex_poles(poles)

    assert block["real_pole_count"] == 1
    assert block["complex_pair_count"] == 1
    assert block["poles_rad_per_s"] == [-1e8, -2e8, 3e8]
    assert block["decoded_poles_rad_per_s"] == [[-1e8, 0.0], [-2e8, 3e8], [-2e8, -3e8]]


def test_pole_block_from_complex_poles_pairs_nearby_opposite_imaginary_poles():
    poles = np.array([-2.0e8 + 3.0e8j, -2.2e8 - 3.1e8j, -5.0e8 + 8.0e8j, -5.1e8 - 8.2e8j])

    block = idem._pole_block_from_complex_poles(poles)

    assert block["real_pole_count"] == 0
    assert block["complex_pair_count"] == 2
    assert len(block["poles_rad_per_s"]) == 4


def test_initial_common_poles_uses_stable_conjugate_pairs():
    poles = initial_common_poles([0.0, 1e6, 10e6], order=4, damping=0.05, spacing="log")

    assert len(poles) == 4
    assert np.all(poles.real < 0.0)
    assert any(pole.imag > 0.0 for pole in poles)
    assert any(pole.imag < 0.0 for pole in poles)


def test_initial_common_poles_can_skip_near_dc_frequency():
    poles = initial_common_poles([0.1, 1e6, 10e6], order=2, damping=0.05, spacing="lin", f_min=1e6)

    assert np.isclose(abs(poles[0].imag) / (2 * np.pi), 1e6)


def test_relocate_common_poles_moves_toward_scalar_response_pole():
    freqs = np.linspace(1e6, 30e6, 80)
    true_pole = -2.0e7 + 2j * np.pi * 8.0e6
    true_conjugate = true_pole.conjugate()
    s = 2j * np.pi * freqs
    values = 0.1 + 1.5e7 / (s - true_pole) + 1.5e7 / (s - true_conjugate)
    samples = values.reshape(len(freqs), 1, 1)
    initial = initial_common_poles(freqs, order=2, damping=0.05, spacing="lin")

    step = relocate_common_poles(freqs, samples, initial, max_responses=None)

    assert len(step.poles_rad_per_s) == 2
    assert np.all(step.poles_rad_per_s.real < 0.0)
    assert step.rank is not None and step.rank > 0
    initial_distance = np.min(np.abs(initial - true_pole))
    relocated_distance = np.min(np.abs(step.poles_rad_per_s - true_pole))
    assert relocated_distance < initial_distance


def test_relocate_common_poles_can_select_diagonal_responses():
    freqs = np.linspace(1e6, 10e6, 16)
    samples = np.zeros((len(freqs), 2, 2), dtype=complex)
    samples[:, 0, 0] = 1.0
    samples[:, 1, 1] = 2.0
    samples[:, 0, 1] = 100.0
    initial = initial_common_poles(freqs, order=2)

    step = relocate_common_poles(freqs, samples, initial, response_selection="diagonal", max_responses=2)

    assert step.selected_response_indices == (0, 3)


def test_relocate_common_poles_can_force_conjugate_pairs():
    freqs = np.linspace(1e6, 10e6, 24)
    samples = np.zeros((len(freqs), 1, 1), dtype=complex)
    samples[:, 0, 0] = 1.0 / (2j * np.pi * freqs - complex(-2e6, 3e7))
    initial = initial_common_poles(freqs, order=4)

    step = relocate_common_poles(freqs, samples, initial, max_responses=None, pole_pairing="conjugate")
    positive = sorted(pole.imag for pole in step.poles_rad_per_s if pole.imag > 0.0)
    negative = sorted(-pole.imag for pole in step.poles_rad_per_s if pole.imag < 0.0)

    assert len(step.poles_rad_per_s) == 4
    assert len(positive) == len(negative) == 2
    assert np.allclose(positive, negative)


def test_adaptive_z_selection_keeps_worst_z_pairs():
    values = np.zeros((3, 2, 2), dtype=complex)
    values[:, 0, 0] = 1.0
    values[:, 0, 1] = 100.0
    values[:, 1, 0] = 50.0
    values[:, 1, 1] = 2.0
    original_z = np.ones((3, 2, 2), dtype=complex)
    fitted_z = original_z.copy()
    fitted_z[:, 1, 1] *= 100.0

    selected = idem._select_adaptive_z_response_indices(values, original_z, fitted_z, 2, worst_pair_count=1)

    assert 3 in selected
    assert len(selected) == 2


def test_run_local_idem_like_fit_selects_best_iteration(tmp_path: Path):
    touchstone = tmp_path / "line.s2p"
    _write_s2p(touchstone)

    result = run_local_idem_like_fit(
        touchstone,
        order=1,
        iterations=1,
        fit_max_frequency_points=2,
        max_pole_responses=2,
        residue_basis="complex",
    )

    assert result["probe"] == "local_idem_like_fit"
    assert result["recipe"]["order"] == 1
    assert len(result["iterations"]) == 2
    assert result["best"]["iteration"] in {0, 1}


def test_run_local_idem_like_fit_backfills_s_mean_for_selection(tmp_path: Path, monkeypatch):
    touchstone = tmp_path / "line.s2p"
    _write_s2p(touchstone)

    def fake_probe(*args, **kwargs):
        return [
            {"iteration": 0, "s_rms_error": 30.0, "ports": 30, "z_log_magnitude_rms_error": 0.1},
            {"iteration": 1, "s_rms_error": 3.0, "ports": 30, "z_log_magnitude_rms_error": 0.2},
        ]

    monkeypatch.setattr(idem, "run_local_pole_relocation_probe", fake_probe)

    result = run_local_idem_like_fit(
        touchstone,
        selection_metric="s_mean_rms_error",
    )

    assert result["iterations"][0]["s_mean_rms_error"] == 1.0
    assert result["iterations"][1]["s_mean_rms_error"] == 0.1
    assert result["best"]["iteration"] == 1


def test_local_idem_like_model_round_trips_metrics(tmp_path: Path):
    touchstone = tmp_path / "line.s2p"
    model = tmp_path / "line_model.npz"
    _write_s2p(touchstone)

    result = run_local_idem_like_fit(
        touchstone,
        order=1,
        iterations=1,
        fit_max_frequency_points=2,
        max_pole_responses=2,
        residue_basis="complex",
        model_output_path=model,
    )
    replay = evaluate_local_idem_like_model(model, touchstone)

    assert model.exists()
    assert replay["basis"] == "complex"
    assert replay["pole_count"] == 1
    assert np.isclose(replay["z_log_magnitude_rms_error"], result["best"]["z_log_magnitude_rms_error"])


def test_export_local_idem_like_touchstone_writes_readable_network(tmp_path: Path):
    import skrf as rf

    touchstone = tmp_path / "line.s2p"
    model = tmp_path / "line_model.npz"
    output = tmp_path / "line_fit.s2p"
    _write_s2p(touchstone)
    run_local_idem_like_fit(
        touchstone,
        order=1,
        iterations=1,
        fit_max_frequency_points=2,
        max_pole_responses=2,
        residue_basis="complex",
        model_output_path=model,
    )

    result = export_local_idem_like_touchstone(model, output, reference_touchstone_path=touchstone)
    exported = rf.Network(str(output))

    assert Path(result["output_path"]) == output
    assert exported.nports == 2
    assert len(exported.f) == 2


def test_export_local_idem_like_state_space_replays_model(tmp_path: Path):
    touchstone = tmp_path / "line.s2p"
    model = tmp_path / "line_model.npz"
    state_space = tmp_path / "line_statespace.npz"
    _write_s2p(touchstone)
    run_local_idem_like_fit(
        touchstone,
        order=1,
        iterations=1,
        fit_max_frequency_points=2,
        max_pole_responses=2,
        residue_basis="complex",
        model_output_path=model,
    )

    export = export_local_idem_like_state_space(model, state_space)
    replay_model = evaluate_local_idem_like_model(model, touchstone)
    replay_state = evaluate_local_idem_like_state_space(state_space, touchstone)

    assert export["states"] == 2
    assert state_space.exists()
    assert np.isclose(replay_state["z_log_magnitude_rms_error"], replay_model["z_log_magnitude_rms_error"])
