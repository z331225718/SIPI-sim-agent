#![forbid(unsafe_code)]

//! Unit-carrying data containers with construction-time invariants only.
//!
//! This crate deliberately contains no conversion, sampling, transform, port,
//! or simulation semantics. Those rules belong to later versioned contracts.

use std::{collections::BTreeSet, error::Error, fmt, num::NonZeroUsize};

/// Identifies the unsupported CLI foundation that consumes this crate.
pub const FOUNDATION_STAGE: &str = "P1-01";

/// Errors raised when a foundational value would violate a structural invariant.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TypeError {
    NonFinite { kind: &'static str },
    Empty { kind: &'static str },
    InvalidPortId,
    DuplicatePortId { value: String },
    ZeroDimension { index: usize },
    ShapeProductOverflow,
    LengthMismatch { expected: usize, actual: usize },
    ZeroStep,
}

impl fmt::Display for TypeError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::NonFinite { kind } => write!(formatter, "{kind} must be finite"),
            Self::Empty { kind } => write!(formatter, "{kind} must not be empty"),
            Self::InvalidPortId => write!(formatter, "port identifier is invalid"),
            Self::DuplicatePortId { value } => {
                write!(formatter, "duplicate port identifier: {value}")
            }
            Self::ZeroDimension { index } => {
                write!(formatter, "tensor dimension {index} must not be zero")
            }
            Self::ShapeProductOverflow => write!(formatter, "tensor shape product overflows usize"),
            Self::LengthMismatch { expected, actual } => {
                write!(
                    formatter,
                    "length mismatch: expected {expected}, got {actual}"
                )
            }
            Self::ZeroStep => write!(formatter, "axis step must not be zero"),
        }
    }
}

impl Error for TypeError {}

/// A finite IEEE-754 `f64` with no unit semantics.
#[derive(Clone, Copy, Debug, PartialEq, PartialOrd)]
pub struct FiniteF64(f64);

impl FiniteF64 {
    pub fn try_new(value: f64, kind: &'static str) -> Result<Self, TypeError> {
        if value.is_finite() {
            Ok(Self(value))
        } else {
            Err(TypeError::NonFinite { kind })
        }
    }

    pub fn get(self) -> f64 {
        self.0
    }
}

mod sealed {
    pub trait Measurement {}
}

/// A unit-bearing finite scalar usable as an axis coordinate or step.
pub trait Measurement: sealed::Measurement + Copy {
    fn finite(self) -> FiniteF64;
}

macro_rules! si_unit {
    ($name:ident, $kind:literal) => {
        #[doc = concat!("A finite SI value measured in ", $kind, ".")]
        #[derive(Clone, Copy, Debug, PartialEq, PartialOrd)]
        pub struct $name(FiniteF64);

        impl $name {
            pub fn try_new(value: f64) -> Result<Self, TypeError> {
                FiniteF64::try_new(value, $kind).map(Self)
            }

            pub fn get(self) -> f64 {
                self.0.get()
            }
        }

        impl sealed::Measurement for $name {}

        impl Measurement for $name {
            fn finite(self) -> FiniteF64 {
                self.0
            }
        }
    };
}

si_unit!(Seconds, "seconds");
si_unit!(Hertz, "hertz");
si_unit!(Volts, "volts");
si_unit!(Amps, "amps");
si_unit!(Ohms, "ohms");
si_unit!(Siemens, "siemens");
si_unit!(Meters, "meters");

/// A finite, non-zero step expressed in the same unit as its axis.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct NonZeroStep<U>(U);

impl<U: Measurement> NonZeroStep<U> {
    pub fn try_new(value: U) -> Result<Self, TypeError> {
        if value.finite().get() == 0.0 {
            Err(TypeError::ZeroStep)
        } else {
            Ok(Self(value))
        }
    }

    pub fn get(self) -> U {
        self.0
    }
}

/// A port name with no implied numbering, direction, or electrical semantics.
#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct PortId(String);

impl PortId {
    pub fn try_new(value: impl Into<String>) -> Result<Self, TypeError> {
        let value = value.into();
        if value.is_empty()
            || value
                .chars()
                .any(|character| character == '\0' || character.is_control())
        {
            return Err(TypeError::InvalidPortId);
        }
        Ok(Self(value))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// A non-empty, declaration-ordered collection of unique port identifiers.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PortList(Vec<PortId>);

impl PortList {
    pub fn try_new(values: Vec<PortId>) -> Result<Self, TypeError> {
        if values.is_empty() {
            return Err(TypeError::Empty { kind: "port list" });
        }
        let mut seen = BTreeSet::new();
        for value in &values {
            if !seen.insert(value.as_str()) {
                return Err(TypeError::DuplicatePortId {
                    value: value.as_str().to_owned(),
                });
            }
        }
        Ok(Self(values))
    }

    pub fn as_slice(&self) -> &[PortId] {
        &self.0
    }
}

/// A finite complex sample with no frequency-domain or impedance semantics.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Complex64 {
    real: FiniteF64,
    imaginary: FiniteF64,
}

impl Complex64 {
    pub fn try_new(real: f64, imaginary: f64) -> Result<Self, TypeError> {
        Ok(Self {
            real: FiniteF64::try_new(real, "complex real component")?,
            imaginary: FiniteF64::try_new(imaginary, "complex imaginary component")?,
        })
    }

    pub fn real(self) -> f64 {
        self.real.get()
    }

    pub fn imaginary(self) -> f64 {
        self.imaginary.get()
    }
}

/// A uniformly represented or explicitly supplied coordinate axis.
#[derive(Clone, Debug, PartialEq)]
pub struct Axis<U>(AxisRepresentation<U>);

#[derive(Clone, Debug, PartialEq)]
enum AxisRepresentation<U> {
    Uniform {
        start: U,
        step: NonZeroStep<U>,
        count: NonZeroUsize,
    },
    Explicit(Box<[U]>),
}

impl<U: Measurement> Axis<U> {
    pub fn uniform(start: U, step: NonZeroStep<U>, count: NonZeroUsize) -> Self {
        Self(AxisRepresentation::Uniform { start, step, count })
    }
}

impl<U> Axis<U> {
    pub fn explicit(values: Vec<U>) -> Result<Self, TypeError> {
        if values.is_empty() {
            return Err(TypeError::Empty { kind: "axis" });
        }
        Ok(Self(AxisRepresentation::Explicit(
            values.into_boxed_slice(),
        )))
    }

    pub fn len(&self) -> usize {
        match &self.0 {
            AxisRepresentation::Uniform { count, .. } => count.get(),
            AxisRepresentation::Explicit(values) => values.len(),
        }
    }

    pub fn is_empty(&self) -> bool {
        false
    }

    pub fn is_uniform(&self) -> bool {
        matches!(&self.0, AxisRepresentation::Uniform { .. })
    }
}

/// A shape-checked dense complex tensor without dimension labels or layout semantics.
#[derive(Clone, Debug, PartialEq)]
pub struct ComplexTensor {
    shape: Box<[NonZeroUsize]>,
    values: Box<[Complex64]>,
}

impl ComplexTensor {
    pub fn try_new(shape: Vec<usize>, values: Vec<Complex64>) -> Result<Self, TypeError> {
        if shape.is_empty() {
            return Err(TypeError::Empty {
                kind: "tensor shape",
            });
        }
        let mut expected = 1usize;
        let mut checked_shape = Vec::with_capacity(shape.len());
        for (index, dimension) in shape.into_iter().enumerate() {
            let Some(dimension) = NonZeroUsize::new(dimension) else {
                return Err(TypeError::ZeroDimension { index });
            };
            expected = expected
                .checked_mul(dimension.get())
                .ok_or(TypeError::ShapeProductOverflow)?;
            checked_shape.push(dimension);
        }
        if values.len() != expected {
            return Err(TypeError::LengthMismatch {
                expected,
                actual: values.len(),
            });
        }
        Ok(Self {
            shape: checked_shape.into_boxed_slice(),
            values: values.into_boxed_slice(),
        })
    }

    pub fn shape(&self) -> &[NonZeroUsize] {
        &self.shape
    }

    pub fn values(&self) -> &[Complex64] {
        &self.values
    }
}

/// Discrete voltage samples associated with a time axis.
#[derive(Clone, Debug, PartialEq)]
pub struct Waveform {
    axis: Axis<Seconds>,
    samples: Box<[Volts]>,
}

impl Waveform {
    pub fn try_new(axis: Axis<Seconds>, samples: Vec<Volts>) -> Result<Self, TypeError> {
        require_matching_length(axis.len(), samples.len())?;
        Ok(Self {
            axis,
            samples: samples.into_boxed_slice(),
        })
    }

    pub fn axis(&self) -> &Axis<Seconds> {
        &self.axis
    }

    pub fn samples(&self) -> &[Volts] {
        &self.samples
    }
}

/// Raw complex bins associated with a frequency axis.
#[derive(Clone, Debug, PartialEq)]
pub struct Spectrum {
    axis: Axis<Hertz>,
    bins: Box<[Complex64]>,
}

impl Spectrum {
    pub fn try_new(axis: Axis<Hertz>, bins: Vec<Complex64>) -> Result<Self, TypeError> {
        require_matching_length(axis.len(), bins.len())?;
        Ok(Self {
            axis,
            bins: bins.into_boxed_slice(),
        })
    }

    pub fn axis(&self) -> &Axis<Hertz> {
        &self.axis
    }

    pub fn bins(&self) -> &[Complex64] {
        &self.bins
    }
}

fn require_matching_length(expected: usize, actual: usize) -> Result<(), TypeError> {
    if expected == actual {
        Ok(())
    } else {
        Err(TypeError::LengthMismatch { expected, actual })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn seconds(value: f64) -> Seconds {
        Seconds::try_new(value).expect("finite seconds")
    }

    fn volts(value: f64) -> Volts {
        Volts::try_new(value).expect("finite volts")
    }

    fn complex(real: f64, imaginary: f64) -> Complex64 {
        Complex64::try_new(real, imaginary).expect("finite complex sample")
    }

    #[test]
    fn finite_wrappers_reject_non_finite_values() {
        assert_eq!(
            FiniteF64::try_new(f64::NAN, "value"),
            Err(TypeError::NonFinite { kind: "value" })
        );
        assert_eq!(
            Ohms::try_new(f64::INFINITY),
            Err(TypeError::NonFinite { kind: "ohms" })
        );
        assert_eq!(
            Complex64::try_new(1.0, f64::NEG_INFINITY),
            Err(TypeError::NonFinite {
                kind: "complex imaginary component"
            })
        );
    }

    #[test]
    fn ports_are_unique_and_preserve_declaration_order() {
        let tx = PortId::try_new("tx").expect("valid port");
        let rx = PortId::try_new("rx").expect("valid port");
        let ports = PortList::try_new(vec![tx.clone(), rx.clone()]).expect("unique ports");

        assert_eq!(ports.as_slice(), &[tx, rx]);
        assert_eq!(PortId::try_new("bad\nport"), Err(TypeError::InvalidPortId));
        assert_eq!(
            PortList::try_new(vec![
                PortId::try_new("tx").unwrap(),
                PortId::try_new("tx").unwrap()
            ]),
            Err(TypeError::DuplicatePortId {
                value: "tx".to_owned()
            })
        );
    }

    #[test]
    fn axes_do_not_impose_direction_or_regular_spacing_on_explicit_values() {
        let explicit = Axis::<Seconds>::explicit(vec![seconds(2.0), seconds(1.0), seconds(1.0)])
            .expect("non-empty explicit axis");
        let uniform = Axis::uniform(
            seconds(0.0),
            NonZeroStep::try_new(seconds(-1.0)).expect("non-zero step"),
            NonZeroUsize::new(3).unwrap(),
        );

        assert_eq!(explicit.len(), 3);
        assert!(!explicit.is_uniform());
        assert!(uniform.is_uniform());
        assert_eq!(NonZeroStep::try_new(seconds(0.0)), Err(TypeError::ZeroStep));
    }

    #[test]
    fn tensors_require_a_non_empty_exact_shape() {
        assert_eq!(
            ComplexTensor::try_new(vec![], vec![]),
            Err(TypeError::Empty {
                kind: "tensor shape"
            })
        );
        assert_eq!(
            ComplexTensor::try_new(vec![2, 0], vec![]),
            Err(TypeError::ZeroDimension { index: 1 })
        );
        assert_eq!(
            ComplexTensor::try_new(vec![2, 2], vec![complex(0.0, 0.0)]),
            Err(TypeError::LengthMismatch {
                expected: 4,
                actual: 1
            })
        );
        assert_eq!(
            ComplexTensor::try_new(vec![usize::MAX, 2], vec![]),
            Err(TypeError::ShapeProductOverflow)
        );
    }

    #[test]
    fn waveform_and_spectrum_require_matching_axis_lengths() {
        let time_axis = Axis::explicit(vec![seconds(0.0), seconds(1.0)]).unwrap();
        let frequency_axis = Axis::explicit(vec![Hertz::try_new(0.0).unwrap()]).unwrap();

        assert_eq!(
            Waveform::try_new(time_axis, vec![volts(1.0)]),
            Err(TypeError::LengthMismatch {
                expected: 2,
                actual: 1
            })
        );
        assert!(Spectrum::try_new(frequency_axis, vec![complex(1.0, 0.0)]).is_ok());
    }
}
