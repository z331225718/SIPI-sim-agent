//! Test-only bridge from an external receiver sidecar to the product receiver.
//!
//! This target is deliberately ignored by ordinary test runs and is never a
//! product CLI command.  The external orchestration tool supplies a bounded,
//! hash-checked temporary directory; this test only validates and decodes the
//! two product-neutral sidecars before calling the one receiver implementation.

use std::{
    env,
    error::Error,
    fmt,
    fs::{self, File},
    io::Write,
    path::{Path, PathBuf},
};

use sipi_contracts::{ReceiverInputV1, RxStagesV1, UniformTimebaseV1};
use sipi_link::{
    ReceiverDecisionV1, ReceiverPhaseSelectionV2, ReferenceBitsV1,
    run_fixed_receiver_delegated_ambiguity_v2, run_fixed_receiver_v1,
};
use sipi_types::{Seconds, Volts};

const WAVEFORM_BYTES: usize = 1024 * size_of::<f64>();
const BIT_COUNT: usize = 128;
const RESULT_SCHEMA: &str = "sipi.receiver-observer-runner.v1";
const DELEGATED_RESULT_SCHEMA: &str = "sipi.receiver-delegated-policy-observer-runner.v1";

#[derive(Debug)]
struct RunnerError(&'static str);

impl fmt::Display for RunnerError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str(self.0)
    }
}

impl Error for RunnerError {}

fn contained_existing(root: &Path, candidate: &Path) -> Result<PathBuf, RunnerError> {
    let root = root
        .canonicalize()
        .map_err(|_| RunnerError("sidecar root is unavailable"))?;
    let candidate = candidate
        .canonicalize()
        .map_err(|_| RunnerError("sidecar file is unavailable"))?;
    candidate
        .starts_with(&root)
        .then_some(candidate)
        .ok_or(RunnerError("sidecar escapes the controlled root"))
}

fn contained_new(root: &Path, candidate: &Path) -> Result<PathBuf, RunnerError> {
    if candidate.exists() {
        return Err(RunnerError("result path must not already exist"));
    }
    let root = root
        .canonicalize()
        .map_err(|_| RunnerError("sidecar root is unavailable"))?;
    let parent = candidate
        .parent()
        .ok_or(RunnerError("result path has no parent"))?
        .canonicalize()
        .map_err(|_| RunnerError("result parent is unavailable"))?;
    parent
        .starts_with(&root)
        .then_some(
            parent.join(
                candidate
                    .file_name()
                    .ok_or(RunnerError("invalid result name"))?,
            ),
        )
        .ok_or(RunnerError("result escapes the controlled root"))
}

fn load_input(
    root: &Path,
    waveform: &Path,
    bits: &Path,
) -> Result<(ReceiverInputV1, ReferenceBitsV1), RunnerError> {
    let waveform = fs::read(contained_existing(root, waveform)?)
        .map_err(|_| RunnerError("waveform read failed"))?;
    if waveform.len() != WAVEFORM_BYTES {
        return Err(RunnerError("waveform sidecar length is invalid"));
    }
    let mut samples = Vec::with_capacity(1024);
    for encoded in waveform.chunks_exact(size_of::<f64>()) {
        let value = f64::from_le_bytes(
            encoded
                .try_into()
                .map_err(|_| RunnerError("waveform decode failed"))?,
        );
        samples.push(
            Volts::try_new(value)
                .map_err(|_| RunnerError("waveform contains non-finite sample"))?,
        );
    }

    let bits = fs::read(contained_existing(root, bits)?)
        .map_err(|_| RunnerError("bit sidecar read failed"))?;
    if bits.len() != BIT_COUNT || !bits.iter().all(|bit| matches!(bit, 0 | 1)) {
        return Err(RunnerError("reference-bit sidecar is invalid"));
    }
    let input = ReceiverInputV1::try_new(
        UniformTimebaseV1::try_new(
            Seconds::try_new(0.0).map_err(|_| RunnerError("invalid receiver start"))?,
            Seconds::try_new(1.0e-12).map_err(|_| RunnerError("invalid receiver interval"))?,
            1024,
        )
        .map_err(|_| RunnerError("receiver timebase rejected"))?,
        samples,
        8,
        RxStagesV1::bypass(),
    )
    .map_err(|_| RunnerError("receiver input rejected"))?;
    let reference = ReferenceBitsV1::try_new(bits.into_iter().map(|bit| bit == 1).collect())
        .map_err(|_| RunnerError("reference bits rejected"))?;
    Ok((input, reference))
}

fn decision_code(decision: ReceiverDecisionV1) -> char {
    match decision {
        ReceiverDecisionV1::Positive => '+',
        ReceiverDecisionV1::Negative => '-',
        ReceiverDecisionV1::Erasure => '0',
    }
}

fn replay(root: &Path, waveform: &Path, bits: &Path, output: &Path) -> Result<(), Box<dyn Error>> {
    let (input, reference) = load_input(root, waveform, bits)?;
    let result = run_fixed_receiver_v1(&input, &reference)?;
    let output = contained_new(root, output)?;
    let mut file = File::create_new(output)?;
    let decisions = result
        .decisions()
        .iter()
        .copied()
        .map(decision_code)
        .collect::<String>();
    write!(
        file,
        concat!(
            "{{\"schema\":\"{}\",\"phase\":{},\"locked\":true,",
            "\"centerVolts\":{},\"amplitudeVolts\":{},\"frozenTaps\":[{},{},{},{},{}],",
            "\"decisions\":\"{}\",\"errorCount\":{},\"berNumerator\":{},\"berDenominator\":{}}}\n"
        ),
        RESULT_SCHEMA,
        result.phase(),
        result.center().get(),
        result.amplitude().get(),
        result.frozen_taps()[0].get(),
        result.frozen_taps()[1].get(),
        result.frozen_taps()[2].get(),
        result.frozen_taps()[3].get(),
        result.frozen_taps()[4].get(),
        decisions,
        result.error_count(),
        result.error_count(),
        result.ber_denominator(),
    )?;
    file.sync_all()?;
    Ok(())
}

fn replay_or_record_rejection(
    root: &Path,
    waveform: &Path,
    bits: &Path,
    output: &Path,
) -> Result<(), Box<dyn Error>> {
    let (input, reference) = load_input(root, waveform, bits)?;
    let output = contained_new(root, output)?;
    let mut file = File::create_new(output)?;
    match run_fixed_receiver_v1(&input, &reference) {
        Ok(result) => {
            let decisions = result
                .decisions()
                .iter()
                .copied()
                .map(decision_code)
                .collect::<String>();
            write!(
                file,
                concat!(
                    "{{\"schema\":\"{}\",\"status\":\"accepted\",\"phase\":{},\"locked\":true,",
                    "\"centerVolts\":{},\"amplitudeVolts\":{},\"frozenTaps\":[{},{},{},{},{}],",
                    "\"decisions\":\"{}\",\"errorCount\":{},\"berNumerator\":{},\"berDenominator\":{}}}\n"
                ),
                RESULT_SCHEMA,
                result.phase(),
                result.center().get(),
                result.amplitude().get(),
                result.frozen_taps()[0].get(),
                result.frozen_taps()[1].get(),
                result.frozen_taps()[2].get(),
                result.frozen_taps()[3].get(),
                result.frozen_taps()[4].get(),
                decisions,
                result.error_count(),
                result.error_count(),
                result.ber_denominator(),
            )?;
        }
        Err(error) => {
            writeln!(
                file,
                "{{\"schema\":\"{}\",\"status\":\"rejected\",\"reason\":\"{:?}\"}}",
                RESULT_SCHEMA, error
            )?;
        }
    }
    file.sync_all()?;
    Ok(())
}

fn delegated_selection_code(selection: ReceiverPhaseSelectionV2) -> (&'static str, &'static str) {
    match selection {
        ReceiverPhaseSelectionV2::UniqueLocked => ("unique_locked", "locked"),
        ReceiverPhaseSelectionV2::DelegatedAmbiguousTieBreak => (
            "delegated_ambiguous_tie_break",
            "policy_selected_not_locked",
        ),
    }
}

fn replay_delegated_policy_or_record_rejection(
    root: &Path,
    waveform: &Path,
    bits: &Path,
    output: &Path,
) -> Result<(), Box<dyn Error>> {
    let (input, reference) = load_input(root, waveform, bits)?;
    let output = contained_new(root, output)?;
    let mut file = File::create_new(output)?;
    match run_fixed_receiver_delegated_ambiguity_v2(&input, &reference) {
        Ok(result) => {
            let decisions = result
                .decisions()
                .iter()
                .copied()
                .map(decision_code)
                .collect::<String>();
            let (phase_selection, cdr_lock_state) =
                delegated_selection_code(result.phase_selection());
            write!(
                file,
                concat!(
                    "{{\"schema\":\"{}\",\"status\":\"accepted\",\"phase\":{},",
                    "\"phaseSelection\":\"{}\",\"cdrLockState\":\"{}\",",
                    "\"centerVolts\":{},\"amplitudeVolts\":{},\"frozenTaps\":[{},{},{},{},{}],",
                    "\"decisions\":\"{}\",\"errorCount\":{},\"berNumerator\":{},\"berDenominator\":{}}}\n"
                ),
                DELEGATED_RESULT_SCHEMA,
                result.phase(),
                phase_selection,
                cdr_lock_state,
                result.center().get(),
                result.amplitude().get(),
                result.frozen_taps()[0].get(),
                result.frozen_taps()[1].get(),
                result.frozen_taps()[2].get(),
                result.frozen_taps()[3].get(),
                result.frozen_taps()[4].get(),
                decisions,
                result.error_count(),
                result.error_count(),
                result.ber_denominator(),
            )?;
        }
        Err(error) => {
            writeln!(
                file,
                "{{\"schema\":\"{}\",\"status\":\"rejected\",\"reason\":\"{:?}\"}}",
                DELEGATED_RESULT_SCHEMA, error
            )?;
        }
    }
    file.sync_all()?;
    Ok(())
}

fn validate_input(
    root: &Path,
    waveform: &Path,
    bits: &Path,
    output: &Path,
) -> Result<(), Box<dyn Error>> {
    let (input, reference) = load_input(root, waveform, bits)?;
    let output = contained_new(root, output)?;
    let mut file = File::create_new(output)?;
    writeln!(
        file,
        "{{\"schema\":\"sipi.receiver-input-observer-runner.v1\",\"sampleCount\":{},\"sampleIntervalSeconds\":{},\"samplesPerUi\":{},\"referenceBitCount\":{}}}",
        input.receive().len(),
        input.timebase().sample_interval().get(),
        input.samples_per_ui().get(),
        reference.bits().len(),
    )?;
    file.sync_all()?;
    Ok(())
}

fn environment_path(name: &str) -> Result<PathBuf, RunnerError> {
    env::var_os(name)
        .map(PathBuf::from)
        .ok_or(RunnerError("required observer environment is absent"))
}

#[test]
#[ignore = "external observer orchestration supplies hash-checked sidecars"]
fn replay_receiver_input() {
    let root = environment_path("SIPI_RECEIVER_HANDOFF_ROOT").unwrap();
    let waveform = environment_path("SIPI_RECEIVER_HANDOFF_WAVEFORM").unwrap();
    let bits = environment_path("SIPI_RECEIVER_HANDOFF_BITS").unwrap();
    let output = environment_path("SIPI_RECEIVER_HANDOFF_OUTPUT").unwrap();
    replay_or_record_rejection(&root, &waveform, &bits, &output).unwrap();
}

#[test]
#[ignore = "external observer orchestration supplies hash-checked sidecars"]
fn replay_receiver_delegated_policy_input() {
    let root = environment_path("SIPI_RECEIVER_HANDOFF_ROOT").unwrap();
    let waveform = environment_path("SIPI_RECEIVER_HANDOFF_WAVEFORM").unwrap();
    let bits = environment_path("SIPI_RECEIVER_HANDOFF_BITS").unwrap();
    let output = environment_path("SIPI_RECEIVER_HANDOFF_OUTPUT").unwrap();
    replay_delegated_policy_or_record_rejection(&root, &waveform, &bits, &output).unwrap();
}

#[test]
#[ignore = "external observer orchestration supplies hash-checked sidecars"]
fn validate_receiver_input() {
    let root = environment_path("SIPI_RECEIVER_HANDOFF_ROOT").unwrap();
    let waveform = environment_path("SIPI_RECEIVER_HANDOFF_WAVEFORM").unwrap();
    let bits = environment_path("SIPI_RECEIVER_HANDOFF_BITS").unwrap();
    let output = environment_path("SIPI_RECEIVER_HANDOFF_OUTPUT").unwrap();
    validate_input(&root, &waveform, &bits, &output).unwrap();
}

#[cfg(test)]
mod tests {
    use super::*;

    fn root(name: &str) -> PathBuf {
        let root = env::temp_dir().join(format!(
            "sipi-receiver-runner-{name}-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        root
    }

    fn write_sidecars(root: &Path) -> (PathBuf, PathBuf) {
        let waveform = root.join("waveform.f64le");
        let mut bytes = Vec::with_capacity(WAVEFORM_BYTES);
        for index in 0..1024 {
            let symbol: f64 = if (index / 8) % 2 == 0 { 1.0 } else { -1.0 };
            let sample: f64 = if index % 8 == 3 { symbol } else { 0.0 };
            bytes.extend_from_slice(&sample.to_le_bytes());
        }
        fs::write(&waveform, bytes).unwrap();
        let bits = root.join("reference.bits");
        fs::write(
            &bits,
            (0..128)
                .map(|index| if index % 2 == 0 { 1 } else { 0 })
                .collect::<Vec<_>>(),
        )
        .unwrap();
        (waveform, bits)
    }

    #[test]
    fn product_owned_sidecars_replay_without_external_oracle() {
        let root = root("valid");
        let (waveform, bits) = write_sidecars(&root);
        let output = root.join("receiver-result.json");
        replay(&root, &waveform, &bits, &output).unwrap();
        let result = fs::read_to_string(&output).unwrap();
        assert!(result.contains(RESULT_SCHEMA));
        assert!(result.contains("\"phase\":3"));
        assert!(result.contains("\"berDenominator\":96"));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn delegated_policy_runner_emits_its_non_lock_selection_state() {
        let root = root("delegated");
        let (waveform, bits) = write_sidecars(&root);
        let output = root.join("receiver-delegated-result.json");
        replay_delegated_policy_or_record_rejection(&root, &waveform, &bits, &output).unwrap();
        let result = fs::read_to_string(&output).unwrap();
        assert!(result.contains(DELEGATED_RESULT_SCHEMA));
        assert!(result.contains("\"phaseSelection\":\"unique_locked\""));
        assert!(result.contains("\"cdrLockState\":\"locked\""));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn product_owned_sidecars_validate_the_receiver_input_boundary() {
        let root = root("input");
        let (waveform, bits) = write_sidecars(&root);
        let output = root.join("receiver-input.json");
        validate_input(&root, &waveform, &bits, &output).unwrap();
        let result = fs::read_to_string(&output).unwrap();
        assert!(result.contains("sipi.receiver-input-observer-runner.v1"));
        assert!(result.contains("\"sampleCount\":1024"));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn malformed_sidecars_and_output_escape_are_rejected() {
        let root = root("invalid");
        let (waveform, bits) = write_sidecars(&root);
        fs::write(&waveform, [0_u8; 8]).unwrap();
        assert!(load_input(&root, &waveform, &bits).is_err());
        let (_, bits) = write_sidecars(&root);
        fs::write(&bits, [2_u8; BIT_COUNT]).unwrap();
        assert!(load_input(&root, &waveform, &bits).is_err());
        assert!(contained_new(&root, &env::temp_dir().join("outside.json")).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
