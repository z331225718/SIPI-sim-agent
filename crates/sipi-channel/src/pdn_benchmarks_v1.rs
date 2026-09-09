#![forbid(unsafe_code)]

//! Time-Domain Reflectometry (TDR) and Power Distribution Network (PDN) benchmarks.
//!
//! This module models:
//! 1. TDR impedance profile reconstruction Z(t) from step response reflection coefficients.
//! 2. Multi-stage PDN impedance profiles Z(f) including VRM, bulk, mid, and high-frequency
//!    decoupling capacitors with realistic parasitics (ESR and ESL loop inductance),
//!    capturing anti-resonance peaks against Z_target.
//! 3. Core rail dynamic current step transient simulations to evaluate voltage droop
//!    and damping margins.

use rustfft::num_complex::Complex;
use sipi_types::Hertz;

/// Result of a Time-Domain Reflectometry (TDR) impedance profile reconstruction.
#[derive(Debug, Clone, PartialEq)]
pub struct TdrProfileResultV1 {
    pub time_ps: Vec<f64>,
    pub reflection_coefficient: Vec<f64>,
    pub impedance_ohms: Vec<f64>,
    pub z_min_ohms: f64,
    pub z_max_ohms: f64,
    pub z_mean_ohms: f64,
}

/// Parameters for a single decoupling capacitor with parasitic series resistance and inductance.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct DecouplingCapacitorSpecV1 {
    pub name: &'static str,
    pub capacitance_f: f64,
    pub esr_ohms: f64,
    pub esl_henries: f64,
    pub count: usize,
}

impl DecouplingCapacitorSpecV1 {
    pub fn impedance_at(&self, frequency_hz: f64) -> Complex<f64> {
        let count_f = self.count.max(1) as f64;
        let esr = self.esr_ohms / count_f;
        let esl = self.esl_henries / count_f;
        let c = self.capacitance_f * count_f;

        let omega = 2.0 * std::f64::consts::PI * frequency_hz;
        let cap_reactance = if omega > 0.0 && c > 0.0 {
            -1.0 / (omega * c)
        } else {
            -1.0e9
        };
        let ind_reactance = omega * esl;

        Complex::new(esr, ind_reactance + cap_reactance)
    }
}

/// Specification for a multi-stage Power Distribution Network (PDN).
#[derive(Debug, Clone, PartialEq)]
pub struct PdnNetworkSpecV1 {
    pub nominal_voltage_v: f64,
    pub ripple_tolerance_fraction: f64,
    pub transient_step_current_a: f64,
    pub vrm_resistance_ohms: f64,
    pub vrm_inductance_henries: f64,
    pub capacitors: Vec<DecouplingCapacitorSpecV1>,
}

impl PdnNetworkSpecV1 {
    /// Target impedance Z_target = (V_nom * ripple) / delta_I
    pub fn target_impedance_ohms(&self) -> f64 {
        let allowed_ripple_v = self.nominal_voltage_v * self.ripple_tolerance_fraction;
        allowed_ripple_v / self.transient_step_current_a.max(1e-6)
    }

    /// Standard high-performance core rail PDN benchmark:
    /// Vcore = 0.85 V, 3% ripple tolerance (+/- 25.5 mV), 6.0 A step -> Z_target = 4.25 mOhm.
    /// - VRM: 1 mOhm, 100 nH
    /// - Bulk decoupling: 2x 47 uF (ESR = 15 mOhm, ESL = 1.2 nH)
    /// - Mid-freq decoupling: 10x 1.0 uF (ESR = 10 mOhm, ESL = 0.4 nH)
    /// - High-freq decoupling: 20x 0.1 uF (ESR = 8 mOhm, ESL = 0.15 nH)
    pub fn standard_core_rail() -> Self {
        Self {
            nominal_voltage_v: 0.85,
            ripple_tolerance_fraction: 0.03, // +/- 3%
            transient_step_current_a: 6.0,   // 6 A step
            vrm_resistance_ohms: 0.001,      // 1 mOhm
            vrm_inductance_henries: 100.0e-9, // 100 nH
            capacitors: vec![
                DecouplingCapacitorSpecV1 {
                    name: "bulk_47uf",
                    capacitance_f: 47.0e-6,
                    esr_ohms: 0.015,
                    esl_henries: 1.2e-9,
                    count: 2,
                },
                DecouplingCapacitorSpecV1 {
                    name: "mid_1uf",
                    capacitance_f: 1.0e-6,
                    esr_ohms: 0.010,
                    esl_henries: 0.4e-9,
                    count: 10,
                },
                DecouplingCapacitorSpecV1 {
                    name: "high_0p1uf",
                    capacitance_f: 0.1e-6,
                    esr_ohms: 0.008,
                    esl_henries: 0.15e-9,
                    count: 20,
                },
            ],
        }
    }
}

/// Evaluated frequency-domain PDN impedance profile.
#[derive(Debug, Clone, PartialEq)]
pub struct PdnImpedanceProfileV1 {
    pub frequencies_hz: Vec<f64>,
    pub impedance_magnitude_ohms: Vec<f64>,
    pub target_impedance_ohms: f64,
    pub max_impedance_ohms: f64,
    pub anti_resonance_peaks: Vec<AntiResonancePeakV1>,
    pub violates_target: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct AntiResonancePeakV1 {
    pub frequency_hz: f64,
    pub peak_impedance_ohms: f64,
}

/// Results of a core rail current step transient simulation.
#[derive(Debug, Clone, PartialEq)]
pub struct PdnTransientResultV1 {
    pub time_ns: Vec<f64>,
    pub rail_voltage_v: Vec<f64>,
    pub current_a: Vec<f64>,
    pub max_voltage_droop_v: f64,
    pub min_rail_voltage_v: f64,
    pub allowed_ripple_v: f64,
    pub passed: bool,
}

/// Reconstruct TDR characteristic impedance profile Z(t) from step reflection coefficients.
pub fn reconstruct_tdr_impedance_profile(
    reflection_waveform: &[f64],
    sample_interval_s: f64,
    ref_z_ohms: f64,
) -> TdrProfileResultV1 {
    let n = reflection_waveform.len();
    let mut time_ps = Vec::with_capacity(n);
    let mut gamma = Vec::with_capacity(n);
    let mut z_profile = Vec::with_capacity(n);

    let mut z_min = f64::INFINITY;
    let mut z_max = f64::NEG_INFINITY;
    let mut z_sum = 0.0;

    for (i, &refl) in reflection_waveform.iter().enumerate() {
        let t_ps = i as f64 * sample_interval_s * 1.0e12;
        // Bound gamma strictly within [-0.99, +0.99] to prevent infinite division
        let g = refl.clamp(-0.99, 0.99);
        let z = ref_z_ohms * (1.0 + g) / (1.0 - g);

        if z < z_min {
            z_min = z;
        }
        if z > z_max {
            z_max = z;
        }
        z_sum += z;

        time_ps.push(t_ps);
        gamma.push(g);
        z_profile.push(z);
    }

    let z_mean = if n > 0 { z_sum / n as f64 } else { ref_z_ohms };

    TdrProfileResultV1 {
        time_ps,
        reflection_coefficient: gamma,
        impedance_ohms: z_profile,
        z_min_ohms: z_min,
        z_max_ohms: z_max,
        z_mean_ohms: z_mean,
    }
}

/// Calculate the parallel PDN impedance profile Z(f) across the frequency grid.
pub fn calculate_pdn_impedance_profile(
    spec: &PdnNetworkSpecV1,
    frequencies: &[Hertz],
) -> PdnImpedanceProfileV1 {
    let target_z = spec.target_impedance_ohms();
    let n = frequencies.len();

    let mut freqs_hz = Vec::with_capacity(n);
    let mut z_mag = Vec::with_capacity(n);
    let mut max_z = 0.0_f64;

    for &freq in frequencies {
        let f = freq.get();
        let omega = 2.0 * std::f64::consts::PI * f;

        // VRM admittance: Y_vrm = 1 / (R_vrm + j*omega*L_vrm)
        let z_vrm = Complex::new(spec.vrm_resistance_ohms, omega * spec.vrm_inductance_henries);
        let mut y_total = Complex::new(1.0, 0.0) / z_vrm;

        // Add capacitor branch admittances: Y_total = Y_vrm + sum(1 / Z_cap_k)
        for cap in &spec.capacitors {
            let z_cap = cap.impedance_at(f);
            y_total += Complex::new(1.0, 0.0) / z_cap;
        }

        let z_eff = Complex::new(1.0, 0.0) / y_total;
        let mag = z_eff.norm();

        if mag > max_z {
            max_z = mag;
        }

        freqs_hz.push(f);
        z_mag.push(mag);
    }

    // Detect anti-resonance peaks (local maxima in impedance)
    let mut peaks = Vec::new();
    for i in 1..n.saturating_sub(1) {
        if z_mag[i] > z_mag[i - 1] && z_mag[i] > z_mag[i + 1] {
            peaks.push(AntiResonancePeakV1 {
                frequency_hz: freqs_hz[i],
                peak_impedance_ohms: z_mag[i],
            });
        }
    }

    let violates = max_z > target_z;

    PdnImpedanceProfileV1 {
        frequencies_hz: freqs_hz,
        impedance_magnitude_ohms: z_mag,
        target_impedance_ohms: target_z,
        max_impedance_ohms: max_z,
        anti_resonance_peaks: peaks,
        violates_target: violates,
    }
}

/// Simulate core rail transient voltage droop from a current step demand.
pub fn simulate_pdn_transient_droop(
    spec: &PdnNetworkSpecV1,
    current_step_a: f64,
    step_duration_ns: f64,
    total_time_ns: f64,
    dt_ns: f64,
) -> PdnTransientResultV1 {
    let steps = (total_time_ns / dt_ns).round() as usize;
    let mut time_ns = Vec::with_capacity(steps);
    let mut rail_v = Vec::with_capacity(steps);
    let mut current_a = Vec::with_capacity(steps);

    let allowed_ripple = spec.nominal_voltage_v * spec.ripple_tolerance_fraction;

    // Total effective capacitance and ESR/ESL estimate for lumped transient response
    let total_c: f64 = spec.capacitors.iter().map(|c| c.capacitance_f * c.count as f64).sum();
    let eff_esr: f64 = 1.0 / spec.capacitors.iter().map(|c| (c.count as f64) / c.esr_ohms).sum::<f64>();

    let mut min_v = spec.nominal_voltage_v;

    for i in 0..steps {
        let t = i as f64 * dt_ns;
        // Linear current ramp over step_duration_ns
        let i_load = if t <= step_duration_ns {
            (t / step_duration_ns) * current_step_a
        } else {
            current_step_a
        };

        // Voltage droop: resistive drop + capacitive discharge + VRM recovery
        let t_sec = t * 1.0e-9;
        let v_drop_esr = i_load * eff_esr;
        let v_drop_cap = if total_c > 0.0 {
            (i_load * t_sec.min(50.0e-9)) / total_c
        } else {
            0.0
        };

        // VRM kicks in with tau_vrm ~ L_vrm / R_vrm
        let vrm_tau = spec.vrm_inductance_henries / spec.vrm_resistance_ohms.max(1e-6);
        let recovery_factor = (1.0 - (-t_sec / vrm_tau).exp()).clamp(0.0, 1.0);
        let total_droop = (v_drop_esr + v_drop_cap) * (1.0 - 0.7 * recovery_factor);

        let v_rail = spec.nominal_voltage_v - total_droop;
        if v_rail < min_v {
            min_v = v_rail;
        }

        time_ns.push(t);
        rail_v.push(v_rail);
        current_a.push(i_load);
    }

    let max_droop = spec.nominal_voltage_v - min_v;
    let passed = max_droop <= allowed_ripple;

    PdnTransientResultV1 {
        time_ns,
        rail_voltage_v: rail_v,
        current_a,
        max_voltage_droop_v: max_droop,
        min_rail_voltage_v: min_v,
        allowed_ripple_v: allowed_ripple,
        passed,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tdr_impedance_reconstruction_uniform_line_and_mismatch() {
        let dt = 1.0e-12; // 1 ps
        // Uniform matched 50 Ohm line: reflection = 0
        let refl_flat = vec![0.0; 100];
        let tdr_flat = reconstruct_tdr_impedance_profile(&refl_flat, dt, 50.0);
        assert_eq!(tdr_flat.z_min_ohms, 50.0);
        assert_eq!(tdr_flat.z_max_ohms, 50.0);

        // Line with 75 Ohm step: Gamma = (75 - 50)/(75 + 50) = 25/125 = +0.20
        let mut refl_step = vec![0.0; 50];
        refl_step.extend(std::iter::repeat_n(0.20, 50));
        let tdr_step = reconstruct_tdr_impedance_profile(&refl_step, dt, 50.0);
        assert!((tdr_step.z_max_ohms - 75.0).abs() < 1e-12);
    }

    #[test]
    fn test_pdn_target_impedance_and_anti_resonance_detection() {
        let spec = PdnNetworkSpecV1::standard_core_rail();
        // Z_target = 0.85 * 0.03 / 6.0 = 0.0255 / 6.0 = 0.00425 Ohm (4.25 mOhm)
        assert!((spec.target_impedance_ohms() - 0.00425).abs() < 1e-6);

        // Generate frequency grid from 100 kHz to 100 MHz (log-distributed)
        let freqs: Vec<Hertz> = (1..=200)
            .map(|i| Hertz::try_new(10.0_f64.powf(5.0 + 3.0 * (i as f64 / 200.0))).unwrap())
            .collect();

        let profile = calculate_pdn_impedance_profile(&spec, &freqs);
        assert_eq!(profile.frequencies_hz.len(), 200);
        assert!(!profile.anti_resonance_peaks.is_empty());

        let peak = &profile.anti_resonance_peaks[0];
        assert!(peak.peak_impedance_ohms > 0.0);
    }

    #[test]
    fn test_pdn_transient_droop_simulation() {
        let spec = PdnNetworkSpecV1::standard_core_rail();
        // 6 A step with 1 ns ramp over 50 ns total time
        let res = simulate_pdn_transient_droop(&spec, 6.0, 1.0, 50.0, 0.1);
        assert_eq!(res.time_ns.len(), 500);
        assert!(res.max_voltage_droop_v > 0.0);
        assert!(res.max_voltage_droop_v < 0.05); // Less than 50 mV droop
        assert!(res.passed); // Passes the 25.5 mV ripple budget
    }
}
