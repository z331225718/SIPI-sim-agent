"""Mutation tests for selected-S4P raw-periodic observation evidence."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from verify_p3c_selected_s4p_raw_periodic_observation_evidence import VerificationError, verify_document




ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "baselines" / "p3c-selected-s4p-raw-periodic-observation-evidence.v1.yaml"

