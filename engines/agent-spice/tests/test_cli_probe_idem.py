import json
from argparse import Namespace
from pathlib import Path

from agent_spice.cli import main


def test_idem_compact_recipe_preserves_explicit_order_from_sys_argv_style():
    import agent_spice.cli as cli

    args = Namespace(
        recipe="idem-compact",
        order=40,
        iterations=4,
        pole_spacing="lin",
        pole_f_min=None,
        pole_pairing="none",
        residue_basis="complex",
        fit_max_frequency_points=256,
        max_pole_responses=64,
    )

    cli._apply_idem_like_recipe(args, ["fit-idem-like", "line.s30p", "--recipe", "idem-compact", "--order", "40"])

    assert args.order == 40
    assert args.iterations == 2
    assert args.pole_spacing == "log"


def test_probe_idem_init_cli_writes_reports(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    calls = []

    def fake_probe(
        touchstone,
        output_root,
        *,
        order,
        initial_iterations,
        idem_bin_dir=None,
        threads=1,
        target=1e-3,
        enforce_asymptotic_passivity=True,
        asymptotic_relocate_poles=False,
        enhance_poles_placement=False,
        timeout_seconds=None,
    ):
        calls.append(
            (
                touchstone,
                output_root,
                order,
                initial_iterations,
                idem_bin_dir,
                threads,
                target,
                enforce_asymptotic_passivity,
                asymptotic_relocate_poles,
                enhance_poles_placement,
                timeout_seconds,
            )
        )
        return [
            {
                "probe": "idem_initial_iterations",
                "touchstone_path": str(touchstone),
                "status": "completed",
                "order": order,
                "initial_iterations": initial_iterations[0],
                "target": target,
                "threads": threads,
                "enforce_asymptotic_passivity": enforce_asymptotic_passivity,
                "asymptotic_relocate_poles": asymptotic_relocate_poles,
                "enhance_poles_placement": enhance_poles_placement,
                "model_path": str(output_root / "model.mod.h5"),
                "xml_path": str(output_root / "fitting_options.fopt.xml"),
                "command": {
                    "command": ["idemmp_fitting.exe"],
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "",
                    "elapsed_seconds": 0.2,
                    "peak_memory_mb": 3.0,
                },
                "model": {
                    "order": order,
                    "total_pole_count": order,
                    "error_history": [0.01],
                    "orders_history": [order],
                },
            }
        ]

    monkeypatch.setattr(cli, "run_idem_initial_iteration_probe", fake_probe)

    report = tmp_path / "idem.jsonl"
    csv_path = tmp_path / "idem.csv"
    exit_code = main(
        [
            "probe-idem-init",
            str(tmp_path / "line.s2p"),
            "--output-root",
            str(tmp_path / "runs"),
            "--report",
            str(report),
            "--csv",
            str(csv_path),
            "--order",
            "32",
            "--initial-iters",
            "0,1,3",
            "--n-threads",
            "2",
            "--target",
            "0.0001",
            "--no-asymptotic-passivity",
            "--enhance-poles-placement",
            "--timeout-seconds",
            "10",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls[0][2] == 32
    assert calls[0][3] == [0, 1, 3]
    assert calls[0][5] == 2
    assert calls[0][6] == 0.0001
    assert calls[0][7] is False
    assert calls[0][9] is True
    assert "init=0: completed order=32 poles=32" in captured.out
    assert json.loads(report.read_text(encoding="utf-8"))["initial_iterations"] == 0
    assert "last_rms_error" in csv_path.read_text(encoding="utf-8")


def test_probe_idem_residue_cli_writes_json_report(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    def fake_probe(
        touchstone,
        model,
        *,
        parameter_type="s",
        basis="complex",
        relative_weight_power=0.0,
        fit_max_frequency_points=None,
        rcond=None,
    ):
        return {
            "probe": "idem_fixed_pole_residue",
            "parameter_type": parameter_type,
            "basis": basis,
            "relative_weight_power": relative_weight_power,
            "touchstone_path": str(touchstone),
            "model_path": str(model),
            "pole_count": 32,
            "fit_frequency_points": fit_max_frequency_points,
            "condition_number": 123.0,
            "s_relative_rms_error": 0.01,
            "z_log_magnitude_rms_error": 0.2,
        }

    monkeypatch.setattr(cli, "run_idem_fixed_pole_residue_probe", fake_probe)

    report = tmp_path / "residue.json"
    exit_code = main(
        [
            "probe-idem-residue",
            str(tmp_path / "line.s2p"),
            "--model",
            str(tmp_path / "model.mod.h5"),
            "--report",
            str(report),
            "--parameter-type",
            "z",
            "--basis",
            "idem-real",
            "--relative-weight-power",
            "1",
            "--fit-max-frequency-points",
            "64",
            "--rcond",
            "1e-12",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "fixed-pole residues: parameter=z basis=idem-real poles=32 fit_points=64" in captured.out
    assert json.loads(report.read_text(encoding="utf-8"))["condition_number"] == 123.0


def test_probe_idem_residue_sweep_cli_ranks_by_z_log_error(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    model = tmp_path / "order32_init2" / "model.mod.h5"
    model.parent.mkdir()
    model.write_text("fake", encoding="utf-8")

    def fake_sweep(
        touchstone,
        model_paths,
        *,
        parameter_types,
        bases,
        relative_weight_powers,
        fit_max_frequency_points=None,
        rcond=None,
    ):
        assert model_paths == [model]
        assert parameter_types == ["s", "z"]
        assert bases == ["idem-real"]
        assert relative_weight_powers == [0.0, 0.5]
        return [
            {
                "model_label": "order32_init2",
                "model_path": str(model),
                "basis": "idem-real",
                "parameter_type": "s",
                "relative_weight_power": 0.5,
                "rank": 33,
                "condition_number": 150.0,
                "s_relative_rms_error": 0.05,
                "s_rms_error": 0.1,
                "z_log_magnitude_rms_error": 1.2,
                "diagonal_z_log_magnitude_rms_error": 1.1,
                "max_abs_z_error_ohm": 2.0,
                "pole_count": 32,
                "basis_term_count": 33,
                "fit_frequency_points": fit_max_frequency_points,
                "idem_model": {"split_rms_error": 0.01, "split_max_error": 0.2},
            }
        ]

    monkeypatch.setattr(cli, "run_idem_residue_sweep", fake_sweep)

    report = tmp_path / "sweep.jsonl"
    csv_path = tmp_path / "sweep.csv"
    exit_code = main(
        [
            "probe-idem-residue-sweep",
            str(tmp_path / "line.s2p"),
            "--model",
            str(model),
            "--report",
            str(report),
            "--csv",
            str(csv_path),
            "--parameter-types",
            "s,z",
            "--bases",
            "idem-real",
            "--relative-weight-powers",
            "0,0.5",
            "--fit-max-frequency-points",
            "128",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "best z_log_rms=1.2 model=order32_init2 basis=idem-real" in captured.out
    assert json.loads(report.read_text(encoding="utf-8"))["model_label"] == "order32_init2"
    assert "idem_split_rms_error" in csv_path.read_text(encoding="utf-8")


def test_probe_idem_relocate_cli_writes_iteration_reports(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    calls = []

    def fake_probe(
        touchstone,
        *,
        order,
        iterations=3,
        parameter_type="s",
        pole_damping=0.05,
        pole_spacing="lin",
        pole_f_min=None,
        response_selection="energy",
        adaptive_worst_pair_count=16,
        residue_basis="complex",
        fit_max_frequency_points=None,
        max_pole_responses=64,
        relative_weight_power=0.0,
        pole_pairing="none",
        relocation_basis="complex",
        relocation_normalization="none",
        relocation_numerator="complex",
        rcond=None,
    ):
        calls.append(
            (
                touchstone,
                order,
                iterations,
                parameter_type,
                pole_damping,
                pole_spacing,
                pole_f_min,
                response_selection,
                adaptive_worst_pair_count,
                residue_basis,
                fit_max_frequency_points,
                max_pole_responses,
                relative_weight_power,
                pole_pairing,
                relocation_basis,
                relocation_normalization,
                relocation_numerator,
                rcond,
            )
        )
        return [
            {
                "probe": "local_common_pole_relocation",
                "iteration": 0,
                "order": order,
                "parameter_type": parameter_type,
                "pole_damping": pole_damping,
                "pole_spacing": pole_spacing,
                "pole_f_min": pole_f_min,
                "response_selection": response_selection,
                "pole_pairing": pole_pairing,
                "relocation_basis": relocation_basis,
                "relocation_normalization": relocation_normalization,
                "relocation_numerator": relocation_numerator,
                "basis": residue_basis,
                "fit_frequency_points": fit_max_frequency_points,
                "selected_response_count": max_pole_responses,
                "relocation_condition_number": None,
                "condition_number": 10.0,
                "s_relative_rms_error": 0.2,
                "z_log_magnitude_rms_error": 1.5,
                "diagonal_z_log_magnitude_rms_error": 1.4,
                "max_abs_z_error_ohm": 3.0,
                "pole_frequencies_hz": [1.0, 2.0],
            },
            {
                "probe": "local_common_pole_relocation",
                "iteration": 1,
                "order": order,
                "parameter_type": parameter_type,
                "pole_damping": pole_damping,
                "pole_spacing": pole_spacing,
                "pole_f_min": pole_f_min,
                "response_selection": response_selection,
                "pole_pairing": pole_pairing,
                "relocation_basis": relocation_basis,
                "relocation_normalization": relocation_normalization,
                "relocation_numerator": relocation_numerator,
                "basis": residue_basis,
                "fit_frequency_points": fit_max_frequency_points,
                "selected_response_count": max_pole_responses,
                "relocation_condition_number": 20.0,
                "condition_number": 11.0,
                "s_relative_rms_error": 0.1,
                "z_log_magnitude_rms_error": 1.0,
                "diagonal_z_log_magnitude_rms_error": 0.9,
                "max_abs_z_error_ohm": 2.0,
                "pole_frequencies_hz": [1.5, 2.5],
            },
        ]

    monkeypatch.setattr(cli, "run_local_pole_relocation_probe", fake_probe)

    report = tmp_path / "relocate.jsonl"
    csv_path = tmp_path / "relocate.csv"
    exit_code = main(
        [
            "probe-idem-relocate",
            str(tmp_path / "line.s2p"),
            "--report",
            str(report),
            "--csv",
            str(csv_path),
            "--order",
            "32",
            "--iterations",
            "2",
            "--parameter-type",
            "z",
            "--pole-damping",
            "0.04",
            "--pole-spacing",
            "log",
            "--pole-f-min",
            "1000000",
            "--response-selection",
            "adaptive-z",
            "--adaptive-worst-pair-count",
            "8",
            "--residue-basis",
            "real-state",
            "--fit-max-frequency-points",
            "128",
            "--max-pole-responses",
            "16",
            "--relative-weight-power",
            "0.5",
            "--pole-pairing",
            "conjugate",
            "--relocation-basis",
            "real-state",
            "--relocation-normalization",
            "frequency",
            "--relocation-numerator",
            "real",
            "--rcond",
            "1e-12",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls[0][1:] == (
        32,
        2,
        "z",
        0.04,
        "log",
        1000000.0,
        "adaptive-z",
        8,
        "real-state",
        128,
        16,
        0.5,
        "conjugate",
        "real-state",
        "frequency",
        "real",
        1e-12,
    )
    assert "relocate iter=1 poles=32 fit_points=128 responses=16" in captured.out
    assert len(report.read_text(encoding="utf-8").splitlines()) == 2
    assert "lowest_pole_frequency_hz" in csv_path.read_text(encoding="utf-8")


def test_probe_idem_relocate_sweep_cli_ranks_trials(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    calls = []

    def fake_sweep(
        touchstone,
        *,
        order,
        iterations,
        parameter_type,
        response_selections,
        max_pole_responses_values,
        relative_weight_powers,
        pole_damping=0.05,
        pole_spacing="lin",
        pole_f_min=None,
        adaptive_worst_pair_count=16,
        residue_bases=None,
        fit_max_frequency_points=None,
        pole_pairings=None,
        relocation_bases=None,
        relocation_normalizations=None,
        relocation_numerators=None,
        rcond=None,
    ):
        calls.append(
            (
                touchstone,
                order,
                iterations,
                parameter_type,
                response_selections,
                max_pole_responses_values,
                relative_weight_powers,
                pole_damping,
                pole_spacing,
                pole_f_min,
                adaptive_worst_pair_count,
                residue_bases,
                fit_max_frequency_points,
                pole_pairings,
                relocation_bases,
                relocation_normalizations,
                relocation_numerators,
                rcond,
            )
        )
        return [
            {
                "probe": "local_common_pole_relocation",
                "sweep_label": "mixed_n32_w0.5",
                "iteration": 2,
                "order": order,
                "parameter_type": parameter_type,
                "relative_weight_power": 0.5,
                "pole_damping": pole_damping,
                "pole_spacing": pole_spacing,
                "pole_f_min": pole_f_min,
                "response_selection": "mixed",
                "pole_pairing": "conjugate",
                "relocation_basis": "real-state",
                "relocation_normalization": "frequency",
                "relocation_numerator": "real",
                "basis": "real-state",
                "fit_frequency_points": fit_max_frequency_points,
                "selected_response_count": 32,
                "relocation_condition_number": 20.0,
                "condition_number": 100.0,
                "s_relative_rms_error": 0.02,
                "z_log_magnitude_rms_error": 1.1,
                "diagonal_z_log_magnitude_rms_error": 1.0,
                "max_abs_z_error_ohm": 2.0,
                "pole_frequencies_hz": [1.0, 2.0],
            }
        ]

    monkeypatch.setattr(cli, "run_local_pole_relocation_sweep", fake_sweep)

    report = tmp_path / "relocate_sweep.jsonl"
    csv_path = tmp_path / "relocate_sweep.csv"
    exit_code = main(
        [
            "probe-idem-relocate-sweep",
            str(tmp_path / "line.s2p"),
            "--report",
            str(report),
            "--csv",
            str(csv_path),
            "--order",
            "32",
            "--iterations",
            "2",
            "--parameter-type",
            "s",
            "--response-selections",
            "energy,mixed",
            "--max-pole-responses-list",
            "32,64",
            "--relative-weight-powers",
            "0,0.5",
            "--pole-f-min",
            "1000000",
            "--adaptive-worst-pair-count",
            "8",
            "--residue-bases",
            "complex,real-state",
            "--fit-max-frequency-points",
            "128",
            "--pole-pairings",
            "none,conjugate",
            "--relocation-bases",
            "complex,real-state",
            "--relocation-normalizations",
            "none,frequency",
            "--relocation-numerators",
            "complex,real",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls[0][4] == ["energy", "mixed"]
    assert calls[0][5] == [32, 64]
    assert calls[0][6] == [0.0, 0.5]
    assert calls[0][10] == 8
    assert calls[0][11] == ["complex", "real-state"]
    assert calls[0][13] == ["none", "conjugate"]
    assert calls[0][14] == ["complex", "real-state"]
    assert calls[0][15] == ["none", "frequency"]
    assert calls[0][16] == ["complex", "real"]
    assert "best z_log_rms=1.1 iter=2 label=mixed_n32_w0.5" in captured.out
    assert json.loads(report.read_text(encoding="utf-8"))["sweep_label"] == "mixed_n32_w0.5"
    assert "response_selection" in csv_path.read_text(encoding="utf-8")


def test_fit_idem_like_cli_writes_best_report(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    calls = []

    def fake_fit(
        touchstone,
        *,
        order=32,
        iterations=4,
        parameter_type="s",
        pole_damping=0.05,
        pole_spacing="lin",
        pole_f_min=None,
        response_selection="energy",
        adaptive_worst_pair_count=16,
        residue_basis="real-state",
        fit_max_frequency_points=256,
        max_pole_responses=64,
        relative_weight_power=0.0,
        pole_pairing="none",
        relocation_basis="complex",
        relocation_normalization="none",
        relocation_numerator="complex",
        rcond=None,
        selection_metric="z_log_magnitude_rms_error",
        model_output_path=None,
    ):
        calls.append(
            (
                touchstone,
                order,
                iterations,
                parameter_type,
                residue_basis,
                fit_max_frequency_points,
                max_pole_responses,
                pole_pairing,
                relocation_basis,
                relocation_normalization,
                relocation_numerator,
                selection_metric,
                model_output_path,
            )
        )
        best = {
            "probe": "local_common_pole_relocation",
            "iteration": 3,
            "order": order,
            "parameter_type": parameter_type,
            "relative_weight_power": relative_weight_power,
            "pole_damping": pole_damping,
            "pole_spacing": pole_spacing,
            "pole_f_min": pole_f_min,
            "response_selection": response_selection,
            "pole_pairing": pole_pairing,
            "relocation_basis": relocation_basis,
            "relocation_normalization": relocation_normalization,
            "relocation_numerator": relocation_numerator,
            "basis": residue_basis,
            "fit_frequency_points": fit_max_frequency_points,
            "selected_response_count": max_pole_responses,
            "relocation_condition_number": 10.0,
            "condition_number": 100.0,
            "s_relative_rms_error": 0.01,
            "z_log_magnitude_rms_error": 0.99,
            "diagonal_z_log_magnitude_rms_error": 1.1,
            "max_abs_z_error_ohm": 2.0,
            "pole_frequencies_hz": [1.0, 2.0],
        }
        return {
            "probe": "local_idem_like_fit",
            "selection_metric": selection_metric,
            "recipe": {"order": order, "residue_basis": residue_basis},
            "best": best,
            "iterations": [best],
        }

    monkeypatch.setattr(cli, "run_local_idem_like_fit", fake_fit)

    report = tmp_path / "idem_like.json"
    csv_path = tmp_path / "idem_like.csv"
    exit_code = main(
        [
            "fit-idem-like",
            str(tmp_path / "line.s2p"),
            "--report",
            str(report),
            "--csv",
            str(csv_path),
            "--model-output",
            str(tmp_path / "idem_like.npz"),
            "--order",
            "32",
            "--iterations",
            "4",
            "--residue-basis",
            "real-state",
            "--fit-max-frequency-points",
            "128",
            "--max-pole-responses",
            "32",
            "--pole-pairing",
            "conjugate",
            "--relocation-basis",
            "real-state",
            "--relocation-normalization",
            "frequency",
            "--relocation-numerator",
            "real",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls[0][1:] == (
        32,
        4,
        "s",
        "real-state",
        128,
        32,
        "conjugate",
        "real-state",
        "frequency",
        "real",
        "z_log_magnitude_rms_error",
        tmp_path / "idem_like.npz",
    )
    assert "fit-idem-like best iter=3 basis=real-state" in captured.out
    assert json.loads(report.read_text(encoding="utf-8"))["best"]["z_log_magnitude_rms_error"] == 0.99
    assert "z_log_magnitude_rms_error" in csv_path.read_text(encoding="utf-8")


def test_fit_idem_like_cli_idem_compact_recipe_sets_compact_defaults(tmp_path: Path, monkeypatch):
    import agent_spice.cli as cli

    calls = []

    def fake_fit(
        touchstone,
        *,
        order=32,
        iterations=4,
        parameter_type="s",
        pole_damping=0.05,
        pole_spacing="lin",
        pole_f_min=None,
        response_selection="energy",
        adaptive_worst_pair_count=16,
        residue_basis="real-state",
        fit_max_frequency_points=256,
        max_pole_responses=64,
        relative_weight_power=0.0,
        pole_pairing="none",
        relocation_basis="complex",
        relocation_normalization="none",
        relocation_numerator="complex",
        rcond=None,
        selection_metric="z_log_magnitude_rms_error",
        model_output_path=None,
    ):
        calls.append(
            (
                iterations,
                pole_spacing,
                pole_f_min,
                pole_pairing,
                residue_basis,
                fit_max_frequency_points,
                max_pole_responses,
            )
        )
        best = {
            "probe": "local_common_pole_relocation",
            "iteration": 1,
            "order": order,
            "parameter_type": parameter_type,
            "relative_weight_power": relative_weight_power,
            "pole_damping": pole_damping,
            "pole_spacing": pole_spacing,
            "pole_f_min": pole_f_min,
            "response_selection": response_selection,
            "pole_pairing": pole_pairing,
            "relocation_basis": relocation_basis,
            "relocation_normalization": relocation_normalization,
            "relocation_numerator": relocation_numerator,
            "basis": residue_basis,
            "fit_frequency_points": fit_max_frequency_points,
            "selected_response_count": max_pole_responses,
            "relocation_condition_number": 10.0,
            "condition_number": 100.0,
            "s_relative_rms_error": 0.01,
            "z_log_magnitude_rms_error": 0.99,
            "diagonal_z_log_magnitude_rms_error": 1.1,
            "max_abs_z_error_ohm": 2.0,
            "pole_frequencies_hz": [1.0, 2.0],
        }
        return {"probe": "local_idem_like_fit", "recipe": {}, "best": best, "iterations": [best]}

    monkeypatch.setattr(cli, "run_local_idem_like_fit", fake_fit)

    report = tmp_path / "idem_like_recipe.json"
    exit_code = main(["fit-idem-like", str(tmp_path / "line.s2p"), "--recipe", "idem-compact", "--report", str(report)])

    assert exit_code == 0
    assert calls == [(2, "log", 1.0e7, "conjugate", "real-state", 128, 128)]
    assert json.loads(report.read_text(encoding="utf-8"))["recipe"]["cli_recipe"] == "idem-compact"


def test_eval_idem_like_model_cli_writes_report(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    def fake_eval(model, touchstone):
        return {
            "probe": "local_idem_like_model_eval",
            "model_path": str(model),
            "touchstone_path": str(touchstone),
            "parameter_type": "s",
            "basis": "real-state",
            "ports": 2,
            "frequency_points": 3,
            "pole_count": 32,
            "basis_term_count": 33,
            "s_rms_error": 0.01,
            "s_relative_rms_error": 0.02,
            "z_log_magnitude_rms_error": 0.99,
            "diagonal_z_log_magnitude_rms_error": 1.1,
            "max_abs_z_error_ohm": 2.0,
        }

    monkeypatch.setattr(cli, "evaluate_local_idem_like_model", fake_eval)

    report = tmp_path / "eval.json"
    exit_code = main(
        [
            "eval-idem-like-model",
            str(tmp_path / "model.npz"),
            str(tmp_path / "line.s2p"),
            "--report",
            str(report),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "eval-idem-like-model basis=real-state poles=32 z_log_rms=0.99" in captured.out
    assert json.loads(report.read_text(encoding="utf-8"))["basis"] == "real-state"


def test_refine_idem_like_cli_writes_report(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    calls = []

    def fake_refine(
        model,
        touchstone,
        output,
        *,
        iterations=1,
        candidate_pair_count=6,
        relative_step=0.02,
        fit_max_frequency_points=128,
        selection_metric="z_log_magnitude_rms_error",
        rcond=None,
    ):
        calls.append(
            (
                model,
                touchstone,
                output,
                iterations,
                candidate_pair_count,
                relative_step,
                fit_max_frequency_points,
                selection_metric,
                rcond,
            )
        )
        return {
            "probe": "local_idem_like_joint_refine",
            "output_path": str(output),
            "initial": {
                "z_log_magnitude_rms_error": 0.9,
                "diagonal_z_log_magnitude_rms_error": 0.8,
                "s_relative_rms_error": 0.2,
            },
            "best": {
                "z_log_magnitude_rms_error": 0.7,
                "diagonal_z_log_magnitude_rms_error": 0.6,
                "s_relative_rms_error": 0.1,
            },
            "history": [],
        }

    monkeypatch.setattr(cli, "refine_local_idem_like_model", fake_refine)

    report = tmp_path / "refine.json"
    output = tmp_path / "refined.npz"
    exit_code = main(
        [
            "refine-idem-like",
            str(tmp_path / "model.npz"),
            str(tmp_path / "line.s2p"),
            "--output",
            str(output),
            "--report",
            str(report),
            "--iterations",
            "2",
            "--candidate-pair-count",
            "4",
            "--relative-step",
            "0.01",
            "--fit-max-frequency-points",
            "64",
            "--selection-metric",
            "s_relative_rms_error",
            "--rcond",
            "1e-12",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert calls == [
        (
            tmp_path / "model.npz",
            tmp_path / "line.s2p",
            output,
            2,
            4,
            0.01,
            64,
            "s_relative_rms_error",
            1e-12,
        )
    ]
    assert "refine-idem-like output=" in captured.out
    assert json.loads(report.read_text(encoding="utf-8"))["best"]["s_relative_rms_error"] == 0.1


def test_export_idem_like_touchstone_cli_writes_report(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    def fake_export(model, output, *, reference_touchstone_path):
        return {
            "probe": "local_idem_like_touchstone_export",
            "model_path": str(model),
            "reference_touchstone_path": str(reference_touchstone_path),
            "output_path": str(output),
            "ports": 2,
            "frequency_points": 3,
            "frequency_range_hz": [1.0, 3.0],
        }

    monkeypatch.setattr(cli, "export_local_idem_like_touchstone", fake_export)

    report = tmp_path / "export.json"
    output = tmp_path / "fit.s2p"
    exit_code = main(
        [
            "export-idem-like-touchstone",
            str(tmp_path / "model.npz"),
            str(output),
            "--reference",
            str(tmp_path / "line.s2p"),
            "--report",
            str(report),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"export-idem-like-touchstone output={output}" in captured.out
    assert json.loads(report.read_text(encoding="utf-8"))["ports"] == 2


def test_export_idem_like_statespace_cli_writes_report(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    def fake_export(model, output):
        return {
            "probe": "local_idem_like_state_space_export",
            "model_path": str(model),
            "output_path": str(output),
            "parameter_type": "s",
            "basis": "real-state",
            "ports": 2,
            "states": 64,
            "pole_count": 32,
        }

    monkeypatch.setattr(cli, "export_local_idem_like_state_space", fake_export)

    report = tmp_path / "statespace_export.json"
    output = tmp_path / "statespace.npz"
    exit_code = main(
        [
            "export-idem-like-statespace",
            str(tmp_path / "model.npz"),
            str(output),
            "--report",
            str(report),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert f"export-idem-like-statespace output={output}" in captured.out
    assert json.loads(report.read_text(encoding="utf-8"))["states"] == 64


def test_eval_idem_like_statespace_cli_writes_report(tmp_path: Path, monkeypatch, capsys):
    import agent_spice.cli as cli

    def fake_eval(statespace, touchstone):
        return {
            "probe": "local_idem_like_state_space_eval",
            "state_space_path": str(statespace),
            "touchstone_path": str(touchstone),
            "parameter_type": "s",
            "basis": "real-state",
            "ports": 2,
            "states": 64,
            "pole_count": 32,
            "s_rms_error": 0.01,
            "s_relative_rms_error": 0.02,
            "z_log_magnitude_rms_error": 0.99,
            "diagonal_z_log_magnitude_rms_error": 1.1,
            "max_abs_z_error_ohm": 2.0,
        }

    monkeypatch.setattr(cli, "evaluate_local_idem_like_state_space", fake_eval)

    report = tmp_path / "statespace_eval.json"
    exit_code = main(
        [
            "eval-idem-like-statespace",
            str(tmp_path / "statespace.npz"),
            str(tmp_path / "line.s2p"),
            "--report",
            str(report),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "eval-idem-like-statespace basis=real-state states=64 z_log_rms=0.99" in captured.out
    assert json.loads(report.read_text(encoding="utf-8"))["basis"] == "real-state"
