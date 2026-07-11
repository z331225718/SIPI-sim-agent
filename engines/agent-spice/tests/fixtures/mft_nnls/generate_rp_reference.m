function generate_rp_reference(toolboxRoot, outputPath)
% Generate a minimal real RP_QRNNLS S/Y one-step artifact.
arguments
    toolboxRoot (1,1) string
    outputPath (1,1) string = fullfile(fileparts(mfilename('fullpath')), 'rp_reference.mat')
end

addpath(toolboxRoot);
addpath(fullfile(toolboxRoot, 'code'));
addpath(fullfile(toolboxRoot, 'code', 'auxiliary'));
s = 2i*pi*linspace(0, 1, 81);

ser_s = struct('poles', -1, 'R', 2, 'D', 0, 'E', 0);
[ser_s] = pr2ss(ser_s);
opts_s = base_options();
opts_s.violtriplets = [1; 0; 2; 1; 1];
[out_s, ~] = RP_QRNNLS_S(ser_s, 1, s, opts_s, 1);

ser_s2 = struct('poles', -1, 'R', [2 0; 0 0.5], 'D', zeros(2), 'E', zeros(2));
[ser_s2] = pr2ss(ser_s2);
opts_s2 = base_options();
opts_s2.violtriplets = [1; 0; 2; 1; 0; 1; 0];
[out_s2, ~] = RP_QRNNLS_S(ser_s2, 1, s, opts_s2, 1);

save(outputPath, 's', 'ser_s', 'out_s', 'ser_s2', 'out_s2');
end

function opts = base_options()
opts = struct('bw', 0, 'auxflag', 1, 'weightfactor', 1e-3, ...
    'weightparam', 1, 'TOLE', 1e-12, 'TOLD', 1e-6, 'TOLG', 1e-6, ...
    'screen', 0, 'solver', 'lsqnonneg', 'nmax', 1e16, 'alpha', 1, ...
    's_ekstra', [], 'solverdata', [], 'oldDflag', -1, 'oldEflag', -1, 'tid', zeros(1,8), 'continue', 0);
end
