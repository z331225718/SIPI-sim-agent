//! Residual-channel discrete PDF stage (port of `residual_channel_pdf`).
//!
//! Ported from agent-com `src/agent_com/noise/discrete_pdf.py` (MIT
//! source, P5-04g source map). Constructs the residual pulse (DFE
//! cancellation for THRU), selects the sampling phase (THRU single
//! phase from the cursor; FEXT/NEXT largest-PDF-RMS over all phases),
//! and builds the sampled-signal PDF on the phase samples. Indices are
//! zero-based; `phase_index` is only used for an MMSE-provided
//! crosstalk phase.

use crate::discrete_pdf_v1::{DiscretePdfV1, PdfErrorV1, matlab_round};
use crate::sampled_signal_pdf_v1::sampled_signal_pdf_v1;

/// Explicit scope policy of the residual-channel PDF stage.
pub const RESIDUAL_CHANNEL_PDF_POLICY_V1: &str =
    "sipi.p5-04g.residual-channel-pdf-v1.dfe-cancel-phase-select";

/// The residual PDF result surface (port of `ResidualPdfResult`).
#[derive(Clone, Debug, PartialEq)]
pub struct ResidualPdfResultV1 {
    pdf: DiscretePdfV1,
    residual_pulse: Vec<f64>,
    selected_phase: i64,
}

impl ResidualPdfResultV1 {
    pub fn pdf(&self) -> &DiscretePdfV1 {
        &self.pdf
    }

    pub fn residual_pulse(&self) -> &[f64] {
        &self.residual_pulse
    }

    pub fn selected_phase(&self) -> i64 {
        self.selected_phase
    }
}

/// Port of `_dfe_bounds`: slice validation of the DFE bound arrays.
fn dfe_bounds_v1(
    maximum: Option<&[f64]>,
    minimum: Option<&[f64]>,
    count: usize,
) -> Result<(Vec<f64>, Vec<f64>), PdfErrorV1> {
    if count == 0 {
        return Ok((Vec::new(), Vec::new()));
    }
    let (Some(maximum), Some(minimum)) = (maximum, minimum) else {
        return Err(PdfErrorV1::InvalidDfeBounds);
    };
    let upper = maximum.to_vec();
    let lower = minimum.to_vec();
    if upper.len() < count || lower.len() < count {
        return Err(PdfErrorV1::InvalidDfeBounds);
    }
    if lower[..count]
        .iter()
        .zip(upper[..count].iter())
        .any(|(low, high)| low > high)
    {
        return Err(PdfErrorV1::InvalidDfeBounds);
    }
    Ok((upper[..count].to_vec(), lower[..count].to_vec()))
}

/// RMS of the PDF support points weighted by probability (port of
/// `np.sqrt(np.sum(x**2 * probability))`).
fn pdf_rms_v1(pdf: &DiscretePdfV1) -> f64 {
    let mut sum = 0.0;
    for index in 0..pdf.probability().len() {
        let x = pdf.x(index);
        sum += x * x * pdf.probability()[index];
    }
    sum.sqrt()
}

/// Port of `residual_channel_pdf` (non-MMSE path).
///
/// `dfe_tap_count` and `dfe_max_count` are signed to preserve the
/// source's negative-count rejection. IEEE f64 division semantics
/// (cursor * dfe_step == 0) follow the source's NumPy behavior.
pub fn residual_channel_pdf_v1(
    pulse_response: &[f64],
    channel_type: &str,
    cursor_index: usize,
    samples_per_ui: usize,
    levels: u32,
    bin_size: f64,
    dfe_tap_count: i64,
    dfe_max: Option<&[f64]>,
    dfe_min: Option<&[f64]>,
    dfe_step: f64,
    floating_dfe: bool,
    dfe_max_count: Option<i64>,
    phase_index: Option<i64>,
) -> Result<ResidualPdfResultV1, PdfErrorV1> {
    let kind = channel_type.to_uppercase();
    let valid_kind = kind == "THRU" || kind == "FEXT" || kind == "NEXT";
    if !valid_kind || samples_per_ui < 1 || levels < 2 || !(bin_size > 0.0) {
        return Err(PdfErrorV1::InvalidResidualControls);
    }
    if dfe_step < 0.0 || (kind == "THRU" && cursor_index >= pulse_response.len()) {
        return Err(PdfErrorV1::InvalidResidualControls);
    }
    let mut residual = pulse_response.to_vec();
    if kind == "THRU" {
        let cancellation_count = if floating_dfe {
            dfe_max_count
        } else {
            Some(dfe_tap_count)
        };
        let Some(cancellation_count) = cancellation_count else {
            return Err(PdfErrorV1::InvalidDfeCancellationCount);
        };
        if cancellation_count < 0 {
            return Err(PdfErrorV1::InvalidDfeCancellationCount);
        }
        let count = cancellation_count as usize;
        if cursor_index + count * samples_per_ui >= residual.len() {
            return Err(PdfErrorV1::DfeSpanExceedsPulse);
        }
        let (maximum, minimum) = dfe_bounds_v1(dfe_max, dfe_min, count)?;
        let cursor = residual[cursor_index];
        let mut cancellation: Vec<f64> = (0..=count)
            .map(|index| residual[cursor_index + index * samples_per_ui])
            .collect();
        if dfe_step != 0.0 {
            for value in cancellation.iter_mut() {
                let scaled = *value / (cursor * dfe_step);
                let sign = if *value > 0.0 {
                    1.0
                } else if *value < 0.0 {
                    -1.0
                } else {
                    0.0
                };
                *value = scaled.abs().floor() * cursor * dfe_step * sign;
            }
        }
        let mut upper = vec![cursor];
        upper.extend_from_slice(&maximum);
        let mut lower = vec![cursor];
        lower.extend_from_slice(&minimum);
        for (value, (high, low)) in cancellation.iter_mut().zip(upper.iter().zip(lower.iter())) {
            *value = (*high).min((*low).max(*value));
        }
        let start = cursor_index as i64 - (samples_per_ui / 2) as i64;
        let stop = start + (cancellation.len() * samples_per_ui) as i64;
        if start < 0 || stop > residual.len() as i64 {
            return Err(PdfErrorV1::DfeWindowExceedsPulse);
        }
        for (offset, value) in cancellation.iter().enumerate() {
            for sample in 0..samples_per_ui {
                residual[(start as usize) + offset * samples_per_ui + sample] -= value;
            }
        }
    }
    let nui = matlab_round(residual.len() as f64 / samples_per_ui as f64);
    if nui < 3 || (nui - 2) * samples_per_ui as i64 + samples_per_ui as i64 > residual.len() as i64
    {
        return Err(PdfErrorV1::PulseTooShort);
    }
    let phases: Vec<i64> = if kind == "THRU" {
        let phase = ((cursor_index + 1) % samples_per_ui) as i64;
        vec![if phase == 0 {
            samples_per_ui as i64 - 1
        } else {
            phase - 1
        }]
    } else {
        (0..samples_per_ui as i64).collect()
    };
    let mut samples_by_phase: Vec<Vec<f64>> = Vec::with_capacity(phases.len());
    for phase in &phases {
        let start = samples_per_ui + *phase as usize;
        let stop = start + (nui - 2) as usize * samples_per_ui;
        let mut values = Vec::with_capacity((nui - 2) as usize);
        let mut index = start;
        while index < stop {
            values.push(residual[index]);
            index += samples_per_ui;
        }
        samples_by_phase.push(values);
    }
    let selected_phase: i64;
    let pdf: DiscretePdfV1;
    if let Some(requested) = phase_index {
        let Some(position) = phases.iter().position(|phase| *phase == requested) else {
            return Err(PdfErrorV1::PhaseOutsideCandidates);
        };
        pdf = sampled_signal_pdf_v1(&samples_by_phase[position], levels, bin_size, false)?;
        selected_phase = requested;
    } else {
        let mut candidates = Vec::with_capacity(phases.len());
        let mut rms_values = Vec::with_capacity(phases.len());
        for values in &samples_by_phase {
            let candidate = sampled_signal_pdf_v1(values, levels, bin_size, false)?;
            rms_values.push(pdf_rms_v1(&candidate));
            candidates.push(candidate);
        }
        let mut selected = 0usize;
        for index in 1..rms_values.len() {
            if rms_values[index] > rms_values[selected] {
                selected = index;
            }
        }
        selected_phase = phases[selected];
        pdf = candidates
            .into_iter()
            .nth(selected)
            .expect("selected phase");
    }
    Ok(ResidualPdfResultV1 {
        pdf,
        residual_pulse: residual,
        selected_phase,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pulse64() -> Vec<f64> {
        (0..64)
            .map(|index| {
                let i = index as f64;
                0.5 * (-(i - 30.0) * (i - 30.0) / 60.0).exp() * (1.0 + 0.1 * (i * 0.7).sin())
            })
            .collect()
    }

    #[test]
    fn thru_no_dfe_selects_cursor_phase_and_cancels() {
        let pulse = pulse64();
        let result = residual_channel_pdf_v1(
            &pulse, "THRU", 30, 8, 4, 0.01, 0, None, None, 0.0, false, None, None,
        )
        .expect("result");
        // Phase = ((30+1) % 8 or 8) - 1 = 7 - 1 = 6.
        assert_eq!(result.selected_phase(), 6);
        // Window [26, 34) has the cursor value subtracted once per sample.
        let cursor = pulse[30];
        for index in 26..34 {
            assert!((result.residual_pulse()[index] - (pulse[index] - cursor)).abs() < 1e-12);
        }
        assert!(!result.pdf().probability().is_empty());
        let total: f64 = result.pdf().probability().iter().sum();
        assert!((total - 1.0).abs() < 1e-12);
    }

    #[test]
    fn thru_dfe_quantize_and_clamp() {
        let pulse = pulse64();
        let result = residual_channel_pdf_v1(
            &pulse,
            "THRU",
            30,
            8,
            4,
            0.01,
            2,
            Some(&[0.4, 0.3]),
            Some(&[-0.2, -0.1]),
            0.01,
            false,
            None,
            None,
        )
        .expect("result");
        assert_eq!(result.selected_phase(), 6);
        assert!(!result.residual_pulse().is_empty());
    }

    #[test]
    fn fext_phase_selection_is_deterministic() {
        let pulse = pulse64();
        let result = residual_channel_pdf_v1(
            &pulse, "FEXT", 0, 8, 4, 0.01, 0, None, None, 0.0, false, None, None,
        )
        .expect("result");
        assert!((0..8).contains(&result.selected_phase()));
        // Same input, same selection (first-maximum RMS semantics).
        let again = residual_channel_pdf_v1(
            &pulse, "FEXT", 0, 8, 4, 0.01, 0, None, None, 0.0, false, None, None,
        )
        .expect("result");
        assert_eq!(result.selected_phase(), again.selected_phase());
    }

    #[test]
    fn forced_phase_index_is_honored() {
        let pulse = pulse64();
        let result = residual_channel_pdf_v1(
            &pulse,
            "FEXT",
            0,
            8,
            4,
            0.01,
            0,
            None,
            None,
            0.0,
            false,
            None,
            Some(3),
        )
        .expect("result");
        assert_eq!(result.selected_phase(), 3);
    }

    #[test]
    fn floating_dfe_uses_max_count() {
        let pulse = pulse64();
        let result = residual_channel_pdf_v1(
            &pulse,
            "THRU",
            30,
            8,
            4,
            0.01,
            5,
            Some(&[0.4]),
            Some(&[-0.2]),
            0.0,
            true,
            Some(1),
            None,
        )
        .expect("result");
        assert_eq!(result.selected_phase(), 6);
    }

    #[test]
    fn controls_and_errors_fail_closed() {
        let pulse = pulse64();
        assert_eq!(
            residual_channel_pdf_v1(
                &pulse, "XTLK", 30, 8, 4, 0.01, 0, None, None, 0.0, false, None, None
            )
            .unwrap_err(),
            PdfErrorV1::InvalidResidualControls,
        );
        assert_eq!(
            residual_channel_pdf_v1(
                &pulse, "THRU", 30, 0, 4, 0.01, 0, None, None, 0.0, false, None, None
            )
            .unwrap_err(),
            PdfErrorV1::InvalidResidualControls,
        );
        assert_eq!(
            residual_channel_pdf_v1(
                &pulse, "THRU", 30, 8, 1, 0.01, 0, None, None, 0.0, false, None, None
            )
            .unwrap_err(),
            PdfErrorV1::InvalidResidualControls,
        );
        assert_eq!(
            residual_channel_pdf_v1(
                &pulse, "THRU", 30, 8, 4, 0.0, 0, None, None, 0.0, false, None, None
            )
            .unwrap_err(),
            PdfErrorV1::InvalidResidualControls,
        );
        assert_eq!(
            residual_channel_pdf_v1(
                &pulse, "THRU", 30, 8, 4, 0.01, 0, None, None, -0.1, false, None, None
            )
            .unwrap_err(),
            PdfErrorV1::InvalidResidualControls,
        );
        assert_eq!(
            residual_channel_pdf_v1(
                &pulse, "THRU", 64, 8, 4, 0.01, 0, None, None, 0.0, false, None, None
            )
            .unwrap_err(),
            PdfErrorV1::InvalidResidualControls,
        );
        assert_eq!(
            residual_channel_pdf_v1(
                &pulse, "THRU", 30, 8, 4, 0.01, -1, None, None, 0.0, false, None, None
            )
            .unwrap_err(),
            PdfErrorV1::InvalidDfeCancellationCount,
        );
        assert_eq!(
            residual_channel_pdf_v1(
                &pulse, "THRU", 30, 8, 4, 0.01, 0, None, None, 0.0, false, None, None
            )
            .ok()
            .map(|_| ()),
            Some(()),
        );
        // DFE bounds required when count > 0.
        assert_eq!(
            residual_channel_pdf_v1(
                &pulse, "THRU", 30, 8, 4, 0.01, 2, None, None, 0.0, false, None, None
            )
            .unwrap_err(),
            PdfErrorV1::InvalidDfeBounds,
        );
        // Span exceeds pulse.
        assert_eq!(
            residual_channel_pdf_v1(
                &pulse,
                "THRU",
                30,
                8,
                4,
                0.01,
                10,
                Some(&[0.1; 10]),
                Some(&[-0.1; 10]),
                0.0,
                false,
                None,
                None
            )
            .unwrap_err(),
            PdfErrorV1::DfeSpanExceedsPulse,
        );
        // Cursor window exceeds pulse at the left edge.
        assert_eq!(
            residual_channel_pdf_v1(
                &pulse,
                "THRU",
                1,
                8,
                4,
                0.01,
                2,
                Some(&[0.1, 0.1]),
                Some(&[-0.1, -0.1]),
                0.0,
                false,
                None,
                None
            )
            .unwrap_err(),
            PdfErrorV1::DfeWindowExceedsPulse,
        );
        // Pulse too short for whole-UI support (window passes, nui = 1 < 3).
        let short = vec![0.1; 9];
        assert_eq!(
            residual_channel_pdf_v1(
                &short, "THRU", 5, 8, 4, 0.01, 0, None, None, 0.0, false, None, None
            )
            .unwrap_err(),
            PdfErrorV1::PulseTooShort,
        );
        // Phase outside candidates.
        assert_eq!(
            residual_channel_pdf_v1(
                &pulse,
                "FEXT",
                0,
                8,
                4,
                0.01,
                0,
                None,
                None,
                0.0,
                false,
                None,
                Some(8)
            )
            .unwrap_err(),
            PdfErrorV1::PhaseOutsideCandidates,
        );
    }

    #[test]
    fn policy_string_is_fixed() {
        assert_eq!(
            RESIDUAL_CHANNEL_PDF_POLICY_V1,
            "sipi.p5-04g.residual-channel-pdf-v1.dfe-cancel-phase-select",
        );
    }
}
