// SPDX-License-Identifier: MIT
//
// This module is a small composition boundary around the public FD leaves in
// `sipi-com`.  Its source behavior is pinned to Agent-COM
// `src/agent_com/_orchestration.py` at commit
// `5272ffe74702cd585054d975559b06f8afae7b6e` (tree
// `7094ab6e84989b218730c52432c70da10261f8ea`).

//! COM R4.80 frequency-domain metric composition.
//!
//! The Agent-COM orchestration layer takes raw mixed-mode `SDD21` traces from
//! the THRU, FEXT, and NEXT networks, selects the workbook controls for the
//! current package case, and feeds them to the FD metric leaf.  This module
//! keeps that small piece of orchestration typed and explicit.  It does not
//! read Touchstone files, perform a port transform, construct a package VTF,
//! run an equalizer, or fit an S-parameter model.

use std::{error::Error, fmt};

use sipi_com::{FdIcnAggressorV1, FdMetricsErrorV1, fd_loss_metrics_v1, r480_fd_icn_metrics_v1};
use sipi_types::Complex64;

/// Provenance policy for the direct COM FD composition boundary.
#[allow(dead_code)]
pub(crate) const FD_RUNTIME_POLICY_V1: &str =
    "sipi.agent-com.fd-runtime-v1.r480-raw-sdd21-composition";

/// One raw mixed-mode SDD21 trace.
///
/// The axis and transfer are deliberately separate borrowed slices.  The
/// caller owns parsing and any port-order conversion; the FD path consumes
/// only the resulting raw `frequency_hz` and `SDD21` values.
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct FdRawSdd21V1<'a> {
    pub(crate) frequency_hz: &'a [f64],
    pub(crate) sdd21: &'a [Complex64],
}

/// Raw networks consumed by the COM FD metric path.
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct FdRawNetworkSetV1<'a> {
    pub(crate) thru: FdRawSdd21V1<'a>,
    pub(crate) fext: &'a [FdRawSdd21V1<'a>],
    pub(crate) next: &'a [FdRawSdd21V1<'a>],
}

/// Workbook-derived controls used by the pinned FD orchestration call.
///
/// `a_icn_*_v` follows the source materialization convention: a singleton
/// broadcasts to all package cases; otherwise `wc_portz` selects by the
/// one-based `tx_rd_sel` control and the normal path selects by the
/// one-based `pkg_len_select[package_case_index]` value.
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct FdRuntimeControlsV1<'a> {
    pub(crate) f1_hz: f64,
    pub(crate) f2_hz: f64,
    pub(crate) baud_hz: f64,
    pub(crate) samples_per_ui: usize,
    pub(crate) sample_dt_s: f64,
    pub(crate) f_v: f64,
    pub(crate) f_r: f64,
    pub(crate) a_icn_fext_v: &'a [f64],
    pub(crate) a_icn_next_v: &'a [f64],
    pub(crate) wc_portz: bool,
    pub(crate) tx_rd_sel: usize,
    pub(crate) pkg_len_select: &'a [usize],
    pub(crate) package_case_index: usize,
}

/// Scalar COM metrics emitted by this composition boundary.
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct FdRuntimeMetricsV1 {
    pub(crate) icn_mv: f64,
    pub(crate) fext_icn_mv: f64,
    pub(crate) next_icn_mv: f64,
    pub(crate) il_db_channel_only_at_fnq: f64,
    pub(crate) fitted_il_db_at_fnq: f64,
    pub(crate) fom_ild: f64,
}

/// Small diagnostics that make workbook selection and leaf integration
/// observable without exposing the full per-frequency arrays in the COM
/// result object.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct FdRuntimeDiagnosticsV1 {
    pub(crate) transition_cutoff_hz: f64,
    pub(crate) receiver_cutoff_hz: f64,
    pub(crate) integration_start_index: usize,
    pub(crate) integration_end_index: isize,
    pub(crate) fext_aggressor_count: usize,
    pub(crate) next_aggressor_count: usize,
    pub(crate) selected_fext_amplitudes_v: Vec<f64>,
    pub(crate) selected_next_amplitudes_v: Vec<f64>,
}

/// Errors at the composition boundary.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum FdRuntimeErrorV1 {
    Metrics(FdMetricsErrorV1),
    MissingAmplitude(&'static str),
    InvalidAmplitude(&'static str),
    InvalidPackageSelection(&'static str),
    InvalidControls(&'static str),
}

impl fmt::Display for FdRuntimeErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Metrics(error) => write!(formatter, "FD metric leaf failed: {error}"),
            Self::MissingAmplitude(role) => {
                write!(formatter, "missing workbook amplitude for {role}")
            }
            Self::InvalidAmplitude(role) => {
                write!(formatter, "invalid workbook amplitude for {role}")
            }
            Self::InvalidPackageSelection(reason) => {
                write!(formatter, "invalid workbook package selection: {reason}")
            }
            Self::InvalidControls(reason) => write!(formatter, "invalid FD controls: {reason}"),
        }
    }
}

impl Error for FdRuntimeErrorV1 {}

impl From<FdMetricsErrorV1> for FdRuntimeErrorV1 {
    fn from(error: FdMetricsErrorV1) -> Self {
        Self::Metrics(error)
    }
}

/// Compose the pinned COM FD ICN and THRU insertion-loss metrics.
///
/// The order mirrors `_orchestration.py`: FEXT and NEXT aggressors are
/// assembled from raw SDD21 traces, amplitudes are selected from the
/// materialized workbook controls, ICN is calculated, and then the THRU FD
/// loss/FOM report is calculated at `fb / 2` with `f1`, `f2`, `f_v`, and `f_r`.
pub(crate) fn compose_fd_metrics_v1(
    networks: &FdRawNetworkSetV1<'_>,
    controls: &FdRuntimeControlsV1<'_>,
) -> Result<(FdRuntimeMetricsV1, FdRuntimeDiagnosticsV1), FdRuntimeErrorV1> {
    validate_controls(controls)?;

    let mut aggressors = Vec::with_capacity(networks.fext.len() + networks.next.len());
    let mut selected_fext_amplitudes_v = Vec::with_capacity(networks.fext.len());
    for network in networks.fext {
        let amplitude_v = select_icn_amplitude_v1(controls.a_icn_fext_v, controls, "a_icn_fext")?;
        selected_fext_amplitudes_v.push(amplitude_v);
        aggressors.push(FdIcnAggressorV1 {
            role: "FEXT",
            frequency_hz: network.frequency_hz,
            transfer: network.sdd21,
            amplitude_v,
        });
    }

    let mut selected_next_amplitudes_v = Vec::with_capacity(networks.next.len());
    for network in networks.next {
        let amplitude_v = select_icn_amplitude_v1(controls.a_icn_next_v, controls, "a_icn_next")?;
        selected_next_amplitudes_v.push(amplitude_v);
        aggressors.push(FdIcnAggressorV1 {
            role: "NEXT",
            frequency_hz: network.frequency_hz,
            transfer: network.sdd21,
            amplitude_v,
        });
    }

    // This is intentionally a raw SDD21 call.  Package/equalizer VTFs are
    // not accepted at this boundary and are never synthesized here.
    let icn = r480_fd_icn_metrics_v1(
        &aggressors,
        controls.f1_hz,
        controls.f2_hz,
        controls.baud_hz,
        controls.samples_per_ui,
        controls.sample_dt_s,
        controls.baud_hz * controls.f_v,
        controls.f_r * controls.baud_hz,
    )?;
    let loss = fd_loss_metrics_v1(
        networks.thru.sdd21,
        networks.thru.frequency_hz,
        controls.baud_hz / 2.0,
        controls.f1_hz,
        controls.f2_hz,
        controls.baud_hz,
        controls.samples_per_ui,
        controls.sample_dt_s,
        controls.baud_hz * controls.f_v,
        controls.f_r * controls.baud_hz,
    )?;

    let metrics = FdRuntimeMetricsV1 {
        icn_mv: icn.icn_v * 1000.0,
        fext_icn_mv: icn.fext_icn_v * 1000.0,
        next_icn_mv: icn.next_icn_v * 1000.0,
        il_db_channel_only_at_fnq: loss.insertion_loss_at_nyquist_db,
        fitted_il_db_at_fnq: loss.fitted_loss_at_nyquist_db,
        fom_ild: loss.fom_ild,
    };
    if [
        metrics.icn_mv,
        metrics.fext_icn_mv,
        metrics.next_icn_mv,
        metrics.il_db_channel_only_at_fnq,
        metrics.fitted_il_db_at_fnq,
        metrics.fom_ild,
    ]
    .iter()
    .any(|value| !value.is_finite())
    {
        return Err(FdRuntimeErrorV1::InvalidControls(
            "FD composition produced a non-finite metric",
        ));
    }

    let diagnostics = FdRuntimeDiagnosticsV1 {
        transition_cutoff_hz: controls.baud_hz * controls.f_v,
        receiver_cutoff_hz: controls.f_r * controls.baud_hz,
        integration_start_index: icn.start_index,
        integration_end_index: icn.end_index,
        fext_aggressor_count: networks.fext.len(),
        next_aggressor_count: networks.next.len(),
        selected_fext_amplitudes_v,
        selected_next_amplitudes_v,
    };
    Ok((metrics, diagnostics))
}

fn validate_controls(controls: &FdRuntimeControlsV1<'_>) -> Result<(), FdRuntimeErrorV1> {
    if !controls.f1_hz.is_finite()
        || !controls.f2_hz.is_finite()
        || controls.f1_hz < 0.0
        || controls.f2_hz < controls.f1_hz
    {
        return Err(FdRuntimeErrorV1::InvalidControls(
            "f1/f2 must be finite with 0 <= f1 <= f2",
        ));
    }
    if controls.baud_hz <= 0.0 || !controls.baud_hz.is_finite() {
        return Err(FdRuntimeErrorV1::InvalidControls(
            "baud_hz must be finite and positive",
        ));
    }
    if controls.samples_per_ui == 0
        || controls.sample_dt_s <= 0.0
        || !controls.sample_dt_s.is_finite()
    {
        return Err(FdRuntimeErrorV1::InvalidControls(
            "samples_per_ui/sample_dt_s are invalid",
        ));
    }
    if controls.f_v <= 0.0
        || !controls.f_v.is_finite()
        || controls.f_r <= 0.0
        || !controls.f_r.is_finite()
        || !(controls.baud_hz * controls.f_v).is_finite()
        || !(controls.baud_hz * controls.f_r).is_finite()
    {
        return Err(FdRuntimeErrorV1::InvalidControls(
            "f_v/f_r must be finite and positive",
        ));
    }
    Ok(())
}

fn select_icn_amplitude_v1(
    values: &[f64],
    controls: &FdRuntimeControlsV1<'_>,
    role: &'static str,
) -> Result<f64, FdRuntimeErrorV1> {
    if values.is_empty() {
        return Err(FdRuntimeErrorV1::MissingAmplitude(role));
    }
    let index = if values.len() == 1 {
        0
    } else if controls.wc_portz {
        controls
            .tx_rd_sel
            .checked_sub(1)
            .ok_or(FdRuntimeErrorV1::InvalidPackageSelection(
                "Tx_rd_sel is one-based",
            ))?
    } else {
        let selected = controls
            .pkg_len_select
            .get(controls.package_case_index)
            .copied()
            .ok_or(FdRuntimeErrorV1::InvalidPackageSelection(
                "package case is outside pkg_len_select",
            ))?;
        selected
            .checked_sub(1)
            .ok_or(FdRuntimeErrorV1::InvalidPackageSelection(
                "pkg_len_select values are one-based",
            ))?
    };
    let amplitude_v =
        values
            .get(index)
            .copied()
            .ok_or(FdRuntimeErrorV1::InvalidPackageSelection(
                "selected package is outside the amplitude vector",
            ))?;
    if !amplitude_v.is_finite() || amplitude_v < 0.0 {
        return Err(FdRuntimeErrorV1::InvalidAmplitude(role));
    }
    Ok(amplitude_v)
}

#[cfg(test)]
mod tests {
    use super::*;

    const BAUD_HZ: f64 = 53_125_000_000.0;
    const SAMPLES_PER_UI: usize = 32;
    const SAMPLE_DT_S: f64 = 1.0 / BAUD_HZ / SAMPLES_PER_UI as f64;
    const F_V: f64 = 0.5935686274509804;
    const F_R: f64 = 0.75;

    fn controls<'a>(fext: &'a [f64], next: &'a [f64]) -> FdRuntimeControlsV1<'a> {
        FdRuntimeControlsV1 {
            f1_hz: 50_000_000.0,
            f2_hz: 40_000_000_000.0,
            baud_hz: BAUD_HZ,
            samples_per_ui: SAMPLES_PER_UI,
            sample_dt_s: SAMPLE_DT_S,
            f_v: F_V,
            f_r: F_R,
            a_icn_fext_v: fext,
            a_icn_next_v: next,
            wc_portz: false,
            tx_rd_sel: 1,
            pkg_len_select: &[1, 2],
            package_case_index: 0,
        }
    }

    fn sample_networks<'a>(
        frequencies: &'a [f64],
        fext: &'a [Complex64],
        next: &'a [Complex64],
    ) -> (FdRawSdd21V1<'a>, FdRawSdd21V1<'a>) {
        (
            FdRawSdd21V1 {
                frequency_hz: frequencies,
                sdd21: fext,
            },
            FdRawSdd21V1 {
                frequency_hz: frequencies,
                sdd21: next,
            },
        )
    }

    fn c(real: f64, imaginary: f64) -> Complex64 {
        Complex64::try_new(real, imaginary).expect("finite complex sample")
    }

    #[test]
    fn composes_raw_leaf_values_and_reports_source_controls() {
        let frequencies = [0.0, 1.0e9, 2.0e9, 3.0e9, 4.0e9];
        let thru = [
            c(1.0, 0.0),
            c(0.99, 0.0),
            c(0.98, 0.0),
            c(0.97, 0.0),
            c(0.96, 0.0),
        ];
        let fext = [
            c(0.01, 0.0),
            c(0.02, 0.0),
            c(0.03, 0.0),
            c(0.04, 0.0),
            c(0.05, 0.0),
        ];
        let next = [
            c(0.02, 0.0),
            c(0.03, 0.0),
            c(0.04, 0.0),
            c(0.05, 0.0),
            c(0.06, 0.0),
        ];
        let (fext_network, next_network) = sample_networks(&frequencies, &fext, &next);
        let networks = FdRawNetworkSetV1 {
            thru: FdRawSdd21V1 {
                frequency_hz: &frequencies,
                sdd21: &thru,
            },
            fext: std::slice::from_ref(&fext_network),
            next: std::slice::from_ref(&next_network),
        };
        let fext_amplitude = [0.6];
        let next_amplitude = [0.4];
        let controls = controls(&fext_amplitude, &next_amplitude);

        let (actual, diagnostics) = compose_fd_metrics_v1(&networks, &controls).unwrap();
        let direct_icn = r480_fd_icn_metrics_v1(
            &[
                FdIcnAggressorV1 {
                    role: "FEXT",
                    frequency_hz: &frequencies,
                    transfer: &fext,
                    amplitude_v: 0.6,
                },
                FdIcnAggressorV1 {
                    role: "NEXT",
                    frequency_hz: &frequencies,
                    transfer: &next,
                    amplitude_v: 0.4,
                },
            ],
            controls.f1_hz,
            controls.f2_hz,
            controls.baud_hz,
            controls.samples_per_ui,
            controls.sample_dt_s,
            controls.baud_hz * controls.f_v,
            controls.f_r * controls.baud_hz,
        )
        .unwrap();
        let direct_loss = fd_loss_metrics_v1(
            &thru,
            &frequencies,
            controls.baud_hz / 2.0,
            controls.f1_hz,
            controls.f2_hz,
            controls.baud_hz,
            controls.samples_per_ui,
            controls.sample_dt_s,
            controls.baud_hz * controls.f_v,
            controls.f_r * controls.baud_hz,
        )
        .unwrap();
        assert_eq!(actual.icn_mv, direct_icn.icn_v * 1000.0);
        assert_eq!(actual.fext_icn_mv, direct_icn.fext_icn_v * 1000.0);
        assert_eq!(actual.next_icn_mv, direct_icn.next_icn_v * 1000.0);
        assert_eq!(
            actual.il_db_channel_only_at_fnq,
            direct_loss.insertion_loss_at_nyquist_db
        );
        assert_eq!(
            actual.fitted_il_db_at_fnq,
            direct_loss.fitted_loss_at_nyquist_db
        );
        assert_eq!(actual.fom_ild, direct_loss.fom_ild);
        assert_eq!(diagnostics.selected_fext_amplitudes_v, vec![0.6]);
        assert_eq!(diagnostics.selected_next_amplitudes_v, vec![0.4]);
        assert_eq!(diagnostics.fext_aggressor_count, 1);
        assert_eq!(diagnostics.next_aggressor_count, 1);
        assert_eq!(
            diagnostics.transition_cutoff_hz,
            controls.baud_hz * controls.f_v
        );
        assert_eq!(
            diagnostics.receiver_cutoff_hz,
            controls.baud_hz * controls.f_r
        );
    }

    #[test]
    fn singleton_amplitudes_broadcast_and_package_controls_select_vectors() {
        let frequencies = [0.0, 1.0e9, 2.0e9, 3.0e9, 4.0e9];
        let thru = [c(1.0, 0.0); 5];
        let fext = [c(0.01, 0.0); 5];
        let next = [c(0.02, 0.0); 5];
        let (fext_network, next_network) = sample_networks(&frequencies, &fext, &next);
        let networks = FdRawNetworkSetV1 {
            thru: FdRawSdd21V1 {
                frequency_hz: &frequencies,
                sdd21: &thru,
            },
            fext: std::slice::from_ref(&fext_network),
            next: std::slice::from_ref(&next_network),
        };

        let singleton_fext = [0.6];
        let singleton_next = [0.4];
        let singleton_controls = controls(&singleton_fext, &singleton_next);
        let (_, diagnostics) = compose_fd_metrics_v1(&networks, &singleton_controls).unwrap();
        assert_eq!(diagnostics.selected_fext_amplitudes_v, vec![0.6]);
        assert_eq!(diagnostics.selected_next_amplitudes_v, vec![0.4]);

        let fext_values = [0.2, 0.6];
        let next_values = [0.3, 0.4];
        let mut package_controls = controls(&fext_values, &next_values);
        package_controls.package_case_index = 1;
        let (_, diagnostics) = compose_fd_metrics_v1(&networks, &package_controls).unwrap();
        assert_eq!(diagnostics.selected_fext_amplitudes_v, vec![0.6]);
        assert_eq!(diagnostics.selected_next_amplitudes_v, vec![0.4]);

        package_controls.wc_portz = true;
        package_controls.tx_rd_sel = 1;
        let (_, diagnostics) = compose_fd_metrics_v1(&networks, &package_controls).unwrap();
        assert_eq!(diagnostics.selected_fext_amplitudes_v, vec![0.2]);
        assert_eq!(diagnostics.selected_next_amplitudes_v, vec![0.3]);
    }

    #[test]
    fn rejects_missing_or_invalid_package_amplitudes() {
        let frequencies = [0.0, 1.0e9, 2.0e9, 3.0e9, 4.0e9];
        let thru = [c(1.0, 0.0); 5];
        let fext = [c(0.01, 0.0); 5];
        let next = [c(0.02, 0.0); 5];
        let (fext_network, next_network) = sample_networks(&frequencies, &fext, &next);
        let networks = FdRawNetworkSetV1 {
            thru: FdRawSdd21V1 {
                frequency_hz: &frequencies,
                sdd21: &thru,
            },
            fext: std::slice::from_ref(&fext_network),
            next: std::slice::from_ref(&next_network),
        };

        let empty: [f64; 0] = [];
        let next_amplitude = [0.4];
        let missing_controls = controls(&empty, &next_amplitude);
        assert_eq!(
            compose_fd_metrics_v1(&networks, &missing_controls),
            Err(FdRuntimeErrorV1::MissingAmplitude("a_icn_fext"))
        );

        let fext_values = [0.2, 0.6];
        let next_values = [0.3, 0.4];
        let mut controls = controls(&fext_values, &next_values);
        controls.package_case_index = 2;
        assert!(matches!(
            compose_fd_metrics_v1(&networks, &controls),
            Err(FdRuntimeErrorV1::InvalidPackageSelection(_))
        ));
        controls.package_case_index = 0;
        controls.pkg_len_select = &[0, 1];
        assert!(matches!(
            compose_fd_metrics_v1(&networks, &controls),
            Err(FdRuntimeErrorV1::InvalidPackageSelection(_))
        ));
        controls.pkg_len_select = &[3, 1];
        assert!(matches!(
            compose_fd_metrics_v1(&networks, &controls),
            Err(FdRuntimeErrorV1::InvalidPackageSelection(_))
        ));
        controls.pkg_len_select = &[1, 2];
        controls.wc_portz = true;
        controls.tx_rd_sel = 0;
        assert!(matches!(
            compose_fd_metrics_v1(&networks, &controls),
            Err(FdRuntimeErrorV1::InvalidPackageSelection(_))
        ));

        let invalid = [f64::NAN];
        controls.wc_portz = false;
        controls.tx_rd_sel = 1;
        controls.a_icn_fext_v = &invalid;
        assert_eq!(
            compose_fd_metrics_v1(&networks, &controls),
            Err(FdRuntimeErrorV1::InvalidAmplitude("a_icn_fext"))
        );
    }

    #[test]
    fn changes_to_raw_transfer_are_reflected_without_constructing_vtf() {
        let frequencies = [0.0, 1.0e9, 2.0e9, 3.0e9, 4.0e9];
        let thru_a = [
            c(1.0, 0.0),
            c(0.99, 0.0),
            c(0.98, 0.0),
            c(0.97, 0.0),
            c(0.96, 0.0),
        ];
        let thru_b = [
            c(0.5, 0.0),
            c(0.49, 0.0),
            c(0.48, 0.0),
            c(0.47, 0.0),
            c(0.46, 0.0),
        ];
        let fext_a = [c(0.01, 0.0); 5];
        let fext_b = [c(0.02, 0.0); 5];
        let next = [c(0.02, 0.0); 5];
        let fext_amplitude = [0.6];
        let next_amplitude = [0.4];
        let controls = controls(&fext_amplitude, &next_amplitude);
        let (fext_a_network, next_a_network) = sample_networks(&frequencies, &fext_a, &next);
        let networks_a = FdRawNetworkSetV1 {
            thru: FdRawSdd21V1 {
                frequency_hz: &frequencies,
                sdd21: &thru_a,
            },
            fext: std::slice::from_ref(&fext_a_network),
            next: std::slice::from_ref(&next_a_network),
        };
        let (fext_b_network, next_b_network) = sample_networks(&frequencies, &fext_b, &next);
        let networks_b = FdRawNetworkSetV1 {
            thru: FdRawSdd21V1 {
                frequency_hz: &frequencies,
                sdd21: &thru_b,
            },
            fext: std::slice::from_ref(&fext_b_network),
            next: std::slice::from_ref(&next_b_network),
        };
        let first = compose_fd_metrics_v1(&networks_a, &controls).unwrap().0;
        let second = compose_fd_metrics_v1(&networks_b, &controls).unwrap().0;
        assert_ne!(first.icn_mv, second.icn_mv);
        assert_ne!(
            first.il_db_channel_only_at_fnq,
            second.il_db_channel_only_at_fnq
        );
        assert_ne!(first.fitted_il_db_at_fnq, second.fitted_il_db_at_fnq);
    }

    #[test]
    fn tp0v_synthetic_raw_sdd21_matches_pinned_fd_canary() {
        let mut frequencies = Vec::with_capacity(8001);
        let mut thru = Vec::with_capacity(8001);
        let mut fext = Vec::with_capacity(8001);
        let mut next = Vec::with_capacity(8001);
        let target_frequency_hz = 26.56e9;
        let thru_target_magnitude = 10.0_f64.powf(-10.0 / 20.0);
        let thru_pole_hz = target_frequency_hz / (1.0 / thru_target_magnitude.powi(2) - 1.0).sqrt();
        for index in 0..=8000 {
            let frequency_hz = index as f64 * 10.0e6;
            frequencies.push(frequency_hz);
            thru.push(thru_transfer(frequency_hz, thru_pole_hz, 1.0e-9));
            fext.push(crosstalk_transfer(
                frequency_hz,
                target_frequency_hz,
                1.15e-9,
            ));
            next.push(crosstalk_transfer(
                frequency_hz,
                target_frequency_hz,
                0.25e-9,
            ));
        }
        let (fext_network, next_network) = sample_networks(&frequencies, &fext, &next);
        let networks = FdRawNetworkSetV1 {
            thru: FdRawSdd21V1 {
                frequency_hz: &frequencies,
                sdd21: &thru,
            },
            fext: std::slice::from_ref(&fext_network),
            next: std::slice::from_ref(&next_network),
        };
        let fext_amplitude = [0.6];
        let next_amplitude = [0.6];
        let controls = controls(&fext_amplitude, &next_amplitude);
        let (metrics, _) = compose_fd_metrics_v1(&networks, &controls).unwrap();
        assert!((metrics.icn_mv - 4.601554213273623).abs() < 2.0e-12);
        assert!((metrics.il_db_channel_only_at_fnq - 10.000735704402235).abs() < 2.0e-12);
        // The source canary was generated through NumPy/MATLAB.  The Rust
        // leaf intentionally keeps its direct normal-equation arithmetic;
        // permit the last few ulps of cross-runtime reduction variation.
        assert!((metrics.fitted_il_db_at_fnq - 9.834912844952038).abs() < 2.0e-9);
    }

    fn crosstalk_transfer(frequency_hz: f64, target_frequency_hz: f64, delay_s: f64) -> Complex64 {
        let target_magnitude = 10.0_f64.powf(-40.0 / 20.0);
        let ratio = frequency_hz / target_frequency_hz;
        let denominator = 1.0 + ratio * ratio;
        let scale = 2.0_f64.sqrt() * target_magnitude;
        let high_pass_real = scale * ratio * ratio / denominator;
        let high_pass_imaginary = scale * ratio / denominator;
        rotate(high_pass_real, high_pass_imaginary, frequency_hz, delay_s)
    }

    fn thru_transfer(frequency_hz: f64, pole_hz: f64, delay_s: f64) -> Complex64 {
        let ratio = frequency_hz / pole_hz;
        let denominator = 1.0 + ratio * ratio;
        let low_pass_real = 1.0 / denominator;
        let low_pass_imaginary = -ratio / denominator;
        rotate(low_pass_real, low_pass_imaginary, frequency_hz, delay_s)
    }

    fn rotate(real: f64, imaginary: f64, frequency_hz: f64, delay_s: f64) -> Complex64 {
        let angle = 2.0 * std::f64::consts::PI * frequency_hz * delay_s;
        let cosine = angle.cos();
        let sine = angle.sin();
        c(
            real * cosine + imaginary * sine,
            imaginary * cosine - real * sine,
        )
    }
}
