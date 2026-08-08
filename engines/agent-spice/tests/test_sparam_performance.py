import pytest

from agent_spice.sparam.performance import blas_thread_environment, phase_profile


def test_blas_thread_environment_sets_every_supported_runtime_without_mutating_input():
    original = {"KEEP": "yes", "OMP_NUM_THREADS": "old"}

    result = blas_thread_environment(32, original)

    assert original == {"KEEP": "yes", "OMP_NUM_THREADS": "old"}
    assert result["KEEP"] == "yes"
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        assert result[name] == "32"


@pytest.mark.parametrize("threads", [0, -1, 1.5])
def test_blas_thread_environment_rejects_invalid_thread_budget(threads):
    with pytest.raises(ValueError, match="threads"):
        blas_thread_environment(threads)


def test_phase_profile_reports_wall_and_cpu_delta(monkeypatch):
    values = iter([10.0, 12.5])
    monkeypatch.setattr("agent_spice.sparam.performance.time.perf_counter", lambda: next(values))
    cpu = iter([3.0, 7.0])

    with phase_profile("native_fit", lambda: next(cpu)) as profile:
        pass

    assert profile.name == "native_fit"
    assert profile.wall_seconds == pytest.approx(2.5)
    assert profile.cpu_seconds == pytest.approx(4.0)
    assert profile.cpu_utilization_percent == pytest.approx(160.0)
