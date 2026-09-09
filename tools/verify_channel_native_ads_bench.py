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


def validate_candidate_artifact_names(receipt):
    names = {"request.json", "meta.json", "arrays.npz", "waveforms.csv", "channel-impulse.csv", "report.html"}
    if receipt.get("channel_policy", "pb-02-compat") == "physical-voltage-v1":
        names.add("frequency-response.csv")
    if "report_data_policy" in receipt:
        assert receipt["report_data_policy"] == "all_waveform_and_impulse_samples_embedded; original_f64; at_most_4096_contiguous_samples_per_view; no_decimation"
        names.add("channel-report.js")
    assert set(receipt["artifacts"]) == names


def checked_ads_arrays(directory):
    """Bind the executed circuit, dataset, export and fresh SDK read together."""
    if not __debug__:
        raise RuntimeError("verification must not run with Python optimization")
    inventory = bench.read_json(directory / "dataset.json")
    for key, name in [("dataset", "channel_native_ads.ds"), ("raw", "raw.npz"),
                      ("executed_netlist", "executed.ckt"), ("solver_log", "hpeesofsim.out")]:
        assert inventory[key + "_sha256"] == bench.digest(directory / name)
    assert (directory / "executed.ckt").read_bytes().replace(b"\r\n", b"\n") == (directory / "requested.ckt").read_bytes()
    raw, sdk = npz(directory / "raw.npz"), {}
    with dataset.open_dataset_for_reading(directory / "channel_native_ads.ds") as ds:
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
    return inventory, raw


def physical_transform_diagnostic(request, arrays, ac_reference, plan):
    """Isolate the declared DSP contract; this is not an ADS Transient oracle."""
    line, tb = request["channel"]["value"], request["timebase"]
    frequency = bench.frequencies(request)
    fft_size = round(1 / (frequency[1] * tb["sampleInterval"]))
    samples = round(line["impulseLength"] / tb["sampleInterval"]) if line.get("impulseLength") is not None else fft_size
    windowed = ac_reference.copy()
    if line["applyRaisedCosineWindow"]:
        windowed *= 0.5 * (1 + np.cos(np.pi * np.arange(len(frequency)) / (len(frequency) - 1)))
        windowed[-1] = 0
    spectrum = np.zeros(fft_size // 2 + 1, dtype=complex)
    spectrum[:len(windowed)] = windowed
    kernel = np.fft.irfft(spectrum, n=fft_size)[:samples]
    tx = np.repeat(np.asarray(request["pattern"]["bits"]) * 2 - 1, tb["samplesPerUi"]) * request["tx"]["amplitude"]
    waveform = np.convolve(tx, kernel)[:len(tx)]
    actual_windowed = arrays["physical_channel_windowed_re"] + 1j * arrays["physical_channel_windowed_im"]
    gates = {
        "windowed_voltage": bench.gate(windowed, actual_windowed, plan["transfer_tolerance"]),
        "origin_preserving_kernel": bench.gate(kernel, arrays["channel_impulse_v_per_v"], plan["transfer_tolerance"]),
        "zero_history_sample_hold_output": bench.gate(waveform, arrays["channel_output_v"], plan["voltage_tolerance"]),
    }
    return {"scope": "ADS AC plus declared window, zero-fill, IFFT, tail truncation and sample-hold convolution; not continuous-time ADS Transient",
            "fft_size": fft_size, "retained_kernel_samples": samples, "gates": gates,
            "passed": all(gate["passed"] for gate in gates.values()), "acceptance": False}


def verify(directory, *, allow_incomplete=False):
    if not __debug__:
        raise RuntimeError("verification must not run with Python optimization")
    plan = bench.read_json(directory / "plan.json")
    bench.validate_plan(plan)
    bindings = bench.read_json(directory / "bindings.json")
    result = bench.read_json(directory / "result.json")
    assert result["schema"] == "sipi.channel.ads-physical-bench-result." + plan["schema"].rsplit(".", 1)[1]
    assert bindings["plan_sha256"] == bench.digest(directory / "plan.json")
    assert bindings["script_sha256"] == bench.digest(directory / "runner-source.py")
    selected = bindings["selected_cases"]
    assert isinstance(selected, list) and len(selected) == len(set(selected))
    assert set(selected) <= {case["name"] for case in plan["cases"]}
    expected = [case for case in plan["cases"] if not selected or case["name"] in selected]
    assert expected and result["planned_cases"] == [case["name"] for case in plan["cases"]]
    assert [case["name"] for case in expected] == [case["name"] for case in result["cases"]]
    assert result["all_plan_cases_selected"] == (len(expected) == len(plan["cases"]))
    assert result["acceptance"] is False and "error" not in result
    checked, incomplete = [], []
    for spec, recorded in zip(expected, result["cases"]):
        complete = "error" not in recorded and recorded.get("repeatable") is True and len(recorded["runs"]) == bench.REPEATS
        if not complete:
            assert allow_incomplete, "incomplete case: " + spec["name"]
            assert recorded["passed"] is False and len(recorded["runs"]) <= bench.REPEATS
            incomplete.append({"case": spec["name"], "completed_runs": len(recorded["runs"]),
                               "recorded_error": recorded.get("error"), "uncompleted_artifacts_verified": False})
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
            generated, material = bench.netlist(request, plan["reference"])
            assert generated.encode("ascii") == (ads / "requested.ckt").read_bytes()
            np.testing.assert_array_equal(bench.read_json(ads / "material.json")["rows"], material)
            receipt = bench.read_json(candidate / "receipt.json")
            assert receipt["backend"] == "in_process_sipi_pybert_direct" and receipt["acceptance"] is False
            policy = plan.get("candidate_channel_policy", "pb-02-compat")
            assert receipt.get("channel_policy", "pb-02-compat") == policy
            assert receipt["executable"]["sha256"] == bindings["sipi_sha256"]
            assert report["receipt_sha256"] == bench.digest(candidate / "receipt.json")
            validate_candidate_artifact_names(receipt)
            for name, identity in receipt["artifacts"].items():
                assert Path(name).name == name
                assert identity["sha256"] == bench.digest(candidate / name)
                assert identity["byte_length"] == (candidate / name).stat().st_size
            arrays = npz(candidate / "arrays.npz")
            inventory, raw = checked_ads_arrays(ads)
            assert report["dataset_sha256"] == inventory["dataset_sha256"]
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
            origin = plan["reference"]["ads_clock_origin_ui"] * tb["samplesPerUi"] * tb["sampleInterval"]
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
            physical_v2 = plan["schema"] != bench.LEGACY_SCHEMA
            physical = bench.material_transfer(request, frequency, exact_dc=physical_v2)
            # Reconstruct from SDK-reexported nodes, not from paired CSV values.
            ac_reference = raw[ac + "__output"].copy()
            if physical_v2:
                assert frequency[0] == 0 and np.all(frequency[1:] > 0)
                np.testing.assert_array_equal(raw[ac + "__dc_source"], np.full(len(frequency), 2, dtype=complex))
                ac_reference[0] = raw[ac + "__dc_load"][0]
                assert report["raw_line_oracle_diagnostic"] == bench.gate(physical, raw[ac + "__output"], plan["transfer_tolerance"])
                assert report["dc_reference"] == {"frequency_hz": 0, "source": "ads_resistive_dc_limit",
                    "raw_line_h_re": float(raw[ac + "__output"][0].real), "raw_line_h_im": float(raw[ac + "__output"][0].imag),
                    "resistive_limit_h_re": float(ac_reference[0].real), "resistive_limit_h_im": float(ac_reference[0].imag)}
            gates["ads_vs_material_equations"] = bench.gate(physical, ac_reference, plan["transfer_tolerance"])
            gates["physical_vs_kernel_dtft"] = bench.gate(ac_reference, kernel, plan["transfer_tolerance"])
            fd = csv_rows(work / "frequency-pointwise.csv")
            np.testing.assert_array_equal(column(fd, "frequency_hz"), frequency)
            if physical_v2:
                np.testing.assert_array_equal(column(fd, "ads_raw_line_h_re"), raw[ac + "__output"].real)
                np.testing.assert_array_equal(column(fd, "ads_raw_line_h_im"), raw[ac + "__output"].imag)
                assert [row["reference_solver"] for row in fd] == ["ads_resistive_dc_limit"] + ["ads_distributed_line"] * (len(frequency) - 1)
            fields = {"ads": ac_reference, "kernel": kernel, "material": physical}
            if policy == "physical-voltage-v1":
                np.testing.assert_array_equal(arrays["physical_channel_frequency_hz"], frequency)
                voltage = arrays["physical_channel_voltage_re"] + 1j * arrays["physical_channel_voltage_im"]
                gates["physical_vs_voltage_transfer"] = bench.gate(ac_reference, voltage, plan["transfer_tolerance"])
                np.testing.assert_array_equal(column(fd, "sipi_physical_voltage_re"), voltage.real)
                np.testing.assert_array_equal(column(fd, "sipi_physical_voltage_im"), voltage.imag)
                np.testing.assert_array_equal(column(fd, "physical_voltage_abs_error"), [abs(value) for value in voltage - ac_reference])
                native_frequency = csv_rows(candidate / "frequency-response.csv")
                for key in native_frequency[0]:
                    name = "physical_channel_frequency_hz" if key == "frequency_hz" else key
                    np.testing.assert_array_equal(column(native_frequency, key), arrays[name])
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
            checked_run = {"case": spec["name"], "repeat": repeat, "time_points": len(time), "frequency_points": len(frequency), "raw_ads_points": len(raw[tran + "__axis"]), "numerically_passed": report["passed"]}
            if policy == "physical-voltage-v1":
                checked_run["declared_transform_diagnostic"] = physical_transform_diagnostic(request, arrays, ac_reference, plan)
            checked.append(checked_run)
            repeats.append((arrays, raw))
        if complete:
            for first, second in zip(repeats[0], repeats[1]):
                assert set(first) == set(second)
                for name in first:
                    np.testing.assert_array_equal(first[name], second[name])
        assert recorded["passed"] == (complete and all(run["passed"] for run in recorded["runs"]))
    assert result["status"] == ("passed" if all(case["passed"] for case in result["cases"]) else "failed")
    return {"verified_artifact_chain": not incomplete,
            "complete_bench_verified": not incomplete and result["all_plan_cases_selected"],
            "all_plan_cases_selected": result["all_plan_cases_selected"],
            "verification_scope": "completed_runs_only" if incomplete else "all_selected_runs",
            "incomplete_cases": incomplete, "sdk_reexport_exact": bool(checked), "all_pointwise_gates_recomputed": not incomplete,
            "completed_run_gates_recomputed": bool(checked),
            "numerical_status": result["status"], "acceptance": False, "runs": checked,
            "result_sha256": bench.digest(directory / "result.json"), "verifier_sha256": bench.digest(__file__)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-incomplete", action="store_true", help="verify completed runs only; missing/failed runs remain explicitly unverified")
    args = parser.parse_args()
    if __debug__ is False:
        raise RuntimeError("verification must not run with Python optimization")
    proof = verify(args.directory, allow_incomplete=args.allow_incomplete)
    bench.write_json(args.output, proof)
    print(f'Verified {proof["verification_scope"]}: {len(proof["runs"])} runs; complete bench verified: {proof["complete_bench_verified"]}; numerical status: {proof["numerical_status"]}; acceptance: false')
