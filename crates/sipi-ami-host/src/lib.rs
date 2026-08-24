#![deny(unsafe_op_in_unsafe_fn)]

//! Windows x64 loading and bounded lifecycle mechanics for the standard AMI
//! ABI. It intentionally provides neither AMI parameter semantics nor vendor
//! model behavior.

use std::{
    error::Error,
    ffi::{CString, c_char, c_long, c_void},
    fmt, fs,
    path::Path,
};

use sha2::{Digest, Sha256};
use sipi_ami_text::{
    AmiForwardedParameterSubsetV1, AmiTextBindingV1, ParseLimitsV1, verify_binding_v1,
};

const SUCCESS: c_long = 1;
const IMAGE_FILE_MACHINE_AMD64: u16 = 0x8664;
const MAX_PARAMETERS_OUT_BYTES: usize = 65_536;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct DllSha256V1([u8; 32]);

impl DllSha256V1 {
    pub const fn from_bytes(bytes: [u8; 32]) -> Self {
        Self(bytes)
    }
    pub const fn bytes(self) -> [u8; 32] {
        self.0
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct AmiInitRequestV1 {
    matrix: Vec<f64>,
    rows: usize,
    aggressors: usize,
    sample_interval_s: f64,
    bit_time_s: f64,
}

impl AmiInitRequestV1 {
    pub fn try_new(
        matrix: Vec<f64>,
        rows: usize,
        aggressors: usize,
        sample_interval_s: f64,
        bit_time_s: f64,
    ) -> Result<Self, AmiHostErrorV1> {
        if rows == 0
            || !sample_interval_s.is_finite()
            || sample_interval_s <= 0.0
            || !bit_time_s.is_finite()
            || bit_time_s <= 0.0
            || matrix.iter().any(|v| !v.is_finite())
        {
            return Err(AmiHostErrorV1::InvalidInput);
        }
        let columns = aggressors
            .checked_add(1)
            .ok_or(AmiHostErrorV1::InvalidInput)?;
        if rows.checked_mul(columns) != Some(matrix.len())
            || rows > c_long::MAX as usize
            || aggressors > c_long::MAX as usize
        {
            return Err(AmiHostErrorV1::InvalidInput);
        }
        Ok(Self {
            matrix,
            rows,
            aggressors,
            sample_interval_s,
            bit_time_s,
        })
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct AmiGetWaveRequestV1 {
    waveform: Vec<f64>,
    clock_capacity: usize,
}

impl AmiGetWaveRequestV1 {
    pub fn try_new(waveform: Vec<f64>, clock_capacity: usize) -> Result<Self, AmiHostErrorV1> {
        if waveform.is_empty()
            || waveform.len() > c_long::MAX as usize
            || clock_capacity == 0
            || waveform.iter().any(|v| !v.is_finite())
        {
            return Err(AmiHostErrorV1::InvalidInput);
        }
        Ok(Self {
            waveform,
            clock_capacity,
        })
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct AmiGetWaveResultV1 {
    waveform: Vec<f64>,
    clocks_s: Vec<f64>,
    parameters_out: String,
}
impl AmiGetWaveResultV1 {
    pub fn waveform(&self) -> &[f64] {
        &self.waveform
    }
    pub fn clocks_s(&self) -> &[f64] {
        &self.clocks_s
    }
    pub fn parameters_out(&self) -> &str {
        &self.parameters_out
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AmiHostErrorV1 {
    UnsupportedPlatform,
    DllPathNotAbsolute,
    DllReadFailed,
    HashMismatch,
    NotPeAmd64,
    OpenFailed,
    MissingRequiredExport,
    InvalidInput,
    InvalidParameters,
    InitFailed(c_long),
    GetWaveUnavailable,
    GetWaveFailed(c_long),
    InvalidWaveform(usize),
    InvalidClock(usize),
    ClockSentinelMissing,
    CloseFailed(c_long),
    Closed,
}
impl fmt::Display for AmiHostErrorV1 {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "AMI host error: {self:?}")
    }
}
impl Error for AmiHostErrorV1 {}

type AmiInitFn = unsafe extern "C" fn(
    *mut f64,
    c_long,
    c_long,
    f64,
    f64,
    *mut c_char,
    *mut *mut c_char,
    *mut *mut c_void,
    *mut *mut c_char,
) -> c_long;
type AmiGetWaveFn =
    unsafe extern "C" fn(*mut f64, c_long, *mut f64, *mut *mut c_char, *mut c_void) -> c_long;
type AmiCloseFn = unsafe extern "C" fn(*mut c_void) -> c_long;

pub struct AmiHostV1 {
    module: Module,
    init: AmiInitFn,
    get_wave: Option<AmiGetWaveFn>,
    close: AmiCloseFn,
}

impl AmiHostV1 {
    pub fn open(path: &Path, expected: DllSha256V1) -> Result<Self, AmiHostErrorV1> {
        if !cfg!(all(windows, target_arch = "x86_64")) {
            return Err(AmiHostErrorV1::UnsupportedPlatform);
        }
        if std::mem::size_of::<c_long>() != 4 {
            return Err(AmiHostErrorV1::UnsupportedPlatform);
        }
        if !path.is_absolute() {
            return Err(AmiHostErrorV1::DllPathNotAbsolute);
        }
        let bytes = fs::read(path).map_err(|_| AmiHostErrorV1::DllReadFailed)?;
        if Sha256::digest(&bytes).as_slice() != expected.0 {
            return Err(AmiHostErrorV1::HashMismatch);
        }
        validate_amd64_pe(&bytes)?;
        let module = Module::open(path)?;
        let init = unsafe { module.export::<AmiInitFn>(b"AMI_Init\0")? };
        let close = unsafe { module.export::<AmiCloseFn>(b"AMI_Close\0")? };
        let get_wave = unsafe { module.optional_export::<AmiGetWaveFn>(b"AMI_GetWave\0")? };
        Ok(Self {
            module,
            init,
            get_wave,
            close,
        })
    }

    fn initialize_internal(
        self,
        request: AmiInitRequestV1,
        binding: &AmiTextBindingV1,
        limits: ParseLimitsV1,
        capture_parameters_out: bool,
    ) -> Result<AmiInstanceV1, AmiHostErrorV1> {
        verify_binding_v1(binding.raw().bytes(), binding, limits)
            .map_err(|_| AmiHostErrorV1::InvalidParameters)?;
        let parameters =
            CString::new(binding.raw().bytes()).map_err(|_| AmiHostErrorV1::InvalidParameters)?;
        let mut matrix = request.matrix;
        let mut parameters_out = std::ptr::null_mut();
        let mut handle = std::ptr::null_mut();
        let mut message = std::ptr::null_mut();
        let status = unsafe {
            (self.init)(
                matrix.as_mut_ptr(),
                request.rows as c_long,
                request.aggressors as c_long,
                request.sample_interval_s,
                request.bit_time_s,
                parameters.as_ptr().cast_mut(),
                &mut parameters_out,
                &mut handle,
                &mut message,
            )
        };
        if status != SUCCESS {
            return Err(AmiHostErrorV1::InitFailed(status));
        }
        let parameters_out_text = if capture_parameters_out {
            match copy_parameters_out(parameters_out) {
                Ok(value) => value,
                Err(error) => {
                    let _ = unsafe { (self.close)(handle) };
                    return Err(error);
                }
            }
        } else {
            String::new()
        };
        Ok(AmiInstanceV1 {
            _module: self.module,
            get_wave: self.get_wave,
            close: self.close,
            handle,
            parameters_out: parameters_out_text,
            active: true,
        })
    }

    pub fn initialize(
        self,
        request: AmiInitRequestV1,
        binding: &AmiTextBindingV1,
        limits: ParseLimitsV1,
    ) -> Result<AmiInstanceV1, AmiHostErrorV1> {
        self.initialize_internal(request, binding, limits, false)
    }

    /// Validate an exact typed host-forwarded subset before forwarding the
    /// unchanged raw AMI text.  This proves neither DLL consumption nor
    /// runtime acceptance of any selected value.
    pub fn initialize_forwarded_subset(
        self,
        request: AmiInitRequestV1,
        binding: &AmiTextBindingV1,
        subset: &AmiForwardedParameterSubsetV1,
        limits: ParseLimitsV1,
    ) -> Result<AmiInstanceV1, AmiHostErrorV1> {
        subset
            .verify_binding_v1(binding)
            .map_err(|_| AmiHostErrorV1::InvalidParameters)?;
        self.initialize_internal(request, binding, limits, false)
    }

    /// V2 explicitly opts into the typed InitOut payload.
    pub fn initialize_v2(
        self,
        request: AmiInitRequestV1,
        binding: &AmiTextBindingV1,
        limits: ParseLimitsV1,
    ) -> Result<AmiInstanceV1, AmiHostErrorV1> {
        self.initialize_internal(request, binding, limits, true)
    }

    pub fn initialize_forwarded_subset_v2(
        self,
        request: AmiInitRequestV1,
        binding: &AmiTextBindingV1,
        subset: &AmiForwardedParameterSubsetV1,
        limits: ParseLimitsV1,
    ) -> Result<AmiInstanceV1, AmiHostErrorV1> {
        subset
            .verify_binding_v1(binding)
            .map_err(|_| AmiHostErrorV1::InvalidParameters)?;
        self.initialize_internal(request, binding, limits, true)
    }
}

pub struct AmiInstanceV1 {
    _module: Module,
    get_wave: Option<AmiGetWaveFn>,
    close: AmiCloseFn,
    handle: *mut c_void,
    parameters_out: String,
    active: bool,
}
impl AmiInstanceV1 {
    pub fn init_parameters_out(&self) -> &str {
        &self.parameters_out
    }

    fn get_wave_internal(
        &mut self,
        request: AmiGetWaveRequestV1,
        capture_parameters_out: bool,
    ) -> Result<AmiGetWaveResultV1, AmiHostErrorV1> {
        if !self.active {
            return Err(AmiHostErrorV1::Closed);
        }
        let get_wave = self.get_wave.ok_or(AmiHostErrorV1::GetWaveUnavailable)?;
        let mut waveform = request.waveform;
        let mut clocks = vec![-1.0; request.clock_capacity];
        let mut parameters_out = std::ptr::null_mut();
        let status = unsafe {
            get_wave(
                waveform.as_mut_ptr(),
                waveform.len() as c_long,
                clocks.as_mut_ptr(),
                &mut parameters_out,
                self.handle,
            )
        };
        if status != SUCCESS {
            self.close_after_error();
            return Err(AmiHostErrorV1::GetWaveFailed(status));
        }
        let parameters_out_text = if capture_parameters_out {
            match copy_parameters_out(parameters_out) {
                Ok(value) => value,
                Err(error) => {
                    self.close_after_error();
                    return Err(error);
                }
            }
        } else {
            String::new()
        };
        if let Some((index, _)) = waveform
            .iter()
            .enumerate()
            .find(|(_, value)| !value.is_finite())
        {
            self.close_after_error();
            return Err(AmiHostErrorV1::InvalidWaveform(index));
        }
        let count = match clocks.iter().position(|value| *value == -1.0) {
            Some(count) => count,
            None => {
                self.close_after_error();
                return Err(AmiHostErrorV1::ClockSentinelMissing);
            }
        };
        if let Some((index, _)) = clocks[..count]
            .iter()
            .enumerate()
            .find(|(_, value)| !value.is_finite() || **value < 0.0)
        {
            self.close_after_error();
            return Err(AmiHostErrorV1::InvalidClock(index));
        }
        Ok(AmiGetWaveResultV1 {
            waveform,
            clocks_s: clocks[..count].to_vec(),
            parameters_out: parameters_out_text,
        })
    }

    pub fn get_wave(
        &mut self,
        request: AmiGetWaveRequestV1,
    ) -> Result<AmiGetWaveResultV1, AmiHostErrorV1> {
        self.get_wave_internal(request, false)
    }

    /// V2 explicitly opts into the typed GetWave parameters-out payload.
    pub fn get_wave_v2(
        &mut self,
        request: AmiGetWaveRequestV1,
    ) -> Result<AmiGetWaveResultV1, AmiHostErrorV1> {
        self.get_wave_internal(request, true)
    }
    pub fn close(mut self) -> Result<(), AmiHostErrorV1> {
        self.close_once()
    }
    fn close_after_error(&mut self) {
        let _ = self.close_once();
    }
    fn close_once(&mut self) -> Result<(), AmiHostErrorV1> {
        if !self.active {
            return Err(AmiHostErrorV1::Closed);
        }
        self.active = false;
        let status = unsafe { (self.close)(self.handle) };
        if status == SUCCESS {
            Ok(())
        } else {
            Err(AmiHostErrorV1::CloseFailed(status))
        }
    }
}
impl Drop for AmiInstanceV1 {
    fn drop(&mut self) {
        if self.active {
            let _ = self.close_once();
        }
    }
}

fn copy_parameters_out(pointer: *mut c_char) -> Result<String, AmiHostErrorV1> {
    if pointer.is_null() {
        return Ok(String::new());
    }
    let mut bytes = Vec::new();
    for index in 0..=MAX_PARAMETERS_OUT_BYTES {
        let value = unsafe { pointer.add(index).read() } as u8;
        if value == 0 {
            return String::from_utf8(bytes).map_err(|_| AmiHostErrorV1::InvalidParameters);
        }
        if index == MAX_PARAMETERS_OUT_BYTES {
            return Err(AmiHostErrorV1::InvalidParameters);
        }
        bytes.push(value);
    }
    Err(AmiHostErrorV1::InvalidParameters)
}

fn validate_amd64_pe(bytes: &[u8]) -> Result<(), AmiHostErrorV1> {
    if bytes.len() < 0x40 || &bytes[..2] != b"MZ" {
        return Err(AmiHostErrorV1::NotPeAmd64);
    }
    let offset = u32::from_le_bytes(bytes[0x3c..0x40].try_into().expect("fixed slice")) as usize;
    let machine_end = offset.checked_add(6).ok_or(AmiHostErrorV1::NotPeAmd64)?;
    if bytes.get(offset..offset + 4) != Some(b"PE\0\0") || machine_end > bytes.len() {
        return Err(AmiHostErrorV1::NotPeAmd64);
    }
    let machine = u16::from_le_bytes(
        bytes[offset + 4..machine_end]
            .try_into()
            .expect("fixed slice"),
    );
    if machine != IMAGE_FILE_MACHINE_AMD64 {
        return Err(AmiHostErrorV1::NotPeAmd64);
    }
    Ok(())
}

struct Module {
    #[cfg(windows)]
    handle: *mut c_void,
    #[cfg(not(windows))]
    _path: PathBuf,
}
impl Module {
    fn open(path: &Path) -> Result<Self, AmiHostErrorV1> {
        #[cfg(windows)]
        {
            use std::os::windows::ffi::OsStrExt;
            let wide: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
            let handle = unsafe {
                LoadLibraryExW(
                    wide.as_ptr(),
                    std::ptr::null_mut(),
                    LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_DEFAULT_DIRS,
                )
            };
            if handle.is_null() {
                return Err(AmiHostErrorV1::OpenFailed);
            }
            Ok(Self { handle })
        }
        #[cfg(not(windows))]
        {
            let _ = path;
            Err(AmiHostErrorV1::UnsupportedPlatform)
        }
    }
    unsafe fn export<T: Copy>(&self, name: &[u8]) -> Result<T, AmiHostErrorV1> {
        unsafe { self.optional_export(name)? }.ok_or(AmiHostErrorV1::MissingRequiredExport)
    }
    unsafe fn optional_export<T: Copy>(&self, name: &[u8]) -> Result<Option<T>, AmiHostErrorV1> {
        #[cfg(windows)]
        {
            let pointer = unsafe { GetProcAddress(self.handle, name.as_ptr().cast()) };
            if pointer.is_null() {
                return Ok(None);
            }
            Ok(Some(unsafe { std::mem::transmute_copy(&pointer) }))
        }
        #[cfg(not(windows))]
        {
            let _ = name;
            Err(AmiHostErrorV1::UnsupportedPlatform)
        }
    }
}
impl Drop for Module {
    fn drop(&mut self) {
        #[cfg(windows)]
        unsafe {
            let _ = FreeLibrary(self.handle);
        }
    }
}

#[cfg(windows)]
const LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR: u32 = 0x0000_0100;
#[cfg(windows)]
const LOAD_LIBRARY_SEARCH_DEFAULT_DIRS: u32 = 0x0000_1000;
#[cfg(windows)]
unsafe extern "system" {
    fn LoadLibraryExW(path: *const u16, file: *mut c_void, flags: u32) -> *mut c_void;
    fn GetProcAddress(module: *mut c_void, name: *const c_char) -> *mut c_void;
    fn FreeLibrary(module: *mut c_void) -> i32;
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn validates_amd64_pe_header() {
        let mut bytes = vec![0; 0x80];
        bytes[..2].copy_from_slice(b"MZ");
        bytes[0x3c..0x40].copy_from_slice(&(0x40u32).to_le_bytes());
        bytes[0x40..0x44].copy_from_slice(b"PE\0\0");
        bytes[0x44..0x46].copy_from_slice(&IMAGE_FILE_MACHINE_AMD64.to_le_bytes());
        assert!(validate_amd64_pe(&bytes).is_ok());
        bytes[0x44] = 0x4c;
        assert_eq!(validate_amd64_pe(&bytes), Err(AmiHostErrorV1::NotPeAmd64));
    }
    #[test]
    fn rejects_unbounded_or_invalid_requests() {
        assert!(AmiInitRequestV1::try_new(vec![1.0], 1, 0, 0.0, 1.0).is_err());
        assert!(AmiGetWaveRequestV1::try_new(vec![], 1).is_err());
        assert!(AmiGetWaveRequestV1::try_new(vec![f64::NAN], 1).is_err());
    }
}
