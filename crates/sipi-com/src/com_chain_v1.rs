//! Fixed-tap COM metric chain composition core (P5-06f).
//!
//! Composes already-ported R480 stage cores into a product chain with
//! caller-supplied equalizer taps and noise scalars: cursor selection
//! (P5-04i) -> residual-channel PDF with DFE cancellation (P5-04g) ->
//! r4.80 noise-PDF build (P5-04h) -> combined noise PDF (P5-04e) ->
//! COM/VEC/VEO metrics (P5-04c). The equalizer search loop (P5-04t),
//! frequency-domain receiver noise (P5-04o) and TX-FFE tap synthesis
//! (P5-04j) remain explicit caller-supplied inputs. FEXT/NEXT pulse inputs
//! are composed through the portable residual PDF and noise-PDF stages
//! rather than being silently ignored. Fail-closed: every stage rejection
//! and every non-finite control is a hard error.

use crate::build_noise_pdf_v1::{R480NoisePdfV1, build_r480_noise_pdf_v1};
use crate::com_metrics_v1::{ComMetricsV1, calculate_com_metrics_v1};
use crate::combined_noise_pdf_v1::{CombinedNoisePdfV1, combine_r480_noise_pdf_v1};
use crate::discrete_pdf_v1::PdfErrorV1;
use crate::equalizer_frontend_v1::{CursorSampleV1, EqualizerErrorV1, cursor_sample_index_v1};
use crate::residual_channel_pdf_v1::{ResidualPdfResultV1, residual_channel_pdf_v1};

/// Explicit scope policy of the fixed-tap chain composition core.
pub const COM_CHAIN_POLICY_V1: &str =
    "sipi.p5-06f.com-chain-v1.fixed-tap-cursor-residual-noise-metrics";

/// Chain composition errors (stage rejections are mapped, never masked).
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum ComChainErrorV1 {
    InvalidControls,
    EmptyPulse,
    NonFinite,
    Equalizer,
    Pdf,
    Metrics,
}

impl From<EqualizerErrorV1> for ComChainErrorV1 {
    fn from(_: EqualizerErrorV1) -> Self {
        ComChainErrorV1::Equalizer
    }
}
impl From<PdfErrorV1> for ComChainErrorV1 {
    fn from(_: PdfErrorV1) -> Self {
        ComChainErrorV1::Pdf
    }
}
impl From<ComMetricsErrorV1> for ComChainErrorV1 {
    fn from(_: ComMetricsErrorV1) -> Self {
        ComChainErrorV1::Metrics
    }
}

use crate::com_metrics_v1::ComMetricsErrorV1;

/// Caller-supplied chain controls. Every scalar is validated finite and
/// in-range at construction; nothing is defaulted or guessed.
#[derive(Clone, Debug, PartialEq)]
pub struct ComChainControlsV1 {
    samples_per_ui: usize,
    levels: u32,
    bin_size: f64,
    dfe_first_max: f64,
    cdr: String,
    peak_start: usize,
    peak_stop: Option<usize>,
    dfe_tap_count: i64,
    dfe_max: Vec<f64>,
    dfe_min: Vec<f64>,
    dfe_step: f64,
    floating_dfe: bool,
    dfe_max_count: Option<i64>,
    available_signal_v: f64,
    r_lm_ohm: f64,
    tx_snr_db: f64,
    sigma_x: f64,
    sigma_rj_s: f64,
    jitter_response: Vec<f64>,
    sigma_n_v: f64,
    amplitude_dd_v: f64,
    spec_ber: f64,
    noise_crest_factor: f64,
    sigma_ne_v: f64,
    bbn_q_factor: Option<f64>,
    sigma_tx_override_v: Option<f64>,
    sigma_rj_override_v: Option<f64>,
    pass_threshold_db: f64,
    t_o_s: f64,
    eye_opening_v: Option<f64>,
}

/// Typed winner state passed from the search loop into the final PDF chain.
/// This is an internal numerical handoff, not a public request control.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct ComWinnerContextV1 {
    pub(crate) cursor_index: usize,
    pub(crate) dfe_taps: Vec<f64>,
    pub(crate) dfe_max: Vec<f64>,
    pub(crate) dfe_min: Vec<f64>,
    pub(crate) dfe_step: f64,
    pub(crate) floating_dfe: bool,
    pub(crate) dfe_max_count: Option<i64>,
    pub(crate) sigma_n_v: f64,
}

impl ComChainControlsV1 {
    fn with_winner(mut self, winner: &ComWinnerContextV1) -> Result<Self, ComChainErrorV1> {
        if winner.dfe_taps.len() != winner.dfe_max.len()
            || winner.dfe_taps.len() != winner.dfe_min.len()
            || winner
                .dfe_taps
                .iter()
                .chain(winner.dfe_max.iter())
                .chain(winner.dfe_min.iter())
                .any(|value| !value.is_finite())
            || !winner.dfe_step.is_finite()
            || winner.dfe_step < 0.0
            || !winner.sigma_n_v.is_finite()
            || winner.sigma_n_v < 0.0
            || winner.dfe_max_count.is_some_and(|count| count < 0)
            || winner
                .dfe_max_count
                .is_some_and(|count| count as usize != winner.dfe_max.len())
        {
            return Err(ComChainErrorV1::InvalidControls);
        }
        self.dfe_tap_count = winner.dfe_taps.len() as i64;
        self.dfe_max = winner.dfe_max.clone();
        self.dfe_min = winner.dfe_min.clone();
        self.dfe_step = winner.dfe_step;
        self.floating_dfe = winner.floating_dfe;
        self.dfe_max_count = winner.dfe_max_count;
        self.sigma_n_v = winner.sigma_n_v;
        Ok(self)
    }

    #[allow(clippy::too_many_arguments)]
    pub fn try_new(
        samples_per_ui: usize,
        levels: u32,
        bin_size: f64,
        dfe_first_max: f64,
        cdr: impl Into<String>,
        peak_start: usize,
        peak_stop: Option<usize>,
        dfe_tap_count: i64,
        dfe_max: Vec<f64>,
        dfe_min: Vec<f64>,
        dfe_step: f64,
        floating_dfe: bool,
        dfe_max_count: Option<i64>,
        available_signal_v: f64,
        r_lm_ohm: f64,
        tx_snr_db: f64,
        sigma_x: f64,
        sigma_rj_s: f64,
        jitter_response: Vec<f64>,
        sigma_n_v: f64,
        amplitude_dd_v: f64,
        spec_ber: f64,
        noise_crest_factor: f64,
        sigma_ne_v: f64,
        bbn_q_factor: Option<f64>,
        sigma_tx_override_v: Option<f64>,
        sigma_rj_override_v: Option<f64>,
        pass_threshold_db: f64,
        t_o_s: f64,
        eye_opening_v: Option<f64>,
    ) -> Result<Self, ComChainErrorV1> {
        let cdr = cdr.into();
        let finite = |value: f64| value.is_finite();
        let option_finite = |value: Option<f64>| value.is_none_or(finite);
        if samples_per_ui < 1
            || levels < 2
            || !(bin_size > 0.0 && finite(bin_size))
            || !(dfe_first_max >= 0.0 && finite(dfe_first_max))
            || cdr.is_empty()
            || !(dfe_step >= 0.0 && finite(dfe_step))
            || !(dfe_tap_count >= 0)
            || dfe_max_count.is_some_and(|count| count < 0)
            || !(available_signal_v > 0.0 && finite(available_signal_v))
            || !(r_lm_ohm > 0.0 && finite(r_lm_ohm))
            || !(tx_snr_db >= 0.0 && finite(tx_snr_db))
            || !(sigma_x >= 0.0 && finite(sigma_x))
            || !(sigma_rj_s >= 0.0 && finite(sigma_rj_s))
            || jitter_response.is_empty()
            || jitter_response.iter().any(|value| !finite(*value))
            || !(sigma_n_v >= 0.0 && finite(sigma_n_v))
            || !(amplitude_dd_v >= 0.0 && finite(amplitude_dd_v))
            || !(0.0 < spec_ber && spec_ber < 1.0 && finite(spec_ber))
            || !(noise_crest_factor >= 0.0 && finite(noise_crest_factor))
            || !(sigma_ne_v >= 0.0 && finite(sigma_ne_v))
            || !option_finite(bbn_q_factor)
            || !option_finite(sigma_tx_override_v)
            || !option_finite(sigma_rj_override_v)
            || !finite(pass_threshold_db)
            || !(t_o_s >= 0.0 && finite(t_o_s))
            || !option_finite(eye_opening_v)
        {
            return Err(ComChainErrorV1::InvalidControls);
        }
        Ok(Self {
            samples_per_ui,
            levels,
            bin_size,
            dfe_first_max,
            cdr,
            peak_start,
            peak_stop,
            dfe_tap_count,
            dfe_max,
            dfe_min,
            dfe_step,
            floating_dfe,
            dfe_max_count,
            available_signal_v,
            r_lm_ohm,
            tx_snr_db,
            sigma_x,
            sigma_rj_s,
            jitter_response,
            sigma_n_v,
            amplitude_dd_v,
            spec_ber,
            noise_crest_factor,
            sigma_ne_v,
            bbn_q_factor,
            sigma_tx_override_v,
            sigma_rj_override_v,
            pass_threshold_db,
            t_o_s,
            eye_opening_v,
        })
    }
}

/// The composed chain report: every stage checkpoint is exposed.
#[derive(Clone, Debug, PartialEq)]
pub struct ComChainReportV1 {
    cursor: CursorSampleV1,
    residual: ResidualPdfResultV1,
    fext: Vec<ResidualPdfResultV1>,
    next: Vec<ResidualPdfResultV1>,
    noise: R480NoisePdfV1,
    combined: CombinedNoisePdfV1,
    metrics: ComMetricsV1,
}

impl ComChainReportV1 {
    pub fn cursor(&self) -> &CursorSampleV1 {
        &self.cursor
    }
    pub fn residual(&self) -> &ResidualPdfResultV1 {
        &self.residual
    }
    pub fn fext(&self) -> &[ResidualPdfResultV1] {
        &self.fext
    }
    pub fn next(&self) -> &[ResidualPdfResultV1] {
        &self.next
    }
    pub fn noise(&self) -> &R480NoisePdfV1 {
        &self.noise
    }
    pub fn combined(&self) -> &CombinedNoisePdfV1 {
        &self.combined
    }
    pub fn metrics(&self) -> &ComMetricsV1 {
        &self.metrics
    }
}

/// Run the fixed-tap chain without crosstalk channels.
pub fn run_com_chain_v1(
    pulse_response: &[f64],
    controls: &ComChainControlsV1,
) -> Result<ComChainReportV1, ComChainErrorV1> {
    run_com_chain_with_crosstalk_v1(pulse_response, &[], &[], controls)
}

/// Run the fixed-tap chain with portable FEXT/NEXT pulse inputs.
///
/// The upstream non-MMSE path constructs a residual PDF for each crosstalk
/// channel, selects its worst phase, and convolves those PDFs into the
/// combined noise distribution. The caller supplies already-resolved
/// impulse/pulse responses; channel fitting and top-level search remain
/// outside this stage.
pub fn run_com_chain_with_crosstalk_v1(
    pulse_response: &[f64],
    fext_pulses: &[&[f64]],
    next_pulses: &[&[f64]],
    controls: &ComChainControlsV1,
) -> Result<ComChainReportV1, ComChainErrorV1> {
    run_com_chain_with_crosstalk_cursor_v1(pulse_response, fext_pulses, next_pulses, controls, None)
}

/// Execute the final chain from the already validated search winner.
pub(crate) fn run_com_chain_with_winner_v1(
    pulse_response: &[f64],
    fext_pulses: &[&[f64]],
    next_pulses: &[&[f64]],
    controls: &ComChainControlsV1,
    winner: &ComWinnerContextV1,
) -> Result<ComChainReportV1, ComChainErrorV1> {
    if winner.cursor_index < controls.samples_per_ui
        || winner.cursor_index >= pulse_response.len()
        || !pulse_response[winner.cursor_index].is_finite()
        || pulse_response[winner.cursor_index] <= 0.0
    {
        return Err(ComChainErrorV1::Equalizer);
    }
    let resolved = controls.clone().with_winner(winner)?;
    run_com_chain_with_crosstalk_cursor_v1(
        pulse_response,
        fext_pulses,
        next_pulses,
        &resolved,
        Some(winner.cursor_index),
    )
}

fn run_com_chain_with_crosstalk_cursor_v1(
    pulse_response: &[f64],
    fext_pulses: &[&[f64]],
    next_pulses: &[&[f64]],
    controls: &ComChainControlsV1,
    forced_cursor_index: Option<usize>,
) -> Result<ComChainReportV1, ComChainErrorV1> {
    if pulse_response.is_empty() {
        return Err(ComChainErrorV1::EmptyPulse);
    }
    if pulse_response.iter().any(|value| !value.is_finite()) {
        return Err(ComChainErrorV1::NonFinite);
    }
    for pulse in fext_pulses.iter().chain(next_pulses.iter()) {
        if pulse.is_empty() {
            return Err(ComChainErrorV1::EmptyPulse);
        }
        if pulse.iter().any(|value| !value.is_finite()) {
            return Err(ComChainErrorV1::NonFinite);
        }
    }
    let cursor = if let Some(index) = forced_cursor_index {
        if index >= pulse_response.len() {
            return Err(ComChainErrorV1::Equalizer);
        }
        CursorSampleV1::with_cursor(index, index as i64, None)
    } else {
        cursor_sample_index_v1(
            pulse_response,
            controls.samples_per_ui,
            controls.dfe_first_max,
            &controls.cdr,
            controls.peak_start,
            controls.peak_stop,
        )?
    };
    let cursor_index = cursor.cursor_index().ok_or(ComChainErrorV1::Equalizer)? as usize;
    let residual = residual_channel_pdf_v1(
        pulse_response,
        "THRU",
        cursor_index,
        controls.samples_per_ui,
        controls.levels,
        controls.bin_size,
        controls.dfe_tap_count,
        Some(&controls.dfe_max),
        Some(&controls.dfe_min),
        controls.dfe_step,
        controls.floating_dfe,
        controls.dfe_max_count,
        None,
    )?;
    let fext = fext_pulses
        .iter()
        .map(|pulse| {
            residual_channel_pdf_v1(
                pulse,
                "FEXT",
                0,
                controls.samples_per_ui,
                controls.levels,
                controls.bin_size,
                0,
                None,
                None,
                0.0,
                false,
                None,
                None,
            )
        })
        .collect::<Result<Vec<_>, _>>()?;
    let next = next_pulses
        .iter()
        .map(|pulse| {
            residual_channel_pdf_v1(
                pulse,
                "NEXT",
                0,
                controls.samples_per_ui,
                controls.levels,
                controls.bin_size,
                0,
                None,
                None,
                0.0,
                false,
                None,
                None,
            )
        })
        .collect::<Result<Vec<_>, _>>()?;
    let fext_pdfs = fext
        .iter()
        .map(|result| result.pdf().clone())
        .collect::<Vec<_>>();
    let next_pdfs = next
        .iter()
        .map(|result| result.pdf().clone())
        .collect::<Vec<_>>();
    let noise = build_r480_noise_pdf_v1(
        residual.pdf(),
        &fext_pdfs,
        &next_pdfs,
        controls.levels,
        controls.available_signal_v,
        controls.r_lm_ohm,
        controls.tx_snr_db,
        controls.sigma_x,
        controls.sigma_rj_s,
        &controls.jitter_response,
        controls.sigma_n_v,
        controls.amplitude_dd_v,
        controls.spec_ber,
        controls.noise_crest_factor,
        controls.sigma_ne_v,
        controls.bbn_q_factor,
        controls.sigma_tx_override_v,
        controls.sigma_rj_override_v,
    )?;
    let combined = combine_r480_noise_pdf_v1(
        residual.pdf(),
        &fext_pdfs,
        &next_pdfs,
        noise.gaussian_pdf(),
        noise.jitter_pdf(),
        controls.spec_ber,
    )?;
    let support: Vec<f64> = (0..combined.combined().probability().len())
        .map(|index| combined.combined().x(index))
        .collect();
    let cdf = combined.combined().cdf();
    let metrics = calculate_com_metrics_v1(
        controls.available_signal_v,
        &support,
        &cdf,
        controls.spec_ber,
        controls.pass_threshold_db,
        controls.t_o_s,
        controls.eye_opening_v,
    )?;
    Ok(ComChainReportV1 {
        cursor,
        residual,
        fext,
        next,
        noise,
        combined,
        metrics,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pulse64() -> Vec<f64> {
        // Bipolar pulse with a rising zero crossing near index 26 (MM CDR).
        (0..64)
            .map(|index| {
                let i = index as f64;
                0.5 * (-(i - 28.0) * (i - 28.0) / 80.0).exp() * (i - 28.0) * 0.4
                    + 0.002 * (i * 0.9).sin()
            })
            .collect()
    }

    fn controls() -> ComChainControlsV1 {
        ComChainControlsV1::try_new(
            8,
            4,
            0.01,
            0.0,
            "MM",
            16,
            Some(44),
            0,
            Vec::new(),
            Vec::new(),
            0.0,
            false,
            None,
            0.5,
            50.0,
            30.0,
            0.03,
            1e-4,
            vec![0.3, 0.5, 0.2],
            0.01,
            0.4,
            1e-4,
            0.0,
            0.0,
            None,
            None,
            None,
            3.0,
            0.0,
            None,
        )
        .expect("controls")
    }

    #[test]
    fn policy_fixed() {
        assert_eq!(
            COM_CHAIN_POLICY_V1,
            "sipi.p5-06f.com-chain-v1.fixed-tap-cursor-residual-noise-metrics"
        );
    }

    #[test]
    fn chain_runs_on_synthetic_pulse() {
        let report = run_com_chain_v1(&pulse64(), &controls()).expect("chain");
        let cursor = report.cursor();
        assert!(cursor.cursor_index().is_some());
        assert!(cursor.cursor_index().expect("cursor") < 64);
        assert!((0..8).contains(&report.residual().selected_phase()));
        let total: f64 = report.residual().pdf().probability().iter().sum();
        assert!((total - 1.0).abs() < 1e-9);
        let combined_total: f64 = report.combined().combined().probability().iter().sum();
        assert!((combined_total - 1.0).abs() < 1e-9);
        let metrics = report.metrics();
        assert!(metrics.com_db().is_finite());
        assert!(metrics.vec_db().is_finite());
        assert!(metrics.veo_mv().is_finite());
        assert!(report.noise().sigma_gaussian_v() > 0.0);
        assert!(report.noise().ber_q() > 3.0 && report.noise().ber_q() < 4.0);
    }

    #[test]
    fn crosstalk_pulses_are_integrated_into_semantic_metrics() {
        let thru = pulse64();
        let fext = thru.iter().map(|value| value * 0.25).collect::<Vec<_>>();
        let next = thru.iter().map(|value| value * 0.15).collect::<Vec<_>>();
        let baseline = run_com_chain_v1(&thru, &controls()).expect("baseline");
        let with_crosstalk = run_com_chain_with_crosstalk_v1(
            &thru,
            &[fext.as_slice()],
            &[next.as_slice()],
            &controls(),
        )
        .expect("crosstalk chain");
        assert_eq!(with_crosstalk.fext().len(), 1);
        assert_eq!(with_crosstalk.next().len(), 1);
        assert!(
            with_crosstalk.metrics().com_db() != baseline.metrics().com_db()
                || with_crosstalk.metrics().vec_db() != baseline.metrics().vec_db()
        );
    }

    #[test]
    fn winner_context_bypasses_cursor_recalculation_and_validates_dfe_state() {
        let winner = ComWinnerContextV1 {
            cursor_index: 30,
            dfe_taps: vec![0.1, -0.02],
            dfe_max: vec![0.4, 0.3],
            dfe_min: vec![-0.2, -0.1],
            dfe_step: 0.01,
            floating_dfe: true,
            dfe_max_count: Some(2),
            sigma_n_v: 0.01,
        };
        let report = run_com_chain_with_winner_v1(&pulse64(), &[], &[], &controls(), &winner)
            .expect("winner chain");
        assert_eq!(report.cursor().cursor_index(), Some(30));
        let invalid = ComWinnerContextV1 {
            dfe_min: vec![-0.2],
            ..winner.clone()
        };
        assert_eq!(
            run_com_chain_with_winner_v1(&pulse64(), &[], &[], &controls(), &invalid),
            Err(ComChainErrorV1::InvalidControls)
        );
        let zero_cursor = ComWinnerContextV1 {
            cursor_index: 0,
            ..winner.clone()
        };
        assert_eq!(
            run_com_chain_with_winner_v1(&pulse64(), &[], &[], &controls(), &zero_cursor),
            Err(ComChainErrorV1::Equalizer)
        );
        let before_window = ComWinnerContextV1 {
            cursor_index: 7,
            ..winner.clone()
        };
        assert_eq!(
            run_com_chain_with_winner_v1(&pulse64(), &[], &[], &controls(), &before_window),
            Err(ComChainErrorV1::Equalizer)
        );
        let mut nonpositive_pulse = pulse64();
        nonpositive_pulse[30] = 0.0;
        assert_eq!(
            run_com_chain_with_winner_v1(&nonpositive_pulse, &[], &[], &controls(), &winner,),
            Err(ComChainErrorV1::Equalizer)
        );
    }

    #[test]
    fn empty_and_nonfinite_pulse_rejected() {
        assert_eq!(
            run_com_chain_v1(&[], &controls()),
            Err(ComChainErrorV1::EmptyPulse)
        );
        let mut bad = pulse64();
        bad[3] = f64::NAN;
        assert_eq!(
            run_com_chain_v1(&bad, &controls()),
            Err(ComChainErrorV1::NonFinite)
        );
    }

    #[test]
    fn invalid_controls_rejected() {
        let cases: Vec<ComChainErrorV1> = vec![
            ComChainControlsV1::try_new(
                0,
                4,
                0.01,
                0.0,
                "peak",
                20,
                Some(40),
                0,
                Vec::new(),
                Vec::new(),
                0.0,
                false,
                None,
                0.5,
                50.0,
                30.0,
                0.03,
                1e-4,
                vec![0.3],
                0.01,
                0.4,
                1e-4,
                0.0,
                0.0,
                None,
                None,
                None,
                3.0,
                0.0,
                None,
            )
            .expect_err("spu"),
            ComChainControlsV1::try_new(
                8,
                1,
                0.01,
                0.0,
                "peak",
                20,
                Some(40),
                0,
                Vec::new(),
                Vec::new(),
                0.0,
                false,
                None,
                0.5,
                50.0,
                30.0,
                0.03,
                1e-4,
                vec![0.3],
                0.01,
                0.4,
                1e-4,
                0.0,
                0.0,
                None,
                None,
                None,
                3.0,
                0.0,
                None,
            )
            .expect_err("levels"),
            ComChainControlsV1::try_new(
                8,
                4,
                0.0,
                0.0,
                "peak",
                20,
                Some(40),
                0,
                Vec::new(),
                Vec::new(),
                0.0,
                false,
                None,
                0.5,
                50.0,
                30.0,
                0.03,
                1e-4,
                vec![0.3],
                0.01,
                0.4,
                1e-4,
                0.0,
                0.0,
                None,
                None,
                None,
                3.0,
                0.0,
                None,
            )
            .expect_err("bin"),
            ComChainControlsV1::try_new(
                8,
                4,
                0.01,
                0.0,
                "peak",
                20,
                Some(40),
                0,
                Vec::new(),
                Vec::new(),
                0.0,
                false,
                None,
                0.5,
                50.0,
                30.0,
                0.03,
                1e-4,
                vec![],
                0.01,
                0.4,
                1e-4,
                0.0,
                0.0,
                None,
                None,
                None,
                3.0,
                0.0,
                None,
            )
            .expect_err("jitter"),
            ComChainControlsV1::try_new(
                8,
                4,
                0.01,
                0.0,
                "peak",
                20,
                Some(40),
                0,
                Vec::new(),
                Vec::new(),
                0.0,
                false,
                None,
                0.5,
                50.0,
                30.0,
                0.03,
                1e-4,
                vec![0.3],
                0.01,
                0.4,
                1.5,
                0.0,
                0.0,
                None,
                None,
                None,
                3.0,
                0.0,
                None,
            )
            .expect_err("spec_ber"),
        ];
        assert_eq!(cases.len(), 5);
        for case in cases {
            let _ = case;
        }
    }
}
