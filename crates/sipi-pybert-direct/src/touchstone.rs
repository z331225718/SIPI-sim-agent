//! Bounded, dependency-free Touchstone reader for the legacy S1P/S2P/S4P
//! file branches.
//!
//! PyBERT's normal channel loader uses scikit-rf, but the S2P file itself is
//! portable data. This module only handles the passive file parse and turns
//! S21 into the typed real impulse-response contract; AMI/IBIS DLLs remain an
//! explicit external boundary.

use std::{fs, path::Path};

use num_complex::Complex64;
use thiserror::Error;

use crate::{ChannelResponseV1, Ohms, Seconds, inverse_real_spectrum};

const MAX_TOUCHSTONE_BYTES: u64 = 16 * 1024 * 1024;
const MAX_TOUCHSTONE_FFT: usize = 1 << 18;

#[derive(Debug, Error, PartialEq)]
pub enum TouchstoneError {
    #[error("Touchstone file must be a regular non-symlink file within 16 MiB")]
    InvalidFile,
    #[error("Touchstone file could not be read: {0}")]
    Io(String),
    #[error("Touchstone S2P option line is missing or unsupported")]
    InvalidOptions,
    #[error("Touchstone S2P data rows are invalid: {0}")]
    InvalidData(String),
    #[error("Touchstone S2P response could not be converted to a real impulse: {0}")]
    Signal(String),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum DataFormat {
    RealImag,
    MagnitudeAngle,
    DecibelAngle,
}

/// Parse a Touchstone 2-port S21 response and sample it on the requested time
/// grid. The output samples use V/s, matching `ChannelResponseV1`.
pub fn parse_s2p_response(
    path: &Path,
    sample_interval: Seconds,
    sample_count: usize,
    source_impedance: Ohms,
    load_impedance: Ohms,
) -> Result<ChannelResponseV1, TouchstoneError> {
    if !sample_interval.is_finite_positive()
        || sample_count < 2
        || !source_impedance.is_finite_positive()
        || !load_impedance.is_finite_positive()
    {
        return Err(TouchstoneError::InvalidData(
            "invalid target timebase".into(),
        ));
    }
    let metadata =
        fs::symlink_metadata(path).map_err(|error| TouchstoneError::Io(error.to_string()))?;
    if metadata.file_type().is_symlink()
        || !metadata.is_file()
        || metadata.len() > MAX_TOUCHSTONE_BYTES
    {
        return Err(TouchstoneError::InvalidFile);
    }
    let bytes = fs::read(path).map_err(|error| TouchstoneError::Io(error.to_string()))?;
    let text = std::str::from_utf8(&bytes)
        .map_err(|_| TouchstoneError::InvalidData("file must be UTF-8".into()))?;
    let (frequency_unit, data_format) = parse_options(text)?;
    let mut tokens = Vec::new();
    for line in text.lines() {
        let line = line.split('!').next().unwrap_or("").trim();
        if line.is_empty() || line.starts_with('#') || line.starts_with('[') {
            continue;
        }
        tokens.extend(line.split_whitespace().map(str::to_owned));
    }
    if tokens.is_empty() || tokens.len() % 9 != 0 {
        return Err(TouchstoneError::InvalidData(
            "each S2P row requires frequency plus eight scalar values".into(),
        ));
    }
    let mut samples = Vec::with_capacity(tokens.len() / 9);
    for row in tokens.chunks_exact(9) {
        let frequency = parse_number(&row[0])? * frequency_unit;
        if !frequency.is_finite() || frequency < 0.0 {
            return Err(TouchstoneError::InvalidData(
                "frequency must be finite and non-negative".into(),
            ));
        }
        let s21 = parse_complex(&row[3], &row[4], data_format)?;
        samples.push((frequency, s21));
    }
    if samples.len() < 2 || samples.windows(2).any(|pair| pair[1].0 <= pair[0].0) {
        return Err(TouchstoneError::InvalidData(
            "frequency rows must contain at least two strictly increasing points".into(),
        ));
    }

    let fft_len = next_power_of_two(sample_count.min(MAX_TOUCHSTONE_FFT));
    let nyquist = 0.5 / sample_interval.0;
    let bin_step = 1.0 / (fft_len as f64 * sample_interval.0);
    let bins = fft_len / 2 + 1;
    let mut real = vec![0.0; bins];
    let mut imag = vec![0.0; bins];
    for index in 0..bins {
        let frequency = index as f64 * bin_step;
        if frequency > nyquist {
            break;
        }
        let value = interpolate(&samples, frequency);
        real[index] = value.re;
        imag[index] = value.im;
    }
    let impulse = inverse_real_spectrum(&real, &imag, fft_len)
        .map_err(|error| TouchstoneError::Signal(error.to_string()))?;
    let impulse = impulse
        .into_iter()
        .map(|value| value / sample_interval.0)
        .collect();
    Ok(ChannelResponseV1 {
        sample_interval,
        impulse_response_volts_per_second: impulse,
        source_impedance,
        load_impedance,
    })
}

/// Parse the portable file forms reachable from the legacy channel/CTLE
/// selectors.  S1P/S2P/S4P are passive data files; `.step` and `.impulse`
/// are the two-column response fixtures used by PyBERT's file branches.
/// AMI/IBIS files never enter this parser.
pub fn parse_touchstone_response(
    path: &Path,
    sample_interval: Seconds,
    sample_count: usize,
    source_impedance: Ohms,
    load_impedance: Ohms,
    renumber: bool,
) -> Result<ChannelResponseV1, TouchstoneError> {
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    if matches!(extension.as_str(), "step" | "impulse" | "tim" | "td") {
        return parse_two_column_response(
            path,
            sample_interval,
            sample_count,
            source_impedance,
            load_impedance,
            if extension == "step" {
                Some(true)
            } else if extension == "impulse" {
                Some(false)
            } else {
                None
            },
        );
    }
    let Some(ports) = (match extension.as_str() {
        "s1p" => Some(1),
        "s2p" => Some(2),
        "s4p" => Some(4),
        _ => None,
    }) else {
        return parse_two_column_response(
            path,
            sample_interval,
            sample_count,
            source_impedance,
            load_impedance,
            None,
        );
    };
    // PyBERT's renumber switch is only meaningful for the 4-port mixed-mode
    // conversion.  scikit-rf leaves an S2P's S21 unchanged when it is set.
    if ports == 2 {
        return parse_s2p_response(
            path,
            sample_interval,
            sample_count,
            source_impedance,
            load_impedance,
        );
    }
    parse_network_response(
        path,
        ports,
        sample_interval,
        sample_count,
        source_impedance,
        load_impedance,
        renumber,
    )
}

fn parse_network_response(
    path: &Path,
    ports: usize,
    sample_interval: Seconds,
    sample_count: usize,
    source_impedance: Ohms,
    load_impedance: Ohms,
    renumber: bool,
) -> Result<ChannelResponseV1, TouchstoneError> {
    validate_target(
        sample_interval,
        sample_count,
        source_impedance,
        load_impedance,
    )?;
    let text = read_touchstone_text(path)?;
    let (frequency_unit, data_format) = parse_options(&text)?;
    let row_width = 1 + 2 * ports * ports;
    let mut tokens = Vec::new();
    for line in text.lines() {
        let line = line.split('!').next().unwrap_or("").trim();
        if line.is_empty() || line.starts_with('#') || line.starts_with('[') {
            continue;
        }
        tokens.extend(line.split_whitespace().map(str::to_owned));
    }
    if tokens.is_empty() || tokens.len() % row_width != 0 {
        return Err(TouchstoneError::InvalidData(format!(
            "each S{ports}P row requires {row_width} scalar values"
        )));
    }
    let mut rows = Vec::with_capacity(tokens.len() / row_width);
    for row in tokens.chunks_exact(row_width) {
        let frequency = parse_number(&row[0])? * frequency_unit;
        if !frequency.is_finite() || frequency < 0.0 {
            return Err(TouchstoneError::InvalidData(
                "frequency must be finite and non-negative".into(),
            ));
        }
        let mut matrix = vec![Complex64::new(0.0, 0.0); ports * ports];
        for (index, value) in matrix.iter_mut().enumerate() {
            *value = parse_complex(&row[1 + index * 2], &row[2 + index * 2], data_format)?;
        }
        rows.push((frequency, matrix));
    }
    if rows.len() < 2 || rows.windows(2).any(|pair| pair[1].0 <= pair[0].0) {
        return Err(TouchstoneError::InvalidData(
            "frequency rows must contain at least two strictly increasing points".into(),
        ));
    }
    let renumber_swap = ports == 4
        && renumber
        && rows
            .get(rows.len() / 20)
            .is_some_and(|(_, matrix)| matrix[4].norm() < matrix[8].norm());
    let samples = rows
        .into_iter()
        .map(|(frequency, matrix)| {
            let response = if ports == 1 {
                one_port_transfer(matrix[0])?
            } else {
                let order = if renumber_swap {
                    [0, 2, 1, 3]
                } else {
                    [0, 1, 2, 3]
                };
                let s = |row: usize, col: usize| matrix[order[row] * 4 + order[col]];
                // scikit-rf's se2mm uses input pair (1,3) and output pair
                // (2,4): Sdd21 = 1/2(S21-S23-S41+S43).
                (s(1, 0) - s(1, 2) - s(3, 0) + s(3, 2)) * 0.5
            };
            Ok((frequency, response))
        })
        .collect::<Result<Vec<_>, TouchstoneError>>()?;
    samples_to_response(
        &samples,
        sample_interval,
        sample_count,
        source_impedance,
        load_impedance,
    )
}

fn parse_two_column_response(
    path: &Path,
    sample_interval: Seconds,
    sample_count: usize,
    source_impedance: Ohms,
    load_impedance: Ohms,
    step: Option<bool>,
) -> Result<ChannelResponseV1, TouchstoneError> {
    validate_target(
        sample_interval,
        sample_count,
        source_impedance,
        load_impedance,
    )?;
    let text = read_touchstone_text(path)?;
    let mut samples = Vec::new();
    for line in text.lines() {
        let line = line.split('!').next().unwrap_or("").trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        // ``import_time`` accepts the same lightweight delimiter set as the
        // legacy loader: whitespace, comma, semicolon, or colon.
        let fields = line
            .split(|character: char| {
                character.is_whitespace() || matches!(character, ',' | ';' | ':')
            })
            .filter(|field| !field.is_empty())
            .collect::<Vec<_>>();
        if fields.len() != 2 {
            return Err(TouchstoneError::InvalidData(
                "two-column response rows require time and value".into(),
            ));
        }
        let time = parse_number(fields[0])?;
        let value = parse_number(fields[1])?;
        // A time-domain impulse/step response is allowed to cross zero. Only
        // the time coordinate is constrained to the causal half-line.
        if !time.is_finite() || !value.is_finite() || time < 0.0 {
            return Err(TouchstoneError::InvalidData(
                "two-column response time must be finite and non-negative; value must be finite"
                    .into(),
            ));
        }
        samples.push((time, Complex64::new(value, 0.0)));
    }
    validate_frequency_rows(&samples)?;
    let mut values = (0..sample_count)
        .map(|index| interpolate(&samples, index as f64 * sample_interval.0).re)
        .collect::<Vec<_>>();
    let is_step = step.unwrap_or_else(|| {
        values.last().copied().is_some_and(|last| {
            last > values.iter().copied().fold(f64::NEG_INFINITY, f64::max) / 2.0
        })
    });
    if is_step {
        let mut prior = 0.0;
        for value in &mut values {
            let current = *value;
            *value = (current - prior) / sample_interval.0;
            prior = current;
        }
    } else {
        // ``import_time`` returns impulse samples in V/sample.  The typed
        // channel boundary carries V/s, so convert the direct impulse form
        // before the native projection multiplies by the declared dt.
        for value in &mut values {
            *value /= sample_interval.0;
        }
    }
    Ok(ChannelResponseV1 {
        sample_interval,
        impulse_response_volts_per_second: values,
        source_impedance,
        load_impedance,
    })
}

fn one_port_transfer(s11: Complex64) -> Result<Complex64, TouchstoneError> {
    let magnitude_squared = s11.norm_sqr();
    if !magnitude_squared.is_finite() || magnitude_squared > 1.0 + 1.0e-12 {
        return Err(TouchstoneError::InvalidData(
            "S1P reflection magnitude must not exceed one".into(),
        ));
    }
    let magnitude = (1.0 - magnitude_squared.max(0.0)).sqrt();
    let phase = s11.arg()
        + if s11.arg() < 0.0 {
            std::f64::consts::FRAC_PI_2
        } else if s11.arg() > 0.0 {
            -std::f64::consts::FRAC_PI_2
        } else {
            0.0
        };
    Ok(Complex64::from_polar(magnitude, phase))
}

fn validate_target(
    sample_interval: Seconds,
    sample_count: usize,
    source_impedance: Ohms,
    load_impedance: Ohms,
) -> Result<(), TouchstoneError> {
    if !sample_interval.is_finite_positive()
        || sample_count < 2
        || !source_impedance.is_finite_positive()
        || !load_impedance.is_finite_positive()
    {
        return Err(TouchstoneError::InvalidData(
            "invalid target timebase".into(),
        ));
    }
    Ok(())
}

fn read_touchstone_text(path: &Path) -> Result<String, TouchstoneError> {
    let metadata =
        fs::symlink_metadata(path).map_err(|error| TouchstoneError::Io(error.to_string()))?;
    if metadata.file_type().is_symlink()
        || !metadata.is_file()
        || metadata.len() > MAX_TOUCHSTONE_BYTES
    {
        return Err(TouchstoneError::InvalidFile);
    }
    let bytes = fs::read(path).map_err(|error| TouchstoneError::Io(error.to_string()))?;
    std::str::from_utf8(&bytes)
        .map(str::to_owned)
        .map_err(|_| TouchstoneError::InvalidData("file must be UTF-8".into()))
}

fn validate_frequency_rows(samples: &[(f64, Complex64)]) -> Result<(), TouchstoneError> {
    if samples.len() < 2 || samples.windows(2).any(|pair| pair[1].0 <= pair[0].0) {
        return Err(TouchstoneError::InvalidData(
            "frequency/time rows must contain at least two strictly increasing points".into(),
        ));
    }
    Ok(())
}

fn samples_to_response(
    samples: &[(f64, Complex64)],
    sample_interval: Seconds,
    sample_count: usize,
    source_impedance: Ohms,
    load_impedance: Ohms,
) -> Result<ChannelResponseV1, TouchstoneError> {
    let fft_len = next_power_of_two(sample_count.min(MAX_TOUCHSTONE_FFT));
    let nyquist = 0.5 / sample_interval.0;
    let bin_step = 1.0 / (fft_len as f64 * sample_interval.0);
    let bins = fft_len / 2 + 1;
    let mut real = vec![0.0; bins];
    let mut imag = vec![0.0; bins];
    for index in 0..bins {
        let frequency = index as f64 * bin_step;
        if frequency > nyquist {
            break;
        }
        let value = interpolate(samples, frequency);
        real[index] = value.re;
        imag[index] = value.im;
    }
    let impulse = inverse_real_spectrum(&real, &imag, fft_len)
        .map_err(|error| TouchstoneError::Signal(error.to_string()))?
        .into_iter()
        .map(|value| value / sample_interval.0)
        .collect();
    Ok(ChannelResponseV1 {
        sample_interval,
        impulse_response_volts_per_second: impulse,
        source_impedance,
        load_impedance,
    })
}

fn parse_options(text: &str) -> Result<(f64, DataFormat), TouchstoneError> {
    let line = text
        .lines()
        .map(|line| line.split('!').next().unwrap_or("").trim())
        .find(|line| line.starts_with('#'))
        .ok_or(TouchstoneError::InvalidOptions)?;
    let fields = line[1..].split_whitespace().collect::<Vec<_>>();
    if fields.len() < 3 || !fields[1].eq_ignore_ascii_case("s") {
        return Err(TouchstoneError::InvalidOptions);
    }
    let frequency_unit = match fields[0].to_ascii_lowercase().as_str() {
        "hz" => 1.0,
        "khz" => 1.0e3,
        "mhz" => 1.0e6,
        "ghz" => 1.0e9,
        _ => return Err(TouchstoneError::InvalidOptions),
    };
    let format = match fields[2].to_ascii_lowercase().as_str() {
        "ri" => DataFormat::RealImag,
        "ma" => DataFormat::MagnitudeAngle,
        "db" => DataFormat::DecibelAngle,
        _ => return Err(TouchstoneError::InvalidOptions),
    };
    if let Some(index) = fields
        .iter()
        .position(|field| field.eq_ignore_ascii_case("r"))
    {
        let reference = fields
            .get(index + 1)
            .ok_or(TouchstoneError::InvalidOptions)?
            .parse::<f64>()
            .map_err(|_| TouchstoneError::InvalidOptions)?;
        if !reference.is_finite() || reference <= 0.0 {
            return Err(TouchstoneError::InvalidOptions);
        }
    }
    Ok((frequency_unit, format))
}

fn parse_number(value: &str) -> Result<f64, TouchstoneError> {
    value
        .parse::<f64>()
        .map_err(|_| TouchstoneError::InvalidData(format!("invalid number {value:?}")))
}

fn parse_complex(
    first: &str,
    second: &str,
    format: DataFormat,
) -> Result<Complex64, TouchstoneError> {
    let a = parse_number(first)?;
    let b = parse_number(second)?;
    let value = match format {
        DataFormat::RealImag => Complex64::new(a, b),
        DataFormat::MagnitudeAngle => Complex64::from_polar(a, b.to_radians()),
        DataFormat::DecibelAngle => Complex64::from_polar(10.0_f64.powf(a / 20.0), b.to_radians()),
    };
    if value.re.is_finite() && value.im.is_finite() {
        Ok(value)
    } else {
        Err(TouchstoneError::InvalidData("S21 must be finite".into()))
    }
}

fn interpolate(samples: &[(f64, Complex64)], frequency: f64) -> Complex64 {
    // PyBERT's S21/time interpolation uses zero outside the sampled support
    // (scikit-rf ``fill_value=0``), not endpoint hold extrapolation.
    if frequency < samples[0].0 {
        return Complex64::new(0.0, 0.0);
    }
    if (frequency - samples[0].0).abs() <= f64::EPSILON {
        return samples[0].1;
    }
    let Some(last) = samples.last() else {
        return Complex64::new(0.0, 0.0);
    };
    if frequency >= last.0 {
        return if (frequency - last.0).abs() <= f64::EPSILON {
            last.1
        } else {
            Complex64::new(0.0, 0.0)
        };
    }
    let index = samples.partition_point(|(sample_frequency, _)| *sample_frequency < frequency);
    let (left_frequency, left) = samples[index - 1];
    let (right_frequency, right) = samples[index];
    let ratio = (frequency - left_frequency) / (right_frequency - left_frequency);
    left + (right - left) * ratio
}

fn next_power_of_two(value: usize) -> usize {
    value.next_power_of_two().clamp(2, MAX_TOUCHSTONE_FFT)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn parses_ri_ma_and_db_rows_into_a_bounded_impulse() {
        let path = std::env::temp_dir().join(format!("pb-s2p-{}.s2p", std::process::id()));
        fs::write(
            &path,
            "# GHz S RI R 50\n0 0 0 1 0 0 0 0 0\n1 0 0 0.8 0.1 0 0 0 0\n2 0 0 0.5 0.2 0 0 0 0\n",
        )
        .unwrap();
        let response =
            parse_s2p_response(&path, Seconds(1.0e-12), 64, Ohms(50.0), Ohms(50.0)).unwrap();
        assert_eq!(response.sample_interval, Seconds(1.0e-12));
        assert_eq!(response.impulse_response_volts_per_second.len(), 64);
        assert!(
            response
                .impulse_response_volts_per_second
                .iter()
                .all(|value| value.is_finite())
        );
        fs::write(
            &path,
            "# MHz S MA R 50\n0 0 0 1 0 0 0 0 0\n1000 0 0 0.8 10 0 0 0 0\n2000 0 0 0.5 20 0 0 0 0\n",
        )
        .unwrap();
        assert!(parse_s2p_response(&path, Seconds(1.0e-12), 64, Ohms(50.0), Ohms(50.0)).is_ok());
        fs::write(
            &path,
            "# MHz S DB R 50\n0 -300 0 -0 0 0 0 0 0\n1000 -1 10 -2 10 -2 10 -2 10\n2000 -2 20 -3 20 -3 20 -3 20\n",
        )
        .unwrap();
        assert!(parse_s2p_response(&path, Seconds(1.0e-12), 64, Ohms(50.0), Ohms(50.0)).is_ok());
        let _ = fs::remove_file(path);
    }

    #[test]
    fn parses_s1p_s4p_renumber_and_two_column_responses() {
        let root = std::env::temp_dir().join(format!("pb-touchstone-{}", std::process::id()));
        fs::create_dir_all(&root).unwrap();
        let s1p = root.join("one.s1p");
        fs::write(&s1p, "# GHz S RI R 75\n0 1 0\n1 0.5 0\n").unwrap();
        let response =
            parse_touchstone_response(&s1p, Seconds(1.0e-12), 32, Ohms(50.0), Ohms(50.0), false)
                .unwrap();
        assert_eq!(response.impulse_response_volts_per_second.len(), 32);

        let s4p = root.join("four.s4p");
        let mut row_fields = (0..16).map(|_| "0 0").collect::<Vec<_>>();
        row_fields[4] = "1 0"; // S21, the normal differential through path.
        let row = row_fields.join(" ");
        fs::write(&s4p, format!("# GHz S RI R 50\n0 {row}\n1 {row}\n")).unwrap();
        let four_response =
            parse_touchstone_response(&s4p, Seconds(1.0e-12), 32, Ohms(50.0), Ohms(50.0), true);
        assert!(four_response.is_ok(), "{four_response:?}");
        let four_response = four_response.unwrap();
        assert!(
            four_response
                .impulse_response_volts_per_second
                .iter()
                .any(|value| value.abs() > 0.0)
        );

        // ``renumber`` detects a fixture whose through path is S31 rather than
        // S21, matching PyBERT's one-time S21/S31 comparison.
        row_fields[4] = "0 0";
        row_fields[8] = "1 0"; // S31, the swapped-through fixture.
        let row = row_fields.join(" ");
        fs::write(&s4p, format!("# GHz S RI R 50\n0 {row}\n1 {row}\n")).unwrap();
        let swapped =
            parse_touchstone_response(&s4p, Seconds(1.0e-12), 32, Ohms(50.0), Ohms(50.0), true)
                .unwrap();
        assert!(
            swapped
                .impulse_response_volts_per_second
                .iter()
                .any(|value| value.abs() > 0.0)
        );

        let s2p = root.join("two.s2p");
        fs::write(
            &s2p,
            "# GHz S RI R 50\n0 0 0 1 0 0 0 0 0\n1 0 0 0.5 0 0 0 0 0\n",
        )
        .unwrap();
        let normal =
            parse_touchstone_response(&s2p, Seconds(1.0e-12), 32, Ohms(50.0), Ohms(50.0), false)
                .unwrap();
        let ignored_s2p_renumber =
            parse_touchstone_response(&s2p, Seconds(1.0e-12), 32, Ohms(50.0), Ohms(50.0), true)
                .unwrap();
        assert_eq!(normal, ignored_s2p_renumber);

        let text = root.join("response.txt");
        fs::write(&text, "0 0\n1e-12 1\n2e-12 1\n").unwrap();
        let text_response =
            parse_touchstone_response(&text, Seconds(1.0e-12), 8, Ohms(50.0), Ohms(50.0), false)
                .unwrap();
        assert!(text_response.impulse_response_volts_per_second[1] > 0.0);
        fs::write(&text, "0,0\n1e-12;1\n2e-12:1\n").unwrap();
        assert!(
            parse_touchstone_response(&text, Seconds(1.0e-12), 8, Ohms(50.0), Ohms(50.0), false,)
                .is_ok()
        );

        fs::write(&s1p, "# GHz S RI R 0\n0 1 0\n1 0.5 0\n").unwrap();
        assert!(matches!(
            parse_touchstone_response(&s1p, Seconds(1.0e-12), 32, Ohms(50.0), Ohms(50.0), false),
            Err(TouchstoneError::InvalidOptions)
        ));

        let step = root.join("response.step");
        fs::write(&step, "0 0\n1e-12 1\n2e-12 1\n").unwrap();
        let step_response =
            parse_touchstone_response(&step, Seconds(1.0e-12), 8, Ohms(50.0), Ohms(50.0), false)
                .unwrap();
        assert!(step_response.impulse_response_volts_per_second[1] > 0.0);
        let impulse = root.join("response.impulse");
        fs::write(&impulse, "0 1\n1e-12 0.5\n2e-12 0\n").unwrap();
        let direct_impulse =
            parse_touchstone_response(&impulse, Seconds(1.0e-12), 8, Ohms(50.0), Ohms(50.0), false)
                .unwrap();
        assert!(
            (direct_impulse.impulse_response_volts_per_second[0] * 1.0e-12 - 1.0).abs() < 1.0e-12
        );
        fs::write(&impulse, "0 -1\n1e-12 0.5\n2e-12 -0.25\n").unwrap();
        let signed_impulse =
            parse_touchstone_response(&impulse, Seconds(1.0e-12), 8, Ohms(50.0), Ohms(50.0), false)
                .unwrap();
        assert!(
            signed_impulse
                .impulse_response_volts_per_second
                .iter()
                .any(|value| *value < 0.0)
        );
        let _ = fs::remove_dir_all(root);
    }
}
