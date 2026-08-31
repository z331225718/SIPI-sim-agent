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
    cases = result_cases(results);
    summaries = repmat(case_summary(cases{1}, 1), 1, numel(cases));
    for index = 1:numel(cases)
        summaries(index) = case_summary(cases{index}, index);
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

function summary = case_summary(result, case_index)
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
