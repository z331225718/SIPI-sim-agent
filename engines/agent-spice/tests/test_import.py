import agent_spice
from agent_spice.cli import main


def test_package_version_is_exposed():
    assert agent_spice.__version__ == "0.1.0"


def test_cli_entry_point_is_importable():
    assert main([]) == 0
