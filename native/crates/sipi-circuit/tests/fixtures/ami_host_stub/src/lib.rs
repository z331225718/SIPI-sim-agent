use std::ffi::{c_char, c_long, c_void};

static PARAMETERS_OUT: &[u8] = b"(stub_parameters)\0";
static INIT_MESSAGE: &[u8] = b"stub init\0";

#[unsafe(no_mangle)]
pub unsafe extern "C" fn AMI_Init(
    impulse_matrix: *mut f64,
    row_size: c_long,
    _aggressors: c_long,
    _sample_interval: f64,
    _bit_time: f64,
    _ami_parameters_in: *const c_char,
    ami_parameters_out: *mut *mut c_char,
    ami_memory_handle: *mut *mut c_void,
    message: *mut *mut c_char,
) -> c_long {
    if row_size <= 0 {
        return 0;
    }
    let samples = unsafe {
        std::slice::from_raw_parts_mut(
            impulse_matrix,
            usize::try_from(row_size).expect("positive row size"),
        )
    };
    samples[0] = 0.5;
    unsafe {
        *ami_parameters_out = PARAMETERS_OUT.as_ptr().cast_mut().cast();
        *ami_memory_handle = std::ptr::dangling_mut::<c_void>();
        *message = INIT_MESSAGE.as_ptr().cast_mut().cast();
    }
    1
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn AMI_GetWave(
    wave: *mut f64,
    wave_size: c_long,
    clock_times: *mut f64,
    ami_parameters_out: *mut *mut c_char,
    _ami_memory: *mut c_void,
) -> c_long {
    if wave_size <= 0 {
        return 0;
    }
    let waveform = unsafe {
        std::slice::from_raw_parts_mut(wave, usize::try_from(wave_size).expect("positive size"))
    };
    waveform[0] = 0.25;
    unsafe {
        *clock_times = 2e-12;
        *clock_times.add(1) = -1.0;
        *ami_parameters_out = PARAMETERS_OUT.as_ptr().cast_mut().cast();
    }
    1
}

#[unsafe(no_mangle)]
pub unsafe extern "C" fn AMI_Close(_ami_memory: *mut c_void) -> c_long {
    if std::env::var_os("AMI_HOST_STUB_CLOSE_FAIL").is_some() {
        0
    } else {
        1
    }
}
