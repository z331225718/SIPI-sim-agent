using System.Globalization;
using System.Numerics;

namespace AgentSpice.Engine;

internal sealed class RfmModel
{
    private sealed record SourceLine(int Number, string Text);
    private sealed record StepKernel(double[] Weights, double[] Inverse, double[] Conductance);
    private readonly Dictionary<double, StepKernel> _trapezoidalStepKernels = [];
    private readonly Dictionary<double, StepKernel> _bdfStepKernels = [];
    private Complex[,]? _dcAdmittance;
    private readonly int[] _historyStarts;
    private readonly int[] _historyStateIndices;
    private readonly bool[] _historyHasImaginaryState;
    private readonly double[] _historyResidueReal;
    private readonly double[] _historyResidueImaginary;

    internal int Version { get; }
    internal int Nports { get; }
    internal double Z0 { get; }
    internal Complex[] Poles { get; }
    internal Complex[] Residues { get; }
    internal double[] Constant { get; }
    internal int[] StateOffsets { get; }
    internal int StateWidth { get; }

    private RfmModel(int version, int nports, double z0, Complex[] poles, Complex[] residues, double[] constant)
    {
        Version = version;
        Nports = nports;
        Z0 = z0;
        Poles = poles;
        Residues = residues;
        Constant = constant;
        StateOffsets = new int[poles.Length];
        var width = 0;
        for (var index = 0; index < poles.Length; index++)
        {
            StateOffsets[index] = width;
            width += poles[index].Imaginary == 0.0 ? 1 : 2;
        }
        StateWidth = width;

        var stateIndices = new List<int>();
        var hasImaginaryState = new List<bool>();
        var residueReal = new List<double>();
        var residueImaginary = new List<double>();
        _historyStarts = new int[nports + 1];
        for (var output = 0; output < nports; output++)
        {
            _historyStarts[output] = stateIndices.Count;
            for (var input = 0; input < nports; input++)
            {
                var response = output * nports + input;
                for (var poleIndex = 0; poleIndex < poles.Length; poleIndex++)
                {
                    var residue = residues[response * poles.Length + poleIndex];
                    if (residue == Complex.Zero)
                        continue;
                    stateIndices.Add(input * StateWidth + StateOffsets[poleIndex]);
                    hasImaginaryState.Add(poles[poleIndex].Imaginary != 0.0);
                    residueReal.Add(residue.Real);
                    residueImaginary.Add(residue.Imaginary);
                }
            }
        }
        _historyStarts[nports] = stateIndices.Count;
        _historyStateIndices = stateIndices.ToArray();
        _historyHasImaginaryState = hasImaginaryState.ToArray();
        _historyResidueReal = residueReal.ToArray();
        _historyResidueImaginary = residueImaginary.ToArray();
    }

    internal static RfmModel Parse(string path)
    {
        var lines = File.ReadAllLines(path)
            .Select((text, index) => new SourceLine(index + 1, text.Trim()))
            .Where(line => line.Text.Length > 0 && !line.Text.StartsWith('*') && !line.Text.StartsWith('!') && !line.Text.StartsWith('#'))
            .ToList();
        if (lines.Count == 0)
            throw new InvalidDataException($"RFM file '{path}' is empty");

        var cursor = 0;
        var headers = new Dictionary<string, (SourceLine Line, string Value)>(StringComparer.OrdinalIgnoreCase);
        while (cursor < lines.Count && !Keyword(lines[cursor], "BEGIN"))
        {
            var tokens = Tokens(lines[cursor]);
            if (tokens.Length != 2)
                Fail(path, lines[cursor], "expected a two-token RFM header");
            if (headers.ContainsKey(tokens[0]))
                Fail(path, lines[cursor], $"duplicate RFM header '{tokens[0]}'");
            headers[tokens[0]] = (lines[cursor], tokens[1]);
            cursor++;
        }
        foreach (var required in new[] { "VERSION", "NPORT", "MATRIX_TYPE", "Z0" })
            if (!headers.ContainsKey(required)) throw new InvalidDataException($"{path}: missing RFM header {required}");

        var version = Integer(headers["VERSION"].Value, path, headers["VERSION"].Line, "VERSION");
        if (version != 200600) Fail(path, headers["VERSION"].Line, $"unsupported RFM VERSION {version}");
        var nports = Integer(headers["NPORT"].Value, path, headers["NPORT"].Line, "NPORT");
        if (nports <= 0) Fail(path, headers["NPORT"].Line, "NPORT must be positive");
        if (!headers["MATRIX_TYPE"].Value.Equals("S", StringComparison.OrdinalIgnoreCase))
            Fail(path, headers["MATRIX_TYPE"].Line, "only MATRIX_TYPE S is supported");
        var z0 = Number(headers["Z0"].Value, path, headers["Z0"].Line, "Z0");
        if (z0 <= 0.0) Fail(path, headers["Z0"].Line, "Z0 must be positive");

        var responseCount = checked(nports * nports);
        var constants = new double[responseCount];
        var responseTerms = new List<(Complex Pole, Complex Residue)>?[responseCount];
        var poles = new List<Complex>();
        var poleIndices = new Dictionary<Complex, int>();
        while (cursor < lines.Count)
        {
            var begin = Expect(lines, ref cursor, path, "BEGIN", 3);
            var row = Integer(begin.Tokens[1], path, begin.Line, "BEGIN row");
            var column = Integer(begin.Tokens[2], path, begin.Line, "BEGIN column");
            if (row < 1 || row > nports || column < 1 || column > nports)
                Fail(path, begin.Line, $"BEGIN indices are outside 1..{nports}");
            var response = (row - 1) * nports + column - 1;
            if (responseTerms[response] is not null)
                Fail(path, begin.Line, $"duplicate BEGIN {row} {column} block");

            var constant = Expect(lines, ref cursor, path, "CONST", 2);
            constants[response] = Number(constant.Tokens[1], path, constant.Line, "CONST");
            if (cursor < lines.Count && Keyword(lines[cursor], "C"))
            {
                var proportional = Expect(lines, ref cursor, path, "C", 2);
                if (Number(proportional.Tokens[1], path, proportional.Line, "C") != 0.0)
                    Fail(path, proportional.Line, "non-zero C is not supported");
            }
            if (cursor < lines.Count && Keyword(lines[cursor], "DELAY"))
            {
                var delay = Expect(lines, ref cursor, path, "DELAY", 2);
                if (Number(delay.Tokens[1], path, delay.Line, "DELAY") != 0.0)
                    Fail(path, delay.Line, "non-zero DELAY is not supported");
            }

            var terms = new List<(Complex Pole, Complex Residue)>();
            var realHeader = Expect(lines, ref cursor, path, "BEGIN_REAL", 2);
            var realCount = Integer(realHeader.Tokens[1], path, realHeader.Line, "BEGIN_REAL count");
            if (realCount < 0) Fail(path, realHeader.Line, "BEGIN_REAL count must be non-negative");
            for (var index = 0; index < realCount; index++)
            {
                if (cursor >= lines.Count) throw new InvalidDataException($"{path}: truncated BEGIN_REAL block");
                var line = lines[cursor++];
                var tokens = Tokens(line);
                if (tokens.Length != 2) Fail(path, line, "real pole row requires damping and residue");
                var damping = Number(tokens[0], path, line, "real-pole damping");
                if (damping <= 0.0) Fail(path, line, "real-pole damping must be positive");
                terms.Add((new Complex(-damping, 0.0), new Complex(Number(tokens[1], path, line, "real residue"), 0.0)));
            }

            var complexHeader = Expect(lines, ref cursor, path, "BEGIN_COMPLEX", 2);
            var complexCount = Integer(complexHeader.Tokens[1], path, complexHeader.Line, "BEGIN_COMPLEX count");
            if (complexCount < 0) Fail(path, complexHeader.Line, "BEGIN_COMPLEX count must be non-negative");
            for (var index = 0; index < complexCount; index++)
            {
                if (cursor >= lines.Count) throw new InvalidDataException($"{path}: truncated BEGIN_COMPLEX block");
                var line = lines[cursor++];
                var tokens = Tokens(line);
                if (tokens.Length != 4) Fail(path, line, "complex pole row requires damping, omega, residue real and residue imag");
                var damping = Number(tokens[0], path, line, "complex-pole damping");
                var omega = Number(tokens[1], path, line, "complex-pole omega");
                if (damping <= 0.0 || omega == 0.0)
                    Fail(path, line, "complex-pole damping must be positive and omega must be non-zero");
                var pole = new Complex(-damping, -omega);
                var residue = new Complex(Number(tokens[2], path, line, "complex residue real"), Number(tokens[3], path, line, "complex residue imag"));
                if (pole.Imaginary < 0.0)
                {
                    pole = Complex.Conjugate(pole);
                    residue = Complex.Conjugate(residue);
                }
                terms.Add((pole, residue));
            }
            Expect(lines, ref cursor, path, "END", 1);
            responseTerms[response] = terms;
            foreach (var (pole, _) in terms)
            {
                if (poleIndices.ContainsKey(pole))
                    continue;
                poleIndices[pole] = poles.Count;
                poles.Add(pole);
            }
        }

        var missing = Enumerable.Range(0, responseCount).Where(index => responseTerms[index] is null).ToArray();
        if (missing.Length > 0)
            throw new InvalidDataException($"{path}: missing response block(s): {string.Join(", ", missing.Select(index => $"{index / nports + 1},{index % nports + 1}"))}");
        var residues = new Complex[responseCount * poles.Count];
        for (var response = 0; response < responseCount; response++)
            foreach (var (pole, residue) in responseTerms[response]!) residues[response * poles.Count + poleIndices[pole]] += residue;
        return new RfmModel(version, nports, z0, poles.ToArray(), residues, constants);
    }

    internal Complex[,] Evaluate(Complex s)
    {
        var result = new Complex[Nports, Nports];
        for (var row = 0; row < Nports; row++)
        {
            for (var column = 0; column < Nports; column++)
            {
                var response = row * Nports + column;
                var value = new Complex(Constant[response], 0.0);
                for (var poleIndex = 0; poleIndex < Poles.Length; poleIndex++)
                {
                    var pole = Poles[poleIndex];
                    var residue = Residues[response * Poles.Length + poleIndex];
                    value += residue / (s - pole);
                    if (pole.Imaginary != 0.0)
                        value += Complex.Conjugate(residue) / (s - Complex.Conjugate(pole));
                }
                result[row, column] = value;
            }
        }
        return result;
    }

    internal Complex[,] Admittance(Complex s)
    {
        var scattering = Evaluate(s);
        var identityPlusScattering = new Complex[Nports, Nports];
        for (var row = 0; row < Nports; row++)
            for (var column = 0; column < Nports; column++)
                identityPlusScattering[row, column] = scattering[row, column] + (row == column ? Complex.One : Complex.Zero);
        var inverse = LinearAlgebra.Invert(identityPlusScattering);
        var admittance = new Complex[Nports, Nports];
        for (var row = 0; row < Nports; row++)
            for (var column = 0; column < Nports; column++)
                admittance[row, column] = 2.0 * inverse[row, column] / Z0 - (row == column ? 1.0 / Z0 : 0.0);
        return admittance;
    }

    internal Complex[,] DcAdmittance() => _dcAdmittance ??= Admittance(Complex.Zero);

    internal RfmState CreateState() => new(this);

    internal RfmCompanion BuildCompanion(
        RfmState previous,
        double step,
        DerivativeCoefficients? bdf)
    {
        if (step <= 0.0) throw new ArgumentOutOfRangeException(nameof(step));
        StepKernel kernel;
        if (bdf is { } coefficients)
        {
            if (!_bdfStepKernels.TryGetValue(coefficients.A0, out kernel!))
            {
                kernel = BuildBdfStepKernel(coefficients.A0);
                _bdfStepKernels[coefficients.A0] = kernel;
            }
            FillBdfBase(previous, coefficients);
        }
        else
        {
            if (!_trapezoidalStepKernels.TryGetValue(step, out kernel!))
            {
                kernel = BuildTrapezoidalStepKernel(step);
                _trapezoidalStepKernels[step] = kernel;
            }
            FillTrapezoidalBase(previous, step);
        }

        var xBase = previous.XBase;
        var history = previous.History;
        FillHistoryVector(xBase, history);
        var offset = previous.Offset;
        for (var row = 0; row < Nports; row++)
        {
            var transformedHistory = 0.0;
            for (var column = 0; column < Nports; column++)
                transformedHistory += kernel.Inverse[row * Nports + column] * history[column];
            offset[row] = -2.0 * transformedHistory / Math.Sqrt(Z0);
        }
        previous.Companion ??= new RfmCompanion(this);
        previous.Companion.Configure(kernel.Inverse, xBase, kernel.Weights, history, kernel.Conductance, offset);
        return previous.Companion;
    }

    private void FillTrapezoidalBase(RfmState previous, double step)
    {
        var half = 0.5 * step;
        var xBase = previous.XBase;
        for (var input = 0; input < Nports; input++)
        {
            var oldIncident = previous.Incident[input];
            for (var poleIndex = 0; poleIndex < Poles.Length; poleIndex++)
            {
                var pole = Poles[poleIndex];
                var state = StateOffsets[poleIndex];
                var baseIndex = input * StateWidth + state;
                if (pole.Imaginary == 0.0)
                {
                    var denominator = 1.0 - half * pole.Real;
                    xBase[baseIndex] = ((1.0 + half * pole.Real) * previous.Values[baseIndex] + half * oldIncident) / denominator;
                    continue;
                }
                var d = 1.0 - half * pole.Real;
                var e = half * pole.Imaginary;
                var denominatorComplex = d * d + e * e;
                var oldReal = previous.Values[baseIndex];
                var oldImaginary = previous.Values[baseIndex + 1];
                var qReal = (1.0 + half * pole.Real) * oldReal + e * oldImaginary + step * oldIncident;
                var qImaginary = -e * oldReal + (1.0 + half * pole.Real) * oldImaginary;
                xBase[baseIndex] = (d * qReal + e * qImaginary) / denominatorComplex;
                xBase[baseIndex + 1] = (-e * qReal + d * qImaginary) / denominatorComplex;
            }
        }
    }

    private void FillBdfBase(RfmState previous, DerivativeCoefficients coefficients)
    {
        var xBase = previous.XBase;
        for (var input = 0; input < Nports; input++)
        {
            for (var poleIndex = 0; poleIndex < Poles.Length; poleIndex++)
            {
                var pole = Poles[poleIndex];
                var state = StateOffsets[poleIndex];
                var baseIndex = input * StateWidth + state;
                var qReal = -coefficients.A1 * previous.Values[baseIndex] -
                    coefficients.A2 * previous.PreviousValues[baseIndex];
                if (pole.Imaginary == 0.0)
                {
                    xBase[baseIndex] = qReal / (coefficients.A0 - pole.Real);
                    continue;
                }

                var qImaginary = -coefficients.A1 * previous.Values[baseIndex + 1] -
                    coefficients.A2 * previous.PreviousValues[baseIndex + 1];
                var d = coefficients.A0 - pole.Real;
                var e = pole.Imaginary;
                var denominator = d * d + e * e;
                xBase[baseIndex] = (d * qReal + e * qImaginary) / denominator;
                xBase[baseIndex + 1] = (-e * qReal + d * qImaginary) / denominator;
            }
        }
    }

    private StepKernel BuildTrapezoidalStepKernel(double step)
    {
        var half = 0.5 * step;
        var weights = new double[StateWidth];
        for (var poleIndex = 0; poleIndex < Poles.Length; poleIndex++)
        {
            var pole = Poles[poleIndex];
            var state = StateOffsets[poleIndex];
            if (pole.Imaginary == 0.0)
            {
                weights[state] = half / (1.0 - half * pole.Real);
                continue;
            }
            var d = 1.0 - half * pole.Real;
            var e = half * pole.Imaginary;
            var denominator = d * d + e * e;
            weights[state] = step * d / denominator;
            weights[state + 1] = -step * e / denominator;
        }
        var inverse = InvertReal(BuildWaveMatrix(weights));
        var conductance = new double[Nports * Nports];
        for (var row = 0; row < Nports; row++)
            for (var column = 0; column < Nports; column++)
                conductance[row * Nports + column] = 2.0 * inverse[row * Nports + column] / Z0 - (row == column ? 1.0 / Z0 : 0.0);
        return new StepKernel(weights, inverse, conductance);
    }

    private StepKernel BuildBdfStepKernel(double a0)
    {
        var weights = new double[StateWidth];
        for (var poleIndex = 0; poleIndex < Poles.Length; poleIndex++)
        {
            var pole = Poles[poleIndex];
            var state = StateOffsets[poleIndex];
            var d = a0 - pole.Real;
            if (pole.Imaginary == 0.0)
            {
                weights[state] = 1.0 / d;
                continue;
            }
            var e = pole.Imaginary;
            var denominator = d * d + e * e;
            weights[state] = 2.0 * d / denominator;
            weights[state + 1] = -2.0 * e / denominator;
        }
        var inverse = InvertReal(BuildWaveMatrix(weights));
        var conductance = new double[Nports * Nports];
        for (var row = 0; row < Nports; row++)
            for (var column = 0; column < Nports; column++)
                conductance[row * Nports + column] = 2.0 * inverse[row * Nports + column] / Z0 -
                    (row == column ? 1.0 / Z0 : 0.0);
        return new StepKernel(weights, inverse, conductance);
    }

    internal void InitializeDc(RfmState state, IReadOnlyList<double> portVoltages)
    {
        var weights = DcWeights();
        var inverse = InvertReal(BuildWaveMatrix(weights));
        for (var input = 0; input < Nports; input++)
        {
            var incident = 0.0;
            for (var column = 0; column < Nports; column++)
                incident += inverse[input * Nports + column] * portVoltages[column] / Math.Sqrt(Z0);
            state.Incident[input] = incident;
            for (var index = 0; index < StateWidth; index++)
                state.Values[input * StateWidth + index] = weights[index] * incident;
        }
        state.Values.CopyTo(state.PreviousValues, 0);
        state.Values.CopyTo(state.OlderValues, 0);
    }

    private double[] DcWeights()
    {
        var weights = new double[StateWidth];
        for (var poleIndex = 0; poleIndex < Poles.Length; poleIndex++)
        {
            var pole = Poles[poleIndex];
            var state = StateOffsets[poleIndex];
            if (pole.Imaginary == 0.0)
            {
                weights[state] = -1.0 / pole.Real;
                continue;
            }
            var denominator = pole.Real * pole.Real + pole.Imaginary * pole.Imaginary;
            weights[state] = -2.0 * pole.Real / denominator;
            weights[state + 1] = -2.0 * pole.Imaginary / denominator;
        }
        return weights;
    }

    private double[] BuildWaveMatrix(IReadOnlyList<double> weights)
    {
        var matrix = new double[Nports * Nports];
        for (var row = 0; row < Nports; row++)
        {
            for (var column = 0; column < Nports; column++)
            {
                var response = row * Nports + column;
                var value = Constant[response] + (row == column ? 1.0 : 0.0);
                for (var poleIndex = 0; poleIndex < Poles.Length; poleIndex++)
                {
                    var residue = Residues[response * Poles.Length + poleIndex];
                    var state = StateOffsets[poleIndex];
                    value += residue.Real * weights[state];
                    if (Poles[poleIndex].Imaginary != 0.0)
                        value += residue.Imaginary * weights[state + 1];
                }
                matrix[row * Nports + column] = value;
            }
        }
        return matrix;
    }

    internal void FillDynamicOutputVoltage(ReadOnlySpan<double> values, Span<double> output)
    {
        FillHistoryVector(values, output);
        var voltageScale = Math.Sqrt(Z0);
        for (var index = 0; index < Nports; index++)
            output[index] *= voltageScale;
    }

    internal void FillDynamicOutputVoltageDerivative(
        ReadOnlySpan<double> values,
        ReadOnlySpan<double> incident,
        Span<double> output,
        Span<double> derivativeScratch)
    {
        for (var input = 0; input < Nports; input++)
        {
            var inputOffset = input * StateWidth;
            for (var poleIndex = 0; poleIndex < Poles.Length; poleIndex++)
            {
                var pole = Poles[poleIndex];
                var state = inputOffset + StateOffsets[poleIndex];
                if (pole.Imaginary == 0.0)
                {
                    derivativeScratch[state] = pole.Real * values[state] + incident[input];
                    continue;
                }
                var real = values[state];
                var imaginary = values[state + 1];
                derivativeScratch[state] = pole.Real * real + pole.Imaginary * imaginary + 2.0 * incident[input];
                derivativeScratch[state + 1] = -pole.Imaginary * real + pole.Real * imaginary;
            }
        }
        FillDynamicOutputVoltage(derivativeScratch, output);
    }

    private void FillHistoryVector(ReadOnlySpan<double> xBase, Span<double> history)
    {
        for (var output = 0; output < Nports; output++)
        {
            var value = 0.0;
            for (var term = _historyStarts[output]; term < _historyStarts[output + 1]; term++)
            {
                var state = _historyStateIndices[term];
                value += _historyResidueReal[term] * xBase[state];
                if (_historyHasImaginaryState[term])
                    value += _historyResidueImaginary[term] * xBase[state + 1];
            }
            history[output] = value;
        }
    }

    private double[] InvertReal(double[] matrix)
    {
        var complex = new Complex[Nports, Nports];
        for (var row = 0; row < Nports; row++)
            for (var column = 0; column < Nports; column++) complex[row, column] = matrix[row * Nports + column];
        var inverse = LinearAlgebra.Invert(complex);
        var real = new double[Nports * Nports];
        for (var row = 0; row < Nports; row++)
            for (var column = 0; column < Nports; column++)
            {
                if (Math.Abs(inverse[row, column].Imaginary) > 1e-12 * (1.0 + Math.Abs(inverse[row, column].Real)))
                    throw new InvalidOperationException("RFM real companion inverse became complex");
                real[row * Nports + column] = inverse[row, column].Real;
            }
        return real;
    }

    private static (SourceLine Line, string[] Tokens) Expect(List<SourceLine> lines, ref int cursor, string path, string keyword, int count)
    {
        if (cursor >= lines.Count) throw new InvalidDataException($"{path}: expected {keyword}, reached end of file");
        var line = lines[cursor++];
        var tokens = Tokens(line);
        if (tokens.Length != count || !tokens[0].Equals(keyword, StringComparison.OrdinalIgnoreCase))
            Fail(path, line, $"expected '{keyword}' with {count - 1} value(s)");
        return (line, tokens);
    }

    private static bool Keyword(SourceLine line, string keyword) => Tokens(line)[0].Equals(keyword, StringComparison.OrdinalIgnoreCase);
    private static string[] Tokens(SourceLine line) => line.Text.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);

    private static int Integer(string token, string path, SourceLine line, string label)
    {
        if (!int.TryParse(token, NumberStyles.Integer, CultureInfo.InvariantCulture, out var value))
            Fail(path, line, $"invalid {label} '{token}'");
        return value;
    }

    private static double Number(string token, string path, SourceLine line, string label)
    {
        token = token.Replace('D', 'E').Replace('d', 'e');
        if (!double.TryParse(token, NumberStyles.Float, CultureInfo.InvariantCulture, out var value) || !double.IsFinite(value))
            Fail(path, line, $"invalid {label} '{token}'");
        return value;
    }

    private static void Fail(string path, SourceLine line, string message) => throw new InvalidDataException($"{path}:{line.Number}: {message}");
}

internal sealed class RfmState
{
    internal double[] Values { get; }
    internal double[] PreviousValues { get; }
    internal double[] OlderValues { get; }
    internal double[] Incident { get; }
    internal double[] XBase { get; }
    internal double[] History { get; }
    internal double[] Offset { get; }
    internal double[] PortVoltages { get; }
    internal double[] TruncationScratch { get; }
    internal RfmCompanion? Companion { get; set; }

    internal RfmState(RfmModel model)
    {
        Values = new double[model.Nports * model.StateWidth];
        PreviousValues = new double[Values.Length];
        OlderValues = new double[Values.Length];
        Incident = new double[model.Nports];
        XBase = new double[Values.Length];
        History = new double[model.Nports];
        Offset = new double[model.Nports];
        PortVoltages = new double[model.Nports];
        TruncationScratch = new double[6 * model.Nports + Values.Length];
    }
}

internal sealed class RfmCompanion(RfmModel model)
{
    private double[] _inverse = [];
    private double[] _xBase = [];
    private double[] _weights = [];
    private double[] _history = [];

    internal double[] Conductance { get; private set; } = [];
    internal double[] Offset { get; private set; } = [];

    internal void Configure(
        double[] inverse,
        double[] xBase,
        double[] weights,
        double[] history,
        double[] conductance,
        double[] offset)
    {
        _inverse = inverse;
        _xBase = xBase;
        _weights = weights;
        _history = history;
        Conductance = conductance;
        Offset = offset;
    }

    internal void Commit(RfmState state, IReadOnlyList<double> portVoltages)
    {
        state.PreviousValues.CopyTo(state.OlderValues, 0);
        state.Values.CopyTo(state.PreviousValues, 0);
        for (var input = 0; input < model.Nports; input++)
        {
            var incident = 0.0;
            for (var output = 0; output < model.Nports; output++)
                incident += _inverse[input * model.Nports + output] * (portVoltages[output] / Math.Sqrt(model.Z0) - _history[output]);
            state.Incident[input] = incident;
            for (var stateIndex = 0; stateIndex < model.StateWidth; stateIndex++)
                state.Values[input * model.StateWidth + stateIndex] = _xBase[input * model.StateWidth + stateIndex] + _weights[stateIndex] * incident;
        }
    }
}
