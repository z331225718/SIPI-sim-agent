function result = sipi_com_warning_capture_selftest_v1(capture_dir)
%SIPI_COM_WARNING_CAPTURE_SELFTEST_V1 Exercise the warning shim in isolation.

if ~isfolder(capture_dir)
    error('sipi_com_warning_capture_selftest_v1:CaptureDir', 'Capture directory missing.');
end
addpath(capture_dir, '-begin');
cleanup = onCleanup(@() cleanup_capture(capture_dir));
clear warning;
global SIPI_COM_WARNING_CAPTURE_V1;
SIPI_COM_WARNING_CAPTURE_V1 = struct( ...
    'enabled', true, ...
    'source_file', [mfilename('fullpath'), '.m'], ...
    'events', {{}}, ...
    'capture_incomplete', false, ...
    'incomplete_reason', '');
prior = warning('query', 'MATLAB:singularMatrix');
warning('off', 'MATLAB:singularMatrix');
warning('selftest:message', 'message %d', 1);
warning('selftest:message', 'message %d', 1);
warning('selftest:other', 'other');
warning(prior);
events = SIPI_COM_WARNING_CAPTURE_V1.events;
result = struct( ...
    'shim_path', which('warning'), ...
    'capture_incomplete', SIPI_COM_WARNING_CAPTURE_V1.capture_incomplete, ...
    'incomplete_reason', SIPI_COM_WARNING_CAPTURE_V1.incomplete_reason, ...
    'event_count', double(numel(events)), ...
    'events', {events});
end

function cleanup_capture(capture_dir)
global SIPI_COM_WARNING_CAPTURE_V1;
SIPI_COM_WARNING_CAPTURE_V1 = [];
rmpath(capture_dir);
clear warning;
end
