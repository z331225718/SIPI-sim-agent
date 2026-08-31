function varargout = warning(varargin)
%WARNING Diagnostic-only source-local warning observer for the COM oracle.
%
% The wrapper always delegates to MATLAB's builtin warning function. It records
% only emission-shaped calls whose stack contains the configured pinned COM
% source file. Toolbox and MATLAB-internal warnings are deliberately excluded.

global SIPI_COM_WARNING_CAPTURE_V1;
global SIPI_COM_WARNING_CAPTURE_DELEGATING_V1;

% MATLAB's builtin warning implementation may re-enter this shadow shim with
% a message object. That nested call is implementation detail, not a source
% warning call; forward it without inspecting it.
if isequal(SIPI_COM_WARNING_CAPTURE_DELEGATING_V1, true)
    if nargout == 0
        builtin('warning', varargin{:});
    else
        [varargout{1:nargout}] = builtin('warning', varargin{:});
    end
    return
end

[record, incomplete] = capture_request(varargin{:});
if incomplete && capture_enabled()
    mark_incomplete(['unrecognized_warning_signature:' signature_of(varargin)]);
end
if record
    lastwarn('');
end

SIPI_COM_WARNING_CAPTURE_DELEGATING_V1 = true;
try
    if nargout == 0
        builtin('warning', varargin{:});
    else
        [varargout{1:nargout}] = builtin('warning', varargin{:});
    end
catch ME
    SIPI_COM_WARNING_CAPTURE_DELEGATING_V1 = false;
    rethrow(ME)
end
SIPI_COM_WARNING_CAPTURE_DELEGATING_V1 = false;

if record
    [message, identifier] = lastwarn;
    visible_to_lastwarn = ~isempty(message);
    if isempty(message)
        [message, identifier, rendered] = render_emission(varargin{:});
        if ~rendered
            mark_incomplete('emission_not_observable_after_builtin');
            return
        end
    end
    event = struct( ...
        'sequence', double(numel(SIPI_COM_WARNING_CAPTURE_V1.events) + 1), ...
        'identifier', char(identifier), ...
        'message', char(message), ...
        'visible_to_lastwarn', visible_to_lastwarn, ...
        'source_line', double(source_line()));
    SIPI_COM_WARNING_CAPTURE_V1.events{end + 1} = event;
end
end

function [record, incomplete] = capture_request(varargin)
record = false;
incomplete = false;
if ~capture_enabled() || ~is_configured_emission_call()
    return
end
if isempty(varargin)
    incomplete = true;
    return
end
first = varargin{1};
if isstruct(first)
    return
end
if ~(ischar(first) || (isstring(first) && isscalar(first)))
    incomplete = true;
    return
end
command = lower(char(first));
if any(strcmp(command, {'on', 'off', 'query', 'error', 'backtrace', 'verbose'}))
    return
end
record = true;
end

function signature = signature_of(args)
if isempty(args)
    signature = 'empty';
    return
end
classes = cell(1, numel(args));
for index = 1:numel(args)
    classes{index} = class(args{index});
end
signature = strjoin(classes, ',');
end

function enabled = capture_enabled()
global SIPI_COM_WARNING_CAPTURE_V1;
enabled = isstruct(SIPI_COM_WARNING_CAPTURE_V1) ...
    && isfield(SIPI_COM_WARNING_CAPTURE_V1, 'enabled') ...
    && isequal(SIPI_COM_WARNING_CAPTURE_V1.enabled, true) ...
    && isfield(SIPI_COM_WARNING_CAPTURE_V1, 'source_file') ...
    && ischar(SIPI_COM_WARNING_CAPTURE_V1.source_file);
end

function matched = is_configured_emission_call()
global SIPI_COM_WARNING_CAPTURE_V1;
matched = false;
expected = char(SIPI_COM_WARNING_CAPTURE_V1.source_file);
frames = dbstack('-completenames');
for index = 2:numel(frames)
    if ~isfield(frames(index), 'file') || ~strcmp(char(frames(index).file), expected)
        continue
    end
    if ~isfield(SIPI_COM_WARNING_CAPTURE_V1, 'source_emission_lines')
        matched = true;
        return
    end
    lines = SIPI_COM_WARNING_CAPTURE_V1.source_emission_lines;
    if isnumeric(lines) && isscalar(frames(index).line) && any(lines == frames(index).line)
        matched = true;
        return
    end
end
end

function line = source_line()
global SIPI_COM_WARNING_CAPTURE_V1;
line = NaN;
expected = char(SIPI_COM_WARNING_CAPTURE_V1.source_file);
frames = dbstack('-completenames');
for index = 2:numel(frames)
    if isfield(frames(index), 'file') && strcmp(char(frames(index).file), expected)
        line = frames(index).line;
        return
    end
end
mark_incomplete('source_stack_missing_after_classification');
end

function mark_incomplete(reason)
global SIPI_COM_WARNING_CAPTURE_V1;
SIPI_COM_WARNING_CAPTURE_V1.capture_incomplete = true;
if ~isfield(SIPI_COM_WARNING_CAPTURE_V1, 'incomplete_reason') ...
        || isempty(SIPI_COM_WARNING_CAPTURE_V1.incomplete_reason)
    SIPI_COM_WARNING_CAPTURE_V1.incomplete_reason = reason;
end
end

function [message, identifier, rendered] = render_emission(varargin)
message = '';
identifier = '';
rendered = false;
if isempty(varargin)
    return
end
first = varargin{1};
if ~(ischar(first) || (isstring(first) && isscalar(first)))
    return
end
first = char(first);
if contains(first, ':')
    if numel(varargin) < 2 || ~(ischar(varargin{2}) || (isstring(varargin{2}) && isscalar(varargin{2})))
        return
    end
    identifier = first;
    format = char(varargin{2});
    values = varargin(3:end);
else
    format = first;
    values = varargin(2:end);
end
try
    if isempty(values)
        message = format;
    else
        message = sprintf(format, values{:});
    end
    rendered = true;
catch
    message = '';
    identifier = '';
end
end
