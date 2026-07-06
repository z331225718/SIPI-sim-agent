import numpy as np
import pytest

from agent_spice.sparam.passivity import sample_streaming_singular_values, sample_vector_fit_passivity


def test_streaming_passivity_checker_chunks_frequency_samples():
    calls = []
    freqs = np.array([0.0, 1.0, 2.0, 3.0])

    def provider(chunk_freqs):
        calls.append(list(chunk_freqs))
        matrices = np.zeros((len(chunk_freqs), 2, 2), dtype=complex)
        for index, freq in enumerate(chunk_freqs):
            matrices[index, 0, 0] = 1.2 if freq == 2.0 else 0.5
            matrices[index, 1, 1] = 0.5
        return matrices

    result = sample_streaming_singular_values(provider, freqs, nports=2, chunk_size=2, epsilon=1e-6)

    assert calls == [[0.0, 1.0], [2.0, 3.0]]
    assert result.max_sigma == 1.2
    assert result.max_sigma_frequency_hz == 2.0
    assert result.violation_bands_hz == [[2.0, 2.0]]
    assert result.frequency_points == 4
    assert result.chunk_size == 2


def test_streaming_passivity_checker_merges_contiguous_sampled_violations():
    freqs = np.array([0.0, 1.0, 2.0, 3.0])

    def provider(chunk_freqs):
        matrices = np.zeros((len(chunk_freqs), 2, 2), dtype=complex)
        for index, freq in enumerate(chunk_freqs):
            matrices[index, 0, 0] = 1.1 if freq in {1.0, 2.0} else 0.5
            matrices[index, 1, 1] = 0.5
        return matrices

    result = sample_streaming_singular_values(provider, freqs, nports=2, chunk_size=3, epsilon=1e-6)

    assert result.violation_bands_hz == [[1.0, 2.0]]


def test_streaming_passivity_checker_rejects_bad_provider_shape():
    def provider(chunk_freqs):
        return np.zeros((len(chunk_freqs), 2), dtype=complex)

    with pytest.raises(ValueError, match="provider returned shape"):
        sample_streaming_singular_values(provider, [1.0], nports=2, chunk_size=1)


def test_sample_vector_fit_passivity_builds_s_matrix_per_chunk():
    class FakeVectorFit:
        def __init__(self):
            self.calls = []

        def get_model_response(self, row, column, freqs=None):
            self.calls.append((row, column, tuple(freqs)))
            if row == column:
                return [0.5 if freq != 2.0 else 1.2 for freq in freqs]
            return [0.0 for _ in freqs]

    vector_fit = FakeVectorFit()

    result = sample_vector_fit_passivity(vector_fit, [1.0, 2.0, 3.0], nports=2, chunk_size=2)

    assert result.max_sigma == 1.2
    assert result.max_sigma_frequency_hz == 2.0
    assert result.violation_bands_hz == [[2.0, 2.0]]
    assert vector_fit.calls == [
        (0, 0, (1.0, 2.0)),
        (0, 1, (1.0, 2.0)),
        (1, 0, (1.0, 2.0)),
        (1, 1, (1.0, 2.0)),
        (0, 0, (3.0,)),
        (0, 1, (3.0,)),
        (1, 0, (3.0,)),
        (1, 1, (3.0,)),
    ]
