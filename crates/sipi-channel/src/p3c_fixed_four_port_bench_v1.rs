//! Fixed four-port static reduction for the P3C PRBS9 candidate bench.
//!
//! This module owns only the matched, four-port frequency-domain reduction
//! observed in the P3C ADS reference bench. It deliberately does not create
//! an impulse response, interpolate frequency samples, or simulate a
//! waveform. Those time-domain policies remain unimplemented.

use std::{error::Error, fmt};

use sipi_types::{Complex64, Hertz, Ohms};

pub const SELECTED_P3C_PORT_COUNT: usize = 4;

/// One four-port S-parameter matrix, indexed as `[output][incident]`.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct FourPortS {
    values: [[Complex64; SELECTED_P3C_PORT_COUNT]; SELECTED_P3C_PORT_COUNT],
}

impl FourPortS {
    pub const fn new(
        values: [[Complex64; SELECTED_P3C_PORT_COUNT]; SELECTED_P3C_PORT_COUNT],
    ) -> Self {
        Self { values }
    }

    pub fn at(self, output_port: usize, incident_port: usize) -> Option<Complex64> {
        self.values
            .get(output_port)
            .and_then(|row| row.get(incident_port))
            .copied()
    }
}

/// The only supported port order: 1=TX+, 2=RX+, 3=TX-, 4=RX-.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum SelectedP3cPortMapV1 {
    TxPlusRxPlusTxMinusRxMinus,
}

/// A finite four-port frequency sample set admitted for static P3C bench
/// reduction. It does not imply causality, passivity, or transient readiness.
#[derive(Clone, Debug, PartialEq)]
pub struct SelectedP3cFourPortSpectrumV1 {
    reference_impedance: Ohms,
    frequencies: Box<[Hertz]>,
    samples: Box<[FourPortS]>,
}

impl SelectedP3cFourPortSpectrumV1 {
    pub fn try_new(
        reference_impedance: Ohms,
        frequencies: Vec<Hertz>,
        samples: Vec<FourPortS>,
    ) -> Result<Self, FixedFourPortBenchError> {
        if reference_impedance.get().to_bits() != 50.0_f64.to_bits() {
            return Err(FixedFourPortBenchError::ReferenceImpedanceNot50Ohms);
        }
        if frequencies.is_empty() {
            return Err(FixedFourPortBenchError::EmptySpectrum);
        }
        if frequencies.len() != samples.len() {
            return Err(FixedFourPortBenchError::LengthMismatch {
                frequencies: frequencies.len(),
                samples: samples.len(),
            });
        }
        if frequencies
            .windows(2)
            .any(|pair| pair[1].get() <= pair[0].get())
        {
            return Err(FixedFourPortBenchError::NonIncreasingFrequency);
        }
        Ok(Self {
            reference_impedance,
            frequencies: frequencies.into_boxed_slice(),
            samples: samples.into_boxed_slice(),
        })
    }

    pub fn reference_impedance(&self) -> Ohms {
        self.reference_impedance
    }

    pub const fn port_map(&self) -> SelectedP3cPortMapV1 {
        SelectedP3cPortMapV1::TxPlusRxPlusTxMinusRxMinus
    }

    pub fn frequencies(&self) -> &[Hertz] {
        &self.frequencies
    }

    pub fn samples(&self) -> &[FourPortS] {
        &self.samples
    }
}

/// The scalar differential transfer for the fixed P3C bench. Its samples are
/// frequency-domain observations only; they are not a time-domain kernel.
#[derive(Clone, Debug, PartialEq)]
pub struct SelectedP3cStaticDifferentialTransferV1 {
    frequencies: Box<[Hertz]>,
    transfer: Box<[Complex64]>,
}

impl SelectedP3cStaticDifferentialTransferV1 {
    pub fn frequencies(&self) -> &[Hertz] {
        &self.frequencies
    }

    pub fn transfer(&self) -> &[Complex64] {
        &self.transfer
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum FixedFourPortBenchError {
    ReferenceImpedanceNot50Ohms,
    EmptySpectrum,
    LengthMismatch { frequencies: usize, samples: usize },
    NonIncreasingFrequency,
    ArithmeticOverflow,
}

impl fmt::Display for FixedFourPortBenchError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            formatter,
            "selected P3C four-port bench is invalid: {self:?}"
        )
    }
}

impl Error for FixedFourPortBenchError {}

fn hdiff(sample: FourPortS) -> Result<Complex64, FixedFourPortBenchError> {
    // S[row output][column incident], port order: TX+, RX+, TX-, RX-.
    // The first half is the differential mixed-mode projection and the
    // second is the matched Thevenin source division.
    let s21 = sample.at(1, 0).expect("fixed 4x4 matrix");
    let s23 = sample.at(1, 2).expect("fixed 4x4 matrix");
    let s41 = sample.at(3, 0).expect("fixed 4x4 matrix");
    let s43 = sample.at(3, 2).expect("fixed 4x4 matrix");
    let real = (s21.real() - s23.real() - s41.real() + s43.real()) / 4.0;
    let imaginary = (s21.imaginary() - s23.imaginary() - s41.imaginary() + s43.imaginary()) / 4.0;
    Complex64::try_new(real, imaginary).map_err(|_| FixedFourPortBenchError::ArithmeticOverflow)
}

/// Reduce the single matched P3C four-port bench to its scalar differential
/// transfer. No source, load, port-map, or solver option is caller-selectable.
pub fn reduce_selected_p3c_fixed_four_port_bench_v1(
    input: &SelectedP3cFourPortSpectrumV1,
) -> Result<SelectedP3cStaticDifferentialTransferV1, FixedFourPortBenchError> {
    let transfer = input
        .samples()
        .iter()
        .copied()
        .map(hdiff)
        .collect::<Result<Vec<_>, _>>()?;
    Ok(SelectedP3cStaticDifferentialTransferV1 {
        frequencies: input.frequencies().to_vec().into_boxed_slice(),
        transfer: transfer.into_boxed_slice(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn c(real: f64, imaginary: f64) -> Complex64 {
        Complex64::try_new(real, imaginary).unwrap()
    }

    fn matrix(entries: &[(usize, usize, f64, f64)]) -> FourPortS {
        let mut values = [[c(0.0, 0.0); SELECTED_P3C_PORT_COUNT]; SELECTED_P3C_PORT_COUNT];
        for &(output, incident, real, imaginary) in entries {
            values[output][incident] = c(real, imaginary);
        }
        FourPortS::new(values)
    }

    fn spectrum(samples: Vec<FourPortS>) -> SelectedP3cFourPortSpectrumV1 {
        let frequencies = (0..samples.len())
            .map(|index| Hertz::try_new(index as f64).unwrap())
            .collect();
        SelectedP3cFourPortSpectrumV1::try_new(Ohms::try_new(50.0).unwrap(), frequencies, samples)
            .unwrap()
    }

    #[test]
    fn asymmetric_matrix_proves_public_port_positions_and_signs() {
        let input = spectrum(vec![matrix(&[
            (1, 0, 4.0, 8.0),
            (1, 2, 8.0, 4.0),
            (3, 0, 12.0, -4.0),
            (3, 2, 16.0, -8.0),
        ])]);
        let transfer = reduce_selected_p3c_fixed_four_port_bench_v1(&input).unwrap();
        assert_eq!(transfer.transfer()[0], c(0.0, 0.0));
    }

    #[test]
    fn differential_through_and_common_mode_are_distinguished() {
        let differential = spectrum(vec![matrix(&[(1, 0, 1.0, 0.0), (3, 2, 1.0, 0.0)])]);
        assert_eq!(
            reduce_selected_p3c_fixed_four_port_bench_v1(&differential)
                .unwrap()
                .transfer()[0],
            c(0.5, 0.0)
        );
        let common_mode = spectrum(vec![matrix(&[(1, 0, 1.0, 0.0), (3, 0, 1.0, 0.0)])]);
        assert_eq!(
            reduce_selected_p3c_fixed_four_port_bench_v1(&common_mode)
                .unwrap()
                .transfer()[0],
            c(0.0, 0.0)
        );
    }

    #[test]
    fn static_input_rejects_unmatched_or_ambiguous_frequency_data() {
        let sample = matrix(&[]);
        assert_eq!(
            SelectedP3cFourPortSpectrumV1::try_new(
                Ohms::try_new(49.0).unwrap(),
                vec![Hertz::try_new(0.0).unwrap()],
                vec![sample],
            )
            .unwrap_err(),
            FixedFourPortBenchError::ReferenceImpedanceNot50Ohms
        );
        assert_eq!(
            SelectedP3cFourPortSpectrumV1::try_new(
                Ohms::try_new(50.0).unwrap(),
                vec![Hertz::try_new(1.0).unwrap(), Hertz::try_new(1.0).unwrap()],
                vec![sample, sample],
            )
            .unwrap_err(),
            FixedFourPortBenchError::NonIncreasingFrequency
        );
    }
}
