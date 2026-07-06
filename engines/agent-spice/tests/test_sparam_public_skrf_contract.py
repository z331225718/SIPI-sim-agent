import inspect

import agent_spice.sparam.benchmark as benchmark
import agent_spice.sparam.fitting as fitting


def test_sparam_code_does_not_call_private_skrf_vector_fitting_core():
    source = inspect.getsource(fitting) + inspect.getsource(benchmark)

    forbidden_fragments = [
        "_pole_relocation(",
        "_fit_residues(",
        "_get_ABCDE(",
        "skrf.vectorFitting._",
    ]
    for fragment in forbidden_fragments:
        assert fragment not in source
