function generate_reference(toolboxRoot, outputPath)
% Regenerate the compact MFT-NNLS reference fixture with MATLAB + NumPy.
arguments
    toolboxRoot (1,1) string
    outputPath (1,1) string = fullfile(fileparts(mfilename('fullpath')), 'ex4_s_small.npz')
end

addpath(toolboxRoot);
addpath(fullfile(toolboxRoot, 'code'));
addpath(fullfile(toolboxRoot, 'code', 'auxiliary'));
sourcePath = fullfile(toolboxRoot, 'ex4_S.mat');
loaded = load(sourcePath, 's', 'bigS');
sampleCount = min(8, numel(loaded.s));

opts.N = 4;
opts.Niter1 = 1;
opts.Niter2 = 1;
opts.poletype = 'linlogcmplx';
opts.asymp = 2;
opts.parametertype = 'S';
opts.weightparam = 1;
[SER, ~, bigSfit, optsOut] = VFdriver(loaded.bigS(:,:,1:sampleCount), loaded.s(1:sampleCount), [], opts);

py.numpy.savez_compressed(outputPath, pyargs( ...
    's', py.numpy.array(loaded.s(1:sampleCount)), ...
    'response', py.numpy.array(permute(loaded.bigS(:,:,1:sampleCount), [3 1 2])), ...
    'fitted_response', py.numpy.array(permute(bigSfit, [3 1 2])), ...
    'poles', py.numpy.array(SER.poles(:)), ...
    'residues', py.numpy.array(SER.R), ...
    'constant', py.numpy.array(SER.D), ...
    'proportional', py.numpy.array(SER.E), ...
    'weightparam', int64(optsOut.weightparam), ...
    'matlab_version', version, ...
    'source_sha256', sha256(sourcePath), ...
    'vfdriver_sha256', sha256(fullfile(toolboxRoot, 'code', 'VFdriver.m')), ...
    'vectfit4_sha256', sha256(fullfile(toolboxRoot, 'code', 'auxiliary', 'vectfit4.m')));
end

function value = sha256(path)
digest = java.security.MessageDigest.getInstance('SHA-256');
stream = java.io.FileInputStream(java.io.File(path));
cleanup = onCleanup(@() stream.close());
buffer = zeros(1, 1048576, 'int8');
while true
    count = stream.read(buffer, 0, numel(buffer));
    if count < 0
        break
    end
    digest.update(buffer(1:count));
end
value = lower(reshape(dec2hex(typecast(digest.digest(), 'uint8'))', 1, []));
end
