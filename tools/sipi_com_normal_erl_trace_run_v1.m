function sipi_com_normal_erl_trace_run_v1(source_root, config_path, output_dir, num_fext, num_next, nonce, varargin)
%SIPI_COM_NORMAL_ERL_TRACE_RUN_V1 Run pinned COM and summarize ERL outputs.
%
% The normal trace sink is reached only when com_ieee8023_480.m is the
% instrumented archive copy.  The uninstrumented call uses this same wrapper
% and therefore proves that the instrumentation did not alter final outputs.

expected_file_count = 1 + num_fext + num_next;
if nargin ~= 6 + expected_file_count
    error('sipi_com_normal_erl_trace_run_v1:Arguments', 'Channel count does not match supplied files.');
end
if ~ischar(nonce) || numel(nonce) ~= 64 || any(~ismember(nonce, '0123456789abcdef'))
    error('sipi_com_normal_erl_trace_run_v1:Nonce', 'Nonce must be 64 lowercase hexadecimal characters.');
end
source_dir = fullfile(source_root, 'matlab_src');
if ~isfolder(source_dir)
    error('sipi_com_normal_erl_trace_run_v1:Source', 'MATLAB source directory does not exist.');
end
if ~isfolder(output_dir)
    mkdir(output_dir);
end
addpath(source_dir);
close all force;
lastwarn('');
started = tic;
try
    results = com_ieee8023_480(config_path, num_fext, num_next, varargin{:});
    elapsed = toc(started);
    [warning_message, warning_identifier] = lastwarn;
    if iscell(results)
        cases = results;
    else
        cases = {results};
    end
    if isempty(cases) || ~isstruct(cases{1})
        error('sipi_com_normal_erl_trace_run_v1:Result', 'COM returned no scalar result case.');
    end
    summaries = cell(1, numel(cases));
    for index = 1:numel(cases)
        summaries{index} = scalar_surface(cases{index});
    end
    summary = struct( ...
        'schema', 'sipi.com.normal-erl-trace-run.v1', ...
        'nonce', nonce, ...
        'matlab_release', version('-release'), ...
        'matlab_version', version, ...
        'duration_seconds', double(elapsed), ...
        'case_count', double(numel(cases)), ...
        'cases', {summaries}, ...
        'last_warning', struct('identifier', char(warning_identifier), 'message', char(warning_message)));
    write_atomic_text(fullfile(output_dir, 'summary.json'), jsonencode(summary, PrettyPrint=true));
catch ME
    failure = struct('identifier', ME.identifier, 'message', ME.message, ...
        'report', getReport(ME, 'extended', 'hyperlinks', 'off'));
    write_atomic_text(fullfile(output_dir, 'failure.json'), jsonencode(failure, PrettyPrint=true));
    rethrow(ME);
end
close all force;
end

function output = scalar_surface(result)
names = {'ERL', 'ERL11', 'ERL22', 'Z11est', 'Z22est'};
output = struct();
for index = 1:numel(names)
    name = names{index};
    if isfield(result, name)
        value = result.(name);
        if isnumeric(value) && isscalar(value)
            output.(name) = scalar_value(value);
        end
    end
end
end

function value = scalar_value(number)
if isnan(number)
    value = 'NaN';
elseif isinf(number)
    if number > 0
        value = '+Inf';
    else
        value = '-Inf';
    end
else
    value = double(number);
end
end

function write_atomic_text(path, text_value)
[directory, ~, ~] = fileparts(path);
temporary = [tempname(directory), '.json'];
file = fopen(temporary, 'w');
if file < 0
    error('sipi_com_normal_erl_trace_run_v1:Write', 'Cannot open summary output.');
end
cleanup = onCleanup(@() fclose(file));
fprintf(file, '%s\n', text_value);
clear cleanup;
[moved, message] = movefile(temporary, path, 'f');
if ~moved
    error('sipi_com_normal_erl_trace_run_v1:Write', 'Cannot publish summary: %s', message);
end
end
