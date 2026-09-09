"""SIPI-vs-ADS physical channel diagnostics. ADS Python is only the oracle host."""

from __future__ import annotations

import argparse
import cmath
import copy
import csv
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "sipi.channel.ads-physical-bench.v1"
REPEATS = 2
REFERENCE = {
    "kind": "physical_two_terminal_differential_equivalent",
    "launch": "ADS open-circuit source = 2 * SIPI TX; fixed before solving, not fitted gain",
    "fd": "ADS load voltage with a 2 V open source; compare native terminated telemetry and actual kernel DTFT separately",
    "td": "full original grid, no warmup discard, alignment, interpolation, scaling or candidate-fed kernel",
    "prehistory": "ADS starts with zero source and zero DC equilibrium; first launch after a fixed four-UI zero guard",
    "ads_clock_origin_ui": 4,
    "edge": "linear ramp lasting dt/8, ending at each symbol boundary",
    "rlgc": "declared material-law tables, never derived from SIPI output; ADS W_Element solves the line",
    "oracle_check": "ADS AC is also checked against the declared RLGC two-port equations; a failure is not attributed solely to SIPI",
    "td_bandwidth": "physical ADS convolution settings and extrapolation remain in the solver log; not assumed equivalent to the PB-02 window/trim",
    "dc_material_evaluation_rad_per_s": 1e-12,
}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, allow_nan=False, ensure_ascii=True, indent=2)
        stream.write("\n")


def read_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result

    def bad_constant(value):
        raise ValueError("nonfinite JSON constant: " + value)

    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs, parse_constant=bad_constant)


def initial_plan():
    base = read_json(ROOT / "examples/channel-native/metallic-line.json")
    base["timebase"]["nbits"] = 64
    base["pattern"] = {"kind": "explicit_bits", "bit_count": 64,
                       "bits": ([0] * 8 + [1] * 8 + [0, 1] * 8 + [1] * 16 + [0] * 16)}
    line = base["channel"]["value"]
    line.update(skinEffectResistanceOhmPerM=0, dcResistanceOhmPerM=0,
                lossTangent=0, sourceCapacitanceF=0, loadCapacitanceF=0,
                propagationVelocityMPerS=200e6, applyRaisedCosineWindow=False)
    cases = []
    for name, changes in [
        ("matched-native-grid", {"frequencyStepHz": None, "frequencyMaxHz": None, "impulseLength": None}),
        ("matched-legacy-grid", {}),
        ("mismatched-legacy-grid", {"characteristicImpedance": 85, "sourceImpedance": 35, "loadImpedance": 90}),
        ("source-cap", {"sourceCapacitanceF": 0.2e-12}),
        ("load-cap", {"loadCapacitanceF": 0.2e-12}),
        ("both-cap", {"sourceCapacitanceF": 0.2e-12, "loadCapacitanceF": 0.2e-12}),
        ("lossy-metallic", {"skinEffectResistanceOhmPerM": 1.452, "dcResistanceOhmPerM": 0.1876,
                            "lossTangent": 0.02, "sourceCapacitanceF": 0.2e-12, "loadCapacitanceF": 0.2e-12,
                            "propagationVelocityMPerS": 201e6, "applyRaisedCosineWindow": True}),
    ]:
        request = copy.deepcopy(base)
        request["runId"] = name
        request["channel"]["value"].update(changes)
        if name == "lossy-metallic":
            request["pattern"]["bits"] *= 8
            request["pattern"]["bit_count"] = 512
            request["timebase"]["nbits"] = 512
        cases.append({"name": name, "request": request})
    return {
        "schema": SCHEMA, "cases": cases, "repeats": REPEATS,
        "voltage_tolerance": {"absolute": 2e-8, "relative": 1e-7},
        "transfer_tolerance": {"absolute": 1e-9, "relative": 1e-8},
        "time_key_absolute_tolerance_s": 1e-24,
        "reference": copy.deepcopy(REFERENCE),
        "acceptance": False,
        "scope": "PB-02 physical-semantics diagnostic, not full link parity or release; mismatches must remain visible",
    }


def validate_plan(plan):
    if plan.get("schema") != SCHEMA or plan.get("repeats") != REPEATS or plan.get("acceptance") is not False:
        raise ValueError("wrong bench schema/repeats/acceptance")
    if plan.get("reference") != REFERENCE:
        raise ValueError("reference semantics must match the implemented physical bench")
    if not 1 <= len(plan["cases"]) <= 32:
        raise ValueError("bench case budget")
    names = set()
    for case in plan["cases"]:
        name = case["name"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name) or name in names:
            raise ValueError("invalid or repeated case name")
        names.add(name)
        request = case["request"]
        tb, pattern, line = request["timebase"], request["pattern"], request["channel"]
        if request["schema"] != "pybert.simulation.v1" or request["modulation"] != "nrz" or line["kind"] != "metallic_line":
            raise ValueError("bench requires the native NRZ metallic-line contract")
        if pattern["kind"] != "explicit_bits" or pattern["bit_count"] != tb["nbits"] or len(pattern["bits"]) != tb["nbits"]:
            raise ValueError("explicit bit inventory mismatch")
        if any(type(bit) is not int or bit not in (0, 1) for bit in pattern["bits"]):
            raise ValueError("invalid explicit bit")
        if any(type(tb[key]) is not int or tb[key] <= 0 for key in ("nbits", "samplesPerUi")):
            raise ValueError("sample counts must be positive integers")
        if type(pattern["bit_count"]) is not int:
            raise ValueError("bit count must be an integer")
        samples = tb["nbits"] * tb["samplesPerUi"]
        if not 32 <= samples <= 32768 or samples & (samples - 1):
            raise ValueError("bench requires a bounded power-of-two sample count")
        if not math.isclose(tb["sampleInterval"] * tb["samplesPerUi"] * tb["dataRate"], 1, rel_tol=1e-12):
            raise ValueError("inconsistent bench timebase")
        for value in (tb["sampleInterval"], tb["dataRate"], request["tx"]["amplitude"]):
            require_number(value, positive=True)
        if request["tx"]["ffe"]["enabled"] or request["tx"]["additiveNoise"] or request["tx"]["periodicNoise"]:
            raise ValueError("this line-stage bench does not model TX EQ/noise")
        if request["rx"]["nativeCtleEnabled"] or request["rx"]["ffe"]["enabled"] or request["rx"]["dfeTaps"] or request["rx"]["viterbiEnabled"]:
            raise ValueError("this line-stage bench does not model RX EQ")
        if request.get("externalModels") or request.get("legacyOptions"):
            raise ValueError("external and legacy branches are outside this physical line bench")
        line = line["value"]
        for key in ("sampleInterval", "lengthM", "crossoverAngularFrequencyRadPerS", "characteristicImpedance",
                    "propagationVelocityMPerS", "sourceImpedance", "loadImpedance"):
            require_number(line[key], positive=True)
        for key in ("skinEffectResistanceOhmPerM", "dcResistanceOhmPerM", "lossTangent", "sourceCapacitanceF", "loadCapacitanceF"):
            require_number(line[key])
        if line["sampleInterval"] != tb["sampleInterval"] or type(line["applyRaisedCosineWindow"]) is not bool:
            raise ValueError("channel grid/window contract mismatch")
        if (line["frequencyStepHz"] is None) != (line["frequencyMaxHz"] is None):
            raise ValueError("frequency grid requires both fields or neither")
        for key in ("frequencyStepHz", "frequencyMaxHz", "impulseLength"):
            if line[key] is not None:
                require_number(line[key], positive=True)
        if line["frequencyStepHz"] is not None:
            ratio = line["frequencyMaxHz"] / line["frequencyStepHz"]
            if not 1 <= ratio <= 32768 or line["frequencyMaxHz"] > 0.5 / tb["sampleInterval"]:
                raise ValueError("frequency grid budget")
    for group in ("voltage_tolerance", "transfer_tolerance"):
        if set(plan[group]) != {"absolute", "relative"}:
            raise ValueError("tolerance needs absolute and relative fields")
        for value in plan[group].values():
            require_number(value)
    require_number(plan["time_key_absolute_tolerance_s"])
    if plan["time_key_absolute_tolerance_s"] > 1e-24:
        raise ValueError("time tolerance cannot authorize nearest-neighbor resampling")


def require_number(value, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError("expected a finite nonnegative number (positive where required)")


def frequencies(request):
    import numpy as np
    tb, line = request["timebase"], request["channel"]["value"]
    if line["frequencyStepHz"] is None and line["frequencyMaxHz"] is None:
        return np.fft.rfftfreq(tb["nbits"] * tb["samplesPerUi"], tb["sampleInterval"])
    step, stop = line["frequencyStepHz"], line["frequencyMaxHz"]
    if not step or not stop or stop / step > 32768:
        raise ValueError("frequency grid budget")
    result = np.arange(0, stop + step, step)
    if result[-1] > 0.5 / tb["sampleInterval"]:
        raise ValueError("frequency exceeds native Nyquist")
    return result


def rlgc_rows(request, frequency):
    """Material parameters only; ADS, not this helper, solves the distributed network."""
    line = request["channel"]["value"]
    inductance = line["characteristicImpedance"] / line["propagationVelocityMPerS"]
    capacitance = 1 / (line["characteristicImpedance"] * line["propagationVelocityMPerS"])
    exponent = -2 * line["lossTangent"] / math.pi
    rows = []
    for f in frequency:
        w = 2 * math.pi * float(f) if f else 1e-12
        resistance = cmath.sqrt(line["dcResistanceOhmPerM"] ** 2 + 2j * w * line["skinEffectResistanceOhmPerM"] ** 2 / line["crossoverAngularFrequencyRadPerS"])
        admittance = 1j * w * capacitance * (1j * w / line["crossoverAngularFrequencyRadPerS"]) ** exponent
        row = (float(f), resistance.real, inductance + resistance.imag / w,
               admittance.real if f else 0.0, admittance.imag / w)
        if not all(math.isfinite(v) for v in row) or min(row[1:]) < 0 or row[2] == 0 or row[4] == 0:
            raise ValueError("non-passive/nonfinite RLGC material table")
        rows.append(row)
    return rows


def material_transfer(request, frequency):
    """Closed-form AC control for the oracle, never a SIPI input or TD engine."""
    import numpy as np
    material = np.asarray(rlgc_rows(request, frequency))
    line = request["channel"]["value"]
    w = 2 * np.pi * frequency
    series = material[:, 1] + 1j * w * material[:, 2]
    shunt = material[:, 3] + 1j * w * material[:, 4]
    q = np.sqrt(series * shunt) * line["lengthM"]
    sinhc = np.ones_like(q)
    np.divide(np.sinh(q), q, out=sinhc, where=q != 0)
    a = np.cosh(q)
    b, c = series * line["lengthM"] * sinhc, shunt * line["lengthM"] * sinhc
    source_divisor = 1 + 1j * w * line["sourceImpedance"] * line["sourceCapacitanceF"]
    zs = line["sourceImpedance"] / source_divisor
    zl = line["loadImpedance"] / (1 + 1j * w * line["loadImpedance"] * line["loadCapacitanceF"])
    return (2 * zl / source_divisor) / (a * zl + b + zs * (c * zl + a))


def netlist(request):
    import numpy as np
    line, tb = request["channel"]["value"], request["timebase"]
    dt, spb = tb["sampleInterval"], tb["samplesPerUi"]
    f = frequencies(request)
    bits = request["pattern"]["bits"]
    voltage = [(2 * bit - 1) * 2 * request["tx"]["amplitude"] for bit in bits]
    origin = REFERENCE["ads_clock_origin_ui"] * spb * dt
    pairs = [(0.0, 0.0), (origin - dt / 8, 0.0), (origin, voltage[0])]
    for i in range(1, len(bits)):
        t = origin + i * spb * dt
        pairs.extend([(t - dt / 8, voltage[i - 1]), (t, voltage[i])])
    stop = origin + (len(bits) * spb - 1) * dt
    pairs.append((stop, voltage[-1]))
    pwl = ",".join(f"{t:.17g},{v:.17g}" for t, v in pairs)
    observation = "0,0," + ",".join(f"{origin + i * dt:.17g},0" for i in range(len(bits) * spb))
    material = rlgc_rows(request, f)
    if line["skinEffectResistanceOhmPerM"] == line["dcResistanceOhmPerM"] == line["lossTangent"] == 0:
        component = f'TLIND:LINE input output Z={line["characteristicImpedance"]:.17g} Ohm Delay={line["lengthM"] / line["propagationVelocityMPerS"]:.17g} sec'
        library = 'TLIND'
    else:
        parameters = []
        for column, key in [(1, "R"), (2, "L"), (3, "G"), (4, "C")]:
            data = ",".join(f"{row[0]:.17g},{row[column]:.17g}" for row in material)
            parameters.append(f'{key}data=list({len(f)},{data}) {key}freqSweep=4')
        component = f'W_Element:LINE input 0 output 0 N=1 Length={line["lengthM"]:.17g} Model_type=1 ' + " ".join(parameters)
        library = None
    text = [
        f'#uselib "ckt" , "{library}"' if library else '; Native W_Element model',
        'Options:OPTIONS V_RelTol=1e-9 I_RelTol=1e-9 V_AbsTol=1e-12 I_AbsTol=1e-15',
        f'V_Source:SOURCE source 0 Vdc=0 V Vac=2 V V_Tran=pwl(time,{pwl}) SaveCurrent=no',
        f'R:SOURCE_R source input R={line["sourceImpedance"]:.17g} Ohm',
        f'C:SOURCE_C input 0 C={line["sourceCapacitanceF"]:.17g} F InitCond=0 V',
        component,
        f'R:LOAD_R output 0 R={line["loadImpedance"]:.17g} Ohm',
        f'C:LOAD_C output 0 C={line["loadCapacitanceF"]:.17g} F InitCond=0 V',
        f'V_Source:OBSERVATION observation 0 Vdc=0 V V_Tran=pwl(time,{observation}) SaveCurrent=no',
        'I_Source:OPEN observation 0 Idc=0 A Iac=0 A',
        'AC:AC1 SweepVar="freq" SweepPlan="FREQUENCIES" CalcNoise=no StatusLevel=2',
        'SweepPlan:FREQUENCIES ' + " ".join(f"Pt={x:.17g}" for x in f),
        f'Tran:TRAN StartTime=0 sec StopTime={stop:.17g} sec MaxTimeStep={dt / 4:.17g} sec '
        'TimeStepControl=2 TruncTol=7 ChargeTol=1e-16 IntegMethod=0 MaxOrder=4 UseInitCond=no OutputAllPoints=yes CheckKCL=yes MaxIters=50 MaxItersDC=200 StatusLevel=2',
    ]
    return "\n".join(text) + "\n", material


def worker(work, ads_root):
    import numpy as np
    from keysight.edatoolbox import ads
    import keysight.ads.dataset as dataset
    requested = work / "requested.ckt"
    ads.CircuitSimulator(hpeesof_dir=str(ads_root)).run_netlist(
        requested.read_text(encoding="ascii"), output_dir=str(work), working_dir=str(work),
        netlist_file=str(work / "executed.ckt"), output_file=str(work / "hpeesofsim.out"),
        rel_data_dir=str(work), dataset_name="channel_native_ads")
    data_path = work / "channel_native_ads.ds"
    arrays, inventory = {}, []
    with dataset.open_dataset_for_reading(data_path) as data:
        for index, name in enumerate(data.varblock_names):
            frame = data[name].to_dataframe()
            if frame.index.nlevels != 1:
                raise ValueError("unexpected ADS index dimensions")
            prefix = f"table{index}"
            arrays[prefix + "__axis"] = frame.index.to_numpy()
            columns = [str(column) for column in frame.columns]
            for column in columns:
                arrays[prefix + "__" + column] = frame[column].to_numpy()
            inventory.append({"name": name, "axis": frame.index.name, "columns": columns, "prefix": prefix, "points": len(frame)})
    np.savez_compressed(work / "raw.npz", **arrays)
    if requested.read_bytes().replace(b"\r\n", b"\n") != (work / "executed.ckt").read_bytes().replace(b"\r\n", b"\n"):
        raise ValueError("executed ADS netlist differs from requested netlist")
    write_json(work / "dataset.json", {"dataset_sha256": digest(data_path), "tables": inventory,
                                      "raw_sha256": digest(work / "raw.npz"),
                                      "executed_netlist_sha256": digest(work / "executed.ckt"),
                                      "solver_log_sha256": digest(work / "hpeesofsim.out")})


def checked_process(command, cwd, log, timeout):
    with Path(log).open("xb") as stream:
        with subprocess.Popen(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                              creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0) as process:
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name == "nt" and process.poll() is None:
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], check=False, capture_output=True)
                else:
                    process.kill()
                process.wait()
                raise RuntimeError("bounded process timeout; see " + str(log))
    if returncode:
        raise RuntimeError(f"process exit {returncode}; see {log}")


def gate(reference, candidate, tolerance):
    import numpy as np
    if reference.shape != candidate.shape or reference.size == 0 or not np.isfinite(reference).all() or not np.isfinite(candidate).all():
        raise ValueError("comparison shape/finiteness mismatch")
    difference = np.abs(candidate - reference)
    allowed = tolerance["absolute"] + tolerance["relative"] * np.abs(reference)
    failed = difference > allowed
    return {"passed": not bool(failed.any()), "points": int(reference.size), "failed_points": int(failed.sum()),
            "max_absolute_error": float(difference.max()), "rms_error": float(np.sqrt(np.mean(difference**2))),
            "max_error_index": int(np.argmax(difference)), "tolerance": tolerance}


def compare_run(request, candidate, ads, output, plan):
    import numpy as np
    receipt = read_json(candidate / "receipt.json")
    if receipt["backend"] != "in_process_sipi_pybert_direct" or receipt["acceptance"] is not False:
        raise ValueError("candidate is not the SIPI in-process native workflow")
    for name, identity in receipt["artifacts"].items():
        if Path(name).name != name or digest(candidate / name) != identity["sha256"] or (candidate / name).stat().st_size != identity["byte_length"]:
            raise ValueError("candidate artifact identity mismatch")
    with np.load(candidate / "arrays.npz", allow_pickle=False) as npz:
        arrays = {name: npz[name] for name in npz.files}
    inventory = read_json(ads / "dataset.json")
    if inventory["dataset_sha256"] != digest(ads / "channel_native_ads.ds"):
        raise ValueError("raw ADS dataset identity mismatch")
    if inventory["raw_sha256"] != digest(ads / "raw.npz"):
        raise ValueError("ADS exported arrays identity mismatch")
    with np.load(ads / "raw.npz", allow_pickle=False) as npz:
        raw = {name: npz[name] for name in npz.files}
    ac_tables = [item for item in inventory["tables"] if item["axis"] == "freq"]
    tran_tables = [item for item in inventory["tables"] if item["axis"] == "time"]
    if len(ac_tables) != 1 or len(tran_tables) != 1:
        raise ValueError("expected exactly one AC and one Transient table")
    ac, tran = ac_tables[0]["prefix"], tran_tables[0]["prefix"]
    f = frequencies(request)
    np.testing.assert_array_equal(raw[ac + "__axis"], f)
    np.testing.assert_array_equal(raw[ac + "__source"], np.full(len(f), 2, dtype=complex))
    time = arrays["time_s"]
    declared_time = np.arange(request["timebase"]["nbits"] * request["timebase"]["samplesPerUi"]) * request["timebase"]["sampleInterval"]
    np.testing.assert_array_equal(time, declared_time)
    native_time = raw[tran + "__axis"]
    if not np.isfinite(native_time).all() or np.any(np.diff(native_time) <= 0):
        raise ValueError("ADS native time axis is not strictly increasing")
    origin = REFERENCE["ads_clock_origin_ui"] * request["timebase"]["samplesPerUi"] * request["timebase"]["sampleInterval"]
    requested_time = origin + time
    right = np.searchsorted(native_time, requested_time).clip(0, len(native_time)-1)
    left = (right - 1).clip(0)
    indices = np.where(abs(native_time[right]-requested_time) < abs(native_time[left]-requested_time), right, left)
    time_error = abs(native_time[indices]-requested_time)
    allowed_time = np.maximum(plan["time_key_absolute_tolerance_s"], 4*np.spacing(requested_time))
    if len(np.unique(indices)) != len(time) or np.any(time_error > allowed_time):
        raise ValueError("ADS did not deliver the declared sample keys; interpolation is forbidden")
    np.testing.assert_array_equal(arrays["tx_waveform_v"], np.repeat(np.array(request["pattern"]["bits"])*2-1, request["timebase"]["samplesPerUi"]) * request["tx"]["amplitude"])
    source = raw[tran + "__source"][indices] / 2
    reference = raw[tran + "__output"][indices]
    gates = {"source_delivery": gate(arrays["tx_waveform_v"], source, plan["voltage_tolerance"])}
    for name in ["channel_output_v", "rx_input_v", "rx_output_v"]:
        gates[name] = gate(reference, arrays[name], plan["voltage_tolerance"])
    with (output / "time-pointwise.csv").open("x", newline="", encoding="ascii") as stream:
        writer = csv.writer(stream)
        writer.writerow(["index", "time_s", "ads_index", "ads_time_s", "sipi_tx_v", "ads_half_open_source_v", "sipi_channel_v", "ads_load_v", "difference_v", "allowed_v"])
        for i in range(len(time)):
            allowed = plan["voltage_tolerance"]["absolute"] + plan["voltage_tolerance"]["relative"] * abs(reference[i])
            writer.writerow([i, time[i], indices[i], native_time[indices[i]], arrays["tx_waveform_v"][i], source[i], arrays["channel_output_v"][i], reference[i], arrays["channel_output_v"][i]-reference[i], allowed])
    impulse = arrays["channel_impulse_v_per_v"]
    nfft_float = 1 / (f[1] * request["timebase"]["sampleInterval"])
    nfft = round(nfft_float)
    if not math.isclose(nfft_float, nfft, rel_tol=1e-12) or len(impulse) > nfft:
        raise ValueError("kernel grid cannot be compared without resampling/truncation")
    post_kernel = np.fft.rfft(impulse, n=nfft)[:len(f)]
    fd_reference = raw[ac + "__output"]
    physical_control = material_transfer(request, f)
    gates["ads_vs_material_equations"] = gate(physical_control, fd_reference, plan["transfer_tolerance"])
    gates["physical_vs_kernel_dtft"] = gate(fd_reference, post_kernel, plan["transfer_tolerance"])
    terminated = None
    if "legacy_channel_terminated_re" in arrays:
        np.testing.assert_array_equal(arrays["legacy_channel_frequency_hz"], f)
        terminated = arrays["legacy_channel_terminated_re"] + 1j*arrays["legacy_channel_terminated_im"]
        gates["physical_vs_legacy_terminated"] = gate(fd_reference, terminated, plan["transfer_tolerance"])
    with (output / "frequency-pointwise.csv").open("x", newline="", encoding="ascii") as stream:
        writer = csv.writer(stream)
        writer.writerow(["frequency_hz", "ads_h_re", "ads_h_im", "kernel_h_re", "kernel_h_im", "kernel_abs_error", "terminated_h_re", "terminated_h_im", "terminated_abs_error", "material_h_re", "material_h_im", "ads_material_abs_error"])
        for i, frequency in enumerate(f):
            row = [frequency, fd_reference[i].real, fd_reference[i].imag, post_kernel[i].real, post_kernel[i].imag, abs(post_kernel[i]-fd_reference[i])]
            row += [terminated[i].real, terminated[i].imag, abs(terminated[i]-fd_reference[i])] if terminated is not None else ["", "", ""]
            row += [physical_control[i].real, physical_control[i].imag, abs(fd_reference[i]-physical_control[i])]
            writer.writerow(row)
    plot_comparison(output, time, reference, arrays["channel_output_v"], f, fd_reference, post_kernel, terminated, physical_control, plan)
    report = {"passed": all(item["passed"] for item in gates.values()), "gates": gates,
              "oracle_contract_passed": gates["ads_vs_material_equations"]["passed"],
              "ads_clock_origin_s": origin, "time_relation": "ADS requested time = fixed source origin + SIPI time; never output-fitted",
              "plot_scope": "all paired time/frequency points; logarithmic error display floor 1e-18, never used in gates/CSV",
              "native_time_points": len(native_time), "maximum_time_key_error_s": float(time_error.max()),
              "receipt_sha256": digest(candidate / "receipt.json"), "dataset_sha256": digest(ads / "channel_native_ads.ds"),
              "csv_sha256": {name: digest(output / name) for name in ("time-pointwise.csv", "frequency-pointwise.csv")}, "acceptance": False}
    report["plot_sha256"] = {name: digest(output / name) for name in ("time-comparison.png", "frequency-comparison.png")}
    write_json(output / "comparison.json", report)
    return report


def plot_comparison(output, time, reference, candidate, frequency, ac, kernel, terminated, material, plan):
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt
    colors = {"ADS": "#2568b7", "SIPI": "#087d67", "Error": "#bc3156", "Material": "#6b617f"}
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.grid": True, "grid.color": "#e5ebe8"}):
        fig, axes = plt.subplots(2, 1, figsize=(12, 5.8), sharex=True, layout="constrained")
        axes[0].plot(time * 1e9, reference, color=colors["ADS"], lw=1.5, label="ADS load")
        axes[0].plot(time * 1e9, candidate, color=colors["SIPI"], lw=1, label="SIPI post-channel")
        axes[0].set_ylabel("Voltage (V)")
        axes[0].legend(loc="upper right", ncols=2)
        allowed = plan["voltage_tolerance"]["absolute"] + plan["voltage_tolerance"]["relative"] * np.abs(reference)
        axes[1].plot(time * 1e9, candidate - reference, color=colors["Error"], lw=1, label="SIPI - ADS")
        axes[1].plot(time * 1e9, allowed, color="#5f6562", lw=0.7, label="+/- tolerance")
        axes[1].plot(time * 1e9, -allowed, color="#5f6562", lw=0.7)
        axes[1].set(xlabel="Time from declared source origin (ns)", ylabel="Error (V)")
        axes[1].legend(loc="upper right", ncols=2)
        fig.savefig(output / "time-comparison.png", dpi=140)
        plt.close(fig)
        fig, axes = plt.subplots(2, 1, figsize=(12, 5.8), sharex=True, layout="constrained")
        curves = [("ADS physical", ac, colors["ADS"]), ("SIPI kernel DTFT", kernel, colors["SIPI"])]
        if terminated is not None:
            curves.append(("SIPI terminated", terminated, "#bc3156"))
        curves.append(("Material equations", material, colors["Material"]))
        for name, values, color in curves:
            axes[0].plot(frequency * 1e-9, np.abs(values), color=color, lw=1, label=name)
        axes[0].set_ylabel("Transfer magnitude (V/V)")
        axes[0].legend(loc="upper right", ncols=2)
        for name, values, color in curves[1:]:
            axes[1].semilogy(frequency * 1e-9, np.maximum(np.abs(values - ac), 1e-18), color=color, lw=1, label=name + " - ADS")
        allowed = plan["transfer_tolerance"]["absolute"] + plan["transfer_tolerance"]["relative"] * np.abs(ac)
        axes[1].semilogy(frequency * 1e-9, np.maximum(allowed, 1e-18), color="#5f6562", lw=0.7, label="Tolerance")
        axes[1].set(xlabel="Frequency (GHz)", ylabel="Complex absolute error (V/V)")
        axes[1].legend(loc="upper right", ncols=2)
        fig.savefig(output / "frequency-comparison.png", dpi=140)
        plt.close(fig)


def render_summary(output, result):
    rows, overview, figures = [], [], []
    for case in result["cases"]:
        name = html.escape(case["name"])
        runs = case.get("runs", [])
        if runs:
            gates = runs[0]["gates"]
            overview.append(f'<tr><td><a href="#{name}">{name}</a></td><td>{gates["channel_output_v"]["max_absolute_error"]:.6e}</td><td>{gates["physical_vs_kernel_dtft"]["max_absolute_error"]:.6e}</td><td>{"PASS" if runs[0]["oracle_contract_passed"] else "FAIL"}</td><td>{"YES" if case.get("repeatable") else "NO"}</td></tr>')
            base = f'{name}/repeat-1'
            figures.append(f'<section id="{name}"><h2>{name}</h2><nav><a href="{base}/time-pointwise.csv">Time CSV</a><a href="{base}/frequency-pointwise.csv">Frequency CSV</a><a href="{base}/candidate/report.html">SIPI run</a><a href="{base}/ads/hpeesofsim.out">ADS log</a><a href="{base}/comparison.json">Comparison</a></nav><div class="scroll"><img width="1680" height="812" src="{base}/time-comparison.png" alt="{name}: all time samples and voltage error"></div><div class="scroll"><img width="1680" height="812" src="{base}/frequency-comparison.png" alt="{name}: transfer magnitude and complex error"></div></section>')
        else:
            overview.append(f'<tr><td>{name}</td><td colspan="4">No complete comparison</td></tr>')
        for index, run in enumerate(case.get("runs", []), 1):
            for name, value in run.get("gates", {}).items():
                rows.append(f'<tr><td>{html.escape(case["name"])}</td><td>{index}</td><td>{html.escape(name)}</td><td>{"PASS" if value["passed"] else "FAIL"}</td><td>{value["points"]}</td><td>{value["failed_points"]}</td><td>{value["max_absolute_error"]:.6e}</td><td><a href="{case["name"]}/repeat-{index}/comparison.json">Data</a></td></tr>')
        if case.get("error"):
            rows.append(f'<tr><td>{html.escape(case["name"])}</td><td colspan="7">{html.escape(case["error"])}</td></tr>')
    page = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SIPI / ADS Channel Bench</title><style>body{font:14px "Segoe UI",sans-serif;margin:24px;color:#202723;letter-spacing:0}main{max-width:1250px;margin:auto}h1{font-size:24px}h2{font-size:18px}p{line-height:1.6}.scroll{overflow:auto;max-width:100%}table{border-collapse:collapse;width:100%;white-space:nowrap}td,th{text-align:left;padding:9px;border-bottom:1px solid #d8dfdc}th{background:#edf5f1}a{color:#19628a}code{overflow-wrap:anywhere}.status{color:#a52d51}nav{display:flex;gap:12px 24px;flex-wrap:wrap}section{border-top:1px solid #d8dfdc;margin-top:24px;padding-top:8px}img{display:block;width:100%;min-width:720px;height:auto;aspect-ratio:1680/812;margin:12px 0}summary{cursor:pointer;padding:14px 0;font-weight:600}@media(max-width:600px){body{margin:16px}h1{font-size:22px}}</style><main><h1>SIPI / ADS Channel Bench</h1>'
    page += f'<p class="status">{html.escape(result["status"])} / acceptance: false / {len(result["cases"])} cases</p><p>In-process SIPI vs fresh ADS. Physical-semantics diagnostic. All SIPI samples retained; fixed four-UI ADS source origin, no output-fitted alignment, gain fitting or interpolation. ADS material-control failures require reference investigation.</p><nav><a href="plan.json">Frozen plan</a><a href="result.json">Result</a><a href="bindings.json">Execution bindings</a></nav><h2>First-Run Errors</h2><div class="scroll"><table><thead><tr><th>Case</th><th>TD max (V)</th><th>Kernel FD max (V/V)</th><th>ADS material control</th><th>Two identical runs</th></tr></thead><tbody>'
    page += "".join(overview) + '</tbody></table></div><details><summary>All Runs / All Pointwise Gates</summary><div class="scroll"><table><thead><tr><th>Case</th><th>Run</th><th>Gate</th><th>Status</th><th>Points</th><th>Failed</th><th>Max abs. error</th><th>Evidence</th></tr></thead><tbody>'
    page += "".join(rows) + "</tbody></table></div></details>" + "".join(figures) + "</main></html>"
    (output / "report.html").write_text(page, encoding="utf-8", newline="\n")


def run(plan_file, output, sipi, ads_root, timeout, selected):
    import numpy as np
    plan = read_json(plan_file)
    validate_plan(plan)
    if timeout <= 0 or timeout > 3600:
        raise ValueError("timeout must be 1..3600 seconds per process")
    names = {case["name"] for case in plan["cases"]}
    if len(set(selected)) != len(selected) or set(selected) - names:
        raise ValueError("unknown or repeated selected case")
    sipi, ads_root = sipi.resolve(strict=True), ads_root.resolve(strict=True)
    python = ads_root / "tools/python/python.exe"
    runtime_files = {"sipi": sipi, "script": Path(__file__), "hpeesofsim": ads_root / "bin/hpeesofsim.exe", "ads_python": python}
    identities = {name + "_sha256": digest(path) for name, path in runtime_files.items()}
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "plan.json", plan)
    with (output / "runner-source.py").open("xb") as snapshot:
        snapshot.write(Path(__file__).read_bytes())
    bindings = {**identities, "plan_sha256": digest(output / "plan.json"),
                "ads_root": str(ads_root), "sipi": str(sipi), "selected_cases": selected}
    write_json(output / "bindings.json", bindings)
    result = {"schema": "sipi.channel.ads-physical-bench-result.v1", "status": "running", "cases": [], "acceptance": False,
              "scope": plan["scope"], "all_plan_cases_selected": not selected or set(selected) == names,
              "planned_cases": [case["name"] for case in plan["cases"]]}
    try:
        for case in plan["cases"]:
            if selected and case["name"] not in selected:
                continue
            record = {"name": case["name"], "runs": [], "passed": False}
            result["cases"].append(record)
            try:
                for repeat in range(1, REPEATS + 1):
                    work = output / case["name"] / f"repeat-{repeat}"
                    work.mkdir(parents=True)
                    request_path = work / "request.json"
                    write_json(request_path, case["request"])
                    ads = work / "ads"
                    ads.mkdir()
                    text, material = netlist(case["request"])
                    (ads / "requested.ckt").write_text(text, encoding="ascii", newline="\n")
                    write_json(ads / "material.json", {"columns": ["frequency_hz", "r_ohm_per_m", "l_h_per_m", "g_s_per_m", "c_f_per_m"], "rows": material})
                    # Both requests are fixed before either backend executes.
                    write_json(work / "input-bindings.json", {"request_sha256": digest(request_path), "netlist_sha256": digest(ads / "requested.ckt"), "material_sha256": digest(ads / "material.json")})
                    checked_process([str(sipi), "channel", "simulate", str(request_path.resolve()), "--output-dir", str((work / "candidate").resolve())], work, work / "candidate.log", timeout)
                    checked_process([str(python), "-X", "utf8", str(Path(__file__).resolve()), "worker", "--work", str(ads.resolve()), "--ads-root", str(ads_root)], work, work / "ads-worker.log", timeout)
                    receipt = read_json(work / "candidate/receipt.json")
                    if receipt["executable"]["sha256"] != bindings["sipi_sha256"]:
                        raise ValueError("candidate executable changed")
                    inputs = read_json(work / "input-bindings.json")
                    for key, path in [("request", request_path), ("netlist", ads / "requested.ckt"), ("material", ads / "material.json")]:
                        if digest(path) != inputs[key + "_sha256"]:
                            raise ValueError("input identity drift during benchmark")
                    if (work / "candidate/request.json").read_bytes() != request_path.read_bytes():
                        raise ValueError("SIPI consumed a different request")
                    record["runs"].append(compare_run(case["request"], work / "candidate", ads, work, plan))
                first, second = output / case["name"] / "repeat-1", output / case["name"] / "repeat-2"
                for backend, file in [("candidate", "arrays.npz"), ("ads", "raw.npz")]:
                    with np.load(first / backend / file, allow_pickle=False) as a, np.load(second / backend / file, allow_pickle=False) as b:
                        if set(a.files) != set(b.files):
                            raise ValueError("repeated array inventory differs")
                        for name in a.files:
                            np.testing.assert_array_equal(a[name], b[name])
                record["repeatable"] = True
                record["passed"] = all(item["passed"] for item in record["runs"])
            except Exception as error:
                record["error"] = f"{type(error).__name__}: {error}"
            print(case["name"], "PASS" if record["passed"] else "FAIL", record.get("error", ""), flush=True)
        if not result["cases"]:
            raise ValueError("selected cases not found")
        for name, path in runtime_files.items():
            if digest(path) != bindings[name + "_sha256"]:
                raise ValueError("code identity drift during benchmark: " + name)
        if digest(output / "plan.json") != bindings["plan_sha256"]:
            raise ValueError("plan identity drift during benchmark")
        result["status"] = "passed" if all(case["passed"] for case in result["cases"]) else "failed"
    except Exception as error:
        result["status"] = "failed"
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        write_json(output / "result.json", result)
        render_summary(output, result)
    return 0 if result["status"] == "passed" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("plan", type=Path)
    execute = commands.add_parser("run")
    execute.add_argument("plan", type=Path)
    execute.add_argument("--output-dir", type=Path, required=True)
    execute.add_argument("--sipi", type=Path, required=True)
    execute.add_argument("--ads-root", type=Path, required=True)
    execute.add_argument("--timeout", type=int, default=180)
    execute.add_argument("--case", action="append", default=[])
    child = commands.add_parser("worker")
    child.add_argument("--work", type=Path, required=True)
    child.add_argument("--ads-root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "init":
        write_json(args.plan, initial_plan())
        return 0
    if args.command == "worker":
        worker(args.work, args.ads_root)
        return 0
    return run(args.plan, args.output_dir, args.sipi, args.ads_root, args.timeout, args.case)


if __name__ == "__main__":
    raise SystemExit(main())
