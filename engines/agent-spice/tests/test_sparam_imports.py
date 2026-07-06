import json
import subprocess
import sys


def test_fitting_module_import_does_not_import_skrf():
    script = (
        "import json, sys; "
        "import agent_spice.sparam.fitting; "
        "print(json.dumps({'skrf_loaded': 'skrf' in sys.modules, "
        "'vectorfitting_loaded': 'skrf.vectorFitting' in sys.modules}))"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload == {"skrf_loaded": False, "vectorfitting_loaded": False}


def test_cli_module_import_does_not_import_skrf():
    script = (
        "import json, sys; "
        "import agent_spice.cli; "
        "print(json.dumps({'skrf_loaded': 'skrf' in sys.modules, "
        "'vectorfitting_loaded': 'skrf.vectorFitting' in sys.modules}))"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload == {"skrf_loaded": False, "vectorfitting_loaded": False}


def test_lightweight_native_fit_does_not_import_skrf(tmp_path):
    script = f"""
import json, sys
from pathlib import Path
from agent_spice.sparam.fitting import SParamFitConfig, fit_touchstone_to_spice
fit_touchstone_to_spice(
    Path('tests/fixtures/sparam/simple_through.s2p'),
    Path(r'{str(tmp_path / "model.sp")}'),
    config=SParamFitConfig(
        mode='manual',
        n_poles_real=1,
        n_poles_cmplx=1,
        fit_max_frequency_points=4,
        max_iterations=2,
        check_passivity=False,
        enforce_passivity=False,
        use_lightweight_network=True,
        vector_fit_backend='native',
    ),
)
print(json.dumps({{'skrf_loaded': 'skrf' in sys.modules, 'vectorfitting_loaded': 'skrf.vectorFitting' in sys.modules}}))
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(completed.stdout)
    assert payload == {"skrf_loaded": False, "vectorfitting_loaded": False}
