from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.sparam_native_frontier_probe as probe


def _fit_result(*, iteration: int) -> SimpleNamespace:
    return SimpleNamespace(
        comparison_mean_rms_error=0.0011 if iteration == 8 else 0.00094,
        passivity_max_sigma_before=1.0 if iteration == 8 else 1.02,
        passivity_max_sigma_frequency_hz_before=1.0e9,
        passivity_violations_before=[] if iteration == 8 else [[9.0e8, 1.1e9]],
        fit_seconds=3.5,
        check_seconds=1.25,
        elapsed_seconds=5.0,
        peak_memory_mb=42.0,
        expanded_model_order=94,
        real_pole_count=86,
        complex_pair_count=4,
        stored_pole_count=90,
        fit_frequency_points=826,
        frequency_points=826,
        passive_before_enforce=iteration == 8,
        passivity_check_skip_reason=None,
    )


def test_frontier_probe_writes_auditable_candidate_records(tmp_path: Path, monkeypatch) -> None:
    touchstone = tmp_path / "fixture.s94p"
    touchstone.write_text("fixture", encoding="utf-8")
    output_root = tmp_path / "frontier"
    calls = []

    def fake_fit(path, output, *, config, report_path, log_path):
        calls.append((path, output, config, report_path, log_path))
        return _fit_result(iteration=config.max_iterations)

    monkeypatch.setattr(probe, "fit_touchstone_to_spice", fake_fit)
    recipes = (
        probe.FrontierRecipe(order=94, real_poles=86, complex_pairs=4, relocations=8),
        probe.FrontierRecipe(order=94, real_poles=86, complex_pairs=4, relocations=9),
    )

    summary = probe.run_frontier_probe(touchstone, output_root=output_root, recipes=recipes)

    assert len(calls) == 2
    assert summary["contract_version"] == "native_frontier_probe_v1"
    assert summary["input"]["sha256"]
    assert summary["candidates"][0]["raw_mean_rms"] == pytest.approx(0.0011)
    assert summary["candidates"][0]["pre_max_sigma"] == pytest.approx(1.0)
    assert summary["candidates"][1]["raw_mean_rms"] == pytest.approx(0.00094)
    assert summary["candidates"][1]["pre_max_sigma"] == pytest.approx(1.02)
    assert summary["candidates"][1]["violation_bands_hz"] == [[9.0e8, 1.1e9]]
    assert summary["candidates"][1]["config"]["fit_max_frequency_points"] is None
    assert (output_root / "summary.json").is_file()
    assert json.loads((output_root / "summary.json").read_text(encoding="utf-8")) == summary


def test_frontier_recipe_rejects_order_mismatch() -> None:
    with pytest.raises(ValueError, match=r"real_poles \+ 2 \* complex_pairs"):
        probe.FrontierRecipe(order=10, real_poles=7, complex_pairs=2, relocations=8)


def test_frontier_probe_can_enable_relocation_checkpoint_selection() -> None:
    recipe = probe.FrontierRecipe(order=94, real_poles=46, complex_pairs=24, relocations=9)

    config = probe._config_for(recipe, fit_aware_frontier=True)

    assert config.native_relocation_frontier_enabled is True
    assert config.native_relocation_frontier_passivity_weight == 1.0
