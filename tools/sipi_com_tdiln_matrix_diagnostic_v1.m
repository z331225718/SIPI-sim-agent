function sipi_com_tdiln_matrix_diagnostic_v1(repo_root, config_path, output_dir, num_fext, num_next, nonce, varargin)
%SIPI_COM_TDILN_MATRIX_DIAGNOSTIC_V1 Measure all source package cases with TDILN.
%
% This diagnostic calls the pinned MATLAB COM implementation once. It exports
% only bounded scalar/vector summaries, not the complete MATLAB result graph.
% An optional final override pair is limited to OP.COMPUTE_TDILN=1 so the
% workbook remains an external source input and the diagnostic has no generic
% MATLAB eval surface of its own.

expected_file_count = 1 + num_fext + num_next;
argument_count = nargin - 6;
if argument_count < expected_file_count || mod(argument_count - expected_file_count, 2) ~= 0
    error('sipi_com_tdiln_matrix_diagnostic_v1:Arguments', ...
        'Channel count does not match supplied files and optional override pairs.');
end
if ~ischar(nonce) || numel(nonce) ~= 64 || any(~ismember(nonce, '0123456789abcdef'))
    error('sipi_com_tdiln_matrix_diagnostic_v1:Nonce', ...
        'Nonce must be 64 lowercase hexadecimal characters.');
end
channel_args = varargin(1:expected_file_count);
override_args = varargin(expected_file_count + 1:end);
if ~isempty(override_args)
    if numel(override_args) ~= 2 || ~isequal(override_args{1}, 'OP.COMPUTE_TDILN') || ...
            ~isequal(override_args{2}, '1')
        error('sipi_com_tdiln_matrix_diagnostic_v1:Override', ...
            'Only OP.COMPUTE_TDILN=1 is admitted by this diagnostic.');
    end
end
if ~isfolder(output_dir)
    mkdir(output_dir);
end

source_dir = fullfile(repo_root, 'matlab_src');
if ~isfolder(source_dir)
    error('sipi_com_tdiln_matrix_diagnostic_v1:Source', ...
        'MATLAB source directory does not exist.');
end
addpath(source_dir);
warning_capture = begin_warning_capture(source_dir);
warning_capture_cleanup = onCleanup(@() end_warning_capture(warning_capture));
close all force;

write_atomic_text(fullfile(output_dir, 'stage.json'), jsonencode(struct( ...
    'schema', 'sipi.com.tdiln-matrix-diagnostic-stage.v1', ...
    'nonce', nonce, 'stage', 'oracle_entered')));
try
    % MATLAB exposes only a process-global last warning. It is recorded as a
    % branch observation, never as a complete warning list or count parity.
    lastwarn('');
    run_timer = tic;
    results = com_ieee8023_480(config_path, num_fext, num_next, channel_args{:}, override_args{:});
    duration_seconds = toc(run_timer);
    [last_warning_message, last_warning_identifier] = lastwarn;
    global SIPI_COM_WARNING_CAPTURE_V1;
    if ~isstruct(SIPI_COM_WARNING_CAPTURE_V1) || ...
            SIPI_COM_WARNING_CAPTURE_V1.capture_incomplete
        reason = 'missing_capture_state';
        if isstruct(SIPI_COM_WARNING_CAPTURE_V1) && ...
                isfield(SIPI_COM_WARNING_CAPTURE_V1, 'incomplete_reason')
            reason = SIPI_COM_WARNING_CAPTURE_V1.incomplete_reason;
        end
        error('sipi_com_tdiln_matrix_diagnostic_v1:WarningCapture', ...
            'Pinned-source warning capture was incomplete: %s.', reason);
    end
    cases = result_cases(results);
    summaries = repmat(case_summary(cases{1}, 1, output_dir), 1, numel(cases));
    for index = 1:numel(cases)
        summaries(index) = case_summary(cases{index}, index, output_dir);
    end
    summary = struct( ...
        'schema', 'sipi.com.tdiln-matrix-diagnostic.v1', ...
        'diagnostic_only', true, ...
        'non_claims', {{'not_release_evidence', 'not_full_result_serialization', ...
            'not_complete_warning_catalog'}}, ...
        'nonce', nonce, ...
        'matlab_release', version('-release'), ...
        'matlab_version', version, ...
        'core_duration_seconds', double(duration_seconds), ...
        'override', struct('name', 'OP.COMPUTE_TDILN', 'value', 1, ...
            'applied', ~isempty(override_args)), ...
        'last_warning', struct( ...
            'capture', 'matlab_lastwarn_only', ...
            'identifier', char(last_warning_identifier), ...
            'message', char(last_warning_message), ...
            'full_warning_catalog_coverage', false), ...
        'source_warning_calls', struct( ...
            'schema', 'sipi.com.pinned-source-warning-call-observation.v1', ...
            'source_local_only', true, ...
            'source_emission_callsite_filter', 'pinned-com_ieee8023_480.m static emission lines only', ...
            'matlab_internal_warning_coverage', false, ...
            'capture_incomplete', false, ...
            'events', {SIPI_COM_WARNING_CAPTURE_V1.events}), ...
        'case_count', numel(summaries));
    % A scalar MATLAB struct encodes as a JSON object. Keep the wire shape
    % stable for one-case ERL-only workbooks and package sweeps alike.
    summary.cases = num2cell(summaries);
    write_atomic_text(fullfile(output_dir, 'summary.json'), jsonencode(summary, PrettyPrint=true));
    write_atomic_text(fullfile(output_dir, 'stage.json'), jsonencode(struct( ...
        'schema', 'sipi.com.tdiln-matrix-diagnostic-stage.v1', ...
        'nonce', nonce, 'stage', 'summary_written')));
catch ME
    failure = struct('identifier', ME.identifier, 'message', ME.message, ...
        'report', getReport(ME, 'extended', 'hyperlinks', 'off'));
    write_atomic_text(fullfile(output_dir, 'failure.json'), jsonencode(failure, PrettyPrint=true));
    rethrow(ME);
end
close all force;
end

function capture = begin_warning_capture(source_dir)
% Add a temporary diagnostic observer before the pinned source. It forwards
% every call to builtin warning and observes only pinned static callsites.
capture_dir = fullfile(fileparts(mfilename('fullpath')), 'matlab_warning_capture_v1');
shim = fullfile(capture_dir, 'warning.m');
source_file = fullfile(source_dir, 'com_ieee8023_480.m');
if ~isfile(shim) || ~isfile(source_file)
    error('sipi_com_tdiln_matrix_diagnostic_v1:WarningCapture', ...
        'Warning observer or pinned source is missing.');
end
addpath(capture_dir, '-begin');
clear warning;
resolved = which('warning');
if ~strcmp(resolved, shim)
    error('sipi_com_tdiln_matrix_diagnostic_v1:WarningCapture', ...
        'Warning observer did not take precedence.');
end
global SIPI_COM_WARNING_CAPTURE_V1 SIPI_COM_WARNING_CAPTURE_DELEGATING_V1;
SIPI_COM_WARNING_CAPTURE_V1 = struct( ...
    'enabled', true, ...
    'source_file', source_file, ...
    'source_emission_lines', [2109 2228 2238 6337 8660 9243 9715 9720 9727 9731 10008 10055], ...
    'interpolation_input_trace_lines', 6337, ...
    'events', {{}}, ...
    'capture_incomplete', false, ...
    'incomplete_reason', '');
SIPI_COM_WARNING_CAPTURE_DELEGATING_V1 = false;
capture = struct('directory', capture_dir);
end

function end_warning_capture(capture)
global SIPI_COM_WARNING_CAPTURE_V1 SIPI_COM_WARNING_CAPTURE_DELEGATING_V1;
SIPI_COM_WARNING_CAPTURE_V1 = [];
SIPI_COM_WARNING_CAPTURE_DELEGATING_V1 = [];
if isstruct(capture) && isfield(capture, 'directory') && isfolder(capture.directory)
    rmpath(capture.directory);
end
clear warning;
end

function cases = result_cases(results)
if iscell(results)
    cases = results;
else
    cases = {results};
end
if isempty(cases) || any(~cellfun(@(result) isstruct(result) && numel(result) == 1, cases))
    error('sipi_com_tdiln_matrix_diagnostic_v1:Result', ...
        'COM must return one or more scalar result structs.');
end
end

function summary = case_summary(result, case_index, output_dir)
summary = struct( ...
    'case_index', double(case_index - 1), ...
    'com_db', optional_scalar(result, 'COM_dB'), ...
    'erl_db', optional_scalar(result, 'ERL'), ...
    'tdiln_applicable', false, ...
    'tdiln_inapplicable_reason', 'source_did_not_emit_FOM_TDILN_and_TD_ILN', ...
    'fom_tdiln', [], ...
    'tdiln', []);
if ~isfield(result, 'FOM_TDILN') || ~isfield(result, 'TD_ILN') || isempty(result.TD_ILN)
    return
end
td = result.TD_ILN;
required = {'t', 'ILN', 'FOM', 'FOM_PDF', 'SNR_ISI_FOM', 'SNR_ISI_FOM_PDF', 'REF', 'FIT'};
for index = 1:numel(required)
    if ~isfield(td, required{index})
        error('sipi_com_tdiln_matrix_diagnostic_v1:TdilnShape', ...
            'TD_ILN is missing %s.', required{index});
    end
end
summary.tdiln_applicable = true;
summary.tdiln_inapplicable_reason = [];
summary.fom_tdiln = finite_scalar(result.FOM_TDILN);
summary.tdiln = struct( ...
        'fom', finite_scalar(td.FOM), ...
        'fom_pdf', finite_scalar(td.FOM_PDF), ...
        'snr_isi_fom', finite_scalar(td.SNR_ISI_FOM), ...
        'snr_isi_fom_pdf', finite_scalar(td.SNR_ISI_FOM_PDF), ...
        'time', vector_summary(td.t), ...
        'iln', vector_summary(td.ILN), ...
        'reference_pr', vector_summary(td.REF.PR), ...
        'fitted_pr', vector_summary(td.FIT.PR));
write_tdiln_sidecar(td, case_index - 1, output_dir);
end

function write_tdiln_sidecar(td, case_index, output_dir)
% Diagnostic-only, repository-external array receipts. These preserve source
% order and f64 bytes for the comparator, never the public result wire.
root = fullfile(output_dir, 'tdiln-sidecar', sprintf('case-%d', case_index));
if ~isfolder(root)
    mkdir(root);
end
vectors = struct( ...
    'time_s', double(td.t(:)), ...
    'iln_pulse', double(td.ILN(:)), ...
    'reference_pulse', double(td.REF.PR(:)), ...
    'fitted_pulse', double(td.FIT.PR(:)), ...
    'pdf_axis', double(td.PDF.x(:)), ...
    'pdf_probability', double(td.PDF.y(:)));
names = fieldnames(vectors);
entries = struct();
for index = 1:numel(names)
    name = names{index};
    values = vectors.(name);
    if isempty(values) || any(~isfinite(values))
        error('sipi_com_tdiln_matrix_diagnostic_v1:Sidecar', ...
            'TDILN sidecar %s must be finite and nonempty.', name);
    end
    filename = [name '.f64le'];
    write_f64le(fullfile(root, filename), values);
    entries.(name) = struct( ...
        'file', filename, 'dtype', 'f64le', 'shape', double(numel(values)), ...
        'bytes', double(numel(values) * 8));
end
manifest = struct( ...
    'schema', 'sipi.com.tdiln-array-sidecar.v1', ...
    'diagnostic_only', true, ...
    'tdiln_applicable', true, ...
    'case_index', double(case_index), ...
    'vectors', entries, ...
    'pdf', struct('bin_size', finite_scalar(td.PDF.BinSize), 'min_bin', double(td.PDF.Min)), ...
    'selected_phase', [], ...
    'scalars', struct( ...
        'fom_v', finite_scalar(td.FOM), ...
        'fom_pdf_v', finite_scalar(td.FOM_PDF), ...
        'snr_isi_fom_db', finite_scalar(td.SNR_ISI_FOM), ...
        'snr_isi_fom_pdf_db', finite_scalar(td.SNR_ISI_FOM_PDF)), ...
    'non_claims', {{'not_public_result_wire', 'not_channel_s_parameter_fit', 'not_full_result_graph'}});
write_atomic_text(fullfile(root, 'manifest.json'), jsonencode(manifest, PrettyPrint=true));
end

function write_f64le(path, values)
file = fopen(path, 'W', 'ieee-le');
if file < 0
    error('sipi_com_tdiln_matrix_diagnostic_v1:Write', 'Cannot open sidecar file.');
end
cleanup = onCleanup(@() fclose(file));
count = fwrite(file, values, 'double');
if count ~= numel(values)
    error('sipi_com_tdiln_matrix_diagnostic_v1:Write', 'Cannot write full sidecar file.');
end
end

function value = optional_scalar(result, name)
if ~isfield(result, name)
    value = [];
else
    value = finite_or_special_scalar(result.(name));
end
end

function value = finite_or_special_scalar(number)
number = double(number);
if ~isscalar(number)
    error('sipi_com_tdiln_matrix_diagnostic_v1:Nonfinite', ...
        'Diagnostic scalar must be one numeric scalar.');
end
if isfinite(number)
    value = number;
elseif isinf(number) && number > 0
    value = '+Inf';
elseif isinf(number)
    value = '-Inf';
else
    value = 'NaN';
end
end

function summary = vector_summary(value)
value = double(value(:));
if isempty(value) || any(~isfinite(value))
    error('sipi_com_tdiln_matrix_diagnostic_v1:Nonfinite', ...
        'TDILN diagnostic vectors must be finite and nonempty.');
end
summary = struct( ...
    'length', double(numel(value)), ...
    'first', value(1), ...
    'last', value(end), ...
    'minimum', min(value), ...
    'maximum', max(value), ...
    'sum', sum(value), ...
    'sum_squares', sum(value .* value));
end

function value = finite_scalar(number)
number = double(number);
if ~isscalar(number) || ~isfinite(number)
    error('sipi_com_tdiln_matrix_diagnostic_v1:Nonfinite', ...
        'TDILN diagnostic scalars must be finite.');
end
value = number;
end

function write_atomic_text(path, text_value)
[directory, ~, ~] = fileparts(path);
temporary = [tempname(directory), '.json'];
file_id = fopen(temporary, 'w');
if file_id < 0
    error('sipi_com_tdiln_matrix_diagnostic_v1:Write', 'Cannot open output file.');
end
cleanup = onCleanup(@() fclose(file_id));
fprintf(file_id, '%s\n', text_value);
clear cleanup;
[moved, message] = movefile(temporary, path, 'f');
if ~moved
    error('sipi_com_tdiln_matrix_diagnostic_v1:Write', ...
        'Cannot publish output: %s', message);
end
end
