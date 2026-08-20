# -*- coding: utf-8 -*-
"""P5-06f fixed-tap COM chain core cross-check (product vs independent reference).

The product fixed-tap chain (cursor -> residual PDF with DFE cancellation ->
r4.80 noise-PDF build -> combined noise PDF -> COM/VEC/VEO metrics) is driven
by the p5_06f_com_chain_runner binary on synthetic bipolar pulses. An
independent Python reference recomputes every stage from the documented
algorithms and the exact input bytes. Fail closed on any per-checkpoint
mismatch (relative 1e-12).
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml
from scipy.special import erfcinv

ROOT = Path(__file__).resolve().parents[1]
CARGO = Path.home() / ".cargo" / "bin" / "cargo.exe"
EVIDENCE = ROOT / "docs" / "baselines" / "p5-06f-com-chain-crosscheck-evidence.v1.yaml"
EVIDENCE_SCHEMA = "sipi.p5-06f.com-chain-crosscheck-evidence.v1"
EPS = 2.220446049250313e-16  # f64::EPSILON


def matlab_round(value: float) -> int:
    if value >= 0.0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


def sign(value: float) -> float:
    return 1.0 if value > 0.0 else (-1.0 if value < 0.0 else 0.0)


def normalize(minimum: int, probability: list[float]) -> tuple[int, list[float]]:
    total = sum(probability)
    return minimum, [p / total for p in probability]


def normal_pdf(sigma: float, nsigma: float, bin_size: float) -> tuple[int, list[float]]:
    minimum = matlab_round(-2.0 * nsigma * sigma / bin_size)
    count = -minimum - minimum + 1
    denominator = 2.0 * sigma * sigma + EPS
    probability = [
        math.exp(-((minimum + i) * bin_size) ** 2 / denominator) for i in range(count)
    ]
    return normalize(minimum, probability)


def from_values(bin_size: float, values: list[float], probabilities: list[float]) -> tuple[int, list[float]]:
    if all(v == 0.0 for v in values):
        return (0, [1.0])
    pairs = sorted(zip(values, probabilities), key=lambda pair: pair[0])
    bins = [matlab_round(v / bin_size) for v, _ in pairs]
    minimum = bins[0]
    maximum = bins[-1]
    mass = [0.0] * (maximum - minimum + 1)
    for (_, probability), bin_index in zip(pairs, bins):
        mass[bin_index - minimum] += probability
    first = next(i for i, m in enumerate(mass) if m != 0.0)
    last = len(mass) - 1 - next(i for i, m in enumerate(reversed(mass)) if m != 0.0)
    return normalize(minimum + first, mass[first : last + 1])


def convolve(left: tuple[int, list[float]], right: tuple[int, list[float]]) -> tuple[int, list[float]]:
    left_min, left_p = left
    right_min, right_p = right
    if left_p == [1.0] and left_min == 0:
        return (right_min, list(right_p))
    if right_p == [1.0] and right_min == 0:
        return (left_min, list(left_p))
    size = len(left_p) + len(right_p) - 1
    result = [0.0] * size
    for i, x in enumerate(left_p):
        for j, y in enumerate(right_p):
            result[i + j] += x * y
    return normalize(matlab_round(left_min + right_min), result)


def symbol_values(levels: int) -> list[float]:
    return [2.0 * i / (levels - 1) - 1.0 for i in range(levels)]


def sampled_signal_pdf(samples: list[float], levels: int, bin_size: float) -> tuple[int, list[float]]:
    values = list(samples)
    maximum = max(values)
    if maximum > bin_size:
        values = [v for v in values if abs(v) > bin_size]
    values = [0.0 if abs(v) < bin_size else v for v in values]
    values.sort(key=lambda v: abs(v), reverse=True)
    symbols = symbol_values(levels)
    symbol_probability = [1.0 / levels] * levels
    result = (0, [1.0])
    for value in values:
        component_values = [abs(value) * s for s in symbols]
        component = from_values(bin_size, component_values, symbol_probability)
        if component == (0, [1.0]):
            continue
        result = convolve(result, component)
    return result


def cursor_mm(pulse: list[float], samples_per_ui: int, dfe_first_max: float,
              peak_start: int, peak_stop: int | None) -> tuple[int | None, int]:
    stop = peak_stop if peak_stop is not None else len(pulse)
    peak_index = peak_start + max(
        range(peak_start, stop), key=lambda i: pulse[i]
    )
    maximum = pulse[peak_index]
    search_start = max(peak_index - 4 * samples_per_ui, 0)
    window = pulse[search_start : peak_index + 1]
    rising: list[int] = []
    for index in range(1, len(window)):
        before = sign(window[index - 1] - 0.01 * maximum)
        after = sign(window[index] - 0.01 * maximum)
        if after - before >= 1.0:
            rising.append(search_start + index - 1)
    if not rising:
        return None, peak_index
    zero_crossing = rising[-1]
    sample_points = list(range(zero_crossing, zero_crossing + 2 * samples_per_ui + 1))
    metric = [
        abs(
            pulse[point - samples_per_ui]
            - max(pulse[point + samples_per_ui] - dfe_first_max * pulse[point], 0.0)
        )
        for point in sample_points
    ]
    selected = zero_crossing + metric.index(min(metric))
    return selected, peak_index


def residual_channel_pdf(pulse: list[float], cursor: int, samples_per_ui: int, levels: int,
                         bin_size: float, dfe_tap_count: int, dfe_max: list[float],
                         dfe_min: list[float], dfe_step: float, floating_dfe: bool,
                         dfe_max_count: int | None) -> tuple[tuple[int, list[float]], list[float], int]:
    residual = list(pulse)
    count = dfe_max_count if floating_dfe else dfe_tap_count
    assert count is not None and count >= 0
    count = int(count)
    assert cursor + count * samples_per_ui < len(residual)
    if count > 0:
        assert len(dfe_max) >= count and len(dfe_min) >= count
        assert all(lo <= hi for lo, hi in zip(dfe_min[:count], dfe_max[:count]))
    cursor_value = residual[cursor]
    cancellation = [residual[cursor + k * samples_per_ui] for k in range(count + 1)]
    if dfe_step != 0.0:
        for i in range(len(cancellation)):
            value = cancellation[i]
            scaled = value / (cursor_value * dfe_step)
            sgn = 1.0 if value > 0.0 else (-1.0 if value < 0.0 else 0.0)
            cancellation[i] = math.floor(abs(scaled)) * cursor_value * dfe_step * sgn
    upper = [cursor_value] + list(dfe_max[:count])
    lower = [cursor_value] + list(dfe_min[:count])
    for i in range(len(cancellation)):
        cancellation[i] = min(upper[i], max(lower[i], cancellation[i]))
    start = cursor - samples_per_ui // 2
    stop = start + len(cancellation) * samples_per_ui
    assert start >= 0 and stop <= len(residual)
    for offset, value in enumerate(cancellation):
        for sample in range(samples_per_ui):
            residual[start + offset * samples_per_ui + sample] -= value
    nui = matlab_round(len(residual) / samples_per_ui)
    assert nui >= 3
    phase = (cursor + 1) % samples_per_ui
    phase = samples_per_ui - 1 if phase == 0 else phase - 1
    start = samples_per_ui + phase
    stop = start + (nui - 2) * samples_per_ui
    values = [residual[i] for i in range(start, stop, samples_per_ui)]
    pdf = sampled_signal_pdf(values, levels, bin_size)
    return pdf, residual, phase


def build_noise_pdf(sci: tuple[int, list[float]], bin_size: float, levels: int,
                    available_signal: float, r_lm: float, tx_snr: float, sigma_x: float,
                    sigma_rj_s: float, h_j: list[float], sigma_n: float, amplitude_dd: float,
                    spec_ber: float, noise_crest: float, sigma_ne: float,
                    bbn_q: float | None, sigma_tx_o: float | None,
                    sigma_rj_o: float | None) -> dict[str, Any]:
    sigma_tx = sigma_tx_o if sigma_tx_o is not None else (
        (levels - 1) * available_signal / r_lm * 10.0 ** (-tx_snr / 20.0)
    )
    norm_h_j = math.sqrt(sum(v * v for v in h_j))
    sigma_rj = sigma_rj_o if sigma_rj_o is not None else sigma_rj_s * sigma_x * norm_h_j
    sigma_gaussian = math.sqrt(sigma_rj * sigma_rj + sigma_n * sigma_n + sigma_tx * sigma_tx)
    ber_q = noise_crest if noise_crest != 0.0 else math.sqrt(2.0) * erfcinv(2.0 * spec_ber)
    ne_q = bbn_q if bbn_q is not None else ber_q
    gaussian_first = normal_pdf(sigma_gaussian, ber_q, bin_size)
    gaussian_second = normal_pdf(sigma_ne, ne_q, bin_size)
    gaussian = convolve(gaussian_first, gaussian_second)
    dual_dirac = sampled_signal_pdf([amplitude_dd * v for v in h_j], levels, bin_size)
    return {
        "sigma_tx": float(sigma_tx), "sigma_rj": float(sigma_rj),
        "sigma_gaussian": float(sigma_gaussian), "ber_q": float(ber_q),
        "gaussian": gaussian, "dual_dirac": dual_dirac,
    }


def combine(sci: tuple[int, list[float]], gaussian: tuple[int, list[float]],
            dual: tuple[int, list[float]], spec_ber: float) -> dict[str, Any]:
    cci = (0, [1.0])
    isi_and_crosstalk = convolve(sci, cci)
    gaussian_and_jitter = convolve(gaussian, dual)
    combined = convolve(isi_and_crosstalk, gaussian_and_jitter)
    cdf: list[float] = []
    running = 0.0
    for value in combined[1]:
        running += value
        cdf.append(running)
    # first_quantile on isi_and_crosstalk: first support point whose CDF >= p
    q_cdf: list[float] = []
    running = 0.0
    for value in isi_and_crosstalk[1]:
        running += value
        q_cdf.append(running)
    index = next((i for i, v in enumerate(q_cdf) if v >= spec_ber), len(q_cdf) - 1)
    # bin size is uniform across the chain (validated by the Rust stage)
    bin_size = abs(combined[0]) + 1.0  # placeholder, replaced below
    bin_size = 0.0
    return {"combined": combined, "cdf": cdf, "peak": 0.0, "_bin": bin_size}


def metrics(available: float, pdf_x: list[float], pdf_cdf: list[float], spec_ber: float,
            pass_threshold: float) -> dict[str, float]:
    interference_index = next(i for i, v in enumerate(pdf_cdf) if v > spec_ber)
    interference = abs(pdf_x[interference_index])
    threshold = -available / 10.0 ** (pass_threshold / 20.0)
    threshold_index = next(i for i, v in enumerate(pdf_x) if v > threshold)
    vec_argument = max((available - interference) / available, EPS)
    com = 20.0 * math.log10(available / interference)
    vec = -20.0 * math.log10(vec_argument)
    veo = 2000.0 * (available - interference)
    return {"com": float(com), "vec": float(vec), "veo": float(veo)}


def near(left: float, right: float, rel: float = 1e-12) -> bool:
    return abs(left - right) <= rel * max(abs(left), abs(right), 1e-300)


def pdf_near(a: tuple[int, list[float]], b: tuple[int, list[float]]) -> bool:
    if a[0] != b[0] or len(a[1]) != len(b[1]):
        return False
    return all(near(x, y) for x, y in zip(a[1], b[1]))


def reference_chain(pulse: list[float], c: dict[str, Any]) -> dict[str, Any]:
    cursor, peak_index = cursor_mm(pulse, c["samples_per_ui"], c["dfe_first_max"],
                                   c["peak_start"], c.get("peak_stop"))
    assert cursor is not None, "reference cursor missing"
    sci, residual_pulse, phase = residual_channel_pdf(
        pulse, cursor, c["samples_per_ui"], c["levels"], c["bin_size"],
        c["dfe_tap_count"], c["dfe_max"], c["dfe_min"], c["dfe_step"],
        c["floating_dfe"], c.get("dfe_max_count"),
    )
    noise = build_noise_pdf(
        sci, c["bin_size"], c["levels"], c["available_signal_v"], c["r_lm_ohm"],
        c["tx_snr_db"], c["sigma_x"], c["sigma_rj_s"], c["jitter_response"],
        c["sigma_n_v"], c["amplitude_dd_v"], c["spec_ber"], c["noise_crest_factor"],
        c["sigma_ne_v"], c.get("bbn_q_factor"), c.get("sigma_tx_override_v"),
        c.get("sigma_rj_override_v"),
    )
    combined = combine(sci, noise["gaussian"], noise["dual_dirac"], c["spec_ber"])
    # recompute peak interference with the true bin size (sci bin size == c bin_size)
    q_cdf: list[float] = []
    running = 0.0
    isi_xt = convolve(sci, (0, [1.0]))
    for value in isi_xt[1]:
        running += value
        q_cdf.append(running)
    q_index = next((i for i, v in enumerate(q_cdf) if v >= c["spec_ber"]), len(q_cdf) - 1)
    combined["peak"] = abs((isi_xt[0] + q_index) * c["bin_size"])
    bin_size = c["bin_size"]
    combined_pdf = combined["combined"]
    support = [(combined_pdf[0] + i) * bin_size for i in range(len(combined_pdf[1]))]
    metric = metrics(c["available_signal_v"], support, combined["cdf"], c["spec_ber"],
                     c["pass_threshold_db"])
    return {
        "cursor_index": cursor,
        "peak_index": peak_index,
        "selected_phase": phase,
        "residual_pulse": residual_pulse,
        "sci": sci,
        "noise": noise,
        "combined_pdf": combined_pdf,
        "combined_cdf": combined["cdf"],
        "peak_interference": combined["peak"],
        "metrics": metric,
    }


def build_case(pulse: list[float], spu: int, dfe_tap_count: int, dfe_max: list[float],
               dfe_min: list[float]) -> dict[str, Any]:
    return {
        "pulse": pulse,
        "controls": {
            "samples_per_ui": spu, "levels": 4, "bin_size": 0.01,
            "dfe_first_max": 0.0, "cdr": "MM", "peak_start": 16, "peak_stop": 44,
            "dfe_tap_count": dfe_tap_count, "dfe_max": dfe_max, "dfe_min": dfe_min,
            "dfe_step": 0.0, "floating_dfe": False, "dfe_max_count": None,
            "available_signal_v": 0.5, "r_lm_ohm": 50.0, "tx_snr_db": 30.0,
            "sigma_x": 0.03, "sigma_rj_s": 1e-4, "jitter_response": [0.3, 0.5, 0.2],
            "sigma_n_v": 0.01, "amplitude_dd_v": 0.4, "spec_ber": 1e-4,
            "noise_crest_factor": 0.0, "sigma_ne_v": 0.0, "bbn_q_factor": None,
            "sigma_tx_override_v": None, "sigma_rj_override_v": None,
            "pass_threshold_db": 3.0, "t_o_s": 0.0, "eye_opening_v": None,
        },
    }


def pulse_bipolar(zero: int, length: int = 64) -> list[float]:
    return [
        0.5 * math.exp(-((i - zero) ** 2) / 80.0) * (i - zero) * 0.4
        + 0.002 * math.sin(i * 0.9)
        for i in range(length)
    ]


def main() -> int:
    built = subprocess.run(
        [str(CARGO), "build", "-p", "sipi-com", "--test", "p5_06f_com_chain_runner"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT,
    )
    if built.returncode != 0:
        raise SystemExit("runner build failed: " + built.stdout + built.stderr)
    runner = sorted((ROOT / "target" / "debug" / "deps").glob("p5_06f_com_chain_runner-*.exe"))[-1]

    cases = [
        build_case(pulse_bipolar(28), 8, 0, [], []),
        build_case(pulse_bipolar(30), 8, 1, [0.25], [-0.25]),
    ]
    ok_all = True
    entries: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="p5-06f-") as tmp:
        work = Path(tmp)
        for index, case in enumerate(cases, start=1):
            input_path = work / f"input{index}.json"
            input_path.write_text(json.dumps(case, separators=(",", ":")), encoding="utf-8")
            report_path = work / f"report{index}.json"
            run = subprocess.run(
                [str(runner), "--input", str(input_path), "--report", str(report_path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if run.returncode != 0:
                raise SystemExit("runner failed: " + run.stdout + run.stderr)
            product = json.loads(report_path.read_text(encoding="utf-8"))
            ref = reference_chain(case["pulse"], case["controls"])
            cursor = product["cursor"]["cursor_index"]
            checks: list[tuple[str, bool, str]] = []
            def check(name: str, ok: bool, detail: str = "") -> None:
                checks.append((name, ok, detail))
            check("cursor_index", cursor == ref["cursor_index"],
                  f"product={cursor} ref={ref['cursor_index']}")
            check("selected_phase", product["residual"]["selected_phase"] == ref["selected_phase"],
                  f"product={product['residual']['selected_phase']} ref={ref['selected_phase']}")
            rpdf = (product["residual"]["pdf"]["min_bin"], product["residual"]["pdf"]["probability"])
            check("residual_pdf", pdf_near(rpdf, ref["sci"]))
            check("residual_pulse", all(near(a, b) for a, b in zip(product["residual"]["residual_pulse"], ref["residual_pulse"])))
            check("sigma_tx", near(product["noise"]["sigma_tx_v"], ref["noise"]["sigma_tx"]))
            check("sigma_rj", near(product["noise"]["sigma_rj_v"], ref["noise"]["sigma_rj"]))
            check("sigma_gaussian", near(product["noise"]["sigma_gaussian_v"], ref["noise"]["sigma_gaussian"]))
            check("ber_q", near(product["noise"]["ber_q"], ref["noise"]["ber_q"]))
            gpdf = (product["noise"]["gaussian_pdf"]["min_bin"], product["noise"]["gaussian_pdf"]["probability"])
            check("gaussian_pdf", pdf_near(gpdf, ref["noise"]["gaussian"]))
            jpdf = (product["noise"]["jitter_pdf"]["min_bin"], product["noise"]["jitter_pdf"]["probability"])
            check("jitter_pdf", pdf_near(jpdf, ref["noise"]["dual_dirac"]))
            cpdf = (product["combined"]["combined_pdf"]["min_bin"], product["combined"]["combined_pdf"]["probability"])
            check("combined_pdf", pdf_near(cpdf, ref["combined_pdf"]))
            check("combined_cdf", len(product["combined"]["cdf"]) == len(ref["combined_cdf"])
                  and all(near(a, b) for a, b in zip(product["combined"]["cdf"], ref["combined_cdf"])))
            check("peak_interference", near(product["combined"]["peak_interference_v"], ref["peak_interference"]))
            check("com_db", near(product["metrics"]["com_db"], ref["metrics"]["com"]))
            check("vec_db", near(product["metrics"]["vec_db"], ref["metrics"]["vec"]))
            check("veo_mv", near(product["metrics"]["veo_mv"], ref["metrics"]["veo"]))
            matched = all(ok for _, ok, _ in checks)
            ok_all = ok_all and matched
            entries.append({
                "label": f"case_{index}",
                "matched": matched,
                "checkpoints": [{"name": name, "ok": ok, "detail": detail} for name, ok, detail in checks],
            })

    evidence = {
        "schema": EVIDENCE_SCHEMA,
        "status": "matched_hash_bound" if ok_all else "mis_match",
        "policy": "sipi.p5-06f.com-chain-v1.fixed-tap-cursor-residual-noise-metrics",
        "matched_count": sum(1 for e in entries if e["matched"]),
        "case_count": len(entries),
        "entries": entries,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    # YAML cannot represent non-finite floats; fail closed if any appear
    import math as _math
    bad = []

    def _scan(value, path=""):
        if isinstance(value, float) and not _math.isfinite(value):
            bad.append(path + "=" + repr(value))
        elif isinstance(value, dict):
            for key, item in value.items():
                _scan(item, path + "." + str(key))
        elif isinstance(value, list):
            for i, item in enumerate(value):
                _scan(item, path + "[" + str(i) + "]")

    _scan(evidence)
    if bad:
        raise SystemExit("non_finite_in_evidence: " + bad[0])
    EVIDENCE.write_text(yaml.safe_dump(evidence, sort_keys=False), encoding="utf-8")
    print(json.dumps({"schema": EVIDENCE_SCHEMA, "status": evidence["status"],
                      "matched_count": evidence["matched_count"], "case_count": evidence["case_count"]}, indent=2))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
