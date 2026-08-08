//! Vendor AMI executable-library discovery through the public C ABI.
//!
//! This module owns the dynamic library and resolves the entry points required
//! by the IBIS AMI executable-model programming guide. It intentionally stops
//! at symbol discovery: a later layer owns parameter strings, model memory,
//! and calls, then adapts their buffers to [`crate::contract`]. No vendor DLL
//! is bundled or certified by this crate.

use std::ffi::{c_char, c_long, c_void};
use std::fmt;
use std::path::{Path, PathBuf};

use libloading::Library;

use crate::ami::AmiHostMetadata;

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
    _library: Library,
    _init: AmiInitFn,
    get_wave: Option<AmiGetWaveFn>,
    _close: AmiCloseFn,
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
            _library: library,
            _init: init,
            get_wave,
            _close: close,
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

#[cfg(all(test, windows))]
mod tests {
    use crate::ami::{AmiHostMetadata, parse_ami_parameters};

    use super::{AmiDll, AmiDllLoadError};

    fn metadata(get_wave_exists: bool) -> AmiHostMetadata {
        let tree = parse_ami_parameters(&format!(
            "(AMI_Version (Type String) (Value 7.2))\n(Init_Returns_Impulse (Type Boolean) (Value false))\n(GetWave_Exists (Type Boolean) (Value {get_wave_exists}))"
        ))
        .expect("valid AMI metadata fixture");
        AmiHostMetadata::from_tree(&tree).expect("typed AMI metadata fixture")
    }

    #[test]
    fn opened_non_ami_windows_library_is_rejected_at_required_init_symbol() {
        let Err(error) = AmiDll::load("kernel32.dll", &metadata(false)) else {
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
}
