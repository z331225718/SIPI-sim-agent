function generate_nnls_reference(outputPath)
% MATLAB lsqnonneg reference for RPdriver's homogeneous QR-NNLS transform.
arguments
    outputPath (1,1) string = fullfile(fileparts(mfilename('fullpath')), 'nnls_reference.mat')
end

constraint_matrix = [1 0; 0 1; 1 1];
constraint_rhs = [-1; -1; -1.5];
E = [constraint_matrix -constraint_rhs].';
f = [zeros(size(constraint_matrix,2), 1); 1];
[dual_variables, ~, homogeneous_residual] = lsqnonneg(E, f);
xbar = -homogeneous_residual(1:end-1) / homogeneous_residual(end);
save(outputPath, 'constraint_matrix', 'constraint_rhs', 'E', 'f', 'dual_variables', 'homogeneous_residual', 'xbar');
end
