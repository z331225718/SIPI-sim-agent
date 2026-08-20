"""Mutation tests for the 04ag waveform-only historical source-drift record."""

from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from verify_p3c_external_ads_selected_highloss_waveform_only_historical_source_drift import VerificationError, verify_document




ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/baselines/p3c-external-ads-selected-highloss-waveform-only-historical-source-drift.v1.yaml"

