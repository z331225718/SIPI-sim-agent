#![cfg(windows)]

use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};

use sha2::{Digest, Sha256};
use sipi_ami_host::{
    AmiGetWaveRequestV1, AmiHostErrorV1, AmiHostV1, AmiInitRequestV1, DllSha256V1,
};
use sipi_ami_text::{ParseLimitsV1, parse_and_bind_v1};

fn limits() -> ParseLimitsV1 {
    ParseLimitsV1::try_new(128, 4, 16, 32).expect("limits")
}

fn binding(mode: &str) -> sipi_ami_text::AmiTextBindingV1 {
    parse_and_bind_v1(format!("(mode {mode})").as_bytes(), limits()).expect("binding")
}

fn hash(path: &Path) -> DllSha256V1 {
    DllSha256V1::from_bytes(Sha256::digest(fs::read(path).expect("dll")).into())
}

fn close_marker(handle: usize) -> PathBuf {
    std::env::temp_dir().join(format!(
        "sipi-ami-host-close-{}-{handle}",
        std::process::id()
    ))
}

fn request() -> AmiInitRequestV1 {
    AmiInitRequestV1::try_new(vec![0.0, 1.0], 2, 0, 1e-12, 8e-12).expect("request")
}

fn build_mock(name: &str, exports: bool) -> PathBuf {
    let root =
        std::env::temp_dir().join(format!("sipi-ami-host-mock-{}-{name}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).expect("root");
    let source = if exports {
        MOCK_SOURCE
    } else {
        MISSING_CLOSE_SOURCE
    };
    let source_path = root.join("mock.rs");
    fs::write(&source_path, source).expect("source");
    let dll = root.join("mock.dll");
    let rustc = std::env::var("RUSTC").unwrap_or_else(|_| "rustc".into());
    let status = Command::new(rustc)
        .args(["--crate-type", "cdylib", "--edition", "2024"])
        .arg(&source_path)
        .arg("-o")
        .arg(&dll)
        .status()
        .expect("run rustc");
    assert!(status.success(), "compile mock DLL");
    dll
}

#[test]
fn validates_mock_lifecycle_failure_and_loader_gates() {
    let dll = build_mock("full", true);
    let expected = hash(&dll);
    let mut instance = AmiHostV1::open(&dll, expected)
        .expect("open")
        .initialize_v2(request(), &binding("success"), limits())
        .expect("init");
    assert_eq!(instance.init_parameters_out(), "init-out");
    let result = instance
        .get_wave_v2(AmiGetWaveRequestV1::try_new(vec![0.0, 0.0], 4).expect("wave request"))
        .expect("get wave");
    assert_eq!(result.waveform(), &[7.0, 8.0]);
    assert_eq!(result.clocks_s(), &[1e-12]);
    assert_eq!(result.parameters_out(), "getwave-out");
    instance.close().expect("close");

    assert!(matches!(
        AmiHostV1::open(&dll, DllSha256V1::from_bytes([0; 32])),
        Err(AmiHostErrorV1::HashMismatch)
    ));
    assert!(matches!(
        AmiHostV1::open(Path::new("mock.dll"), expected),
        Err(AmiHostErrorV1::DllPathNotAbsolute)
    ));
    assert!(matches!(
        AmiHostV1::open(&dll, expected).expect("open").initialize(
            request(),
            &binding("init_fail"),
            limits()
        ),
        Err(AmiHostErrorV1::InitFailed(0))
    ));
    let mut failing = AmiHostV1::open(&dll, expected)
        .expect("open")
        .initialize(request(), &binding("getwave_fail"), limits())
        .expect("init");
    assert_eq!(
        failing
            .get_wave(AmiGetWaveRequestV1::try_new(vec![0.0], 2).expect("wave request"))
            .expect_err("get wave failure"),
        AmiHostErrorV1::GetWaveFailed(0)
    );
    assert_eq!(
        failing
            .get_wave(AmiGetWaveRequestV1::try_new(vec![0.0], 2).expect("wave request"))
            .expect_err("closed after failure"),
        AmiHostErrorV1::Closed
    );
    let mut bad_clock = AmiHostV1::open(&dll, expected)
        .expect("open")
        .initialize(request(), &binding("bad_clock"), limits())
        .expect("init");
    assert_eq!(
        bad_clock
            .get_wave(AmiGetWaveRequestV1::try_new(vec![0.0], 2).expect("wave request"))
            .expect_err("clock failure"),
        AmiHostErrorV1::InvalidClock(0)
    );
    let mut bad_wave = AmiHostV1::open(&dll, expected)
        .expect("open")
        .initialize(request(), &binding("bad_wave"), limits())
        .expect("init");
    assert_eq!(
        bad_wave
            .get_wave(AmiGetWaveRequestV1::try_new(vec![0.0], 2).expect("wave request"))
            .expect_err("wave failure"),
        AmiHostErrorV1::InvalidWaveform(0)
    );
    let mut no_sentinel = AmiHostV1::open(&dll, expected)
        .expect("open")
        .initialize(request(), &binding("no_sentinel"), limits())
        .expect("init");
    assert_eq!(
        no_sentinel
            .get_wave(AmiGetWaveRequestV1::try_new(vec![0.0], 2).expect("wave request"))
            .expect_err("sentinel failure"),
        AmiHostErrorV1::ClockSentinelMissing
    );
    let close_failure = AmiHostV1::open(&dll, expected)
        .expect("open")
        .initialize(request(), &binding("close_fail"), limits())
        .expect("init");
    assert_eq!(
        close_failure.close().expect_err("close failure"),
        AmiHostErrorV1::CloseFailed(0)
    );

    let missing = build_mock("missing", false);
    assert!(matches!(
        AmiHostV1::open(&missing, hash(&missing)),
        Err(AmiHostErrorV1::MissingRequiredExport)
    ));
}

#[test]
fn v1_ignores_invalid_or_oversize_init_out_while_v2_closes_and_rejects() {
    let dll = build_mock("out-contract", true);
    let expected = hash(&dll);
    for mode in ["invalid_out", "oversize_out"] {
        let handle = if mode == "invalid_out" { 7 } else { 10 };
        let marker = close_marker(handle);
        let _ = fs::remove_file(&marker);
        let v1 = AmiHostV1::open(&dll, expected)
            .expect("open")
            .initialize(request(), &binding(mode), limits())
            .expect("V1 ignores InitOut");
        assert_eq!(v1.init_parameters_out(), "");
        v1.close().expect("V1 close");
        let _ = fs::remove_file(&marker);
        let result = AmiHostV1::open(&dll, expected)
            .expect("open")
            .initialize_v2(request(), &binding(mode), limits());
        assert!(matches!(result, Err(AmiHostErrorV1::InvalidParameters)));
        assert_eq!(fs::read(&marker).expect("V2 close marker").len(), 1);
        let _ = fs::remove_file(marker);
    }
}

#[test]
fn v1_ignores_invalid_or_oversize_getwave_out_while_v2_closes_and_rejects() {
    let dll = build_mock("getwave-out-contract", true);
    let expected = hash(&dll);
    for mode in ["getwave_invalid_out", "getwave_oversize_out"] {
        let handle = if mode == "getwave_invalid_out" { 8 } else { 9 };
        let marker = close_marker(handle);
        let _ = fs::remove_file(&marker);
        let mut v1 = AmiHostV1::open(&dll, expected)
            .expect("open")
            .initialize(request(), &binding(mode), limits())
            .expect("V1 init");
        let result = v1
            .get_wave(AmiGetWaveRequestV1::try_new(vec![0.0, 0.0], 4).expect("wave request"))
            .expect("V1 ignores GetWave output");
        assert_eq!(result.parameters_out(), "");
        v1.close().expect("V1 close");
        let _ = fs::remove_file(&marker);
        let mut v2 = AmiHostV1::open(&dll, expected)
            .expect("open")
            .initialize(request(), &binding(mode), limits())
            .expect("V2 init");
        assert!(matches!(
            v2.get_wave_v2(AmiGetWaveRequestV1::try_new(vec![0.0, 0.0], 4).expect("wave request")),
            Err(AmiHostErrorV1::InvalidParameters)
        ));
        assert_eq!(fs::read(&marker).expect("V2 close marker").len(), 1);
        assert!(matches!(
            v2.get_wave(AmiGetWaveRequestV1::try_new(vec![0.0, 0.0], 4).expect("closed request")),
            Err(AmiHostErrorV1::Closed)
        ));
        assert_eq!(fs::read(&marker).expect("close marker").len(), 1);
        let _ = fs::remove_file(marker);
    }
}

const MOCK_SOURCE: &str = r#"
#![allow(unsafe_op_in_unsafe_fn)]
use std::ffi::{c_char, c_long, c_void, CStr};
use std::io::Write;
static INIT_OUT: &[u8] = b"init-out\0";
static GETWAVE_OUT: &[u8] = b"getwave-out\0";
static INVALID_OUT: &[u8] = &[0xff, 0x00];
static OVERSIZE_OUT: [u8; 65538] = [b'x'; 65538];
fn mode(parameters: *const c_char, value: &str) -> bool { unsafe { CStr::from_ptr(parameters).to_bytes().windows(value.len()).any(|w| w == value.as_bytes()) } }
#[unsafe(no_mangle)]
pub unsafe extern "C" fn AMI_Init(matrix: *mut f64, _rows: c_long, _aggressors: c_long, _dt: f64, _bit: f64, parameters: *mut c_char, out: *mut *mut c_char, handle: *mut *mut c_void, _message: *mut *mut c_char) -> c_long {
    if mode(parameters, "init_fail") { return 0; }
    *matrix = 42.0;
    *out = if mode(parameters, "getwave_invalid_out") || mode(parameters, "getwave_oversize_out") { INIT_OUT.as_ptr() } else if mode(parameters, "invalid_out") { INVALID_OUT.as_ptr() } else if mode(parameters, "oversize_out") { OVERSIZE_OUT.as_ptr() } else { INIT_OUT.as_ptr() } as *mut c_char;
    *handle = if mode(parameters, "getwave_fail") { 2usize as *mut c_void } else if mode(parameters, "bad_clock") { 3usize as *mut c_void } else if mode(parameters, "close_fail") { 4usize as *mut c_void } else if mode(parameters, "bad_wave") { 5usize as *mut c_void } else if mode(parameters, "no_sentinel") { 6usize as *mut c_void } else if mode(parameters, "getwave_invalid_out") { 8usize as *mut c_void } else if mode(parameters, "getwave_oversize_out") { 9usize as *mut c_void } else if mode(parameters, "invalid_out") { 7usize as *mut c_void } else if mode(parameters, "oversize_out") { 10usize as *mut c_void } else { 1usize as *mut c_void };
    1
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn AMI_GetWave(wave: *mut f64, size: c_long, clocks: *mut f64, out: *mut *mut c_char, handle: *mut c_void) -> c_long {
    if handle as usize == 2 { return 0; }
    *out = if handle as usize == 8 { INVALID_OUT.as_ptr() } else if handle as usize == 9 { OVERSIZE_OUT.as_ptr() } else { GETWAVE_OUT.as_ptr() } as *mut c_char;
    if size > 0 { *wave = if handle as usize == 5 { f64::NAN } else { 7.0 }; }
    if size > 1 { *wave.add(1) = 8.0; }
    *clocks = if handle as usize == 3 { -2.0 } else { 1e-12 };
    *clocks.add(1) = if handle as usize == 6 { 0.0 } else { -1.0 };
    1
}
#[unsafe(no_mangle)]
pub unsafe extern "C" fn AMI_Close(handle: *mut c_void) -> c_long {
    let marker = std::env::temp_dir().join(format!("sipi-ami-host-close-{}-{}", std::process::id(), handle as usize));
    if let Ok(mut file) = std::fs::OpenOptions::new().create(true).append(true).open(marker) { let _ = file.write_all(b"x"); }
    if handle as usize == 4 { 0 } else { 1 }
}
"#;

const MISSING_CLOSE_SOURCE: &str = r#"
#![allow(unsafe_op_in_unsafe_fn)]
use std::ffi::{c_char, c_long, c_void};
#[unsafe(no_mangle)]
pub unsafe extern "C" fn AMI_Init(_matrix: *mut f64, _rows: c_long, _aggressors: c_long, _dt: f64, _bit: f64, _parameters: *mut c_char, _out: *mut *mut c_char, _handle: *mut *mut c_void, _message: *mut *mut c_char) -> c_long { 1 }
"#;
