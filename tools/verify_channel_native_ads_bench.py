"""Re-read ADS datasets and recompute every frozen pointwise gate, without simulating."""

import argparse
import csv
from pathlib import Path

import numpy as np
import keysight.ads.dataset as dataset

import run_channel_native_ads_bench as bench


def npz(path):
    with np.load(path, allow_pickle=False) as bundle:
        return {name: bundle[name] for name in bundle.files}


def csv_rows(path):
    with path.open(encoding="ascii", newline="") as stream:
        return list(csv.DictReader(stream))


def column(rows, key, dtype=float):
    return np.asarray([dtype(row[key]) for row in rows])


def verify(directory):
    plan = bench.read_json(directory / "plan.json")
    bench.validate_plan(plan)
    bindings = bench.read_json(directory / "bindings.json")
    result = bench.read_json(directory / "result.json")
    assert bindings["plan_sha256"] == bench.digest(directory / "plan.json")
    assert bindings["script_sha256"] == bench.digest(directory / "runner-source.py")
    selected = bindings["selected_cases"]
    expected = [case for case in plan["cases"] if not selected or case["name"] in selected]
    assert [case["name"] for case in expected] == [case["name"] for case in result["cases"]]
    assert result["all_plan_cases_selected"] == (len(expected) == len(plan["cases"]))
    assert result["acceptance"] is False and "error" not in result
    checked = []
    for spec, recorded in zip(expected, result["cases"]):
        assert "error" not in recorded and recorded["repeatable"] is True
        assert len(recorded["runs"]) == bench.REPEATS
        request = spec["request"]
        repeats = []
        for repeat, report in enumerate(recorded["runs"], 1):
            work = directory / spec["name"] / f"repeat-{repeat}"
            candidate, ads = work / "candidate", work / "ads"
            assert bench.read_json(work / "request.json") == request
            assert (candidate / "request.json").read_bytes() == (work / "request.json").read_bytes()
            inputs = bench.read_json(work / "input-bindings.json")
            for key, path in [("request", work / "request.json"), ("netlist", ads / "requested.ckt"), ("material", ads / "material.json")]:
                assert inputs[key + "_sha256"] == bench.digest(path)
            generated, material = bench.netlist(request)
            assert generated.encode("ascii") == (ads / "requested.ckt").read_bytes()
            np.testing.assert_array_equal(bench.read_json(ads / "material.json")["rows"], material)
            receipt = bench.read_json(candidate / "receipt.json")
            assert receipt["backend"] == "in_process_sipi_pybert_direct" and receipt["acceptance"] is False
            assert receipt["executable"]["sha256"] == bindings["sipi_sha256"]
            assert report["receipt_sha256"] == bench.digest(candidate / "receipt.json")
            assert set(receipt["artifacts"]) == {"request.json", "meta.json", "arrays.npz", "waveforms.csv", "channel-impulse.csv", "report.html"}
            for name, identity in receipt["artifacts"].items():
                assert Path(name).name == name
                assert identity["sha256"] == bench.digest(candidate / name)
                assert identity["byte_length"] == (candidate / name).stat().st_size
            arrays, raw = npz(candidate / "arrays.npz"), npz(ads / "raw.npz")
            inventory = bench.read_json(ads / "dataset.json")
            for key, name in [("dataset", "channel_native_ads.ds"), ("raw", "raw.npz"), ("executed_netlist", "executed.ckt"), ("solver_log", "hpeesofsim.out")]:
                assert inventory[key + "_sha256"] == bench.digest(ads / name)
            assert report["dataset_sha256"] == inventory["dataset_sha256"]
            assert (ads / "executed.ckt").read_bytes().replace(b"\r\n", b"\n") == (ads / "requested.ckt").read_bytes()
            sdk = {}
            with dataset.open_dataset_for_reading(ads / "channel_native_ads.ds") as ds:
                assert list(ds.varblock_names) == [table["name"] for table in inventory["tables"]]
                for table in inventory["tables"]:
                    frame = ds[table["name"]].to_dataframe()
                    assert frame.index.nlevels == 1 and frame.index.name == table["axis"]
                    assert list(frame.columns) == table["columns"] and len(frame) == table["points"]
                    prefix = table["prefix"]
                    sdk[prefix + "__axis"] = frame.index.to_numpy()
                    sdk.update({prefix + "__" + name: frame[name].to_numpy() for name in frame.columns})
            assert set(sdk) == set(raw)
            for name in sdk:
                assert np.isfinite(sdk[name]).all()
                np.testing.assert_array_equal(raw[name], sdk[name])
            ac = next(table["prefix"] for table in inventory["tables"] if table["axis"] == "freq")
            tran = next(table["prefix"] for table in inventory["tables"] if table["axis"] == "time")
            time = arrays["time_s"]
            tb = request["timebase"]
            np.testing.assert_array_equal(time, np.arange(tb["nbits"] * tb["samplesPerUi"]) * tb["sampleInterval"])
            np.testing.assert_array_equal(arrays["tx_waveform_v"], np.repeat(np.asarray(request["pattern"]["bits"]) * 2 - 1, tb["samplesPerUi"]) * request["tx"]["amplitude"])
            waveform = csv_rows(candidate / "waveforms.csv")
            for name in waveform[0]:
                np.testing.assert_array_equal(column(waveform, name), arrays[name])
            impulse = csv_rows(candidate / "channel-impulse.csv")
            np.testing.assert_array_equal(column(impulse, "channel_impulse_v_per_v"), arrays["channel_impulse_v_per_v"])
            np.testing.assert_array_equal(column(impulse, "time_s"), np.arange(len(impulse)) * tb["sampleInterval"])
            rows = csv_rows(work / "time-pointwise.csv")
            assert len(rows) == len(time)
            np.testing.assert_array_equal(column(rows, "index", int), np.arange(len(time)))
            indices = column(rows, "ads_index", int)
            assert len(np.unique(indices)) == len(time) and np.all(indices >= 0) and np.all(indices < len(raw[tran + "__axis"]))
            np.testing.assert_array_equal(column(rows, "time_s"), time)
            np.testing.assert_array_equal(column(rows, "ads_time_s"), raw[tran + "__axis"][indices])
            origin = bench.REFERENCE["ads_clock_origin_ui"] * tb["samplesPerUi"] * tb["sampleInterval"]
            assert report["ads_clock_origin_s"] == origin
            error = abs(raw[tran + "__axis"][indices] - (origin + time))
            assert np.all(error <= np.maximum(plan["time_key_absolute_tolerance_s"], 4 * np.spacing(origin + time)))
            assert error.max() == report["maximum_time_key_error_s"]
            reference = raw[tran + "__output"][indices]
            for key, values in [("sipi_tx_v", arrays["tx_waveform_v"]), ("ads_half_open_source_v", raw[tran + "__source"][indices] / 2), ("sipi_channel_v", arrays["channel_output_v"]), ("ads_load_v", reference), ("difference_v", arrays["channel_output_v"] - reference), ("allowed_v", plan["voltage_tolerance"]["absolute"] + plan["voltage_tolerance"]["relative"] * abs(reference))]:
                np.testing.assert_array_equal(column(rows, key), values)
            gates = {"source_delivery": bench.gate(arrays["tx_waveform_v"], raw[tran + "__source"][indices] / 2, plan["voltage_tolerance"])}
            for name in ("channel_output_v", "rx_input_v", "rx_output_v"):
                gates[name] = bench.gate(reference, arrays[name], plan["voltage_tolerance"])
            frequency = bench.frequencies(request)
            np.testing.assert_array_equal(raw[ac + "__axis"], frequency)
            np.testing.assert_array_equal(raw[ac + "__source"], np.full(len(frequency), 2, dtype=complex))
            kernel = np.fft.rfft(arrays["channel_impulse_v_per_v"], n=round(1 / (frequency[1] * tb["sampleInterval"])))[:len(frequency)]
            physical = bench.material_transfer(request, frequency)
            ac_reference = raw[ac + "__output"]
            gates["ads_vs_material_equations"] = bench.gate(physical, ac_reference, plan["transfer_tolerance"])
            gates["physical_vs_kernel_dtft"] = bench.gate(ac_reference, kernel, plan["transfer_tolerance"])
            fd = csv_rows(work / "frequency-pointwise.csv")
            np.testing.assert_array_equal(column(fd, "frequency_hz"), frequency)
            fields = {"ads": ac_reference, "kernel": kernel, "material": physical}
            if "legacy_channel_terminated_re" in arrays:
                fields["terminated"] = arrays["legacy_channel_terminated_re"] + 1j * arrays["legacy_channel_terminated_im"]
                gates["physical_vs_legacy_terminated"] = bench.gate(ac_reference, fields["terminated"], plan["transfer_tolerance"])
                np.testing.assert_array_equal(column(fd, "terminated_abs_error"), [abs(value) for value in fields["terminated"] - ac_reference])
            else:
                assert all(row["terminated_h_re"] == row["terminated_h_im"] == row["terminated_abs_error"] == "" for row in fd)
            for key, values in fields.items():
                np.testing.assert_array_equal(column(fd, key + "_h_re"), values.real)
                np.testing.assert_array_equal(column(fd, key + "_h_im"), values.imag)
            # CSV uses scalar complex abs; gates use NumPy's vector abs. Verify
            # each exact operation, rather than relaxing a rounding tolerance.
            np.testing.assert_array_equal(column(fd, "kernel_abs_error"), [abs(value) for value in kernel - ac_reference])
            np.testing.assert_array_equal(column(fd, "ads_material_abs_error"), [abs(value) for value in ac_reference - physical])
            assert gates == report["gates"]
            assert report["passed"] == all(g["passed"] for g in gates.values())
            assert report["oracle_contract_passed"] == gates["ads_vs_material_equations"]["passed"]
            assert report == bench.read_json(work / "comparison.json")
            for hashes in (report["csv_sha256"], report["plot_sha256"]):
                for name, sha in hashes.items():
                    assert Path(name).name == name and bench.digest(work / name) == sha
            checked.append({"case": spec["name"], "repeat": repeat, "time_points": len(time), "frequency_points": len(frequency), "raw_ads_points": len(raw[tran + "__axis"]), "numerically_passed": report["passed"]})
            repeats.append((arrays, raw))
        for first, second in zip(repeats[0], repeats[1]):
            assert set(first) == set(second)
            for name in first:
                np.testing.assert_array_equal(first[name], second[name])
        assert recorded["passed"] == all(run["passed"] for run in recorded["runs"])
    assert result["status"] == ("passed" if all(case["passed"] for case in result["cases"]) else "failed")
    return {"verified_artifact_chain": True, "sdk_reexport_exact": True, "all_pointwise_gates_recomputed": True,
            "numerical_status": result["status"], "acceptance": False, "runs": checked,
            "result_sha256": bench.digest(directory / "result.json"), "verifier_sha256": bench.digest(__file__)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if __debug__ is False:
        raise RuntimeError("verification must not run with Python optimization")
    proof = verify(args.directory)
    bench.write_json(args.output, proof)
    print(f'Artifact chain verified: {len(proof["runs"])} runs; numerical status: {proof["numerical_status"]}; acceptance: false')
