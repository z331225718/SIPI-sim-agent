use std::collections::{BTreeMap, HashMap};
use std::f64::consts::PI;
use std::time::{Duration, Instant};

use faer::c64;
use faer::sparse::Triplet;

use crate::error::{Error, Result};
use crate::expression;
use crate::netlist::{
    AcScale, Analysis, Deck, Element, IntegrationMethod, MeasurementEvent,
    MeasurementEventDirection, MeasurementEventOccurrence, MeasurementOperation,
    MeasurementQuantity, MeasurementTarget, MeasurementTrigger, Node, Waveform,
};
use crate::result::{
    ComplexSample, MeasurementResult, SimulationPoint, SimulationResult, SimulationStatistics,
};
use crate::rfm::{RfmModel, RfmState};
use crate::sparse::{SymbolicCache, TransientMatrixKey};

type AcSample = (f64, Vec<c64>);

pub trait SimulationObserver {
    fn analysis_started(&mut self, _analysis: &str, _total_points: usize) -> Result<()> {
        Ok(())
    }

    fn point(
        &mut self,
        _point: &SimulationPoint,
        _index: usize,
        _total_points: usize,
        _statistics: &SimulationStatistics,
    ) -> Result<()> {
        Ok(())
    }

    fn analysis_finished(
        &mut self,
        _analysis: &str,
        _total_points: usize,
        _statistics: &SimulationStatistics,
    ) -> Result<()> {
        Ok(())
    }
}

fn rfm_model<'a>(
    deck: &'a Deck,
    command_line_model: Option<&'a RfmModel>,
    model_name: &Option<String>,
) -> Result<&'a RfmModel> {
    match model_name {
        Some(name) => deck
            .rfm_models
            .get(name)
            .ok_or_else(|| Error::InvalidDeck(format!("RFM model '{name}' was not loaded"))),
        None => command_line_model
            .ok_or_else(|| Error::InvalidDeck("RFM instance has no command-line model".into())),
    }
}

pub fn run_with_observer(
    deck: &Deck,
    rfm: Option<&RfmModel>,
    observer: &mut dyn SimulationObserver,
    retain_points: bool,
) -> Result<SimulationResult> {
    let mut points = Vec::new();
    let mut statistics = SimulationStatistics::default();
    let mut real_cache = SymbolicCache::default();
    for analysis in &deck.analyses {
        match analysis {
            Analysis::Op => {
                observer.analysis_started("op", 1)?;
                let solution = solve_dc(deck, None, rfm, &mut real_cache, &mut statistics)?;
                let point = real_point(deck, "op", 0.0, &solution);
                observer.point(&point, 1, 1, &statistics)?;
                if retain_points {
                    points.push(point);
                }
                observer.analysis_finished("op", 1, &statistics)?;
            }
            Analysis::Dc {
                source,
                start,
                stop,
                step,
            } => {
                if !deck.elements.iter().any(|element| {
                    element.name().eq_ignore_ascii_case(source)
                        && matches!(element, Element::Voltage { .. } | Element::Current { .. })
                }) {
                    return Err(Error::InvalidDeck(format!(
                        ".dc source '{source}' was not found"
                    )));
                }
                let total_points = dc_output_count(*start, *stop, *step);
                observer.analysis_started("dc", total_points)?;
                let mut value = *start;
                let mut index = 0usize;
                while reached(value, *stop, *step) {
                    let solution = solve_dc(
                        deck,
                        Some((source, value)),
                        rfm,
                        &mut real_cache,
                        &mut statistics,
                    )?;
                    let point = real_point(deck, "dc", value, &solution);
                    index += 1;
                    observer.point(&point, index, total_points, &statistics)?;
                    if retain_points {
                        points.push(point);
                    }
                    value += step;
                }
                observer.analysis_finished("dc", index, &statistics)?;
            }
            Analysis::Ac {
                scale,
                points: point_count,
                start,
                stop,
            } => {
                let frequencies = frequencies(*scale, *point_count, *start, *stop);
                let total_points = frequencies.len();
                observer.analysis_started("ac", total_points)?;
                let (samples, symbolic_factorizations) = solve_ac_sweep(deck, rfm, &frequencies)?;
                statistics.sparse_numeric_refactorizations += samples.len();
                statistics.sparse_symbolic_factorizations += symbolic_factorizations;
                statistics.ac_matrix_assembly_replays += samples.len();
                for (index, (frequency, solution)) in samples.into_iter().enumerate() {
                    let point = complex_point(deck, frequency, &solution);
                    observer.point(&point, index + 1, total_points, &statistics)?;
                    if retain_points {
                        points.push(point);
                    }
                }
                observer.analysis_finished("ac", total_points, &statistics)?;
            }
            Analysis::Tran { step, stop } => {
                let total_points = transient_output_count(*step, *stop);
                observer.analysis_started("tran", total_points)?;
                points.extend(run_transient(
                    deck,
                    rfm,
                    (*step, *stop),
                    &mut real_cache,
                    &mut statistics,
                    observer,
                    retain_points,
                )?);
                observer.analysis_finished("tran", total_points, &statistics)?;
            }
        }
    }
    let measurements = evaluate_measurements(deck, &points)?;
    Ok(SimulationResult {
        nodes: deck.nodes.clone(),
        points,
        measurements,
        statistics,
    })
}

fn evaluate_measurements(
    deck: &Deck,
    points: &[SimulationPoint],
) -> Result<Vec<MeasurementResult>> {
    let mut scope = deck.parameters.clone();
    let mut results = Vec::with_capacity(deck.measurements.len());
    for measurement in &deck.measurements {
        let samples = match &measurement.operation {
            MeasurementOperation::Find { .. }
            | MeasurementOperation::Derivative { .. }
            | MeasurementOperation::Min { .. }
            | MeasurementOperation::Max { .. }
            | MeasurementOperation::Average { .. }
            | MeasurementOperation::Rms { .. }
            | MeasurementOperation::Integral { .. } => Some(measurement_samples(
                points,
                &measurement.analysis,
                measurement
                    .target
                    .as_ref()
                    .expect("sample measurements have a target"),
                &measurement.name,
            )?),
            _ => None,
        };
        let value = match &measurement.operation {
            MeasurementOperation::Find { at, when } => {
                let samples = samples.as_ref().expect("FIND has measurement samples");
                let x = if let Some(event) = when {
                    measurement_event_x(points, &measurement.analysis, event, &measurement.name)?
                } else {
                    at.unwrap_or_else(|| samples.last().expect("samples are non-empty").0)
                };
                interpolate_measurement(samples, x, &measurement.name)?
            }
            MeasurementOperation::Derivative { at, when } => {
                let samples = samples.as_ref().expect("DERIV has measurement samples");
                let x = if let Some(event) = when {
                    measurement_event_x(points, &measurement.analysis, event, &measurement.name)?
                } else {
                    at.unwrap_or_else(|| samples.last().expect("samples are non-empty").0)
                };
                derivative_measurement(samples, x, &measurement.name)?
            }
            MeasurementOperation::Min { from, to } => measurement_window(
                samples.as_ref().expect("MIN has measurement samples"),
                *from,
                *to,
                &measurement.name,
            )?
            .iter()
            .map(|(_, value)| *value)
            .reduce(f64::min)
            .expect("measurement window is non-empty"),
            MeasurementOperation::Max { from, to } => measurement_window(
                samples.as_ref().expect("MAX has measurement samples"),
                *from,
                *to,
                &measurement.name,
            )?
            .iter()
            .map(|(_, value)| *value)
            .reduce(f64::max)
            .expect("measurement window is non-empty"),
            MeasurementOperation::Average { from, to } => {
                let window = measurement_window(
                    samples.as_ref().expect("AVG has measurement samples"),
                    *from,
                    *to,
                    &measurement.name,
                )?;
                integrate_measurement(&window, false, true)
            }
            MeasurementOperation::Rms { from, to } => {
                let window = measurement_window(
                    samples.as_ref().expect("RMS has measurement samples"),
                    *from,
                    *to,
                    &measurement.name,
                )?;
                integrate_measurement(&window, true, true)
            }
            MeasurementOperation::Integral { from, to } => {
                let window = measurement_window(
                    samples.as_ref().expect("INTEG has measurement samples"),
                    *from,
                    *to,
                    &measurement.name,
                )?;
                integrate_measurement(&window, false, false)
            }
            MeasurementOperation::When { event } => {
                measurement_event_x(points, &measurement.analysis, event, &measurement.name)?
            }
            MeasurementOperation::Delay { trigger, target } => {
                let trigger_x = match trigger {
                    MeasurementTrigger::Event(event) => measurement_event_x(
                        points,
                        &measurement.analysis,
                        event,
                        &measurement.name,
                    )?,
                    MeasurementTrigger::At(value) => *value,
                };
                let target_x =
                    measurement_event_x(points, &measurement.analysis, target, &measurement.name)?;
                target_x - trigger_x
            }
            MeasurementOperation::Parameter { expression: text } => {
                expression::evaluate(text, &scope).map_err(|error| {
                    Error::InvalidDeck(format!(
                        ".measure '{}' PARAM expression failed: {error}",
                        measurement.name
                    ))
                })?
            }
        };
        scope.insert(measurement.name.to_ascii_lowercase(), value);
        results.push(MeasurementResult {
            analysis: measurement.analysis.clone(),
            name: measurement.name.clone(),
            value,
        });
    }
    Ok(results)
}

fn measurement_samples(
    points: &[SimulationPoint],
    analysis: &str,
    target: &MeasurementTarget,
    name: &str,
) -> Result<Vec<(f64, f64)>> {
    let mut samples: Vec<_> = points
        .iter()
        .filter(|point| point.analysis.eq_ignore_ascii_case(analysis))
        .map(|point| measurement_value(point, target).map(|value| (point.x, value)))
        .collect::<Result<_>>()?;
    if samples.is_empty() {
        return Err(Error::InvalidDeck(format!(
            ".measure '{name}' has no {analysis} analysis points"
        )));
    }
    samples.sort_by(|left, right| left.0.total_cmp(&right.0));
    Ok(samples)
}

fn measurement_event_x(
    points: &[SimulationPoint],
    analysis: &str,
    event: &MeasurementEvent,
    name: &str,
) -> Result<f64> {
    let samples = measurement_samples(points, analysis, &event.target, name)?;
    let delay = event.delay.unwrap_or(f64::NEG_INFINITY);
    let mut events = Vec::new();
    for pair in samples.windows(2) {
        let left = pair[0].1 - event.value;
        let right = pair[1].1 - event.value;
        let matches = match event.direction {
            MeasurementEventDirection::Rise => left < 0.0 && right >= 0.0,
            MeasurementEventDirection::Fall => left > 0.0 && right <= 0.0,
            MeasurementEventDirection::Cross => {
                (left < 0.0 && right >= 0.0) || (left > 0.0 && right <= 0.0)
            }
        };
        if !matches {
            continue;
        }
        let span = pair[1].1 - pair[0].1;
        let x = if span == 0.0 {
            pair[1].0
        } else {
            pair[0].0 + (event.value - pair[0].1) / span * (pair[1].0 - pair[0].0)
        };
        let tolerance = 1e-15_f64.max(x.abs() * 1e-12);
        if x >= delay - tolerance {
            events.push(x);
        }
    }
    let selected = match event.occurrence {
        MeasurementEventOccurrence::Index(index) => events.get(index - 1),
        MeasurementEventOccurrence::Last => events.last(),
    };
    selected.copied().ok_or_else(|| {
        let occurrence = match event.occurrence {
            MeasurementEventOccurrence::Index(index) => index.to_string(),
            MeasurementEventOccurrence::Last => "LAST".into(),
        };
        let direction = match event.direction {
            MeasurementEventDirection::Rise => "RISE",
            MeasurementEventDirection::Fall => "FALL",
            MeasurementEventDirection::Cross => "CROSS",
        };
        Error::InvalidDeck(format!(
            ".measure '{name}' did not find {direction}={occurrence} at value {:.17e}",
            event.value
        ))
    })
}

fn measurement_value(point: &SimulationPoint, target: &MeasurementTarget) -> Result<f64> {
    if point.analysis == "ac" {
        let positive = complex_measurement_component(point, &target.positive)?;
        let value = if target.branch_current {
            positive
        } else {
            positive
                - target
                    .negative
                    .as_deref()
                    .map(|name| complex_measurement_component(point, name))
                    .transpose()?
                    .unwrap_or(c64::new(0.0, 0.0))
        };
        return Ok(match target.quantity {
            MeasurementQuantity::Value | MeasurementQuantity::Real => value.re,
            MeasurementQuantity::Imaginary => value.im,
            MeasurementQuantity::Magnitude => value.norm(),
            MeasurementQuantity::Phase => value.arg().to_degrees(),
        });
    }
    let positive = real_measurement_component(point, &target.positive)?;
    let value = if target.branch_current {
        positive
    } else {
        positive
            - target
                .negative
                .as_deref()
                .map(|name| real_measurement_component(point, name))
                .transpose()?
                .unwrap_or(0.0)
    };
    Ok(match target.quantity {
        MeasurementQuantity::Value | MeasurementQuantity::Real => value,
        MeasurementQuantity::Imaginary => 0.0,
        MeasurementQuantity::Magnitude => value.abs(),
        MeasurementQuantity::Phase => {
            if value.is_sign_negative() {
                180.0
            } else {
                0.0
            }
        }
    })
}

fn real_measurement_component(point: &SimulationPoint, name: &str) -> Result<f64> {
    if name == "0" || name.eq_ignore_ascii_case("gnd") {
        return Ok(0.0);
    }
    point
        .values
        .iter()
        .find(|(candidate, _)| candidate.eq_ignore_ascii_case(name))
        .map(|(_, value)| *value)
        .ok_or_else(|| Error::InvalidDeck(format!(".measure target '{name}' was not found")))
}

fn complex_measurement_component(point: &SimulationPoint, name: &str) -> Result<c64> {
    if name == "0" || name.eq_ignore_ascii_case("gnd") {
        return Ok(c64::new(0.0, 0.0));
    }
    point
        .complex
        .iter()
        .find(|(candidate, _)| candidate.eq_ignore_ascii_case(name))
        .map(|(_, value)| c64::new(value.re, value.im))
        .ok_or_else(|| Error::InvalidDeck(format!(".measure target '{name}' was not found")))
}

fn interpolate_measurement(samples: &[(f64, f64)], x: f64, name: &str) -> Result<f64> {
    let first = samples.first().expect("samples are non-empty");
    let last = samples.last().expect("samples are non-empty");
    let tolerance = 1e-15_f64.max(x.abs() * 1e-12);
    if x < first.0 - tolerance || x > last.0 + tolerance {
        return Err(Error::InvalidDeck(format!(
            ".measure '{name}' requested x={x:.17e} outside [{:.17e}, {:.17e}]",
            first.0, last.0
        )));
    }
    if (x - first.0).abs() <= tolerance {
        return Ok(first.1);
    }
    if (x - last.0).abs() <= tolerance {
        return Ok(last.1);
    }
    for pair in samples.windows(2) {
        if x >= pair[0].0 - tolerance && x <= pair[1].0 + tolerance {
            let width = pair[1].0 - pair[0].0;
            if width == 0.0 {
                return Ok(pair[1].1);
            }
            let fraction = (x - pair[0].0) / width;
            return Ok(pair[0].1 + fraction * (pair[1].1 - pair[0].1));
        }
    }
    Err(Error::InvalidDeck(format!(
        ".measure '{name}' could not interpolate x={x:.17e}"
    )))
}

fn derivative_measurement(samples: &[(f64, f64)], x: f64, name: &str) -> Result<f64> {
    if samples.len() < 2 {
        return Err(Error::InvalidDeck(format!(
            ".measure '{name}' DERIV requires at least two analysis points"
        )));
    }
    interpolate_measurement(samples, x, name)?;
    let tolerance = 1e-15_f64.max(x.abs() * 1e-12);
    if let Some(index) = samples
        .iter()
        .position(|sample| (sample.0 - x).abs() <= tolerance)
    {
        let (left, right) = if index == 0 {
            (samples[0], samples[1])
        } else if index + 1 == samples.len() {
            (samples[index - 1], samples[index])
        } else {
            (samples[index - 1], samples[index + 1])
        };
        return Ok((right.1 - left.1) / (right.0 - left.0));
    }
    for pair in samples.windows(2) {
        if x > pair[0].0 && x < pair[1].0 {
            return Ok((pair[1].1 - pair[0].1) / (pair[1].0 - pair[0].0));
        }
    }
    Err(Error::InvalidDeck(format!(
        ".measure '{name}' could not evaluate DERIV at x={x:.17e}"
    )))
}

fn measurement_window(
    samples: &[(f64, f64)],
    from: Option<f64>,
    to: Option<f64>,
    name: &str,
) -> Result<Vec<(f64, f64)>> {
    let lower = from.unwrap_or_else(|| samples.first().expect("samples are non-empty").0);
    let upper = to.unwrap_or_else(|| samples.last().expect("samples are non-empty").0);
    if upper < lower {
        return Err(Error::InvalidDeck(format!(
            ".measure '{name}' has TO below FROM"
        )));
    }
    let mut window = vec![(lower, interpolate_measurement(samples, lower, name)?)];
    window.extend(
        samples
            .iter()
            .copied()
            .filter(|(x, _)| *x > lower && *x < upper),
    );
    if upper > lower {
        window.push((upper, interpolate_measurement(samples, upper, name)?));
    }
    Ok(window)
}

fn integrate_measurement(samples: &[(f64, f64)], squared: bool, normalize: bool) -> f64 {
    if samples.len() == 1 {
        return if !normalize {
            0.0
        } else if squared {
            samples[0].1.abs()
        } else {
            samples[0].1
        };
    }
    let span = samples.last().expect("samples are non-empty").0
        - samples.first().expect("samples are non-empty").0;
    let integral: f64 = samples
        .windows(2)
        .map(|pair| {
            let left = if squared {
                pair[0].1.powi(2)
            } else {
                pair[0].1
            };
            let right = if squared {
                pair[1].1.powi(2)
            } else {
                pair[1].1
            };
            0.5 * (left + right) * (pair[1].0 - pair[0].0)
        })
        .sum();
    if !normalize {
        return integral;
    }
    let average = integral / span;
    if squared { average.sqrt() } else { average }
}

fn solve_ac_sweep(
    deck: &Deck,
    rfm: Option<&RfmModel>,
    frequencies: &[f64],
) -> Result<(Vec<AcSample>, usize)> {
    let thread_count = std::thread::available_parallelism()
        .map(usize::from)
        .unwrap_or(1)
        .min(4)
        .min(frequencies.len());
    if thread_count <= 1 || frequencies.len() < 64 || deck.unknown_count < 256 {
        let mut cache = SymbolicCache::default();
        let mut samples = Vec::with_capacity(frequencies.len());
        let mut symbolic_factorizations = 0usize;
        for frequency in frequencies {
            let (solution, symbolic) = solve_ac(deck, rfm, *frequency, &mut cache)?;
            symbolic_factorizations += usize::from(symbolic);
            samples.push((*frequency, solution));
        }
        return Ok((samples, symbolic_factorizations));
    }

    let chunk_size = frequencies.len().div_ceil(thread_count);
    let batches = std::thread::scope(|scope| {
        let handles: Vec<_> = frequencies
            .chunks(chunk_size)
            .enumerate()
            .map(|(chunk_index, chunk)| {
                scope.spawn(move || {
                    let mut cache = SymbolicCache::default();
                    let mut batch = Vec::with_capacity(chunk.len());
                    let mut symbolic_factorizations = 0usize;
                    for (offset, frequency) in chunk.iter().enumerate() {
                        let (solution, symbolic) = solve_ac(deck, rfm, *frequency, &mut cache)?;
                        symbolic_factorizations += usize::from(symbolic);
                        batch.push((chunk_index * chunk_size + offset, *frequency, solution));
                    }
                    Ok((batch, symbolic_factorizations))
                })
            })
            .collect();
        handles
            .into_iter()
            .map(|handle| {
                handle
                    .join()
                    .map_err(|_| Error::Sparse("parallel AC worker panicked".into()))?
            })
            .collect::<Result<Vec<_>>>()
    })?;
    let symbolic_factorizations = batches.iter().map(|(_, count)| count).sum();
    let mut indexed_samples: Vec<_> = batches.into_iter().flat_map(|(batch, _)| batch).collect();
    indexed_samples.sort_unstable_by_key(|(index, _, _)| *index);
    Ok((
        indexed_samples
            .into_iter()
            .map(|(_, frequency, solution)| (frequency, solution))
            .collect(),
        symbolic_factorizations,
    ))
}

fn solve_dc(
    deck: &Deck,
    sweep: Option<(&str, f64)>,
    rfm: Option<&RfmModel>,
    cache: &mut SymbolicCache,
    statistics: &mut SimulationStatistics,
) -> Result<Vec<f64>> {
    if cache.has_real_constant_factor() {
        let mut rhs = vec![0.0; deck.unknown_count];
        for element in &deck.elements {
            match element {
                Element::Voltage {
                    name,
                    source,
                    branch,
                    ..
                } => {
                    let value = sweep
                        .filter(|(target, _)| name.eq_ignore_ascii_case(target))
                        .map_or(source.dc, |(_, value)| value);
                    rhs[*branch] += value;
                }
                Element::Current {
                    name,
                    positive,
                    negative,
                    source,
                } => {
                    let value = sweep
                        .filter(|(target, _)| name.eq_ignore_ascii_case(target))
                        .map_or(source.dc, |(_, value)| value);
                    stamp_current_real(&mut rhs, *positive, *negative, value);
                }
                _ => {}
            }
        }
        let (solution, _, _) = cache.solve_real_constant(deck.unknown_count, &[], &rhs)?;
        return Ok(solution);
    }
    let mut matrix = Vec::new();
    let mut rhs = vec![0.0; deck.unknown_count];
    let mut rfm_admittances = HashMap::new();
    for element in &deck.elements {
        match element {
            Element::Resistor {
                positive,
                negative,
                resistance,
                ..
            } => stamp_admittance_real(&mut matrix, *positive, *negative, 1.0 / resistance),
            Element::Capacitor {
                positive, negative, ..
            } => stamp_admittance_real(&mut matrix, *positive, *negative, 0.0),
            Element::Inductor {
                positive,
                negative,
                branch,
                ..
            } => stamp_branch_real(
                &mut matrix,
                &mut rhs,
                *positive,
                *negative,
                *branch,
                0.0,
                0.0,
            ),
            Element::Voltage {
                name,
                positive,
                negative,
                source,
                branch,
            } => {
                let value = sweep
                    .filter(|(target, _)| name.eq_ignore_ascii_case(target))
                    .map_or(source.dc, |(_, value)| value);
                stamp_branch_real(
                    &mut matrix,
                    &mut rhs,
                    *positive,
                    *negative,
                    *branch,
                    0.0,
                    value,
                );
            }
            Element::Current {
                name,
                positive,
                negative,
                source,
            } => {
                let value = sweep
                    .filter(|(target, _)| name.eq_ignore_ascii_case(target))
                    .map_or(source.dc, |(_, value)| value);
                stamp_current_real(&mut rhs, *positive, *negative, value);
            }
            Element::Vcvs {
                positive,
                negative,
                control_positive,
                control_negative,
                gain,
                branch,
                ..
            } => stamp_vcvs_real(
                &mut matrix,
                &mut rhs,
                (*positive, *negative),
                (*control_positive, *control_negative),
                *branch,
                *gain,
            ),
            Element::Vccs {
                positive,
                negative,
                control_positive,
                control_negative,
                transconductance,
                ..
            } => stamp_vccs_real(
                &mut matrix,
                *positive,
                *negative,
                *control_positive,
                *control_negative,
                *transconductance,
            ),
            Element::Cccs {
                positive,
                negative,
                control_branch,
                gain,
                ..
            } => stamp_cccs_real(&mut matrix, *positive, *negative, *control_branch, *gain),
            Element::Ccvs {
                positive,
                negative,
                control_branch,
                transresistance,
                branch,
                ..
            } => stamp_ccvs_real(
                &mut matrix,
                &mut rhs,
                *positive,
                *negative,
                *control_branch,
                *branch,
                *transresistance,
            ),
            Element::Rfm {
                ports,
                references,
                model,
                ..
            } => {
                if !rfm_admittances.contains_key(model) {
                    rfm_admittances.insert(
                        model.clone(),
                        rfm_model(deck, rfm, model)?.dc_admittance_real()?,
                    );
                }
                stamp_nport_real(
                    &mut matrix,
                    &mut rhs,
                    ports,
                    references,
                    &rfm_admittances[model],
                    None,
                );
            }
        }
    }
    let (solution, symbolic, numeric) =
        cache.solve_real_constant(deck.unknown_count, &matrix, &rhs)?;
    statistics.sparse_numeric_refactorizations += usize::from(numeric);
    statistics.sparse_symbolic_factorizations += usize::from(symbolic);
    Ok(solution)
}

fn solve_ac(
    deck: &Deck,
    rfm: Option<&RfmModel>,
    frequency: f64,
    cache: &mut SymbolicCache,
) -> Result<(Vec<c64>, bool)> {
    let omega = 2.0 * PI * frequency;
    let mut matrix = Vec::new();
    let mut rhs = vec![c64::new(0.0, 0.0); deck.unknown_count];
    let mut rfm_admittances = HashMap::new();
    for element in &deck.elements {
        match element {
            Element::Resistor {
                positive,
                negative,
                resistance,
                ..
            } => stamp_admittance_complex(
                &mut matrix,
                *positive,
                *negative,
                c64::new(1.0 / resistance, 0.0),
            ),
            Element::Capacitor {
                positive,
                negative,
                capacitance,
                ..
            } => stamp_admittance_complex(
                &mut matrix,
                *positive,
                *negative,
                c64::new(0.0, omega * capacitance),
            ),
            Element::Inductor {
                positive,
                negative,
                inductance,
                branch,
                ..
            } => stamp_branch_complex(
                &mut matrix,
                &mut rhs,
                *positive,
                *negative,
                *branch,
                c64::new(0.0, -omega * inductance),
                c64::new(0.0, 0.0),
            ),
            Element::Voltage {
                positive,
                negative,
                source,
                branch,
                ..
            } => stamp_branch_complex(
                &mut matrix,
                &mut rhs,
                *positive,
                *negative,
                *branch,
                c64::new(0.0, 0.0),
                source.ac,
            ),
            Element::Current {
                positive,
                negative,
                source,
                ..
            } => stamp_current_complex(&mut rhs, *positive, *negative, source.ac),
            Element::Vcvs {
                positive,
                negative,
                control_positive,
                control_negative,
                gain,
                branch,
                ..
            } => stamp_vcvs_complex(
                &mut matrix,
                &mut rhs,
                (*positive, *negative),
                (*control_positive, *control_negative),
                *branch,
                *gain,
            ),
            Element::Vccs {
                positive,
                negative,
                control_positive,
                control_negative,
                transconductance,
                ..
            } => stamp_vccs_complex(
                &mut matrix,
                *positive,
                *negative,
                *control_positive,
                *control_negative,
                *transconductance,
            ),
            Element::Cccs {
                positive,
                negative,
                control_branch,
                gain,
                ..
            } => stamp_cccs_complex(&mut matrix, *positive, *negative, *control_branch, *gain),
            Element::Ccvs {
                positive,
                negative,
                control_branch,
                transresistance,
                branch,
                ..
            } => stamp_ccvs_complex(
                &mut matrix,
                &mut rhs,
                *positive,
                *negative,
                *control_branch,
                *branch,
                *transresistance,
            ),
            Element::Rfm {
                ports,
                references,
                model,
                ..
            } => {
                if !rfm_admittances.contains_key(model) {
                    rfm_admittances.insert(
                        model.clone(),
                        rfm_model(deck, rfm, model)?.admittance(c64::new(0.0, omega))?,
                    );
                }
                stamp_nport_complex(&mut matrix, ports, references, &rfm_admittances[model]);
            }
        }
    }
    cache.solve_complex(deck.unknown_count, &matrix, &rhs)
}

#[derive(Default)]
struct DynamicState {
    capacitor: HashMap<String, CapacitorState>,
    inductor: HashMap<String, InductorState>,
    rfm: HashMap<String, RfmState>,
}

#[derive(Debug, Clone, Copy)]
struct CapacitorState {
    voltage: f64,
    previous_voltage: f64,
    older_voltage: f64,
    current: f64,
}

#[derive(Debug, Clone, Copy)]
struct InductorState {
    current: f64,
    previous_current: f64,
    older_current: f64,
    voltage: f64,
}

fn run_transient(
    deck: &Deck,
    rfm: Option<&RfmModel>,
    analysis: (f64, f64),
    cache: &mut SymbolicCache,
    statistics: &mut SimulationStatistics,
    observer: &mut dyn SimulationObserver,
    retain_points: bool,
) -> Result<Vec<SimulationPoint>> {
    let (step, stop) = analysis;
    for element in &deck.elements {
        if let Element::Rfm { model, .. } = element {
            let model_data = rfm_model(deck, rfm, model)?;
            if !model_data.supports_transient() {
                return Err(Error::InvalidDeck(format!(
                    "S-parameter model '{}' cannot run TRAN without RATIONAL_FUNC=1 on its TSTONEFILE .model",
                    model.as_deref().unwrap_or("<command-line>")
                )));
            }
        }
    }
    let total_points = transient_output_count(step, stop);
    let initial = solve_dc(deck, None, rfm, cache, statistics)?;
    let mut state = DynamicState::default();
    for element in &deck.elements {
        match element {
            Element::Capacitor {
                name,
                positive,
                negative,
                ..
            } => {
                state.capacitor.insert(
                    name.clone(),
                    CapacitorState {
                        voltage: node_voltage(&initial, *positive)
                            - node_voltage(&initial, *negative),
                        previous_voltage: node_voltage(&initial, *positive)
                            - node_voltage(&initial, *negative),
                        older_voltage: node_voltage(&initial, *positive)
                            - node_voltage(&initial, *negative),
                        current: 0.0,
                    },
                );
            }
            Element::Inductor { name, branch, .. } => {
                state.inductor.insert(
                    name.clone(),
                    InductorState {
                        current: initial[*branch],
                        previous_current: initial[*branch],
                        older_current: initial[*branch],
                        voltage: 0.0,
                    },
                );
            }
            Element::Rfm {
                name,
                ports,
                references,
                model,
            } => {
                let model = rfm_model(deck, rfm, model)?;
                let mut rfm_state = model.create_state();
                let port_voltages = port_voltages(&initial, ports, references);
                model.initialize_dc(&mut rfm_state, &port_voltages)?;
                state.rfm.insert(name.clone(), rfm_state);
            }
            _ => {}
        }
    }
    let initial_point = real_point(deck, "tran", 0.0, &initial);
    observer.point(&initial_point, 1, total_points, statistics)?;
    let mut result = Vec::new();
    if retain_points {
        result.push(initial_point);
    }
    let mut first_step = true;
    let mut restart_integration = false;
    let mut previous_time = 0.0;
    let mut previous_step = 0.0;
    let mut older_step = 0.0;
    let mut accepted_history_depth = 0usize;
    let source_waveforms: Vec<_> = deck
        .elements
        .iter()
        .filter_map(|element| match element {
            Element::Voltage { source, .. } | Element::Current { source, .. } => {
                source.waveform.as_ref()
            }
            _ => None,
        })
        .collect();
    let requires_error_control = deck.elements.iter().any(|element| {
        matches!(
            element,
            Element::Capacitor { .. } | Element::Inductor { .. } | Element::Rfm { .. }
        )
    });
    let minimum_step = (step * 1e-9).max(1e-18);
    let mut suggested_step = step;
    let mut output_index = 1usize;
    let mut matrix = Vec::new();
    let mut rhs = vec![0.0; deck.unknown_count];
    let mut capacitor_companions = Vec::new();
    let mut inductor_companions = Vec::new();
    let mut capacitor_candidates = Vec::new();
    let mut inductor_candidates = Vec::new();
    let mut rfm_port_voltages = Vec::new();
    let mut rfm_candidate_state = state.rfm.clone();
    let profile = std::env::var_os("AGENT_SPICE_PROFILE").is_some();
    let profile_started = Instant::now();
    let mut profile_stamp = Duration::ZERO;
    let mut profile_rfm_stamp = Duration::ZERO;
    let mut profile_solve = Duration::ZERO;
    let mut profile_numeric_solve = Duration::ZERO;
    let mut profile_cached_solve = Duration::ZERO;
    let mut profile_candidate = Duration::ZERO;
    let mut profile_rfm_candidate = Duration::ZERO;
    let mut profile_lte = Duration::ZERO;
    let mut profile_output = Duration::ZERO;
    loop {
        let stamp_started = profile.then(Instant::now);
        let raw_output_time = output_index as f64 * step;
        let output_time = if raw_output_time >= stop - step * 1e-9 {
            stop
        } else {
            raw_output_time
        };
        let candidate_step = if requires_error_control {
            quantize_transient_step(suggested_step, step)
        } else {
            step
        };
        let natural_time = (previous_time + candidate_step).min(output_time);
        let breakpoint = next_source_breakpoint(&source_waveforms, previous_time, stop);
        let candidate_time = breakpoint.map_or(natural_time, |value| value.min(natural_time));
        let time_tolerance = step * 1e-9;
        let reaches_output = (candidate_time - output_time).abs() <= time_tolerance;
        let time = if reaches_output {
            output_time
        } else {
            candidate_time
        };
        let breakpoint_hit = breakpoint.is_some_and(|value| (time - value).abs() <= time_tolerance);
        let measured_step = time - previous_time;
        let actual_step = if (measured_step - candidate_step).abs() <= time_tolerance {
            candidate_step
        } else {
            measured_step
        };
        let backward_euler = first_step || restart_integration || previous_step <= 0.0;
        let bdf = if backward_euler {
            Some((1.0 / actual_step, -1.0 / actual_step, 0.0))
        } else if deck.integration_method == IntegrationMethod::Gear2 {
            let ratio = actual_step / previous_step;
            Some((
                (1.0 + 2.0 * ratio) / (actual_step * (1.0 + ratio)),
                -(1.0 + ratio) / actual_step,
                ratio * ratio / (actual_step * (1.0 + ratio)),
            ))
        } else {
            None
        };
        let matrix_key = transient_matrix_key(
            deck.integration_method,
            backward_euler,
            actual_step,
            previous_step,
        );
        let build_matrix = !cache.has_transient_factor(matrix_key);
        if build_matrix {
            matrix.clear();
            statistics.transient_matrix_cache_misses += 1;
        } else {
            statistics.transient_matrix_cache_hits += 1;
        }
        rhs.fill(0.0);
        capacitor_companions.clear();
        inductor_companions.clear();
        capacitor_candidates.clear();
        inductor_candidates.clear();
        for element in &deck.elements {
            match element {
                Element::Resistor {
                    positive,
                    negative,
                    resistance,
                    ..
                } => {
                    if build_matrix {
                        stamp_admittance_real(&mut matrix, *positive, *negative, 1.0 / resistance);
                    }
                }
                Element::Capacitor {
                    name,
                    positive,
                    negative,
                    capacitance,
                } => {
                    let capacitor = state.capacitor[name];
                    let (conductance, history) = if let Some((a0, a1, a2)) = bdf {
                        (
                            capacitance * a0,
                            capacitance
                                * (a1 * capacitor.voltage + a2 * capacitor.previous_voltage),
                        )
                    } else {
                        let conductance = 2.0 * capacitance / actual_step;
                        let history = -conductance * capacitor.voltage - capacitor.current;
                        (conductance, history)
                    };
                    if build_matrix {
                        stamp_admittance_real(&mut matrix, *positive, *negative, conductance);
                    }
                    stamp_current_real(&mut rhs, *positive, *negative, history);
                    capacitor_companions.push((
                        name.as_str(),
                        *positive,
                        *negative,
                        *capacitance,
                        conductance,
                        history,
                    ));
                }
                Element::Inductor {
                    name,
                    positive,
                    negative,
                    inductance,
                    branch,
                } => {
                    let inductor = state.inductor[name];
                    let (resistance, history) = if let Some((a0, a1, a2)) = bdf {
                        (
                            inductance * a0,
                            inductance * (a1 * inductor.current + a2 * inductor.previous_current),
                        )
                    } else {
                        let resistance = 2.0 * inductance / actual_step;
                        let history = -resistance * inductor.current - inductor.voltage;
                        (resistance, history)
                    };
                    if build_matrix {
                        stamp_branch_real(
                            &mut matrix,
                            &mut rhs,
                            *positive,
                            *negative,
                            *branch,
                            -resistance,
                            history,
                        );
                    } else {
                        rhs[*branch] += history;
                    }
                    inductor_companions.push((
                        name.as_str(),
                        *positive,
                        *negative,
                        *inductance,
                        *branch,
                    ));
                }
                Element::Voltage {
                    positive,
                    negative,
                    source,
                    branch,
                    ..
                } => {
                    let value = source.transient_value(time);
                    if build_matrix {
                        stamp_branch_real(
                            &mut matrix,
                            &mut rhs,
                            *positive,
                            *negative,
                            *branch,
                            0.0,
                            value,
                        );
                    } else {
                        rhs[*branch] += value;
                    }
                }
                Element::Current {
                    positive,
                    negative,
                    source,
                    ..
                } => {
                    stamp_current_real(&mut rhs, *positive, *negative, source.transient_value(time))
                }
                Element::Vcvs {
                    positive,
                    negative,
                    control_positive,
                    control_negative,
                    gain,
                    branch,
                    ..
                } => {
                    if build_matrix {
                        stamp_vcvs_real(
                            &mut matrix,
                            &mut rhs,
                            (*positive, *negative),
                            (*control_positive, *control_negative),
                            *branch,
                            *gain,
                        );
                    }
                }
                Element::Vccs {
                    positive,
                    negative,
                    control_positive,
                    control_negative,
                    transconductance,
                    ..
                } => {
                    if build_matrix {
                        stamp_vccs_real(
                            &mut matrix,
                            *positive,
                            *negative,
                            *control_positive,
                            *control_negative,
                            *transconductance,
                        );
                    }
                }
                Element::Cccs {
                    positive,
                    negative,
                    control_branch,
                    gain,
                    ..
                } => {
                    if build_matrix {
                        stamp_cccs_real(&mut matrix, *positive, *negative, *control_branch, *gain);
                    }
                }
                Element::Ccvs {
                    positive,
                    negative,
                    control_branch,
                    transresistance,
                    branch,
                    ..
                } => {
                    if build_matrix {
                        stamp_ccvs_real(
                            &mut matrix,
                            &mut rhs,
                            *positive,
                            *negative,
                            *control_branch,
                            *branch,
                            *transresistance,
                        );
                    }
                }
                Element::Rfm {
                    name,
                    ports,
                    references,
                    model,
                } => {
                    let rfm_stamp_started = profile.then(Instant::now);
                    let model = rfm_model(deck, rfm, model)?;
                    let rfm_state = state.rfm.get_mut(name).ok_or_else(|| {
                        Error::InvalidDeck(format!("RFM state for '{name}' was not initialized"))
                    })?;
                    if let Some((a0, a1, a2)) = bdf {
                        model.prepare_bdf(rfm_state, a0, a1, a2)?;
                    } else {
                        model.prepare_trapezoidal(rfm_state, actual_step)?;
                    }
                    if build_matrix {
                        stamp_nport_real(
                            &mut matrix,
                            &mut rhs,
                            ports,
                            references,
                            rfm_state.conductance(),
                            Some(rfm_state.offset()),
                        );
                    } else {
                        stamp_nport_offset_real(&mut rhs, ports, references, rfm_state.offset());
                    }
                    if let Some(started) = rfm_stamp_started {
                        profile_rfm_stamp += started.elapsed();
                    }
                }
            }
        }
        if let Some(started) = stamp_started {
            profile_stamp += started.elapsed();
        }
        let solve_started = profile.then(Instant::now);
        let (symbolic, numeric) = if build_matrix {
            let symbolic = cache.solve_real_transient_in_place(
                matrix_key,
                deck.unknown_count,
                &matrix,
                &mut rhs,
            )?;
            (symbolic, true)
        } else {
            cache.solve_transient_factor_in_place(matrix_key, deck.unknown_count, &mut rhs)?;
            (false, false)
        };
        if let Some(started) = solve_started {
            let elapsed = started.elapsed();
            profile_solve += elapsed;
            if numeric {
                profile_numeric_solve += elapsed;
            } else {
                profile_cached_solve += elapsed;
            }
        }
        statistics.sparse_numeric_refactorizations += usize::from(numeric);
        statistics.sparse_symbolic_factorizations += usize::from(symbolic);
        let solution = &rhs;
        let candidate_started = profile.then(Instant::now);
        for (name, positive, negative, capacitance, conductance, history) in &capacitor_companions {
            let voltage = node_voltage(solution, *positive) - node_voltage(solution, *negative);
            capacitor_candidates.push((
                *name,
                *capacitance,
                voltage,
                conductance * voltage + history,
            ));
        }
        for (name, positive, negative, inductance, branch) in &inductor_companions {
            let voltage = node_voltage(solution, *positive) - node_voltage(solution, *negative);
            inductor_candidates.push((*name, *inductance, solution[*branch], voltage));
        }
        for element in &deck.elements {
            if let Element::Rfm {
                name,
                ports,
                references,
                model,
            } = element
            {
                let rfm_candidate_started = profile.then(Instant::now);
                let rfm_model = rfm_model(deck, rfm, model)?;
                rfm_port_voltages.clear();
                rfm_port_voltages.extend(ports.iter().zip(references).map(|(port, reference)| {
                    node_voltage(solution, *port) - node_voltage(solution, *reference)
                }));
                let previous = state.rfm.get(name).ok_or_else(|| {
                    Error::InvalidDeck(format!("RFM state for '{name}' was not initialized"))
                })?;
                let candidate = rfm_candidate_state.get_mut(name).ok_or_else(|| {
                    Error::InvalidDeck(format!(
                        "RFM candidate state for '{name}' was not initialized"
                    ))
                })?;
                rfm_model.commit_candidate(candidate, previous, &rfm_port_voltages);
                if let Some(started) = rfm_candidate_started {
                    profile_rfm_candidate += started.elapsed();
                }
            }
        }
        if let Some(started) = candidate_started {
            profile_candidate += started.elapsed();
        }

        let lte_started = profile.then(Instant::now);
        let error_order = if !backward_euler
            && accepted_history_depth >= 2
            && previous_step > 0.0
            && older_step > 0.0
        {
            2
        } else {
            1
        };
        let error_ratio = if requires_error_control {
            statistics.device_truncation_evaluations += 1;
            transient_truncation_error_ratio(
                deck,
                rfm,
                &state,
                &capacitor_candidates,
                &inductor_candidates,
                &rfm_candidate_state,
                actual_step,
                if previous_step > 0.0 {
                    previous_step
                } else {
                    actual_step
                },
                if older_step > 0.0 {
                    older_step
                } else if previous_step > 0.0 {
                    previous_step
                } else {
                    actual_step
                },
                error_order,
                accepted_history_depth,
            )?
        } else {
            0.0
        };
        if let Some(started) = lte_started {
            profile_lte += started.elapsed();
        }
        if error_ratio > 1.0 {
            statistics.rejected_transient_steps += 1;
            if actual_step <= minimum_step * (1.0 + 1e-12) {
                return Err(Error::InvalidDeck(format!(
                    "transient LTE tolerance could not be met at t={time:.17e} (normalized error={error_ratio:.6e}, minimum step={minimum_step:.6e})"
                )));
            }
            suggested_step = (actual_step * transient_step_scale(error_ratio, false, error_order))
                .max(minimum_step);
            continue;
        }

        for &(name, _, voltage, current) in &capacitor_candidates {
            let previous = state.capacitor.get_mut(name).ok_or_else(|| {
                Error::InvalidDeck(format!("capacitor state for '{name}' was not initialized"))
            })?;
            *previous = CapacitorState {
                voltage,
                previous_voltage: previous.voltage,
                older_voltage: previous.previous_voltage,
                current,
            };
        }
        for &(name, _, current, voltage) in &inductor_candidates {
            let previous = state.inductor.get_mut(name).ok_or_else(|| {
                Error::InvalidDeck(format!("inductor state for '{name}' was not initialized"))
            })?;
            *previous = InductorState {
                current,
                previous_current: previous.current,
                older_current: previous.previous_current,
                voltage,
            };
        }
        std::mem::swap(&mut state.rfm, &mut rfm_candidate_state);
        statistics.accepted_transient_steps += 1;
        statistics.fixed_transient_steps +=
            usize::from((actual_step - step).abs() <= time_tolerance && !breakpoint_hit);
        statistics.breakpoint_transient_steps += usize::from(breakpoint_hit);
        if reaches_output {
            let output_started = profile.then(Instant::now);
            let point = real_point(deck, "tran", output_time, solution);
            observer.point(&point, output_index + 1, total_points, statistics)?;
            if retain_points {
                result.push(point);
            }
            if let Some(started) = output_started {
                profile_output += started.elapsed();
            }
            output_index += 1;
        }
        first_step = false;
        restart_integration = breakpoint_hit;
        accepted_history_depth = if breakpoint_hit {
            0
        } else {
            (accepted_history_depth + 1).min(3)
        };
        previous_time = time;
        older_step = previous_step;
        previous_step = actual_step;
        let mut next_step = actual_step * transient_step_scale(error_ratio, true, error_order);
        if reaches_output && !breakpoint_hit && actual_step < candidate_step - time_tolerance {
            next_step = next_step.max(candidate_step);
        }
        suggested_step = next_step.min(step);
        if breakpoint_hit {
            suggested_step = suggested_step.min((actual_step * 0.25).max(minimum_step));
        }
        if time >= stop {
            break;
        }
    }
    if profile {
        crate::logging::line(format_args!(
            "[agent-spice-profile] total={:.6}s stamp={:.6}s solve={:.6}s candidate={:.6}s lte={:.6}s rfm-stamp={:.6}s numeric-solve={:.6}s cached-solve={:.6}s rfm-candidate={:.6}s output={:.6}s matrix-cache={}/{}",
            profile_started.elapsed().as_secs_f64(),
            profile_stamp.as_secs_f64(),
            profile_solve.as_secs_f64(),
            profile_candidate.as_secs_f64(),
            profile_lte.as_secs_f64(),
            profile_rfm_stamp.as_secs_f64(),
            profile_numeric_solve.as_secs_f64(),
            profile_cached_solve.as_secs_f64(),
            profile_rfm_candidate.as_secs_f64(),
            profile_output.as_secs_f64(),
            statistics.transient_matrix_cache_hits,
            statistics.transient_matrix_cache_misses
        ));
    }
    Ok(result)
}

#[allow(clippy::too_many_arguments)]
fn transient_truncation_error_ratio(
    deck: &Deck,
    rfm: Option<&RfmModel>,
    state: &DynamicState,
    capacitor_candidates: &[(&str, f64, f64, f64)],
    inductor_candidates: &[(&str, f64, f64, f64)],
    rfm_candidates: &HashMap<String, RfmState>,
    h0: f64,
    h1: f64,
    h2: f64,
    order: usize,
    accepted_history_depth: usize,
) -> Result<f64> {
    if accepted_history_depth == 0 {
        return Ok(0.0);
    }
    let second_order_factor = if deck.integration_method == IntegrationMethod::Gear2 {
        2.0 / 9.0
    } else {
        1.0 / 12.0
    };
    let truncation_scale = if deck.elements.iter().any(|element| {
        matches!(
            element,
            Element::Voltage {
                source: crate::netlist::Source {
                    waveform: Some(crate::netlist::Waveform::Pulse { rise, fall, .. }),
                    ..
                },
                ..
            } | Element::Current {
                source: crate::netlist::Source {
                    waveform: Some(crate::netlist::Waveform::Pulse { rise, fall, .. }),
                    ..
                },
                ..
            } if *rise == 0.0 || *fall == 0.0
        )
    }) {
        0.03
    } else {
        0.3
    };
    let mut maximum: f64 = 0.0;
    for (name, capacitance, voltage, current) in capacitor_candidates {
        let previous = state.capacitor.get(*name).ok_or_else(|| {
            Error::InvalidDeck(format!("capacitor state for '{name}' was not initialized"))
        })?;
        maximum = maximum.max(charge_truncation_ratio(
            capacitance * voltage,
            capacitance * previous.voltage,
            capacitance * previous.previous_voltage,
            capacitance * previous.older_voltage,
            *current,
            previous.current,
            h0,
            h1,
            h2,
            order,
            second_order_factor,
            deck.current_tolerance,
            deck.relative_tolerance,
            deck.charge_tolerance,
            deck.truncation_tolerance * truncation_scale,
        ));
    }
    for (name, inductance, current, voltage) in inductor_candidates {
        let previous = state.inductor.get(*name).ok_or_else(|| {
            Error::InvalidDeck(format!("inductor state for '{name}' was not initialized"))
        })?;
        maximum = maximum.max(charge_truncation_ratio(
            inductance * current,
            inductance * previous.current,
            inductance * previous.previous_current,
            inductance * previous.older_current,
            *voltage,
            previous.voltage,
            h0,
            h1,
            h2,
            order,
            second_order_factor,
            deck.voltage_tolerance,
            deck.relative_tolerance,
            deck.charge_tolerance,
            deck.truncation_tolerance * truncation_scale,
        ));
    }
    if !rfm_candidates.is_empty() {
        for element in &deck.elements {
            if let Element::Rfm {
                name,
                model: model_name,
                ..
            } = element
            {
                let model = rfm_model(deck, rfm, model_name)?;
                let previous = state.rfm.get(name).ok_or_else(|| {
                    Error::InvalidDeck(format!("RFM state for '{name}' was not initialized"))
                })?;
                let candidate = rfm_candidates.get(name).ok_or_else(|| {
                    Error::InvalidDeck(format!(
                        "RFM candidate state for '{name}' was not initialized"
                    ))
                })?;
                maximum = maximum.max(model.truncation_error_ratio(
                    candidate,
                    previous,
                    h0,
                    h1,
                    h2,
                    order,
                    second_order_factor,
                    deck.voltage_tolerance,
                    deck.relative_tolerance,
                    deck.truncation_tolerance,
                    truncation_scale,
                ));
            }
        }
    }
    Ok(maximum)
}

#[allow(clippy::too_many_arguments)]
fn charge_truncation_ratio(
    q0: f64,
    q1: f64,
    q2: f64,
    q3: f64,
    derivative0: f64,
    derivative1: f64,
    h0: f64,
    h1: f64,
    h2: f64,
    order: usize,
    second_order_factor: f64,
    derivative_absolute_tolerance: f64,
    relative_tolerance: f64,
    state_absolute_tolerance: f64,
    truncation_tolerance: f64,
) -> f64 {
    let derivative_tolerance = derivative_absolute_tolerance
        + relative_tolerance * derivative0.abs().max(derivative1.abs());
    let scaled_state_tolerance =
        relative_tolerance * q0.abs().max(q1.abs()).max(state_absolute_tolerance) / h0;
    let tolerance = derivative_tolerance.max(scaled_state_tolerance);
    let scaled_error = if order == 1 {
        let difference0 = (q0 - q1) / h0;
        let difference1 = (q1 - q2) / h1;
        0.5 * ((difference0 - difference1) / (h0 + h1)).abs() * h0
    } else {
        let difference0 = (q0 - q1) / h0;
        let difference1 = (q1 - q2) / h1;
        let difference2 = (q2 - q3) / h2;
        let second0 = (difference0 - difference1) / (h0 + h1);
        let second1 = (difference1 - difference2) / (h1 + h2);
        second_order_factor * ((second0 - second1) / (h0 + h1 + h2)).abs() * h0 * h0
    };
    let ratio = scaled_error / (truncation_tolerance * tolerance);
    if ratio.is_finite() {
        ratio
    } else {
        f64::INFINITY
    }
}

fn transient_step_scale(error_ratio: f64, accepted: bool, order: usize) -> f64 {
    let unconstrained = if error_ratio <= 1e-12 {
        2.0
    } else {
        0.9 / error_ratio.powf(1.0 / order.max(1) as f64)
    };
    if accepted {
        unconstrained.clamp(0.5, 2.0)
    } else {
        unconstrained.clamp(0.1, 0.5)
    }
}

fn transient_matrix_key(
    integration_method: IntegrationMethod,
    backward_euler: bool,
    step: f64,
    previous_step: f64,
) -> TransientMatrixKey {
    if backward_euler {
        return TransientMatrixKey::BackwardEuler {
            step_bits: step.to_bits(),
        };
    }
    match integration_method {
        IntegrationMethod::Gear2 => TransientMatrixKey::Gear2 {
            step_bits: step.to_bits(),
            previous_step_bits: previous_step.to_bits(),
        },
        IntegrationMethod::Trap => TransientMatrixKey::Trapezoidal {
            step_bits: step.to_bits(),
        },
    }
}

fn quantize_transient_step(step: f64, maximum_step: f64) -> f64 {
    if step >= maximum_step {
        return maximum_step;
    }
    // Dyadic levels keep output-grid fragments on a small set of reusable LU factors.
    let level = ((maximum_step / step).log2() - 1e-12).ceil().max(0.0);
    maximum_step * 2.0_f64.powf(-level)
}

fn stamp_nport_real(
    matrix: &mut Vec<Triplet<usize, usize, f64>>,
    rhs: &mut [f64],
    ports: &[Node],
    references: &[Node],
    admittance: &[f64],
    offset: Option<&[f64]>,
) {
    debug_assert_eq!(admittance.len(), ports.len() * ports.len());
    debug_assert_eq!(references.len(), ports.len());
    for (row, positive_row) in ports.iter().enumerate() {
        let negative_row = references[row];
        for (column, positive_column) in ports.iter().enumerate() {
            let value = admittance[row * ports.len() + column];
            if value == 0.0 {
                continue;
            }
            stamp_vccs_real(
                matrix,
                *positive_row,
                negative_row,
                *positive_column,
                references[column],
                value,
            );
        }
        if let Some(offset) = offset {
            stamp_current_real(rhs, *positive_row, negative_row, offset[row]);
        }
    }
}

fn stamp_nport_offset_real(rhs: &mut [f64], ports: &[Node], references: &[Node], offset: &[f64]) {
    debug_assert_eq!(offset.len(), ports.len());
    for ((positive, negative), value) in ports.iter().zip(references).zip(offset) {
        stamp_current_real(rhs, *positive, *negative, *value);
    }
}

fn stamp_nport_complex(
    matrix: &mut Vec<Triplet<usize, usize, c64>>,
    ports: &[Node],
    references: &[Node],
    admittance: &[c64],
) {
    debug_assert_eq!(admittance.len(), ports.len() * ports.len());
    debug_assert_eq!(references.len(), ports.len());
    for (row, positive_row) in ports.iter().enumerate() {
        for (column, positive_column) in ports.iter().enumerate() {
            let value = admittance[row * ports.len() + column];
            if value == c64::new(0.0, 0.0) {
                continue;
            }
            stamp_vccs_value_complex(
                matrix,
                *positive_row,
                references[row],
                *positive_column,
                references[column],
                value,
            );
        }
    }
}

fn stamp_admittance_real(
    matrix: &mut Vec<Triplet<usize, usize, f64>>,
    positive: Node,
    negative: Node,
    admittance: f64,
) {
    if let Some(positive) = positive {
        matrix.push(Triplet::new(positive, positive, admittance));
    }
    if let Some(negative) = negative {
        matrix.push(Triplet::new(negative, negative, admittance));
    }
    if let (Some(positive), Some(negative)) = (positive, negative) {
        matrix.push(Triplet::new(positive, negative, -admittance));
        matrix.push(Triplet::new(negative, positive, -admittance));
    }
}

fn stamp_admittance_complex(
    matrix: &mut Vec<Triplet<usize, usize, c64>>,
    positive: Node,
    negative: Node,
    admittance: c64,
) {
    if let Some(positive) = positive {
        matrix.push(Triplet::new(positive, positive, admittance));
    }
    if let Some(negative) = negative {
        matrix.push(Triplet::new(negative, negative, admittance));
    }
    if let (Some(positive), Some(negative)) = (positive, negative) {
        matrix.push(Triplet::new(positive, negative, -admittance));
        matrix.push(Triplet::new(negative, positive, -admittance));
    }
}

fn stamp_branch_real(
    matrix: &mut Vec<Triplet<usize, usize, f64>>,
    rhs: &mut [f64],
    positive: Node,
    negative: Node,
    branch: usize,
    impedance: f64,
    value: f64,
) {
    if let Some(positive) = positive {
        matrix.push(Triplet::new(positive, branch, 1.0));
        matrix.push(Triplet::new(branch, positive, 1.0));
    }
    if let Some(negative) = negative {
        matrix.push(Triplet::new(negative, branch, -1.0));
        matrix.push(Triplet::new(branch, negative, -1.0));
    }
    matrix.push(Triplet::new(branch, branch, impedance));
    rhs[branch] += value;
}

fn stamp_branch_complex(
    matrix: &mut Vec<Triplet<usize, usize, c64>>,
    rhs: &mut [c64],
    positive: Node,
    negative: Node,
    branch: usize,
    impedance: c64,
    value: c64,
) {
    if let Some(positive) = positive {
        matrix.push(Triplet::new(positive, branch, c64::new(1.0, 0.0)));
        matrix.push(Triplet::new(branch, positive, c64::new(1.0, 0.0)));
    }
    if let Some(negative) = negative {
        matrix.push(Triplet::new(negative, branch, c64::new(-1.0, 0.0)));
        matrix.push(Triplet::new(branch, negative, c64::new(-1.0, 0.0)));
    }
    matrix.push(Triplet::new(branch, branch, impedance));
    rhs[branch] += value;
}

fn stamp_current_real(rhs: &mut [f64], positive: Node, negative: Node, current: f64) {
    if let Some(positive) = positive {
        rhs[positive] -= current;
    }
    if let Some(negative) = negative {
        rhs[negative] += current;
    }
}

fn stamp_current_complex(rhs: &mut [c64], positive: Node, negative: Node, current: c64) {
    if let Some(positive) = positive {
        rhs[positive] -= current;
    }
    if let Some(negative) = negative {
        rhs[negative] += current;
    }
}

fn stamp_vcvs_real(
    matrix: &mut Vec<Triplet<usize, usize, f64>>,
    rhs: &mut [f64],
    terminals: (Node, Node),
    control: (Node, Node),
    branch: usize,
    gain: f64,
) {
    let (positive, negative) = terminals;
    let (control_positive, control_negative) = control;
    stamp_branch_real(matrix, rhs, positive, negative, branch, 0.0, 0.0);
    if let Some(control_positive) = control_positive {
        matrix.push(Triplet::new(branch, control_positive, -gain));
    }
    if let Some(control_negative) = control_negative {
        matrix.push(Triplet::new(branch, control_negative, gain));
    }
}

fn stamp_vcvs_complex(
    matrix: &mut Vec<Triplet<usize, usize, c64>>,
    rhs: &mut [c64],
    terminals: (Node, Node),
    control: (Node, Node),
    branch: usize,
    gain: f64,
) {
    let (positive, negative) = terminals;
    let (control_positive, control_negative) = control;
    stamp_branch_complex(
        matrix,
        rhs,
        positive,
        negative,
        branch,
        c64::new(0.0, 0.0),
        c64::new(0.0, 0.0),
    );
    if let Some(control_positive) = control_positive {
        matrix.push(Triplet::new(branch, control_positive, c64::new(-gain, 0.0)));
    }
    if let Some(control_negative) = control_negative {
        matrix.push(Triplet::new(branch, control_negative, c64::new(gain, 0.0)));
    }
}

fn stamp_vccs_real(
    matrix: &mut Vec<Triplet<usize, usize, f64>>,
    positive: Node,
    negative: Node,
    control_positive: Node,
    control_negative: Node,
    transconductance: f64,
) {
    if let (Some(row), Some(column)) = (positive, control_positive) {
        matrix.push(Triplet::new(row, column, transconductance));
    }
    if let (Some(row), Some(column)) = (positive, control_negative) {
        matrix.push(Triplet::new(row, column, -transconductance));
    }
    if let (Some(row), Some(column)) = (negative, control_positive) {
        matrix.push(Triplet::new(row, column, -transconductance));
    }
    if let (Some(row), Some(column)) = (negative, control_negative) {
        matrix.push(Triplet::new(row, column, transconductance));
    }
}

fn stamp_vccs_complex(
    matrix: &mut Vec<Triplet<usize, usize, c64>>,
    positive: Node,
    negative: Node,
    control_positive: Node,
    control_negative: Node,
    transconductance: f64,
) {
    stamp_vccs_value_complex(
        matrix,
        positive,
        negative,
        control_positive,
        control_negative,
        c64::new(transconductance, 0.0),
    );
}

fn stamp_vccs_value_complex(
    matrix: &mut Vec<Triplet<usize, usize, c64>>,
    positive: Node,
    negative: Node,
    control_positive: Node,
    control_negative: Node,
    transconductance: c64,
) {
    if let (Some(row), Some(column)) = (positive, control_positive) {
        matrix.push(Triplet::new(row, column, transconductance));
    }
    if let (Some(row), Some(column)) = (positive, control_negative) {
        matrix.push(Triplet::new(row, column, -transconductance));
    }
    if let (Some(row), Some(column)) = (negative, control_positive) {
        matrix.push(Triplet::new(row, column, -transconductance));
    }
    if let (Some(row), Some(column)) = (negative, control_negative) {
        matrix.push(Triplet::new(row, column, transconductance));
    }
}

fn stamp_cccs_real(
    matrix: &mut Vec<Triplet<usize, usize, f64>>,
    positive: Node,
    negative: Node,
    control_branch: usize,
    gain: f64,
) {
    if let Some(positive) = positive {
        matrix.push(Triplet::new(positive, control_branch, gain));
    }
    if let Some(negative) = negative {
        matrix.push(Triplet::new(negative, control_branch, -gain));
    }
}

fn stamp_cccs_complex(
    matrix: &mut Vec<Triplet<usize, usize, c64>>,
    positive: Node,
    negative: Node,
    control_branch: usize,
    gain: f64,
) {
    if let Some(positive) = positive {
        matrix.push(Triplet::new(positive, control_branch, c64::new(gain, 0.0)));
    }
    if let Some(negative) = negative {
        matrix.push(Triplet::new(negative, control_branch, c64::new(-gain, 0.0)));
    }
}

fn stamp_ccvs_real(
    matrix: &mut Vec<Triplet<usize, usize, f64>>,
    rhs: &mut [f64],
    positive: Node,
    negative: Node,
    control_branch: usize,
    branch: usize,
    transresistance: f64,
) {
    stamp_branch_real(matrix, rhs, positive, negative, branch, 0.0, 0.0);
    matrix.push(Triplet::new(branch, control_branch, -transresistance));
}

fn stamp_ccvs_complex(
    matrix: &mut Vec<Triplet<usize, usize, c64>>,
    rhs: &mut [c64],
    positive: Node,
    negative: Node,
    control_branch: usize,
    branch: usize,
    transresistance: f64,
) {
    stamp_branch_complex(
        matrix,
        rhs,
        positive,
        negative,
        branch,
        c64::new(0.0, 0.0),
        c64::new(0.0, 0.0),
    );
    matrix.push(Triplet::new(
        branch,
        control_branch,
        c64::new(-transresistance, 0.0),
    ));
}

fn real_point(deck: &Deck, analysis: &str, x: f64, solution: &[f64]) -> SimulationPoint {
    let mut values = BTreeMap::new();
    for (index, name) in deck.nodes.iter().enumerate() {
        if selected_probe(deck, analysis, name) {
            values.insert(name.clone(), solution[index]);
        }
    }
    for (name, index) in &deck.branch_names {
        if selected_probe(deck, analysis, name) {
            values.insert(name.clone(), solution[*index]);
        }
    }
    SimulationPoint {
        analysis: analysis.into(),
        x,
        values,
        complex: BTreeMap::new(),
    }
}

fn complex_point(deck: &Deck, x: f64, solution: &[c64]) -> SimulationPoint {
    let mut complex = BTreeMap::new();
    for (index, name) in deck.nodes.iter().enumerate() {
        if selected_probe(deck, "ac", name) {
            complex.insert(
                name.clone(),
                ComplexSample {
                    re: solution[index].re,
                    im: solution[index].im,
                },
            );
        }
    }
    for (name, index) in &deck.branch_names {
        if selected_probe(deck, "ac", name) {
            complex.insert(
                name.clone(),
                ComplexSample {
                    re: solution[*index].re,
                    im: solution[*index].im,
                },
            );
        }
    }
    SimulationPoint {
        analysis: "ac".into(),
        x,
        values: BTreeMap::new(),
        complex,
    }
}

fn selected_probe(deck: &Deck, analysis: &str, name: &str) -> bool {
    let explicitly_selected = deck
        .probes
        .get(analysis)
        .is_none_or(|probes| probes.iter().any(|probe| probe.eq_ignore_ascii_case(name)));
    explicitly_selected
        || deck.measurements.iter().any(|measurement| {
            measurement.analysis.eq_ignore_ascii_case(analysis) && measurement.references(name)
        })
}

fn node_voltage(solution: &[f64], node: Node) -> f64 {
    node.map_or(0.0, |index| solution[index])
}

fn port_voltages(solution: &[f64], ports: &[Node], references: &[Node]) -> Vec<f64> {
    debug_assert_eq!(references.len(), ports.len());
    ports
        .iter()
        .zip(references)
        .map(|(port, reference)| node_voltage(solution, *port) - node_voltage(solution, *reference))
        .collect()
}

fn next_source_breakpoint(waveforms: &[&Waveform], time: f64, stop: f64) -> Option<f64> {
    waveforms
        .iter()
        .filter_map(|waveform| waveform.next_breakpoint_after(time, stop))
        .min_by(f64::total_cmp)
}

fn reached(value: f64, stop: f64, step: f64) -> bool {
    if step > 0.0 {
        value <= stop + step.abs() * 1e-9
    } else {
        value >= stop - step.abs() * 1e-9
    }
}

fn dc_output_count(start: f64, stop: f64, step: f64) -> usize {
    (((stop - start) / step + 1e-9).floor().max(0.0) as usize).saturating_add(1)
}

fn transient_output_count(step: f64, stop: f64) -> usize {
    let complete_steps = (stop / step).floor().max(0.0) as usize;
    let last_grid_time = complete_steps as f64 * step;
    1usize
        .saturating_add(complete_steps)
        .saturating_add(usize::from((last_grid_time - stop).abs() > step * 1e-9))
}

fn frequencies(scale: AcScale, points: usize, start: f64, stop: f64) -> Vec<f64> {
    match scale {
        AcScale::Linear => {
            if points == 1 {
                vec![start]
            } else {
                (0..points)
                    .map(|index| start + (stop - start) * index as f64 / (points - 1) as f64)
                    .collect()
            }
        }
        AcScale::Decade | AcScale::Octave => {
            let base: f64 = if matches!(scale, AcScale::Decade) {
                10.0
            } else {
                2.0
            };
            let factor = base.powf(1.0 / points as f64);
            let mut frequencies = Vec::new();
            let mut frequency = start;
            while frequency <= stop * (1.0 + 1e-12) {
                frequencies.push(frequency.min(stop));
                frequency *= factor;
            }
            frequencies
        }
    }
}
