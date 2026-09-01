function as_performance_rfm_kernel_bench(rfm_path, output_path, frequency_count, fmax_hz, warmups, repetitions)
% Benchmark the same existing AS-06 pole/residue response kernel as Rust.
% Parsing and JSON output are outside the timed region.
    if nargin ~= 6
        error('as_performance_rfm_kernel_bench requires six arguments');
    end
    model = parse_rfm(char(rfm_path));
    if frequency_count < 1 || frequency_count ~= floor(frequency_count)
        error('frequency_count must be a positive integer');
    end
    if fmax_hz <= 0 || ~isfinite(fmax_hz)
        error('fmax_hz must be finite and positive');
    end
    if warmups < 0 || warmups ~= floor(warmups) || repetitions < 1 || repetitions ~= floor(repetitions)
        error('warmups/repetitions are outside the bounded range');
    end
    if frequency_count == 1
        frequencies = 0;
    else
        frequencies = (0:frequency_count-1)' .* (fmax_hz / (frequency_count - 1));
    end
    warmup_completed = warmups == 0;
    for index = 1:warmups
        values = evaluate_rfm(model, frequencies); %#ok<NASGU>
        warmup_completed = true;
    end
    durations = zeros(1, repetitions);
    for index = 1:repetitions
        started = tic;
        values = evaluate_rfm(model, frequencies);
        durations(index) = toc(started);
    end
    checksum = struct();
    checksum.sum_real = sum(real(values(:)));
    checksum.sum_imag = sum(imag(values(:)));
    checksum.sum_abs_squared = sum(abs(values(:)).^2);
    checksum.first_re = real(values(1, 1));
    checksum.first_im = imag(values(1, 1));
    checksum.first_re_bits = sprintf('%016x', typecast(real(values(1, 1)), 'uint64'));
    checksum.first_im_bits = sprintf('%016x', typecast(imag(values(1, 1)), 'uint64'));
    checksum.response_count = size(values, 2);
    checksum.frequency_count = size(values, 1);
    report = struct();
    report.schema = 'sipi.as-performance-rfm-kernel.v1';
    report.status = 'observed';
    report.engine = 'matlab';
    report.matlab_release = version('-release');
    report.timing_scope = 'evaluate_rfm_only_after_single_parse';
    report.timing_clock = 'tic/toc';
    report.input = struct('file_name', string(get_last_path_component(char(rfm_path))), ...
        'nports', model.nports, 'stored_poles', numel(model.poles), ...
        'effective_order', model.effective_order);
    report.workload = struct('frequency_count', frequency_count, 'fmax_hz', fmax_hz, ...
        'response_count', model.nports * model.nports, 'warmup_count', warmups, ...
        'repetition_count', repetitions);
    report.durations_seconds = durations;
    report.median_seconds = median(durations);
    report.checksum = checksum;
    report.warmup_completed = warmup_completed;
    report.limitations = { ...
        'kernel-only timing; RFM parse, process launch, filesystem and JSON serialization are excluded', ...
        'same mathematical pole/residue evaluator is compared; this is not a MATLAB SPICE solver comparison', ...
        'no performance acceptance threshold is asserted by this observation'};
    text = jsonencode(report, 'PrettyPrint', true);
    handle = fopen(char(output_path), 'w');
    if handle < 0
        error('cannot open output report');
    end
    cleaner = onCleanup(@() fclose(handle));
    fwrite(handle, text, 'char');
    fwrite(handle, newline, 'char');
end

function model = parse_rfm(path)
    lines = splitlines(string(fileread(path)));
    compact = strings(0, 1);
    for index = 1:numel(lines)
        line = strtrim(lines(index));
        if strlength(line) == 0 || startsWith(line, '*') || startsWith(line, '!') || startsWith(line, '#')
            continue;
        end
        compact(end + 1, 1) = line; %#ok<AGROW>
    end
    cursor = 1;
    headers = struct();
    while cursor <= numel(compact)
        tokens = split(compact(cursor));
        if numel(tokens) == 0 || strcmpi(tokens(1), 'BEGIN')
            break;
        end
        if numel(tokens) ~= 2 || ~ismember(upper(tokens(1)), ["VERSION", "NPORT", "MATRIX_TYPE", "Z0"])
            break;
        end
        key = lower(char(tokens(1)));
        if isfield(headers, key)
            error('duplicate RFM header');
        end
        headers.(key) = str2double(tokens(2));
        if strcmp(key, 'matrix_type')
            headers.(key) = upper(char(tokens(2)));
        end
        cursor = cursor + 1;
    end
    required = {'version', 'nport', 'matrix_type', 'z0'};
    for index = 1:numel(required)
        if ~isfield(headers, required{index})
            error('missing RFM header');
        end
    end
    if headers.version ~= 200600 || ~strcmp(headers.matrix_type, 'S') || headers.nport < 1 || headers.z0 <= 0
        error('unsupported RFM header');
    end
    nports = headers.nport;
    response_count = nports * nports;
    constants = zeros(response_count, 1);
    term_cells = cell(response_count, 1);
    poles = complex([]);
    while cursor <= numel(compact)
        [tokens, cursor] = take_tokens(compact, cursor, 'BEGIN', 3);
        row = str2double(tokens(2));
        column = str2double(tokens(3));
        if row < 1 || row > nports || column < 1 || column > nports
            error('RFM response index out of range');
        end
        response = (row - 1) * nports + column;
        if ~isempty(term_cells{response})
            error('duplicate RFM response block');
        end
        [tokens, cursor] = take_tokens(compact, cursor, 'CONST', 2);
        constants(response) = finite_number(tokens(2));
        terms = complex([]);
        residues_for_terms = complex([]);
        next_tokens = strings(0, 1);
        if cursor <= numel(compact)
            next_tokens = split(compact(cursor));
        end
        if cursor <= numel(compact) && ~isempty(next_tokens) && strcmpi(next_tokens(1), 'C')
            [tokens, cursor] = take_tokens(compact, cursor, 'C', 2);
            if finite_number(tokens(2)) ~= 0
                error('non-zero proportional C is unsupported');
            end
        end
        next_tokens = strings(0, 1);
        if cursor <= numel(compact)
            next_tokens = split(compact(cursor));
        end
        if cursor <= numel(compact) && ~isempty(next_tokens) && strcmpi(next_tokens(1), 'DELAY')
            [tokens, cursor] = take_tokens(compact, cursor, 'DELAY', 2);
            if finite_number(tokens(2)) ~= 0
                error('non-zero delay is unsupported');
            end
        end
        [tokens, cursor] = take_tokens(compact, cursor, 'BEGIN_REAL', 2);
        real_count = nonnegative_integer(tokens(2));
        for item = 1:real_count
            tokens = split(compact(cursor));
            if numel(tokens) ~= 2
                error('invalid real-pole row');
            end
            damping = finite_number(tokens(1));
            residue = finite_number(tokens(2));
            if damping <= 0
                error('real-pole damping must be positive');
            end
            terms(end + 1) = complex(-damping, 0); %#ok<AGROW>
            residues_for_terms(end + 1) = complex(residue, 0); %#ok<AGROW>
            cursor = cursor + 1;
        end
        [tokens, cursor] = take_tokens(compact, cursor, 'BEGIN_COMPLEX', 2);
        complex_count = nonnegative_integer(tokens(2));
        for item = 1:complex_count
            tokens = split(compact(cursor));
            if numel(tokens) ~= 4
                error('invalid complex-pole row');
            end
            damping = finite_number(tokens(1));
            omega = finite_number(tokens(2));
            residue = complex(finite_number(tokens(3)), finite_number(tokens(4)));
            if damping <= 0 || omega == 0
                error('invalid complex-pole values');
            end
            pole = complex(-damping, -omega);
            if imag(pole) < 0
                pole = conj(pole);
                residue = conj(residue);
            end
            terms(end + 1) = pole; %#ok<AGROW>
            residues_for_terms(end + 1) = residue; %#ok<AGROW>
            cursor = cursor + 1;
        end
        [~, cursor] = take_tokens(compact, cursor, 'END', 1);
        term_cells{response} = [terms; residues_for_terms];
        for item = 1:numel(terms)
            if ~any(poles == terms(item))
                poles(end + 1) = terms(item); %#ok<AGROW>
            end
        end
    end
    for response = 1:response_count
        if isempty(term_cells{response})
            error('missing RFM response block');
        end
    end
    residues = complex(zeros(response_count, numel(poles)));
    for response = 1:response_count
        terms = term_cells{response}(1, :);
        response_residues = term_cells{response}(2, :);
        for item = 1:numel(terms)
            location = find(poles == terms(item), 1);
            residues(response, location) = residues(response, location) + response_residues(item);
        end
    end
    model = struct('nports', nports, 'poles', poles, 'residues', residues, ...
        'constants', complex(constants), 'effective_order', sum(1 + (imag(poles) ~= 0)));
end

function values = evaluate_rfm(model, frequencies)
    s_axis = 2i * pi .* frequencies;
    values = repmat(reshape(model.constants, 1, []), numel(frequencies), 1);
    for pole_index = 1:numel(model.poles)
        pole = model.poles(pole_index);
        residue = model.residues(:, pole_index).';
        values = values + residue ./ (s_axis - pole);
        if imag(pole) ~= 0
            values = values + conj(residue) ./ (s_axis - conj(pole));
        end
    end
end

function [tokens, cursor] = take_tokens(lines, cursor, keyword, count)
    if cursor > numel(lines)
        error('RFM input ended while reading %s', keyword);
    end
    tokens = split(lines(cursor));
    if numel(tokens) ~= count || ~strcmpi(tokens(1), keyword)
        error('expected %s in RFM input', keyword);
    end
    cursor = cursor + 1;
end

function value = finite_number(token)
    value = str2double(strrep(strrep(char(token), 'D', 'E'), 'd', 'e'));
    if ~isfinite(value)
        error('RFM value must be finite');
    end
end

function value = nonnegative_integer(token)
    value = finite_number(token);
    if value < 0 || value ~= floor(value)
        error('RFM count must be a non-negative integer');
    end
end

function value = get_last_path_component(path)
    parts = regexp(path, '[\\/]', 'split');
    value = parts{end};
end
