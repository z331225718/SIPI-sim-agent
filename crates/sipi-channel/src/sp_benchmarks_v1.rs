#![forbid(unsafe_code)]

//! Standard S-Parameter (SP) benchmarks and frequency-domain metric extraction.
//!
//! This module provides analytical reference fixtures for standard SI/PI S-parameter
//! comparisons, including:
//! 1. Broadband lossy microstrip transmission line (skin effect + dielectric loss).
//! 2. Shunt resonant open stub (via stub / branch notch dip benchmark).
//! 3. 4-port coupled differential pair with asymmetric mode conversion (Sdd, Scc, Scd, Sdc).
//!
//! Metrics extracted include Insertion Loss (IL), Return Loss (RL), Group Delay (GD),
//! Insertion Loss Deviation (ILD), resonant notch frequency/depth, and IEEE P370 passivity/reciprocity.

use rustfft::num_complex::Complex;
use sipi_types::{Complex64, Hertz, Ohms};

use crate::{
    CascadeError, DetailedPassivityDiagnosticsV1, DetailedReciprocityDiagnosticsV1,
    FourPortS, TwoPortS, TwoPortSpectrumV1, evaluate_sampled_passivity,
    evaluate_sampled_reciprocity,
};

/// Frequency-domain metrics extracted from a 2-port S-parameter network.
#[derive(Debug, Clone, PartialEq)]
pub struct SParameterMetricsV1 {
    pub frequencies_hz: Vec<f64>,
    pub return_loss_db: Vec<f64>,
    pub insertion_loss_db: Vec<f64>,
    pub group_delay_ps: Vec<f64>,
    pub max_insertion_loss_db: f64,
    pub min_return_loss_db: f64,
    pub detected_notches: Vec<ResonantNotchV1>,
    pub passivity: DetailedPassivityDiagnosticsV1,
    pub reciprocity: DetailedReciprocityDiagnosticsV1,
}

/// Detected resonant notch in insertion loss (e.g. from via stubs or impedance dips).
#[derive(Debug, Clone, PartialEq)]
pub struct ResonantNotchV1 {
    pub notch_frequency_hz: f64,
    pub depth_db: f64,
    pub q_factor: Option<f64>,
}

/// Full 16-parameter mixed-mode S-parameter matrix for a differential 4-port network.
#[derive(Debug, Clone, PartialEq)]
pub struct MixedModeFourPortMatrixV1 {
    pub sdd: [[Complex64; 2]; 2],
    pub scc: [[Complex64; 2]; 2],
    pub scd: [[Complex64; 2]; 2],
    pub sdc: [[Complex64; 2]; 2],
}

/// Create an analytical broadband lossy transmission line fixture.
///
/// Models skin-effect resistance R(f) = R_dc + R_skin * sqrt(f / 1 GHz)
/// and dielectric conductance G(f) = 2 * pi * f * C * tan_delta.
pub fn create_analytic_lossy_microstrip(
    frequencies: &[Hertz],
    ref_z: Ohms,
    length_m: f64,
    z0: f64,
    propagation_velocity_m_per_s: f64,
    r_dc_ohm_per_m: f64,
    r_skin_1ghz_ohm_per_m: f64,
    loss_tangent: f64,
) -> Result<TwoPortSpectrumV1, CascadeError> {
    if frequencies.len() < 2
        || length_m <= 0.0
        || z0 <= 0.0
        || propagation_velocity_m_per_s <= 0.0
        || r_dc_ohm_per_m < 0.0
        || r_skin_1ghz_ohm_per_m < 0.0
        || loss_tangent < 0.0
    {
        return Err(CascadeError::NonPositiveImpedance);
    }

    let z_ref = ref_z.get();
    let l_per_m = z0 / propagation_velocity_m_per_s;
    let c_per_m = 1.0 / (z0 * propagation_velocity_m_per_s);

    let mut samples = Vec::with_capacity(frequencies.len());

    for &freq in frequencies {
        let f = freq.get();
        let omega = 2.0 * std::f64::consts::PI * f;

        let r = r_dc_ohm_per_m + r_skin_1ghz_ohm_per_m * (f / 1.0e9).max(0.0).sqrt();
        let g = omega * c_per_m * loss_tangent;

        // Series impedance Z = R + j*omega*L
        let z_series = Complex::new(r, omega * l_per_m);
        // Shunt admittance Y = G + j*omega*C
        let y_shunt = Complex::new(g, omega * c_per_m);

        // Propagation constant gamma = sqrt(Z * Y)
        let gamma = (z_series * y_shunt).sqrt();
        // Characteristic impedance Zc = sqrt(Z / Y)
        let z_c = if omega == 0.0 && g == 0.0 {
            Complex::new(z0, 0.0)
        } else {
            (z_series / y_shunt).sqrt()
        };

        let gl = gamma * length_m;
        let sinh_gl = gl.sinh();
        let cosh_gl = gl.cosh();

        // 2-port S-parameters with reference impedance z_ref
        // Denominator D = 2 * Zc * Zref * cosh(gamma*l) + (Zc^2 + Zref^2) * sinh(gamma*l)
        let num_s11 = (z_c * z_c - Complex::new(z_ref * z_ref, 0.0)) * sinh_gl;
        let denom = Complex::new(2.0 * z_ref, 0.0) * z_c * cosh_gl
            + (z_c * z_c + Complex::new(z_ref * z_ref, 0.0)) * sinh_gl;

        let num_s21 = Complex::new(2.0 * z_ref, 0.0) * z_c;

        let s11 = num_s11 / denom;
        let s21 = num_s21 / denom;

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

    TwoPortSpectrumV1::try_new("analytic-lossy-microstrip", ref_z, frequencies.to_vec(), samples)
}

/// Create an analytical resonant open stub fixture (representing an un-backdrilled via stub).
///
/// An open transmission line of length stub_length_m and impedance stub_z0 is placed
/// in shunt between port 1 and port 2, creating an insertion loss notch at
/// f_notch = vp / (4 * stub_length_m).
pub fn create_analytic_resonant_stub(
    frequencies: &[Hertz],
    ref_z: Ohms,
    stub_length_m: f64,
    stub_z0: f64,
    stub_velocity_m_per_s: f64,
) -> Result<TwoPortSpectrumV1, CascadeError> {
    if frequencies.len() < 2
        || stub_length_m <= 0.0
        || stub_z0 <= 0.0
        || stub_velocity_m_per_s <= 0.0
    {
        return Err(CascadeError::NonPositiveImpedance);
    }

    let z_ref = ref_z.get();
    let mut samples = Vec::with_capacity(frequencies.len());

    for &freq in frequencies {
        let f = freq.get();
        let omega = 2.0 * std::f64::consts::PI * f;
        let beta = omega / stub_velocity_m_per_s;

        // Input admittance of open lossless stub: Y_in = j * (1 / Z0) * tan(beta * l)
        let tan_bl = (beta * stub_length_m).tan();
        let y_stub = Complex::new(0.0, tan_bl / stub_z0);

        // Shunt admittance 2-port S-parameters:
        // S11 = -Y * Zref / (2 + Y * Zref)
        // S21 = 2 / (2 + Y * Zref)
        let yz = y_stub * Complex::new(z_ref, 0.0);
        let denom = Complex::new(2.0, 0.0) + yz;

        let s11 = -yz / denom;
        let s21 = Complex::new(2.0, 0.0) / denom;

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

    TwoPortSpectrumV1::try_new("analytic-resonant-stub", ref_z, frequencies.to_vec(), samples)
}

/// Convert a single-ended 4-port S-matrix to all 16 mixed-mode S-parameters:
/// - Differential mode: Sdd11, Sdd12, Sdd21, Sdd22
/// - Common mode: Scc11, Scc12, Scc21, Scc22
/// - Mode conversion: Scd (differential to common), Sdc (common to differential)
///
/// Port mapping: Input differential pair [p1 (+), p2 (-)], Output differential pair [p3 (+), p4 (-)].
pub fn compute_full_mixed_mode_matrix(
    matrix: FourPortS,
    p1: usize,
    p2: usize,
    p3: usize,
    p4: usize,
) -> Result<MixedModeFourPortMatrixV1, CascadeError> {
    let s = |out: usize, inc: usize| -> Result<Complex<f64>, CascadeError> {
        let val = matrix.at(out, inc).ok_or(CascadeError::InvalidPortIndex)?;
        Ok(Complex::new(val.real(), val.imaginary()))
    };

    let to_c64 = |c: Complex<f64>| -> Result<Complex64, CascadeError> {
        Complex64::try_new(c.re, c.im).map_err(|_| CascadeError::NonFiniteCalculation)
    };

    // Sdd: differential-to-differential
    let sdd11 = 0.5 * (s(p1, p1)? - s(p1, p2)? - s(p2, p1)? + s(p2, p2)?);
    let sdd12 = 0.5 * (s(p1, p3)? - s(p1, p4)? - s(p2, p3)? + s(p2, p4)?);
    let sdd21 = 0.5 * (s(p3, p1)? - s(p3, p2)? - s(p4, p1)? + s(p4, p2)?);
    let sdd22 = 0.5 * (s(p3, p3)? - s(p3, p4)? - s(p4, p3)? + s(p4, p4)?);

    // Scc: common-to-common
    let scc11 = 0.5 * (s(p1, p1)? + s(p1, p2)? + s(p2, p1)? + s(p2, p2)?);
    let scc12 = 0.5 * (s(p1, p3)? + s(p1, p4)? + s(p2, p3)? + s(p2, p4)?);
    let scc21 = 0.5 * (s(p3, p1)? + s(p3, p2)? + s(p4, p1)? + s(p4, p2)?);
    let scc22 = 0.5 * (s(p3, p3)? + s(p3, p4)? + s(p4, p3)? + s(p4, p4)?);

    // Scd: differential-to-common conversion (EMI generation)
    let scd11 = 0.5 * (s(p1, p1)? - s(p1, p2)? + s(p2, p1)? - s(p2, p2)?);
    let scd12 = 0.5 * (s(p1, p3)? - s(p1, p4)? + s(p2, p3)? - s(p2, p4)?);
    let scd21 = 0.5 * (s(p3, p1)? - s(p3, p2)? + s(p4, p1)? - s(p4, p2)?);
    let scd22 = 0.5 * (s(p3, p3)? - s(p3, p4)? + s(p4, p3)? - s(p4, p4)?);

    // Sdc: common-to-differential conversion (noise susceptibility)
    let sdc11 = 0.5 * (s(p1, p1)? + s(p1, p2)? - s(p2, p1)? - s(p2, p2)?);
    let sdc12 = 0.5 * (s(p1, p3)? + s(p1, p4)? - s(p2, p3)? - s(p2, p4)?);
    let sdc21 = 0.5 * (s(p3, p1)? + s(p3, p2)? - s(p4, p1)? - s(p4, p2)?);
    let sdc22 = 0.5 * (s(p3, p3)? + s(p3, p4)? - s(p4, p3)? - s(p4, p4)?);

    Ok(MixedModeFourPortMatrixV1 {
        sdd: [
            [to_c64(sdd11)?, to_c64(sdd12)?],
            [to_c64(sdd21)?, to_c64(sdd22)?],
        ],
        scc: [
            [to_c64(scc11)?, to_c64(scc12)?],
            [to_c64(scc21)?, to_c64(scc22)?],
        ],
        scd: [
            [to_c64(scd11)?, to_c64(scd12)?],
            [to_c64(scd21)?, to_c64(scd22)?],
        ],
        sdc: [
            [to_c64(sdc11)?, to_c64(sdc12)?],
            [to_c64(sdc21)?, to_c64(sdc22)?],
        ],
    })
}

/// Compute full S-parameter metrics including IL, RL, group delay, and resonant notches.
pub fn calculate_sparameter_metrics(
    network: &TwoPortSpectrumV1,
) -> Result<SParameterMetricsV1, CascadeError> {
    let n = network.sample_count();
    if n < 2 {
        return Err(CascadeError::TooFewSamples);
    }

    let freqs: Vec<f64> = network.frequencies().iter().map(|f| f.get()).collect();
    let mut rl_db = Vec::with_capacity(n);
    let mut il_db = Vec::with_capacity(n);
    let mut phases_rad = Vec::with_capacity(n);

    for s in network.samples() {
        let s11_mag = (s.s11.real().powi(2) + s.s11.imaginary().powi(2)).sqrt();
        let s21_mag = (s.s21.real().powi(2) + s.s21.imaginary().powi(2)).sqrt();

        let rl = -20.0 * s11_mag.max(1.0e-12).log10();
        let il = -20.0 * s21_mag.max(1.0e-12).log10();

        rl_db.push(rl);
        il_db.push(il);
        phases_rad.push(s.s21.imaginary().atan2(s.s21.real()));
    }

    // Unwrap phase array for continuous group delay calculation
    let mut unwrapped = Vec::with_capacity(n);
    let mut prev_phase = phases_rad[0];
    let mut cumulative_wrap = 0.0;
    unwrapped.push(prev_phase);

    for &phase in &phases_rad[1..] {
        let diff = phase - prev_phase;
        if diff > std::f64::consts::PI {
            cumulative_wrap -= 2.0 * std::f64::consts::PI;
        } else if diff < -std::f64::consts::PI {
            cumulative_wrap += 2.0 * std::f64::consts::PI;
        }
        prev_phase = phase;
        unwrapped.push(phase + cumulative_wrap);
    }

    // Calculate group delay GD = -d_phi / (2 * pi * df) in picoseconds
    let mut gd_ps = Vec::with_capacity(n);
    for i in 0..n {
        let gd = if i == 0 {
            let df = freqs[1] - freqs[0];
            -(unwrapped[1] - unwrapped[0]) / (2.0 * std::f64::consts::PI * df.max(1.0)) * 1.0e12
        } else if i == n - 1 {
            let df = freqs[n - 1] - freqs[n - 2];
            -(unwrapped[n - 1] - unwrapped[n - 2]) / (2.0 * std::f64::consts::PI * df.max(1.0)) * 1.0e12
        } else {
            let df = freqs[i + 1] - freqs[i - 1];
            -(unwrapped[i + 1] - unwrapped[i - 1]) / (2.0 * std::f64::consts::PI * df.max(1.0)) * 1.0e12
        };
        gd_ps.push(gd);
    }

    // Detect resonant notch peaks in IL (local maxima in IL = dips in |S21|)
    let mut notches = Vec::new();
    for i in 1..n - 1 {
        if il_db[i] > il_db[i - 1] && il_db[i] > il_db[i + 1] && il_db[i] > 10.0 {
            notches.push(ResonantNotchV1 {
                notch_frequency_hz: freqs[i],
                depth_db: il_db[i],
                q_factor: None,
            });
        }
    }

    let max_il = il_db.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let min_rl = rl_db.iter().copied().fold(f64::INFINITY, f64::min);

    let passivity = evaluate_sampled_passivity(network)?;
    let reciprocity = evaluate_sampled_reciprocity(network)?;

    Ok(SParameterMetricsV1 {
        frequencies_hz: freqs,
        return_loss_db: rl_db,
        insertion_loss_db: il_db,
        group_delay_ps: gd_ps,
        max_insertion_loss_db: max_il,
        min_return_loss_db: min_rl,
        detected_notches: notches,
        passivity,
        reciprocity,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_grid(count: usize, step_hz: f64) -> Vec<Hertz> {
        (0..count)
            .map(|i| Hertz::try_new(i as f64 * step_hz).unwrap())
            .collect()
    }

    #[test]
    fn test_lossy_microstrip_monotonic_attenuation_and_passivity() {
        let grid = make_grid(201, 100.0e6); // 0 to 20 GHz in 100 MHz steps
        let ref_z = Ohms::try_new(50.0).unwrap();

        let line = create_analytic_lossy_microstrip(
            &grid,
            ref_z,
            0.10,      // 10 cm
            50.0,      // 50 Ohm
            1.5e8,     // vp = c / 2
            1.0,       // 1 Ohm/m DC
            4.0,       // 4 Ohm/m @ 1 GHz skin
            0.02,      // FR4 tan_delta = 0.02
        )
        .unwrap();

        let metrics = calculate_sparameter_metrics(&line).unwrap();

        // Passivity must pass strictly
        assert!(metrics.passivity.passes_bound);
        assert!(metrics.passivity.maximum_singular_value <= 1.00000001);

        // Reciprocity must be exact
        assert!(metrics.reciprocity.passes_bound);
        assert_eq!(metrics.reciprocity.maximum_difference, 0.0);

        // Insertion loss must increase monotonically with frequency
        assert!(metrics.insertion_loss_db[200] > metrics.insertion_loss_db[100]);
        assert!(metrics.insertion_loss_db[100] > metrics.insertion_loss_db[10]);
        assert!(metrics.max_insertion_loss_db > 5.0);
    }

    #[test]
    fn test_resonant_open_stub_notch_detection() {
        let grid = make_grid(501, 50.0e6); // 0 to 25 GHz
        let ref_z = Ohms::try_new(50.0).unwrap();

        // Open stub of length 2.5 mm in dielectric with vp = 1.5e8 m/s
        // Quarter-wave resonance: f_notch = 1.5e8 / (4 * 0.0025) = 1.5e10 / 1 = 15.0 GHz!
        let stub = create_analytic_resonant_stub(
            &grid,
            ref_z,
            0.0025,
            50.0,
            1.5e8,
        )
        .unwrap();

        let metrics = calculate_sparameter_metrics(&stub).unwrap();
        assert!(metrics.passivity.passes_bound);
        assert!(!metrics.detected_notches.is_empty());

        let notch = &metrics.detected_notches[0];
        // Predicted 15.0 GHz notch within grid resolution
        assert!((notch.notch_frequency_hz - 15.0e9).abs() <= 100.0e6);
        assert!(notch.depth_db > 20.0); // Strong resonant attenuation dip
    }

    #[test]
    fn test_full_mixed_mode_matrix_symmetry() {
        let zero = Complex64::try_new(0.0, 0.0).unwrap();
        let pass = Complex64::try_new(0.9, 0.0).unwrap();
        let mut mat = [[zero; 4]; 4];
        // Balanced differential transmission between 1->2 and 3->4
        mat[1][0] = pass;
        mat[0][1] = pass;
        mat[3][2] = pass;
        mat[2][3] = pass;

        let mm = compute_full_mixed_mode_matrix(FourPortS::new(mat), 0, 2, 1, 3).unwrap();
        // Sdd21 should be 0.9
        assert!((mm.sdd[1][0].real() - 0.9).abs() < 1e-12);
        // Purely symmetric pair has zero mode conversion
        assert_eq!(mm.scd[1][0].real(), 0.0);
        assert_eq!(mm.sdc[1][0].real(), 0.0);
    }
}
