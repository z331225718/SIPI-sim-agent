//! Typed, allocation-owning AMI Init/GetWave host boundary.
//!
//! The boundary validates shapes, finite values, and capability declarations.
//! It deliberately does not implement a channel solver or vendor ABI; the
//! later DLL host adapts its FFI buffers to these types.

use std::fmt;

use crate::ami::AmiHostMetadata;

/// Input handed to an AMI model's initialization entry point.
#[derive(Debug, Clone, PartialEq)]
pub struct AmiInitRequest {
    sample_interval: f64,
    impulse_response: Vec<f64>,
}

impl AmiInitRequest {
    /// Creates a request after validating time and waveform values.
    pub fn new(sample_interval: f64, impulse_response: Vec<f64>) -> Result<Self, AmiContractError> {
        validate_sample_interval(sample_interval)?;
        validate_waveform("init impulse response", &impulse_response)?;
        Ok(Self {
            sample_interval,
            impulse_response,
        })
    }

    /// Time between impulse-response samples, in seconds.
    #[must_use]
    pub const fn sample_interval(&self) -> f64 {
        self.sample_interval
    }

    /// Input impulse-response samples in chronological order.
    #[must_use]
    pub fn impulse_response(&self) -> &[f64] {
        &self.impulse_response
    }
}

/// Output returned by an AMI model initialization entry point.
#[derive(Debug, Clone, PartialEq)]
pub struct AmiInitResponse {
    impulse_response: Option<Vec<f64>>,
}

impl AmiInitResponse {
    /// Creates a response. Its compatibility with model metadata is checked by
    /// [`validate_init_response`].
    #[must_use]
    pub fn new(impulse_response: Option<Vec<f64>>) -> Self {
        Self { impulse_response }
    }

    /// Model-provided impulse response, when the model declares one.
    #[must_use]
    pub fn impulse_response(&self) -> Option<&[f64]> {
        self.impulse_response.as_deref()
    }
}

/// Input handed to an AMI model's optional GetWave entry point.
#[derive(Debug, Clone, PartialEq)]
pub struct AmiGetWaveRequest {
    sample_interval: f64,
    waveform: Vec<f64>,
}

impl AmiGetWaveRequest {
    /// Creates a request after validating time and waveform values.
    pub fn new(sample_interval: f64, waveform: Vec<f64>) -> Result<Self, AmiContractError> {
        validate_sample_interval(sample_interval)?;
        validate_waveform("GetWave input waveform", &waveform)?;
        Ok(Self {
            sample_interval,
            waveform,
        })
    }

    /// Time between waveform samples, in seconds.
    #[must_use]
    pub const fn sample_interval(&self) -> f64 {
        self.sample_interval
    }

    /// Input waveform samples in chronological order.
    #[must_use]
    pub fn waveform(&self) -> &[f64] {
        &self.waveform
    }
}

/// Output returned by an AMI model GetWave entry point.
#[derive(Debug, Clone, PartialEq)]
pub struct AmiGetWaveResponse {
    waveform: Vec<f64>,
    clock_times: Vec<f64>,
}

impl AmiGetWaveResponse {
    /// Creates a response. Its compatibility with the request is checked by
    /// [`validate_get_wave_response`].
    #[must_use]
    pub fn new(waveform: Vec<f64>, clock_times: Vec<f64>) -> Self {
        Self {
            waveform,
            clock_times,
        }
    }

    /// Output waveform samples in chronological order.
    #[must_use]
    pub fn waveform(&self) -> &[f64] {
        &self.waveform
    }

    /// Optional clock times reported by the model, in seconds.
    #[must_use]
    pub fn clock_times(&self) -> &[f64] {
        &self.clock_times
    }
}

/// Host-boundary validation failures before or after an AMI call.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AmiContractError {
    /// The sample interval was zero, negative, NaN, or infinite.
    InvalidSampleInterval,
    /// A required waveform was empty.
    EmptyWaveform { name: &'static str },
    /// A waveform or clock-time value was NaN or infinite.
    NonFiniteValue { name: &'static str, index: usize },
    /// Model metadata says `AMI_Init` returns an impulse response, but none was supplied.
    MissingInitImpulseResponse,
    /// Model metadata says `AMI_Init` does not return an impulse response, but one was supplied.
    UnexpectedInitImpulseResponse,
    /// An Init response did not preserve the request sample count.
    InitResponseLengthMismatch { expected: usize, actual: usize },
    /// GetWave was attempted for a model that did not declare that entry point.
    GetWaveUnavailable,
    /// A GetWave response did not preserve the request sample count.
    GetWaveResponseLengthMismatch { expected: usize, actual: usize },
}

impl fmt::Display for AmiContractError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidSampleInterval => write!(
                formatter,
                "sample interval must be finite and greater than zero"
            ),
            Self::EmptyWaveform { name } => write!(formatter, "{name} must not be empty"),
            Self::NonFiniteValue { name, index } => {
                write!(
                    formatter,
                    "{name} contains a non-finite value at index {index}"
                )
            }
            Self::MissingInitImpulseResponse => write!(
                formatter,
                "AMI_Init must return an impulse response when Init_Returns_Impulse is true"
            ),
            Self::UnexpectedInitImpulseResponse => write!(
                formatter,
                "AMI_Init must not return an impulse response when Init_Returns_Impulse is false"
            ),
            Self::InitResponseLengthMismatch { expected, actual } => write!(
                formatter,
                "AMI_Init impulse response length mismatch: expected {expected}, got {actual}"
            ),
            Self::GetWaveUnavailable => write!(
                formatter,
                "AMI_GetWave is unavailable because GetWave_Exists is false"
            ),
            Self::GetWaveResponseLengthMismatch { expected, actual } => write!(
                formatter,
                "AMI_GetWave waveform length mismatch: expected {expected}, got {actual}"
            ),
        }
    }
}

impl std::error::Error for AmiContractError {}

/// Validates a post-`AMI_Init` response against model metadata and its request.
pub fn validate_init_response(
    metadata: &AmiHostMetadata,
    request: &AmiInitRequest,
    response: &AmiInitResponse,
) -> Result<(), AmiContractError> {
    match (metadata.init_returns_impulse(), response.impulse_response()) {
        (true, None) => Err(AmiContractError::MissingInitImpulseResponse),
        (false, Some(_)) => Err(AmiContractError::UnexpectedInitImpulseResponse),
        (false, None) => Ok(()),
        (true, Some(impulse_response)) => {
            validate_waveform("AMI_Init impulse response", impulse_response)?;
            if impulse_response.len() != request.impulse_response().len() {
                return Err(AmiContractError::InitResponseLengthMismatch {
                    expected: request.impulse_response().len(),
                    actual: impulse_response.len(),
                });
            }
            Ok(())
        }
    }
}

/// Checks that the model declared `AMI_GetWave` before an FFI call is attempted.
pub fn validate_get_wave_request(
    metadata: &AmiHostMetadata,
    _request: &AmiGetWaveRequest,
) -> Result<(), AmiContractError> {
    if metadata.get_wave_exists() {
        Ok(())
    } else {
        Err(AmiContractError::GetWaveUnavailable)
    }
}

/// Validates a post-`AMI_GetWave` response against its request.
pub fn validate_get_wave_response(
    request: &AmiGetWaveRequest,
    response: &AmiGetWaveResponse,
) -> Result<(), AmiContractError> {
    validate_waveform("AMI_GetWave output waveform", response.waveform())?;
    validate_finite_values("AMI_GetWave clock times", response.clock_times())?;
    if response.waveform().len() != request.waveform().len() {
        return Err(AmiContractError::GetWaveResponseLengthMismatch {
            expected: request.waveform().len(),
            actual: response.waveform().len(),
        });
    }
    Ok(())
}

fn validate_sample_interval(sample_interval: f64) -> Result<(), AmiContractError> {
    if sample_interval.is_finite() && sample_interval > 0.0 {
        Ok(())
    } else {
        Err(AmiContractError::InvalidSampleInterval)
    }
}

fn validate_waveform(name: &'static str, waveform: &[f64]) -> Result<(), AmiContractError> {
    if waveform.is_empty() {
        return Err(AmiContractError::EmptyWaveform { name });
    }
    validate_finite_values(name, waveform)
}

fn validate_finite_values(name: &'static str, values: &[f64]) -> Result<(), AmiContractError> {
    values
        .iter()
        .position(|value| !value.is_finite())
        .map_or(Ok(()), |index| {
            Err(AmiContractError::NonFiniteValue { name, index })
        })
}

#[cfg(test)]
mod tests {
    use crate::ami::{AmiHostMetadata, parse_ami_parameters};

    use super::{
        AmiContractError, AmiGetWaveRequest, AmiGetWaveResponse, AmiInitRequest, AmiInitResponse,
        validate_get_wave_request, validate_get_wave_response, validate_init_response,
    };

    fn metadata(init_returns_impulse: bool, get_wave_exists: bool) -> AmiHostMetadata {
        let tree = parse_ami_parameters(&format!(
            "(AMI_Version (Type String) (Value 7.2))\n(Init_Returns_Impulse (Type Boolean) (Value {init_returns_impulse}))\n(GetWave_Exists (Type Boolean) (Value {get_wave_exists}))"
        ))
        .expect("valid AMI metadata fixture");
        AmiHostMetadata::from_tree(&tree).expect("typed AMI metadata fixture")
    }

    #[test]
    fn init_response_honors_declared_impulse_capability() {
        let request = AmiInitRequest::new(1e-12, vec![0.0, 1.0]).unwrap();
        let response = AmiInitResponse::new(Some(vec![0.25, 0.75]));
        validate_init_response(&metadata(true, false), &request, &response).unwrap();

        assert_eq!(
            validate_init_response(&metadata(false, false), &request, &response),
            Err(AmiContractError::UnexpectedInitImpulseResponse)
        );
        assert_eq!(
            validate_init_response(
                &metadata(true, false),
                &request,
                &AmiInitResponse::new(None)
            ),
            Err(AmiContractError::MissingInitImpulseResponse)
        );
    }

    #[test]
    fn init_response_rejects_non_finite_and_wrong_length_values() {
        let request = AmiInitRequest::new(1e-12, vec![0.0, 1.0]).unwrap();
        assert_eq!(
            validate_init_response(
                &metadata(true, false),
                &request,
                &AmiInitResponse::new(Some(vec![0.0]))
            ),
            Err(AmiContractError::InitResponseLengthMismatch {
                expected: 2,
                actual: 1,
            })
        );
        assert_eq!(
            AmiInitRequest::new(0.0, vec![0.0]),
            Err(AmiContractError::InvalidSampleInterval)
        );
        assert_eq!(
            AmiInitRequest::new(1e-12, vec![f64::NAN]),
            Err(AmiContractError::NonFiniteValue {
                name: "init impulse response",
                index: 0,
            })
        );
    }

    #[test]
    fn get_wave_requires_the_declared_entry_point_and_preserves_shape() {
        let request = AmiGetWaveRequest::new(1e-12, vec![1.0, 2.0]).unwrap();
        assert_eq!(
            validate_get_wave_request(&metadata(true, false), &request),
            Err(AmiContractError::GetWaveUnavailable)
        );
        validate_get_wave_request(&metadata(true, true), &request).unwrap();
        validate_get_wave_response(
            &request,
            &AmiGetWaveResponse::new(vec![0.5, 1.5], vec![0.0, 2e-12]),
        )
        .unwrap();
    }

    #[test]
    fn get_wave_rejects_bad_output_values_and_lengths() {
        let request = AmiGetWaveRequest::new(1e-12, vec![1.0, 2.0]).unwrap();
        assert_eq!(
            validate_get_wave_response(&request, &AmiGetWaveResponse::new(vec![0.0], Vec::new())),
            Err(AmiContractError::GetWaveResponseLengthMismatch {
                expected: 2,
                actual: 1,
            })
        );
        assert_eq!(
            validate_get_wave_response(
                &request,
                &AmiGetWaveResponse::new(vec![0.0, 1.0], vec![f64::INFINITY])
            ),
            Err(AmiContractError::NonFiniteValue {
                name: "AMI_GetWave clock times",
                index: 0,
            })
        );
    }
}
