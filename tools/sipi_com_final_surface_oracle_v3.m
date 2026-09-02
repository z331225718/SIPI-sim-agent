function sipi_com_final_surface_oracle_v3(repo_root, config_path, output_dir, num_fext, num_next, nonce, varargin)
%SIPI_COM_FINAL_SURFACE_ORACLE_V3 Run the pinned COM core and export scalars.
%
% This SIPI-owned harness deliberately does not save the full MATLAB results
% graph.  P5-06s accepts only the final scalar surface; serializing the graph
% can consume far more memory than the core calculation itself.

expected_file_count = 1 + num_fext + num_next;
if nargin ~= 6 + expected_file_count
    error('sipi_com_final_surface_oracle_v3:Arguments', ...
        'Channel count does not match the supplied files.');
end
if ~ischar(nonce) || numel(nonce) ~= 64 || any(~ismember(nonce, '0123456789abcdef'))
    error('sipi_com_final_surface_oracle_v3:Nonce', 'Nonce must be 64 lowercase hexadecimal characters.');
end
if ~isfolder(output_dir)
    mkdir(output_dir);
end

source_dir = fullfile(repo_root, 'matlab_src');
if ~isfolder(source_dir)
    error('sipi_com_final_surface_oracle_v3:Source', 'MATLAB source directory does not exist.');
end
addpath(source_dir);
close all force;

write_stage(output_dir, nonce, 'oracle_entered');
started_at = datetime('now', 'TimeZone', 'UTC', 'Format', "yyyy-MM-dd'T'HH:mm:ss'Z'");
run_timer = tic;
try
    write_parameter_bridge(config_path, output_dir);
    % Keep one output local to MATLAB.  Calling the pinned core with no
    % output makes it display its full result graph, which is both unrelated
    % to the scalar contract and unsafe for a noninteractive Engine session.
    % The graph is never saved or returned through the Engine boundary.
    results = com_ieee8023_480(config_path, num_fext, num_next, varargin{:});
    write_stage(output_dir, nonce, 'core_returned');

    case_metrics = final_scalar_metrics(results);
    summary = struct( ...
        'schema_version', 3, ...
        'started_at_utc', char(started_at), ...
        'duration_seconds', toc(run_timer), ...
        'matlab_release', version('-release'), ...
        'matlab_version', version, ...
        'case_count', numel(case_metrics), ...
        'summary_case_index', 1, ...
        'output_metrics', case_metrics(1).output_metrics);
    summary.case_metrics = num2cell(case_metrics);
    write_atomic_text(fullfile(output_dir, 'summary.json'), jsonencode(summary, PrettyPrint=true));
    write_stage(output_dir, nonce, 'summary_written');
catch ME
    failure = struct( ...
        'identifier', ME.identifier, ...
        'message', ME.message, ...
        'report', getReport(ME, 'extended', 'hyperlinks', 'off'));
    write_atomic_text(fullfile(output_dir, 'failure.json'), jsonencode(failure, PrettyPrint=true));
    write_stage(output_dir, nonce, 'oracle_exception');
    rethrow(ME);
end
close all force;
end

function write_parameter_bridge(config_path, output_dir)
% Confirm the exact cell matrix MATLAB will hand to the pinned core.  This is
% intentionally a cache-bridge receipt, not a serialized result graph.
loaded = load(config_path, 'parameter');
if ~isfield(loaded, 'parameter') || ~iscell(loaded.parameter)
    error('sipi_com_final_surface_oracle_v3:ParameterBridge', ...
        'MAT cache must provide a cell parameter matrix.');
end
parameter = loaded.parameter;
[rows, columns] = size(parameter);
slots = repmat(struct('row', 0, 'column', 0, 'kind', '', 'value', []), 1, rows * columns);
slot_index = 1;
for row = 1:rows
    for column = 1:columns
        raw = parameter{row, column};
        slots(slot_index).row = double(row - 1);
        slots(slot_index).column = double(column - 1);
        if isempty(raw)
            slots(slot_index).kind = 'blank';
            slots(slot_index).value = '';
        elseif isnumeric(raw) && isscalar(raw) && isfinite(raw)
            slots(slot_index).kind = 'number';
            slots(slot_index).value = double(raw);
        elseif ischar(raw)
            slots(slot_index).kind = 'string';
            slots(slot_index).value = raw;
        else
            error('sipi_com_final_surface_oracle_v3:ParameterBridge', ...
                'MAT cache contains an unsupported parameter cell.');
        end
        slot_index = slot_index + 1;
    end
end
bridge = struct('shape', [double(rows), double(columns)], 'slots', slots);
write_atomic_text(fullfile(output_dir, 'parameter-bridge.json'), jsonencode(bridge));
end

function metrics = final_scalar_metrics(results)
if iscell(results)
    cases = results;
else
    cases = {results};
end
names = { ...
    'COM_dB', 'CTLE_DC_gain_dB', 'ERL', 'FOM', 'ICN_mV', ...
    'IL_dB_channel_only_at_Fnq', 'Peak_ISI_XTK_and_Noise_interference_at_BER_mV', ...
    'VEC_dB', 'VEO_mV', 'fitted_IL_dB_at_Fnq', 'g_DC_HP', 'itick'};
metrics = repmat(struct('case_index', 0, 'output_metrics', struct()), 1, numel(cases));
for case_index = 1:numel(cases)
    result = cases{case_index};
    output = struct();
    for name_index = 1:numel(names)
        name = names{name_index};
        if isfield(result, name)
            value = result.(name);
            if isnumeric(value) && isscalar(value)
                output.(name) = scalar_value(value);
            end
        end
    end
    metrics(case_index).case_index = case_index;
    metrics(case_index).output_metrics = output;
end
end

function value = scalar_value(number)
if isnan(number)
    value = struct('kind', 'nan');
elseif isinf(number)
    if number > 0
        value = struct('kind', 'inf');
    else
        value = struct('kind', '-inf');
    end
else
    value = struct('kind', 'finite', 'value', double(number));
end
end

function write_stage(output_dir, nonce, stage)
payload = struct('schema', 'sipi.com.final-surface-stage.v3', 'nonce', nonce, 'stage', stage);
write_atomic_text(fullfile(output_dir, 'stage.json'), jsonencode(payload));
end

function write_atomic_text(path, text_value)
[directory, ~, ~] = fileparts(path);
temporary = [tempname(directory), '.json'];
file_id = fopen(temporary, 'w');
if file_id < 0
    error('sipi_com_final_surface_oracle_v3:Write', 'Cannot open output file.');
end
cleanup = onCleanup(@() fclose(file_id));
fprintf(file_id, '%s\n', text_value);
clear cleanup;
[moved, message] = movefile(temporary, path, 'f');
if ~moved
    error('sipi_com_final_surface_oracle_v3:Write', 'Cannot publish output: %s', message);
end
end
