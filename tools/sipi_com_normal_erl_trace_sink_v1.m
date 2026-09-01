function sipi_com_normal_erl_trace_sink_v1(chdata, OP, package_testcase_i)
%SIPI_COM_NORMAL_ERL_TRACE_SINK_V1 Write a private TDR/PTDR trace receipt.
%
% The pinned COM source calls this function only in an archive-local,
% instrumented copy.  It reads completed TDR values and writes no source
% variables.  This is deliberately not a public COM result format.

root = getenv('SIPI_COM_NORMAL_ERL_TRACE_DIR');
if isempty(root)
    return
end
if package_testcase_i ~= 1 || ~isfield(OP, 'TDR') || ~OP.TDR || ...
        ~isfield(OP, 'ERL') || ~OP.ERL
    return
end
if ~isstruct(chdata) || isempty(chdata) || ...
        ~isfield(chdata(1), 'TDR11') || ~isfield(chdata(1), 'PDTR11')
    error('sipi_com_normal_erl_trace_sink_v1:Input', ...
        'Normal ERL trace requires completed first-port TDR and PTDR data.');
end

if ~isfolder(root)
    mkdir(root);
end
ports = cell(1, 2);
ports{1} = write_port(root, 1, chdata(1).TDR11, chdata(1).PDTR11);
if isfield(chdata(1), 'TDR22') && isfield(chdata(1), 'PDTR22') && ...
        ~isempty(chdata(1).TDR22) && ~isempty(chdata(1).PDTR22)
    ports{2} = write_port(root, 2, chdata(1).TDR22, chdata(1).PDTR22);
else
    ports{2} = struct('port', 2, 'available', false);
end

manifest = struct( ...
    'schema', 'sipi.com.normal-erl-array-trace.v1', ...
    'diagnostic_only', true, ...
    'package_testcase_index', double(package_testcase_i - 1), ...
    'ports', {ports}, ...
    'non_claims', {{'not_public_result_wire', 'not_source_modification', ...
        'not_full_result_graph', 'not_channel_s_parameter_fit'}});
write_atomic_text(fullfile(root, 'manifest.json'), jsonencode(manifest, PrettyPrint=true));
end

function entry = write_port(root, port, tdr, ptdr)
if numel(tdr) ~= 1 || numel(ptdr) ~= 1 || ...
        ~isfield(tdr, 't') || ~isfield(tdr, 'ZSR') || ...
        ~isfield(ptdr, 'ptdr') || ~isfield(ptdr, 'ptdr_raw')
    error('sipi_com_normal_erl_trace_sink_v1:Port', ...
        'Normal ERL trace port must have one completed TDR/PTDR result.');
end
vectors = struct( ...
    'time_s', double(tdr.t(:)), ...
    'impedance_ohm', double(tdr.ZSR(:)), ...
    'ptdr', double(ptdr.ptdr_raw(:)), ...
    'gated', double(ptdr.ptdr(:)));
names = fieldnames(vectors);
entries = struct();
port_root = fullfile(root, sprintf('port-%d', port));
if ~isfolder(port_root)
    mkdir(port_root);
end
for index = 1:numel(names)
    name = names{index};
    values = vectors.(name);
    if isempty(values) || any(~isfinite(values))
        error('sipi_com_normal_erl_trace_sink_v1:Finite', ...
            'Trace vector %s must be finite and nonempty.', name);
    end
    filename = [name '.f64le'];
    write_f64le(fullfile(port_root, filename), values);
    entries.(name) = struct( ...
        'file', fullfile(sprintf('port-%d', port), filename), ...
        'dtype', 'f64le', ...
        'shape', double(numel(values)), ...
        'bytes', double(numel(values) * 8));
end
entry = struct('port', double(port), 'available', true, 'vectors', entries);
end

function write_f64le(path, values)
file = fopen(path, 'W', 'ieee-le');
if file < 0
    error('sipi_com_normal_erl_trace_sink_v1:Write', 'Cannot open trace vector.');
end
cleanup = onCleanup(@() fclose(file));
count = fwrite(file, values, 'double');
if count ~= numel(values)
    error('sipi_com_normal_erl_trace_sink_v1:Write', 'Cannot write full trace vector.');
end
end

function write_atomic_text(path, text_value)
[directory, ~, ~] = fileparts(path);
temporary = [tempname(directory), '.json'];
file = fopen(temporary, 'w');
if file < 0
    error('sipi_com_normal_erl_trace_sink_v1:Write', 'Cannot open trace manifest.');
end
cleanup = onCleanup(@() fclose(file));
fprintf(file, '%s\n', text_value);
clear cleanup;
[moved, message] = movefile(temporary, path, 'f');
if ~moved
    error('sipi_com_normal_erl_trace_sink_v1:Write', ...
        'Cannot publish trace manifest: %s', message);
end
end
