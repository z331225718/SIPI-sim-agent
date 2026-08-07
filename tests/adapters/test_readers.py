from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "sipi-contracts" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "sipi-adapters" / "src"))

from sipi_adapters import PROFILES, ReaderError, cross_profile_fixture_matrix, read_network


class ReaderTests(unittest.TestCase):
    def test_each_profile_reads_into_valid_tensor(self):
        matrix = cross_profile_fixture_matrix()
        tensors = {}
        for profile in PROFILES:
            with self.subTest(profile=profile):
                tensor = read_network(profile, matrix[profile])
                tensors[profile] = tensor
                self.assertEqual(tensor.to_wire()["reader"]["source_reader"], PROFILES[profile]["source_reader"])
                self.assertEqual(tensor.to_wire()["reader"]["reader_semantics"], PROFILES[profile]["semantics"])

    def test_cross_profile_fixtures_share_semantic_input(self):
        matrix = cross_profile_fixture_matrix()
        data_hashes = {profile: matrix[profile]["data"]["sha256"] for profile in PROFILES}
        self.assertEqual(len(set(data_hashes.values())), 1)
        shapes = {profile: tuple(matrix[profile]["shape"].values()) for profile in PROFILES}
        self.assertEqual(len(set(shapes.values())), 1)
        semantics = {read_network(profile, matrix[profile]).to_wire()["reader"]["reader_semantics"] for profile in PROFILES}
        self.assertEqual(len(semantics), len(PROFILES))

    def test_unknown_profile_and_missing_fields_fail_closed(self):
        matrix = cross_profile_fixture_matrix()
        with self.assertRaises(ReaderError):
            read_network("unknown", matrix["com-r480"])
        broken = dict(matrix["com-r480"])
        del broken["axis"]
        with self.assertRaises(ReaderError):
            read_network("com-r480", broken)


if __name__ == "__main__":
    unittest.main()
