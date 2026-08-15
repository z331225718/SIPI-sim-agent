from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Values:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def to_numpy(self) -> list[object]:
        return self.values


class Frame:
    def __init__(self, axis: list[float], values: list[complex]) -> None:
        self.index = Values(axis)
        self.values = values

    def __getitem__(self, key: str) -> Values:
        if key != "freqResp":
            raise KeyError(key)
        return Values(self.values)


class Block:
    def __init__(self, axis: list[float], values: list[complex]) -> None:
        self.frame = Frame(axis, values)

    def to_dataframe(self) -> Frame:
        return self.frame


class Dataset:
    def __init__(self, blocks: dict[str, Block]) -> None:
        self.blocks = blocks

    def __getitem__(self, name: str) -> Block:
        return self.blocks[name]

    def __enter__(self) -> "Dataset":
        return self

    def __exit__(self, *_: object) -> None:
        return None


def load_module(dataset: Dataset):
    package = types.ModuleType("keysight")
    ads = types.ModuleType("keysight.ads")
    dataset_module = types.ModuleType("keysight.ads.dataset")
    dataset_module.open_dataset_for_reading = lambda _: dataset
    saved = {name: sys.modules.get(name) for name in ("keysight", "keysight.ads", "keysight.ads.dataset")}
    sys.modules.update({"keysight": package, "keysight.ads": ads, "keysight.ads.dataset": dataset_module})
    try:
        spec = importlib.util.spec_from_file_location("common_nodes", ROOT / "tools/extract_p3c_ads_pre_final_common_nodes.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, prior in saved.items():
            if prior is None:
                del sys.modules[name]
            else:
                sys.modules[name] = prior


def fixture() -> Dataset:
    blocks: dict[str, Block] = {}
    s0_axis = [float(index) for index in range(1024)]
    final_axis = [index / 4.0 for index in range(4096)]
    for row in range(1, 5):
        for column in range(1, 5):
            base = complex(row * 10 + column, row - column)
            s0 = [base + complex(index, -index) for index in range(1024)]
            final = [complex(-index, index) for index in range(4096)]
            for index, value in enumerate(s0):
                final[4 * index] = value + complex(0.5, -0.25)
            blocks[f"TRAN.CHANNEL.CMP1_S0({row};{column})"] = Block(list(s0_axis), s0)
            blocks[f"TRAN.CHANNEL.CMP1_FFT_IMP({row};{column})"] = Block(list(final_axis), final)
    return Dataset(blocks)


def or_fixture() -> Dataset:
    blocks: dict[str, Block] = {}
    axis = [float(index) * 2.5 for index in range(7)]
    for row in range(1, 5):
        for column in range(1, 5):
            base = complex(row * 10 + column, row - column)
            blocks[f"TRAN.CHANNEL.CMP1_OR({row};{column})"] = Block(list(axis), [base + complex(index, -index) for index in range(len(axis))])
    return Dataset(blocks)


def or_s0_fixture() -> Dataset:
    blocks: dict[str, Block] = {}
    s0_axis = [float(index) for index in range(1024)]
    or_axis = [index / 4.0 for index in range(4096)]
    for row in range(1, 5):
        for column in range(1, 5):
            base = complex(row * 10 + column, row - column)
            original = [base + complex(index, -index) for index in range(4096)]
            s0 = [original[4 * index] + complex(0.5, -0.25) for index in range(1024)]
            blocks[f"TRAN.CHANNEL.CMP1_OR({row};{column})"] = Block(list(or_axis), original)
            blocks[f"TRAN.CHANNEL.CMP1_S0({row};{column})"] = Block(list(s0_axis), s0)
    return Dataset(blocks)


class CommonNodeExtractionTests(unittest.TestCase):
    def test_exact_four_to_one_summary_has_explicit_coordinates(self) -> None:
        module = load_module(fixture())
        result = module.extract(Path("external.ds"))
        self.assertEqual(result["common_node_count"], 1024)
        self.assertEqual(result["mapping"], "fft_imp_index_equals_4_times_s0_index")
        self.assertIn(result["full_matrix"]["max_row"], range(1, 5))
        self.assertIn(result["full_matrix"]["max_column"], range(1, 5))
        self.assertLess(result["full_matrix"]["max_common_index"], 1024)
        self.assertLess(result["selected_hdiff"]["max_common_index"], 1024)

    def test_non_exact_mapping_rejects_without_nearest_bin_fallback(self) -> None:
        data = fixture()
        data.blocks["TRAN.CHANNEL.CMP1_FFT_IMP(1;1)"].frame.index.values[4] = 1.1
        module = load_module(data)
        with self.assertRaisesRegex(module.ExtractError, "common_node_member_axis_mismatch"):
            module.extract(Path("external.ds"))

    def test_missing_common_node_rejects(self) -> None:
        data = fixture()
        for row in range(1, 5):
            for column in range(1, 5):
                data.blocks[f"TRAN.CHANNEL.CMP1_FFT_IMP({row};{column})"].frame.index.values[4] = 1.1
        module = load_module(data)
        with self.assertRaisesRegex(module.ExtractError, "common_node_missing_or_duplicate"):
            module.extract(Path("external.ds"))

    def test_non_four_to_one_mapping_rejects_without_reindexing(self) -> None:
        data = fixture()
        shifted = [-0.25] + [index / 4.0 for index in range(4095)]
        for row in range(1, 5):
            for column in range(1, 5):
                data.blocks[f"TRAN.CHANNEL.CMP1_FFT_IMP({row};{column})"].frame.index.values = list(shifted)
        module = load_module(data)
        with self.assertRaisesRegex(module.ExtractError, "common_node_mapping_not_exact_four_to_one"):
            module.extract(Path("external.ds"))

    def test_payload_is_bounded_to_the_reduced_s0_hdiff_surface(self) -> None:
        module = load_module(fixture())
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory) / "s0-hdiff.bin"
            result = module.extract(Path("external.ds"), payload)
            self.assertEqual(result["s0_hdiff_payload"]["byte_length"], len(b"sipi.p3c.ads-s0-hdiff-payload.v1\0") + 8 + 1024 * 24)
            self.assertEqual(payload.stat().st_size, result["s0_hdiff_payload"]["byte_length"])

    def test_or_payload_is_reduced_only_after_all_member_axes_match(self) -> None:
        module = load_module(or_fixture())
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory) / "or-hdiff.bin"
            result = module.extract_or(Path("external.ds"), payload)
            self.assertEqual(result["or_node_count"], 7)
            self.assertEqual(payload.stat().st_size, len(b"sipi.p3c.ads-or-hdiff-payload.v1\0") + 8 + 7 * 24)

    def test_or_member_axis_mismatch_is_rejected_before_payload_write(self) -> None:
        data = or_fixture()
        data.blocks["TRAN.CHANNEL.CMP1_OR(1;1)"].frame.index.values[1] = 2.75
        module = load_module(data)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(module.ExtractError, "or_member_axis_mismatch"):
                module.extract_or(Path("external.ds"), Path(directory) / "or-hdiff.bin")

    def test_or_s0_exact_four_to_one_exports_only_common_selected_pairs(self) -> None:
        module = load_module(or_s0_fixture())
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory) / "or-s0-hdiff.bin"
            result = module.extract_or_s0_common(Path("external.ds"), payload)
            self.assertEqual(result["common_node_count"], 1024)
            self.assertEqual(result["mapping"], "or_index_equals_4_times_s0_index")
            self.assertEqual(payload.stat().st_size, len(b"sipi.p3c.ads-or-s0-hdiff-payload.v1\0") + 8 + 1024 * 40)

    def test_or_s0_frequency_bit_mismatch_rejects_without_resampling(self) -> None:
        data = or_s0_fixture()
        for row in range(1, 5):
            for column in range(1, 5):
                data.blocks[f"TRAN.CHANNEL.CMP1_OR({row};{column})"].frame.index.values[4] = 1.0000000000000002
        module = load_module(data)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(module.ExtractError, "or_s0_mapping_not_exact_four_to_one"):
                module.extract_or_s0_common(Path("external.ds"), Path(directory) / "or-s0-hdiff.bin")


if __name__ == "__main__":
    unittest.main()
