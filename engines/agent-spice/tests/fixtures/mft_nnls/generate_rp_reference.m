function generate_rp_reference(toolboxRoot, outputPath)
% Generate a minimal real RP_QRNNLS S/Y one-step artifact.
arguments
    toolboxRoot (1,1) string
    outputPath (1,1) string = fullfile(fileparts(mfilename('fullpath')), 'rp_reference.mat')
end

addpath(toolboxRoot);
addpath(fullfile(toolboxRoot, 'code'));
addpath(fullfile(toolboxRoot, 'code', 'auxiliary'));
% The distributed Y helper's filename and declared function name differ.
% Shadow it temporarily without modifying the reference toolbox.
y_helper = fullfile(toolboxRoot, 'code', 'auxiliary', 'RP_QRNNLS_Y.m');
y_tempdir = tempname;
mkdir(y_tempdir);
copyfile(y_helper, fullfile(y_tempdir, 'RP_QRNLLS_Y.m'));
addpath(y_tempdir, '-begin');
cleanup = onCleanup(@() rmdir(y_tempdir, 's'));
s = 2i*pi*linspace(0, 1, 81);

ser_s = struct('poles', -1, 'R', 2, 'D', 0, 'E', 0);
[ser_s] = pr2ss(ser_s);
opts_s = base_options();
opts_s.violtriplets = [1; 0; 2; 1; 1];
[out_s, ~] = RP_QRNNLS_S(ser_s, 1, s, opts_s, 1);

ser_sd = struct('poles', -1, 'R', 0, 'D', 1.2, 'E', 0);
[ser_sd] = pr2ss(ser_sd);
opts_sd = base_options();
opts_sd.violtriplets = [1; 0; 1.2; 1; 1];
[out_sd, ~] = RP_QRNNLS_S(ser_sd, 1, s, opts_sd, 1);

ser_s2 = struct('poles', -1, 'R', [2 0; 0 0.5], 'D', zeros(2), 'E', zeros(2));
[ser_s2] = pr2ss(ser_s2);
opts_s2 = base_options();
opts_s2.violtriplets = [1; 0; 2; 1; 0; 1; 0];
[out_s2, ~] = RP_QRNNLS_S(ser_s2, 1, s, opts_s2, 1);

ser_s2off = struct('poles', -1, 'R', [2 0.3; 0.3 0.5], 'D', zeros(2), 'E', zeros(2));
[ser_s2off] = pr2ss(ser_s2off);
opts_s2off = base_options();
opts_s2off.bw = 1;
[u_s2off, sigma_s2off, v_s2off] = svd(ser_s2off.R);
opts_s2off.violtriplets = [1; 0; sigma_s2off(1,1); u_s2off(:,1); v_s2off(:,1)];
[out_s2off, ~] = RP_QRNNLS_S(ser_s2off, 1, s, opts_s2off, 1);

ser_y = struct('poles', -1, 'R', -2, 'D', 1, 'E', 0);
[ser_y] = pr2ss(ser_y);
opts_y = base_options();
opts_y.violpairs = [1; 0; -1; 1];
[out_y, ~] = RP_QRNLLS_Y(ser_y, 1, s, opts_y, 1);

save(outputPath, 's', 'ser_s', 'out_s', 'ser_sd', 'out_sd', 'ser_s2', 'out_s2', 'ser_s2off', 'out_s2off', 'ser_y', 'out_y');
end

function opts = base_options()
opts = struct('bw', 0, 'auxflag', 1, 'weightfactor', 1e-3, ...
    'weightparam', 1, 'TOLE', 1e-12, 'TOLD', 1e-6, 'TOLG', 1e-6, ...
    'screen', 0, 'solver', 'lsqnonneg', 'nmax', 1e16, 'alpha', 1, ...
    's_ekstra', [], 'solverdata', [], 'oldDflag', -1, 'oldEflag', -1, 'tid', zeros(1,8), 'continue', 0);
end
