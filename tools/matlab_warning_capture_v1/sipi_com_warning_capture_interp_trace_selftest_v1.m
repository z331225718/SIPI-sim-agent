function result = sipi_com_warning_capture_interp_trace_selftest_v1(capture_dir)
%SIPI_COM_WARNING_CAPTURE_INTERP_TRACE_SELFTEST_V1 Verify caller-local Sin capture.

if ~isfolder(capture_dir)
    error('sipi_com_warning_capture_interp_trace_selftest_v1:CaptureDir', ...
        'Capture directory missing.');
end
addpath(capture_dir, '-begin');
cleanup = onCleanup(@() cleanup_capture(capture_dir));
clear warning;
global SIPI_COM_WARNING_CAPTURE_V1;
source_file = [mfilename('fullpath'), '.m'];
SIPI_COM_WARNING_CAPTURE_V1 = struct( ...
    'enabled', true, ...
    'source_file', source_file, ...
    'source_emission_lines', 32, ...
    'interpolation_input_trace_lines', 32, ...
    'events', {{}}, ...
    'capture_incomplete', false, ...
    'incomplete_reason', '');
emit_interpolation_warning();
events = SIPI_COM_WARNING_CAPTURE_V1.events;
result = struct( ...
    'capture_incomplete', SIPI_COM_WARNING_CAPTURE_V1.capture_incomplete, ...
    'incomplete_reason', SIPI_COM_WARNING_CAPTURE_V1.incomplete_reason, ...
    'event_count', double(numel(events)), ...
    'events', {events});
end

function emit_interpolation_warning()
Sin = [1 + 0i, 0 - 1i, -1 + 0i];
warning('selftest:interp', 'interpolation trace');
end

function cleanup_capture(capture_dir)
global SIPI_COM_WARNING_CAPTURE_V1;
SIPI_COM_WARNING_CAPTURE_V1 = [];
rmpath(capture_dir);
clear warning;
end
