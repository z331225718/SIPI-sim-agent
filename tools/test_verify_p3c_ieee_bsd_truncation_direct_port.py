"""Mutation tests for the fixed IEEE BSD truncation direct-port boundary."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from verify_p3c_ieee_bsd_truncation_direct_port import DirectPortError, verify_document




ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "baselines" / "p3c-ieee-bsd-truncation-direct-port.v1.yaml"

