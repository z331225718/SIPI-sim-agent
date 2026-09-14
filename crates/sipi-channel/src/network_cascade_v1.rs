#![forbid(unsafe_code)]

//! Typed Touchstone network workflow, port mapping, multi-stage cascade,
//! frequency-domain loading, and single final FD-to-TD transformation.
//!
//! This module implements the clean-room frequency-domain network assembly
//! without piece-wise impulse truncation, intermediate S-parameter fitting,
//! or implicit grid interpolation.

use std::{error::Error, fmt};

use rustfft::{FftPlanner, num_complex::Complex};
use sipi_types::{Complex64, Hertz, Ohms, Seconds};

use crate::{FourPortS, TwoPortS};

const NUMERICAL_EPSILON: f64 = 1.0e-15;
const PASSIVITY_TOLERANCE: f64 = 1.0e-10;
const RECIPROCITY_TOLERANCE: f64 = 1.0e-10;

/// Upper bound for the discrete-kernel IFFT length. The frequency grid and the
/// target sample interval jointly determine `N_fft = 1 / (df * dt)`, so a
/// caller that pairs a tiny step with a tiny interval can otherwise request an
/// allocation far beyond physical memory. The certified one-sided sample
/// budgets stay far below this bound, so the request fails closed instead.
const MAX_DISCRETE_KERNEL_FFT_LENGTH: usize = 1 << 24;

/// Errors arising during Touchstone network admission, port mapping,
/// cascade, termination loading, or FD-to-TD transformation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CascadeError {
    EmptyFrequencyGrid,
    TooFewSamples,
    NonIncreasingFrequency,
    NonPositiveImpedance,
    InvalidPortIndex,
    DuplicatePortIndex,
    FrequencyGridMismatch { expected_len: usize, actual_len: usize },
    FrequencyValuesMismatch { index: usize },
    SingularCascadeDenominator { frequency_hz_bits: u64 },
    SingularTerminationDenominator { frequency_hz_bits: u64 },
    NonFiniteCalculation,
    NonUniformFrequencyGrid,
    InvalidNyquistGrid,
    FftLengthOverflow,
    InverseImaginaryResidue,
}

impl fmt::Display for CascadeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "network cascade error: {self:?}")
    }
}

impl Error for CascadeError {}

/// Port mapping policy for 4-port single-ended Touchstone data
/// to 2-port differential mode.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PortMapV1 {
    /// Standard Touchstone column-major mapping (default in S4P files):
    /// Port 1 = TX+, Port 2 = RX+, Port 3 = TX-, Port 4 = RX-.
    TxPlusRxPlusTxMinusRxMinus,
    /// Adjacent differential pair mapping:
    /// Port 1 = TX+, Port 2 = TX-, Port 3 = RX+, Port 4 = RX-.
    TxPlusTxMinusRxPlusRxMinus,
    /// Explicit 0-indexed port mapping: [TX+, TX-, RX+, RX-].
    Custom([usize; 4]),
}

impl PortMapV1 {
    /// Return the 0-indexed port indices `[tx_plus, tx_minus, rx_plus, rx_minus]`.
    pub const fn port_indices(self) -> [usize; 4] {
        match self {
            Self::TxPlusRxPlusTxMinusRxMinus => [0, 2, 1, 3],
            Self::TxPlusTxMinusRxPlusRxMinus => [0, 1, 2, 3],
            Self::Custom(indices) => indices,
        }
    }
}

/// Convert a single-ended 4-port S-parameter matrix to a 2-port differential
/// S-parameter matrix (Sdd) using the specified port mapping.
///
/// All four elements of the differential matrix (Sdd11, Sdd12, Sdd21, Sdd22)
/// are computed and retained; Sdd21 is never taken in isolation.
pub fn four_port_to_differential_two_port(
    matrix: FourPortS,
    port_map: PortMapV1,
) -> Result<TwoPortS, CascadeError> {
    let [p1, p2, p3, p4] = port_map.port_indices();
    if p1 >= 4 || p2 >= 4 || p3 >= 4 || p4 >= 4 {
        return Err(CascadeError::InvalidPortIndex);
    }
    if p1 == p2 || p1 == p3 || p1 == p4 || p2 == p3 || p2 == p4 || p3 == p4 {
        return Err(CascadeError::DuplicatePortIndex);
    }

    let s = |out: usize, inc: usize| -> Result<Complex<f64>, CascadeError> {
        let val = matrix.at(out, inc).ok_or(CascadeError::InvalidPortIndex)?;
        Ok(Complex::new(val.real(), val.imaginary()))
    };

    // Mixed-mode modal decomposition:
    // Input differential pair: port p1 (+), port p2 (-)
    // Output differential pair: port p3 (+), port p4 (-)
    // Sdd11 = 0.5 * (S[p1,p1] - S[p1,p2] - S[p2,p1] + S[p2,p2])
    // Sdd12 = 0.5 * (S[p1,p3] - S[p1,p4] - S[p2,p3] + S[p2,p4])
    // Sdd21 = 0.5 * (S[p3,p1] - S[p3,p2] - S[p4,p1] + S[p4,p2])
    // Sdd22 = 0.5 * (S[p3,p3] - S[p3,p4] - S[p4,p3] + S[p4,p4])
    let sdd11 = (s(p1, p1)? - s(p1, p2)? - s(p2, p1)? + s(p2, p2)?) * 0.5;
    let sdd12 = (s(p1, p3)? - s(p1, p4)? - s(p2, p3)? + s(p2, p4)?) * 0.5;
    let sdd21 = (s(p3, p1)? - s(p3, p2)? - s(p4, p1)? + s(p4, p2)?) * 0.5;
    let sdd22 = (s(p3, p3)? - s(p3, p4)? - s(p4, p3)? + s(p4, p4)?) * 0.5;

    let to_c64 = |c: Complex<f64>| -> Result<Complex64, CascadeError> {
        Complex64::try_new(c.re, c.im).map_err(|_| CascadeError::NonFiniteCalculation)
    };

    Ok(TwoPortS {
        s11: to_c64(sdd11)?,
        s12: to_c64(sdd12)?,
        s21: to_c64(sdd21)?,
        s22: to_c64(sdd22)?,
    })
}

/// Mixed-mode modal diagnostics for a 4-port network.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct MixedModeDiagnosticsV1 {
    pub sdd21_mag: f64,
    pub scc21_mag: f64,
    pub scd21_mag: f64,
    pub sdc21_mag: f64,
    pub mode_conversion_ratio: f64,
}

/// Compute mixed-mode components and conversion ratio for diagnostic inspection.
pub fn analyze_mixed_mode_components(
    matrix: FourPortS,
    port_map: PortMapV1,
) -> Result<MixedModeDiagnosticsV1, CascadeError> {
    let [p1, p2, p3, p4] = port_map.port_indices();
    let s = |out: usize, inc: usize| -> Result<Complex<f64>, CascadeError> {
        let val = matrix.at(out, inc).ok_or(CascadeError::InvalidPortIndex)?;
        Ok(Complex::new(val.real(), val.imaginary()))
    };

    let sdd21 = (s(p3, p1)? - s(p3, p2)? - s(p4, p1)? + s(p4, p2)?) * 0.5;
    let scc21 = (s(p3, p1)? + s(p3, p2)? + s(p4, p1)? + s(p4, p2)?) * 0.5;
    let scd21 = (s(p3, p1)? - s(p3, p2)? + s(p4, p1)? - s(p4, p2)?) * 0.5;
    let sdc21 = (s(p3, p1)? + s(p3, p2)? - s(p4, p1)? - s(p4, p2)?) * 0.5;

    let sdd = sdd21.norm();
    let scc = scc21.norm();
    let scd = scd21.norm();
    let sdc = sdc21.norm();
    let mode_conv = if sdd > NUMERICAL_EPSILON {
        scd / sdd
    } else {
        0.0
    };

    Ok(MixedModeDiagnosticsV1 {
        sdd21_mag: sdd,
        scc21_mag: scc,
        scd21_mag: scd,
        sdc21_mag: sdc,
        mode_conversion_ratio: mode_conv,
    })
}

/// Cascade two 2-port S-parameter networks connected in series:
/// Output (port 2) of network A connected to input (port 1) of network B.
///
/// Uses the exact, closed-form Redheffer star product without matrix inversion:
///
///   D = 1 - S22_A * S11_B
///   S11 = S11_A + (S12_A * S11_B * S21_A) / D
///   S21 = (S21_A * S21_B) / D
///   S12 = (S12_A * S12_B) / D
///   S22 = S22_B + (S21_B * S22_A * S12_B) / D
pub fn cascade_two_ports(a: TwoPortS, b: TwoPortS) -> Result<TwoPortS, CascadeError> {
    let a11 = Complex::new(a.s11.real(), a.s11.imaginary());
    let a12 = Complex::new(a.s12.real(), a.s12.imaginary());
    let a21 = Complex::new(a.s21.real(), a.s21.imaginary());
    let a22 = Complex::new(a.s22.real(), a.s22.imaginary());

    let b11 = Complex::new(b.s11.real(), b.s11.imaginary());
    let b12 = Complex::new(b.s12.real(), b.s12.imaginary());
    let b21 = Complex::new(b.s21.real(), b.s21.imaginary());
    let b22 = Complex::new(b.s22.real(), b.s22.imaginary());

    let one = Complex::new(1.0, 0.0);
    let denominator = one - a22 * b11;
    if denominator.norm() < NUMERICAL_EPSILON {
        return Err(CascadeError::SingularCascadeDenominator {
            frequency_hz_bits: 0,
        });
    }

    let s11 = a11 + (a12 * b11 * a21) / denominator;
    let s21 = (a21 * b21) / denominator;
    let s12 = (a12 * b12) / denominator;
    let s22 = b22 + (b21 * a22 * b12) / denominator;

    let to_c64 = |c: Complex<f64>| -> Result<Complex64, CascadeError> {
        if !c.re.is_finite() || !c.im.is_finite() {
            return Err(CascadeError::NonFiniteCalculation);
        }
        Complex64::try_new(c.re, c.im).map_err(|_| CascadeError::NonFiniteCalculation)
    };

    Ok(TwoPortS {
        s11: to_c64(s11)?,
        s12: to_c64(s12)?,
        s21: to_c64(s21)?,
        s22: to_c64(s22)?,
    })
}

/// A 2-port network sampled over a discrete frequency grid.
#[derive(Clone, Debug, PartialEq)]
pub struct TwoPortSpectrumV1 {
    name: String,
    reference_impedance: Ohms,
    frequencies: Vec<Hertz>,
    samples: Vec<TwoPortS>,
}

impl TwoPortSpectrumV1 {
    pub fn try_new(
        name: impl Into<String>,
        reference_impedance: Ohms,
        frequencies: Vec<Hertz>,
        samples: Vec<TwoPortS>,
    ) -> Result<Self, CascadeError> {
        if reference_impedance.get() <= 0.0 {
            return Err(CascadeError::NonPositiveImpedance);
        }
        if frequencies.is_empty() {
            return Err(CascadeError::EmptyFrequencyGrid);
        }
        if frequencies.len() < 2 {
            return Err(CascadeError::TooFewSamples);
        }
        if frequencies.len() != samples.len() {
            return Err(CascadeError::FrequencyGridMismatch {
                expected_len: frequencies.len(),
                actual_len: samples.len(),
            });
        }
        for window in frequencies.windows(2) {
            if window[1].get() <= window[0].get() {
                return Err(CascadeError::NonIncreasingFrequency);
            }
        }
        Ok(Self {
            name: name.into(),
            reference_impedance,
            frequencies,
            samples,
        })
    }

    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn reference_impedance(&self) -> Ohms {
        self.reference_impedance
    }

    pub fn frequencies(&self) -> &[Hertz] {
        &self.frequencies
    }

    pub fn samples(&self) -> &[TwoPortS] {
        &self.samples
    }

    pub fn sample_count(&self) -> usize {
        self.samples.len()
    }
}

/// Cascade a sequence of two-port network stages on a common frequency grid.
///
/// If fewer than 1 stage is provided, returns an error.
/// If 1 stage is provided, returns a clone of that stage.
/// If 2 or more stages are provided, cascades them sequentially.
pub fn cascade_network_stages(
    name: impl Into<String>,
    stages: &[TwoPortSpectrumV1],
) -> Result<TwoPortSpectrumV1, CascadeError> {
    if stages.is_empty() {
        return Err(CascadeError::TooFewSamples);
    }
    let first = &stages[0];
    let freq_len = first.frequencies().len();
    let ref_z = first.reference_impedance();

    // Verify all stages share the exact same frequency grid and reference impedance
    for (stage_idx, stage) in stages.iter().enumerate().skip(1) {
        if stage.frequencies().len() != freq_len {
            return Err(CascadeError::FrequencyGridMismatch {
                expected_len: freq_len,
                actual_len: stage.frequencies().len(),
            });
        }
        for (i, (&f_expected, &f_actual)) in first
            .frequencies()
            .iter()
            .zip(stage.frequencies())
            .enumerate()
        {
            if f_expected.get().to_bits() != f_actual.get().to_bits() {
                return Err(CascadeError::FrequencyValuesMismatch { index: i });
            }
        }
        if (stage.reference_impedance().get() - ref_z.get()).abs() > NUMERICAL_EPSILON {
            return Err(CascadeError::NonPositiveImpedance);
        }
        let _ = stage_idx;
    }

    let mut cumulative_samples = first.samples().to_vec();

    for next_stage in &stages[1..] {
        for (i, next_sample) in next_stage.samples().iter().enumerate() {
            cumulative_samples[i] = match cascade_two_ports(cumulative_samples[i], *next_sample) {
                Ok(cascaded) => cascaded,
                Err(CascadeError::SingularCascadeDenominator { .. }) => {
                    return Err(CascadeError::SingularCascadeDenominator {
                        frequency_hz_bits: first.frequencies()[i].get().to_bits(),
                    });
                }
                Err(err) => return Err(err),
            };
        }
    }

    TwoPortSpectrumV1::try_new(
        name,
        ref_z,
        first.frequencies().to_vec(),
        cumulative_samples,
    )
}

/// Frequency grid and Nyquist coverage diagnostics.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct FrequencyGridCoverageV1 {
    pub is_uniform: bool,
    pub frequency_step_hz: Option<f64>,
    pub has_dc: bool,
    pub min_frequency_hz: f64,
    pub max_frequency_hz: f64,
    pub nyquist_frequency_hz: Option<f64>,
    pub nyquist_coverage_ratio: Option<f64>,
    pub nyquist_adequate: Option<bool>,
}

/// Assess frequency grid coverage, uniformity, and Nyquist adequacy without modifying points.
pub fn assess_frequency_grid_coverage(
    frequencies: &[Hertz],
    target_dt: Option<Seconds>,
) -> Result<FrequencyGridCoverageV1, CascadeError> {
    if frequencies.len() < 2 {
        return Err(CascadeError::TooFewSamples);
    }
    let min_f = frequencies[0].get();
    let max_f = frequencies[frequencies.len() - 1].get();
    let has_dc = min_f == 0.0;

    let mut is_uniform = true;
    let initial_step = frequencies[1].get() - frequencies[0].get();
    for window in frequencies.windows(2) {
        let step = window[1].get() - window[0].get();
        if (step - initial_step).abs() > 1e-9 * initial_step.max(1.0) {
            is_uniform = false;
            break;
        }
    }
    let frequency_step_hz = if is_uniform { Some(initial_step) } else { None };

    let (nyquist_f, ratio, adequate) = if let Some(dt) = target_dt {
        if dt.get() > 0.0 {
            let nyq = 0.5 / dt.get();
            let r = max_f / nyq;
            (Some(nyq), Some(r), Some(max_f >= nyq * (1.0 - 1e-9)))
        } else {
            (None, None, None)
        }
    } else {
        (None, None, None)
    };

    Ok(FrequencyGridCoverageV1 {
        is_uniform,
        frequency_step_hz,
        has_dc,
        min_frequency_hz: min_f,
        max_frequency_hz: max_f,
        nyquist_frequency_hz: nyquist_f,
        nyquist_coverage_ratio: ratio,
        nyquist_adequate: adequate,
    })
}

/// Sampled passivity evaluation across a 2-port spectrum.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct DetailedPassivityDiagnosticsV1 {
    pub passes_bound: bool,
    pub worst_frequency_hz: f64,
    pub worst_index: usize,
    pub maximum_singular_value: f64,
}

/// Evaluate maximum singular value at every frequency point to assess passivity.
pub fn evaluate_sampled_passivity(
    network: &TwoPortSpectrumV1,
) -> Result<DetailedPassivityDiagnosticsV1, CascadeError> {
    let mut worst_sigma = 0.0_f64;
    let mut worst_index = 0;
    let mut worst_freq = 0.0_f64;

    for (index, (&freq, &sample)) in network.frequencies().iter().zip(network.samples()).enumerate() {
        let a = Complex::new(sample.s11.real(), sample.s11.imaginary());
        let b = Complex::new(sample.s12.real(), sample.s12.imaginary());
        let c = Complex::new(sample.s21.real(), sample.s21.imaginary());
        let d = Complex::new(sample.s22.real(), sample.s22.imaginary());
        // Form Hermitian matrix M = S^H * S
        // M11 = |a|^2 + |c|^2
        // M22 = |b|^2 + |d|^2
        // M12 = a* b + c* d
        // Eigenvalues: lambda = (M11 + M22 +/- sqrt((M11 - M22)^2 + 4 |M12|^2)) / 2
        // Using the sum of squares avoids catastrophic cancellation.
        let m11 = a.norm_sqr() + c.norm_sqr();
        let m22 = b.norm_sqr() + d.norm_sqr();
        let m12 = a.conj() * b + c.conj() * d;
        let diff = m11 - m22;
        let disc = (diff * diff + 4.0 * m12.norm_sqr()).sqrt();
        let lambda_max = (m11 + m22 + disc) * 0.5;
        let sigma_max = lambda_max.max(0.0).sqrt();

        if sigma_max > worst_sigma {
            worst_sigma = sigma_max;
            worst_index = index;
            worst_freq = freq.get();
        }
    }

    Ok(DetailedPassivityDiagnosticsV1 {
        passes_bound: worst_sigma <= 1.0 + PASSIVITY_TOLERANCE,
        worst_frequency_hz: worst_freq,
        worst_index,
        maximum_singular_value: worst_sigma,
    })
}

/// Sampled reciprocity evaluation across a 2-port spectrum.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct DetailedReciprocityDiagnosticsV1 {
    pub passes_bound: bool,
    pub worst_frequency_hz: f64,
    pub worst_index: usize,
    pub maximum_difference: f64,
}

/// Evaluate |S12 - S21| at every frequency point to assess reciprocity.
pub fn evaluate_sampled_reciprocity(
    network: &TwoPortSpectrumV1,
) -> Result<DetailedReciprocityDiagnosticsV1, CascadeError> {
    let mut worst_diff = 0.0_f64;
    let mut worst_index = 0;
    let mut worst_freq = 0.0_f64;

    for (index, (&freq, &sample)) in network.frequencies().iter().zip(network.samples()).enumerate() {
        let s12 = Complex::new(sample.s12.real(), sample.s12.imaginary());
        let s21 = Complex::new(sample.s21.real(), sample.s21.imaginary());
        let diff = (s12 - s21).norm();

        if diff > worst_diff {
            worst_diff = diff;
            worst_index = index;
            worst_freq = freq.get();
        }
    }

    Ok(DetailedReciprocityDiagnosticsV1 {
        passes_bound: worst_diff <= RECIPROCITY_TOLERANCE,
        worst_frequency_hz: worst_freq,
        worst_index,
        maximum_difference: worst_diff,
    })
}

/// Termination parameters for source or load.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct TerminationParamsV1 {
    pub resistance_ohms: Ohms,
    pub capacitance_farads: f64,
}

impl TerminationParamsV1 {
    pub fn new(resistance_ohms: Ohms, capacitance_farads: f64) -> Result<Self, CascadeError> {
        if resistance_ohms.get() <= 0.0 || !capacitance_farads.is_finite() || capacitance_farads < 0.0 {
            return Err(CascadeError::NonPositiveImpedance);
        }
        Ok(Self {
            resistance_ohms,
            capacitance_farads,
        })
    }
}

/// Calculate the loaded voltage transfer function H(f) = Vload(f) / Vhalf_open(f)
/// for a 2-port network with explicit source and load terminations.
///
/// Vhalf_open is half of the open-circuit source voltage: V_source = 2 * Vhalf_open.
///
///   Zs(w) = Rs / (1 + j*w*Rs*Cs)
///   Zl(w) = Rl / (1 + j*w*Rl*Cl)
///   Gamma_s = (Zs - Z0) / (Zs + Z0)
///   Gamma_l = (Zl - Z0) / (Zl + Z0)
///
///   H(f) = (1 - Gamma_s) * (1 + Gamma_l) * S21 /
///          [ (1 - S11*Gamma_s)*(1 - S22*Gamma_l) - S12*S21*Gamma_s*Gamma_l ]
pub fn calculate_loaded_voltage_transfer(
    network: &TwoPortSpectrumV1,
    source: TerminationParamsV1,
    load: TerminationParamsV1,
) -> Result<Vec<Complex<f64>>, CascadeError> {
    let z0 = network.reference_impedance().get();
    let rs = source.resistance_ohms.get();
    let cs = source.capacitance_farads;
    let rl = load.resistance_ohms.get();
    let cl = load.capacitance_farads;

    let one = Complex::new(1.0, 0.0);
    let mut transfer = Vec::with_capacity(network.sample_count());

    for (&freq, &sample) in network.frequencies().iter().zip(network.samples()) {
        let f = freq.get();
        let omega = 2.0 * std::f64::consts::PI * f;

        let zs = if cs > 0.0 && omega > 0.0 {
            Complex::new(rs, 0.0) / Complex::new(1.0, omega * rs * cs)
        } else {
            Complex::new(rs, 0.0)
        };

        let zl = if cl > 0.0 && omega > 0.0 {
            Complex::new(rl, 0.0) / Complex::new(1.0, omega * rl * cl)
        } else {
            Complex::new(rl, 0.0)
        };

        let gamma_s = (zs - z0) / (zs + z0);
        let gamma_l = (zl - z0) / (zl + z0);

        let s11 = Complex::new(sample.s11.real(), sample.s11.imaginary());
        let s12 = Complex::new(sample.s12.real(), sample.s12.imaginary());
        let s21 = Complex::new(sample.s21.real(), sample.s21.imaginary());
        let s22 = Complex::new(sample.s22.real(), sample.s22.imaginary());

        let denom = (one - s11 * gamma_s) * (one - s22 * gamma_l) - s12 * s21 * gamma_s * gamma_l;
        if denom.norm() < NUMERICAL_EPSILON {
            return Err(CascadeError::SingularTerminationDenominator {
                frequency_hz_bits: f.to_bits(),
            });
        }

        let num = (one - gamma_s) * (one + gamma_l) * s21;
        let h = num / denom;
        if !h.re.is_finite() || !h.im.is_finite() {
            return Err(CascadeError::NonFiniteCalculation);
        }
        transfer.push(h);
    }

    Ok(transfer)
}

/// Time-domain impulse response kernel metrics.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct KernelMetricsV1 {
    pub peak_index: usize,
    pub peak_time_s: f64,
    pub peak_value: f64,
    pub total_energy: f64,
    pub tail_energy_ratio: f64,
    pub precursor_energy_ratio: f64,
}

/// Perform one single final FD-to-TD transformation from the loaded voltage
/// transfer function to a discrete time-domain impulse response kernel.
///
/// Origin t=0 is retained at index 0 without trimming, peak shifting,
/// or window phase alignment.
pub fn spectrum_to_discrete_kernel(
    frequencies: &[Hertz],
    transfer: &[Complex<f64>],
    target_dt: Seconds,
    apply_raised_cosine_window: bool,
    impulse_length: Option<Seconds>,
) -> Result<(Vec<f64>, KernelMetricsV1), CascadeError> {
    if frequencies.len() < 2 || frequencies.len() != transfer.len() {
        return Err(CascadeError::TooFewSamples);
    }
    if target_dt.get() <= 0.0 {
        return Err(CascadeError::InvalidNyquistGrid);
    }

    let df = frequencies[1].get() - frequencies[0].get();
    if df <= 0.0 {
        return Err(CascadeError::NonUniformFrequencyGrid);
    }
    if frequencies[0].get() != 0.0 {
        return Err(CascadeError::NonUniformFrequencyGrid);
    }

    // N_fft = 1 / (df * dt)
    let n_fft_float = 1.0 / (df * target_dt.get());
    let n_fft = n_fft_float.round() as usize;
    if (n_fft_float - n_fft as f64).abs() > 1e-6 {
        return Err(CascadeError::InvalidNyquistGrid);
    }
    if n_fft < 2 || n_fft % 2 != 0 {
        return Err(CascadeError::InvalidNyquistGrid);
    }
    if n_fft > MAX_DISCRETE_KERNEL_FFT_LENGTH {
        return Err(CascadeError::FftLengthOverflow);
    }

    let one_sided_bins = n_fft / 2 + 1;
    let max_f = frequencies[frequencies.len() - 1].get();

    // Prepare full two-sided spectrum
    let mut full_spectrum = vec![Complex::new(0.0, 0.0); n_fft];

    for (k, (&freq, &h_val)) in frequencies.iter().zip(transfer).enumerate() {
        if k >= one_sided_bins {
            break;
        }
        let f = freq.get();
        let window = if apply_raised_cosine_window {
            if f <= max_f && max_f > 0.0 {
                0.5 * (1.0 + (std::f64::consts::PI * f / max_f).cos())
            } else {
                0.0
            }
        } else {
            1.0
        };

        let mut val = h_val * window;
        // DC and Nyquist must be purely real for Hermitian symmetry
        if k == 0 {
            val.im = 0.0;
        }
        if k == n_fft / 2 {
            val.im = 0.0;
        }
        full_spectrum[k] = val;
    }

    // Hermitian conjugate for negative frequencies: X[N - k] = X[k]*
    for k in 1..(n_fft / 2) {
        full_spectrum[n_fft - k] = full_spectrum[k].conj();
    }

    // Execute IFFT
    let mut planner = FftPlanner::new();
    let ifft = planner.plan_fft_inverse(n_fft);
    ifft.process(&mut full_spectrum);

    let scale = 1.0 / (n_fft as f64);
    let raw_kernel = full_spectrum
        .iter()
        .map(|c| {
            if c.im.abs() > 1e-7 * (c.re.abs().max(1.0)) {
                // If residual imaginary component is large, something broke symmetry
            }
            c.re * scale
        })
        .collect::<Vec<_>>();

    // Bounded truncation if impulse_length is requested
    let retained_len = if let Some(len) = impulse_length {
        let samples = (len.get() / target_dt.get()).round() as usize;
        samples.clamp(1, n_fft)
    } else {
        n_fft
    };

    let kernel = raw_kernel[..retained_len].to_vec();

    // Evaluate kernel metrics
    let mut peak_val = 0.0_f64;
    let mut peak_idx = 0;
    let mut total_energy = 0.0_f64;

    for (idx, &val) in kernel.iter().enumerate() {
        let abs_val = val.abs();
        if abs_val > peak_val {
            peak_val = abs_val;
            peak_idx = idx;
        }
        total_energy += val * val;
    }

    let tail_start = retained_len * 3 / 4;
    let mut tail_energy = 0.0_f64;
    for &val in &kernel[tail_start..] {
        tail_energy += val * val;
    }
    let tail_ratio = if total_energy > 0.0 {
        tail_energy / total_energy
    } else {
        0.0
    };

    // Pre-cursor energy evaluated relative to peak
    let mut precursor_energy = 0.0_f64;
    for &val in &kernel[..peak_idx] {
        precursor_energy += val * val;
    }
    let precursor_ratio = if total_energy > 0.0 {
        precursor_energy / total_energy
    } else {
        0.0
    };

    let metrics = KernelMetricsV1 {
        peak_index: peak_idx,
        peak_time_s: peak_idx as f64 * target_dt.get(),
        peak_value: peak_val,
        total_energy,
        tail_energy_ratio: tail_ratio,
        precursor_energy_ratio: precursor_ratio,
    };

    Ok((kernel, metrics))
}

// ---------------------------------------------------------------------------
// Analytical Fixture Generators for Testing and Verification
// ---------------------------------------------------------------------------

/// Create an ideal lossless Thru 2-port network:
/// S11 = S22 = 0, S21 = S12 = 1.
pub fn create_analytic_thru_network(
    frequencies: &[Hertz],
    reference_impedance: Ohms,
) -> Result<TwoPortSpectrumV1, CascadeError> {
    let one = Complex64::try_new(1.0, 0.0).map_err(|_| CascadeError::NonFiniteCalculation)?;
    let zero = Complex64::try_new(0.0, 0.0).map_err(|_| CascadeError::NonFiniteCalculation)?;
    let sample = TwoPortS {
        s11: zero,
        s12: one,
        s21: one,
        s22: zero,
    };
    let samples = vec![sample; frequencies.len()];
    TwoPortSpectrumV1::try_new(
        "analytic_thru",
        reference_impedance,
        frequencies.to_vec(),
        samples,
    )
}

/// Create an ideal pure-delay 2-port network:
/// S11 = S22 = 0, S21 = S12 = exp(-j * omega * tau).
pub fn create_analytic_delay_network(
    frequencies: &[Hertz],
    reference_impedance: Ohms,
    delay_seconds: f64,
) -> Result<TwoPortSpectrumV1, CascadeError> {
    let zero = Complex64::try_new(0.0, 0.0).map_err(|_| CascadeError::NonFiniteCalculation)?;
    let mut samples = Vec::with_capacity(frequencies.len());
    for &freq in frequencies {
        let omega = 2.0 * std::f64::consts::PI * freq.get();
        let phase = -omega * delay_seconds;
        let trans = Complex64::try_new(phase.cos(), phase.sin())
            .map_err(|_| CascadeError::NonFiniteCalculation)?;
        samples.push(TwoPortS {
            s11: zero,
            s12: trans,
            s21: trans,
            s22: zero,
        });
    }
    TwoPortSpectrumV1::try_new(
        "analytic_delay",
        reference_impedance,
        frequencies.to_vec(),
        samples,
    )
}

/// Create an analytical mismatched transmission line 2-port network:
/// Characterized by characteristic impedance Zc, propagation velocity v, and length L.
///
/// S-parameters relative to reference impedance Z0:
///   theta = omega * L / v
///   Gamma = (Zc - Z0) / (Zc + Z0)
///   D = 1 - Gamma^2 * exp(-2*j*theta)
///   S11 = S22 = Gamma * (1 - exp(-2*j*theta)) / D
///   S21 = S12 = (1 - Gamma^2) * exp(-j*theta) / D
pub fn create_analytic_mismatched_line_network(
    frequencies: &[Hertz],
    reference_impedance: Ohms,
    line_impedance_ohms: f64,
    propagation_velocity_m_per_s: f64,
    length_m: f64,
) -> Result<TwoPortSpectrumV1, CascadeError> {
    let z0 = reference_impedance.get();
    let zc = line_impedance_ohms;
    if zc <= 0.0 || propagation_velocity_m_per_s <= 0.0 || length_m < 0.0 {
        return Err(CascadeError::NonPositiveImpedance);
    }

    let mut samples = Vec::with_capacity(frequencies.len());
    for &freq in frequencies {
        let omega = 2.0 * std::f64::consts::PI * freq.get();
        let theta = omega * length_m / propagation_velocity_m_per_s;
        let cos_t = theta.cos();
        let sin_t = theta.sin();

        // Exact ABCD conversion to S-parameters with reference impedance Z0:
        // Delta = 2*cos(theta) + j*(Zc/Z0 + Z0/Zc)*sin(theta)
        // S11 = S22 = j*(Zc/Z0 - Z0/Zc)*sin(theta) / Delta
        // S21 = S12 = 2 / Delta
        let delta = Complex::new(2.0 * cos_t, (zc / z0 + z0 / zc) * sin_t);
        let s11 = Complex::new(0.0, (zc / z0 - z0 / zc) * sin_t) / delta;
        let s21 = Complex::new(2.0, 0.0) / delta;

        let to_c64 = |c: Complex<f64>| -> Result<Complex64, CascadeError> {
            Complex64::try_new(c.re, c.im).map_err(|_| CascadeError::NonFiniteCalculation)
        };

        samples.push(TwoPortS {
            s11: to_c64(s11)?,
            s12: to_c64(s21)?,
            s21: to_c64(s21)?,
            s22: to_c64(s11)?,
        });
    }

    TwoPortSpectrumV1::try_new(
        "analytic_mismatched_line",
        reference_impedance,
        frequencies.to_vec(),
        samples,
    )
}

/// Create an uncoupled 4-port network consisting of two identical, independent 2-port lines.
/// Line 1 connects Port 1 (TX+) to Port 2 (RX+).
/// Line 2 connects Port 3 (TX-) to Port 4 (RX-).
/// Coupling between the two lines is strictly zero.
pub fn create_analytic_uncoupled_four_port(
    line: TwoPortS,
) -> Result<FourPortS, CascadeError> {
    let zero = Complex64::try_new(0.0, 0.0).map_err(|_| CascadeError::NonFiniteCalculation)?;
    let mut matrix = [[zero; 4]; 4];

    // Port 1 <-> Port 2
    matrix[0][0] = line.s11;
    matrix[0][1] = line.s12;
    matrix[1][0] = line.s21;
    matrix[1][1] = line.s22;

    // Port 3 <-> Port 4
    matrix[2][2] = line.s11;
    matrix[2][3] = line.s12;
    matrix[3][2] = line.s21;
    matrix[3][3] = line.s22;

    // All cross-terms remain strictly zero
    Ok(FourPortS::new(matrix))
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TouchstoneDataFormat {
    RealImaginary,
    MagnitudeDegrees,
    DecibelsDegrees,
}

/// Parse the Touchstone option line `# [Hz|kHz|MHz|GHz] S [RI|MA|DB] R <z0>`
pub fn parse_touchstone_options(
    text: &str,
) -> Result<(f64, TouchstoneDataFormat, f64), CascadeError> {
    for line in text.lines() {
        let trimmed = line.split('!').next().unwrap_or("").trim();
        if trimmed.starts_with('#') {
            let tokens = trimmed[1..].split_whitespace().collect::<Vec<_>>();
            if tokens.len() < 4 {
                return Err(CascadeError::NonFiniteCalculation);
            }
            let freq_unit = match tokens[0].to_ascii_uppercase().as_str() {
                "HZ" => 1.0,
                "KHZ" => 1.0e3,
                "MHZ" => 1.0e6,
                "GHZ" => 1.0e9,
                _ => return Err(CascadeError::NonFiniteCalculation),
            };
            if !tokens[1].eq_ignore_ascii_case("S") {
                return Err(CascadeError::NonFiniteCalculation);
            }
            let format = match tokens[2].to_ascii_uppercase().as_str() {
                "RI" => TouchstoneDataFormat::RealImaginary,
                "MA" => TouchstoneDataFormat::MagnitudeDegrees,
                "DB" => TouchstoneDataFormat::DecibelsDegrees,
                _ => return Err(CascadeError::NonFiniteCalculation),
            };
            let z0 = if tokens.len() >= 5 && tokens[3].eq_ignore_ascii_case("R") {
                tokens[4]
                    .parse::<f64>()
                    .map_err(|_| CascadeError::NonFiniteCalculation)?
            } else if tokens[3].to_ascii_uppercase().starts_with('R') {
                tokens[3][1..]
                    .parse::<f64>()
                    .map_err(|_| CascadeError::NonFiniteCalculation)?
            } else {
                50.0
            };
            if z0 <= 0.0 || !z0.is_finite() {
                return Err(CascadeError::NonPositiveImpedance);
            }
            return Ok((freq_unit, format, z0));
        }
    }
    // Default if option line is missing: GHz, S, MA, 50 ohms
    Ok((1.0e9, TouchstoneDataFormat::MagnitudeDegrees, 50.0))
}

fn parse_touchstone_complex(
    v1: f64,
    v2: f64,
    format: TouchstoneDataFormat,
) -> Result<Complex64, CascadeError> {
    if !v1.is_finite() || !v2.is_finite() {
        return Err(CascadeError::NonFiniteCalculation);
    }
    let (re, im) = match format {
        TouchstoneDataFormat::RealImaginary => (v1, v2),
        TouchstoneDataFormat::MagnitudeDegrees => {
            let rad = v2.to_radians();
            (v1 * rad.cos(), v1 * rad.sin())
        }
        TouchstoneDataFormat::DecibelsDegrees => {
            let mag = 10.0_f64.powf(v1 / 20.0);
            let rad = v2.to_radians();
            (mag * rad.cos(), mag * rad.sin())
        }
    };
    Complex64::try_new(re, im).map_err(|_| CascadeError::NonFiniteCalculation)
}

/// Parse a Touchstone 2-port (.s2p) file into `TwoPortSpectrumV1`.
pub fn parse_touchstone_2port(
    text: &str,
    name: impl Into<String>,
) -> Result<TwoPortSpectrumV1, CascadeError> {
    let (freq_unit, format, z0) = parse_touchstone_options(text)?;
    let ref_z = Ohms::try_new(z0).map_err(|_| CascadeError::NonPositiveImpedance)?;

    let mut tokens = Vec::new();
    for line in text.lines() {
        let line = line.split('!').next().unwrap_or("").trim();
        if line.is_empty() || line.starts_with('#') || line.starts_with('[') {
            continue;
        }
        tokens.extend(line.split_whitespace().map(str::to_owned));
    }

    let row_width = 9; // f, s11(2), s21(2), s12(2), s22(2)
    if tokens.is_empty() || tokens.len() % row_width != 0 {
        return Err(CascadeError::TooFewSamples);
    }

    let mut frequencies = Vec::with_capacity(tokens.len() / row_width);
    let mut samples = Vec::with_capacity(tokens.len() / row_width);

    for chunk in tokens.chunks_exact(row_width) {
        let f_val = chunk[0]
            .parse::<f64>()
            .map_err(|_| CascadeError::NonFiniteCalculation)?
            * freq_unit;
        if !f_val.is_finite() || f_val < 0.0 {
            return Err(CascadeError::NonFiniteCalculation);
        }
        let freq = Hertz::try_new(f_val).map_err(|_| CascadeError::NonFiniteCalculation)?;

        let s11 = parse_touchstone_complex(
            chunk[1].parse().map_err(|_| CascadeError::NonFiniteCalculation)?,
            chunk[2].parse().map_err(|_| CascadeError::NonFiniteCalculation)?,
            format,
        )?;
        let s21 = parse_touchstone_complex(
            chunk[3].parse().map_err(|_| CascadeError::NonFiniteCalculation)?,
            chunk[4].parse().map_err(|_| CascadeError::NonFiniteCalculation)?,
            format,
        )?;
        let s12 = parse_touchstone_complex(
            chunk[5].parse().map_err(|_| CascadeError::NonFiniteCalculation)?,
            chunk[6].parse().map_err(|_| CascadeError::NonFiniteCalculation)?,
            format,
        )?;
        let s22 = parse_touchstone_complex(
            chunk[7].parse().map_err(|_| CascadeError::NonFiniteCalculation)?,
            chunk[8].parse().map_err(|_| CascadeError::NonFiniteCalculation)?,
            format,
        )?;

        frequencies.push(freq);
        samples.push(TwoPortS { s11, s12, s21, s22 });
    }

    TwoPortSpectrumV1::try_new(name, ref_z, frequencies, samples)
}

/// Parse a Touchstone 4-port (.s4p) file into reference impedance, frequency vector, and `FourPortS` matrices.
pub fn parse_touchstone_4port(
    text: &str,
) -> Result<(Ohms, Vec<Hertz>, Vec<FourPortS>), CascadeError> {
    let (freq_unit, format, z0) = parse_touchstone_options(text)?;
    let ref_z = Ohms::try_new(z0).map_err(|_| CascadeError::NonPositiveImpedance)?;

    let mut tokens = Vec::new();
    for line in text.lines() {
        let line = line.split('!').next().unwrap_or("").trim();
        if line.is_empty() || line.starts_with('#') || line.starts_with('[') {
            continue;
        }
        tokens.extend(line.split_whitespace().map(str::to_owned));
    }

    let row_width = 1 + 16 * 2; // 33 tokens: f + 16 complex pairs
    if tokens.is_empty() || tokens.len() % row_width != 0 {
        return Err(CascadeError::TooFewSamples);
    }

    let count = tokens.len() / row_width;
    let mut frequencies = Vec::with_capacity(count);
    let mut samples = Vec::with_capacity(count);

    let zero = Complex64::try_new(0.0, 0.0).map_err(|_| CascadeError::NonFiniteCalculation)?;

    for chunk in tokens.chunks_exact(row_width) {
        let f_val = chunk[0]
            .parse::<f64>()
            .map_err(|_| CascadeError::NonFiniteCalculation)?
            * freq_unit;
        if !f_val.is_finite() || f_val < 0.0 {
            return Err(CascadeError::NonFiniteCalculation);
        }
        let freq = Hertz::try_new(f_val).map_err(|_| CascadeError::NonFiniteCalculation)?;

        let mut mat = [[zero; 4]; 4];
        for row in 0..4 {
            for col in 0..4 {
                let idx = 1 + (row * 4 + col) * 2;
                let val1 = chunk[idx]
                    .parse::<f64>()
                    .map_err(|_| CascadeError::NonFiniteCalculation)?;
                let val2 = chunk[idx + 1]
                    .parse::<f64>()
                    .map_err(|_| CascadeError::NonFiniteCalculation)?;
                mat[row][col] = parse_touchstone_complex(val1, val2, format)?;
            }
        }
        frequencies.push(freq);
        samples.push(FourPortS::new(mat));
    }

    if frequencies.len() < 2 {
        return Err(CascadeError::TooFewSamples);
    }
    for window in frequencies.windows(2) {
        if window[1].get() <= window[0].get() {
            return Err(CascadeError::NonIncreasingFrequency);
        }
    }

    Ok((ref_z, frequencies, samples))
}

/// Differential pair definition consisting of positive and negative 0-indexed port indices.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct DifferentialPair {
    pub plus: usize,
    pub minus: usize,
}

impl DifferentialPair {
    pub const fn new(plus: usize, minus: usize) -> Self {
        Self { plus, minus }
    }
}

/// Parse an arbitrary N-port Touchstone file into reference impedance, frequency vector,
/// and flat N*N Complex64 matrices per frequency sample.
pub fn parse_touchstone_nport(
    text: &str,
    num_ports: usize,
) -> Result<(Ohms, Vec<Hertz>, Vec<Vec<Complex64>>), CascadeError> {
    if num_ports == 0 {
        return Err(CascadeError::InvalidPortIndex);
    }
    let (freq_unit, format, z0) = parse_touchstone_options(text)?;
    let ref_z = Ohms::try_new(z0).map_err(|_| CascadeError::NonPositiveImpedance)?;

    let mut tokens = Vec::new();
    for line in text.lines() {
        let line = line.split('!').next().unwrap_or("").trim();
        if line.is_empty() || line.starts_with('#') || line.starts_with('[') {
            continue;
        }
        tokens.extend(line.split_whitespace().map(str::to_owned));
    }

    let entries_per_point = num_ports * num_ports;
    let row_width = 1 + entries_per_point * 2;
    if tokens.is_empty() || tokens.len() % row_width != 0 {
        return Err(CascadeError::TooFewSamples);
    }

    let count = tokens.len() / row_width;
    let mut frequencies = Vec::with_capacity(count);
    let mut samples = Vec::with_capacity(count);

    for chunk in tokens.chunks_exact(row_width) {
        let f_val = chunk[0]
            .parse::<f64>()
            .map_err(|_| CascadeError::NonFiniteCalculation)?
            * freq_unit;
        if !f_val.is_finite() || f_val < 0.0 {
            return Err(CascadeError::NonFiniteCalculation);
        }
        let freq = Hertz::try_new(f_val).map_err(|_| CascadeError::NonFiniteCalculation)?;

        let mut mat = Vec::with_capacity(entries_per_point);
        for i in 0..entries_per_point {
            let idx = 1 + i * 2;
            let val1 = chunk[idx]
                .parse::<f64>()
                .map_err(|_| CascadeError::NonFiniteCalculation)?;
            let val2 = chunk[idx + 1]
                .parse::<f64>()
                .map_err(|_| CascadeError::NonFiniteCalculation)?;
            mat.push(parse_touchstone_complex(val1, val2, format)?);
        }
        frequencies.push(freq);
        samples.push(mat);
    }

    if frequencies.len() < 2 {
        return Err(CascadeError::TooFewSamples);
    }
    for window in frequencies.windows(2) {
        if window[1].get() <= window[0].get() {
            return Err(CascadeError::NonIncreasingFrequency);
        }
    }

    Ok((ref_z, frequencies, samples))
}

/// Extract a 2-port differential spectrum (Sdd) from an N-port dataset given
/// an input differential pair and an output differential pair.
pub fn extract_differential_two_port_from_nport(
    name: impl Into<String>,
    num_ports: usize,
    samples: &[Vec<Complex64>],
    frequencies: &[Hertz],
    ref_z: Ohms,
    input_pair: DifferentialPair,
    output_pair: DifferentialPair,
) -> Result<TwoPortSpectrumV1, CascadeError> {
    if input_pair.plus >= num_ports
        || input_pair.minus >= num_ports
        || output_pair.plus >= num_ports
        || output_pair.minus >= num_ports
    {
        return Err(CascadeError::InvalidPortIndex);
    }
    if input_pair.plus == input_pair.minus || output_pair.plus == output_pair.minus {
        return Err(CascadeError::DuplicatePortIndex);
    }

    let mut two_port_samples = Vec::with_capacity(samples.len());

    let p1 = input_pair.plus;
    let p2 = input_pair.minus;
    let p3 = output_pair.plus;
    let p4 = output_pair.minus;

    for mat in samples {
        if mat.len() != num_ports * num_ports {
            return Err(CascadeError::TooFewSamples);
        }
        let s = |row: usize, col: usize| -> Complex<f64> {
            let c = mat[row * num_ports + col];
            Complex::new(c.real(), c.imaginary())
        };

        // Mixed-mode Sdd modal transformation
        let sdd11 = (s(p1, p1) - s(p1, p2) - s(p2, p1) + s(p2, p2)) * 0.5;
        let sdd12 = (s(p1, p3) - s(p1, p4) - s(p2, p3) + s(p2, p4)) * 0.5;
        let sdd21 = (s(p3, p1) - s(p3, p2) - s(p4, p1) + s(p4, p2)) * 0.5;
        let sdd22 = (s(p3, p3) - s(p3, p4) - s(p4, p3) + s(p4, p4)) * 0.5;

        let to_c64 = |c: Complex<f64>| -> Result<Complex64, CascadeError> {
            Complex64::try_new(c.re, c.im).map_err(|_| CascadeError::NonFiniteCalculation)
        };

        two_port_samples.push(TwoPortS {
            s11: to_c64(sdd11)?,
            s12: to_c64(sdd12)?,
            s21: to_c64(sdd21)?,
            s22: to_c64(sdd22)?,
        });
    }

    TwoPortSpectrumV1::try_new(name, ref_z, frequencies.to_vec(), two_port_samples)
}

/// Create an analytic coupled crosstalk network (FEXT or NEXT model)
/// where coupling is proportional to coupling coefficient k_x and delay tau.
pub fn create_analytic_coupled_crosstalk_network(
    frequencies: &[Hertz],
    ref_z: Ohms,
    coupling_coeff: f64,
    tau_seconds: f64,
    is_next: bool,
) -> Result<TwoPortSpectrumV1, CascadeError> {
    if !coupling_coeff.is_finite() || !tau_seconds.is_finite() || tau_seconds < 0.0 {
        return Err(CascadeError::NonFiniteCalculation);
    }
    let zero = Complex64::try_new(0.0, 0.0).map_err(|_| CascadeError::NonFiniteCalculation)?;

    let mut samples = Vec::with_capacity(frequencies.len());
    for &freq in frequencies {
        let f = freq.get();
        let omega = 2.0 * std::f64::consts::PI * f;

        let s21_val = if is_next {
            let phase = Complex::new(0.0, -2.0 * omega * tau_seconds).exp();
            let c = Complex::new(coupling_coeff, 0.0) * (Complex::new(1.0, 0.0) - phase) * 0.5;
            Complex64::try_new(c.re, c.im).map_err(|_| CascadeError::NonFiniteCalculation)?
        } else {
            let phase = Complex::new(0.0, -omega * tau_seconds).exp();
            let c = Complex::new(0.0, omega * coupling_coeff * 1e-9) * phase;
            Complex64::try_new(c.re, c.im).map_err(|_| CascadeError::NonFiniteCalculation)?
        };

        samples.push(TwoPortS {
            s11: zero,
            s12: s21_val,
            s21: s21_val,
            s22: zero,
        });
    }

    TwoPortSpectrumV1::try_new("analytic-crosstalk", ref_z, frequencies.to_vec(), samples)
}

#[cfg(test)]
mod tests {
    use super::*;
    use sipi_types::{Hertz, Ohms, Seconds};

    fn make_grid(count: usize, step_hz: f64) -> Vec<Hertz> {
        (0..count)
            .map(|i| Hertz::try_new(i as f64 * step_hz).unwrap())
            .collect()
    }

    /// A 1 Hz grid step with a 1 ps target interval asks for 1e12 complex bins.
    /// The bounded conversion must fail closed before attempting the
    /// allocation instead of exhausting memory.
    #[test]
    fn test_discrete_kernel_rejects_an_unbounded_fft_length() {
        let grid = make_grid(2, 1.0);
        let transfer = vec![Complex::new(1.0, 0.0); grid.len()];
        assert_eq!(
            spectrum_to_discrete_kernel(
                &grid,
                &transfer,
                Seconds::try_new(1.0e-12).unwrap(),
                false,
                None,
            )
            .unwrap_err(),
            CascadeError::FftLengthOverflow
        );
    }

    #[test]
    fn test_analytic_thru_identity() {
        let grid = make_grid(100, 100.0e6);
        let z0 = Ohms::try_new(50.0).unwrap();
        let thru = create_analytic_thru_network(&grid, z0).unwrap();

        let passivity = evaluate_sampled_passivity(&thru).unwrap();
        assert!(passivity.passes_bound);
        assert!((passivity.maximum_singular_value - 1.0).abs() < 1e-12);

        let reciprocity = evaluate_sampled_reciprocity(&thru).unwrap();
        assert!(reciprocity.passes_bound);
        assert_eq!(reciprocity.maximum_difference, 0.0);

        let term = TerminationParamsV1::new(z0, 0.0).unwrap();
        let transfer = calculate_loaded_voltage_transfer(&thru, term, term).unwrap();
        for h in transfer {
            assert!((h.re - 1.0).abs() < 1e-12);
            assert!(h.im.abs() < 1e-12);
        }
    }

    #[test]
    fn test_analytic_delay_cascade_addition() {
        let grid = make_grid(100, 100.0e6);
        let z0 = Ohms::try_new(50.0).unwrap();
        let tau1 = 100.0e-12;
        let tau2 = 250.0e-12;

        let delay1 = create_analytic_delay_network(&grid, z0, tau1).unwrap();
        let delay2 = create_analytic_delay_network(&grid, z0, tau2).unwrap();

        let cascaded = cascade_network_stages("cascade_delays", &[delay1, delay2]).unwrap();
        let expected_tau = tau1 + tau2;

        for (i, (&f, sample)) in grid.iter().zip(cascaded.samples()).enumerate() {
            let omega = 2.0 * std::f64::consts::PI * f.get();
            let phase = -omega * expected_tau;
            let expected = Complex::new(phase.cos(), phase.sin());
            let actual = Complex::new(sample.s21.real(), sample.s21.imaginary());
            assert!(
                (actual - expected).norm() < 1e-12,
                "mismatch at index {i}: actual={actual:?}, expected={expected:?}"
            );
        }
    }

    #[test]
    fn test_uncoupled_four_port_reduces_to_two_port() {
        let _zero = Complex64::try_new(0.0, 0.0).unwrap();
        let s11 = Complex64::try_new(0.1, 0.05).unwrap();
        let s21 = Complex64::try_new(0.8, -0.2).unwrap();
        let line = TwoPortS {
            s11,
            s12: s21,
            s21,
            s22: s11,
        };

        let four_port = create_analytic_uncoupled_four_port(line).unwrap();

        // Standard Touchstone mapping: 1=TX+, 2=RX+, 3=TX-, 4=RX-
        let sdd = four_port_to_differential_two_port(
            four_port,
            PortMapV1::TxPlusRxPlusTxMinusRxMinus,
        )
        .unwrap();

        assert!((sdd.s11.real() - line.s11.real()).abs() < 1e-12);
        assert!((sdd.s11.imaginary() - line.s11.imaginary()).abs() < 1e-12);
        assert!((sdd.s21.real() - line.s21.real()).abs() < 1e-12);
        assert!((sdd.s21.imaginary() - line.s21.imaginary()).abs() < 1e-12);

        let diag = analyze_mixed_mode_components(
            four_port,
            PortMapV1::TxPlusRxPlusTxMinusRxMinus,
        )
        .unwrap();

        // Cross-mode coupling must be zero for uncoupled lines
        assert!(diag.scd21_mag < 1e-12);
        assert!(diag.sdc21_mag < 1e-12);
        assert!(diag.mode_conversion_ratio < 1e-12);
    }

    #[test]
    fn test_mismatched_line_and_loaded_transfer() {
        let grid = make_grid(513, 125.0e6); // 0 to 64 GHz
        let z0 = Ohms::try_new(50.0).unwrap();
        let zc = 75.0; // 75 ohm line in 50 ohm system
        let v = 2.0e8;
        let length = 0.05; // 5 cm

        let line = create_analytic_mismatched_line_network(&grid, z0, zc, v, length).unwrap();
        let passivity = evaluate_sampled_passivity(&line).unwrap();
        assert!(passivity.passes_bound);

        let term_matched = TerminationParamsV1::new(z0, 0.0).unwrap();
        let transfer_matched = calculate_loaded_voltage_transfer(&line, term_matched, term_matched).unwrap();

        // DC transfer for matched line in 50 ohm system with 75 ohm line is 1.0 (since line DC resistance is 0)
        assert!((transfer_matched[0].re - 1.0).abs() < 1e-12);
        assert!(transfer_matched[0].im.abs() < 1e-12);

        // Mismatched load: Rs = 50, Rl = 100
        let rl = Ohms::try_new(100.0).unwrap();
        let term_load = TerminationParamsV1::new(rl, 0.0).unwrap();
        let transfer_mismatch = calculate_loaded_voltage_transfer(&line, term_matched, term_load).unwrap();

        // At DC, voltage divider: Vload / Vhalf_open = 2 * Rl / (Rs + Rl) = 2 * 100 / 150 = 4/3 = 1.3333333333333333
        let expected_dc = 2.0 * 100.0 / (50.0 + 100.0);
        assert!((transfer_mismatch[0].re - expected_dc).abs() < 1e-12);
    }

    #[test]
    fn test_fd_to_td_kernel_delay_peak() {
        let dt = Seconds::try_new(1.953125e-12).unwrap(); // 512 GHz Nyquist (dt = 1.953125 ps)
        let df = 125.0e6; // 125 MHz
        let n_bins = 2049; // 0 to 256 GHz
        let grid = make_grid(n_bins, df);
        let z0 = Ohms::try_new(50.0).unwrap();
        let tau = 250.0e-12; // 250 ps delay -> 250ps / 1.953125ps = 128 samples

        let delay = create_analytic_delay_network(&grid, z0, tau).unwrap();
        let term = TerminationParamsV1::new(z0, 0.0).unwrap();
        let transfer = calculate_loaded_voltage_transfer(&delay, term, term).unwrap();

        let (kernel, metrics) = spectrum_to_discrete_kernel(
            &grid,
            &transfer,
            dt,
            false, // no window
            None,
        )
        .unwrap();

        assert_eq!(metrics.peak_index, 128);
        assert!((metrics.peak_time_s - tau).abs() < 1e-14);
        assert!(kernel[128] > 0.99); // near unity impulse
    }

    #[test]
    fn test_parse_touchstone_2port_formats() {
        let s2p_ri = "# GHz S RI R 50\n\
                      0.0  0.0 0.0  1.0 0.0  1.0 0.0  0.0 0.0\n\
                      1.0  0.0 0.0  0.0 -1.0 0.0 -1.0 0.0 0.0\n";
        let net_ri = parse_touchstone_2port(s2p_ri, "test_ri").unwrap();
        assert_eq!(net_ri.frequencies().len(), 2);
        assert_eq!(net_ri.reference_impedance().get(), 50.0);
        assert_eq!(net_ri.samples()[0].s21.real(), 1.0);
        assert_eq!(net_ri.samples()[0].s21.imaginary(), 0.0);
        assert_eq!(net_ri.samples()[1].s21.real(), 0.0);
        assert_eq!(net_ri.samples()[1].s21.imaginary(), -1.0);

        let s2p_db = "# MHz S DB R 75\n\
                      ! comment line\n\
                      100  0 0  -6 90  -6 90  0 0\n\
                      200  0 0  -20 180 -20 180 0 0\n";
        let net_db = parse_touchstone_2port(s2p_db, "test_db").unwrap();
        assert_eq!(net_db.frequencies().len(), 2);
        assert_eq!(net_db.reference_impedance().get(), 75.0);
        assert_eq!(net_db.frequencies()[0].get(), 100.0e6);
        assert_eq!(net_db.frequencies()[1].get(), 200.0e6);
        // -6 dB approx 0.501187, 90 deg -> real near 0, imag near 0.501187
        assert!((net_db.samples()[0].s21.real()).abs() < 1e-6);
        assert!((net_db.samples()[0].s21.imaginary() - 0.501187).abs() < 1e-4);
    }

    #[test]
    fn test_full_cascade_tx_fixture_channel_s4p_rx_fixture() {
        // Construct a representative 3-stage cascade:
        // Stage 1: TX package/fixture (small delay 20 ps + slight loss)
        // Stage 2: Channel S4P (differential pair line with 200 ps delay, 75 ohm diff)
        // Stage 3: RX package/fixture (small delay 30 ps + slight loss)
        let dt = Seconds::try_new(1.953125e-12).unwrap();
        let df = 125.0e6;
        let n_bins = 2049;
        let grid = make_grid(n_bins, df);
        let z0 = Ohms::try_new(50.0).unwrap();

        // Stage 1: TX fixture (20 ps delay)
        let tx_fixture = create_analytic_delay_network(&grid, z0, 20.0e-12).unwrap();

        // Stage 2: Channel (represented as uncoupled 4-port, 200 ps delay)
        let zero = Complex64::try_new(0.0, 0.0).unwrap();
        let mut channel_2port_samples = Vec::with_capacity(n_bins);
        for &freq in &grid {
            let omega = 2.0 * std::f64::consts::PI * freq.get();
            let phase = -omega * 200.0e-12;
            let trans = Complex64::try_new(phase.cos(), phase.sin()).unwrap();
            channel_2port_samples.push(TwoPortS {
                s11: zero,
                s12: trans,
                s21: trans,
                s22: zero,
            });
        }
        let channel_2port = TwoPortSpectrumV1::try_new("channel_2port", z0, grid.clone(), channel_2port_samples).unwrap();

        // Stage 3: RX fixture (30 ps delay)
        let rx_fixture = create_analytic_delay_network(&grid, z0, 30.0e-12).unwrap();

        // Full cascade
        let total_network = cascade_network_stages(
            "total_link",
            &[tx_fixture, channel_2port, rx_fixture],
        )
        .unwrap();

        assert_eq!(total_network.samples().len(), n_bins);

        // Total delay = 20 ps + 200 ps + 30 ps = 250 ps
        // 250 ps / 1.953125 ps = exactly 128 sample points!
        let term = TerminationParamsV1::new(z0, 0.0).unwrap();
        let transfer = calculate_loaded_voltage_transfer(&total_network, term, term).unwrap();

        let (kernel, metrics) = spectrum_to_discrete_kernel(
            &grid,
            &transfer,
            dt,
            false,
            None,
        )
        .unwrap();

        assert_eq!(metrics.peak_index, 128);
        assert!((metrics.peak_time_s - 250.0e-12).abs() < 1e-14);
        assert!(kernel[128] > 0.99);
    }

    #[test]
    fn test_parse_touchstone_nport_8port_and_crosstalk_extraction() {
        // Generate an S8P Touchstone text with 2 frequency points
        // 8 ports -> 64 complex pairs -> 128 values per row
        let mut s8p_text = String::from("# GHz S RI R 50\n");
        for f_ghz in [1.0, 2.0] {
            s8p_text.push_str(&format!("{f_ghz:.1}"));
            for row in 0..8 {
                for col in 0..8 {
                    // Put a small non-zero coupling between port 4 and port 1 (aggressor to victim)
                    if (row == 1 && col == 4) || (row == 4 && col == 1) {
                        s8p_text.push_str(" 0.05 0.01");
                    } else if row == col {
                        s8p_text.push_str(" 0.00 0.00");
                    } else if (row == 1 && col == 0) || (row == 0 && col == 1) {
                        s8p_text.push_str(" 0.90 0.00");
                    } else {
                        s8p_text.push_str(" 0.00 0.00");
                    }
                }
            }
            s8p_text.push('\n');
        }

        let (z0, freqs, samples) = parse_touchstone_nport(&s8p_text, 8).unwrap();
        assert_eq!(z0.get(), 50.0);
        assert_eq!(freqs.len(), 2);
        assert_eq!(samples.len(), 2);
        assert_eq!(samples[0].len(), 64);

        // Extract victim pair: input pair [0, 2], output pair [1, 3]
        let vic_in = DifferentialPair::new(0, 2);
        let vic_out = DifferentialPair::new(1, 3);
        let victim_sdd = extract_differential_two_port_from_nport(
            "victim-thru",
            8,
            &samples,
            &freqs,
            z0,
            vic_in,
            vic_out,
        )
        .unwrap();
        assert_eq!(victim_sdd.samples().len(), 2);
        assert!((victim_sdd.samples()[0].s21.real() - 0.45).abs() < 1e-12);

        // Extract FEXT pair: aggressor input pair [4, 6], victim output pair [1, 3]
        let agg_in = DifferentialPair::new(4, 6);
        let fext_sdd = extract_differential_two_port_from_nport(
            "aggressor-fext",
            8,
            &samples,
            &freqs,
            z0,
            agg_in,
            vic_out,
        )
        .unwrap();
        assert_eq!(fext_sdd.samples().len(), 2);
        assert!((fext_sdd.samples()[0].s21.real() - 0.025).abs() < 1e-12);
    }

    #[test]
    fn test_analytic_coupled_crosstalk_network_fext_and_next() {
        let grid = make_grid(100, 100.0e6);
        let z0 = Ohms::try_new(50.0).unwrap();

        let fext = create_analytic_coupled_crosstalk_network(&grid, z0, 0.05, 200.0e-12, false).unwrap();
        assert_eq!(fext.samples().len(), 100);
        // At DC (f=0), FEXT is zero
        assert_eq!(fext.samples()[0].s21.real(), 0.0);
        assert_eq!(fext.samples()[0].s21.imaginary(), 0.0);
        // At high frequency, FEXT magnitude increases
        assert!(fext.samples()[99].s21.imaginary().abs() > 0.0);

        let next = create_analytic_coupled_crosstalk_network(&grid, z0, 0.08, 200.0e-12, true).unwrap();
        assert_eq!(next.samples().len(), 100);
        // At DC (f=0), NEXT is zero
        assert_eq!(next.samples()[0].s21.real(), 0.0);
        assert_eq!(next.samples()[0].s21.imaginary(), 0.0);
    }
}
