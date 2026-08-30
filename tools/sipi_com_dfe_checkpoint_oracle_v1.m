function sipi_com_dfe_checkpoint_oracle_v1(repo_root, config_path, output_dir, num_fext, num_next, nonce, varargin)
%SIPI_COM_DFE_CHECKPOINT_ORACLE_V1 Export only source-visible DFE winners.
expected_file_count = 1 + num_fext + num_next;
if nargin ~= 6 + expected_file_count
    error('sipi_com_dfe_checkpoint_oracle_v1:Arguments', 'Channel count does not match the supplied files.');
end
if ~ischar(nonce) || numel(nonce) ~= 64 || any(~ismember(nonce, '0123456789abcdef'))
    error('sipi_com_dfe_checkpoint_oracle_v1:Nonce', 'Nonce must be 64 lowercase hexadecimal characters.');
end
if ~isfolder(output_dir), mkdir(output_dir); end
source_dir = fullfile(repo_root, 'matlab_src');
if ~isfolder(source_dir), error('sipi_com_dfe_checkpoint_oracle_v1:Source', 'MATLAB source directory does not exist.'); end
addpath(source_dir); close all force;
write_stage(output_dir, nonce, 'oracle_entered');
started_at = datetime('now', 'TimeZone', 'UTC', 'Format', "yyyy-MM-dd'T'HH:mm:ss'Z'");
run_timer = tic;
try
    results = com_ieee8023_480(config_path, num_fext, num_next, varargin{:});
    checkpoints = case_checkpoints(results);
    summary = struct('schema_version', 1, 'started_at_utc', char(started_at), ...
        'duration_seconds', toc(run_timer), 'matlab_release', version('-release'), ...
        'matlab_version', version, 'diagnostic_only', true, ...
        'non_claims', {{'not_acceptance', 'not_full_result_graph', 'not_public_product_api'}});
    summary.case_count = numel(checkpoints);
    summary.case_checkpoints = num2cell(checkpoints);
    write_atomic_text(fullfile(output_dir, 'summary.json'), jsonencode(summary, PrettyPrint=true));
    write_stage(output_dir, nonce, 'summary_written');
catch ME
    failure = struct('identifier', ME.identifier, 'message', ME.message, 'report', getReport(ME, 'extended', 'hyperlinks', 'off'));
    write_atomic_text(fullfile(output_dir, 'failure.json'), jsonencode(failure, PrettyPrint=true));
    write_stage(output_dir, nonce, 'oracle_exception'); rethrow(ME);
end
close all force;
end

function checkpoints = case_checkpoints(results)
if iscell(results), cases = results; else, cases = {results}; end
checkpoints = repmat(struct('case_index', 0, 'applicable', false, 'final_scalar_metrics', struct(), 'dfe_taps', struct()), 1, numel(cases));
for case_index = 1:numel(cases)
    result = cases{case_index};
    if ~isstruct(result) || numel(result) ~= 1, error('sipi_com_dfe_checkpoint_oracle_v1:Result', 'Each returned COM case must be one scalar struct.'); end
    checkpoints(case_index).case_index = case_index;
    checkpoints(case_index).final_scalar_metrics = final_scalar_metrics(result);
    if isfield(result, 'DFE_taps')
        checkpoints(case_index).applicable = true;
        checkpoints(case_index).dfe_taps = vector_checkpoint(result.DFE_taps);
    else
        checkpoints(case_index).dfe_taps = struct('reason', 'source_DFE_taps_missing_due_to_ERL_ONLY');
    end
end
end

function output = final_scalar_metrics(result)
names = {'COM_dB', 'CTLE_DC_gain_dB', 'ERL', 'FOM', 'ICN_mV', 'IL_dB_channel_only_at_Fnq', 'Peak_ISI_XTK_and_Noise_interference_at_BER_mV', 'VEC_dB', 'VEO_mV', 'fitted_IL_dB_at_Fnq', 'g_DC_HP', 'itick'};
output = struct();
for name_index = 1:numel(names)
    name = names{name_index};
    if isfield(result, name) && isnumeric(result.(name)) && isscalar(result.(name)), output.(name) = scalar_value(result.(name)); end
end
end

function checkpoint = vector_checkpoint(value)
if ~isa(value, 'double') || ~isreal(value) || (~isvector(value) && ~isempty(value)) || any(~isfinite(value(:)))
    error('sipi_com_dfe_checkpoint_oracle_v1:DFE', 'DFE_taps must be a finite real double vector or empty double.');
end
column_major = reshape(double(value), 1, []);
checkpoint = struct('class', 'double', 'shape', double(size(value)), 'value_count', double(numel(value)), ...
    'storage_order', 'matlab_column_major', 'semantic_axis', 'postcursor_ui_offsets_from_winner_cursor', ...
    'axis_origin_ui', 1, 'axis_step_ui', 1, 'unit', 'ratio', ...
    'encoding', 'ieee754_f64_little_endian_column_major', 'raw_f64_sha256', sha256_bytes(typecast(value(:), 'uint8')));
checkpoint.column_major_values = num2cell(column_major);
% jsonencode may shorten decimal literals.  Keep the exact MATLAB doubles as
% a transport receipt so the Python projector never reconstructs them from
% presentation decimals.
raw_bytes = typecast(value(:), 'uint8');
checkpoint.raw_f64_le_hex = lower(reshape(dec2hex(raw_bytes, 2).', 1, []));
end

function value = scalar_value(number)
if isnan(number), value = struct('kind', 'nan'); elseif isinf(number) && number > 0, value = struct('kind', 'inf'); elseif isinf(number), value = struct('kind', '-inf'); else, value = struct('kind', 'finite', 'value', double(number)); end
end

function digest = sha256_bytes(bytes)
engine = java.security.MessageDigest.getInstance('SHA-256'); engine.update(bytes); raw = typecast(engine.digest(), 'uint8'); digest = lower(reshape(dec2hex(raw, 2).', 1, []));
end

function write_stage(output_dir, nonce, stage)
write_atomic_text(fullfile(output_dir, 'stage.json'), jsonencode(struct('schema', 'sipi.com.dfe-checkpoint-stage.v1', 'nonce', nonce, 'stage', stage)));
end

function write_atomic_text(path, text_value)
[directory, ~, ~] = fileparts(path); temporary = [tempname(directory), '.json']; file_id = fopen(temporary, 'w');
if file_id < 0, error('sipi_com_dfe_checkpoint_oracle_v1:Write', 'Cannot open output file.'); end
cleanup = onCleanup(@() fclose(file_id)); fprintf(file_id, '%s\n', text_value); clear cleanup;
[moved, message] = movefile(temporary, path, 'f'); if ~moved, error('sipi_com_dfe_checkpoint_oracle_v1:Write', 'Cannot publish output: %s', message); end
end
