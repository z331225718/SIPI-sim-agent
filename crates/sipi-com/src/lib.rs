#![forbid(unsafe_code)]
// The clean-room COM ports intentionally retain source-shaped numerical loops
// and fixed public call surfaces so their index/order semantics remain auditable.
#![allow(
    clippy::needless_range_loop,
    clippy::neg_cmp_op_on_partial_ord,
    clippy::too_many_arguments,
    clippy::type_complexity
)]

//! Clean-room typed stage-output envelope for the R480 COM surface.
//!
//! The envelope types are structured after the observed MATLAB oracle
//! output surface (P5-06b metric surface): network metrics, output
//! metrics, and per-case checkpoints. Portable numerical stages are exposed
//! alongside the envelope; MATLAB-only reporting and acceptance remain out
//! of scope for this crate.

mod bathtub_fit_v1;
mod bathtub_v1;
mod build_noise_pdf_v1;
mod c2m_eye_v1;
mod calibration_v1;
mod candidate_eval_v1;
mod candidate_helpers_v1;
mod canonical_input_keys_v1;
mod com_chain_v1;
mod com_metrics_v1;
mod com_parameter_ingestion_v1;
mod com_parameter_resolver_v1;
mod com_parameters_v1;
mod com_run_admission_v1;
mod com_run_artifact_execution_v1;
mod com_run_artifact_provenance_v1;
mod com_run_execution_v1;
mod com_specified_artifact_execution_v1;
mod com_specified_parameter_ingestion_v1;
mod combined_noise_pdf_v1;
mod compliance_report_v1;
mod crosstalk_noise_v1;
mod csv_reader_v1;
mod db_tolerance_v1;
mod dfe_v1;
mod discrete_pdf_v1;
mod equalization_apply_v1;
mod equalizer_frontend_v1;
mod erf_v1;
mod eye_contour_v1;
mod fd_to_td_v1;
mod horizontal_margin_v1;
mod ingest_v1;
mod mat_reader_v1;
mod matlab_literal_v1;
mod mixed_mode_v1;
mod mmse_v1;
mod parameter_surface_v1;
mod qfactor_ber_v1;
mod receiver_noise_v1;
mod residual_channel_pdf_v1;
mod resolve_parameters_v1;
mod rx_ffe_v1;
mod rxffe_search_v1;
mod sampled_signal_pdf_v1;
mod search_loop_v1;
mod search_support_v1;
mod tdiln_v1;
mod tx_ffe_v1;
mod value_consumption_v1;
mod warning_detector_v1;
mod warning_report_v1;
mod workbook_v1;
pub use bathtub_fit_v1::{
    BATHTUB_FIT_MAX_ORDER, BATHTUB_FIT_POLICY_V1, BathtubCurveFitV1, BathtubFitErrorV1,
    fit_bathtub_curve_v1,
};
pub use bathtub_v1::{
    BATHTUB_POLICY_V1, BathtubErrorV1, BathtubSampleV1, bathtub_opening_width_v1,
};
pub use build_noise_pdf_v1::{BUILD_NOISE_PDF_POLICY_V1, R480NoisePdfV1, build_r480_noise_pdf_v1};
pub use c2m_eye_v1::{C2M_EYE_POLICY_V1, C2mEyeErrorV1, calculate_c2m_vertical_eye_v1};
pub use calibration_v1::{
    CALIBRATION_POLICY_V1, CalibrationErrorV1, CalibrationIterationV1, CalibrationNoiseResultV1,
    CalibrationResultV1, MAX_CALIBRATION_ITERATIONS_V1, calculate_r480_calibration_noise_v1,
    calibrate_receiver_noise_v1,
};
pub use candidate_eval_v1::{
    CANDIDATE_EVAL_POLICY_V1, CandidateEvalErrorV1, CandidateEvalOptionsV1, CandidateEvalParamsV1,
    NonMmseSearchResultV1, c2m_candidate_fom_v1, evaluate_candidate_v1,
};
pub use candidate_helpers_v1::{
    CANDIDATE_HELPERS_POLICY_V1, CandidateErrorV1, DfeCandidateParamsV1, candidate_ber_q_v1,
    cannot_improve_fom_v1, dfe_candidate_bounds_v1, jitter_response_v1, jitter_sigma_v1,
    r480_bbn_q_factor_v1, r480_pdf_bin_size_v1,
};
pub use canonical_input_keys_v1::{
    CANONICAL_INPUT_KEYS_POLICY_V1, CanonicalInputKeysErrorV1, canonical_input_keys_v1,
};
pub use com_chain_v1::{
    COM_CHAIN_POLICY_V1, ComChainControlsV1, ComChainErrorV1, ComChainReportV1, run_com_chain_v1,
    run_com_chain_with_crosstalk_v1,
};
pub use com_metrics_v1::{
    COM_METRICS_POLICY_V1, ComMetricsErrorV1, ComMetricsV1, calculate_com_metrics_v1,
};
pub use com_parameter_ingestion_v1::{
    COM_PARAMETER_INGESTION_POLICY_V1, ComParameterConsumptionReportV1,
    ComParameterIngestionErrorV1, ComParameterIngestionV1, ingest_com_parameters_v1,
};
pub use com_parameter_resolver_v1::{
    COM_PARAMETER_RESOLVER_POLICY_V1, ComParameterResolverErrorV1,
    resolve_com_parameter_controls_v1,
};
pub use com_parameters_v1::{
    COM_PARAMETERS_POLICY_V1, ComParametersErrorV1, ComParametersV1, merge_com_parameters_v1,
};
pub use com_run_admission_v1::{
    COM_RUN_ADMISSION_POLICY_V1, COM_RUN_REQUEST_SCHEMA_V1, ComRunAdmissionErrorV1,
    ComRunAdmissionV1, com_run_admission_v1,
};
pub use com_run_artifact_execution_v1::{
    COM_RUN_ARTIFACT_EXECUTION_POLICY_V1, COM_RUN_ARTIFACT_EXECUTION_RESULT_SCHEMA_V1,
    COM_RUN_PULSE_FILE_V1, COM_RUN_PULSE_MAX_BYTES_V1, COM_RUN_RESULT_FILE_V1,
    COM_RUN_RESULT_MAX_BYTES_V1, ComRunArtifactExecutionErrorV1, ComRunArtifactExecutionReportV1,
    ComRunPulseArtifactIdentityV1, execute_com_run_artifact_v1,
};
pub use com_run_artifact_provenance_v1::{
    COM_RUN_ARTIFACT_MAX_ENTRY_COUNT_V1, COM_RUN_ARTIFACT_MAX_MANIFEST_BYTES_V1,
    COM_RUN_ARTIFACT_MAX_REPORT_BYTES_V1, COM_RUN_ARTIFACT_MAX_TOTAL_PAYLOAD_BYTES_V1,
    COM_RUN_ARTIFACT_PROVENANCE_POLICY_V1, COM_RUN_ARTIFACT_REQUEST_MAX_BYTES_V1,
    ComRunArtifactBindingV1, ComRunArtifactProvenanceErrorV1, ComRunArtifactProvenanceV1,
    inspect_com_run_artifact_provenance_v1, parse_com_run_artifact_binding_v1,
};
pub use com_run_execution_v1::{
    COM_RUN_EXECUTION_POLICY_V1, COM_RUN_RESULT_SCHEMA_V1, ComRunExecutionErrorV1,
    ComRunResultEnvelopeV1, execute_com_run_v1, execute_com_run_with_crosstalk_v1,
};
pub use com_specified_artifact_execution_v1::{
    COM_RUN_ARTIFACT_SPECIFIED_POLICY_V1, COM_RUN_ARTIFACT_SPECIFIED_RESULT_SCHEMA_V1,
    ComSpecifiedArtifactExecutionErrorV1, ComSpecifiedArtifactExecutionReportV1,
    execute_com_run_artifact_from_product_values_v1,
};
pub use com_specified_parameter_ingestion_v1::{
    COM_SPECIFIED_PARAMETER_INGESTION_POLICY_V1, ComSpecifiedParameterConsumptionReportV1,
    ComSpecifiedParameterIngestionErrorV1, ComSpecifiedParameterIngestionV1,
    ingest_com_specified_parameters_v1,
};
pub use combined_noise_pdf_v1::{
    COMBINED_NOISE_PDF_POLICY_V1, CombinedNoisePdfV1, combine_r480_noise_pdf_v1,
};
pub use compliance_report_v1::{
    COMPLIANCE_REPORT_POLICY_V1, ComplianceErrorV1, ComplianceMetricSpecV1, ComplianceReportV1,
    MetricComplianceV1, compliance_report_v1,
};
pub use crosstalk_noise_v1::{
    CROSSTALK_NOISE_POLICY_V1, XtalkChannelV1, XtalkErrorV1, XtalkParamsV1, crosstalk_noise_v1,
    td_source_crosstalk_noise_v1,
};
pub use csv_reader_v1::{CSV_READER_POLICY_V1, csv_value_v1, read_com_settings_csv_v1};
pub use db_tolerance_v1::{
    DB_TOLERANCE_POLICY_V1, DbToleranceErrorV1, DbToleranceResultV1, OWNER_DB_TOLERANCE_V1,
    db_tolerance_check_v1, owner_db_tolerance_check_v1,
};
pub use dfe_v1::{
    DFE_POLICY_V1, DfeBankResultV1, DfeErrorV1, TailRssBoundsV1, apply_dfe_bank_v1,
    apply_tail_rss_bounds_v1, clip_dfe_v1, find_dfe_bank_locations_v1,
};
pub use discrete_pdf_v1::{
    DISCRETE_PDF_POLICY_V1, DiscretePdfV1, PdfErrorV1, convolve_v1, normal_pdf_v1,
};
pub use equalization_apply_v1::{
    EQUALIZATION_APPLY_POLICY_V1, EqualizationApplyErrorV1, EqualizedChannelsV1,
    apply_r480_equalization_v1,
};
pub use equalizer_frontend_v1::{
    CursorSampleV1, EQUALIZER_FRONTEND_POLICY_V1, EqualizerErrorV1, cursor_sample_index_v1,
    fd_ctle_v1, td_ctle_v1,
};
pub use erf_v1::{ERF_POLICY_V1, erf_v1, erfcinv_v1, erfinv_v1};
pub use eye_contour_v1::{
    EYE_CONTOUR_POLICY_V1, EyeContourErrorV1, EyeContourV1, EyeGridV1, TimeColumnContourV1,
    statistical_eye_contour_v1,
};
pub use fd_to_td_v1::{
    FD_TO_TD_POLICY_V1, FdToTdErrorV1, FdToTdOptionsV1, ImpulseResultV1, MAX_FD_TO_TD_BINS_V1,
    rectangular_pulse_response_fd_v1, s21_to_impulse_dc_v1,
};
pub use horizontal_margin_v1::{
    HORIZONTAL_MARGIN_POLICY_V1, HorizontalMarginErrorV1, HorizontalMarginsV1,
    compute_horizontal_margins_v1, margins_from_bathtub_v1,
};
pub use ingest_v1::{
    FILE_TO_INTERNAL_ORDER_V1, INGEST_POLICY_V1, Sdd21SampleV1, apply_internal_port_order_v1,
    ingest_row_v1,
};
pub use mat_reader_v1::{MAT_READER_POLICY_V1, read_com_settings_mat_v1};
pub use matlab_literal_v1::{LiteralV1, parse_literal_v1};
pub use mixed_mode_v1::{
    FourPortSMatrixV1, MixedModeErrorV1, NETWORK_INGEST_POLICY_V1, apply_r480_pn_skew_v1,
    com_mixed_mode_spectrum_v1, com_mixed_mode_v1, com_t_v1, sdd21_v1,
};
pub use mmse_v1::{
    MAX_MMSE_CANDIDATES_V1, MAX_MMSE_MATRIX_DIM_V1, MMSE_POLICY_V1, MmseCandidateSpecV1,
    MmseErrorV1, MmseResultV1, MmseSearchResultV1, constrained_mmse_v1, search_mmse_candidates_v1,
};
pub use parameter_surface_v1::{
    PARAMETER_SURFACE_POLICY_V1, ParameterPairV1, ParameterSurfaceReportV1,
    classify_parameter_surface_v1, extract_parameter_pairs_v1,
};
pub use qfactor_ber_v1::{
    OWNER_TOLERANCE_POLICY_V1, QFACTOR_BER_POLICY_V1, QFactorBerErrorV1, ber_to_q_factor_v1,
    estimate_ber_v1, estimate_q_factor_v1, q_factor_to_ber_v1,
};
pub use receiver_noise_v1::{
    NoiseErrorV1, RECEIVER_NOISE_POLICY_V1, ReceiverNoiseOptionsV1, ReceiverNoiseParamsV1,
    bessel_thomson_filter_v1, butterworth_filter_v1, raised_cosine_filter_v1, receiver_noise_v1,
    rx_ffe_frequency_response_v1, tukey_window_v1,
};
pub use residual_channel_pdf_v1::{
    RESIDUAL_CHANNEL_PDF_POLICY_V1, ResidualPdfResultV1, residual_channel_pdf_v1,
};
pub use resolve_parameters_v1::{
    RESOLVE_PARAMETERS_POLICY_V1, ResolveParametersErrorV1, resolve_default_set_v1,
};
pub use rx_ffe_v1::{
    FLOATING_RX_FFE_POLICY_V1, ForcedRxFfeResultV1, RX_FFE_POLICY_V1, RxFfeErrorV1,
    apply_rx_ffe_v1, force_floating_rx_ffe_v1, force_rx_ffe_v1,
};
pub use rxffe_search_v1::{
    MAX_RXFFE_SEARCH_CANDIDATES_V1, MAX_RXFFE_SEARCH_WAVEFORM_SAMPLES_V1, RXFFE_SEARCH_POLICY_V1,
    RxFfeSearchCandidateV1, RxFfeSearchErrorV1, RxFfeSearchEvaluationV1, RxFfeSearchResultV1,
    search_fvlms_rxffe_candidates_v1,
};
pub use sampled_signal_pdf_v1::{
    PAM4_SYMBOL_VALUES, SAMPLED_SIGNAL_PDF_POLICY_V1, accelerated_sampled_signal_pdf_v1,
    from_values_v1, sampled_signal_pdf_v1, sparse_pam_component_v1,
};
pub use search_loop_v1::{
    SEARCH_LOOP_POLICY_V1, SearchFullOptionsV1, SearchFullParamsV1, SearchLoopErrorV1,
    SearchLoopOptionsV1, SearchLoopParamsV1, SearchLoopResultV1, anchored_cursor, peak_window,
    r480_sample_offsets, rectangular_pulse_response_v1, search_r480_nonmmse_no_xtalk_v1,
    search_r480_nonmmse_no_xtalk_with_sigma_v1, shift_matrix, skip_high_pass_local_search,
    skip_local_search, validate_supported_branch,
};
pub use search_support_v1::{
    CtleParamsV1, SEARCH_SUPPORT_POLICY_V1, SearchErrorV1, apply_ctle_candidate_v1,
    ctle_frequency_response_v1, high_pass_candidates_v1, indexed_config_value_v1,
    qualified_ctle_pair_v1, selected_accm_rms_v1, selected_sndr_v1, system_noise_response_v1,
};
pub use tdiln_v1::{TDILN_POLICY_V1, TdIlnErrorV1, TdIlnResultV1, r480_tdiln_v1};
pub use tx_ffe_v1::{
    CandidateSelectionV1, FomSelectionV1, TX_FFE_POLICY_V1, TxFfeErrorV1, TxFfeGridV1,
    build_txffe_grid_v1, first_strict_best_v1, full_grid_matrix_v1, select_fom_tracker_v1,
    select_strict_best_v1,
};
pub use value_consumption_v1::{
    ConsumptionErrorV1, ResolvedDefaultV1, VALUE_CONSUMPTION_POLICY_V1, resolve_default_value_v1,
};
pub use warning_detector_v1::{
    WARNING_DETECTOR_POLICY_V1, WarningDetectorErrorV1, anti_causal_precursor_fraction_v1,
    detect_anti_causal_v1, detect_high_freq_non_decay_v1,
};
pub use warning_report_v1::{
    WARNING_REPORT_POLICY_V1, WarningCodeV1, WarningReportErrorV1, WarningReportV1,
    WarningSliceReportV1, aggregate_warning_report_v1,
};
pub use workbook_v1::{
    CellValueV1, ComSettingsV1, RawCellV1, WORKBOOK_IMPORT_POLICY_V1, WorkbookErrorV1,
    is_strict_ooxml_v1, read_com_settings_xlsx_v1, validate_xlsx_container_v1,
};

/// One metric value: `Some(finite)` for a finite value, `None` for
/// infinity (observed e.g. as ERL11 = inf in the oracle output).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ComMetricValueV1 {
    finite: Option<f64>,
}
impl ComMetricValueV1 {
    pub fn try_new(finite: Option<f64>) -> Result<Self, ComEnvelopeErrorV1> {
        if let Some(value) = finite
            && !value.is_finite()
        {
            return Err(ComEnvelopeErrorV1::NonFiniteMetric);
        }
        Ok(Self { finite })
    }

    pub const fn finite(self) -> Option<f64> {
        self.finite
    }
}

/// Envelope construction errors.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ComEnvelopeErrorV1 {
    NonFiniteMetric,
}

/// The fourteen output metrics observed in the oracle summary.
#[derive(Clone, Debug, PartialEq)]
pub struct ComOutputMetricsV1 {
    fom: ComMetricValueV1,
    com_db: ComMetricValueV1,
    vec_db: ComMetricValueV1,
    veo_mv: ComMetricValueV1,
    erl: ComMetricValueV1,
    erl11: ComMetricValueV1,
    erl22: ComMetricValueV1,
    il_db_channel_only_at_fnq: ComMetricValueV1,
    fitted_il_db_at_fnq: ComMetricValueV1,
    icn_mv: ComMetricValueV1,
    peak_isi_xtk_noise_at_ber_mv: ComMetricValueV1,
    ctle_dc_gain_db: ComMetricValueV1,
    g_dc_hp: ComMetricValueV1,
    itick: ComMetricValueV1,
}

impl ComOutputMetricsV1 {
    pub fn try_new(values: [ComMetricValueV1; 14]) -> Self {
        Self {
            fom: values[0],
            com_db: values[1],
            vec_db: values[2],
            veo_mv: values[3],
            erl: values[4],
            erl11: values[5],
            erl22: values[6],
            il_db_channel_only_at_fnq: values[7],
            fitted_il_db_at_fnq: values[8],
            icn_mv: values[9],
            peak_isi_xtk_noise_at_ber_mv: values[10],
            ctle_dc_gain_db: values[11],
            g_dc_hp: values[12],
            itick: values[13],
        }
    }

    pub fn fom(&self) -> ComMetricValueV1 {
        self.fom
    }

    pub fn com_db(&self) -> ComMetricValueV1 {
        self.com_db
    }
}

/// One observed network metric row (THRU / FEXT1 / NEXT1 roles).
#[derive(Clone, Debug, PartialEq)]
pub struct ComNetworkMetricV1 {
    role: String,
    input_kind: String,
    frequency_hz: f64,
    sdd21_db: f64,
    sdc21_abs: f64,
}

impl ComNetworkMetricV1 {
    pub fn try_new(
        role: String,
        input_kind: String,
        frequency_hz: f64,
        sdd21_db: f64,
        sdc21_abs: f64,
    ) -> Result<Self, ComEnvelopeErrorV1> {
        if !(frequency_hz > 0.0) || !sdd21_db.is_finite() || !sdc21_abs.is_finite() {
            return Err(ComEnvelopeErrorV1::NonFiniteMetric);
        }
        Ok(Self {
            role,
            input_kind,
            frequency_hz,
            sdd21_db,
            sdc21_abs,
        })
    }

    pub fn role(&self) -> &str {
        &self.role
    }

    pub fn sdd21_db(&self) -> f64 {
        self.sdd21_db
    }
}

/// One observed internal checkpoint row (TXLE/DFE taps, sigma_N,
/// tail_RSS, sgm, itick).
#[derive(Clone, Debug, PartialEq)]
pub struct ComCaseCheckpointV1 {
    txle_taps: Vec<i64>,
    dfe_taps: Vec<i64>,
    sigma_n: f64,
    tail_rss: f64,
    sgm: f64,
    itick: i64,
}

impl ComCaseCheckpointV1 {
    pub fn try_new(
        txle_taps: Vec<i64>,
        dfe_taps: Vec<i64>,
        sigma_n: f64,
        tail_rss: f64,
        sgm: f64,
        itick: i64,
    ) -> Result<Self, ComEnvelopeErrorV1> {
        if txle_taps.is_empty()
            || txle_taps.iter().any(|tap| *tap < 0)
            || dfe_taps.iter().any(|tap| *tap < 0)
            || itick < 0
            || !sigma_n.is_finite()
            || !tail_rss.is_finite()
            || !sgm.is_finite()
        {
            return Err(ComEnvelopeErrorV1::NonFiniteMetric);
        }
        Ok(Self {
            txle_taps,
            dfe_taps,
            sigma_n,
            tail_rss,
            sgm,
            itick,
        })
    }

    pub fn txle_taps(&self) -> &[i64] {
        &self.txle_taps
    }

    pub fn itick(&self) -> i64 {
        self.itick
    }
}

/// Explicit scope policy of the typed stage-output envelope.
pub const COM_STAGE_OUTPUT_ENVELOPE_POLICY_V1: &str =
    "sipi.p5-03a.com-stage-output-envelope-v1.typed-structure-only";

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn metrics_accept_finite_and_infinity() {
        assert!(ComMetricValueV1::try_new(Some(3.0)).is_ok());
        assert!(ComMetricValueV1::try_new(None).is_ok());
        assert!(ComMetricValueV1::try_new(Some(f64::INFINITY)).is_err());
    }

    #[test]
    fn output_metrics_envelope_constructs() {
        let values: [ComMetricValueV1; 14] =
            std::array::from_fn(|_| ComMetricValueV1::try_new(Some(1.0)).expect("metric"));
        let metrics = ComOutputMetricsV1::try_new(values);
        assert_eq!(metrics.fom().finite(), Some(1.0));
        assert_eq!(metrics.com_db().finite(), Some(1.0));
    }

    #[test]
    fn network_metric_validates_scalars() {
        let metric = ComNetworkMetricV1::try_new(
            "THRU".to_string(),
            "s4p".to_string(),
            2.656e10,
            -10.0,
            0.316,
        )
        .expect("metric");
        assert_eq!(metric.role(), "THRU");
        assert!(
            ComNetworkMetricV1::try_new("THRU".to_string(), "s4p".to_string(), 0.0, -10.0, 0.316,)
                .is_err()
        );
    }

    #[test]
    fn checkpoint_validates_taps_and_itick() {
        let checkpoint = ComCaseCheckpointV1::try_new(vec![2, 1, 0], vec![1], 0.01, 0.02, 0.03, 4)
            .expect("checkpoint");
        assert_eq!(checkpoint.txle_taps(), &[2, 1, 0]);
        assert_eq!(checkpoint.itick(), 4);
        assert!(ComCaseCheckpointV1::try_new(vec![], vec![1], 0.01, 0.02, 0.03, 4).is_err());
        assert!(ComCaseCheckpointV1::try_new(vec![1], vec![], 0.01, 0.02, 0.03, -1).is_err());
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            COM_STAGE_OUTPUT_ENVELOPE_POLICY_V1,
            "sipi.p5-03a.com-stage-output-envelope-v1.typed-structure-only",
        );
    }
}
