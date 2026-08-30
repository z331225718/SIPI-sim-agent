function sipi_com_result_surface_inventory_v1(repo_root, config_path, output_dir, num_fext, num_next, nonce, varargin)
%SIPI_COM_RESULT_SURFACE_INVENTORY_V1 Observe the legacy result surface.
%
% This diagnostic harness is deliberately outside the product runtime.  It
% invokes the pinned MATLAB implementation once, then records a bounded,
% deterministic inventory of its returned output fields.  It neither changes
% COM controls nor re-runs any numerical stage.  The inventory is for choosing
% the next direct-port comparison surface; it is not acceptance evidence.

expected_file_count = 1 + num_fext + num_next;
if nargin ~= 6 + expected_file_count
    error('sipi_com_result_surface_inventory_v1:Arguments', ...
        'Channel count does not match the supplied files.');
end
if ~ischar(nonce) || numel(nonce) ~= 64 || any(~ismember(nonce, '0123456789abcdef'))
    error('sipi_com_result_surface_inventory_v1:Nonce', ...
        'Nonce must be 64 lowercase hexadecimal characters.');
end
if ~isfolder(output_dir)
    mkdir(output_dir);
end
source_dir = fullfile(repo_root, 'matlab_src');
if ~isfolder(source_dir)
    error('sipi_com_result_surface_inventory_v1:Source', 'MATLAB source directory does not exist.');
end
addpath(source_dir);
close all force;

write_stage(output_dir, nonce, 'oracle_entered');
try
    results = com_ieee8023_480(config_path, num_fext, num_next, varargin{:});
    write_stage(output_dir, nonce, 'core_returned');
    inventory = inventory_results(results);
    inventory.schema = 'sipi.com.result-surface-inventory.v1';
    inventory.matlab_release = version('-release');
    inventory.matlab_version = version;
    inventory.nonce = nonce;
    inventory.diagnostic_only = true;
    inventory.non_claims = {'not_acceptance', 'not_numeric_parity', 'not_public_product_api'};
    write_atomic_text(fullfile(output_dir, 'inventory.json'), jsonencode(inventory, PrettyPrint=true));
    write_stage(output_dir, nonce, 'inventory_written');
catch ME
    failure = struct('identifier', ME.identifier, 'message', ME.message, ...
        'report', getReport(ME, 'extended', 'hyperlinks', 'off'));
    write_atomic_text(fullfile(output_dir, 'failure.json'), jsonencode(failure, PrettyPrint=true));
    write_stage(output_dir, nonce, 'oracle_exception');
    rethrow(ME);
end
close all force;
end

function observed = inventory_results(results)
if iscell(results)
    cases = results;
else
    cases = {results};
end
observed = struct();
observed.case_count = numel(cases);
observed.cases = cell(1, numel(cases));
for case_index = 1:numel(cases)
    result = cases{case_index};
    if ~isstruct(result) || numel(result) ~= 1
        error('sipi_com_result_surface_inventory_v1:Result', ...
            'Each returned COM case must be one scalar struct.');
    end
    names = sort(fieldnames(result));
    fields = cell(1, numel(names));
    for field_index = 1:numel(names)
        name = names{field_index};
        fields{field_index} = inventory_field(name, result.(name));
    end
    observed.cases{case_index} = struct('case_index', case_index, 'fields', {fields});
end
end

function observed = inventory_field(name, value)
observed = struct('name', name, 'class', class(value), 'shape', double(size(value)), ...
    'numel', double(numel(value)), 'kind', 'unsupported', 'content_exported', false);
if isempty(value)
    observed.kind = 'empty';
    return;
end
if ischar(value)
    observed.kind = 'char';
    observed.content_exported = numel(value) <= 4096;
    if observed.content_exported
        observed.value = value;
    end
    return;
end
if ~isnumeric(value) || ~isreal(value)
    return;
end
if ~isa(value, 'double')
    observed.kind = 'numeric_non_double';
    return;
end
observed.kind = 'double';
observed.finite = all(isfinite(value(:)));
if isscalar(value)
    observed.content_exported = true;
    observed.value = scalar_value(value);
    return;
end
% Preserve source shape and MATLAB column-major element order.  This bounded
% payload is only for discovering which existing source arrays have a direct
% Rust counterpart; it is never a product result format.
if numel(value) <= 16384
    observed.content_exported = true;
    observed.column_major_values = reshape(double(value), 1, []);
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
payload = struct('schema', 'sipi.com.result-surface-inventory-stage.v1', ...
    'nonce', nonce, 'stage', stage);
write_atomic_text(fullfile(output_dir, 'stage.json'), jsonencode(payload));
end

function write_atomic_text(path, text_value)
[directory, ~, ~] = fileparts(path);
temporary = [tempname(directory), '.json'];
file_id = fopen(temporary, 'w');
if file_id < 0
    error('sipi_com_result_surface_inventory_v1:Write', 'Cannot open output file.');
end
cleanup = onCleanup(@() fclose(file_id));
fprintf(file_id, '%s\n', text_value);
clear cleanup;
[moved, message] = movefile(temporary, path, 'f');
if ~moved
    error('sipi_com_result_surface_inventory_v1:Write', 'Cannot publish output: %s', message);
end
end
