#![forbid(unsafe_code)]

//! Strict, directional comparison for caller-aligned finite numeric arrays.
//!
//! This crate does not align axes, convert units, choose tolerances, read
//! files, or know any simulation domain. Callers must establish those facts
//! before constructing [`AlignedArrayV1`].

pub mod prbs9_waveform_v2;
pub mod selected_highloss_prbs9_waveform_only_v3;

use std::{error::Error, fmt};

use sha2::{Digest, Sha256};

pub const ARRAY_COMPARE_SCHEMA_V1: &str = "sipi.compare.array-report.v1";
pub const ARRAY_COMPARE_POLICY_V1: &str = "sipi.compare.reference-to-candidate.abs-rel.v1";

/// A validated, non-empty tensor shape with no layout or axis semantics.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ArrayShapeV1(Vec<usize>);

impl ArrayShapeV1 {
    pub fn try_new(dimensions: Vec<usize>) -> Result<Self, ArrayCompareErrorV1> {
        if dimensions.is_empty() {
            return Err(ArrayCompareErrorV1::EmptyShape);
        }
        let mut count = 1_usize;
        for (index, dimension) in dimensions.iter().copied().enumerate() {
            if dimension == 0 {
                return Err(ArrayCompareErrorV1::ZeroDimension { index });
            }
            count = count
                .checked_mul(dimension)
                .ok_or(ArrayCompareErrorV1::ShapeProductOverflow)?;
        }
        Ok(Self(dimensions))
    }

    pub fn dimensions(&self) -> &[usize] {
        &self.0
    }

    pub fn element_count(&self) -> Result<usize, ArrayCompareErrorV1> {
        self.0.iter().try_fold(1_usize, |count, dimension| {
            count
                .checked_mul(*dimension)
                .ok_or(ArrayCompareErrorV1::ShapeProductOverflow)
        })
    }
}

/// A canonical lowercase ASCII unit token. It carries no conversion rule.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct UnitTagV1(String);

impl UnitTagV1 {
    pub fn try_new(value: impl Into<String>) -> Result<Self, ArrayCompareErrorV1> {
        let value = value.into();
        if value.is_empty()
            || value.len() > 64
            || !value.bytes().enumerate().all(|(index, byte)| {
                byte.is_ascii_lowercase()
                    || byte.is_ascii_digit()
                    || (index > 0 && matches!(byte, b'.' | b'_' | b'-' | b'/'))
            })
        {
            return Err(ArrayCompareErrorV1::InvalidUnitTag);
        }
        Ok(Self(value))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// A caller-owned digest that binds the axis and semantic interpretation.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SemanticBindingDigestV1(String);

impl SemanticBindingDigestV1 {
    pub fn try_new(value: impl Into<String>) -> Result<Self, ArrayCompareErrorV1> {
        let value = value.into();
        if !is_lowercase_sha256(&value) {
            return Err(ArrayCompareErrorV1::InvalidBindingDigest);
        }
        Ok(Self(value))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

/// A finite array whose shape, unit, and semantic binding have been supplied
/// by the caller. The array is not resampled or otherwise transformed.
#[derive(Clone, Debug, PartialEq)]
pub struct AlignedArrayV1 {
    shape: ArrayShapeV1,
    unit: UnitTagV1,
    semantic_binding: SemanticBindingDigestV1,
    values: Vec<f64>,
}

impl AlignedArrayV1 {
    pub fn try_new(
        shape: ArrayShapeV1,
        unit: UnitTagV1,
        semantic_binding: SemanticBindingDigestV1,
        values: Vec<f64>,
    ) -> Result<Self, ArrayCompareErrorV1> {
        let expected = shape.element_count()?;
        if values.len() != expected {
            return Err(ArrayCompareErrorV1::LengthMismatch {
                expected,
                actual: values.len(),
            });
        }
        for (index, value) in values.iter().enumerate() {
            if !value.is_finite() {
                return Err(ArrayCompareErrorV1::NonFiniteValue { index });
            }
        }
        Ok(Self {
            shape,
            unit,
            semantic_binding,
            values,
        })
    }

    pub fn shape(&self) -> &ArrayShapeV1 {
        &self.shape
    }

    pub fn unit(&self) -> &UnitTagV1 {
        &self.unit
    }

    pub fn semantic_binding(&self) -> &SemanticBindingDigestV1 {
        &self.semantic_binding
    }

    pub fn values(&self) -> &[f64] {
        &self.values
    }

    pub fn canonical_digest(&self) -> String {
        let mut hash = Sha256::new();
        update_length_prefixed(&mut hash, b"sipi.compare.aligned-array.v1");
        update_u64(&mut hash, self.shape.dimensions().len() as u64);
        for dimension in self.shape.dimensions() {
            update_u64(&mut hash, *dimension as u64);
        }
        update_length_prefixed(&mut hash, self.unit.as_str().as_bytes());
        update_length_prefixed(&mut hash, self.semantic_binding.as_str().as_bytes());
        update_u64(&mut hash, self.values.len() as u64);
        for value in &self.values {
            hash.update(value.to_bits().to_le_bytes());
        }
        format!("{:x}", hash.finalize())
    }
}

/// Explicit absolute and reference-relative error limits. There are no
/// defaults: callers must choose both values.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ToleranceV1 {
    absolute: f64,
    relative: f64,
}

impl ToleranceV1 {
    pub fn try_new(absolute: f64, relative: f64) -> Result<Self, ArrayCompareErrorV1> {
        if !absolute.is_finite() || absolute < 0.0 {
            return Err(ArrayCompareErrorV1::InvalidTolerance { field: "absolute" });
        }
        if !relative.is_finite() || relative < 0.0 {
            return Err(ArrayCompareErrorV1::InvalidTolerance { field: "relative" });
        }
        Ok(Self { absolute, relative })
    }

    pub fn absolute(self) -> f64 {
        self.absolute
    }

    pub fn relative(self) -> f64 {
        self.relative
    }
}

/// A metadata-only outcome of one directional reference-to-candidate compare.
#[derive(Clone, Debug, PartialEq)]
pub struct ArrayCompareReportV1 {
    schema: &'static str,
    policy: &'static str,
    reference_digest: String,
    candidate_digest: String,
    shape: ArrayShapeV1,
    unit: UnitTagV1,
    semantic_binding: SemanticBindingDigestV1,
    passed: bool,
    mismatch_count: usize,
    max_absolute_error: f64,
    max_allowed_error: f64,
    first_mismatch_index: Option<usize>,
}

impl ArrayCompareReportV1 {
    pub fn schema(&self) -> &'static str {
        self.schema
    }
    pub fn policy(&self) -> &'static str {
        self.policy
    }
    pub fn reference_digest(&self) -> &str {
        &self.reference_digest
    }
    pub fn candidate_digest(&self) -> &str {
        &self.candidate_digest
    }
    pub fn shape(&self) -> &ArrayShapeV1 {
        &self.shape
    }
    pub fn unit(&self) -> &UnitTagV1 {
        &self.unit
    }
    pub fn semantic_binding(&self) -> &SemanticBindingDigestV1 {
        &self.semantic_binding
    }
    pub fn passed(&self) -> bool {
        self.passed
    }
    pub fn mismatch_count(&self) -> usize {
        self.mismatch_count
    }
    pub fn max_absolute_error(&self) -> f64 {
        self.max_absolute_error
    }
    pub fn max_allowed_error(&self) -> f64 {
        self.max_allowed_error
    }
    pub fn first_mismatch_index(&self) -> Option<usize> {
        self.first_mismatch_index
    }
}

/// Fail-closed structural and numerical comparison errors.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ArrayCompareErrorV1 {
    MissingReference,
    MissingCandidate,
    EmptyShape,
    ZeroDimension { index: usize },
    ShapeProductOverflow,
    LengthMismatch { expected: usize, actual: usize },
    InvalidUnitTag,
    InvalidBindingDigest,
    NonFiniteValue { index: usize },
    InvalidTolerance { field: &'static str },
    ShapeMismatch,
    UnitMismatch,
    BindingMismatch,
    NumericOverflow { index: usize },
}

impl fmt::Display for ArrayCompareErrorV1 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::MissingReference => write!(formatter, "reference array is missing"),
            Self::MissingCandidate => write!(formatter, "candidate array is missing"),
            Self::EmptyShape => write!(formatter, "array shape must not be empty"),
            Self::ZeroDimension { index } => write!(formatter, "array dimension {index} is zero"),
            Self::ShapeProductOverflow => write!(formatter, "array shape product overflows usize"),
            Self::LengthMismatch { expected, actual } => {
                write!(
                    formatter,
                    "array length mismatch: expected {expected}, got {actual}"
                )
            }
            Self::InvalidUnitTag => write!(formatter, "unit tag is not canonical ASCII"),
            Self::InvalidBindingDigest => write!(formatter, "semantic binding digest is invalid"),
            Self::NonFiniteValue { index } => {
                write!(formatter, "array value {index} is non-finite")
            }
            Self::InvalidTolerance { field } => write!(formatter, "{field} tolerance is invalid"),
            Self::ShapeMismatch => write!(formatter, "array shapes differ"),
            Self::UnitMismatch => write!(formatter, "array units differ"),
            Self::BindingMismatch => write!(formatter, "array semantic bindings differ"),
            Self::NumericOverflow { index } => {
                write!(
                    formatter,
                    "comparison arithmetic is non-finite at index {index}"
                )
            }
        }
    }
}

impl Error for ArrayCompareErrorV1 {}

/// Compares already-aligned arrays with the directional v1 criterion:
/// `abs(candidate - reference) <= abs_tol + rel_tol * abs(reference)`.
pub fn compare_arrays_v1(
    reference: Option<&AlignedArrayV1>,
    candidate: Option<&AlignedArrayV1>,
    tolerance: ToleranceV1,
) -> Result<ArrayCompareReportV1, ArrayCompareErrorV1> {
    let reference = reference.ok_or(ArrayCompareErrorV1::MissingReference)?;
    let candidate = candidate.ok_or(ArrayCompareErrorV1::MissingCandidate)?;
    if reference.shape != candidate.shape {
        return Err(ArrayCompareErrorV1::ShapeMismatch);
    }
    if reference.unit != candidate.unit {
        return Err(ArrayCompareErrorV1::UnitMismatch);
    }
    if reference.semantic_binding != candidate.semantic_binding {
        return Err(ArrayCompareErrorV1::BindingMismatch);
    }

    let mut mismatch_count = 0_usize;
    let mut first_mismatch_index = None;
    let mut max_absolute_error = 0.0_f64;
    let mut max_allowed_error = 0.0_f64;
    for (index, (reference_value, candidate_value)) in
        reference.values.iter().zip(&candidate.values).enumerate()
    {
        let absolute_error = (*candidate_value - *reference_value).abs();
        let allowed_error = tolerance.absolute + tolerance.relative * reference_value.abs();
        if !absolute_error.is_finite() || !allowed_error.is_finite() {
            return Err(ArrayCompareErrorV1::NumericOverflow { index });
        }
        max_absolute_error = max_absolute_error.max(absolute_error);
        max_allowed_error = max_allowed_error.max(allowed_error);
        if absolute_error > allowed_error {
            mismatch_count += 1;
            first_mismatch_index.get_or_insert(index);
        }
    }

    Ok(ArrayCompareReportV1 {
        schema: ARRAY_COMPARE_SCHEMA_V1,
        policy: ARRAY_COMPARE_POLICY_V1,
        reference_digest: reference.canonical_digest(),
        candidate_digest: candidate.canonical_digest(),
        shape: reference.shape.clone(),
        unit: reference.unit.clone(),
        semantic_binding: reference.semantic_binding.clone(),
        passed: mismatch_count == 0,
        mismatch_count,
        max_absolute_error,
        max_allowed_error,
        first_mismatch_index,
    })
}

fn update_length_prefixed(hash: &mut Sha256, bytes: &[u8]) {
    update_u64(hash, bytes.len() as u64);
    hash.update(bytes);
}

fn update_u64(hash: &mut Sha256, value: u64) {
    hash.update(value.to_le_bytes());
}

fn is_lowercase_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

#[cfg(test)]
mod tests {
    use super::*;

    const BINDING: &str = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";

    fn array(values: &[f64]) -> AlignedArrayV1 {
        AlignedArrayV1::try_new(
            ArrayShapeV1::try_new(vec![values.len()]).unwrap(),
            UnitTagV1::try_new("v").unwrap(),
            SemanticBindingDigestV1::try_new(BINDING).unwrap(),
            values.to_vec(),
        )
        .unwrap()
    }

    #[test]
    fn exact_and_directional_tolerance_comparisons_are_deterministic() {
        let reference = array(&[0.0, -2.0, 4.0]);
        let candidate = array(&[0.0, -1.999, 4.004]);
        let tolerance = ToleranceV1::try_new(0.0, 0.001).unwrap();
        let report = compare_arrays_v1(Some(&reference), Some(&candidate), tolerance).unwrap();
        assert!(report.passed());
        assert_eq!(report.mismatch_count(), 0);
        assert_eq!(report.first_mismatch_index(), None);
        assert_eq!(report.schema(), ARRAY_COMPARE_SCHEMA_V1);
        assert_eq!(report.policy(), ARRAY_COMPARE_POLICY_V1);
        assert_eq!(
            report,
            compare_arrays_v1(Some(&reference), Some(&candidate), tolerance).unwrap()
        );

        let failed = compare_arrays_v1(
            Some(&reference),
            Some(&array(&[0.0, -1.998, 4.004])),
            tolerance,
        )
        .unwrap();
        assert!(!failed.passed());
        assert_eq!(failed.mismatch_count(), 1);
        assert_eq!(failed.first_mismatch_index(), Some(1));
    }

    #[test]
    fn zero_reference_and_negative_zero_identity_are_intentional() {
        let reference = array(&[-0.0]);
        let candidate = array(&[0.0]);
        let report = compare_arrays_v1(
            Some(&reference),
            Some(&candidate),
            ToleranceV1::try_new(0.0, 0.0).unwrap(),
        )
        .unwrap();
        assert!(report.passed());
        assert_ne!(report.reference_digest(), report.candidate_digest());

        let zero = array(&[0.0]);
        let failed = compare_arrays_v1(
            Some(&zero),
            Some(&array(&[1.0e-12])),
            ToleranceV1::try_new(0.0, 1.0).unwrap(),
        )
        .unwrap();
        assert!(!failed.passed());
    }

    #[test]
    fn structural_missing_and_non_finite_inputs_fail_closed() {
        let reference = array(&[1.0, 2.0]);
        let candidate = array(&[1.0, 2.0]);
        let tolerance = ToleranceV1::try_new(0.0, 0.0).unwrap();
        assert_eq!(
            compare_arrays_v1(None, Some(&candidate), tolerance),
            Err(ArrayCompareErrorV1::MissingReference)
        );
        assert_eq!(
            compare_arrays_v1(Some(&reference), None, tolerance),
            Err(ArrayCompareErrorV1::MissingCandidate)
        );
        assert_eq!(
            ArrayShapeV1::try_new(vec![]),
            Err(ArrayCompareErrorV1::EmptyShape)
        );
        assert_eq!(
            ArrayShapeV1::try_new(vec![1, 0]),
            Err(ArrayCompareErrorV1::ZeroDimension { index: 1 })
        );
        assert_eq!(
            AlignedArrayV1::try_new(
                ArrayShapeV1::try_new(vec![1]).unwrap(),
                UnitTagV1::try_new("v").unwrap(),
                SemanticBindingDigestV1::try_new(BINDING).unwrap(),
                vec![f64::NAN],
            ),
            Err(ArrayCompareErrorV1::NonFiniteValue { index: 0 })
        );
        assert_eq!(
            ToleranceV1::try_new(-1.0, 0.0),
            Err(ArrayCompareErrorV1::InvalidTolerance { field: "absolute" })
        );
        assert_eq!(
            ToleranceV1::try_new(0.0, f64::INFINITY),
            Err(ArrayCompareErrorV1::InvalidTolerance { field: "relative" })
        );
    }

    #[test]
    fn shape_unit_binding_and_numeric_overflow_never_degrade_to_mismatch() {
        let reference = array(&[1.0, 2.0]);
        let shape_mismatch = array(&[1.0]);
        assert_eq!(
            compare_arrays_v1(
                Some(&reference),
                Some(&shape_mismatch),
                ToleranceV1::try_new(0.0, 0.0).unwrap()
            ),
            Err(ArrayCompareErrorV1::ShapeMismatch)
        );
        let other_unit = AlignedArrayV1::try_new(
            ArrayShapeV1::try_new(vec![2]).unwrap(),
            UnitTagV1::try_new("a").unwrap(),
            SemanticBindingDigestV1::try_new(BINDING).unwrap(),
            vec![1.0, 2.0],
        )
        .unwrap();
        assert_eq!(
            compare_arrays_v1(
                Some(&reference),
                Some(&other_unit),
                ToleranceV1::try_new(0.0, 0.0).unwrap()
            ),
            Err(ArrayCompareErrorV1::UnitMismatch)
        );
        let other_binding = AlignedArrayV1::try_new(
            ArrayShapeV1::try_new(vec![2]).unwrap(),
            UnitTagV1::try_new("v").unwrap(),
            SemanticBindingDigestV1::try_new(
                "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            )
            .unwrap(),
            vec![1.0, 2.0],
        )
        .unwrap();
        assert_eq!(
            compare_arrays_v1(
                Some(&reference),
                Some(&other_binding),
                ToleranceV1::try_new(0.0, 0.0).unwrap()
            ),
            Err(ArrayCompareErrorV1::BindingMismatch)
        );
        assert_eq!(
            compare_arrays_v1(
                Some(&array(&[f64::MAX])),
                Some(&array(&[-f64::MAX])),
                ToleranceV1::try_new(0.0, 0.0).unwrap(),
            ),
            Err(ArrayCompareErrorV1::NumericOverflow { index: 0 })
        );
    }

    #[test]
    fn malformed_tokens_and_shape_overflow_are_rejected() {
        assert_eq!(
            UnitTagV1::try_new("V"),
            Err(ArrayCompareErrorV1::InvalidUnitTag)
        );
        assert_eq!(
            UnitTagV1::try_new("v / v"),
            Err(ArrayCompareErrorV1::InvalidUnitTag)
        );
        assert_eq!(
            SemanticBindingDigestV1::try_new("not-a-digest"),
            Err(ArrayCompareErrorV1::InvalidBindingDigest)
        );
        assert_eq!(
            ArrayShapeV1::try_new(vec![usize::MAX, 2]),
            Err(ArrayCompareErrorV1::ShapeProductOverflow)
        );
    }
}
