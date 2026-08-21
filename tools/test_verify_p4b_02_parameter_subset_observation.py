"""Mutation tests for the P4B-02 hash-only observation verifier."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import verify_p4b_02_parameter_subset_observation as gate


class ParameterSubsetObservationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = gate._load(gate.EVIDENCE)

    def _path(self, document: dict) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / gate.EVIDENCE.name
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_current_observation_is_valid(self) -> None:
        result = gate.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["tx_selected_count"], 8)
        self.assertEqual(result["rx_selected_count"], 30)
        self.assertFalse(result["dll_loaded"])
        self.assertFalse(result["ami_init_invoked"])
        self.assertFalse(result["ami_get_wave_invoked"])

    def test_rejects_source_digest_mutation(self) -> None:
        document = copy.deepcopy(self.document)
        document["profiles"]["tx"]["source_sha256"] = "0" * 64
        with patch.object(gate, "EVIDENCE", self._path(document)):
            with self.assertRaisesRegex(gate.ObservationError, "tx_source_sha256_invalid"):
                gate.validate()

    def test_rejects_runtime_claim(self) -> None:
        document = copy.deepcopy(self.document)
        document["runtime_observation"]["ami_init_invoked"] = True
        with patch.object(gate, "EVIDENCE", self._path(document)):
            with self.assertRaisesRegex(gate.ObservationError, "runtime_claim_invalid"):
                gate.validate()

    def test_rejects_selected_count_mutation(self) -> None:
        document = copy.deepcopy(self.document)
        document["profiles"]["rx"]["selected_count"] = 29
        with patch.object(gate, "EVIDENCE", self._path(document)):
            with self.assertRaisesRegex(gate.ObservationError, "rx_selected_count_invalid"):
                gate.validate()

    def test_rejects_raw_value_field(self) -> None:
        document = copy.deepcopy(self.document)
        document["profiles"]["tx"]["value_token"] = "0.886"
        with patch.object(gate, "EVIDENCE", self._path(document)):
            with self.assertRaisesRegex(gate.ObservationError, "raw_value_leak"):
                gate.validate()


if __name__ == "__main__":
    unittest.main()
