function sipi_com_tdiln_diagnostic_v1(repo_root, config_path, output_dir, num_fext, num_next, nonce, varargin)
%SIPI_COM_TDILN_DIAGNOSTIC_V1 Measure the legacy TDILN result and core time.
%
% This is deliberately a diagnostic harness, not a release oracle.  It keeps
% MATLAB startup outside the reported core duration, calls the pinned COM
% implementation once, and exports only finite scalar/vector summaries.  The
% narrow surface is sufficient to compare the direct Rust TDILN leaf without
% serializing MATLAB's complete result graph.

expected_file_count = 1 + num_fext + num_next;
if nargin ~= 6 + expected_file_count
    error('sipi_com_tdiln_diagnostic_v1:Arguments', ...
        'Channel count does not match the supplied files.');
end
if ~ischar(nonce) || numel(nonce) ~= 64 || any(~ismember(nonce, '0123456789abcdef'))
    error('sipi_com_tdiln_diagnostic_v1:Nonce', ...
        'Nonce must be 64 lowercase hexadecimal characters.');
end
if ~isfolder(output_dir)
    mkdir(output_dir);
end

source_dir = fullfile(repo_root, 'matlab_src');
if ~isfolder(source_dir)
    error('sipi_com_tdiln_diagnostic_v1:Source', 'MATLAB source directory does not exist.');
end
addpath(source_dir);
close all force;

write_atomic_text(fullfile(output_dir, 'stage.json'), jsonencode(struct( ...
    'schema', 'sipi.com.tdiln-diagnostic-stage.v1', 'nonce', nonce, 'stage', 'oracle_entered')));
try
    run_timer = tic;
    results = com_ieee8023_480(config_path, num_fext, num_next, varargin{:});
    duration_seconds = toc(run_timer);
    result = first_case(results);
    if ~isfield(result, 'FOM_TDILN') || ~isfield(result, 'TD_ILN') || isempty(result.TD_ILN)
        error('sipi_com_tdiln_diagnostic_v1:MissingTdiln', ...
            'COMPUTE_TDILN did not produce FOM_TDILN and TD_ILN.');
    end
    td = result.TD_ILN;
    required = {'t', 'ILN', 'FOM', 'FOM_PDF', 'SNR_ISI_FOM', 'SNR_ISI_FOM_PDF', 'REF', 'FIT'};
    for index = 1:numel(required)
        if ~isfield(td, required{index})
            error('sipi_com_tdiln_diagnostic_v1:TdilnShape', ...
                'TD_ILN is missing %s.', required{index});
        end
    end
    summary = struct( ...
        'schema', 'sipi.com.tdiln-diagnostic.v1', ...
        'diagnostic_only', true, ...
        'non_claims', {{'not_release_evidence', 'not_full_result_serialization'}}, ...
        'nonce', nonce, ...
        'matlab_release', version('-release'), ...
        'matlab_version', version, ...
        'core_duration_seconds', double(duration_seconds), ...
        'fom_tdiln', finite_scalar(result.FOM_TDILN), ...
        'tdiln', struct( ...
            'fom', finite_scalar(td.FOM), ...
            'fom_pdf', finite_scalar(td.FOM_PDF), ...
            'snr_isi_fom', finite_scalar(td.SNR_ISI_FOM), ...
            'snr_isi_fom_pdf', finite_scalar(td.SNR_ISI_FOM_PDF), ...
            'time', vector_summary(td.t), ...
            'iln', vector_summary(td.ILN), ...
            'reference_pr', vector_summary(td.REF.PR), ...
            'fitted_pr', vector_summary(td.FIT.PR)));
    write_atomic_text(fullfile(output_dir, 'summary.json'), jsonencode(summary, PrettyPrint=true));
    write_atomic_text(fullfile(output_dir, 'stage.json'), jsonencode(struct( ...
        'schema', 'sipi.com.tdiln-diagnostic-stage.v1', 'nonce', nonce, 'stage', 'summary_written')));
catch ME
    failure = struct('identifier', ME.identifier, 'message', ME.message, ...
        'report', getReport(ME, 'extended', 'hyperlinks', 'off'));
    write_atomic_text(fullfile(output_dir, 'failure.json'), jsonencode(failure, PrettyPrint=true));
    rethrow(ME);
end
close all force;
end

function result = first_case(results)
if iscell(results)
    if isempty(results)
        error('sipi_com_tdiln_diagnostic_v1:Result', 'COM returned no cases.');
    end
    result = results{1};
else
    result = results;
end
if ~isstruct(result) || numel(result) ~= 1
    error('sipi_com_tdiln_diagnostic_v1:Result', 'COM must return one scalar result struct.');
end
end

function summary = vector_summary(value)
value = double(value(:));
if isempty(value) || any(~isfinite(value))
    error('sipi_com_tdiln_diagnostic_v1:Nonfinite', 'TDILN diagnostic vectors must be finite and nonempty.');
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
    error('sipi_com_tdiln_diagnostic_v1:Nonfinite', 'TDILN diagnostic scalars must be finite.');
end
value = number;
end

function write_atomic_text(path, text_value)
[directory, ~, ~] = fileparts(path);
temporary = [tempname(directory), '.json'];
file_id = fopen(temporary, 'w');
if file_id < 0
    error('sipi_com_tdiln_diagnostic_v1:Write', 'Cannot open output file.');
end
cleanup = onCleanup(@() fclose(file_id));
fprintf(file_id, '%s\n', text_value);
clear cleanup;
[moved, message] = movefile(temporary, path, 'f');
if ~moved
    error('sipi_com_tdiln_diagnostic_v1:Write', 'Cannot publish output: %s', message);
end
end
