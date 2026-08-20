"""Mutation tests for the IEEE BSD bounded inline-causality direct port."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from verify_p3c_ieee_bsd_inline_causality_direct_port import DirectPortError, verify_document




ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs" / "baselines" / "p3c-ieee-bsd-inline-causality-direct-port.v1.yaml"

