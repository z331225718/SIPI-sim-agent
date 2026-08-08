//! Vendor AMI executable-library discovery through the public C ABI.
//!
//! This module owns the dynamic library and invokes its public initialization
//! ABI. It keeps parameter strings and model memory at the host boundary, then
//! adapts the modified impulse buffer to [`crate::contract`]. No vendor DLL is
//! bundled or certified by this crate.

use std::ffi::{CStr, CString, c_char, c_long, c_void};
use std::fmt;
use std::path::{Path, PathBuf};

use libloading::Library;

use crate::ami::AmiHostMetadata;
use crate::contract::{AmiContractError, AmiInitRequest, AmiInitResponse, validate_init_response};

/// Public C ABI for an IBIS AMI initialization entry point.
///
/// `impulse_matrix` is modified in place; the matrix has `row_size` rows and
/// `aggressors + 1` columns. The other pointer ownership rules remain with the
/// model as defined by the public IBIS AMI programming guide.
pub type AmiInitFn = unsafe extern "C" fn(
    impulse_matrix: *mut f64,
    row_size: c_long,
    aggressors: c_long,
    sample_interval: f64,
    bit_time: f64,
    ami_parameters_in: *const c_char,
    ami_parameters_out: *mut *mut c_char,
    ami_memory_handle: *mut *mut c_void,
    message: *mut *mut c_char,
) -> c_long;

/// Public C ABI for an optional IBIS AMI time-domain entry point.
pub type AmiGetWaveFn = unsafe extern "C" fn(
    wave: *mut f64,
    wave_size: c_long,
    clock_times: *mut f64,
    ami_parameters_out: *mut *mut c_char,
    ami_memory: *mut c_void,
) -> c_long;

/// Public C ABI for the required IBIS AMI lifecycle termination entry point.
pub type AmiCloseFn = unsafe extern "C" fn(ami_memory: *mut c_void) -> c_long;

/// Errors while opening an AMI executable model or resolving its ABI.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AmiDllLoadError {
    /// The executable model library could not be opened.
    Open { path: PathBuf, detail: String },
    /// A required IBIS AMI function was absent or could not be resolved.
    MissingRequiredSymbol {
        symbol: &'static str,
        detail: String,
    },
}

impl fmt::Display for AmiDllLoadError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Open { path, detail } => write!(
                formatter,
                "failed to open AMI executable model '{}': {detail}",
                path.display()
            ),
            Self::MissingRequiredSymbol { symbol, detail } => {
                write!(
                    formatter,
                    "AMI executable model is missing {symbol}: {detail}"
                )
            }
        }
    }
}

impl std::error::Error for AmiDllLoadError {}

/// A loaded AMI executable model whose function pointers cannot outlive it.
///
/// The private `Library` field deliberately keeps the module mapped for every
/// function pointer retained by this value.
pub struct AmiDll {
    path: PathBuf,
    _library: Option<Library>,
    init: AmiInitFn,
    get_wave: Option<AmiGetWaveFn>,
    close: AmiCloseFn,
}

impl AmiDll {
    /// Opens `path` and resolves the entry points required by `metadata`.
    ///
    /// `AMI_Init` and `AMI_Close` are always required. `AMI_GetWave` is
    /// required only if the parsed AMI metadata declares `GetWave_Exists`.
    pub fn load(
        path: impl AsRef<Path>,
        metadata: &AmiHostMetadata,
    ) -> Result<Self, AmiDllLoadError> {
        let path = path.as_ref().to_path_buf();
        // Loading executes the platform loader; callers choose the vendor file.
        let library =
            unsafe { Library::new(&path) }.map_err(|error| Self::open_error(&path, error))?;
        let init = unsafe { required_symbol(&library, b"AMI_Init\0", "AMI_Init")? };
        let close = unsafe { required_symbol(&library, b"AMI_Close\0", "AMI_Close")? };
        let get_wave = metadata
            .get_wave_exists()
            .then(|| unsafe { required_symbol(&library, b"AMI_GetWave\0", "AMI_GetWave") })
            .transpose()?;

        Ok(Self {
            path,
            _library: Some(library),
            init,
            get_wave,
            close,
        })
    }

    fn open_error(path: &Path, error: libloading::Error) -> AmiDllLoadError {
        AmiDllLoadError::Open {
            path: path.to_path_buf(),
            detail: error.to_string(),
        }
    }

    /// Filesystem location used to open this executable model.
    #[must_use]
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Returns whether this model declared and provided `AMI_GetWave`.
    #[must_use]
    pub const fn has_get_wave(&self) -> bool {
        self.get_wave.is_some()
    }

    #[cfg(test)]
    fn from_functions_for_test(
        init: AmiInitFn,
        get_wave: Option<AmiGetWaveFn>,
        close: AmiCloseFn,
    ) -> Self {
        Self {
            path: PathBuf::from("test-ami.dll"),
            _library: None,
            init,
            get_wave,
            close,
        }
    }
}

/// Owns one AMI model's initialization lifecycle and opaque model memory.
pub struct AmiModel {
    metadata: AmiHostMetadata,
    dll: AmiDll,
    state: AmiModelState,
}

#[derive(Clone, Copy)]
enum AmiModelState {
    Uninitialized,
    Active(*mut c_void),
    Closed,
}

/// Data returned after a successful `AMI_Init` call.
#[derive(Debug, Clone, PartialEq)]
pub struct AmiInitOutcome {
    response: AmiInitResponse,
    parameters_out: Option<String>,
    message: Option<String>,
}

impl AmiInitOutcome {
    /// Typed waveform response validated against the parsed AMI metadata.
    #[must_use]
    pub const fn response(&self) -> &AmiInitResponse {
        &self.response
    }

    /// Optional model-owned parameter tree copied during the call.
    #[must_use]
    pub fn parameters_out(&self) -> Option<&str> {
        self.parameters_out.as_deref()
    }

    /// Optional model-owned diagnostic copied during the call.
    #[must_use]
    pub fn message(&self) -> Option<&str> {
        self.message.as_deref()
    }
}

/// Errors while invoking the AMI initialization lifecycle.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AmiModelError {
    /// `bit_time` was zero, negative, NaN, or infinite.
    InvalidBitTime,
    /// The AMI input parameter tree contained an interior NUL byte.
    ParameterStringContainsNul,
    /// `AMI_Init` may be called only once for a model instance.
    AlreadyInitialized,
    /// `AMI_Close` requires a successful `AMI_Init` first.
    NotInitialized,
    /// The model has already been closed.
    AlreadyClosed,
    /// `AMI_Init` or `AMI_Close` returned a failure status.
    ModelFailure {
        function: &'static str,
        status: c_long,
    },
    /// The returned model string was not valid UTF-8.
    InvalidModelString { field: &'static str },
    /// The clean-room typed response contract rejected the model output.
    Contract(AmiContractError),
}

impl fmt::Display for AmiModelError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidBitTime => {
                write!(formatter, "bit time must be finite and greater than zero")
            }
            Self::ParameterStringContainsNul => {
                write!(
                    formatter,
                    "AMI parameter input must not contain an interior NUL byte"
                )
            }
            Self::AlreadyInitialized => write!(formatter, "AMI model is already initialized"),
            Self::NotInitialized => write!(formatter, "AMI model is not initialized"),
            Self::AlreadyClosed => write!(formatter, "AMI model has already been closed"),
            Self::ModelFailure { function, status } => {
                write!(formatter, "{function} returned failure status {status}")
            }
            Self::InvalidModelString { field } => {
                write!(formatter, "{field} returned a non-UTF-8 string")
            }
            Self::Contract(error) => error.fmt(formatter),
        }
    }
}

impl std::error::Error for AmiModelError {}

/// Creates, invokes, and closes one AMI model instance.
impl AmiModel {
    /// Couples an opened AMI library to the metadata used to resolve it.
    #[must_use]
    pub fn new(dll: AmiDll, metadata: AmiHostMetadata) -> Self {
        Self {
            metadata,
            dll,
            state: AmiModelState::Uninitialized,
        }
    }

    /// Invokes `AMI_Init` for the primary impulse-response column.
    ///
    /// The call copies all model-owned output strings before returning. The
    /// public ABI owns any returned strings and model memory; this host neither
    /// frees those strings nor performs numerical processing on the impulse.
    pub fn initialize(
        &mut self,
        request: &AmiInitRequest,
        bit_time: f64,
        ami_parameters_in: &str,
    ) -> Result<AmiInitOutcome, AmiModelError> {
        if !bit_time.is_finite() || bit_time <= 0.0 {
            return Err(AmiModelError::InvalidBitTime);
        }
        match self.state {
            AmiModelState::Uninitialized => {}
            AmiModelState::Active(_) => return Err(AmiModelError::AlreadyInitialized),
            AmiModelState::Closed => return Err(AmiModelError::AlreadyClosed),
        }

        let parameters_in = CString::new(ami_parameters_in)
            .map_err(|_| AmiModelError::ParameterStringContainsNul)?;
        let mut impulse = request.impulse_response().to_vec();
        let row_size =
            c_long::try_from(impulse.len()).map_err(|_| AmiModelError::ModelFailure {
                function: "AMI_Init",
                status: 0,
            })?;
        let mut parameters_out = std::ptr::null_mut();
        let mut memory = std::ptr::null_mut();
        let mut message = std::ptr::null_mut();
        // The public C ABI requires writable waveform/output pointers for the call.
        let status = unsafe {
            (self.dll.init)(
                impulse.as_mut_ptr(),
                row_size,
                0,
                request.sample_interval(),
                bit_time,
                parameters_in.as_ptr(),
                &mut parameters_out,
                &mut memory,
                &mut message,
            )
        };
        if status != 1 {
            self.close_failed_initialization(memory);
            return Err(AmiModelError::ModelFailure {
                function: "AMI_Init",
                status,
            });
        }

        let outcome = (|| {
            let response =
                AmiInitResponse::new(self.metadata.init_returns_impulse().then_some(impulse));
            validate_init_response(&self.metadata, request, &response)
                .map_err(AmiModelError::Contract)?;
            Ok(AmiInitOutcome {
                response,
                parameters_out: copy_model_string(parameters_out, "AMI_parameters_out")?,
                message: copy_model_string(message, "AMI_Init message")?,
            })
        })();

        match outcome {
            Ok(outcome) => {
                self.state = AmiModelState::Active(memory);
                Ok(outcome)
            }
            Err(error) => {
                self.close_failed_initialization(memory);
                Err(error)
            }
        }
    }

    /// Closes the model's opaque memory once after a successful initialization.
    pub fn close(&mut self) -> Result<(), AmiModelError> {
        let AmiModelState::Active(memory) = self.state else {
            return match self.state {
                AmiModelState::Uninitialized => Err(AmiModelError::NotInitialized),
                AmiModelState::Closed => Err(AmiModelError::AlreadyClosed),
                AmiModelState::Active(_) => unreachable!("active state was matched"),
            };
        };
        let status = unsafe { (self.dll.close)(memory) };
        self.state = AmiModelState::Closed;
        if status == 1 {
            Ok(())
        } else {
            Err(AmiModelError::ModelFailure {
                function: "AMI_Close",
                status,
            })
        }
    }

    fn close_failed_initialization(&mut self, memory: *mut c_void) {
        let _ = unsafe { (self.dll.close)(memory) };
    }
}

impl Drop for AmiModel {
    fn drop(&mut self) {
        if let AmiModelState::Active(memory) = self.state {
            let _ = unsafe { (self.dll.close)(memory) };
        }
    }
}

fn copy_model_string(
    value: *mut c_char,
    field: &'static str,
) -> Result<Option<String>, AmiModelError> {
    if value.is_null() {
        return Ok(None);
    }
    let string = unsafe { CStr::from_ptr(value) }
        .to_str()
        .map_err(|_| AmiModelError::InvalidModelString { field })?;
    Ok(Some(string.to_owned()))
}

unsafe fn required_symbol<T: Copy>(
    library: &Library,
    name: &[u8],
    display_name: &'static str,
) -> Result<T, AmiDllLoadError> {
    let symbol = unsafe { library.get::<T>(name) }.map_err(|error| {
        AmiDllLoadError::MissingRequiredSymbol {
            symbol: display_name,
            detail: error.to_string(),
        }
    })?;
    Ok(*symbol)
}

#[cfg(test)]
mod tests {
    use std::ffi::{c_char, c_long, c_void};

    use crate::ami::{AmiHostMetadata, parse_ami_parameters};
    use crate::contract::AmiInitRequest;

    use super::{
        AmiCloseFn, AmiDll, AmiDllLoadError, AmiGetWaveFn, AmiInitFn, AmiModel, AmiModelError,
    };

    fn metadata(init_returns_impulse: bool, get_wave_exists: bool) -> AmiHostMetadata {
        let tree = parse_ami_parameters(&format!(
            "(AMI_Version (Type String) (Value 7.2))\n(Init_Returns_Impulse (Type Boolean) (Value {init_returns_impulse}))\n(GetWave_Exists (Type Boolean) (Value {get_wave_exists}))"
        ))
        .expect("valid AMI metadata fixture");
        AmiHostMetadata::from_tree(&tree).expect("typed AMI metadata fixture")
    }

    #[cfg(windows)]
    #[test]
    fn opened_non_ami_windows_library_is_rejected_at_required_init_symbol() {
        let Err(error) = AmiDll::load("kernel32.dll", &metadata(false, false)) else {
            panic!("a system library is not an AMI executable model");
        };
        assert!(matches!(
            error,
            AmiDllLoadError::MissingRequiredSymbol {
                symbol: "AMI_Init",
                ..
            }
        ));
    }

    unsafe extern "C" fn fixture_init(
        impulse_matrix: *mut f64,
        row_size: c_long,
        _aggressors: c_long,
        _sample_interval: f64,
        _bit_time: f64,
        _ami_parameters_in: *const c_char,
        _ami_parameters_out: *mut *mut c_char,
        _ami_memory_handle: *mut *mut c_void,
        _message: *mut *mut c_char,
    ) -> c_long {
        let samples = unsafe {
            std::slice::from_raw_parts_mut(
                impulse_matrix,
                usize::try_from(row_size).expect("fixture row count is non-negative"),
            )
        };
        samples[0] = 0.5;
        1
    }

    unsafe extern "C" fn fixture_close(_memory: *mut c_void) -> c_long {
        1
    }

    #[test]
    fn initialization_adapts_the_modified_abi_buffer_and_closes_once() {
        let dll = AmiDll::from_functions_for_test(
            fixture_init as AmiInitFn,
            None::<AmiGetWaveFn>,
            fixture_close as AmiCloseFn,
        );
        let mut model = AmiModel::new(dll, metadata(false, false));
        let request = AmiInitRequest::new(1e-12, vec![0.0, 1.0]).unwrap();

        let outcome = model.initialize(&request, 1e-10, "(root)").unwrap();
        assert_eq!(outcome.response().impulse_response(), None);
        assert_eq!(model.close(), Ok(()));
        assert_eq!(model.close(), Err(AmiModelError::AlreadyClosed));
    }

    #[test]
    fn initialization_rejects_bad_time_and_reentry_before_ffi() {
        let dll = AmiDll::from_functions_for_test(
            fixture_init as AmiInitFn,
            None::<AmiGetWaveFn>,
            fixture_close as AmiCloseFn,
        );
        let mut model = AmiModel::new(dll, metadata(true, false));
        let request = AmiInitRequest::new(1e-12, vec![0.0, 1.0]).unwrap();

        assert_eq!(
            model.initialize(&request, 0.0, "(root)"),
            Err(AmiModelError::InvalidBitTime)
        );
        let outcome = model.initialize(&request, 1e-10, "(root)").unwrap();
        assert_eq!(outcome.response().impulse_response(), Some(&[0.5, 1.0][..]));
        assert_eq!(
            model.initialize(&request, 1e-10, "(root)"),
            Err(AmiModelError::AlreadyInitialized)
        );
    }
}
