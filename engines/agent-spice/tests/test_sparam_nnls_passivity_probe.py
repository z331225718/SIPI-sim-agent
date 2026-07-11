from __future__ import annotations

from scripts.sparam_nnls_passivity_probe import NnlsProbeRecipe, config_for_recipe


def test_nnls_probe_config_exercises_compressed_active_mode_without_damping() -> None:
    recipe = NnlsProbeRecipe(order=93, real_poles=45, complex_pairs=24, relocations=12)

    config = config_for_recipe(recipe, max_mode_responses=32)

    assert config.enforce_passivity is True
    assert config.fit_max_frequency_points is None
    assert config.passivity_spectral_projection_fallback is True
    assert config.passivity_spectral_projection_active_mode_candidate is True
    assert config.passivity_spectral_projection_active_mode_solver == "nnls"
    assert config.passivity_spectral_projection_active_mode_max_responses == 32
    assert config.passivity_global_damping_fallback is False


def test_probe_can_reproduce_current_projection_without_active_mode_nnls() -> None:
    recipe = NnlsProbeRecipe(order=94, real_poles=46, complex_pairs=24, relocations=12)

    config = config_for_recipe(recipe, active_mode=False)

    assert config.passivity_spectral_projection_fallback is True
    assert config.passivity_spectral_projection_active_mode_candidate is False
    assert config.passivity_global_damping_fallback is False
