//! Normal r4.80 S4P TDR/PTDR/ERL numerical leaf.
//!
//! This module is deliberately crate-private.  The public direct-run wire
//! remains unchanged; the caller supplies the already assembled DD network
//! from `package_vtf_v1` and receives a typed two-port result.  The numerical
//! operations follow Agent-COM's `erl/tdr.py`, `erl/metric.py`, and the
//! `get_TDR` portion of the pinned r4.80 MATLAB source.  In particular, this
//! path does not fit an S-parameter model and does not reuse the ERL-only
//! envelope.

use std::collections::BTreeMap;

use sipi_com::{
    FdToTdOptionsV1, MAX_FD_TO_TD_BINS_V1, ResolvedDefaultV1, butterworth_filter_v1,
    has_positive_unwrapped_phase_slope_v1, raised_cosine_filter_v1, rectangular_pulse_response_v1,
    s21_to_impulse_dc_v1, sampled_signal_pdf_v1,
};
use sipi_types::Complex64;

use crate::DirectRunErrorV1;
use crate::package_vtf_v1::R480TdrDdNetworkV1;

/// Numerical policy for the normal S4P TDR/ERL leaf.
pub(crate) const NORMAL_ERL_TDR_POLICY_V1: &str =
    "sipi.com-r480.normal-s4p-tdr-ptdr-erl-v1.final-fd-to-td-no-fit";

const TDR_DELAY_S: f64 = 500.0e-12;
const TDR_REFERENCE_OHM: f64 = 100.0;
const MAX_TDR_SAMPLES: usize = 2_097_152;

/// Typed controls consumed by the normal TDR/ERL leaf.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct R480NormalErlControlsV1 {
    pub(crate) tdr_enabled: bool,
    pub(crate) erl_enabled: bool,
    pub(crate) tdr_w_txpkg: bool,
    pub(crate) n_ui: f64,
    pub(crate) tdr_duration_ui: f64,
    pub(crate) tr_tdr_ns: f64,
    pub(crate) tdr_butterworth: bool,
    pub(crate) tukey_window: bool,
    pub(crate) auto_tfx: bool,
    pub(crate) t_k_s: f64,
    pub(crate) rl_norm_test: bool,
    pub(crate) spec_ber: f64,
    pub(crate) n_bx: i64,
    pub(crate) rho_x: f64,
    pub(crate) grr: i64,
    pub(crate) beta_x_db_per_s: f64,
    pub(crate) z_t_ohm: f64,
    pub(crate) fb_hz: f64,
    pub(crate) sample_dt_s: f64,
    pub(crate) samples_per_ui: usize,
    pub(crate) levels: u32,
    pub(crate) bin_size: f64,
    pub(crate) f_r: f64,
    pub(crate) fb_bw_cutoff: f64,
    pub(crate) tfx_s: [f64; 2],
    pub(crate) interpolation_magnitude_policy: String,
    pub(crate) interpolation_phase_policy: String,
    pub(crate) enforce_causality: bool,
    pub(crate) ec_pulse_tolerance: f64,
    pub(crate) ec_relative_tolerance: f64,
    pub(crate) ec_difference_tolerance: f64,
    pub(crate) impulse_response_truncation_threshold: f64,
    pub(crate) debug: bool,
}

impl R480NormalErlControlsV1 {
    /// Materialize the exact normal TDR/ERL control surface from resolved
    /// workbook/JSON values.  Aliases must agree bit-for-bit; no default is
    /// inferred for a required numeric control.
    pub(crate) fn from_values(
        values: &BTreeMap<String, ResolvedDefaultV1>,
    ) -> Result<Self, DirectRunErrorV1> {
        let n_ui = integer_required(values, &["N", "n"])? as f64;
        let tdr_duration_ui = scalar_required(values, &["TDR_duration", "tdr_duration"])?;
        let tr_tdr_ns = scalar_required(values, &["TR_TDR", "tr_tdr"])?;
        let t_k_s = scalar_required(values, &["T_k", "t_k"])?;
        let spec_ber = scalar_required(values, &["specBER", "spec_ber"])?;
        let n_bx = integer_required(values, &["N_bx", "n_bx"])?;
        let grr = integer_required(values, &["Grr", "grr"])?;
        let fb_hz = scalar_required(values, &["fb", "baud_hz"])?;
        let sample_dt_s = scalar_required(values, &["sample_dt", "sample_dt_s"])?;
        let samples_per_ui = positive_usize(values, &["samples_per_ui"])?;
        let levels = positive_u32(values, &["levels", "LEVELS"])?;
        let bin_size = scalar_required(values, &["BinSize", "bin_size"])?;
        let f_r = scalar_required(values, &["f_r", "receiver_cutoff_multiplier"])?;
        let fb_bw_cutoff =
            scalar_required(values, &["fb_BW_cutoff", "butterworth_cutoff_multiplier"])?;
        let tfx = vector_exact(values, &["tfx"], 2)?;
        let tfx_s = [tfx[0], tfx[1]];
        if tfx_s.iter().any(|value| *value < 0.0) {
            return Err(parameter_error("tfx must be finite and non-negative"));
        }

        require_nonnegative(n_ui, "N")?;
        require_nonnegative(tdr_duration_ui, "TDR_duration")?;
        require_positive(tr_tdr_ns, "TR_TDR")?;
        require_positive(t_k_s, "T_k")?;
        if !(0.0 < spec_ber && spec_ber <= 1.0) {
            return Err(parameter_error("specBER must be in (0, 1]"));
        }
        if n_bx < 0 {
            return Err(parameter_error("N_bx must be non-negative"));
        }
        if !(0..=2).contains(&grr) {
            return Err(parameter_error("Grr must be 0, 1, or 2"));
        }
        require_positive(fb_hz, "fb")?;
        require_positive(sample_dt_s, "sample_dt")?;
        require_positive(bin_size, "BinSize")?;
        if f_r < 0.0 || !f_r.is_finite() {
            return Err(parameter_error("f_r must be finite and non-negative"));
        }
        require_positive(fb_bw_cutoff, "fb_BW_cutoff")?;
        let z_t_ohm = scalar_required(values, &["Z_t", "zt_ohm"])?;
        require_positive(z_t_ohm, "Z_t")?;
        if levels < 2 {
            return Err(parameter_error("levels must be at least 2"));
        }

        let ec_pulse_tolerance = scalar_optional(values, &["EC_PULSE_TOL"])?.unwrap_or(0.05);
        let ec_relative_tolerance = scalar_optional(values, &["EC_REL_TOL"])?.unwrap_or(0.006);
        let ec_difference_tolerance = scalar_optional(values, &["EC_DIFF_TOL"])?.unwrap_or(1.0e-4);
        let impulse_response_truncation_threshold = scalar_optional(
            values,
            &[
                "impulse_response_truncation_threshold",
                "Impulse response truncation threshold",
                "Impulse response truncatio threshold",
            ],
        )?
        .unwrap_or(1.0e-3);
        if !(0.0 < ec_pulse_tolerance && ec_pulse_tolerance <= 1.0)
            || ec_relative_tolerance < 0.0
            || ec_difference_tolerance < 0.0
            || impulse_response_truncation_threshold < 0.0
        {
            return Err(parameter_error("invalid TDR causality tolerances"));
        }

        Ok(Self {
            tdr_enabled: bool_optional(values, &["TDR", "tdr"])?.unwrap_or(true),
            erl_enabled: bool_optional(values, &["ERL", "erl"])?.unwrap_or(false),
            tdr_w_txpkg: bool_optional(values, &["TDR_W_TXPKG", "tdr_w_txpkg"])?.unwrap_or(false),
            n_ui,
            tdr_duration_ui,
            tr_tdr_ns,
            tdr_butterworth: bool_optional(values, &["TDR_Butterworth", "tdr_butterworth"])?
                .unwrap_or(true),
            tukey_window: bool_optional(values, &["Tukey_Window", "tukey_window"])?
                .unwrap_or(false),
            auto_tfx: bool_optional(values, &["AUTO_TFX", "auto_tfx"])?.unwrap_or(false),
            t_k_s,
            rl_norm_test: bool_optional(values, &["RL_norm_test", "rl_norm_test"])?.unwrap_or(true),
            spec_ber,
            n_bx,
            rho_x: scalar_required(values, &["rho_x"])?,
            grr,
            beta_x_db_per_s: scalar_required(values, &["beta_x"])?,
            z_t_ohm,
            fb_hz,
            sample_dt_s,
            samples_per_ui,
            levels,
            bin_size,
            f_r,
            fb_bw_cutoff,
            tfx_s,
            interpolation_magnitude_policy: string_optional(
                values,
                &["interp_sparam_mag", "interpolation_magnitude_policy"],
            )?
            .unwrap_or_else(|| "linear_trend_to_DC".to_owned()),
            interpolation_phase_policy: string_optional(
                values,
                &["interp_sparam_phase", "interpolation_phase_policy"],
            )?
            .unwrap_or_else(|| "extrap_cubic_to_dc_linear_to_inf".to_owned()),
            enforce_causality: bool_optional(values, &["ENFORCE_CAUSALITY", "enforce_causality"])?
                .unwrap_or(false),
            ec_pulse_tolerance,
            ec_relative_tolerance,
            ec_difference_tolerance,
            impulse_response_truncation_threshold,
            debug: bool_optional(values, &["DEBUG", "debug"])?.unwrap_or(false),
        })
    }
}

/// One port's typed TDR/PTDR/ERL result.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct R480NormalErlPortV1 {
    pub(crate) port: u8,
    pub(crate) time_s: Vec<f64>,
    pub(crate) impedance_ohm: Vec<f64>,
    pub(crate) step_reflection: Vec<f64>,
    pub(crate) ptdr: Vec<f64>,
    pub(crate) gated: Vec<f64>,
    pub(crate) worst_samples: Vec<f64>,
    pub(crate) phase_index: usize,
    /// The exact interpolation guard was bypassed because DEBUG=true.
    /// This is a SIPI observation, not a MATLAB warning-count claim.
    pub(crate) phase_slope_debug_bypassed: bool,
    /// Bounded summary of the exact normal-TDR FD vector passed to the
    /// interpolation guard when DEBUG is enabled. It is diagnostic-only.
    pub(crate) interpolation_input_trace: Option<R480NormalTdrInterpolationTraceV1>,
    pub(crate) erl_db: f64,
    pub(crate) erl_rms_db: f64,
    pub(crate) avg_port_impedance_ohm: f64,
}

/// Scalar-only interpolation input observation for source-stage diagnosis.
///
/// This deliberately excludes the waveform itself and is never a source
/// warning claim. Its shape mirrors the MATLAB observer's bounded trace so
/// callsite identity can be established before any warning-wire promotion.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct R480NormalTdrInterpolationTraceV1 {
    pub(crate) element_count: usize,
    pub(crate) first_real: f64,
    pub(crate) first_imaginary: f64,
    pub(crate) last_real: f64,
    pub(crate) last_imaginary: f64,
    pub(crate) sum_real: f64,
    pub(crate) sum_imaginary: f64,
    pub(crate) maximum_magnitude: f64,
    pub(crate) mean_unwrapped_phase_step: f64,
    pub(crate) positive_mean_phase_step: bool,
}

/// Both normal S4P TDR ports and the effective fixture delays used by them.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct R480NormalErlResultV1 {
    pub(crate) ports: [R480NormalErlPortV1; 2],
    pub(crate) tfx_s: [f64; 2],
    pub(crate) input_is_ideal_match: bool,
}

/// Frequency-domain filters shared by the two normal-TDR reflection ports.
///
/// Agent-COM evaluates the same transition, receiver and Tukey responses for
/// both ports.  Materializing the immutable product once keeps the numerical
/// operation order inside each port unchanged while avoiding a second set of
/// O(N) filter construction and temporary allocations.
struct R480NormalTdrFiltersV1 {
    transition: Vec<Complex64>,
    receiver_tukey: Vec<Complex64>,
}

/// Execute one normal S4P TDR/PTDR/ERL result from an assembled DD network.
///
/// The outer caller is responsible for invoking this once per run (normally
/// on package case zero) and copying the typed result to the package cases.
/// `fix_erl_best_phase` is the pinned `experimental_corrected` correction for
/// non-normalized phase selection.
pub(crate) fn run_normal_erl_with_profile_v1(
    network: &R480TdrDdNetworkV1,
    values: &BTreeMap<String, ResolvedDefaultV1>,
    fix_erl_best_phase: bool,
) -> Result<R480NormalErlResultV1, DirectRunErrorV1> {
    validate_network(network)?;
    let controls = R480NormalErlControlsV1::from_values(values)?;
    if controls.erl_enabled && !controls.tdr_enabled {
        return Err(DirectRunErrorV1::Unsupported(
            "normal ERL requires TDR=true in the r4.80 TDR_ERL_Processing path".to_owned(),
        ));
    }
    if !controls.tdr_enabled && !controls.erl_enabled {
        return Err(DirectRunErrorV1::Unsupported(
            "normal TDR/ERL leaf requires TDR or ERL to be enabled".to_owned(),
        ));
    }

    let mut tfx_s = controls.tfx_s;
    if controls.auto_tfx {
        tfx_s[1] = estimate_auto_tfx_v1(network, &controls)?;
    }
    let max_time_s = r480_tdr_max_time_v1(network, &controls)?;
    let filters = normal_tdr_filters_v1(network, &controls)?;
    let port1 = run_port_v1(
        network,
        &controls,
        &filters,
        1,
        tfx_s[0],
        max_time_s,
        fix_erl_best_phase,
    )?;
    let port2 = run_port_v1(
        network,
        &controls,
        &filters,
        2,
        tfx_s[1],
        max_time_s,
        fix_erl_best_phase,
    )?;
    let input_is_ideal_match = network
        .s11
        .iter()
        .chain(&network.s22)
        .all(|value| value.real() == 0.0 && value.imaginary() == 0.0);
    Ok(R480NormalErlResultV1 {
        ports: [port1, port2],
        tfx_s,
        input_is_ideal_match,
    })
}

fn normal_tdr_filters_v1(
    network: &R480TdrDdNetworkV1,
    controls: &R480NormalErlControlsV1,
) -> Result<R480NormalTdrFiltersV1, DirectRunErrorV1> {
    let transition = transition_filter_v1(&network.frequency_hz, controls.tr_tdr_ns)?;
    let receiver = butterworth_filter_v1(
        &network.frequency_hz,
        controls.fb_bw_cutoff,
        controls.fb_hz,
        controls.tdr_butterworth,
    )
    .map_err(|error| DirectRunErrorV1::Channel(format!("TDR Butterworth filter: {error:?}")))?;
    let tukey = raised_cosine_filter_v1(
        &network.frequency_hz,
        controls.f_r * controls.fb_hz,
        controls.fb_hz,
        controls.tukey_window,
    )
    .map_err(|error| DirectRunErrorV1::Channel(format!("TDR Tukey filter: {error:?}")))?;
    let receiver_tukey = receiver
        .into_iter()
        .zip(tukey)
        .map(|(receiver, tukey)| {
            Complex64::try_new(receiver.real() * tukey, receiver.imaginary() * tukey)
                .map_err(|_| DirectRunErrorV1::Channel("non-finite TDR receiver filter".to_owned()))
        })
        .collect::<Result<Vec<_>, _>>()?;
    if transition.len() != receiver_tukey.len() || transition.len() != network.frequency_hz.len() {
        return Err(DirectRunErrorV1::Channel(
            "normal TDR filter axes are not aligned".to_owned(),
        ));
    }
    Ok(R480NormalTdrFiltersV1 {
        transition,
        receiver_tukey,
    })
}

fn validate_network(network: &R480TdrDdNetworkV1) -> Result<(), DirectRunErrorV1> {
    let n = network.frequency_hz.len();
    if !(3..=MAX_TDR_SAMPLES).contains(&n)
        || network.s11.len() != n
        || network.s12.len() != n
        || network.s21.len() != n
        || network.s22.len() != n
        || network.raw_sdd12.len() != n
    {
        return Err(DirectRunErrorV1::Channel(
            "normal TDR network axes are not aligned".to_owned(),
        ));
    }
    if network
        .frequency_hz
        .iter()
        .any(|value| !value.is_finite() || *value < 0.0)
        || network
            .frequency_hz
            .windows(2)
            .any(|pair| pair[1] <= pair[0])
        || network
            .s11
            .iter()
            .chain(&network.s12)
            .chain(&network.s21)
            .chain(&network.s22)
            .chain(&network.raw_sdd12)
            .any(|value| !finite_complex(*value))
    {
        return Err(DirectRunErrorV1::Channel(
            "normal TDR network contains invalid frequency or S-parameter data".to_owned(),
        ));
    }
    Ok(())
}

fn estimate_auto_tfx_v1(
    network: &R480TdrDdNetworkV1,
    controls: &R480NormalErlControlsV1,
) -> Result<f64, DirectRunErrorV1> {
    let receiver = butterworth_filter_v1(&network.frequency_hz, 0.75, controls.fb_hz, true)
        .map_err(|error| {
            DirectRunErrorV1::Channel(format!("AUTO_TFX receiver filter: {error:?}"))
        })?;
    let filtered = network
        .raw_sdd12
        .iter()
        .zip(receiver)
        .map(|(value, filter)| complex_mul(*value, filter))
        .collect::<Result<Vec<_>, _>>()?;
    let impulse = s21_to_impulse_dc_v1(&filtered, &network.frequency_hz, &fd_options_v1(controls))
        .map_err(|error| DirectRunErrorV1::Channel(format!("AUTO_TFX FD-to-TD: {error:?}")))?;
    let peak_index = impulse
        .voltage
        .iter()
        .enumerate()
        .max_by(|(_, left), (_, right)| left.total_cmp(right))
        .map(|(index, _)| index)
        .ok_or_else(|| {
            DirectRunErrorV1::Channel("AUTO_TFX produced no impulse samples".to_owned())
        })?;
    let result = 2.0 * impulse.time_s[peak_index];
    if !result.is_finite() || result < 0.0 {
        return Err(DirectRunErrorV1::Channel(
            "AUTO_TFX produced an invalid fixture delay".to_owned(),
        ));
    }
    Ok(result)
}

fn r480_tdr_max_time_v1(
    network: &R480TdrDdNetworkV1,
    controls: &R480NormalErlControlsV1,
) -> Result<f64, DirectRunErrorV1> {
    let ui_s = 1.0 / controls.fb_hz;
    if controls.n_ui != 0.0 {
        let result = controls.n_ui * ui_s;
        if !result.is_finite() || result < 0.0 {
            return Err(parameter_error("N*ui is invalid"));
        }
        return Ok(result);
    }
    let receiver = butterworth_filter_v1(&network.frequency_hz, 0.75, controls.fb_hz, true)
        .map_err(|error| {
            DirectRunErrorV1::Channel(format!("TDR transit receiver filter: {error:?}"))
        })?;
    let filtered = network
        .s21
        .iter()
        .zip(receiver)
        .map(|(value, filter)| complex_mul(*value, filter))
        .collect::<Result<Vec<_>, _>>()?;
    // get_TDR's N=0 transit probe uses the fixed raw-FIR interpolation policy
    // rather than the later TDR waveform's user-selected aliases.
    let probe_options = FdToTdOptionsV1 {
        sample_dt_s: controls.sample_dt_s,
        magnitude_policy: "linear_trend_to_DC".to_owned(),
        phase_policy: "extrap_cubic_to_dc_linear_to_inf".to_owned(),
        enforce_causality: controls.enforce_causality,
        ec_pulse_tolerance: controls.ec_pulse_tolerance,
        ec_relative_tolerance: controls.ec_relative_tolerance,
        ec_difference_tolerance: controls.ec_difference_tolerance,
        truncation_threshold: 1.0e-5,
        debug: controls.debug,
        ..FdToTdOptionsV1::default()
    };
    let impulse = s21_to_impulse_dc_v1(&filtered, &network.frequency_hz, &probe_options)
        .map_err(|error| DirectRunErrorV1::Channel(format!("TDR transit FD-to-TD: {error:?}")))?;
    let peak_time_s = impulse
        .voltage
        .iter()
        .enumerate()
        .max_by(|(_, left), (_, right)| left.total_cmp(right))
        .map(|(index, _)| impulse.time_s[index])
        .ok_or_else(|| DirectRunErrorV1::Channel("TDR transit probe is empty".to_owned()))?;
    let result = (peak_time_s * controls.tdr_duration_ui + TDR_DELAY_S).min(
        *impulse.time_s.last().ok_or_else(|| {
            DirectRunErrorV1::Channel("TDR transit probe has no time axis".to_owned())
        })?,
    );
    if !result.is_finite() || result < 0.0 {
        return Err(DirectRunErrorV1::Channel(
            "TDR transit max time is invalid".to_owned(),
        ));
    }
    Ok(result)
}

fn run_port_v1(
    network: &R480TdrDdNetworkV1,
    controls: &R480NormalErlControlsV1,
    filters: &R480NormalTdrFiltersV1,
    port: u8,
    fixture_delay_s: f64,
    max_time_s: f64,
    fix_erl_best_phase: bool,
) -> Result<R480NormalErlPortV1, DirectRunErrorV1> {
    if !fixture_delay_s.is_finite() {
        return Err(parameter_error("tfx must be finite"));
    }
    let reflection = if port == 1 {
        reflection_renormalize_v1(
            &network.s11,
            &network.s12,
            &network.s21,
            &network.s22,
            controls.z_t_ohm,
        )?
    } else if port == 2 {
        reflection_renormalize_v1(
            &network.s22,
            &network.s21,
            &network.s12,
            &network.s11,
            controls.z_t_ohm,
        )?
    } else {
        return Err(parameter_error("normal TDR port must be 1 or 2"));
    };
    let exact_zero_reflection = reflection
        .iter()
        .all(|value| value.real() == 0.0 && value.imaginary() == 0.0);
    let filtered = reflection
        .into_iter()
        .zip(&filters.transition)
        .zip(&filters.receiver_tukey)
        .map(|((value, transition), receiver_tukey)| {
            complex_mul(complex_mul(value, *transition)?, *receiver_tukey)
        })
        .collect::<Result<Vec<_>, _>>()?;
    // Match the signal passed to get_TDR's interpolation step, not the raw
    // S11/S22 trace before the TDR transition and receiver filters.
    let phase_slope_debug_bypassed = controls.debug
        && has_positive_unwrapped_phase_slope_v1(&filtered)
            .map_err(|error| DirectRunErrorV1::Channel(format!("TDR phase guard: {error:?}")))?;
    let interpolation_input_trace = controls
        .debug
        .then(|| normal_tdr_interpolation_input_trace_v1(&filtered))
        .transpose()?;
    let (mut selected_time, mut selected_impulse) = if exact_zero_reflection {
        // MATLAB's mixed-mode matrix product can leave subnormal round-off in
        // an otherwise ideal reflection. The source then retains a complete
        // zero-equivalent TDR observation window. Rust cancellation is exact,
        // so construct that physical zero response explicitly rather than
        // collapsing the port to one sample and publishing Z=0 ohm.
        zero_reflection_tdr_window_v1(network, controls, fixture_delay_s, max_time_s)?
    } else {
        let impulse = s21_to_impulse_dc_v1(
            &filtered,
            &network.frequency_hz,
            &tdr_fd_options_v1(controls),
        )
        .map_err(|error| DirectRunErrorV1::Channel(format!("TDR FD-to-TD: {error:?}")))?;
        let shifted_time = impulse
            .time_s
            .iter()
            .map(|time| *time - TDR_DELAY_S)
            .collect::<Vec<_>>();
        let end = shifted_time
            .iter()
            .position(|time| *time >= max_time_s + fixture_delay_s)
            .map_or(shifted_time.len(), |index| index.saturating_add(1));
        (
            shifted_time[..end].to_vec(),
            impulse.voltage[..end].to_vec(),
        )
    };
    let average_start = selected_time
        .iter()
        .position(|time| *time >= 3.0 * controls.tr_tdr_ns * 1.0e-9);
    let mut start = selected_time
        .iter()
        .position(|time| *time >= controls.tr_tdr_ns * 1.0e-9)
        .unwrap_or(0);
    if start >= selected_time.len() {
        start = 0;
    }
    if start >= selected_time.len() {
        return Err(DirectRunErrorV1::Channel(
            "normal TDR observation window is empty".to_owned(),
        ));
    }
    selected_time = selected_time.split_off(start);
    selected_impulse = selected_impulse.split_off(start);
    let step_reflection = cumulative_sum_v1(&selected_impulse);
    let impedance_ohm = step_reflection
        .iter()
        .map(|reflection| (1.0 + reflection) / (1.0 - reflection) * controls.z_t_ohm * 2.0)
        .collect::<Vec<_>>();
    let ptdr = pulse_response_v1(&selected_impulse, controls.samples_per_ui)?;
    let gated = erl_gate_v1(
        &ptdr,
        &selected_time,
        fixture_delay_s,
        1.0 / controls.fb_hz,
        controls.n_bx,
        controls.tr_tdr_ns,
        controls.rho_x,
        controls.grr,
        controls.beta_x_db_per_s,
    )?;
    let (phase_index, worst_samples, erl_db, erl_rms_db) = effective_return_loss_v1(
        &gated,
        controls.samples_per_ui,
        controls.levels,
        controls.bin_size,
        controls.spec_ber,
        controls.rl_norm_test,
        fix_erl_best_phase,
    )?;
    let avg_port_impedance_ohm = average_port_impedance_v1(
        &selected_time,
        &impedance_ohm,
        average_start,
        controls.t_k_s,
    );
    Ok(R480NormalErlPortV1 {
        port,
        time_s: selected_time,
        impedance_ohm,
        step_reflection,
        ptdr,
        gated,
        worst_samples,
        phase_index,
        phase_slope_debug_bypassed,
        interpolation_input_trace,
        erl_db,
        erl_rms_db,
        avg_port_impedance_ohm,
    })
}

fn zero_reflection_tdr_window_v1(
    network: &R480TdrDdNetworkV1,
    controls: &R480NormalErlControlsV1,
    fixture_delay_s: f64,
    max_time_s: f64,
) -> Result<(Vec<f64>, Vec<f64>), DirectRunErrorV1> {
    let source_df = network.frequency_hz[2] - network.frequency_hz[1];
    let fmax = 1.0 / (2.0 * controls.sample_dt_s);
    let points_float = (fmax / source_df + 0.5).floor();
    if !(source_df.is_finite() && source_df > 0.0)
        || !(points_float.is_finite() && points_float >= 1.0)
        || points_float > MAX_FD_TO_TD_BINS_V1 as f64
    {
        return Err(DirectRunErrorV1::Channel(
            "normal TDR zero reflection axis is invalid".to_owned(),
        ));
    }
    let length = (points_float as usize).checked_mul(2).ok_or_else(|| {
        DirectRunErrorV1::Channel("normal TDR zero reflection axis overflow".to_owned())
    })?;
    let dt_s = 1.0 / (source_df * length as f64);
    if !(dt_s.is_finite() && dt_s > 0.0) {
        return Err(DirectRunErrorV1::Channel(
            "normal TDR zero reflection timestep is invalid".to_owned(),
        ));
    }
    let first_at_or_after = |target: f64| {
        let mut index = ((target + TDR_DELAY_S) / dt_s).ceil().max(0.0) as usize;
        while index < length && index as f64 * dt_s - TDR_DELAY_S < target {
            index += 1;
        }
        index
    };
    let end = first_at_or_after(max_time_s + fixture_delay_s).min(length.saturating_sub(1));
    let start = first_at_or_after(controls.tr_tdr_ns * 1.0e-9);
    // Match the source fallback when a threshold lands beyond the already
    // truncated TDR span.  The fallback starts at its first sample; it must
    // not re-expand the selection to the full IFFT horizon.
    let (start, end) = if start >= end { (0, end) } else { (start, end) };
    let time_s = (start..=end)
        .map(|index| index as f64 * dt_s - TDR_DELAY_S)
        .collect::<Vec<_>>();
    if time_s.is_empty() {
        return Err(DirectRunErrorV1::Channel(
            "normal TDR zero reflection window is empty".to_owned(),
        ));
    }
    Ok((time_s, vec![0.0; end - start + 1]))
}

fn normal_tdr_interpolation_input_trace_v1(
    values: &[Complex64],
) -> Result<R480NormalTdrInterpolationTraceV1, DirectRunErrorV1> {
    if values.len() < 2 {
        return Err(DirectRunErrorV1::Channel(
            "normal TDR interpolation trace needs at least two samples".to_owned(),
        ));
    }
    let first = values[0];
    let last = *values.last().expect("length checked");
    let mut sum_real = 0.0;
    let mut sum_imaginary = 0.0;
    let mut maximum_magnitude = 0.0_f64;
    let mut previous_phase = None;
    let mut phase_delta_sum = 0.0;
    for value in values {
        let real = value.real();
        let imaginary = value.imaginary();
        if !real.is_finite() || !imaginary.is_finite() {
            return Err(DirectRunErrorV1::Channel(
                "normal TDR interpolation trace contains non-finite input".to_owned(),
            ));
        }
        sum_real += real;
        sum_imaginary += imaginary;
        maximum_magnitude = maximum_magnitude.max(real.hypot(imaginary));
        let mut phase = imaginary.atan2(real);
        if let Some(previous) = previous_phase {
            let mut delta = phase - previous;
            while delta > std::f64::consts::PI {
                phase -= std::f64::consts::TAU;
                delta -= std::f64::consts::TAU;
            }
            while delta <= -std::f64::consts::PI {
                phase += std::f64::consts::TAU;
                delta += std::f64::consts::TAU;
            }
            phase_delta_sum += phase - previous;
        }
        previous_phase = Some(phase);
    }
    let mean_unwrapped_phase_step = phase_delta_sum / (values.len() - 1) as f64;
    if !sum_real.is_finite()
        || !sum_imaginary.is_finite()
        || !maximum_magnitude.is_finite()
        || !mean_unwrapped_phase_step.is_finite()
    {
        return Err(DirectRunErrorV1::Channel(
            "normal TDR interpolation trace calculation is non-finite".to_owned(),
        ));
    }
    Ok(R480NormalTdrInterpolationTraceV1 {
        element_count: values.len(),
        first_real: first.real(),
        first_imaginary: first.imaginary(),
        last_real: last.real(),
        last_imaginary: last.imaginary(),
        sum_real,
        sum_imaginary,
        maximum_magnitude,
        mean_unwrapped_phase_step,
        positive_mean_phase_step: mean_unwrapped_phase_step > 0.0,
    })
}

fn fd_options_v1(controls: &R480NormalErlControlsV1) -> FdToTdOptionsV1 {
    FdToTdOptionsV1 {
        sample_dt_s: controls.sample_dt_s,
        magnitude_policy: controls.interpolation_magnitude_policy.clone(),
        phase_policy: controls.interpolation_phase_policy.clone(),
        enforce_causality: controls.enforce_causality,
        ec_pulse_tolerance: controls.ec_pulse_tolerance,
        ec_relative_tolerance: controls.ec_relative_tolerance,
        ec_difference_tolerance: controls.ec_difference_tolerance,
        truncation_threshold: controls.impulse_response_truncation_threshold,
        debug: controls.debug,
        ..FdToTdOptionsV1::default()
    }
}

fn tdr_fd_options_v1(controls: &R480NormalErlControlsV1) -> FdToTdOptionsV1 {
    FdToTdOptionsV1 {
        sample_dt_s: controls.sample_dt_s,
        // process_sxp overwrites these options immediately before each
        // get_TDR call; they are not user-selectable on the normal path.
        magnitude_policy: "linear_trend_to_DC".to_owned(),
        phase_policy: "extrap_cubic_to_dc_linear_to_inf".to_owned(),
        enforce_causality: controls.enforce_causality,
        ec_pulse_tolerance: controls.ec_pulse_tolerance,
        ec_relative_tolerance: controls.ec_relative_tolerance,
        ec_difference_tolerance: controls.ec_difference_tolerance,
        truncation_threshold: 1.0e-5,
        debug: controls.debug,
        ..FdToTdOptionsV1::default()
    }
}

fn transition_filter_v1(
    frequency_hz: &[f64],
    transition_ns: f64,
) -> Result<Vec<Complex64>, DirectRunErrorV1> {
    frequency_hz
        .iter()
        .map(|frequency| {
            let frequency_ghz = *frequency / 1.0e9;
            let magnitude = (-2.0
                * (std::f64::consts::PI * frequency_ghz * transition_ns / 1.6832).powi(2))
            .exp();
            let phase = -2.0
                * std::f64::consts::PI
                * frequency_ghz
                * (TDR_DELAY_S / 1.0e-9 + 3.0 * transition_ns);
            Complex64::try_new(magnitude * phase.cos(), magnitude * phase.sin()).map_err(|_| {
                DirectRunErrorV1::Channel("non-finite TDR transition filter".to_owned())
            })
        })
        .collect()
}

fn reflection_renormalize_v1(
    s11: &[Complex64],
    s12: &[Complex64],
    s21: &[Complex64],
    s22: &[Complex64],
    z_t_ohm: f64,
) -> Result<Vec<Complex64>, DirectRunErrorV1> {
    if s11.len() != s12.len() || s11.len() != s21.len() || s11.len() != s22.len() {
        return Err(DirectRunErrorV1::Channel(
            "TDR reflection S-parameter lengths differ".to_owned(),
        ));
    }
    if !(z_t_ohm > 0.0 && z_t_ohm.is_finite()) {
        return Err(parameter_error("Z_t must be finite and positive"));
    }
    let zin = TDR_REFERENCE_OHM;
    let zout = 2.0 * z_t_ohm;
    s11.iter()
        .zip(s12)
        .zip(s21)
        .zip(s22)
        .map(|(((s11, s12), s21), s22)| {
            // get_TDR receives the differential SDD network with a 100 ohm
            // input and 2*ZT output.  The normal constants are kept explicit
            // to avoid silently applying the S2P renormalization branch.
            reflection_renormalize_one_v1(*s11, *s12, *s21, *s22, zin, zout)
        })
        .collect()
}

fn reflection_renormalize_one_v1(
    s11: Complex64,
    s12: Complex64,
    s21: Complex64,
    s22: Complex64,
    zin: f64,
    zout: f64,
) -> Result<Complex64, DirectRunErrorV1> {
    let zin2 = zin * zin;
    let zout2 = zout * zout;
    let zprod = zin * zout;
    let s11s22 = complex_mul(s11, s22)?;
    let s12s21 = complex_mul(s12, s21)?;
    let numerator = sum_complex_v1(&[
        complex_scale(s11, zin2)?,
        complex_scale(s22, zin2)?,
        complex_scale(s11, zout2)?,
        complex_scale(s22, zout2)?,
        real_complex(zin2 - zout2)?,
        complex_scale(s11, 2.0 * zprod)?,
        complex_scale(s22, -2.0 * zprod)?,
        complex_scale(s11s22, zin2)?,
        complex_scale(s12s21, -zin2)?,
        complex_scale(s11s22, -zout2)?,
        complex_scale(s12s21, zout2)?,
    ])?;
    let denominator = sum_complex_v1(&[
        real_complex(2.0 * zprod)?,
        complex_scale(s11, zin2)?,
        complex_scale(s22, zin2)?,
        complex_scale(s11, -zout2)?,
        complex_scale(s22, -zout2)?,
        real_complex(zin2 + zout2)?,
        complex_scale(s11s22, zin2)?,
        complex_scale(s12s21, -zin2)?,
        complex_scale(s11s22, zout2)?,
        complex_scale(s12s21, -zout2)?,
        complex_scale(s11s22, -2.0 * zprod)?,
        complex_scale(s12s21, 2.0 * zprod)?,
    ])?;
    complex_div(numerator, denominator)
}

fn cumulative_sum_v1(values: &[f64]) -> Vec<f64> {
    let mut total = 0.0;
    values
        .iter()
        .map(|value| {
            total += *value;
            total
        })
        .collect()
}

fn pulse_response_v1(impulse: &[f64], samples_per_ui: usize) -> Result<Vec<f64>, DirectRunErrorV1> {
    if impulse.is_empty() || samples_per_ui == 0 {
        return Err(parameter_error(
            "normal TDR pulse requires a non-empty impulse and positive samples_per_ui",
        ));
    }
    rectangular_pulse_response_v1(impulse, samples_per_ui)
        .map_err(|error| DirectRunErrorV1::Channel(format!("TDR pulse: {error:?}")))
}

#[allow(clippy::too_many_arguments)]
fn erl_gate_v1(
    ptdr: &[f64],
    time_s: &[f64],
    tfx_s: f64,
    ui_s: f64,
    n_bx: i64,
    transition_ns: f64,
    rho_x: f64,
    grr: i64,
    beta_x_db_per_s: f64,
) -> Result<Vec<f64>, DirectRunErrorV1> {
    if ptdr.len() != time_s.len()
        || ptdr.is_empty()
        || !ptdr.iter().chain(time_s).all(|value| value.is_finite())
        || !tfx_s.is_finite()
        || !(ui_s > 0.0 && ui_s.is_finite())
        || n_bx < 0
        || !(transition_ns >= 0.0 && transition_ns.is_finite())
        || !rho_x.is_finite()
        || !beta_x_db_per_s.is_finite()
        || !(0..=2).contains(&grr)
    {
        return Err(DirectRunErrorV1::Channel(
            "invalid normal ERL gate inputs".to_owned(),
        ));
    }
    let transition_delay = 3.0 * transition_ns * 1.0e-9;
    let gate_start = tfx_s + transition_delay;
    let Some(start) = time_s.iter().position(|time| *time >= gate_start) else {
        return Ok(ptdr.to_vec());
    };
    let gate_end = (n_bx as f64 + 1.0) * ui_s + tfx_s + transition_delay;
    let end = time_s
        .iter()
        .position(|time| *time > gate_end)
        .unwrap_or(ptdr.len().saturating_sub(1));
    let tk = gate_end;
    let mut gated = ptdr.to_vec();
    gated[..start].fill(0.0);
    for index in start..=end.min(ptdr.len().saturating_sub(1)) {
        let x = (time_s[index] - tfx_s - transition_delay) / ui_s;
        let reflection = if grr == 2 {
            rho_x
        } else {
            (1.0 + rho_x)
                * rho_x
                * (-(x - n_bx as f64 - 1.0).powi(2) / (1.0 + n_bx as f64).powi(2)).exp()
        };
        let loss = if n_bx > 0 && beta_x_db_per_s != 0.0 {
            10.0_f64.powf(beta_x_db_per_s * (time_s[index] - tk) / 20.0)
        } else {
            1.0
        };
        let value = ptdr[index] * loss * reflection;
        if !value.is_finite() {
            return Err(DirectRunErrorV1::Channel(
                "normal ERL gate produced a non-finite sample".to_owned(),
            ));
        }
        gated[index] = value;
    }
    Ok(gated)
}

fn effective_return_loss_v1(
    ptdr: &[f64],
    samples_per_ui: usize,
    levels: u32,
    bin_size: f64,
    spec_ber: f64,
    rl_norm_test: bool,
    fix_erl_best_phase: bool,
) -> Result<(usize, Vec<f64>, f64, f64), DirectRunErrorV1> {
    if ptdr.is_empty() || samples_per_ui == 0 {
        return Err(parameter_error("normal ERL PTDR input is empty"));
    }
    let mut best_selector = f64::NEG_INFINITY;
    let mut best_phase = 0usize;
    let mut best_samples = ptdr[0..].iter().step_by(samples_per_ui).copied().collect();
    let mut best_quantile = 0.0;
    let mut last_quantile = 0.0;
    for phase in 0..samples_per_ui {
        let samples = ptdr
            .iter()
            .skip(phase)
            .step_by(samples_per_ui)
            .copied()
            .collect::<Vec<_>>();
        if samples.is_empty() {
            continue;
        }
        let pdf = sampled_signal_pdf_v1(&samples, levels, bin_size * 10.0, false)
            .map_err(|error| DirectRunErrorV1::Channel(format!("normal ERL PDF: {error:?}")))?;
        let quantile = -pdf.first_quantile(spec_ber).map_err(|error| {
            DirectRunErrorV1::Channel(format!("normal ERL quantile: {error:?}"))
        })?;
        last_quantile = quantile;
        let selector = if rl_norm_test {
            samples
                .iter()
                .map(|value| value * value)
                .sum::<f64>()
                .sqrt()
        } else {
            quantile
        };
        if selector > best_selector {
            best_selector = selector;
            best_phase = phase;
            best_samples = samples;
            best_quantile = quantile;
        }
    }
    let best_erl_voltage = if rl_norm_test {
        let samples = ptdr
            .iter()
            .skip(best_phase)
            .step_by(samples_per_ui)
            .copied()
            .collect::<Vec<_>>();
        let pdf =
            sampled_signal_pdf_v1(&samples, levels, bin_size * 10.0, false).map_err(|error| {
                DirectRunErrorV1::Channel(format!("normal ERL selected PDF: {error:?}"))
            })?;
        -pdf.first_quantile(spec_ber).map_err(|error| {
            DirectRunErrorV1::Channel(format!("normal ERL selected quantile: {error:?}"))
        })?
    } else if fix_erl_best_phase {
        best_quantile
    } else {
        // This is the source r4.80 branch: best_erl is overwritten on every
        // phase while best_phase still records the strict winning selector.
        let _ = best_quantile;
        last_quantile
    };
    let erl_db = minus_db_v1(best_erl_voltage);
    let rms_voltage =
        ptdr.iter().map(|value| value * value).sum::<f64>().sqrt() / (ptdr.len() as f64).sqrt();
    let erl_rms_db = minus_db_v1(rms_voltage);
    Ok((best_phase, best_samples, erl_db, erl_rms_db))
}

fn average_port_impedance_v1(
    time_s: &[f64],
    impedance_ohm: &[f64],
    average_start: Option<usize>,
    t_k_s: f64,
) -> f64 {
    let Some(start) = average_start.filter(|index| *index < time_s.len()) else {
        return 0.0;
    };
    let times = &time_s[start..];
    let values = &impedance_ohm[start..];
    if times.is_empty() || !(t_k_s > 0.0 && t_k_s.is_finite()) {
        return 0.0;
    }
    let first = times[0];
    let weights = times
        .iter()
        .map(|time| (-(time - first) / t_k_s).exp())
        .collect::<Vec<_>>();
    let denominator = weights.iter().sum::<f64>();
    if denominator == 0.0 || !denominator.is_finite() {
        return 0.0;
    }
    values
        .iter()
        .zip(weights)
        .map(|(value, weight)| value * weight)
        .sum::<f64>()
        / denominator
}

fn minus_db_v1(value: f64) -> f64 {
    if value == 0.0 {
        f64::INFINITY
    } else {
        -20.0 * value.abs().log10()
    }
}

fn sum_complex_v1(values: &[Complex64]) -> Result<Complex64, DirectRunErrorV1> {
    values
        .iter()
        .try_fold(real_complex(0.0)?, |sum, value| complex_add(sum, *value))
}

fn real_complex(value: f64) -> Result<Complex64, DirectRunErrorV1> {
    Complex64::try_new(value, 0.0)
        .map_err(|_| DirectRunErrorV1::Channel("non-finite TDR intermediate".to_owned()))
}

fn finite_complex(value: Complex64) -> bool {
    value.real().is_finite() && value.imaginary().is_finite()
}

fn complex_add(a: Complex64, b: Complex64) -> Result<Complex64, DirectRunErrorV1> {
    Complex64::try_new(a.real() + b.real(), a.imaginary() + b.imaginary())
        .map_err(|_| DirectRunErrorV1::Channel("TDR complex addition overflow".to_owned()))
}

fn complex_scale(value: Complex64, factor: f64) -> Result<Complex64, DirectRunErrorV1> {
    Complex64::try_new(value.real() * factor, value.imaginary() * factor)
        .map_err(|_| DirectRunErrorV1::Channel("TDR complex scaling overflow".to_owned()))
}

fn complex_mul(a: Complex64, b: Complex64) -> Result<Complex64, DirectRunErrorV1> {
    Complex64::try_new(
        a.real() * b.real() - a.imaginary() * b.imaginary(),
        a.real() * b.imaginary() + a.imaginary() * b.real(),
    )
    .map_err(|_| DirectRunErrorV1::Channel("TDR complex multiplication overflow".to_owned()))
}

fn complex_div(a: Complex64, b: Complex64) -> Result<Complex64, DirectRunErrorV1> {
    let denominator = b.real() * b.real() + b.imaginary() * b.imaginary();
    if denominator == 0.0 || !denominator.is_finite() {
        return Err(DirectRunErrorV1::Channel(
            "TDR reflection renormalization is singular".to_owned(),
        ));
    }
    Complex64::try_new(
        (a.real() * b.real() + a.imaginary() * b.imaginary()) / denominator,
        (a.imaginary() * b.real() - a.real() * b.imaginary()) / denominator,
    )
    .map_err(|_| DirectRunErrorV1::Channel("TDR complex division overflow".to_owned()))
}

fn parameter_error(message: &str) -> DirectRunErrorV1 {
    DirectRunErrorV1::Parameters(message.to_owned())
}

fn matching_value<'a>(
    values: &'a BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
) -> Result<Option<&'a ResolvedDefaultV1>, DirectRunErrorV1> {
    let mut found: Option<&ResolvedDefaultV1> = None;
    for (key, value) in values {
        if !names.iter().any(|name| key.eq_ignore_ascii_case(name)) {
            continue;
        }
        if found.is_some_and(|previous| previous != value) {
            return Err(parameter_error(
                "case-insensitive TDR control aliases conflict",
            ));
        }
        found = Some(value);
    }
    Ok(found)
}

fn scalar_optional(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
) -> Result<Option<f64>, DirectRunErrorV1> {
    let Some(value) = matching_value(values, names)? else {
        return Ok(None);
    };
    match value {
        ResolvedDefaultV1::Scalar(value) if value.is_finite() => Ok(Some(*value)),
        ResolvedDefaultV1::Vector(values) if values.len() == 1 && values[0].is_finite() => {
            Ok(Some(values[0]))
        }
        _ => Err(parameter_error("TDR scalar control must be finite")),
    }
}

fn scalar_required(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
) -> Result<f64, DirectRunErrorV1> {
    scalar_optional(values, names)?.ok_or_else(|| {
        DirectRunErrorV1::Parameters(format!("missing normal TDR control {}", names[0]))
    })
}

fn bool_optional(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
) -> Result<Option<bool>, DirectRunErrorV1> {
    let Some(value) = matching_value(values, names)? else {
        return Ok(None);
    };
    match value {
        ResolvedDefaultV1::Boolean(value) => Ok(Some(*value)),
        ResolvedDefaultV1::Scalar(value) if value.is_finite() => Ok(Some(*value != 0.0)),
        _ => Err(parameter_error(
            "TDR boolean control must use finite source truthiness",
        )),
    }
}

fn string_optional(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
) -> Result<Option<String>, DirectRunErrorV1> {
    let Some(value) = matching_value(values, names)? else {
        return Ok(None);
    };
    match value {
        ResolvedDefaultV1::String(value) => Ok(Some(value.clone())),
        _ => Err(parameter_error("TDR interpolation policy must be a string")),
    }
}

fn vector_exact(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
    length: usize,
) -> Result<Vec<f64>, DirectRunErrorV1> {
    let value = matching_value(values, names)?.ok_or_else(|| {
        DirectRunErrorV1::Parameters(format!("missing normal TDR vector {}", names[0]))
    })?;
    let result = match value {
        ResolvedDefaultV1::Vector(values) if values.len() == length => values.clone(),
        _ => return Err(parameter_error("normal TDR vector has the wrong shape")),
    };
    if result.iter().any(|value| !value.is_finite()) {
        return Err(parameter_error(
            "normal TDR vector contains a non-finite value",
        ));
    }
    Ok(result)
}

fn integer_required(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
) -> Result<i64, DirectRunErrorV1> {
    let value = scalar_required(values, names)?;
    if value.fract() != 0.0 || value < i64::MIN as f64 || value > i64::MAX as f64 {
        return Err(parameter_error("normal TDR integer control is invalid"));
    }
    Ok(value as i64)
}

fn positive_usize(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
) -> Result<usize, DirectRunErrorV1> {
    let value = scalar_required(values, names)?;
    if value < 1.0 || value.fract() != 0.0 || value > usize::MAX as f64 {
        return Err(parameter_error("normal TDR sample count is invalid"));
    }
    Ok(value as usize)
}

fn positive_u32(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
) -> Result<u32, DirectRunErrorV1> {
    let value = scalar_required(values, names)?;
    if value < 1.0 || value.fract() != 0.0 || value > u32::MAX as f64 {
        return Err(parameter_error("normal TDR level count is invalid"));
    }
    Ok(value as u32)
}

fn require_positive(value: f64, name: &str) -> Result<(), DirectRunErrorV1> {
    if !(value > 0.0 && value.is_finite()) {
        return Err(DirectRunErrorV1::Parameters(format!(
            "{name} must be finite and positive"
        )));
    }
    Ok(())
}

fn require_nonnegative(value: f64, name: &str) -> Result<(), DirectRunErrorV1> {
    if !(value >= 0.0 && value.is_finite()) {
        return Err(DirectRunErrorV1::Parameters(format!(
            "{name} must be finite and non-negative"
        )));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::package_vtf_v1::R480TdrDdNetworkV1;

    fn c(real: f64, imaginary: f64) -> Complex64 {
        Complex64::try_new(real, imaginary).expect("finite complex")
    }

    fn controls() -> BTreeMap<String, ResolvedDefaultV1> {
        BTreeMap::from([
            ("TDR".to_owned(), ResolvedDefaultV1::Boolean(true)),
            ("ERL".to_owned(), ResolvedDefaultV1::Boolean(true)),
            ("TDR_W_TXPKG".to_owned(), ResolvedDefaultV1::Boolean(false)),
            ("N".to_owned(), ResolvedDefaultV1::Scalar(10.0)),
            ("TDR_duration".to_owned(), ResolvedDefaultV1::Scalar(5.0)),
            ("TR_TDR".to_owned(), ResolvedDefaultV1::Scalar(0.01)),
            (
                "TDR_Butterworth".to_owned(),
                ResolvedDefaultV1::Boolean(true),
            ),
            ("Tukey_Window".to_owned(), ResolvedDefaultV1::Boolean(true)),
            ("AUTO_TFX".to_owned(), ResolvedDefaultV1::Boolean(false)),
            ("T_k".to_owned(), ResolvedDefaultV1::Scalar(0.6e-9)),
            ("RL_norm_test".to_owned(), ResolvedDefaultV1::Boolean(true)),
            ("specBER".to_owned(), ResolvedDefaultV1::Scalar(1.0e-5)),
            ("N_bx".to_owned(), ResolvedDefaultV1::Scalar(6.0)),
            ("rho_x".to_owned(), ResolvedDefaultV1::Scalar(0.618)),
            ("Grr".to_owned(), ResolvedDefaultV1::Scalar(1.0)),
            ("beta_x".to_owned(), ResolvedDefaultV1::Scalar(0.0)),
            ("Z_t".to_owned(), ResolvedDefaultV1::Scalar(50.0)),
            ("fb".to_owned(), ResolvedDefaultV1::Scalar(53.125e9)),
            (
                "sample_dt".to_owned(),
                ResolvedDefaultV1::Scalar(1.0 / (53.125e9 * 32.0)),
            ),
            ("samples_per_ui".to_owned(), ResolvedDefaultV1::Scalar(32.0)),
            ("levels".to_owned(), ResolvedDefaultV1::Scalar(4.0)),
            ("BinSize".to_owned(), ResolvedDefaultV1::Scalar(1.0e-5)),
            ("f_r".to_owned(), ResolvedDefaultV1::Scalar(0.75)),
            ("fb_BW_cutoff".to_owned(), ResolvedDefaultV1::Scalar(0.75)),
            ("tfx".to_owned(), ResolvedDefaultV1::Vector(vec![0.0, 0.0])),
        ])
    }

    fn network() -> R480TdrDdNetworkV1 {
        let frequency_hz: Vec<_> = (0..65).map(|index| index as f64 * 0.1e9).collect();
        let s11 = vec![c(0.1, 0.0); frequency_hz.len()];
        let s22 = vec![c(0.2, 0.0); frequency_hz.len()];
        let s12 = vec![c(0.0, 0.0); frequency_hz.len()];
        let s21 = frequency_hz
            .iter()
            .map(|frequency| {
                let phase = -2.0 * std::f64::consts::PI * frequency * 1.0e-9;
                c(0.8 * phase.cos(), 0.8 * phase.sin())
            })
            .collect();
        R480TdrDdNetworkV1 {
            frequency_hz,
            s11,
            s12: s12.clone(),
            s21,
            s22,
            raw_sdd12: s12,
        }
    }

    #[test]
    fn normal_controls_cover_tdr_and_erl_switches() {
        let controls = R480NormalErlControlsV1::from_values(&controls()).expect("controls");
        assert!(controls.tdr_enabled);
        assert!(controls.erl_enabled);
        assert!(!controls.tdr_w_txpkg);
        assert_eq!(controls.tfx_s, [0.0, 0.0]);
        assert_eq!(controls.impulse_response_truncation_threshold, 1.0e-3);
    }

    #[test]
    fn reflection_renormalization_uses_requested_zt() {
        let s11 = [c(0.1, 0.02)];
        let s12 = [c(0.2, -0.01)];
        let s21 = [c(0.3, 0.04)];
        let s22 = [c(0.05, -0.02)];
        let result =
            reflection_renormalize_v1(&s11, &s12, &s21, &s22, 50.0).expect("renormalization");
        assert!((result[0].real() - s11[0].real()).abs() < 1.0e-12);
        assert!((result[0].imaginary() - s11[0].imaginary()).abs() < 1.0e-12);
    }

    #[test]
    fn invalid_normal_controls_fail_closed() {
        let mut values = controls();
        values.insert("N".to_owned(), ResolvedDefaultV1::Scalar(1.5));
        assert!(R480NormalErlControlsV1::from_values(&values).is_err());
        let mut values = controls();
        values.insert("levels".to_owned(), ResolvedDefaultV1::Scalar(1.0));
        assert!(R480NormalErlControlsV1::from_values(&values).is_err());
        let mut values = controls();
        values.insert("tfx".to_owned(), ResolvedDefaultV1::Vector(vec![-1.0, 0.0]));
        assert!(R480NormalErlControlsV1::from_values(&values).is_err());
    }

    #[test]
    fn erl_without_tdr_is_rejected_before_fd_work() {
        let mut values = controls();
        values.insert("TDR".to_owned(), ResolvedDefaultV1::Boolean(false));
        let network = network();
        let error = run_normal_erl_with_profile_v1(&network, &values, false)
            .expect_err("TDR=false must fail closed");
        assert!(error.to_string().contains("requires TDR=true"));
    }

    #[test]
    fn ideal_match_input_produces_infinite_erl_without_nan() {
        let mut values = controls();
        values.insert("Tukey_Window".to_owned(), ResolvedDefaultV1::Boolean(false));
        let mut network = network();
        network.s11.fill(c(0.0, 0.0));
        network.s22.fill(c(0.0, 0.0));
        let result = run_normal_erl_with_profile_v1(&network, &values, false).expect("ideal input");
        assert!(result.input_is_ideal_match);
        assert!(result.ports.iter().all(|port| port.erl_db.is_infinite()));
    }

    #[test]
    fn exact_zero_reflection_keeps_a_source_equivalent_tdr_window() {
        let mut values = controls();
        values.insert("Tukey_Window".to_owned(), ResolvedDefaultV1::Boolean(false));
        let mut network = network();
        // With ZT=50 ohm, the r4.80 renormalization reduces port 1 to S11.
        // An exact zero must still publish the physical 100-ohm TDR window,
        // not a one-sample artifact of FD truncation.
        network.s11.fill(c(0.0, 0.0));
        let result =
            run_normal_erl_with_profile_v1(&network, &values, false).expect("zero reflection");
        let port = &result.ports[0];
        assert!(port.time_s.len() > 1);
        assert!(port.impedance_ohm.iter().all(|value| *value == 100.0));
        assert!(port.ptdr.iter().all(|value| *value == 0.0));
        assert!((port.avg_port_impedance_ohm - 100.0).abs() < 1.0e-12);
    }

    #[test]
    fn exact_zero_reflection_uses_the_requested_termination() {
        let mut values = controls();
        values.insert("Z_t".to_owned(), ResolvedDefaultV1::Scalar(55.0));
        let controls = R480NormalErlControlsV1::from_values(&values).expect("controls");
        let network = network();
        let (_, impulse) = zero_reflection_tdr_window_v1(&network, &controls, 0.0, 1.0e-9)
            .expect("zero reflection");
        let impedance = cumulative_sum_v1(&impulse)
            .into_iter()
            .map(|reflection| (1.0 + reflection) / (1.0 - reflection) * controls.z_t_ohm * 2.0)
            .collect::<Vec<_>>();
        assert!(impedance.iter().all(|value| *value == 110.0));
    }

    #[test]
    fn zero_reflection_fallback_stays_within_truncated_tdr_span() {
        let mut values = controls();
        values.insert("TR_TDR".to_owned(), ResolvedDefaultV1::Scalar(10_000.0));
        let controls = R480NormalErlControlsV1::from_values(&values).expect("controls");
        let network = network();
        let max_time_s = r480_tdr_max_time_v1(&network, &controls).expect("max time");
        let (time_s, zeros) = zero_reflection_tdr_window_v1(&network, &controls, 0.0, max_time_s)
            .expect("zero window");
        assert_eq!(time_s.len(), zeros.len());
        assert!(time_s.len() > 1);
        assert!(time_s.last().copied().expect("last") <= max_time_s);
        assert!(zeros.iter().all(|value| *value == 0.0));
    }

    #[test]
    fn anti_causal_tdr_reflection_is_rejected_without_debug_bypass() {
        let values = controls();
        let mut network = network();
        network.s11 = network
            .frequency_hz
            .iter()
            .map(|frequency| {
                let phase = 31.0 * frequency * 1.0e-9;
                c(0.1 * phase.cos(), 0.1 * phase.sin())
            })
            .collect();
        let error = run_normal_erl_with_profile_v1(&network, &values, false)
            .expect_err("anti-causal input");
        assert!(error.to_string().contains("anti-causal"), "{error}");
    }

    #[test]
    fn debug_bypass_records_the_tdr_port_without_changing_erl_output_shape() {
        let mut values = controls();
        values.insert("DEBUG".to_owned(), ResolvedDefaultV1::Boolean(true));
        let mut network = network();
        network.s11 = network
            .frequency_hz
            .iter()
            .map(|frequency| {
                let phase = 31.0 * frequency * 1.0e-9;
                c(0.1 * phase.cos(), 0.1 * phase.sin())
            })
            .collect();
        let result =
            run_normal_erl_with_profile_v1(&network, &values, false).expect("DEBUG bypass");
        assert!(result.ports[0].phase_slope_debug_bypassed);
        assert!(!result.ports[1].phase_slope_debug_bypassed);
        assert!(
            result
                .ports
                .iter()
                .all(|port| port.erl_db.is_finite() || port.erl_db.is_infinite())
        );
    }

    #[test]
    fn gate_preserves_waveform_before_fixture_start() {
        let ptdr = vec![0.1, 0.2, 0.3];
        let time = vec![0.0, 1.0e-12, 2.0e-12];
        let gated = erl_gate_v1(&ptdr, &time, 1.0, 1.0, 0, 0.01, 0.618, 1, 0.0).expect("gate");
        assert_eq!(gated, ptdr);
    }

    #[test]
    fn experimental_best_phase_fix_changes_only_non_normalized_erl_value() {
        // Phase zero has the larger PDF quantile.  Pinned r4.80 publishes
        // the last phase when `rl_norm_test=false`; the approved experimental
        // profile instead keeps the selected phase's quantile.
        let ptdr = [1.2, 0.1, 0.9, 0.05, 1.1, 0.1, 0.8, 0.05];
        let r480 =
            effective_return_loss_v1(&ptdr, 2, 4, 0.01, 1.0e-3, false, false).expect("r480 ERL");
        let corrected = effective_return_loss_v1(&ptdr, 2, 4, 0.01, 1.0e-3, false, true)
            .expect("corrected ERL");
        assert_eq!(r480.0, 0);
        assert_eq!(corrected.0, r480.0);
        assert_eq!(corrected.1, r480.1);
        assert_ne!(corrected.2.to_bits(), r480.2.to_bits());
        assert!(
            (r480.2 - 13.979_400_086_720_375).abs() < 1.0e-12,
            "r480={}",
            r480.2
        );
        assert!(
            (corrected.2 - -12.041_199_826_559_248).abs() < 1.0e-12,
            "corrected={}",
            corrected.2
        );

        let normalized_r480 =
            effective_return_loss_v1(&ptdr, 2, 4, 0.01, 1.0e-3, true, false).expect("r480");
        let normalized_corrected =
            effective_return_loss_v1(&ptdr, 2, 4, 0.01, 1.0e-3, true, true).expect("corrected");
        assert_eq!(
            normalized_corrected.2.to_bits(),
            normalized_r480.2.to_bits()
        );
    }
}
