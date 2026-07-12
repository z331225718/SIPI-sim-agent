function generate_reference(toolboxRoot, outputPath)
% Regenerate the compact MFT-NNLS reference fixture with MATLAB + NumPy.
arguments
    toolboxRoot (1,1) string
    outputPath (1,1) string = fullfile(fileparts(mfilename('fullpath')), 'ex4_s_reference.mat')
end

addpath(toolboxRoot);
addpath(fullfile(toolboxRoot, 'code'));
addpath(fullfile(toolboxRoot, 'code', 'auxiliary'));
sourcePath = fullfile(toolboxRoot, 'ex4_S.mat');
loaded = load(sourcePath, 's', 'bigS');
sampleCount = numel(loaded.s);

opts.N = 4;
opts.Niter1 = 1;
opts.Niter2 = 1;
opts.poletype = 'linlogcmplx';
opts.asymp = 2;
opts.parametertype = 'S';
opts.weightparam = 1;
[SER, ~, bigSfit, optsOut] = VFdriver(loaded.bigS(:,:,1:sampleCount), loaded.s(1:sampleCount), [], opts);

Nc = size(loaded.bigS, 1);
Ns = sampleCount;
relocation_response = zeros(Nc*(Nc+1)/2, Ns);
tell = 0;
for col = 1:Nc
    for row = col:Nc
        tell = tell + 1;
        relocation_response(tell,:) = squeeze(loaded.bigS(row,col,1:sampleCount)).';
    end
end
relocation_weight = ones(1, Ns);
relocation_opts = struct('relax', 1, 'stable', 1, 'asymp', 2, 'skip_pole', 0, 'skip_res', 1, 'cmplx_ss', 1, 'spy1', 0, 'spy2', 0, 'logx', 1, 'logy', 1, 'errplot', 1, 'phaseplot', 0, 'legend', 0);
relocation_cases = struct();
for order = [4 5 6 7 9 13]
    initial_poles = mft_initial_poles(loaded.s(1), loaded.s(sampleCount), order);
    [~, relocated_poles] = vectfit4(relocation_response, loaded.s(1:sampleCount), initial_poles, relocation_weight, relocation_opts);
    residue_opts = relocation_opts;
    residue_opts.skip_pole = 1;
    residue_opts.skip_res = 0;
    [~, ~, raw_rms] = vectfit4(relocation_response, loaded.s(1:sampleCount), relocated_poles, relocation_weight, residue_opts);
    relocation_cases.(sprintf('order_%d', order)) = struct('initial_poles', initial_poles, 'poles', relocated_poles, 'rms', raw_rms);
end
relocation_initial_poles = relocation_cases.order_4.initial_poles;
relocation_poles = relocation_cases.order_4.poles;
[medium_frequencies_hz, medium_response, medium_initial_poles, medium_relocated_poles, medium_fitted_response, medium_rms] = medium_case(relocation_opts);
[passivity_sweep_frequencies_hz, passivity_s_bands_hz, passivity_y_bands_hz] = passivity_sweep_case();

s = loaded.s(1:sampleCount);
response = permute(loaded.bigS(:,:,1:sampleCount), [3 1 2]);
fitted_response = permute(bigSfit, [3 1 2]);
poles = SER.poles(:);
residues = SER.R;
constant = SER.D;
proportional = SER.E;
weightparam = int64(optsOut.weightparam);
matlab_version = version;
source_sha256 = sha256(sourcePath);
vfdriver_sha256 = sha256(fullfile(toolboxRoot, 'code', 'VFdriver.m'));
vectfit4_sha256 = sha256(fullfile(toolboxRoot, 'code', 'auxiliary', 'vectfit4.m'));
save(outputPath, 's', 'response', 'fitted_response', 'poles', 'residues', 'constant', 'proportional', 'weightparam', 'matlab_version', 'source_sha256', 'vfdriver_sha256', 'vectfit4_sha256', 'relocation_response', 'relocation_weight', 'relocation_initial_poles', 'relocation_poles', 'relocation_cases', 'medium_frequencies_hz', 'medium_response', 'medium_initial_poles', 'medium_relocated_poles', 'medium_fitted_response', 'medium_rms', 'passivity_sweep_frequencies_hz', 'passivity_s_bands_hz', 'passivity_y_bands_hz');
end

function [frequencies_hz, s_bands_hz, y_bands_hz] = passivity_sweep_case()
frequencies_hz = linspace(0, 1, 801);
s = 2i*pi*frequencies_hz;
SER = struct('A', -1, 'B', 1, 'C', 2, 'D', 0, 'E', 0);
[s_bands, ~] = pass_check_S_sweep_new(0, SER, s);
SER = struct('A', -1, 'B', 1, 'C', -2, 'D', 1, 'E', 0);
[y_bands, ~] = pass_check_Y_sweep_new(0, SER, s);
s_bands_hz = s_bands.' / (2*pi);
y_bands_hz = y_bands.' / (2*pi);
end

function [frequencies_hz, response, initial_poles, relocated_poles, fitted_response, rms] = medium_case(relocation_opts)
% A well-conditioned, order-six rational matrix used for response parity.
frequencies_hz = logspace(5, 8, 161);
s = 2i*pi*frequencies_hz;
beta = [8e5 8e6 5e7] * 2*pi;
alpha = [-2e5 -5e5 -1e6];
initial_poles = zeros(1, 6);
response = zeros(3, 3, numel(s));
constant = [0.10 0.01 0.015; 0.01 0.12 0.02; 0.015 0.02 0.11];
for k = 1:numel(s)
    response(:,:,k) = constant;
end
for pair = 1:3
    lower = alpha(pair) - 1i*beta(pair);
    upper = conj(lower);
    initial_poles(2*pair-1:2*pair) = [lower upper];
    residue = (0.01 + 0.002*pair) * (-alpha(pair) + 1i*beta(pair)) * ...
        [1 0.2 0.1; 0.2 0.8 0.15; 0.1 0.15 0.6];
    for k = 1:numel(s)
        response(:,:,k) = response(:,:,k) + residue/(s(k)-lower) + conj(residue)/(s(k)-upper);
    end
end
packed = zeros(6, numel(s));
tell = 0;
for col = 1:3
    for row = col:3
        tell = tell + 1;
        packed(tell,:) = squeeze(response(row,col,:)).';
    end
end
[~, relocated_poles] = vectfit4(packed, s, initial_poles, ones(1, numel(s)), relocation_opts);
residue_opts = relocation_opts;
residue_opts.skip_pole = 1;
residue_opts.skip_res = 0;
[~, ~, ~, fit] = vectfit4(packed, s, relocated_poles, ones(1, numel(s)), residue_opts);
fitted_response = zeros(3, 3, numel(s));
tell = 0;
for col = 1:3
    for row = col:3
        tell = tell + 1;
        fitted_response(row,col,:) = fit(tell,:);
        fitted_response(col,row,:) = fit(tell,:);
    end
end
rms = sqrt(mean(abs(fitted_response(:) - response(:)).^2));
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

function poles = mft_initial_poles(sfirst, slast, order)
lo = sfirst / 1i;
hi = slast / 1i;
effective_type = 'linlogcmplx';
if order < 6
    effective_type = 'logcmplx';
end
if strcmp(effective_type, 'logcmplx')
    beta = logspace(log10(lo), log10(hi), floor(order/2));
    extra = -10^((log10(lo)+log10(hi))/2);
else
    linear = linspace(lo, hi, ceil((order-1)/4));
    logarithmic = logspace(log10(lo), log10(hi), 2+floor(order/4));
    beta = [linear logarithmic(2:end-1)];
    extra = -10^((log10(lo)+log10(hi))/2);
end
poles = [];
for index = 1:numel(beta)
    alpha = -1e-3 * beta(index);
    poles = [poles (alpha - 1i*beta(index)) (alpha + 1i*beta(index))]; %#ok<AGROW>
end
if numel(poles) < order
    poles = [poles extra];
end
poles = poles(1:order);
end
