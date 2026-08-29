//! R4.80 package/VTF frequency-domain cascade for the admitted S4P route.
//!
//! This is a crate-private direct port of `network/two_port.py` and the
//! package helpers in `network/package.py`.  It deliberately keeps the
//! frequency axis intact until the final `s21_to_impulse_dc_v1` call: no fit,
//! interpolation, alignment, or epsilon substitution is performed.

use std::collections::BTreeMap;

use sipi_com::{
    FourPortSMatrixV1, ResolvedDefaultV1, bessel_thomson_filter_v1, butterworth_filter_v1,
    com_mixed_mode_v1, raised_cosine_filter_v1,
};
use sipi_types::Complex64;

use crate::DirectRunErrorV1;

const MAX_FREQUENCY_POINTS: usize = 1_000_000;
const MAX_SEGMENTS: usize = 64;
const MAX_PACKAGE_PARAMETER_ABS: f64 = 1.0e150;
#[allow(dead_code)]
pub(crate) const PACKAGE_VTF_POLICY_V1: &str =
    "sipi.com-r480.package-vtf-v1.s4p-mixed-mode-two-port-cascade-final-impulse-no-fit";

#[derive(Clone, Debug)]
struct TwoPort {
    s11: Vec<Complex64>,
    s12: Vec<Complex64>,
    s21: Vec<Complex64>,
    s22: Vec<Complex64>,
}

impl TwoPort {
    fn new(
        s11: Vec<Complex64>,
        s12: Vec<Complex64>,
        s21: Vec<Complex64>,
        s22: Vec<Complex64>,
    ) -> Result<Self, DirectRunErrorV1> {
        let n = s11.len();
        if n == 0
            || n > MAX_FREQUENCY_POINTS
            || [s12.len(), s21.len(), s22.len()].iter().any(|&m| m != n)
        {
            return Err(DirectRunErrorV1::Parameters(
                "package TwoPort vectors are not aligned".to_owned(),
            ));
        }
        if s11
            .iter()
            .chain(&s12)
            .chain(&s21)
            .chain(&s22)
            .any(|value| !finite(*value))
        {
            return Err(DirectRunErrorV1::Parameters(
                "package TwoPort contains a non-finite value".to_owned(),
            ));
        }
        Ok(Self { s11, s12, s21, s22 })
    }
}

/// The differential network consumed by the normal (non-ERL-only) TDR path.
///
/// The source keeps the raw DD reflection at port 1 even when `SHOW_BRD` or
/// `TDR_W_TXPKG` changes the network used for the other three entries.  The
/// raw SDD12 trace is retained as well because `AUTO_TFX` estimates the
/// receiver fixture delay from that pre-assembly channel trace.  This type is
/// crate-private on purpose: it is an internal hand-off between the package
/// assembler and the normal ERL leaf, not a second public S-parameter API.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct R480TdrDdNetworkV1 {
    pub(crate) frequency_hz: Vec<f64>,
    pub(crate) s11: Vec<Complex64>,
    pub(crate) s12: Vec<Complex64>,
    pub(crate) s21: Vec<Complex64>,
    pub(crate) s22: Vec<Complex64>,
    pub(crate) raw_sdd12: Vec<Complex64>,
}

impl R480TdrDdNetworkV1 {
    fn from_parts(
        frequency_hz: &[f64],
        network: TwoPort,
        raw_sdd12: Vec<Complex64>,
    ) -> Result<Self, DirectRunErrorV1> {
        if frequency_hz.len() != raw_sdd12.len() || frequency_hz.len() != network.s11.len() {
            return Err(DirectRunErrorV1::Parameters(
                "normal TDR network vectors are not aligned".to_owned(),
            ));
        }
        Ok(Self {
            frequency_hz: frequency_hz.to_vec(),
            s11: network.s11,
            s12: network.s12,
            s21: network.s21,
            s22: network.s22,
            raw_sdd12,
        })
    }
}

/// Assemble the raw DD network used by r4.80 `get_TDR`/`process_sxp`.
///
/// This is intentionally not the normal package VTF route.  The source
/// first extracts raw SDD, optionally adds the board when `SHOW_BRD` is set,
/// and only then (when `TDR_W_TXPKG` is set) prepends the selected TX package
/// and applies the differential source load.  Finally it restores the raw
/// pre-board SDD11 at port 1.  No kappa scaling or S-parameter fitting is
/// performed here.
pub(crate) fn assemble_r480_tdr_dd_network_v1(
    frequency_hz: &[f64],
    samples: &[FourPortSMatrixV1],
    values: &BTreeMap<String, ResolvedDefaultV1>,
    package_case_index: usize,
) -> Result<R480TdrDdNetworkV1, DirectRunErrorV1> {
    validate_s4p_axis_v1(frequency_hz, samples)?;
    let mixed = samples.iter().map(com_mixed_mode_v1).collect::<Vec<_>>();
    let original = TwoPort::new(
        mixed.iter().map(|sample| sample[1][1]).collect(),
        mixed.iter().map(|sample| sample[1][3]).collect(),
        mixed.iter().map(|sample| sample[3][1]).collect(),
        mixed.iter().map(|sample| sample[3][3]).collect(),
    )?;
    let raw_sdd12 = original.s12.clone();
    let component_frequency = frequency_hz
        .iter()
        .map(|frequency| frequency.max(f64::EPSILON))
        .collect::<Vec<_>>();
    let show_board = boolean(values, &["SHOW_BRD", "show_brd"])?.unwrap_or(false);
    let channel = if show_board {
        let include_pcb = scalar(values, &["include_pcb", "INCLUDE_PCB"])?.unwrap_or(0.0);
        if !matches!(include_pcb, 0.0 | 1.0 | 2.0) {
            return Err(DirectRunErrorV1::Parameters(
                "SHOW_BRD include_pcb must be exactly 0, 1, or 2".to_owned(),
            ));
        }
        if include_pcb == 0.0 {
            original.clone()
        } else {
            add_board_v1(
                original.clone(),
                &component_frequency,
                "THRU",
                include_pcb as u8,
                values,
            )?
        }
    } else {
        original.clone()
    };
    let with_tx_package = boolean(values, &["TDR_W_TXPKG", "tdr_w_txpkg"])?.unwrap_or(false);
    let assembled = if !with_tx_package {
        channel
    } else {
        let selected = selected_case(values, package_case_index)?;
        let tx_package = full_package_mode_v1(
            "TX",
            &component_frequency,
            "THRU",
            selected,
            values,
            true,
            false,
        )?;
        let cascaded = combine(&tx_package, &channel)?;
        let r_diepad = vector_required(values, &["R_diepad", "r_diepad"], 2)?;
        let loaded = source_load_v1(cascaded, 2.0 * r_diepad[0])?;
        // process_sxp restores sdd11_orig here, rather than the reflection
        // of the optional board network or of the TX package cascade.
        TwoPort::new(original.s11.clone(), loaded.s12, loaded.s21, loaded.s22)?
    };
    R480TdrDdNetworkV1::from_parts(frequency_hz, assembled, raw_sdd12)
}

pub(crate) fn s4p_package_vtf_v1(
    frequency_hz: &[f64],
    samples: &[FourPortSMatrixV1],
    values: &BTreeMap<String, ResolvedDefaultV1>,
    channel_type: &str,
    package_case_index: usize,
) -> Result<Vec<Complex64>, DirectRunErrorV1> {
    validate_s4p_axis_v1(frequency_hz, samples)?;
    let mixed_work = frequency_hz.len().checked_mul(4).ok_or_else(|| {
        DirectRunErrorV1::Parameters("package mixed-mode work budget overflow".to_owned())
    })?;
    if mixed_work > 4_000_000 {
        return Err(DirectRunErrorV1::Parameters(
            "package mixed-mode work budget exceeded".to_owned(),
        ));
    }
    let mixed = samples.iter().map(com_mixed_mode_v1).collect::<Vec<_>>();
    let channel = TwoPort::new(
        mixed.iter().map(|s| s[1][1]).collect(),
        mixed.iter().map(|s| s[1][3]).collect(),
        mixed.iter().map(|s| s[3][1]).collect(),
        mixed.iter().map(|s| s[3][3]).collect(),
    )?;
    let include_pcb = scalar_required(values, &["include_pcb", "INCLUDE_PCB"])?;
    if !matches!(include_pcb, 0.0 | 1.0 | 2.0) {
        return Err(DirectRunErrorV1::Parameters(
            "include_pcb must be exactly 0, 1, or 2".to_owned(),
        ));
    }
    let channel = if include_pcb == 0.0 {
        channel
    } else {
        let component_frequency = frequency_hz
            .iter()
            .map(|frequency| frequency.max(f64::EPSILON))
            .collect::<Vec<_>>();
        add_board_v1(
            channel,
            &component_frequency,
            channel_type,
            include_pcb as u8,
            values,
        )?
    };
    let component_frequency = frequency_hz
        .iter()
        .map(|frequency| frequency.max(f64::EPSILON))
        .collect::<Vec<_>>();
    let include_package = boolean(values, &["INC_PACKAGE", "inc_package"])?.ok_or_else(|| {
        DirectRunErrorV1::Parameters("INC_PACKAGE is required for the package FD route".to_owned())
    })?;
    let selected = if include_package {
        selected_case(values, package_case_index)?
    } else {
        0
    };
    let mut result = if include_package {
        // The public S4P route is the admitted DD profile.  Die inclusion is
        // not a JSON wire control; both package sides and the termination
        // calculation receive the same typed profile decision.
        let include_die = true;
        let tx = full_package_mode_v1(
            "TX",
            &component_frequency,
            channel_type,
            selected,
            values,
            include_die,
            false,
        )?;
        let rx = full_package_mode_v1(
            "RX",
            &component_frequency,
            channel_type,
            selected,
            values,
            include_die,
            false,
        )?;
        let z0 = scalar_required(values, &["Z0", "z0"])?;
        let r_die = vector_required(values, &["R_diepad", "r_diepad"], 2)?;
        let tx_sel = selector(values, &["Tx_rd_sel", "tx_rd_sel"])?;
        let rx_sel = selector(values, &["Rx_rd_sel", "rx_rd_sel"])?;
        let ideal_tx = boolean(values, &["IDEAL_TX_TERM", "ideal_tx_term"])?.unwrap_or(false);
        let ideal_rx = boolean(values, &["IDEAL_RX_TERM", "ideal_rx_term"])?.unwrap_or(false);
        let gamma_tx = if ideal_tx || include_pcb == 2.0 {
            0.0
        } else {
            (r_die[tx_sel] - z0) / (r_die[tx_sel] + z0)
        };
        let gamma_rx = if ideal_rx {
            0.0
        } else {
            (r_die[rx_sel] - z0) / (r_die[rx_sel] + z0)
        };
        package_vtf_v1(
            scale_dd_reflections_v1(channel, values)?,
            tx,
            rx,
            gamma_tx,
            gamma_rx,
            ideal_tx,
            ideal_rx,
            include_die,
        )?
    } else {
        channel.s21
    };
    apply_fd_filters_v1(
        &mut result,
        frequency_hz,
        values,
        package_case_index,
        selected,
        include_package,
    )?;
    Ok(result)
}

/// Build the common-mode transfer consumed by the ACCM receiver-noise leaf.
///
/// This is deliberately separate from the DD channel route: the upstream
/// `assemble_r480_dc_vtf` path extracts SDC directly, skips DD kappa/board
/// processing, uses a common-mode TX package and a DD RX package, and keeps
/// the frequency axis intact for the FD-domain receiver-noise consumer. Only
/// the parallel DD channel route performs the final FD-to-TD conversion.
pub(crate) fn s4p_package_dc_vtf_v1(
    frequency_hz: &[f64],
    samples: &[FourPortSMatrixV1],
    values: &BTreeMap<String, ResolvedDefaultV1>,
    channel_type: &str,
    package_case_index: usize,
) -> Result<Vec<Complex64>, DirectRunErrorV1> {
    validate_s4p_axis_v1(frequency_hz, samples)?;
    if !matches!(channel_type, "THRU" | "FEXT" | "NEXT") {
        return Err(DirectRunErrorV1::Unsupported(
            "ACCM common-mode transfer requires a typed channel role".to_owned(),
        ));
    }
    let include_package = boolean(values, &["INC_PACKAGE", "inc_package"])?.ok_or_else(|| {
        DirectRunErrorV1::Parameters("INC_PACKAGE is required for ACCM".to_owned())
    })?;
    if !include_package {
        return Err(DirectRunErrorV1::Unsupported(
            "ACCM requires INC_PACKAGE=1; raw SDC fallback is not admitted".to_owned(),
        ));
    }
    let mixed = samples.iter().map(com_mixed_mode_v1).collect::<Vec<_>>();
    // `_mixed_dc_network` in the pinned source uses SDC=[D(2,1),D(2,3);
    // D(4,1),D(4,3)] (Python zero-based [1,0],[1,2],[3,0],[3,2]).
    let raw = TwoPort::new(
        mixed.iter().map(|sample| sample[1][0]).collect(),
        mixed.iter().map(|sample| sample[1][2]).collect(),
        mixed.iter().map(|sample| sample[3][0]).collect(),
        mixed.iter().map(|sample| sample[3][2]).collect(),
    )?;
    let selected = selected_case(values, package_case_index)?;
    let component_frequency = frequency_hz
        .iter()
        .map(|frequency| frequency.max(f64::EPSILON))
        .collect::<Vec<_>>();
    let tx = full_package_mode_v1(
        "TX",
        &component_frequency,
        channel_type,
        selected,
        values,
        true,
        true,
    )?;
    let rx = full_package_mode_v1(
        "RX",
        &component_frequency,
        channel_type,
        selected,
        values,
        true,
        false,
    )?;
    let z0_common = scalar_required(values, &["Z0", "z0"])? / 2.0;
    let r_die = vector_required(values, &["R_diepad", "r_diepad"], 2)?;
    let tx_sel = selector(values, &["Tx_rd_sel", "tx_rd_sel"])?;
    let rx_sel = selector(values, &["Rx_rd_sel", "rx_rd_sel"])?;
    let ideal_tx = boolean(values, &["IDEAL_TX_TERM", "ideal_tx_term"])?.unwrap_or(false);
    let ideal_rx = boolean(values, &["IDEAL_RX_TERM", "ideal_rx_term"])?.unwrap_or(false);
    let include_pcb = scalar_required(values, &["include_pcb", "INCLUDE_PCB"])?;
    let gamma_tx = if ideal_tx || include_pcb == 2.0 {
        0.0
    } else {
        (r_die[tx_sel] / 2.0 - z0_common) / (r_die[tx_sel] / 2.0 + z0_common)
    };
    let gamma_rx = if ideal_rx {
        0.0
    } else {
        (r_die[rx_sel] / 2.0 - z0_common) / (r_die[rx_sel] / 2.0 + z0_common)
    };
    let mut result = package_vtf_v1(raw, tx, rx, gamma_tx, gamma_rx, ideal_tx, ideal_rx, true)?;
    if let Some(filter) = transmitter_filter_v1(frequency_hz, values)? {
        for (value, filter) in result.iter_mut().zip(filter) {
            *value = mul(*value, filter)?;
        }
    }
    Ok(result)
}

/// Validate the typed controls before the Touchstone rows are materialized.
/// The frequency-dependent matrix/package work is rechecked by the consumer,
/// but malformed case selectors and role amplitudes must never reach parsing
/// and cloning first.
pub(crate) fn validate_s4p_package_controls_v1(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    channel_type: &str,
    package_case_index: usize,
) -> Result<f64, DirectRunErrorV1> {
    if !matches!(channel_type, "THRU" | "FEXT" | "NEXT") {
        return Err(DirectRunErrorV1::Unsupported(
            "package S4P role is not a typed THRU/FEXT/NEXT route".to_owned(),
        ));
    }
    let include_pcb = scalar_required(values, &["include_pcb", "INCLUDE_PCB"])?;
    if !matches!(include_pcb, 0.0 | 1.0 | 2.0) {
        return Err(DirectRunErrorV1::Parameters(
            "include_pcb must be exactly 0, 1, or 2".to_owned(),
        ));
    }
    let include_package = boolean(values, &["INC_PACKAGE", "inc_package"])?
        .ok_or_else(|| DirectRunErrorV1::Parameters("INC_PACKAGE is required".to_owned()))?;
    let selected = if include_package {
        selected_case(values, package_case_index)?
    } else {
        0
    };
    validate_package_preset_shape_v1(values, selected)?;
    package_channel_amplitude_v1(values, channel_type, package_case_index)
}

fn validate_package_preset_shape_v1(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    selected_case: usize,
) -> Result<(), DirectRunErrorV1> {
    let Some(value) = values
        .iter()
        .find(|(key, _)| key.eq_ignore_ascii_case("PKG_Tx_FFE_preset"))
        .map(|(_, value)| value)
    else {
        return Ok(());
    };
    let valid = match value {
        ResolvedDefaultV1::Scalar(value) => value.is_finite(),
        ResolvedDefaultV1::Vector(row) => {
            !row.is_empty()
                && row.len() <= MAX_SEGMENTS
                && row
                    .iter()
                    .all(|value| value.is_finite() && value.abs() <= MAX_PACKAGE_PARAMETER_ABS)
        }
        ResolvedDefaultV1::Matrix(rows) => rows.get(selected_case).is_some_and(|row| {
            !row.is_empty()
                && row.len() <= MAX_SEGMENTS
                && row
                    .iter()
                    .all(|value| value.is_finite() && value.abs() <= MAX_PACKAGE_PARAMETER_ABS)
        }),
        _ => false,
    };
    if !valid {
        return Err(DirectRunErrorV1::Parameters(
            "PKG_Tx_FFE_preset is invalid before S4P materialization".to_owned(),
        ));
    }
    Ok(())
}

fn validate_s4p_axis_v1(
    frequency_hz: &[f64],
    samples: &[FourPortSMatrixV1],
) -> Result<(), DirectRunErrorV1> {
    if frequency_hz.len() != samples.len()
        || frequency_hz.is_empty()
        || frequency_hz.len() > MAX_FREQUENCY_POINTS
    {
        return Err(DirectRunErrorV1::Parameters(
            "package S4P frequency axis and samples must align".to_owned(),
        ));
    }
    if frequency_hz
        .iter()
        .any(|frequency| !frequency.is_finite() || *frequency < 0.0)
        || frequency_hz.windows(2).any(|pair| pair[1] <= pair[0])
    {
        return Err(DirectRunErrorV1::Parameters(
            "package S4P frequency axis must be finite and strictly increasing".to_owned(),
        ));
    }
    Ok(())
}

/// Resolve the source-exact workbook `snpPortsOrder` execution control.
///
/// The pinned reader requires this one-based permutation for trusted
/// workbooks. Keeping validation and matrix application on the same typed
/// path prevents diagnostics or tests from re-reading or guessing the order.
pub(crate) fn configured_snp_port_order_v1(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    trusted_workbook: bool,
) -> Result<Option<[usize; 4]>, DirectRunErrorV1> {
    let folded_keys = values
        .keys()
        .filter(|key| key.eq_ignore_ascii_case("snpPortsOrder"))
        .collect::<Vec<_>>();
    if folded_keys.len() > 1 {
        return Err(DirectRunErrorV1::Parameters(
            "snpPortsOrder case-insensitive aliases must be unique".to_owned(),
        ));
    }
    if !trusted_workbook {
        if !folded_keys.is_empty() {
            return Err(DirectRunErrorV1::Unsupported(
                "snpPortsOrder is a trusted workbook-only control".to_owned(),
            ));
        }
        return Ok(None);
    }
    let Some(value) = values.get("snpPortsOrder") else {
        return Err(DirectRunErrorV1::Parameters(
            "trusted workbook requires source-exact snpPortsOrder".to_owned(),
        ));
    };
    let order = match value {
        ResolvedDefaultV1::Vector(order) => order.clone(),
        _ => {
            return Err(DirectRunErrorV1::Parameters(
                "snpPortsOrder must be a numeric vector".to_owned(),
            ));
        }
    };
    if order.len() != 4
        || order
            .iter()
            .any(|value| !value.is_finite() || value.fract() != 0.0)
        || {
            let mut sorted = order.clone();
            sorted.sort_by(|left, right| left.total_cmp(right));
            sorted != [1.0, 2.0, 3.0, 4.0]
        }
    {
        return Err(DirectRunErrorV1::Parameters(
            "snpPortsOrder must be a one-based four-port permutation".to_owned(),
        ));
    }
    let mut normalized = [0usize; 4];
    for (index, value) in order.iter().enumerate() {
        normalized[index] = *value as usize;
    }
    Ok(Some(normalized))
}

/// Apply the workbook's `snpPortsOrder` before the mixed-mode transform.
///
/// The pinned reader reorders the single-ended matrix before both the DD and
/// SDC paths.  The direct parser owns raw file order, so skipping this step
/// silently produces a plausible but different VTF.  The legacy JSON route is
/// left unchanged when no typed workbook order is present.
pub(crate) fn reorder_s4p_samples_v1(
    samples: &[FourPortSMatrixV1],
    values: &BTreeMap<String, ResolvedDefaultV1>,
    trusted_workbook: bool,
) -> Result<Vec<FourPortSMatrixV1>, DirectRunErrorV1> {
    let Some(order) = configured_snp_port_order_v1(values, trusted_workbook)? else {
        return Ok(samples.to_vec());
    };
    samples
        .iter()
        .map(|sample| {
            let mut reordered = *sample;
            for row in 0..4 {
                for column in 0..4 {
                    reordered[row][column] = sample[order[row] - 1][order[column] - 1];
                }
            }
            Ok(reordered)
        })
        .collect()
}

#[allow(clippy::too_many_arguments)]
fn package_vtf_v1(
    channel: TwoPort,
    tx_package: TwoPort,
    rx_package: TwoPort,
    gamma_tx: f64,
    gamma_rx: f64,
    ideal_tx: bool,
    ideal_rx: bool,
    include_die: bool,
) -> Result<Vec<Complex64>, DirectRunErrorV1> {
    let mut assembled = channel;
    if !ideal_tx {
        assembled = combine(&tx_package, &assembled)?;
    }
    if !ideal_rx {
        let flipped = TwoPort::new(
            rx_package.s22.clone(),
            rx_package.s21.clone(),
            rx_package.s12.clone(),
            rx_package.s11.clone(),
        )?;
        assembled = combine(&assembled, &flipped)?;
    }
    if !include_die {
        return Ok(assembled.s21);
    }
    let mut result = Vec::with_capacity(assembled.s21.len());
    for i in 0..assembled.s21.len() {
        let a = assembled.s11[i];
        let b = assembled.s12[i];
        let c = assembled.s21[i];
        let d = assembled.s22[i];
        let denominator = add(
            add(sub(one()?, scale(a, gamma_tx)?)?, scale(d, -gamma_rx)?)?,
            add(
                scale(mul(c, b)?, -gamma_tx * gamma_rx)?,
                scale(mul(a, d)?, gamma_tx * gamma_rx)?,
            )?,
        )?;
        if zero(denominator) || !finite(denominator) {
            return Err(DirectRunErrorV1::Parameters(
                "package VTF singular termination denominator".to_owned(),
            ));
        }
        result.push(div(
            scale(c, (1.0 - gamma_tx) * (1.0 + gamma_rx))?,
            denominator,
        )?);
    }
    Ok(result)
}

fn transmitter_filter_v1(
    frequency_hz: &[f64],
    values: &BTreeMap<String, ResolvedDefaultV1>,
) -> Result<Option<Vec<Complex64>>, DirectRunErrorV1> {
    let ideal = boolean(values, &["IDEAL_TX_TERM", "ideal_tx_term"])?.unwrap_or(false);
    let filter_type = scalar_required(values, &["T_r_filter_type", "tr_filter_type"])?;
    if !filter_type.is_finite() || filter_type.fract() != 0.0 || !(0.0..=1.0).contains(&filter_type)
    {
        return Err(DirectRunErrorV1::Parameters(
            "T_r_filter_type must be 0 or 1".to_owned(),
        ));
    }
    if !ideal && filter_type != 1.0 {
        return Ok(None);
    }
    let transition_ns = scalar_required(
        values,
        &[
            "transmitter_transition_time",
            "transmitter_transition_time_ns",
        ],
    )?;
    if transition_ns <= 0.0 {
        return Err(DirectRunErrorV1::Parameters(
            "transmitter transition time must be positive for package filter".to_owned(),
        ));
    }
    let measured = scalar_required(values, &["T_r_meas_point", "tr_meas_point"])? == 1.0;
    frequency_hz
        .iter()
        .map(|frequency| {
            let ghz = *frequency / 1.0e9;
            if !ghz.is_finite() || ghz < 0.0 {
                return Err(DirectRunErrorV1::Parameters(
                    "package filter frequency is invalid".to_owned(),
                ));
            }
            if filter_type == 0.0 {
                // R4.80's ideal Gaussian branch is selected by filter type;
                // the measurement point only modifies the type-1 measured
                // transition response.
                let exponent = -(std::f64::consts::PI * ghz * transition_ns / 1.6832).powi(2);
                Complex64::try_new(exponent.exp(), 0.0)
                    .map_err(|_| DirectRunErrorV1::Parameters("package filter overflow".to_owned()))
            } else if measured {
                let inside = 1.0 - 6.51e-3 / transition_ns;
                if inside < 0.0 {
                    return Err(DirectRunErrorV1::Parameters(
                        "package filter transition is too short for measured point".to_owned(),
                    ));
                }
                let coefficient = 1.9466 + 7.12 * inside.sqrt();
                let x = ghz * coefficient * transition_ns;
                let j = Complex64::try_new(0.0, 1.0).map_err(|_| {
                    DirectRunErrorV1::Parameters("package filter constant".to_owned())
                })?;
                let x1 = Complex64::try_new(x, 0.0).map_err(|_| {
                    DirectRunErrorV1::Parameters("package filter overflow".to_owned())
                })?;
                let x2 = mul(x1, x1)?;
                let x3 = mul(x2, x1)?;
                let x4 = mul(x3, x1)?;
                let denominator = add(
                    add(
                        add(add(x4, scale(mul(j, x3)?, -10.0)?)?, scale(x2, -45.0)?)?,
                        scale(mul(j, x1)?, 105.0)?,
                    )?,
                    Complex64::try_new(105.0, 0.0).map_err(|_| {
                        DirectRunErrorV1::Parameters("package filter constant".to_owned())
                    })?,
                )?;
                div(
                    Complex64::try_new(105.0, 0.0).map_err(|_| {
                        DirectRunErrorV1::Parameters("package filter constant".to_owned())
                    })?,
                    denominator,
                )
            } else {
                let exponent = -2.0 * (std::f64::consts::PI * ghz * transition_ns / 1.6832).powi(2);
                let phase = -2.0 * std::f64::consts::PI * ghz * transition_ns * 3.0;
                Complex64::try_new(exponent.exp() * phase.cos(), exponent.exp() * phase.sin())
                    .map_err(|_| DirectRunErrorV1::Parameters("package filter overflow".to_owned()))
            }
        })
        .collect::<Result<Vec<_>, _>>()
        .map(Some)
}

fn scale_dd_reflections_v1(
    channel: TwoPort,
    values: &BTreeMap<String, ResolvedDefaultV1>,
) -> Result<TwoPort, DirectRunErrorV1> {
    let kappa1 = scalar_required(values, &["kappa1"])?;
    let kappa2 = scalar_required(values, &["kappa2"])?;
    TwoPort::new(
        channel
            .s11
            .into_iter()
            .map(|value| scale(value, kappa1))
            .collect::<Result<Vec<_>, _>>()?,
        channel.s12,
        channel.s21,
        channel
            .s22
            .into_iter()
            .map(|value| scale(value, kappa2))
            .collect::<Result<Vec<_>, _>>()?,
    )
}

fn apply_fd_filters_v1(
    values_fd: &mut [Complex64],
    frequency_hz: &[f64],
    values: &BTreeMap<String, ResolvedDefaultV1>,
    package_case_index: usize,
    selected_case: usize,
    include_package: bool,
) -> Result<(), DirectRunErrorV1> {
    if values_fd.len() != frequency_hz.len() {
        return Err(DirectRunErrorV1::Parameters(
            "package FD filter axis mismatch".to_owned(),
        ));
    }
    if include_package && let Some(filter) = transmitter_filter_v1(frequency_hz, values)? {
        for (value, filter) in values_fd.iter_mut().zip(filter) {
            *value = mul(*value, filter)?;
        }
    }
    let include_filter =
        boolean(values, &["INCLUDE_FILTER", "include_filter"])?.ok_or_else(|| {
            DirectRunErrorV1::Parameters(
                "INCLUDE_FILTER is required for the package FD route".to_owned(),
            )
        })?;
    let get_fd = boolean(values, &["GET_FD", "get_fd"])?.ok_or_else(|| {
        DirectRunErrorV1::Parameters("GET_FD is required for the package FD route".to_owned())
    })?;
    if !include_filter || !get_fd {
        return Ok(());
    }
    let baud = scalar_required(values, &["fb", "baud_hz"])?;
    let order = scalar_required(values, &["BTorder", "btorder"])?;
    if order < 0.0 || order.fract() != 0.0 || order > 32.0 {
        return Err(DirectRunErrorV1::Parameters(
            "BTorder is outside the bounded receiver filter range".to_owned(),
        ));
    }
    let bt_cutoff = scalar_required(values, &["fb_BT_cutoff", "bessel_cutoff_multiplier"])?;
    let bw_cutoff = scalar_required(values, &["fb_BW_cutoff", "butterworth_cutoff_multiplier"])?;
    let bessel = boolean(values, &["Bessel_Thomson", "bessel_thomson"])?.ok_or_else(|| {
        DirectRunErrorV1::Parameters(
            "Bessel_Thomson control is required with INCLUDE_FILTER".to_owned(),
        )
    })?;
    let butterworth = boolean(values, &["Butterworth", "butterworth"])?.ok_or_else(|| {
        DirectRunErrorV1::Parameters(
            "Butterworth control is required with INCLUDE_FILTER".to_owned(),
        )
    })?;
    let raised = boolean(values, &["Raised_Cosine", "raised_cosine"])?.ok_or_else(|| {
        DirectRunErrorV1::Parameters(
            "Raised_Cosine control is required with INCLUDE_FILTER".to_owned(),
        )
    })?;
    let start = scalar_required(values, &["RC_Start", "rc_start"])?;
    let end = scalar_required(values, &["RC_end", "rc_end"])?;
    let bt = bessel_thomson_filter_v1(frequency_hz, order as usize, bt_cutoff, baud, bessel)
        .map_err(|error| {
            DirectRunErrorV1::Parameters(format!("Bessel receiver filter: {error:?}"))
        })?;
    let bw =
        butterworth_filter_v1(frequency_hz, bw_cutoff, baud, butterworth).map_err(|error| {
            DirectRunErrorV1::Parameters(format!("Butterworth receiver filter: {error:?}"))
        })?;
    let rc = raised_cosine_filter_v1(frequency_hz, start, end, raised).map_err(|error| {
        DirectRunErrorV1::Parameters(format!("raised-cosine receiver filter: {error:?}"))
    })?;
    let preset = package_preset_v1(values, package_case_index, selected_case)?;
    let ffe = package_preset_response_v1(frequency_hz, baud, &preset)?;
    for index in 0..values_fd.len() {
        let receiver = mul(
            mul(bt[index], bw[index])?,
            Complex64::try_new(rc[index], 0.0).map_err(|_| {
                DirectRunErrorV1::Parameters("receiver filter is non-finite".to_owned())
            })?,
        )?;
        values_fd[index] = mul(mul(values_fd[index], receiver)?, ffe[index])?;
    }
    Ok(())
}

fn package_preset_v1(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    package_case_index: usize,
    selected_case: usize,
) -> Result<Vec<f64>, DirectRunErrorV1> {
    let Some(value) = values
        .iter()
        .find(|(key, _)| key.eq_ignore_ascii_case("PKG_Tx_FFE_preset"))
        .map(|(_, value)| value)
    else {
        return Ok(vec![0.0]);
    };
    let result = match value {
        ResolvedDefaultV1::Scalar(value) => vec![*value],
        ResolvedDefaultV1::Vector(values) => {
            if values.is_empty() || values.len() > MAX_SEGMENTS {
                return Err(DirectRunErrorV1::Parameters(
                    "PKG_Tx_FFE_preset vector shape exceeds the admitted tap budget".to_owned(),
                ));
            }
            values
                .iter()
                .all(|value| value.is_finite() && value.abs() <= MAX_PACKAGE_PARAMETER_ABS)
                .then(|| values.clone())
                .ok_or_else(|| {
                    DirectRunErrorV1::Parameters("PKG_Tx_FFE_preset is invalid".to_owned())
                })?
        }
        ResolvedDefaultV1::Matrix(rows) => {
            let row = rows.get(selected_case).ok_or_else(|| {
                DirectRunErrorV1::Parameters(format!(
                    "package preset case {package_case_index} is outside PKG_Tx_FFE_preset"
                ))
            })?;
            if row.is_empty() || row.len() > MAX_SEGMENTS {
                return Err(DirectRunErrorV1::Parameters(
                    "PKG_Tx_FFE_preset row shape exceeds the admitted tap budget".to_owned(),
                ));
            }
            row.iter()
                .all(|value| value.is_finite() && value.abs() <= MAX_PACKAGE_PARAMETER_ABS)
                .then(|| row.clone())
                .ok_or_else(|| {
                    DirectRunErrorV1::Parameters("PKG_Tx_FFE_preset is invalid".to_owned())
                })?
        }
        _ => {
            return Err(DirectRunErrorV1::Parameters(
                "PKG_Tx_FFE_preset must be numeric".to_owned(),
            ));
        }
    };
    if result.is_empty()
        || result.len() > MAX_SEGMENTS
        || result
            .iter()
            .any(|value| !value.is_finite() || value.abs() > MAX_PACKAGE_PARAMETER_ABS)
    {
        return Err(DirectRunErrorV1::Parameters(
            "PKG_Tx_FFE_preset is invalid".to_owned(),
        ));
    }
    Ok(result)
}

pub(crate) fn package_channel_amplitude_v1(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    channel_type: &str,
    package_case_index: usize,
) -> Result<f64, DirectRunErrorV1> {
    let key = match channel_type {
        "THRU" => "a_thru",
        "FEXT" => "a_fext",
        "NEXT" => "a_next",
        _ => {
            return Err(DirectRunErrorV1::Unsupported(
                "package amplitude role must be THRU, FEXT, or NEXT".to_owned(),
            ));
        }
    };
    let Some(value) = values
        .iter()
        .find(|(candidate, _)| candidate.eq_ignore_ascii_case(key))
        .map(|(_, value)| value)
    else {
        return Err(DirectRunErrorV1::Parameters(format!(
            "resolved package amplitude {key} is missing"
        )));
    };
    let wc_portz = boolean(values, &["WC_PORTZ", "wc_portz"])?.unwrap_or(false);
    let selected = if wc_portz {
        selector(values, &["Tx_rd_sel", "tx_rd_sel"])?
    } else {
        selected_case(values, package_case_index)?
    };
    let amplitude = match value {
        ResolvedDefaultV1::Scalar(value) if selected == 0 => *value,
        ResolvedDefaultV1::Scalar(_) => {
            return Err(DirectRunErrorV1::Parameters(format!(
                "{key} scalar amplitude is only valid for selected package case 0"
            )));
        }
        ResolvedDefaultV1::Vector(values) => values.get(selected).copied().ok_or_else(|| {
            DirectRunErrorV1::Parameters(format!(
                "{key} has no amplitude for selected package case {selected}"
            ))
        })?,
        ResolvedDefaultV1::Matrix(rows) => rows
            .get(selected)
            .and_then(|row| (row.len() == 1).then_some(row[0]))
            .ok_or_else(|| {
                DirectRunErrorV1::Parameters(format!(
                    "{key} must provide one scalar per selected package case"
                ))
            })?,
        _ => {
            return Err(DirectRunErrorV1::Parameters(format!(
                "{key} must be a finite scalar/vector/matrix"
            )));
        }
    };
    if !amplitude.is_finite() || amplitude.abs() > MAX_PACKAGE_PARAMETER_ABS {
        return Err(DirectRunErrorV1::Parameters(format!(
            "{key} amplitude is non-finite or outside the bounded range"
        )));
    }
    Ok(amplitude)
}

#[cfg(test)]
fn package_case_amplitude_v1(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    channel_type: &str,
    selected_case: usize,
) -> Result<f64, DirectRunErrorV1> {
    package_channel_amplitude_v1(values, channel_type, selected_case)
}

fn package_preset_response_v1(
    frequency_hz: &[f64],
    baud_hz: f64,
    taps: &[f64],
) -> Result<Vec<Complex64>, DirectRunErrorV1> {
    if baud_hz <= 0.0 || taps.is_empty() || taps.len() > MAX_SEGMENTS {
        return Err(DirectRunErrorV1::Parameters(
            "package preset FFE requires positive fb and taps".to_owned(),
        ));
    }
    let work = frequency_hz.len().checked_mul(taps.len()).ok_or_else(|| {
        DirectRunErrorV1::Parameters("package preset work budget overflow".to_owned())
    })?;
    if work > 16_000_000 {
        return Err(DirectRunErrorV1::Parameters(
            "package preset work budget exceeded".to_owned(),
        ));
    }
    if taps.iter().all(|tap| *tap == 0.0) {
        return Ok(vec![
            Complex64::try_new(1.0, 0.0).map_err(|_| {
                DirectRunErrorV1::Parameters("package preset identity response".to_owned())
            })?;
            frequency_hz.len()
        ]);
    }
    // Match numpy.argmax: ties retain the first maximum.
    let mut cursor = 0usize;
    for index in 1..taps.len() {
        if taps[index] > taps[cursor] {
            cursor = index;
        }
    }
    frequency_hz
        .iter()
        .map(|frequency| {
            let mut response = Complex64::try_new(0.0, 0.0)
                .map_err(|_| DirectRunErrorV1::Parameters("package preset response".to_owned()))?;
            for (index, tap) in taps.iter().enumerate() {
                let phase =
                    -2.0 * std::f64::consts::PI * (index as f64 - cursor as f64) * *frequency
                        / baud_hz;
                response = add(
                    response,
                    Complex64::try_new(*tap * phase.cos(), *tap * phase.sin()).map_err(|_| {
                        DirectRunErrorV1::Parameters("package preset response overflow".to_owned())
                    })?,
                )?;
            }
            Ok(response)
        })
        .collect()
}

fn combine(first: &TwoPort, second: &TwoPort) -> Result<TwoPort, DirectRunErrorV1> {
    let mut out = (
        Vec::with_capacity(first.s11.len()),
        Vec::with_capacity(first.s11.len()),
        Vec::with_capacity(first.s11.len()),
        Vec::with_capacity(first.s11.len()),
    );
    for i in 0..first.s11.len() {
        let denominator = sub(one()?, mul(first.s22[i], second.s11[i])?)?;
        if zero(denominator) {
            return Err(DirectRunErrorV1::Parameters(
                "package TwoPort cascade singular denominator".to_owned(),
            ));
        }
        out.0.push(add(
            first.s11[i],
            div(
                mul(mul(first.s12[i], first.s21[i])?, second.s11[i])?,
                denominator,
            )?,
        )?);
        out.1
            .push(div(mul(first.s12[i], second.s12[i])?, denominator)?);
        out.2.push(div(
            mul(mul(second.s21[i], first.s21[i])?, one()?)?,
            denominator,
        )?);
        out.3.push(add(
            second.s22[i],
            div(
                mul(mul(second.s12[i], second.s21[i])?, first.s22[i])?,
                denominator,
            )?,
        )?);
    }
    TwoPort::new(out.0, out.1, out.2, out.3)
}

/// Cascade the source-load adjustment used by normal r4.80 TDR.
///
/// Differential TDR uses a 100 ohm reference.  A source resistance above the
/// reference is represented as a series element; a lower resistance is
/// represented as the equivalent shunt element.  Keeping this as a two-port
/// cascade, rather than altering S11/S21 directly, preserves the same order
/// of operations as the source `SL` helper.
fn source_load_v1(
    channel: TwoPort,
    source_resistance_ohm: f64,
) -> Result<TwoPort, DirectRunErrorV1> {
    const ZREF_OHM: f64 = 100.0;
    if !(source_resistance_ohm.is_finite() && source_resistance_ohm > 0.0) {
        return Err(DirectRunErrorV1::Parameters(
            "TDR source resistance must be finite and positive".to_owned(),
        ));
    }
    if source_resistance_ohm == ZREF_OHM {
        return Ok(channel);
    }
    let (s11, s21) = if source_resistance_ohm > ZREF_OHM {
        let series = source_resistance_ohm - ZREF_OHM;
        let denominator = series + 2.0 * ZREF_OHM;
        if !(denominator.is_finite() && denominator > 0.0) {
            return Err(DirectRunErrorV1::Parameters(
                "TDR source-load series denominator is invalid".to_owned(),
            ));
        }
        (series / denominator, 2.0 * ZREF_OHM / denominator)
    } else {
        let parallel = source_resistance_ohm * ZREF_OHM / (ZREF_OHM - source_resistance_ohm);
        let denominator = ZREF_OHM / parallel + 2.0;
        if !(parallel.is_finite() && parallel > 0.0 && denominator.is_finite() && denominator > 0.0)
        {
            return Err(DirectRunErrorV1::Parameters(
                "TDR source-load shunt denominator is invalid".to_owned(),
            ));
        }
        (-ZREF_OHM / (parallel * denominator), 2.0 / denominator)
    };
    let source = TwoPort::new(
        vec![
            Complex64::try_new(s11, 0.0).map_err(|_| {
                DirectRunErrorV1::Parameters("non-finite TDR source-load S11".to_owned())
            })?;
            channel.s11.len()
        ],
        vec![
            Complex64::try_new(s21, 0.0).map_err(|_| {
                DirectRunErrorV1::Parameters("non-finite TDR source-load S21".to_owned())
            })?;
            channel.s11.len()
        ],
        vec![
            Complex64::try_new(s21, 0.0).map_err(|_| {
                DirectRunErrorV1::Parameters("non-finite TDR source-load S21".to_owned())
            })?;
            channel.s11.len()
        ],
        vec![
            Complex64::try_new(s11, 0.0).map_err(|_| {
                DirectRunErrorV1::Parameters("non-finite TDR source-load S22".to_owned())
            })?;
            channel.s11.len()
        ],
    )?;
    combine(&source, &channel)
}

fn full_package_mode_v1(
    side: &str,
    frequency: &[f64],
    channel: &str,
    selected: usize,
    values: &BTreeMap<String, ResolvedDefaultV1>,
    include_die: bool,
    common_mode: bool,
) -> Result<TwoPort, DirectRunErrorV1> {
    let side_index = match side {
        "TX" => 0,
        "RX" => 1,
        _ => {
            return Err(DirectRunErrorV1::Parameters(
                "package side must be TX or RX".to_owned(),
            ));
        }
    };
    let z_pkg = matrix_required(values, &["pkg_Z_c", "package_Z_c"])?;
    if z_pkg.len() != 2 {
        return Err(DirectRunErrorV1::Parameters(
            "pkg_Z_c must have TX and RX rows".to_owned(),
        ));
    }
    let lengths_key = match (side, channel) {
        ("TX", "THRU") => &["z_p_tx_cases"][..],
        ("TX", "FEXT") => &["z_p_fext_cases"][..],
        ("TX", "NEXT") => &["z_p_next_cases"][..],
        (_, "THRU") => &["z_p_rx_cases"][..],
        (_, "FEXT") | (_, "NEXT") => &["z_p_rx_cases"][..],
        _ => {
            return Err(DirectRunErrorV1::Parameters(
                "unsupported package channel type".to_owned(),
            ));
        }
    };
    let lengths_all = matrix_required(values, lengths_key)?;
    let selected_lengths = lengths_all.get(selected).ok_or_else(|| {
        DirectRunErrorV1::Parameters("pkg_len_select case is outside package lengths".to_owned())
    })?;
    if selected_lengths.is_empty()
        || selected_lengths.len() > MAX_SEGMENTS
        || z_pkg[side_index].len() != selected_lengths.len()
    {
        return Err(DirectRunErrorV1::Parameters(
            "package segment dimensions do not align".to_owned(),
        ));
    }
    let work = frequency
        .len()
        .checked_mul(selected_lengths.len())
        .ok_or_else(|| {
            DirectRunErrorV1::Parameters("package cascade work budget overflow".to_owned())
        })?;
    if work > 16_000_000 {
        return Err(DirectRunErrorV1::Parameters(
            "package cascade work budget exceeded".to_owned(),
        ));
    }
    let lengths = selected_lengths.to_vec();
    let c_die = if include_die {
        chain(values, &["C_diepad"], side_index)?
    } else {
        vec![0.0]
    };
    let l_comp = if include_die {
        chain(values, &["L_comp"], side_index)?
    } else {
        vec![0.0]
    };
    if c_die.len() != l_comp.len() {
        return Err(DirectRunErrorV1::Parameters(
            "C_diepad and L_comp chains must align".to_owned(),
        ));
    }
    let c_bump = if include_die {
        vector_required(values, &["C_bump"], 2)?[side_index]
    } else {
        0.0
    };
    let c_v = vector_required(values, &["C_v"], 2)?[side_index];
    let c_pkg_board = vector_required(values, &["C_pkg_board"], 2)?[side_index];
    let gamma = vector_required(values, &["pkg_gamma0_a1_a2"], 3)?;
    let z0 = scalar_required(values, &["Z0", "z0"])?;
    let tau = scalar_required(values, &["pkg_tau"])?;
    let expanded_segments = lengths
        .len()
        .checked_add(c_die.len().saturating_sub(1))
        .ok_or_else(|| {
            DirectRunErrorV1::Parameters("package expanded segment budget overflow".to_owned())
        })?;
    if expanded_segments > 67 {
        return Err(DirectRunErrorV1::Parameters(
            "package expanded segment budget exceeded".to_owned(),
        ));
    }
    let expanded_work = frequency
        .len()
        .checked_mul(expanded_segments)
        .ok_or_else(|| {
            DirectRunErrorV1::Parameters("expanded package cascade work budget overflow".to_owned())
        })?;
    if expanded_work > 16_000_000 {
        return Err(DirectRunErrorV1::Parameters(
            "expanded package cascade work budget exceeded".to_owned(),
        ));
    }
    let mut pad = c_die.clone();
    let mut inductance = l_comp.clone();
    let mut seg_lengths = lengths.clone();
    let mut zc = z_pkg[side_index].clone();
    let mut bump = vec![0.0; seg_lengths.len()];
    let mut ball = vec![0.0; seg_lengths.len()];
    if seg_lengths.len() == 1 {
        bump[0] = c_bump;
        ball[0] = c_pkg_board;
    } else if seg_lengths.len() == 4 {
        bump[0] = c_bump;
        ball[2] = c_v;
        ball[3] = c_pkg_board;
    } else {
        return Err(DirectRunErrorV1::Parameters(
            "only one or four package segments are supported".to_owned(),
        ));
    }
    if seg_lengths.len() == 4 {
        pad.extend([0.0; 3]);
        inductance.extend([0.0; 3]);
    }
    if c_die.len() > 1 {
        let extra = c_die.len() - 1;
        let mut zeros = vec![0.0; extra];
        zeros.append(&mut seg_lengths);
        seg_lengths = zeros;
        let mut zeros = vec![0.0; extra];
        zeros.append(&mut zc);
        zc = zeros;
        let mut zeros = vec![0.0; extra];
        zeros.append(&mut bump);
        bump = zeros;
        let mut zeros = vec![0.0; extra];
        zeros.append(&mut ball);
        ball = zeros;
    }
    if common_mode {
        if side_index != 0 {
            return Err(DirectRunErrorV1::Parameters(
                "common-mode package transform is only valid for TX".to_owned(),
            ));
        }
        zc.iter_mut().for_each(|value| *value *= 2.0);
        pad.iter_mut().for_each(|value| *value *= 2.0);
        bump.iter_mut().for_each(|value| *value *= 2.0);
        ball.iter_mut().for_each(|value| *value *= 2.0);
        inductance.iter_mut().for_each(|value| *value /= 2.0);
    }
    let mut result = None;
    for i in 0..seg_lengths.len() {
        let segment = make_package(
            frequency,
            seg_lengths[i],
            pad[i],
            ball[i],
            zc[i],
            if common_mode { z0 / 2.0 } else { z0 },
            &gamma,
            tau,
            inductance[i],
            bump[i],
        )?;
        result = Some(match result {
            None => segment,
            Some(previous) => combine(&previous, &segment)?,
        });
    }
    result.ok_or_else(|| DirectRunErrorV1::Parameters("empty package cascade".to_owned()))
}

#[allow(clippy::too_many_arguments)]
fn make_package(
    frequency: &[f64],
    length: f64,
    c_pad: f64,
    c_ball: f64,
    zc: f64,
    z0: f64,
    gamma: &[f64],
    tau: f64,
    l_comp: f64,
    c_bump: f64,
) -> Result<TwoPort, DirectRunErrorV1> {
    let pad = shunt(frequency, c_pad, z0)?;
    let pad = if l_comp > 0.0 {
        combine(&pad, &series(frequency, l_comp, z0)?)?
    } else {
        pad
    };
    let pad = if c_bump > 0.0 {
        combine(&pad, &shunt(frequency, c_bump, z0)?)?
    } else {
        pad
    };
    let line = synth_line(frequency, zc, z0, gamma, tau, length)?;
    combine(&combine(&pad, &line)?, &shunt(frequency, c_ball, z0)?)
}

fn shunt(frequency: &[f64], capacitance: f64, z0: f64) -> Result<TwoPort, DirectRunErrorV1> {
    let mut a = Vec::with_capacity(frequency.len());
    let mut b = Vec::with_capacity(frequency.len());
    for &f in frequency {
        let x = 2.0 * std::f64::consts::PI * f * capacitance * z0;
        let d = Complex64::try_new(2.0, x)
            .map_err(|_| DirectRunErrorV1::Parameters("non-finite package shunt".to_owned()))?;
        let s = div(
            Complex64::try_new(0.0, -x)
                .map_err(|_| DirectRunErrorV1::Parameters("non-finite package shunt".to_owned()))?,
            d,
        )?;
        let t = scale(div(one()?, d)?, 2.0)?;
        a.push(s);
        b.push(t);
    }
    TwoPort::new(a.clone(), b.clone(), b, a)
}

fn series(frequency: &[f64], inductance: f64, z0: f64) -> Result<TwoPort, DirectRunErrorV1> {
    let mut a = Vec::with_capacity(frequency.len());
    let mut b = Vec::with_capacity(frequency.len());
    for &f in frequency {
        let x = 2.0 * std::f64::consts::PI * f * inductance / z0;
        let d = Complex64::try_new(2.0, x)
            .map_err(|_| DirectRunErrorV1::Parameters("non-finite package series".to_owned()))?;
        let s = div(
            Complex64::try_new(0.0, x).map_err(|_| {
                DirectRunErrorV1::Parameters("non-finite package series".to_owned())
            })?,
            d,
        )?;
        let t = scale(div(one()?, d)?, 2.0)?;
        a.push(s);
        b.push(t);
    }
    TwoPort::new(a.clone(), b.clone(), b, a)
}

fn synth_line(
    frequency: &[f64],
    zc: f64,
    z0: f64,
    coefficients: &[f64],
    tau: f64,
    length: f64,
) -> Result<TwoPort, DirectRunErrorV1> {
    if coefficients.len() != 3 || z0 <= 0.0 || length < 0.0 || (length > 0.0 && zc <= 0.0) {
        return Err(DirectRunErrorV1::Parameters(
            "invalid package transmission line".to_owned(),
        ));
    }
    let mut s11 = Vec::with_capacity(frequency.len());
    let mut s21 = Vec::with_capacity(frequency.len());
    let rho = if length == 0.0 {
        0.0
    } else {
        (zc - 2.0 * z0) / (zc + 2.0 * z0)
    };
    for &f in frequency {
        let ghz = f / 1.0e9;
        let gamma = if ghz == 0.0 {
            Complex64::try_new(coefficients[0], 0.0).map_err(|_| {
                DirectRunErrorV1::Parameters("non-finite package line gamma".to_owned())
            })?
        } else {
            let root = ghz.sqrt();
            let g1 = Complex64::try_new(coefficients[1] * root, coefficients[1] * root).map_err(
                |_| DirectRunErrorV1::Parameters("non-finite package line gamma".to_owned()),
            )?;
            let log = ghz.ln();
            let g2 = Complex64::try_new(
                coefficients[2] * ghz,
                coefficients[2] * ghz * (-2.0 / std::f64::consts::PI * log),
            )
            .map_err(|_| {
                DirectRunErrorV1::Parameters("non-finite package line gamma".to_owned())
            })?;
            add(
                Complex64::try_new(coefficients[0], 0.0).map_err(|_| {
                    DirectRunErrorV1::Parameters("non-finite package line gamma".to_owned())
                })?,
                add(
                    g1,
                    add(
                        g2,
                        Complex64::try_new(0.0, 2.0 * std::f64::consts::PI * tau * ghz).map_err(
                            |_| {
                                DirectRunErrorV1::Parameters(
                                    "non-finite package line gamma".to_owned(),
                                )
                            },
                        )?,
                    )?,
                )?,
            )?
        };
        let e = exp_neg(gamma, length)?;
        let d = sub(one()?, scale(mul(e, e)?, rho * rho)?)?;
        if zero(d) {
            return Err(DirectRunErrorV1::Parameters(
                "singular package line denominator".to_owned(),
            ));
        }
        s11.push(scale(div(sub(one()?, mul(e, e)?)?, d)?, rho)?);
        s21.push(div(scale(e, 1.0 - rho * rho)?, d)?);
    }
    TwoPort::new(s11.clone(), s21.clone(), s21, s11)
}

fn add_board_v1(
    channel: TwoPort,
    frequency: &[f64],
    channel_type: &str,
    include_pcb: u8,
    values: &BTreeMap<String, ResolvedDefaultV1>,
) -> Result<TwoPort, DirectRunErrorV1> {
    if !matches!(include_pcb, 1 | 2) {
        return Err(DirectRunErrorV1::Parameters(
            "include_pcb must be 1 or 2 when adding a board".to_owned(),
        ));
    }
    let c0 = vector_required(values, &["C_0", "c_0"], 2)?;
    let c1 = vector_required(values, &["C_1", "c_1"], 2)?;
    let zc = vector_required(values, &["brd_Z_c", "board_Z_c"], 2)?;
    let gamma = vector_required(values, &["brd_gamma0_a1_a2", "board_gamma0_a1_a2"], 3)?;
    let z0 = scalar_required(values, &["Z0", "z0"])?;
    let tau = scalar_required(values, &["brd_tau", "board_tau"])?;
    let tx_length = match channel_type.to_ascii_uppercase().as_str() {
        "THRU" => scalar_required(values, &["z_bp_tx", "z_bp_tx_mm"])?,
        "NEXT" => scalar_required(values, &["z_bp_rx", "z_bp_rx_mm"])?,
        "FEXT" => scalar_required(values, &["z_bp_fext", "z_bp_fext_mm"])?,
        _ => {
            return Err(DirectRunErrorV1::Parameters(
                "unsupported board channel type".to_owned(),
            ));
        }
    };
    let rx_length = match channel_type.to_ascii_uppercase().as_str() {
        "THRU" | "FEXT" => scalar_required(values, &["z_bp_rx", "z_bp_rx_mm"])?,
        "NEXT" => scalar_required(values, &["z_bp_next", "z_bp_next_mm"])?,
        _ => {
            return Err(DirectRunErrorV1::Parameters(
                "unsupported board channel type".to_owned(),
            ));
        }
    };
    let tx = combine(
        &combine(
            &shunt(frequency, c0[0], z0)?,
            &synth_line(frequency, zc[0], z0, &gamma, tau, tx_length)?,
        )?,
        &shunt(frequency, c1[0], z0)?,
    )?;
    let rx = combine(
        &combine(
            &shunt(frequency, c1[1], z0)?,
            &synth_line(frequency, zc[1], z0, &gamma, tau, rx_length)?,
        )?,
        &shunt(frequency, c0[1], z0)?,
    )?;
    match include_pcb {
        1 => combine(&combine(&tx, &channel)?, &rx),
        2 => combine(&channel, &rx),
        _ => unreachable!(),
    }
}

fn selected_case(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    index: usize,
) -> Result<usize, DirectRunErrorV1> {
    let selected = vector_any(values, &["pkg_len_select"])?;
    let value = *selected.get(index).ok_or_else(|| {
        DirectRunErrorV1::Parameters("pkg_len_select index is outside selected cases".to_owned())
    })?;
    if value < 1.0 || value.fract() != 0.0 {
        return Err(DirectRunErrorV1::Parameters(
            "pkg_len_select must contain positive integer one-based indices".to_owned(),
        ));
    }
    Ok(value as usize - 1)
}

fn unique_alias_value<'a>(
    values: &'a BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
) -> Result<Option<&'a ResolvedDefaultV1>, DirectRunErrorV1> {
    let matches: Vec<&ResolvedDefaultV1> = values
        .iter()
        .filter(|(key, _)| names.iter().any(|name| key.eq_ignore_ascii_case(name)))
        .map(|(_, value)| value)
        .collect();
    let Some(first) = matches.first().copied() else {
        return Ok(None);
    };
    if matches.iter().any(|value| *value != first) {
        return Err(DirectRunErrorV1::Parameters(format!(
            "case-insensitive package aliases conflict for {}",
            names[0]
        )));
    }
    Ok(Some(first))
}

fn scalar(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
) -> Result<Option<f64>, DirectRunErrorV1> {
    let Some(value) = unique_alias_value(values, names)? else {
        return Ok(None);
    };
    match value {
        ResolvedDefaultV1::Scalar(v) if v.is_finite() => Ok(Some(*v)),
        _ => Ok(None),
    }
}
fn scalar_required(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
) -> Result<f64, DirectRunErrorV1> {
    scalar(values, names)?.ok_or_else(|| {
        DirectRunErrorV1::Parameters(format!("missing finite package scalar {}", names[0]))
    })
}
fn vector_required(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
    expected: usize,
) -> Result<Vec<f64>, DirectRunErrorV1> {
    let result = vector_any(values, names)?;
    if result.len() != expected {
        return Err(DirectRunErrorV1::Parameters(format!(
            "package {} must have {expected} values",
            names[0]
        )));
    }
    Ok(result)
}
fn vector_any(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
) -> Result<Vec<f64>, DirectRunErrorV1> {
    let value = unique_alias_value(values, names)?.ok_or_else(|| {
        DirectRunErrorV1::Parameters(format!("missing package vector {}", names[0]))
    })?;
    let result = match value {
        ResolvedDefaultV1::Scalar(v) => Ok(vec![*v]),
        ResolvedDefaultV1::Vector(v) => Ok(v.clone()),
        _ => Err(DirectRunErrorV1::Parameters(format!(
            "package {} must be numeric vector",
            names[0]
        ))),
    }?;
    if result.is_empty()
        || result
            .iter()
            .any(|v| !v.is_finite() || v.abs() > MAX_PACKAGE_PARAMETER_ABS)
    {
        return Err(DirectRunErrorV1::Parameters(format!(
            "package {} contains non-finite or empty values",
            names[0]
        )));
    }
    Ok(result)
}
fn matrix_required(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
) -> Result<Vec<Vec<f64>>, DirectRunErrorV1> {
    let value = unique_alias_value(values, names)?.ok_or_else(|| {
        DirectRunErrorV1::Parameters(format!("missing package matrix {}", names[0]))
    })?;
    let result = match value {
        ResolvedDefaultV1::Matrix(v) => Ok(v.clone()),
        _ => Err(DirectRunErrorV1::Parameters(format!(
            "package {} must be numeric matrix",
            names[0]
        ))),
    }?;
    let width = result.first().map_or(0, Vec::len);
    if result.is_empty()
        || width == 0
        || result.iter().any(|row| {
            row.len() != width
                || row
                    .iter()
                    .any(|v| !v.is_finite() || v.abs() > MAX_PACKAGE_PARAMETER_ABS)
        })
    {
        return Err(DirectRunErrorV1::Parameters(format!(
            "package {} must be a finite rectangular matrix",
            names[0]
        )));
    }
    Ok(result)
}
fn chain(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
    side: usize,
) -> Result<Vec<f64>, DirectRunErrorV1> {
    let value = unique_alias_value(values, names)?.ok_or_else(|| {
        DirectRunErrorV1::Parameters(format!("missing package chain {}", names[0]))
    })?;
    let result = match value {
        ResolvedDefaultV1::Vector(v) if v.len() == 2 => vec![v[side]],
        ResolvedDefaultV1::Matrix(v) if v.len() == 2 => v[side].clone(),
        _ => Err(DirectRunErrorV1::Parameters(format!(
            "package {} must be TX/RX chain",
            names[0]
        )))?,
    };
    if result.is_empty()
        || result.len() > MAX_SEGMENTS
        || result
            .iter()
            .any(|v| !v.is_finite() || v.abs() > MAX_PACKAGE_PARAMETER_ABS)
    {
        return Err(DirectRunErrorV1::Parameters(format!(
            "package {} chain is invalid",
            names[0]
        )));
    }
    Ok(result)
}
fn selector(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
) -> Result<usize, DirectRunErrorV1> {
    let v = scalar_required(values, names)?;
    if !(1.0..=2.0).contains(&v) || v.fract() != 0.0 {
        return Err(DirectRunErrorV1::Parameters(
            "package termination selector must be 1 or 2".to_owned(),
        ));
    }
    Ok(v as usize - 1)
}
fn boolean(
    values: &BTreeMap<String, ResolvedDefaultV1>,
    names: &[&str],
) -> Result<Option<bool>, DirectRunErrorV1> {
    let Some(value) = unique_alias_value(values, names)? else {
        return Ok(None);
    };
    match value {
        ResolvedDefaultV1::Boolean(v) => Ok(Some(*v)),
        // Numeric 0/1 reaches this typed leaf only after the trusted
        // workbook materializer has normalized its source controls.  The
        // public JSON parser rejects the same spelling before this boundary.
        ResolvedDefaultV1::Scalar(v) if *v == 0.0 || *v == 1.0 => Ok(Some(*v != 0.0)),
        _ => Err(DirectRunErrorV1::Parameters(format!(
            "package {} must be boolean",
            names[0]
        ))),
    }
}
fn finite(value: Complex64) -> bool {
    value.real().is_finite() && value.imaginary().is_finite()
}
fn one() -> Result<Complex64, DirectRunErrorV1> {
    Complex64::try_new(1.0, 0.0)
        .map_err(|_| DirectRunErrorV1::Parameters("non-finite package constant".to_owned()))
}
fn zero(value: Complex64) -> bool {
    value.real() == 0.0 && value.imaginary() == 0.0
}
fn add(a: Complex64, b: Complex64) -> Result<Complex64, DirectRunErrorV1> {
    Complex64::try_new(a.real() + b.real(), a.imaginary() + b.imaginary())
        .map_err(|_| DirectRunErrorV1::Parameters("package complex addition overflow".to_owned()))
}
fn sub(a: Complex64, b: Complex64) -> Result<Complex64, DirectRunErrorV1> {
    Complex64::try_new(a.real() - b.real(), a.imaginary() - b.imaginary()).map_err(|_| {
        DirectRunErrorV1::Parameters("package complex subtraction overflow".to_owned())
    })
}
fn mul(a: Complex64, b: Complex64) -> Result<Complex64, DirectRunErrorV1> {
    Complex64::try_new(
        a.real() * b.real() - a.imaginary() * b.imaginary(),
        a.real() * b.imaginary() + a.imaginary() * b.real(),
    )
    .map_err(|_| DirectRunErrorV1::Parameters("package complex multiplication overflow".to_owned()))
}
fn div(a: Complex64, b: Complex64) -> Result<Complex64, DirectRunErrorV1> {
    let d = b.real() * b.real() + b.imaginary() * b.imaginary();
    if d == 0.0 || !d.is_finite() {
        return Err(DirectRunErrorV1::Parameters(
            "package complex division singular or overflow".to_owned(),
        ));
    }
    Complex64::try_new(
        (a.real() * b.real() + a.imaginary() * b.imaginary()) / d,
        (a.imaginary() * b.real() - a.real() * b.imaginary()) / d,
    )
    .map_err(|_| DirectRunErrorV1::Parameters("package complex division overflow".to_owned()))
}
fn scale(a: Complex64, factor: f64) -> Result<Complex64, DirectRunErrorV1> {
    Complex64::try_new(a.real() * factor, a.imaginary() * factor)
        .map_err(|_| DirectRunErrorV1::Parameters("package complex scale overflow".to_owned()))
}
fn exp_neg(gamma: Complex64, length: f64) -> Result<Complex64, DirectRunErrorV1> {
    let a = -length * gamma.real();
    let b = -length * gamma.imaginary();
    if !a.is_finite() || !b.is_finite() || a > 709.0 {
        return Err(DirectRunErrorV1::Parameters(
            "package line exponential overflow".to_owned(),
        ));
    }
    let e = a.exp();
    Complex64::try_new(e * b.cos(), e * b.sin())
        .map_err(|_| DirectRunErrorV1::Parameters("package line exponential overflow".to_owned()))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn c(real: f64, imaginary: f64) -> Complex64 {
        Complex64::try_new(real, imaginary).unwrap()
    }

    fn values() -> BTreeMap<String, ResolvedDefaultV1> {
        BTreeMap::from([
            (
                "pkg_len_select".to_owned(),
                ResolvedDefaultV1::Vector(vec![1.0, 1.0]),
            ),
            (
                "pkg_Z_c".to_owned(),
                ResolvedDefaultV1::Matrix(vec![vec![50.0], vec![50.0]]),
            ),
            (
                "z_p_tx_cases".to_owned(),
                ResolvedDefaultV1::Matrix(vec![vec![0.0]]),
            ),
            (
                "z_p_rx_cases".to_owned(),
                ResolvedDefaultV1::Matrix(vec![vec![0.0]]),
            ),
            (
                "z_p_fext_cases".to_owned(),
                ResolvedDefaultV1::Matrix(vec![vec![0.0]]),
            ),
            (
                "z_p_next_cases".to_owned(),
                ResolvedDefaultV1::Matrix(vec![vec![0.0]]),
            ),
            (
                "C_diepad".to_owned(),
                ResolvedDefaultV1::Vector(vec![0.0, 0.0]),
            ),
            (
                "L_comp".to_owned(),
                ResolvedDefaultV1::Vector(vec![0.0, 0.0]),
            ),
            (
                "C_bump".to_owned(),
                ResolvedDefaultV1::Vector(vec![0.0, 0.0]),
            ),
            ("C_v".to_owned(), ResolvedDefaultV1::Vector(vec![0.0, 0.0])),
            (
                "C_pkg_board".to_owned(),
                ResolvedDefaultV1::Vector(vec![0.0, 0.0]),
            ),
            (
                "pkg_gamma0_a1_a2".to_owned(),
                ResolvedDefaultV1::Vector(vec![0.0, 0.0, 0.0]),
            ),
            ("pkg_tau".to_owned(), ResolvedDefaultV1::Scalar(0.0)),
            ("Z0".to_owned(), ResolvedDefaultV1::Scalar(50.0)),
            (
                "R_diepad".to_owned(),
                ResolvedDefaultV1::Vector(vec![50.0, 50.0]),
            ),
            ("Tx_rd_sel".to_owned(), ResolvedDefaultV1::Scalar(1.0)),
            ("Rx_rd_sel".to_owned(), ResolvedDefaultV1::Scalar(1.0)),
            ("INC_PACKAGE".to_owned(), ResolvedDefaultV1::Boolean(true)),
            ("include_pcb".to_owned(), ResolvedDefaultV1::Scalar(0.0)),
            (
                "INCLUDE_FILTER".to_owned(),
                ResolvedDefaultV1::Boolean(false),
            ),
            ("GET_FD".to_owned(), ResolvedDefaultV1::Boolean(true)),
            ("T_r_filter_type".to_owned(), ResolvedDefaultV1::Scalar(0.0)),
            ("T_r_meas_point".to_owned(), ResolvedDefaultV1::Scalar(0.0)),
            ("kappa1".to_owned(), ResolvedDefaultV1::Scalar(1.0)),
            ("kappa2".to_owned(), ResolvedDefaultV1::Scalar(1.0)),
            ("a_thru".to_owned(), ResolvedDefaultV1::Scalar(1.0)),
            ("a_fext".to_owned(), ResolvedDefaultV1::Scalar(1.0)),
            ("a_next".to_owned(), ResolvedDefaultV1::Scalar(1.0)),
        ])
    }

    #[test]
    fn workbook_snp_port_order_is_applied_before_mixed_mode() {
        let mut sample = [[c(0.0, 0.0); 4]; 4];
        sample[2][1] = c(3.0, 0.0);
        sample[1][2] = c(4.0, 0.0);
        let mut config = values();
        config.insert(
            "snpPortsOrder".to_owned(),
            ResolvedDefaultV1::Vector(vec![1.0, 3.0, 2.0, 4.0]),
        );
        let reordered = reorder_s4p_samples_v1(&[sample], &config, true).unwrap();
        assert_eq!(reordered[0][1][2].real(), 3.0);
        assert_eq!(reordered[0][2][1].real(), 4.0);
    }

    #[test]
    fn configured_snp_port_order_is_the_applied_one_based_permutation() {
        let mut config = values();
        config.insert(
            "snpPortsOrder".to_owned(),
            ResolvedDefaultV1::Vector(vec![1.0, 3.0, 2.0, 4.0]),
        );
        assert_eq!(
            configured_snp_port_order_v1(&config, true).unwrap(),
            Some([1, 3, 2, 4])
        );
        assert_eq!(
            configured_snp_port_order_v1(&values(), false).unwrap(),
            None
        );
    }

    #[test]
    fn snp_port_order_is_source_exact_and_trusted_only() {
        let samples = vec![[[c(0.0, 0.0); 4]; 4]; 1];
        let no_order = values();
        assert!(reorder_s4p_samples_v1(&samples, &no_order, true).is_err());
        assert!(reorder_s4p_samples_v1(&samples, &no_order, false).is_ok());
        let mut identity = values();
        identity.insert(
            "snpPortsOrder".to_owned(),
            ResolvedDefaultV1::Vector(vec![1.0, 2.0, 3.0, 4.0]),
        );
        assert!(reorder_s4p_samples_v1(&samples, &identity, true).is_ok());
        assert!(reorder_s4p_samples_v1(&samples, &identity, false).is_err());

        let mut folded = values();
        folded.insert(
            "SNPPORTSORDER".to_owned(),
            ResolvedDefaultV1::Vector(vec![1.0, 2.0, 3.0, 4.0]),
        );
        assert!(reorder_s4p_samples_v1(&samples, &folded, true).is_err());
        assert!(reorder_s4p_samples_v1(&samples, &folded, false).is_err());

        let mut duplicate = identity.clone();
        duplicate.insert(
            "SNPPOrtsOrder".to_owned(),
            ResolvedDefaultV1::Vector(vec![1.0, 2.0, 3.0, 4.0]),
        );
        assert!(reorder_s4p_samples_v1(&samples, &duplicate, true).is_err());
    }

    #[test]
    fn snp_port_order_rejects_invalid_typed_values() {
        let samples = vec![[[c(0.0, 0.0); 4]; 4]; 1];
        for order in [
            vec![1.0, 2.0, 3.0],
            vec![1.0, 1.0, 2.0, 3.0],
            vec![0.0, 1.0, 2.0, 3.0],
            vec![1.0, 2.0, 3.0, 5.0],
            vec![1.0, 2.0, 3.5, 4.0],
            vec![1.0, 2.0, f64::NAN, 4.0],
        ] {
            let mut config = values();
            config.insert("snpPortsOrder".to_owned(), ResolvedDefaultV1::Vector(order));
            assert!(reorder_s4p_samples_v1(&samples, &config, true).is_err());
        }
        let mut wrong_type = values();
        wrong_type.insert("snpPortsOrder".to_owned(), ResolvedDefaultV1::Scalar(1.0));
        assert!(reorder_s4p_samples_v1(&samples, &wrong_type, true).is_err());
    }

    #[test]
    fn package_aliases_require_typed_consistency() {
        let mut config = values();
        config.insert("inc_package".to_owned(), ResolvedDefaultV1::Boolean(true));
        assert_eq!(
            boolean(&config, &["INC_PACKAGE", "inc_package"]).unwrap(),
            Some(true)
        );
        config.insert("inc_package".to_owned(), ResolvedDefaultV1::Boolean(false));
        assert!(boolean(&config, &["INC_PACKAGE", "inc_package"]).is_err());

        let mut matrix_aliases = values();
        matrix_aliases.insert(
            "PKG_Z_C".to_owned(),
            ResolvedDefaultV1::Matrix(vec![vec![50.0], vec![50.0]]),
        );
        assert!(matrix_required(&matrix_aliases, &["pkg_Z_c", "package_Z_c"]).is_ok());
        matrix_aliases.insert(
            "package_Z_c".to_owned(),
            ResolvedDefaultV1::Matrix(vec![vec![51.0], vec![50.0]]),
        );
        assert!(matrix_required(&matrix_aliases, &["pkg_Z_c", "package_Z_c"]).is_err());
    }

    #[test]
    fn zero_length_package_preserves_sdd21_before_final_impulse() {
        assert!(PACKAGE_VTF_POLICY_V1.contains("no-fit"));
        let frequency = vec![0.0, 1.0e9, 2.0e9];
        let mut samples = vec![[[c(0.0, 0.0); 4]; 4]; 3];
        for sample in &mut samples {
            sample[2][0] = c(1.0, 0.0);
            sample[3][1] = c(1.0, 0.0);
        }
        let result = s4p_package_vtf_v1(&frequency, &samples, &values(), "THRU", 0).unwrap();
        assert_eq!(result.len(), frequency.len());
        assert!(
            result
                .iter()
                .all(|value| (value.real() - 1.0).abs() < 1.0e-12
                    && value.imaginary().abs() < 1.0e-12)
        );
    }

    #[test]
    fn dc_common_mode_vtf_uses_pinned_sdc_indices_and_keeps_frequency_axis() {
        let frequency = vec![0.0, 1.0e9];
        let mut samples = vec![[[c(0.0, 0.0); 4]; 4]; 2];
        for sample in &mut samples {
            // These two single-ended entries produce SDC21=0.5 after the
            // fixed mixed-mode transform; the zero package profile leaves it
            // unchanged.  This is a numeric checkpoint before FD-to-TD.
            sample[0][0] = c(1.0, 0.0);
            sample[2][0] = c(1.0, 0.0);
        }
        let result =
            s4p_package_dc_vtf_v1(&frequency, &samples, &values(), "THRU", 0).expect("DC VTF");
        assert_eq!(result.len(), frequency.len());
        assert!(result.iter().all(|value| {
            (value.real() - 0.5).abs() < 1.0e-12 && value.imaginary().abs() < 1.0e-12
        }));
    }

    #[test]
    fn snp_port_order_is_shared_by_thru_fext_next_dd_and_sdc_routes() {
        let frequency = vec![0.0, 1.0e9];
        let mut samples = vec![[[c(0.0, 0.0); 4]; 4]; 2];
        for sample in &mut samples {
            sample[2][0] = c(1.0, 0.0);
            sample[3][1] = c(0.25, 0.0);
        }
        let mut config = values();
        config.insert(
            "snpPortsOrder".to_owned(),
            ResolvedDefaultV1::Vector(vec![1.0, 3.0, 2.0, 4.0]),
        );
        let reordered = reorder_s4p_samples_v1(&samples, &config, true).unwrap();
        for role in ["THRU", "FEXT", "NEXT"] {
            assert!(s4p_package_vtf_v1(&frequency, &reordered, &config, role, 0).is_ok());
            assert!(s4p_package_dc_vtf_v1(&frequency, &reordered, &config, role, 0).is_ok());
        }
    }

    #[test]
    fn repeated_sparse_selection_and_axis_mismatch_fail_closed() {
        let frequency = vec![0.0, 1.0e9];
        let samples = vec![[[c(0.0, 0.0); 4]; 4]; 2];
        let mut config = values();
        config.insert(
            "pkg_len_select".to_owned(),
            ResolvedDefaultV1::Vector(vec![2.0]),
        );
        let result = s4p_package_vtf_v1(&frequency, &samples, &config, "THRU", 0);
        assert!(result.is_err());
        assert!(s4p_package_vtf_v1(&frequency[..1], &samples, &values(), "THRU", 0).is_err());
    }

    #[test]
    fn singular_termination_is_not_hidden_by_epsilon() {
        let mut samples = vec![[[c(0.0, 0.0); 4]; 4]; 2];
        for sample in &mut samples {
            sample[1][1] = c(1.0, 0.0);
            sample[2][2] = c(1.0, 0.0);
            sample[2][0] = c(1.0, 0.0);
            sample[3][1] = c(1.0, 0.0);
        }
        let singular = TwoPort::new(
            vec![c(1.0, 0.0); 2],
            vec![c(1.0, 0.0); 2],
            vec![c(1.0, 0.0); 2],
            vec![c(1.0, 0.0); 2],
        )
        .unwrap();
        assert!(combine(&singular, &singular).is_err());
    }

    #[test]
    fn board_cascade_uses_pinned_tx_rx_length_mapping() {
        let frequency = vec![0.0, 1.0e9];
        let mut samples = vec![[[c(0.0, 0.0); 4]; 4]; 2];
        for sample in &mut samples {
            sample[2][0] = c(1.0, 0.0);
            sample[3][1] = c(1.0, 0.0);
        }
        let mut config = values();
        config.insert("include_pcb".to_owned(), ResolvedDefaultV1::Scalar(1.0));
        config.insert("C_0".to_owned(), ResolvedDefaultV1::Vector(vec![0.0, 0.0]));
        config.insert("C_1".to_owned(), ResolvedDefaultV1::Vector(vec![0.0, 0.0]));
        config.insert(
            "brd_Z_c".to_owned(),
            ResolvedDefaultV1::Vector(vec![50.0, 50.0]),
        );
        config.insert(
            "brd_gamma0_a1_a2".to_owned(),
            ResolvedDefaultV1::Vector(vec![0.0, 0.0, 0.0]),
        );
        config.insert("brd_tau".to_owned(), ResolvedDefaultV1::Scalar(0.0));
        config.insert("z_bp_tx".to_owned(), ResolvedDefaultV1::Scalar(0.0));
        config.insert("z_bp_rx".to_owned(), ResolvedDefaultV1::Scalar(0.0));
        config.insert("z_bp_next".to_owned(), ResolvedDefaultV1::Scalar(0.0));
        config.insert("z_bp_fext".to_owned(), ResolvedDefaultV1::Scalar(0.0));
        let result = s4p_package_vtf_v1(&frequency, &samples, &config, "THRU", 0).unwrap();
        assert!(
            result
                .iter()
                .all(|value| (value.real() - 1.0).abs() < 1.0e-12)
        );
    }

    #[test]
    fn oversized_and_nonrectangular_package_controls_fail_closed() {
        let frequency = vec![0.0, 1.0e9];
        let samples = vec![[[c(0.0, 0.0); 4]; 4]; 2];
        let mut huge = values();
        huge.insert(
            "pkg_Z_c".to_owned(),
            ResolvedDefaultV1::Matrix(vec![vec![f64::MAX], vec![50.0]]),
        );
        assert!(s4p_package_vtf_v1(&frequency, &samples, &huge, "THRU", 0).is_err());
        let mut ragged = values();
        ragged.insert(
            "pkg_Z_c".to_owned(),
            ResolvedDefaultV1::Matrix(vec![vec![50.0], vec![50.0, 50.0]]),
        );
        assert!(s4p_package_vtf_v1(&frequency, &samples, &ragged, "THRU", 0).is_err());
    }

    #[test]
    fn transmitter_filter_is_applied_after_package_vtf() {
        let frequency = vec![0.0, 1.0e9];
        let mut samples = vec![[[c(0.0, 0.0); 4]; 4]; 2];
        for sample in &mut samples {
            sample[2][0] = c(1.0, 0.0);
            sample[3][1] = c(1.0, 0.0);
        }
        let mut config = values();
        config.insert("T_r_filter_type".to_owned(), ResolvedDefaultV1::Scalar(1.0));
        config.insert(
            "transmitter_transition_time".to_owned(),
            ResolvedDefaultV1::Scalar(10.0),
        );
        let result = s4p_package_vtf_v1(&frequency, &samples, &config, "THRU", 0).unwrap();
        assert!((result[0].real() - 1.0).abs() < 1.0e-12);
        assert!(result[1].real() < 1.0);
    }

    #[test]
    fn ideal_type_zero_uses_gaussian_even_when_measurement_flag_is_set() {
        let frequency = vec![0.0, 1.0e9];
        let mut config = values();
        config.insert("IDEAL_TX_TERM".to_owned(), ResolvedDefaultV1::Boolean(true));
        config.insert("T_r_meas_point".to_owned(), ResolvedDefaultV1::Scalar(1.0));
        config.insert(
            "transmitter_transition_time".to_owned(),
            ResolvedDefaultV1::Scalar(10.0),
        );
        let response = transmitter_filter_v1(&frequency, &config).unwrap().unwrap();
        let expected = (-(std::f64::consts::PI * 10.0 / 1.6832).powi(2)).exp();
        assert!((response[1].real() - expected).abs() < 1.0e-12);
        assert_eq!(response[1].imaginary(), 0.0);
    }

    #[test]
    fn missing_and_zero_package_preset_are_identity_and_cursor_ties_are_first() {
        let frequency = vec![0.0, 1.0e9];
        let missing = package_preset_v1(&values(), 0, 0).unwrap();
        assert_eq!(missing, vec![0.0]);
        let missing_response = package_preset_response_v1(&frequency, 1.0e9, &missing).unwrap();
        assert!(
            missing_response
                .iter()
                .all(|value| (value.real() - 1.0).abs() < 1.0e-12)
        );
        let mut zero = values();
        zero.insert(
            "PKG_Tx_FFE_preset".to_owned(),
            ResolvedDefaultV1::Vector(vec![0.0, 0.0]),
        );
        let response =
            package_preset_response_v1(&frequency, 1.0e9, &package_preset_v1(&zero, 0, 0).unwrap())
                .unwrap();
        assert!(
            response
                .iter()
                .all(|value| (value.real() - 1.0).abs() < 1.0e-12)
        );
        let tie = package_preset_response_v1(&frequency, 1.0e9, &[1.0, 1.0]).unwrap();
        assert!((tie[1].real() - 2.0).abs() < 1.0e-12);
        assert!(tie[1].imaginary().abs() < 1.0e-12);
    }

    #[test]
    fn receiver_filter_product_and_package_preset_are_applied_in_fd_order() {
        let frequency = vec![0.0, 1.0e9];
        let mut samples = vec![[[c(0.0, 0.0); 4]; 4]; 2];
        for sample in &mut samples {
            sample[2][0] = c(1.0, 0.0);
            sample[3][1] = c(1.0, 0.0);
        }
        let mut config = values();
        config.insert(
            "INCLUDE_FILTER".to_owned(),
            ResolvedDefaultV1::Boolean(true),
        );
        config.insert("GET_FD".to_owned(), ResolvedDefaultV1::Boolean(true));
        config.insert("fb".to_owned(), ResolvedDefaultV1::Scalar(1.0e9));
        config.insert("BTorder".to_owned(), ResolvedDefaultV1::Scalar(1.0));
        config.insert("fb_BT_cutoff".to_owned(), ResolvedDefaultV1::Scalar(1.0));
        config.insert("fb_BW_cutoff".to_owned(), ResolvedDefaultV1::Scalar(1.0));
        config.insert(
            "Bessel_Thomson".to_owned(),
            ResolvedDefaultV1::Boolean(true),
        );
        config.insert("Butterworth".to_owned(), ResolvedDefaultV1::Boolean(false));
        config.insert(
            "Raised_Cosine".to_owned(),
            ResolvedDefaultV1::Boolean(false),
        );
        config.insert("RC_Start".to_owned(), ResolvedDefaultV1::Scalar(0.0));
        config.insert("RC_end".to_owned(), ResolvedDefaultV1::Scalar(2.0e9));
        config.insert(
            "PKG_Tx_FFE_preset".to_owned(),
            ResolvedDefaultV1::Vector(vec![1.0, 0.25]),
        );
        let result = s4p_package_vtf_v1(&frequency, &samples, &config, "THRU", 0).unwrap();
        assert_eq!(result.len(), frequency.len());
        assert!(result[1].real() < 0.9);
    }

    #[test]
    fn board_fd_path_remains_reachable_when_package_is_disabled() {
        let frequency = vec![0.0, 1.0e9];
        let mut samples = vec![[[c(0.0, 0.0); 4]; 4]; 2];
        for sample in &mut samples {
            sample[2][0] = c(1.0, 0.0);
            sample[3][1] = c(1.0, 0.0);
        }
        let mut config = values();
        config.insert("INC_PACKAGE".to_owned(), ResolvedDefaultV1::Boolean(false));
        config.insert("include_pcb".to_owned(), ResolvedDefaultV1::Scalar(1.0));
        config.insert("C_0".to_owned(), ResolvedDefaultV1::Vector(vec![0.0, 0.0]));
        config.insert("C_1".to_owned(), ResolvedDefaultV1::Vector(vec![0.0, 0.0]));
        config.insert(
            "brd_Z_c".to_owned(),
            ResolvedDefaultV1::Vector(vec![50.0, 50.0]),
        );
        config.insert(
            "brd_gamma0_a1_a2".to_owned(),
            ResolvedDefaultV1::Vector(vec![0.0, 0.0, 0.0]),
        );
        config.insert("brd_tau".to_owned(), ResolvedDefaultV1::Scalar(0.0));
        config.insert("z_bp_tx".to_owned(), ResolvedDefaultV1::Scalar(0.0));
        config.insert("z_bp_rx".to_owned(), ResolvedDefaultV1::Scalar(0.0));
        config.insert("z_bp_next".to_owned(), ResolvedDefaultV1::Scalar(0.0));
        config.insert("z_bp_fext".to_owned(), ResolvedDefaultV1::Scalar(0.0));
        let result = s4p_package_vtf_v1(&frequency, &samples, &config, "THRU", 0).unwrap();
        assert!(result.iter().all(|value| finite(*value)));
    }

    #[test]
    fn die_chain_is_prepended_only_to_lengths_and_segment_controls() {
        let frequency = vec![0.0, 1.0e9];
        let mut samples = vec![[[c(0.0, 0.0); 4]; 4]; 2];
        for sample in &mut samples {
            sample[2][0] = c(1.0, 0.0);
            sample[3][1] = c(1.0, 0.0);
        }
        let mut config = values();
        config.insert(
            "C_diepad".to_owned(),
            ResolvedDefaultV1::Matrix(vec![vec![0.0, 0.0], vec![0.0, 0.0]]),
        );
        config.insert(
            "L_comp".to_owned(),
            ResolvedDefaultV1::Matrix(vec![vec![0.0, 0.0], vec![0.0, 0.0]]),
        );
        let result = s4p_package_vtf_v1(&frequency, &samples, &config, "THRU", 0).unwrap();
        assert!(result.iter().all(|value| finite(*value)));
    }

    #[test]
    fn excluded_die_profile_zeroes_bump_and_omits_die_chain() {
        let frequency = vec![0.0, 1.0e9];
        let mut config = values();
        config.insert(
            "C_bump".to_owned(),
            ResolvedDefaultV1::Vector(vec![1.0e-6, 1.0e-6]),
        );
        let tx = full_package_mode_v1("TX", &frequency, "THRU", 0, &config, false, false).unwrap();
        let mut zero = config;
        zero.insert(
            "C_bump".to_owned(),
            ResolvedDefaultV1::Vector(vec![0.0, 0.0]),
        );
        let expected =
            full_package_mode_v1("TX", &frequency, "THRU", 0, &zero, false, false).unwrap();
        assert_eq!(tx.s21, expected.s21);
    }

    #[test]
    fn package_case_amplitude_is_selected_per_role_and_case() {
        let frequency = vec![0.0, 1.0e9];
        let mut config = values();
        config.insert(
            "a_thru".to_owned(),
            ResolvedDefaultV1::Vector(vec![0.5, 0.25]),
        );
        config.insert(
            "a_fext".to_owned(),
            ResolvedDefaultV1::Vector(vec![0.2, 0.1]),
        );
        config.insert(
            "pkg_len_select".to_owned(),
            ResolvedDefaultV1::Vector(vec![1.0, 2.0]),
        );
        assert_eq!(package_case_amplitude_v1(&config, "THRU", 1).unwrap(), 0.25);
        assert_eq!(package_case_amplitude_v1(&config, "FEXT", 0).unwrap(), 0.2);
        assert_eq!(package_case_amplitude_v1(&config, "NEXT", 0).unwrap(), 1.0);
        let mut samples = vec![[[c(0.0, 0.0); 4]; 4]; 2];
        for sample in &mut samples {
            sample[2][0] = c(1.0, 0.0);
            sample[3][1] = c(1.0, 0.0);
        }
        let selected = s4p_package_vtf_v1(&frequency, &samples, &config, "THRU", 0).unwrap();
        assert!((selected[0].real() - 1.0).abs() < 1.0e-12);
    }

    #[test]
    fn channel_amplitude_matches_wc_portz_and_broadcast_rules() {
        let mut config = values();
        config.insert(
            "pkg_len_select".to_owned(),
            ResolvedDefaultV1::Vector(vec![2.0]),
        );
        config.insert(
            "a_thru".to_owned(),
            ResolvedDefaultV1::Vector(vec![0.25, -0.5]),
        );
        config.insert("a_fext".to_owned(), ResolvedDefaultV1::Scalar(0.0));
        assert_eq!(
            package_channel_amplitude_v1(&config, "THRU", 0).unwrap(),
            -0.5
        );
        assert!(package_channel_amplitude_v1(&config, "FEXT", 0).is_err());
        config.insert(
            "pkg_len_select".to_owned(),
            ResolvedDefaultV1::Vector(vec![1.0]),
        );
        assert_eq!(
            package_channel_amplitude_v1(&config, "FEXT", 0).unwrap(),
            0.0
        );

        config.insert("WC_PORTZ".to_owned(), ResolvedDefaultV1::Boolean(true));
        config.insert("Tx_rd_sel".to_owned(), ResolvedDefaultV1::Scalar(2.0));
        assert_eq!(
            package_channel_amplitude_v1(&config, "THRU", 0).unwrap(),
            -0.5
        );
        config.insert("a_thru".to_owned(), ResolvedDefaultV1::Scalar(-0.5));
        assert!(package_channel_amplitude_v1(&config, "THRU", 0).is_err());
        config.insert("Tx_rd_sel".to_owned(), ResolvedDefaultV1::Scalar(0.0));
        assert!(package_channel_amplitude_v1(&config, "THRU", 0).is_err());
        config.insert("WC_PORTZ".to_owned(), ResolvedDefaultV1::Boolean(false));
        config.insert(
            "pkg_len_select".to_owned(),
            ResolvedDefaultV1::Vector(vec![3.0]),
        );
        config.insert(
            "a_thru".to_owned(),
            ResolvedDefaultV1::Vector(vec![0.25, -0.5]),
        );
        assert!(package_channel_amplitude_v1(&config, "THRU", 0).is_err());
    }

    #[test]
    fn four_segment_thru_fext_next_cases_preserve_channel_role() {
        let frequency = vec![0.0, 1.0e9];
        let mut samples = vec![[[c(0.0, 0.0); 4]; 4]; 2];
        for sample in &mut samples {
            sample[2][0] = c(1.0, 0.0);
            sample[3][1] = c(1.0, 0.0);
        }
        let mut config = values();
        config.insert(
            "pkg_Z_c".to_owned(),
            ResolvedDefaultV1::Matrix(vec![vec![50.0; 4], vec![50.0; 4]]),
        );
        for key in [
            "z_p_tx_cases",
            "z_p_rx_cases",
            "z_p_fext_cases",
            "z_p_next_cases",
        ] {
            config.insert(
                key.to_owned(),
                ResolvedDefaultV1::Matrix(vec![vec![0.0; 4]]),
            );
        }
        for channel in ["THRU", "FEXT", "NEXT"] {
            let result = s4p_package_vtf_v1(&frequency, &samples, &config, channel, 0).unwrap();
            assert_eq!(result.len(), frequency.len());
            assert!(result.iter().all(|value| finite(*value)));
        }
    }

    #[test]
    fn normal_tdr_assembly_retains_raw_dd_channel_and_sdd12() {
        let frequency = vec![0.0, 1.0e9, 2.0e9];
        let mut samples = vec![[[c(0.0, 0.0); 4]; 4]; 3];
        for (index, sample) in samples.iter_mut().enumerate() {
            sample[0][2] = c(0.5 + index as f64 * 0.01, 0.0);
            sample[2][0] = c(0.7, 0.0);
            sample[1][3] = c(0.1, 0.0);
            sample[3][1] = c(0.2, 0.0);
        }
        let config = values();
        let mixed = samples.iter().map(com_mixed_mode_v1).collect::<Vec<_>>();
        let assembled =
            assemble_r480_tdr_dd_network_v1(&frequency, &samples, &config, 0).expect("assembly");
        let expected_s11 = mixed.iter().map(|sample| sample[1][1]).collect::<Vec<_>>();
        let expected_s12 = mixed.iter().map(|sample| sample[1][3]).collect::<Vec<_>>();
        let expected_s21 = mixed.iter().map(|sample| sample[3][1]).collect::<Vec<_>>();
        let expected_s22 = mixed.iter().map(|sample| sample[3][3]).collect::<Vec<_>>();
        assert_eq!(assembled.s11, expected_s11);
        assert_eq!(assembled.s12, expected_s12);
        assert_eq!(assembled.s21, expected_s21);
        assert_eq!(assembled.s22, expected_s22);
        assert_eq!(assembled.raw_sdd12, expected_s12);
    }

    #[test]
    fn normal_tdr_tx_package_restores_preassembly_sdd11() {
        let frequency = vec![0.0, 1.0e9, 2.0e9];
        let mut samples = vec![[[c(0.0, 0.0); 4]; 4]; 3];
        for sample in &mut samples {
            sample[0][0] = c(0.4, 0.0);
            sample[1][1] = c(0.3, 0.0);
            sample[2][2] = c(0.2, 0.0);
            sample[3][3] = c(0.1, 0.0);
            sample[2][0] = c(0.7, 0.0);
            sample[0][2] = c(0.7, 0.0);
        }
        let mut config = values();
        config.insert("TDR_W_TXPKG".to_owned(), ResolvedDefaultV1::Boolean(true));
        let mixed = samples.iter().map(com_mixed_mode_v1).collect::<Vec<_>>();
        let raw_s11 = mixed.iter().map(|sample| sample[1][1]).collect::<Vec<_>>();
        let assembled =
            assemble_r480_tdr_dd_network_v1(&frequency, &samples, &config, 0).expect("assembly");
        assert_eq!(assembled.s11, raw_s11);
    }

    #[test]
    fn source_load_identity_and_nonidentity_are_explicit() {
        let n = 3;
        let channel = TwoPort::new(
            vec![c(0.1, 0.0); n],
            vec![c(0.2, 0.0); n],
            vec![c(0.3, 0.0); n],
            vec![c(0.4, 0.0); n],
        )
        .expect("channel");
        let identity = source_load_v1(channel.clone(), 100.0).expect("identity load");
        assert_eq!(identity.s11, channel.s11);
        assert_eq!(identity.s21, channel.s21);
        let changed = source_load_v1(channel, 110.0).expect("series load");
        assert_ne!(changed.s11, vec![c(0.1, 0.0); n]);
        assert_ne!(changed.s21, vec![c(0.3, 0.0); n]);
    }
}
