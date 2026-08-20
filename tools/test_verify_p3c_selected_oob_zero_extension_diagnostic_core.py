"""Mutation tests for the selected OOB zero-extension diagnostic core."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from verify_p3c_selected_oob_zero_extension_diagnostic_core import VerificationError, verify_document




ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/baselines/p3c-selected-oob-zero-extension-diagnostic-core.v1.yaml"

