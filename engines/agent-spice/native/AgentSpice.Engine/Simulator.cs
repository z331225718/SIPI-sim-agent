using System.Buffers;
using System.Diagnostics;
using System.Numerics;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace AgentSpice.Engine;

internal sealed record ComplexSample(double Re, double Im);
[JsonConverter(typeof(SimulationPointJsonConverter))]
internal readonly struct SimulationPoint(
    string analysis,
    double x,
    string[] valueNames,
    double[] values,
    int valueOffset,
    string[] complexNames,
    ComplexSample[] complex,
    double[]? internalSolution)
{
    public string Analysis { get; } = analysis;
    public double X { get; } = x;
    internal string[] ValueNames { get; } = valueNames;
    internal double[] Values { get; } = values;
    internal int ValueOffset { get; } = valueOffset;
    internal string[] ComplexNames { get; } = complexNames;
    internal ComplexSample[] Complex { get; } = complex;

    [JsonIgnore]
    internal double[]? InternalSolution { get; } = internalSolution;
}

internal sealed class SimulationPointJsonConverter : JsonConverter<SimulationPoint>
{
    public override SimulationPoint Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options) =>
        throw new NotSupportedException();

    public override void Write(Utf8JsonWriter writer, SimulationPoint point, JsonSerializerOptions options)
    {
        writer.WriteStartObject();
        writer.WriteString("analysis", point.Analysis);
        writer.WriteNumber("x", point.X);
        writer.WritePropertyName("values");
        writer.WriteStartObject();
        for (var index = 0; index < point.ValueNames.Length; index++)
            writer.WriteNumber(point.ValueNames[index], point.Values[point.ValueOffset + index]);
        writer.WriteEndObject();
        writer.WritePropertyName("complex");
        writer.WriteStartObject();
        for (var index = 0; index < point.ComplexNames.Length; index++)
        {
            writer.WritePropertyName(point.ComplexNames[index]);
            writer.WriteStartObject();
            writer.WriteNumber("re", point.Complex[index].Re);
            writer.WriteNumber("im", point.Complex[index].Im);
            writer.WriteEndObject();
        }
        writer.WriteEndObject();
        writer.WriteEndObject();
    }
}

internal sealed class SimulationStatistics
{
    internal bool CollectSparseFactorProfile { get; } =
        Environment.GetEnvironmentVariable("AGENT_SPICE_NATIVE_FACTOR_PROFILE") == "1";
    internal long SparseCopyScaleTicks { get; set; }
    internal long SparseEliminationTicks { get; set; }
    internal long SparseTriangularSolveTicks { get; set; }
    internal long SparseFreshFactorTicks { get; set; }
    internal long SparsePlanBuildTicks { get; set; }
    internal int SparsePivotRejectionCount { get; set; }
    internal int SparseLastRejectedPivotColumn { get; set; } = -1;
    internal double SparseMinimumRejectedPivotRatio { get; set; } = double.PositiveInfinity;
    internal double SparseMaximumRejectedPivotRatio { get; set; }
    public int AcceptedTransientSteps { get; internal set; }
    public int RejectedTransientSteps { get; internal set; }
    public int BreakpointTransientSteps { get; internal set; }
    public int DiscontinuityTransientEvents { get; internal set; }
    public int DeviceTruncationEvaluations { get; internal set; }
    public int StepDoublingEvaluations { get; internal set; }
    public int NewtonIterations { get; internal set; }
    public int LineSearchBacktracks { get; internal set; }
    public int PredictorInitializations { get; internal set; }
    public int SparseSymbolicFactorizations { get; internal set; }
    public int SparseNumericRefactorizations { get; internal set; }
    public int SparsePlanFallbacks { get; internal set; }
    public int AcMatrixAssemblyReplays { get; internal set; }
    public double MaximumConvergedResidualRatio { get; internal set; }

    internal string SparseFactorProfileSummary()
    {
        static double Seconds(long ticks) => (double)ticks / Stopwatch.Frequency;
        return $"sparse-profile copy-scale={Seconds(SparseCopyScaleTicks):F6}s " +
            $"eliminate={Seconds(SparseEliminationTicks):F6}s " +
            $"solve={Seconds(SparseTriangularSolveTicks):F6}s " +
            $"fresh-factor={Seconds(SparseFreshFactorTicks):F6}s " +
            $"plan-build={Seconds(SparsePlanBuildTicks):F6}s " +
            $"pivot-rejections={SparsePivotRejectionCount} " +
            $"pivot-ratio=[{SparseMinimumRejectedPivotRatio:E3},{SparseMaximumRejectedPivotRatio:E3}] " +
            $"last-pivot-column={SparseLastRejectedPivotColumn}";
    }

    internal void RecordSparsePivotRejection(int column, double ratio)
    {
        if (!CollectSparseFactorProfile)
            return;
        SparsePivotRejectionCount++;
        SparseLastRejectedPivotColumn = column;
        SparseMinimumRejectedPivotRatio = Math.Min(SparseMinimumRejectedPivotRatio, ratio);
        SparseMaximumRejectedPivotRatio = Math.Max(SparseMaximumRejectedPivotRatio, ratio);
    }
}

internal sealed record SimulationResult(
    IReadOnlyList<string> Nodes,
    IReadOnlyList<SimulationPoint> Points,
    SimulationStatistics Statistics);

internal sealed record OutputProbe(string Name, int Index);

internal readonly record struct BjtTerminalVector(double Collector, double Base, double Emitter)
{
    internal static BjtTerminalVector Zero => new(0.0, 0.0, 0.0);

    public static BjtTerminalVector operator +(BjtTerminalVector left, BjtTerminalVector right) =>
        new(left.Collector + right.Collector, left.Base + right.Base, left.Emitter + right.Emitter);

    public static BjtTerminalVector operator -(BjtTerminalVector left, BjtTerminalVector right) =>
        new(left.Collector - right.Collector, left.Base - right.Base, left.Emitter - right.Emitter);

    public static BjtTerminalVector operator *(double scale, BjtTerminalVector values) =>
        new(scale * values.Collector, scale * values.Base, scale * values.Emitter);
}

internal readonly record struct BjtTerminalMatrix(
    double Cc,
    double Cb,
    double Ce,
    double Bc,
    double Bb,
    double Be,
    double Ec,
    double Eb,
    double Ee)
{
    internal BjtTerminalVector Multiply(double collector, double @base, double emitter) => new(
        Cc * collector + Cb * @base + Ce * emitter,
        Bc * collector + Bb * @base + Be * emitter,
        Ec * collector + Eb * @base + Ee * emitter);
}

internal readonly record struct BjtEvaluation(
    double CollectorCurrent,
    double BaseCurrent,
    double EmitterCurrent,
    double Jcc,
    double Jcb,
    double Jce,
    double Jbc,
    double Jbb,
    double Jbe,
    double Jec,
    double Jeb,
    double Jee,
    BjtTerminalVector Charge,
    BjtTerminalMatrix Capacitance);

internal readonly record struct DiodeEvaluation(
    double Current,
    double Conductance,
    double Charge,
    double Capacitance);

internal readonly record struct Dual4(
    double Value,
    double Drain,
    double Gate,
    double Source,
    double Bulk)
{
    internal static Dual4 Variable(double value, int index) => index switch
    {
        0 => new Dual4(value, 1.0, 0.0, 0.0, 0.0),
        1 => new Dual4(value, 0.0, 1.0, 0.0, 0.0),
        2 => new Dual4(value, 0.0, 0.0, 1.0, 0.0),
        3 => new Dual4(value, 0.0, 0.0, 0.0, 1.0),
        _ => throw new ArgumentOutOfRangeException(nameof(index))
    };

    public static implicit operator Dual4(double value) => new(value, 0.0, 0.0, 0.0, 0.0);

    public static Dual4 operator +(Dual4 left, Dual4 right) => new(
        left.Value + right.Value,
        left.Drain + right.Drain,
        left.Gate + right.Gate,
        left.Source + right.Source,
        left.Bulk + right.Bulk);

    public static Dual4 operator -(Dual4 left, Dual4 right) => new(
        left.Value - right.Value,
        left.Drain - right.Drain,
        left.Gate - right.Gate,
        left.Source - right.Source,
        left.Bulk - right.Bulk);

    public static Dual4 operator -(Dual4 value) => new(
        -value.Value,
        -value.Drain,
        -value.Gate,
        -value.Source,
        -value.Bulk);

    public static Dual4 operator *(Dual4 left, Dual4 right) => new(
        left.Value * right.Value,
        left.Drain * right.Value + left.Value * right.Drain,
        left.Gate * right.Value + left.Value * right.Gate,
        left.Source * right.Value + left.Value * right.Source,
        left.Bulk * right.Value + left.Value * right.Bulk);

    public static Dual4 operator *(double scale, Dual4 value) => new(
        scale * value.Value,
        scale * value.Drain,
        scale * value.Gate,
        scale * value.Source,
        scale * value.Bulk);

    public static Dual4 operator *(Dual4 value, double scale) => scale * value;

    public static Dual4 operator /(Dual4 value, double divisor) => (1.0 / divisor) * value;

    internal static Dual4 Sqrt(Dual4 value)
    {
        var root = Math.Sqrt(Math.Max(value.Value, 0.0));
        if (root == 0.0)
            return new Dual4(root, 0.0, 0.0, 0.0, 0.0);
        var scale = 1.0 / (2.0 * root);
        return new Dual4(
            root,
            scale * value.Drain,
            scale * value.Gate,
            scale * value.Source,
            scale * value.Bulk);
    }

    internal static Dual4 ExpClamped(Dual4 value)
    {
        var exponential = Math.Exp(Math.Clamp(value.Value, -80.0, 40.0));
        return new Dual4(
            exponential,
            exponential * value.Drain,
            exponential * value.Gate,
            exponential * value.Source,
            exponential * value.Bulk);
    }
}

internal readonly record struct MosTerminalVector(double Drain, double Gate, double Source, double Bulk)
{
    internal static MosTerminalVector Zero => new(0.0, 0.0, 0.0, 0.0);

    public static MosTerminalVector operator +(MosTerminalVector left, MosTerminalVector right) =>
        new(
            left.Drain + right.Drain,
            left.Gate + right.Gate,
            left.Source + right.Source,
            left.Bulk + right.Bulk);

    public static MosTerminalVector operator -(MosTerminalVector left, MosTerminalVector right) =>
        new(
            left.Drain - right.Drain,
            left.Gate - right.Gate,
            left.Source - right.Source,
            left.Bulk - right.Bulk);

    public static MosTerminalVector operator *(double scale, MosTerminalVector values) =>
        new(
            scale * values.Drain,
            scale * values.Gate,
            scale * values.Source,
            scale * values.Bulk);
}

internal readonly record struct MosTerminalMatrix(
    double Dd,
    double Dg,
    double Ds,
    double Db,
    double Gd,
    double Gg,
    double Gs,
    double Gb,
    double Sd,
    double Sg,
    double Ss,
    double Sb,
    double Bd,
    double Bg,
    double Bs,
    double Bb)
{
    public static MosTerminalMatrix operator +(MosTerminalMatrix left, MosTerminalMatrix right) =>
        new(
            left.Dd + right.Dd,
            left.Dg + right.Dg,
            left.Ds + right.Ds,
            left.Db + right.Db,
            left.Gd + right.Gd,
            left.Gg + right.Gg,
            left.Gs + right.Gs,
            left.Gb + right.Gb,
            left.Sd + right.Sd,
            left.Sg + right.Sg,
            left.Ss + right.Ss,
            left.Sb + right.Sb,
            left.Bd + right.Bd,
            left.Bg + right.Bg,
            left.Bs + right.Bs,
            left.Bb + right.Bb);

    internal MosTerminalVector Multiply(double drain, double gate, double source, double bulk) => new(
        Dd * drain + Dg * gate + Ds * source + Db * bulk,
        Gd * drain + Gg * gate + Gs * source + Gb * bulk,
        Sd * drain + Sg * gate + Ss * source + Sb * bulk,
        Bd * drain + Bg * gate + Bs * source + Bb * bulk);
}

internal readonly record struct MosGateVector(double GateDrain, double GateSource, double GateBulk)
{
    internal static MosGateVector Zero => new(0.0, 0.0, 0.0);

    public static MosGateVector operator +(MosGateVector left, MosGateVector right) =>
        new(
            left.GateDrain + right.GateDrain,
            left.GateSource + right.GateSource,
            left.GateBulk + right.GateBulk);

    public static MosGateVector operator -(MosGateVector left, MosGateVector right) =>
        new(
            left.GateDrain - right.GateDrain,
            left.GateSource - right.GateSource,
            left.GateBulk - right.GateBulk);

    public static MosGateVector operator *(double scale, MosGateVector values) =>
        new(
            scale * values.GateDrain,
            scale * values.GateSource,
            scale * values.GateBulk);

    internal MosGateVector Multiply(MosGateVector values) =>
        new(
            GateDrain * values.GateDrain,
            GateSource * values.GateSource,
            GateBulk * values.GateBulk);
}

internal readonly record struct MosEvaluation(
    MosTerminalVector Current,
    MosTerminalMatrix Conductance,
    MosTerminalVector JunctionCharge,
    MosTerminalMatrix JunctionCapacitance,
    MosGateVector MeyerHalfCapacitance);

internal readonly record struct MosDynamicChargeEvaluation(
    MosTerminalVector Charge,
    MosTerminalMatrix Capacitance,
    MosGateVector GateCharge,
    MosGateVector GateVoltage);

internal sealed class LinearContext
{
    internal IComplexFactorization? Factorization { get; set; }
    internal double[]? NonlinearGuess { get; set; }
    internal Dictionary<string, int> NodeIndex { get; }
    internal List<Element> BranchElements { get; }
    internal List<Element> SourceElements { get; }
    internal Dictionary<string, int> BranchIndex { get; }
    internal bool OptimizeRepeatedSolve { get; }
    internal SparseFactorizationCache SparseFactorizationCache { get; } = new();
    internal IReadOnlyDictionary<string, OutputProbe[]> OutputProbes { get; }
    internal IReadOnlyDictionary<string, string[]> OutputNames { get; }

    internal LinearContext(Deck deck)
    {
        NodeIndex = deck.Nodes.Select((node, index) => (node, index)).ToDictionary(pair => pair.node, pair => pair.index, StringComparer.OrdinalIgnoreCase);
        BranchElements = deck.Elements.Where(element => element.Kind is 'V' or 'L' or 'E' or 'H').ToList();
        SourceElements = deck.Elements.Where(element => element.Kind is 'V' or 'I').ToList();
        BranchIndex = BranchElements.Select((element, offset) => (element.Name, Index: deck.Nodes.Count + offset)).ToDictionary(pair => pair.Name, pair => pair.Index, StringComparer.OrdinalIgnoreCase);
        OptimizeRepeatedSolve = deck.Analyses.Count(analysis => analysis.Kind is "op" or "dc") > 1 ||
            deck.Analyses.Any(analysis => analysis.Kind == "dc" && analysis.A != analysis.B);
        var probes = deck.Nodes
            .Select((name, index) => new OutputProbe(name, index))
            .Concat(BranchElements.Select(element => new OutputProbe(element.Name, BranchIndex[element.Name])))
            .ToArray();
        OutputProbes = new[] { "op", "dc", "ac" }.ToDictionary(
            kind => kind,
            kind => probes.Where(probe => Simulator.RequestedOutput(deck, kind, probe.Name)).ToArray(),
            StringComparer.OrdinalIgnoreCase);
        OutputNames = OutputProbes.ToDictionary(
            pair => pair.Key,
            pair => pair.Value.Select(probe => probe.Name).ToArray(),
            StringComparer.OrdinalIgnoreCase);
    }
}

internal readonly record struct TransientMatrixKey(
    IntegrationMethod IntegrationMethod,
    bool UseBackwardEuler,
    long StepBits,
    long PreviousStepBits);

internal sealed class TransientContext
{
    private const int MaximumLinearSystemCaches = 64;
    private readonly Dictionary<TransientMatrixKey, IComplexFactorization> _linearSystemCaches = [];
    private readonly Queue<TransientMatrixKey> _linearSystemCacheOrder = [];
    private IComplexFactorization? _factorization;
    private TransientMatrixKey? _factorizationKey;
    internal double Step { get; private set; }
    internal double DefaultSourceTransition { get; }
    internal IntegrationMethod IntegrationMethod { get; }
    internal bool UseBackwardEuler { get; private set; }
    internal bool UsesBdfIntegration => UseBackwardEuler || IntegrationMethod == IntegrationMethod.Gear;
    internal double PreviousAcceptedStep { get; set; }
    internal double OlderAcceptedStep { get; set; }
    internal int AcceptedHistoryDepth { get; set; }
    internal double[] Capacitors { get; }
    internal double[] CapacitorPreviousVoltages { get; }
    internal double[] CapacitorOlderVoltages { get; }
    internal double[] CapacitorCurrents { get; }
    internal double[] Inductors { get; }
    internal double[] InductorPreviousCurrents { get; }
    internal double[] InductorOlderCurrents { get; }
    internal double[] InductorVoltages { get; }
    internal double[] DiodeCharges { get; }
    internal double[] DiodePreviousCharges { get; }
    internal double[] DiodeOlderCharges { get; }
    internal double[] DiodeDisplacementCurrents { get; }
    internal BjtTerminalVector[] BjtCharges { get; }
    internal BjtTerminalVector[] BjtPreviousCharges { get; }
    internal BjtTerminalVector[] BjtOlderCharges { get; }
    internal BjtTerminalVector[] BjtDisplacementCurrents { get; }
    internal MosTerminalVector[] MosCharges { get; }
    internal MosTerminalVector[] MosPreviousCharges { get; }
    internal MosTerminalVector[] MosOlderCharges { get; }
    internal MosTerminalVector[] MosDisplacementCurrents { get; }
    internal MosGateVector[] MosGateCharges { get; }
    internal MosGateVector[] MosGateVoltages { get; }
    internal MosGateVector[] MosMeyerHalfCapacitances { get; }
    internal Dictionary<string, RfmState> RfmStates { get; }
    internal IComplexFactorization? Factorization
    {
        get
        {
            var key = CurrentMatrixKey();
            if (_factorizationKey == key)
                return _factorization;
            _factorizationKey = key;
            _factorization = _linearSystemCaches.GetValueOrDefault(key);
            return _factorization;
        }
        set
        {
            var key = CurrentMatrixKey();
            _factorizationKey = key;
            _factorization = value;
            if (value is not IFactorizationSnapshot snapshot)
                return;
            if (!_linearSystemCaches.ContainsKey(key))
                _linearSystemCacheOrder.Enqueue(key);
            _linearSystemCaches[key] = snapshot.Snapshot();
            while (_linearSystemCaches.Count > MaximumLinearSystemCaches)
            {
                var expired = _linearSystemCacheOrder.Dequeue();
                _linearSystemCaches.Remove(expired);
            }
        }
    }
    internal double[]? NonlinearGuess { get; set; }
    internal double[]? PreviousNonlinearGuess { get; private set; }
    internal double PreviousNonlinearStep { get; private set; }
    internal Dictionary<string, int> NodeIndex { get; }
    internal List<Element> BranchElements { get; }
    internal List<Element> CapacitorElements { get; }
    internal List<Element> InductorElements { get; }
    internal List<Element> DiodeElements { get; }
    internal List<Element> BjtElements { get; }
    internal List<Element> MosElements { get; }
    internal List<RfmInstance> RfmInstances { get; }
    internal Dictionary<string, int> BranchIndex { get; }
    internal OutputProbe[] OutputProbes { get; }
    internal string[] OutputNames { get; }
    internal SparseFactorizationCache SparseFactorizationCache { get; } = new();

    internal TransientContext(Deck deck, double step)
    {
        Step = step;
        DefaultSourceTransition = step;
        IntegrationMethod = deck.TransientIntegrationMethod;
        NodeIndex = deck.Nodes.Select((node, index) => (node, index)).ToDictionary(pair => pair.node, pair => pair.index, StringComparer.OrdinalIgnoreCase);
        BranchElements = deck.Elements.Where(element => element.Kind is 'V' or 'L' or 'E' or 'H').ToList();
        CapacitorElements = deck.Elements.Where(element => element.Kind == 'C').ToList();
        InductorElements = deck.Elements.Where(element => element.Kind == 'L').ToList();
        DiodeElements = deck.Elements.Where(element => element.Kind == 'D').ToList();
        BjtElements = deck.Elements.Where(element => element.Kind == 'Q').ToList();
        MosElements = deck.Elements.Where(element => element.Kind == 'M').ToList();
        RfmInstances = deck.RfmInstances;
        BranchIndex = BranchElements.Select((element, offset) => (element.Name, Index: deck.Nodes.Count + offset)).ToDictionary(pair => pair.Name, pair => pair.Index, StringComparer.OrdinalIgnoreCase);
        OutputProbes = deck.Nodes
            .Select((name, index) => new OutputProbe(name, index))
            .Concat(BranchElements.Select(element => new OutputProbe(element.Name, BranchIndex[element.Name])))
            .Where(probe => Simulator.RequestedOutput(deck, "tran", probe.Name))
            .ToArray();
        OutputNames = OutputProbes.Select(probe => probe.Name).ToArray();
        for (var index = 0; index < CapacitorElements.Count; index++)
            CapacitorElements[index].TransientStateIndex = index;
        for (var index = 0; index < InductorElements.Count; index++)
            InductorElements[index].TransientStateIndex = index;
        for (var index = 0; index < DiodeElements.Count; index++)
            DiodeElements[index].TransientStateIndex = index;
        for (var index = 0; index < BjtElements.Count; index++)
            BjtElements[index].TransientStateIndex = index;
        for (var index = 0; index < MosElements.Count; index++)
            MosElements[index].TransientStateIndex = index;
        Capacitors = new double[CapacitorElements.Count];
        CapacitorPreviousVoltages = new double[CapacitorElements.Count];
        CapacitorOlderVoltages = new double[CapacitorElements.Count];
        CapacitorCurrents = new double[CapacitorElements.Count];
        Inductors = new double[InductorElements.Count];
        InductorPreviousCurrents = new double[InductorElements.Count];
        InductorOlderCurrents = new double[InductorElements.Count];
        InductorVoltages = new double[InductorElements.Count];
        DiodeCharges = new double[DiodeElements.Count];
        DiodePreviousCharges = new double[DiodeElements.Count];
        DiodeOlderCharges = new double[DiodeElements.Count];
        DiodeDisplacementCurrents = new double[DiodeElements.Count];
        BjtCharges = new BjtTerminalVector[BjtElements.Count];
        BjtPreviousCharges = new BjtTerminalVector[BjtElements.Count];
        BjtOlderCharges = new BjtTerminalVector[BjtElements.Count];
        BjtDisplacementCurrents = new BjtTerminalVector[BjtElements.Count];
        MosCharges = new MosTerminalVector[MosElements.Count];
        MosPreviousCharges = new MosTerminalVector[MosElements.Count];
        MosOlderCharges = new MosTerminalVector[MosElements.Count];
        MosDisplacementCurrents = new MosTerminalVector[MosElements.Count];
        MosGateCharges = new MosGateVector[MosElements.Count];
        MosGateVoltages = new MosGateVector[MosElements.Count];
        MosMeyerHalfCapacitances = new MosGateVector[MosElements.Count];
        RfmStates = deck.RfmInstances.ToDictionary(instance => instance.Name, instance => instance.Model.CreateState(), StringComparer.OrdinalIgnoreCase);
    }

    internal void SetStep(double step)
    {
        if (step <= 0.0 || !double.IsFinite(step))
            throw new ArgumentOutOfRangeException(nameof(step));
        if (Step == step)
            return;
        Step = step;
    }

    internal void SetBackwardEuler(bool enabled)
    {
        if (UseBackwardEuler == enabled)
            return;
        UseBackwardEuler = enabled;
    }

    internal void RestartTruncationHistory() => AcceptedHistoryDepth = 0;

    internal void InitializeNonlinearGuess(double[] guess)
    {
        NonlinearGuess = guess;
        PreviousNonlinearGuess = null;
        PreviousNonlinearStep = 0.0;
    }

    internal double[] PredictNonlinearGuess(out bool usedPrediction)
    {
        if (NonlinearGuess is null)
        {
            usedPrediction = false;
            return [];
        }
        if (PreviousNonlinearGuess is null || PreviousNonlinearStep <= 0.0)
        {
            usedPrediction = false;
            return NonlinearGuess.ToArray();
        }

        usedPrediction = true;
        var ratio = Math.Clamp(Step / PreviousNonlinearStep, 0.0, 2.0);
        var predicted = new double[NonlinearGuess.Length];
        for (var index = 0; index < predicted.Length; index++)
            predicted[index] = NonlinearGuess[index] +
                ratio * (NonlinearGuess[index] - PreviousNonlinearGuess[index]);
        return predicted;
    }

    internal void AdvanceNonlinearGuess(double[] guess)
    {
        PreviousNonlinearGuess = NonlinearGuess;
        NonlinearGuess = guess;
        PreviousNonlinearStep = Step;
    }

    internal DerivativeCoefficients BdfCoefficients()
    {
        if (UseBackwardEuler)
            return new DerivativeCoefficients(1.0 / Step, -1.0 / Step, 0.0);
        if (PreviousAcceptedStep <= 0.0)
            return new DerivativeCoefficients(1.0 / Step, -1.0 / Step, 0.0);
        var ratio = Step / PreviousAcceptedStep;
        return new DerivativeCoefficients(
            (1.0 + 2.0 * ratio) / (Step * (1.0 + ratio)),
            -(1.0 + ratio) / Step,
            ratio * ratio / (Step * (1.0 + ratio)));
    }

    internal TransientSnapshot CaptureState() => new(
        Capacitors.ToArray(),
        CapacitorPreviousVoltages.ToArray(),
        CapacitorOlderVoltages.ToArray(),
        CapacitorCurrents.ToArray(),
        Inductors.ToArray(),
        InductorPreviousCurrents.ToArray(),
        InductorOlderCurrents.ToArray(),
        InductorVoltages.ToArray(),
        DiodeCharges.ToArray(),
        DiodePreviousCharges.ToArray(),
        DiodeOlderCharges.ToArray(),
        DiodeDisplacementCurrents.ToArray(),
        BjtCharges.ToArray(),
        BjtPreviousCharges.ToArray(),
        BjtOlderCharges.ToArray(),
        BjtDisplacementCurrents.ToArray(),
        MosCharges.ToArray(),
        MosPreviousCharges.ToArray(),
        MosOlderCharges.ToArray(),
        MosDisplacementCurrents.ToArray(),
        MosGateCharges.ToArray(),
        MosGateVoltages.ToArray(),
        MosMeyerHalfCapacitances.ToArray(),
        RfmInstances.Select(instance => RfmStateSnapshot.Capture(RfmStates[instance.Name])).ToArray(),
        NonlinearGuess?.ToArray(),
        PreviousNonlinearGuess?.ToArray(),
        PreviousNonlinearStep,
        PreviousAcceptedStep,
        OlderAcceptedStep,
        AcceptedHistoryDepth,
        UseBackwardEuler);

    internal void RestoreState(TransientSnapshot snapshot)
    {
        snapshot.Capacitors.CopyTo(Capacitors, 0);
        snapshot.CapacitorPreviousVoltages.CopyTo(CapacitorPreviousVoltages, 0);
        snapshot.CapacitorOlderVoltages.CopyTo(CapacitorOlderVoltages, 0);
        snapshot.CapacitorCurrents.CopyTo(CapacitorCurrents, 0);
        snapshot.Inductors.CopyTo(Inductors, 0);
        snapshot.InductorPreviousCurrents.CopyTo(InductorPreviousCurrents, 0);
        snapshot.InductorOlderCurrents.CopyTo(InductorOlderCurrents, 0);
        snapshot.InductorVoltages.CopyTo(InductorVoltages, 0);
        snapshot.DiodeCharges.CopyTo(DiodeCharges, 0);
        snapshot.DiodePreviousCharges.CopyTo(DiodePreviousCharges, 0);
        snapshot.DiodeOlderCharges.CopyTo(DiodeOlderCharges, 0);
        snapshot.DiodeDisplacementCurrents.CopyTo(DiodeDisplacementCurrents, 0);
        snapshot.BjtCharges.CopyTo(BjtCharges, 0);
        snapshot.BjtPreviousCharges.CopyTo(BjtPreviousCharges, 0);
        snapshot.BjtOlderCharges.CopyTo(BjtOlderCharges, 0);
        snapshot.BjtDisplacementCurrents.CopyTo(BjtDisplacementCurrents, 0);
        snapshot.MosCharges.CopyTo(MosCharges, 0);
        snapshot.MosPreviousCharges.CopyTo(MosPreviousCharges, 0);
        snapshot.MosOlderCharges.CopyTo(MosOlderCharges, 0);
        snapshot.MosDisplacementCurrents.CopyTo(MosDisplacementCurrents, 0);
        snapshot.MosGateCharges.CopyTo(MosGateCharges, 0);
        snapshot.MosGateVoltages.CopyTo(MosGateVoltages, 0);
        snapshot.MosMeyerHalfCapacitances.CopyTo(MosMeyerHalfCapacitances, 0);
        for (var index = 0; index < RfmInstances.Count; index++)
            snapshot.RfmStates[index].Restore(RfmStates[RfmInstances[index].Name]);
        NonlinearGuess = snapshot.NonlinearGuess?.ToArray();
        PreviousNonlinearGuess = snapshot.PreviousNonlinearGuess?.ToArray();
        PreviousNonlinearStep = snapshot.PreviousNonlinearStep;
        PreviousAcceptedStep = snapshot.PreviousAcceptedStep;
        OlderAcceptedStep = snapshot.OlderAcceptedStep;
        AcceptedHistoryDepth = snapshot.AcceptedHistoryDepth;
        UseBackwardEuler = snapshot.UseBackwardEuler;
    }

    private TransientMatrixKey CurrentMatrixKey()
    {
        var previousStep = IntegrationMethod == IntegrationMethod.Gear && !UseBackwardEuler
            ? PreviousAcceptedStep
            : 0.0;
        return new TransientMatrixKey(
            IntegrationMethod,
            UseBackwardEuler,
            BitConverter.DoubleToInt64Bits(Step),
            BitConverter.DoubleToInt64Bits(previousStep));
    }
}

internal sealed record TransientSnapshot(
    double[] Capacitors,
    double[] CapacitorPreviousVoltages,
    double[] CapacitorOlderVoltages,
    double[] CapacitorCurrents,
    double[] Inductors,
    double[] InductorPreviousCurrents,
    double[] InductorOlderCurrents,
    double[] InductorVoltages,
    double[] DiodeCharges,
    double[] DiodePreviousCharges,
    double[] DiodeOlderCharges,
    double[] DiodeDisplacementCurrents,
    BjtTerminalVector[] BjtCharges,
    BjtTerminalVector[] BjtPreviousCharges,
    BjtTerminalVector[] BjtOlderCharges,
    BjtTerminalVector[] BjtDisplacementCurrents,
    MosTerminalVector[] MosCharges,
    MosTerminalVector[] MosPreviousCharges,
    MosTerminalVector[] MosOlderCharges,
    MosTerminalVector[] MosDisplacementCurrents,
    MosGateVector[] MosGateCharges,
    MosGateVector[] MosGateVoltages,
    MosGateVector[] MosMeyerHalfCapacitances,
    RfmStateSnapshot[] RfmStates,
    double[]? NonlinearGuess,
    double[]? PreviousNonlinearGuess,
    double PreviousNonlinearStep,
    double PreviousAcceptedStep,
    double OlderAcceptedStep,
    int AcceptedHistoryDepth,
    bool UseBackwardEuler);

internal readonly record struct DerivativeCoefficients(double A0, double A1, double A2);

internal sealed record RfmStateSnapshot(
    double[] Values,
    double[] PreviousValues,
    double[] OlderValues,
    double[] Incident,
    double[] PortVoltages)
{
    internal static RfmStateSnapshot Capture(RfmState state) => new(
        state.Values.ToArray(),
        state.PreviousValues.ToArray(),
        state.OlderValues.ToArray(),
        state.Incident.ToArray(),
        state.PortVoltages.ToArray());

    internal void Restore(RfmState state)
    {
        Values.CopyTo(state.Values, 0);
        PreviousValues.CopyTo(state.PreviousValues, 0);
        OlderValues.CopyTo(state.OlderValues, 0);
        Incident.CopyTo(state.Incident, 0);
        PortVoltages.CopyTo(state.PortVoltages, 0);
    }
}

internal sealed class NonlinearConvergenceException(string message) : InvalidOperationException(message);

internal static class Simulator
{
    internal static SimulationResult Run(Deck deck)
    {
        var points = new List<SimulationPoint>();
        var statistics = new SimulationStatistics();
        LinearContext? linearContext = null;
        foreach (var analysis in deck.Analyses)
        {
            switch (analysis.Kind)
            {
                case "op":
                    linearContext ??= new LinearContext(deck);
                    points.Add(SolvePoint(deck, "op", 0.0, null, null, null, linear: linearContext, statistics: statistics));
                    break;
                case "dc":
                    ValidateDcSweep(deck, analysis);
                    linearContext ??= new LinearContext(deck);
                    for (var value = analysis.A; Reached(value, analysis.B, analysis.C); value += analysis.C)
                        points.Add(SolvePoint(deck, "dc", value, analysis.Mode, null, null, linear: linearContext, statistics: statistics));
                    break;
                case "ac":
                    {
                        double[]? nonlinearOperatingPoint = null;
                        if (deck.HasNonlinearDevices)
                        {
                            linearContext ??= new LinearContext(deck);
                            _ = SolvePoint(deck, "op", 0.0, null, null, null, linear: linearContext, statistics: statistics);
                            nonlinearOperatingPoint = linearContext.NonlinearGuess;
                        }
                        var acContext = linearContext ?? new LinearContext(deck);
                        var factorizationCache = new SparseFactorizationCache();
                        foreach (var frequency in Frequencies(analysis))
                            points.Add(SolvePoint(
                                deck,
                                "ac",
                                frequency,
                                null,
                                frequency,
                                null,
                                linear: acContext,
                                nonlinearGuess: nonlinearOperatingPoint,
                                statistics: statistics,
                                factorizationCache: factorizationCache));
                        break;
                    }
                case "tran":
                    points.AddRange(RunTransient(deck, analysis, statistics));
                    break;
                default:
                    throw new InvalidDataException($"unsupported analysis '{analysis.Kind}'");
            }
        }
        return new SimulationResult(
            deck.Nodes.Where(node => !deck.InternalNodes.Contains(node)).ToArray(),
            points,
            statistics);
    }

    private static void ValidateDcSweep(Deck deck, Analysis analysis)
    {
        var source = deck.Elements.FirstOrDefault(element => element.Name.Equals(analysis.Mode, StringComparison.OrdinalIgnoreCase));
        if (source is null)
            throw new InvalidDataException($".dc source '{analysis.Mode}' not found");
        if (source.Kind is not ('V' or 'I'))
            throw new InvalidDataException($".dc target '{analysis.Mode}' must be an independent V or I source");
        if (analysis.C == 0.0 || Math.Sign(analysis.B - analysis.A) != Math.Sign(analysis.C))
            throw new InvalidDataException(".dc step must move from start toward stop");
    }

    private static bool Reached(double value, double stop, double step) => step > 0.0
        ? value <= stop + Math.Abs(step) * 1e-9
        : value >= stop - Math.Abs(step) * 1e-9;

    private static IEnumerable<double> Frequencies(Analysis analysis)
    {
        if (analysis.A <= 0.0 || analysis.B <= 0.0 || analysis.C < analysis.B)
            throw new InvalidDataException("invalid .ac frequency range");
        if (analysis.Mode == "lin")
        {
            var count = Math.Max(1, (int)Math.Round(analysis.A));
            for (var index = 0; index < count; index++)
                yield return analysis.B + (analysis.C - analysis.B) * index / Math.Max(1, count - 1);
            yield break;
        }
        var span = analysis.Mode == "dec" ? Math.Log10(analysis.C / analysis.B) : Math.Log(analysis.C / analysis.B, 2.0);
        var countPerUnit = Math.Max(1, (int)Math.Round(analysis.A));
        var countTotal = (int)Math.Floor(span * countPerUnit);
        for (var index = 0; index <= countTotal; index++)
            yield return analysis.B * Math.Pow(analysis.Mode == "dec" ? 10.0 : 2.0, (double)index / countPerUnit);
    }

    private static IEnumerable<SimulationPoint> RunTransient(
        Deck deck,
        Analysis analysis,
        SimulationStatistics statistics)
    {
        if (analysis.A <= 0.0 || analysis.B < 0.0 || analysis.C < 0.0 || analysis.C > analysis.B)
            throw new InvalidDataException("invalid .tran step, stop, or start");
        var context = new TransientContext(deck, analysis.A);
        context.SetBackwardEuler(deck.Elements.Any(element => element.Transient?.HasInitialBreakpoint == true));
        var maximumPoints = checked((int)Math.Floor(analysis.B / analysis.A + 1e-9) + 1);
        var outputStorage = new double[checked(maximumPoints * context.OutputProbes.Length)];
        var outputOffset = 0;

        var initial = SolvePoint(
            deck,
            "tran",
            0.0,
            null,
            null,
            null,
            captureInternal: true,
            statistics: statistics);
        InitializeStoredState(deck, context, initial);
        if (deck.HasNonlinearDevices)
            context.InitializeNonlinearGuess(ExtractSolution(initial));
        foreach (var instance in deck.RfmInstances)
        {
            var state = context.RfmStates[instance.Name];
            FillPortVoltages(initial, context.NodeIndex, instance, state.PortVoltages);
            instance.Model.InitializeDc(state, state.PortVoltages);
        }
        if (analysis.C == 0.0)
            yield return initial;

        var currentTime = 0.0;
        var minimumStep = Math.Max(1e-18, analysis.A * 1e-9);
        var restartIntegrationAtSourceEdges = context.IntegrationMethod == IntegrationMethod.Gear ||
            context.BjtElements.Any(element => deck.BjtModels[element.ModelName!].HasDynamicCharge) ||
            context.MosElements.Any(element => deck.MosModels[element.ModelName!].HasDynamicCharge) ||
            deck.RfmInstances.Count > 0;
        var requiresErrorControl = context.CapacitorElements.Count > 0 ||
            context.InductorElements.Count > 0 ||
            context.DiodeElements.Any(element =>
            {
                var model = deck.DiodeModels[element.ModelName!];
                return model.ZeroBiasJunctionCapacitance > 0.0 || model.TransitTime > 0.0;
            }) ||
            context.BjtElements.Any(element => deck.BjtModels[element.ModelName!].HasDynamicCharge) ||
            context.MosElements.Any(element => deck.MosModels[element.ModelName!].HasDynamicCharge) ||
            deck.RfmInstances.Count > 0;
        var useStepDoubling =
            Environment.GetEnvironmentVariable("AGENT_SPICE_NATIVE_USE_STEP_DOUBLING_LTE") == "1";
        var maximumAdaptiveStep = useStepDoubling
            ? analysis.A
            : DeviceLteMaximumStep(deck, analysis.A, context.DefaultSourceTransition);
        var linearStateTruncationScale = deck.Elements.Any(
            element => element.Transient is PulseSource pulse &&
                (pulse.Rise == 0.0 || pulse.Fall == 0.0))
            ? 0.03
            : 0.3;
        var restartStep = DeviceLteRestartStep(
            deck,
            maximumAdaptiveStep,
            minimumStep,
            context.DefaultSourceTransition);
        var suggestedStep = requiresErrorControl && !useStepDoubling
            ? restartStep
            : analysis.A;
        var outputCount = (int)Math.Floor(analysis.B / analysis.A + 1e-9);
        for (var outputIndex = 1; outputIndex <= outputCount; outputIndex++)
        {
            var outputTime = outputIndex * analysis.A;
            var emit = outputTime + analysis.A * 1e-9 >= analysis.C;
            SimulationPoint point = default;
            while (currentTime < outputTime - Math.Max(1e-18, outputTime * 1e-14))
            {
                var timeTolerance = Math.Max(1e-18, Math.Max(currentTime, outputTime) * 1e-14);
                var remaining = outputTime - currentTime;
                var candidateStep = requiresErrorControl
                    ? QuantizeTransientStep(suggestedStep, maximumAdaptiveStep)
                    : suggestedStep;
                if (requiresErrorControl && !useStepDoubling)
                    candidateStep = Math.Min(
                        candidateStep,
                        SourceTransitionStepLimit(
                            deck,
                            Math.BitIncrement(currentTime),
                            context.DefaultSourceTransition));
                var step = Math.Min(candidateStep, remaining);
                var outputLimited = remaining < candidateStep - timeTolerance;
                if (!requiresErrorControl && Math.Abs(remaining - analysis.A) <= timeTolerance)
                    step = analysis.A;
                var breakpoint = (requiresErrorControl || deck.RfmInstances.Count > 0)
                    ? NextSourceBreakpoint(deck, currentTime, timeTolerance, context.DefaultSourceTransition)
                    : double.PositiveInfinity;
                var naturalEndpoint = currentTime + step;
                var breakpointHit = breakpoint <= naturalEndpoint + timeTolerance;
                var breakpointLimited = breakpoint < naturalEndpoint - timeTolerance;
                var endpoint = naturalEndpoint;
                if (breakpointHit)
                {
                    endpoint = Math.Min(breakpoint, outputTime);
                    step = endpoint - currentTime;
                }
                var breakpointAtEndpoint = breakpointHit && Math.Abs(endpoint - breakpoint) <= timeTolerance;
                var discontinuity = breakpointAtEndpoint &&
                    SourceHasDiscontinuityAt(deck, endpoint, context.DefaultSourceTransition);
                double? sourceEvaluationTime = discontinuity ? Math.BitDecrement(endpoint) : null;
                var reachesOutput = endpoint >= outputTime - timeTolerance;
                if (reachesOutput)
                    endpoint = outputTime;

                if (!requiresErrorControl)
                {
                    context.SetStep(step);
                    point = SolvePoint(
                        deck,
                        "tran",
                        endpoint,
                        null,
                        null,
                        context,
                        reachesOutput && emit ? outputStorage : null,
                        outputOffset,
                        statistics: statistics,
                        sourceEvaluationTime: sourceEvaluationTime);
                    currentTime = endpoint;
                    statistics.AcceptedTransientSteps++;
                    context.SetBackwardEuler(
                        restartIntegrationAtSourceEdges &&
                        (breakpointAtEndpoint || SourceIsTransitioningAt(
                            deck,
                            Math.BitIncrement(endpoint),
                            context.DefaultSourceTransition)));
                    if (breakpointLimited)
                        statistics.BreakpointTransientSteps++;
                    suggestedStep = Math.Min(analysis.A, step * 2.0);
                    if (discontinuity)
                    {
                        statistics.DiscontinuityTransientEvents++;
                        suggestedStep = Math.Min(suggestedStep, Math.Max(minimumStep, analysis.A * 1e-3));
                    }
                    continue;
                }

                var snapshot = context.CaptureState();
                SimulationPoint acceptedPoint;
                double errorRatio;
                int errorOrder;
                try
                {
                    if (useStepDoubling)
                    {
                        context.SetStep(step);
                        var coarse = SolvePoint(
                            deck,
                            "tran",
                            endpoint,
                            null,
                            null,
                            context,
                            captureInternal: true,
                            statistics: statistics,
                            sourceEvaluationTime: sourceEvaluationTime);

                        context.RestoreState(snapshot);
                        var halfStep = step * 0.5;
                        context.SetStep(halfStep);
                        _ = SolvePoint(
                            deck,
                            "tran",
                            currentTime + halfStep,
                            null,
                            null,
                            context,
                            captureInternal: true,
                            statistics: statistics);
                        acceptedPoint = SolvePoint(
                            deck,
                            "tran",
                            endpoint,
                            null,
                            null,
                            context,
                            reachesOutput && emit ? outputStorage : null,
                            outputOffset,
                            captureInternal: true,
                            statistics: statistics,
                            sourceEvaluationTime: sourceEvaluationTime);
                        errorRatio = TransientErrorRatio(deck, context, coarse, acceptedPoint);
                        errorOrder = 3;
                        statistics.StepDoublingEvaluations++;
                    }
                    else
                    {
                        context.SetStep(step);
                        acceptedPoint = SolvePoint(
                            deck,
                            "tran",
                            endpoint,
                            null,
                            null,
                            context,
                            reachesOutput && emit ? outputStorage : null,
                            outputOffset,
                            captureInternal: true,
                            statistics: statistics,
                            sourceEvaluationTime: sourceEvaluationTime);
                        var estimate = DeviceTruncationErrorRatio(
                            deck,
                            context,
                            snapshot,
                            linearStateTruncationScale);
                        errorRatio = estimate.Ratio;
                        errorOrder = estimate.Order;
                        statistics.DeviceTruncationEvaluations++;
                    }
                }
                catch (NonlinearConvergenceException) when (step > minimumStep)
                {
                    context.RestoreState(snapshot);
                    statistics.RejectedTransientSteps++;
                    suggestedStep = Math.Max(minimumStep, step * 0.25);
                    continue;
                }

                if (errorRatio > 1.0)
                {
                    context.RestoreState(snapshot);
                    statistics.RejectedTransientSteps++;
                    if (step <= minimumStep)
                        throw new InvalidOperationException(
                            $"transient LTE tolerance could not be met at t={currentTime + step:G17} " +
                            $"(normalized error={errorRatio:G6}, minimum step={minimumStep:G6})");
                    suggestedStep = Math.Max(
                        minimumStep,
                        step * StepScale(errorRatio, accepted: false, errorOrder));
                    continue;
                }

                currentTime = endpoint;
                statistics.AcceptedTransientSteps++;
                context.SetBackwardEuler(
                    restartIntegrationAtSourceEdges &&
                    (breakpointAtEndpoint || SourceIsTransitioningAt(
                        deck,
                        Math.BitIncrement(endpoint),
                        context.DefaultSourceTransition)));
                if (breakpointLimited)
                    statistics.BreakpointTransientSteps++;
                var nextStep = step * StepScale(errorRatio, accepted: true, errorOrder);
                if (outputLimited && reachesOutput && !breakpointAtEndpoint)
                {
                    var errorLimitedStep = errorRatio <= 1e-12
                        ? candidateStep
                        : step * 0.9 / Math.Pow(errorRatio, 1.0 / Math.Max(1, errorOrder));
                    nextStep = Math.Max(nextStep, Math.Min(candidateStep, errorLimitedStep));
                }
                suggestedStep = Math.Min(maximumAdaptiveStep, nextStep);
                if (!useStepDoubling && breakpointAtEndpoint)
                {
                    context.RestartTruncationHistory();
                    suggestedStep = Math.Min(
                        suggestedStep,
                        restartStep);
                }
                if (discontinuity)
                {
                    statistics.DiscontinuityTransientEvents++;
                    suggestedStep = Math.Min(suggestedStep, restartStep);
                }
                if (reachesOutput)
                    point = acceptedPoint;
            }
            if (emit)
            {
                outputOffset += context.OutputProbes.Length;
                yield return point;
            }
        }
    }

    private static double NextSourceBreakpoint(
        Deck deck,
        double time,
        double tolerance,
        double defaultTransition)
    {
        var next = double.PositiveInfinity;
        foreach (var element in deck.Elements)
        {
            if (element.Transient is null)
                continue;
            next = Math.Min(next, element.Transient.NextBreakpointAfter(time, tolerance, defaultTransition));
        }
        return next;
    }

    private static bool SourceHasDiscontinuityAt(Deck deck, double time, double defaultTransition) =>
        deck.Elements.Any(element => element.Transient?.IsDiscontinuityAt(time, defaultTransition) == true);

    private static bool SourceIsTransitioningAt(Deck deck, double time, double defaultTransition) =>
        deck.Elements.Any(element => element.Transient?.IsTransitioningAt(time, defaultTransition) == true);

    private static double DeviceLteRestartStep(
        Deck deck,
        double maximumStep,
        double minimumStep,
        double defaultTransition)
    {
        var characteristicTime = MinimumSourceCharacteristicTime(deck, defaultTransition);
        var startup = double.IsFinite(characteristicTime)
            ? Math.Min(maximumStep, characteristicTime * 1e-3)
            : maximumStep;
        return Math.Max(minimumStep, startup);
    }

    private static double DeviceLteMaximumStep(
        Deck deck,
        double requestedMaximumStep,
        double defaultTransition)
    {
        var characteristicTime = MinimumSourceCharacteristicTime(deck, defaultTransition);
        return double.IsFinite(characteristicTime) && requestedMaximumStep > 4.0 * characteristicTime
            ? Math.Min(requestedMaximumStep, 0.5 * characteristicTime)
            : requestedMaximumStep;
    }

    private static double MinimumSourceCharacteristicTime(Deck deck, double defaultTransition)
    {
        var characteristicTime = double.PositiveInfinity;
        foreach (var element in deck.Elements)
            if (element.Transient is not null)
                characteristicTime = Math.Min(
                    characteristicTime,
                    element.Transient.CharacteristicTime(defaultTransition));
        return characteristicTime;
    }

    private static double SourceTransitionStepLimit(
        Deck deck,
        double time,
        double defaultTransition)
    {
        var limit = double.PositiveInfinity;
        foreach (var element in deck.Elements)
            if (element.Transient is not null)
                limit = Math.Min(
                    limit,
                    element.Transient.TransitionStepLimit(time, defaultTransition));
        return limit;
    }

    private readonly record struct TransientErrorEstimate(double Ratio, int Order);

    private static TransientErrorEstimate DeviceTruncationErrorRatio(
        Deck deck,
        TransientContext context,
        TransientSnapshot snapshot,
        double linearStateTruncationScale)
    {
        const double JunctionChargeTruncationScale = 14.0;
        const double MosChargeTruncationScale = 1.0;
        if (snapshot.AcceptedHistoryDepth == 0)
            return new TransientErrorEstimate(0.0, 1);

        var secondOrder = !snapshot.UseBackwardEuler &&
            snapshot.AcceptedHistoryDepth >= 2 &&
            snapshot.PreviousAcceptedStep > 0.0 &&
            snapshot.OlderAcceptedStep > 0.0;
        var order = secondOrder ? 2 : 1;
        var h0 = context.Step;
        var h1 = snapshot.PreviousAcceptedStep > 0.0
            ? snapshot.PreviousAcceptedStep
            : h0;
        var h2 = snapshot.OlderAcceptedStep > 0.0
            ? snapshot.OlderAcceptedStep
            : h1;
        var secondOrderFactor = context.IntegrationMethod == IntegrationMethod.Gear
            ? 0.2222222222
            : 0.08333333333;
        var maximum = 0.0;

        void Accumulate(
            double q0,
            double q1,
            double q2,
            double q3,
            double derivative0,
            double derivative1,
            double derivativeAbsoluteTolerance,
            double truncationScale)
        {
            AccumulateWithTolerances(
                q0,
                q1,
                q2,
                q3,
                derivative0,
                derivative1,
                derivativeAbsoluteTolerance,
                deck.ChargeTolerance,
                truncationScale);
        }

        void AccumulateWithTolerances(
            double q0,
            double q1,
            double q2,
            double q3,
            double derivative0,
            double derivative1,
            double derivativeAbsoluteTolerance,
            double stateAbsoluteTolerance,
            double truncationScale)
        {
            var ratio = ChargeTruncationRatio(
                q0,
                q1,
                q2,
                q3,
                derivative0,
                derivative1,
                h0,
                h1,
                h2,
                order,
                secondOrderFactor,
                derivativeAbsoluteTolerance,
                deck.RelativeTolerance,
                stateAbsoluteTolerance,
                deck.TruncationTolerance * truncationScale);
            maximum = Math.Max(maximum, ratio);
        }

        foreach (var capacitor in context.CapacitorElements)
        {
            var state = capacitor.TransientStateIndex;
            Accumulate(
                capacitor.Value * context.Capacitors[state],
                capacitor.Value * snapshot.Capacitors[state],
                capacitor.Value * snapshot.CapacitorPreviousVoltages[state],
                capacitor.Value * snapshot.CapacitorOlderVoltages[state],
                context.CapacitorCurrents[state],
                snapshot.CapacitorCurrents[state],
                deck.CurrentTolerance,
                linearStateTruncationScale);
        }
        foreach (var inductor in context.InductorElements)
        {
            var state = inductor.TransientStateIndex;
            Accumulate(
                inductor.Value * context.Inductors[state],
                inductor.Value * snapshot.Inductors[state],
                inductor.Value * snapshot.InductorPreviousCurrents[state],
                inductor.Value * snapshot.InductorOlderCurrents[state],
                context.InductorVoltages[state],
                snapshot.InductorVoltages[state],
                deck.VoltageTolerance,
                linearStateTruncationScale);
        }
        foreach (var diode in context.DiodeElements)
        {
            var state = diode.TransientStateIndex;
            Accumulate(
                context.DiodeCharges[state],
                snapshot.DiodeCharges[state],
                snapshot.DiodePreviousCharges[state],
                snapshot.DiodeOlderCharges[state],
                context.DiodeDisplacementCurrents[state],
                snapshot.DiodeDisplacementCurrents[state],
                deck.CurrentTolerance,
                JunctionChargeTruncationScale);
        }
        foreach (var bjt in context.BjtElements)
        {
            var state = bjt.TransientStateIndex;
            var q0 = context.BjtCharges[state];
            var q1 = snapshot.BjtCharges[state];
            var q2 = snapshot.BjtPreviousCharges[state];
            var q3 = snapshot.BjtOlderCharges[state];
            var derivative0 = context.BjtDisplacementCurrents[state];
            var derivative1 = snapshot.BjtDisplacementCurrents[state];
            Accumulate(
                q0.Collector,
                q1.Collector,
                q2.Collector,
                q3.Collector,
                derivative0.Collector,
                derivative1.Collector,
                deck.CurrentTolerance,
                JunctionChargeTruncationScale);
            Accumulate(
                q0.Base,
                q1.Base,
                q2.Base,
                q3.Base,
                derivative0.Base,
                derivative1.Base,
                deck.CurrentTolerance,
                JunctionChargeTruncationScale);
            Accumulate(
                q0.Emitter,
                q1.Emitter,
                q2.Emitter,
                q3.Emitter,
                derivative0.Emitter,
                derivative1.Emitter,
                deck.CurrentTolerance,
                JunctionChargeTruncationScale);
        }
        foreach (var mos in context.MosElements)
        {
            var state = mos.TransientStateIndex;
            var q0 = context.MosCharges[state];
            var q1 = snapshot.MosCharges[state];
            var q2 = snapshot.MosPreviousCharges[state];
            var q3 = snapshot.MosOlderCharges[state];
            var derivative0 = context.MosDisplacementCurrents[state];
            var derivative1 = snapshot.MosDisplacementCurrents[state];
            Accumulate(
                q0.Drain,
                q1.Drain,
                q2.Drain,
                q3.Drain,
                derivative0.Drain,
                derivative1.Drain,
                deck.CurrentTolerance,
                MosChargeTruncationScale);
            Accumulate(
                q0.Gate,
                q1.Gate,
                q2.Gate,
                q3.Gate,
                derivative0.Gate,
                derivative1.Gate,
                deck.CurrentTolerance,
                MosChargeTruncationScale);
            Accumulate(
                q0.Source,
                q1.Source,
                q2.Source,
                q3.Source,
                derivative0.Source,
                derivative1.Source,
                deck.CurrentTolerance,
                MosChargeTruncationScale);
            Accumulate(
                q0.Bulk,
                q1.Bulk,
                q2.Bulk,
                q3.Bulk,
                derivative0.Bulk,
                derivative1.Bulk,
                deck.CurrentTolerance,
                MosChargeTruncationScale);
        }
        for (var instanceIndex = 0; instanceIndex < context.RfmInstances.Count; instanceIndex++)
        {
            var instance = context.RfmInstances[instanceIndex];
            var model = instance.Model;
            var state = context.RfmStates[instance.Name];
            var previous = snapshot.RfmStates[instanceIndex];
            var nports = model.Nports;
            var scratch = state.TruncationScratch.AsSpan();
            var q0 = scratch[..nports];
            var q1 = scratch.Slice(nports, nports);
            var q2 = scratch.Slice(2 * nports, nports);
            var q3 = scratch.Slice(3 * nports, nports);
            var derivative0 = scratch.Slice(4 * nports, nports);
            var derivative1 = scratch.Slice(5 * nports, nports);
            var derivativeState = scratch[(6 * nports)..];
            model.FillDynamicOutputVoltage(state.Values, q0);
            model.FillDynamicOutputVoltage(previous.Values, q1);
            model.FillDynamicOutputVoltage(previous.PreviousValues, q2);
            model.FillDynamicOutputVoltage(previous.OlderValues, q3);
            model.FillDynamicOutputVoltageDerivative(
                state.Values,
                state.Incident,
                derivative0,
                derivativeState);
            model.FillDynamicOutputVoltageDerivative(
                previous.Values,
                previous.Incident,
                derivative1,
                derivativeState);
            for (var port = 0; port < nports; port++)
                AccumulateWithTolerances(
                    q0[port],
                    q1[port],
                    q2[port],
                    q3[port],
                    derivative0[port],
                    derivative1[port],
                    deck.VoltageTolerance / h0,
                    deck.VoltageTolerance,
                    linearStateTruncationScale);
        }
        return new TransientErrorEstimate(maximum, order);
    }

    private static double ChargeTruncationRatio(
        double q0,
        double q1,
        double q2,
        double q3,
        double derivativeCurrent,
        double previousDerivativeCurrent,
        double h0,
        double h1,
        double h2,
        int order,
        double secondOrderFactor,
        double derivativeAbsoluteTolerance,
        double relativeTolerance,
        double chargeTolerance,
        double truncationTolerance)
    {
        var derivativeTolerance = derivativeAbsoluteTolerance + relativeTolerance *
            Math.Max(Math.Abs(derivativeCurrent), Math.Abs(previousDerivativeCurrent));
        var scaledChargeTolerance = relativeTolerance *
            Math.Max(Math.Max(Math.Abs(q0), Math.Abs(q1)), chargeTolerance) / h0;
        var tolerance = Math.Max(derivativeTolerance, scaledChargeTolerance);
        double scaledError;
        if (order == 1)
        {
            var derivative0 = (q0 - q1) / h0;
            var derivative1 = (q1 - q2) / h1;
            var secondDifference = (derivative0 - derivative1) / (h0 + h1);
            scaledError = 0.5 * Math.Abs(secondDifference) * h0;
        }
        else
        {
            var derivative0 = (q0 - q1) / h0;
            var derivative1 = (q1 - q2) / h1;
            var derivative2 = (q2 - q3) / h2;
            var secondDifference0 = (derivative0 - derivative1) / (h0 + h1);
            var secondDifference1 = (derivative1 - derivative2) / (h1 + h2);
            var thirdDifference =
                (secondDifference0 - secondDifference1) / (h0 + h1 + h2);
            scaledError = secondOrderFactor * Math.Abs(thirdDifference) * h0 * h0;
        }
        var ratio = scaledError / (truncationTolerance * tolerance);
        return double.IsFinite(ratio) ? ratio : double.PositiveInfinity;
    }

    private static double StepScale(double errorRatio, bool accepted, int errorOrder)
    {
        var unconstrained = errorRatio <= 1e-12
            ? 2.0
            : 0.9 / Math.Pow(errorRatio, 1.0 / Math.Max(1, errorOrder));
        return accepted
            ? Math.Clamp(unconstrained, 0.5, 2.0)
            : Math.Clamp(unconstrained, 0.1, 0.5);
    }

    private static double QuantizeTransientStep(double step, double maximumStep)
    {
        if (step >= maximumStep)
            return maximumStep;
        const int levelsPerOctave = 4;
        var level = Math.Max(
            0,
            (int)Math.Ceiling(levelsPerOctave * Math.Log2(maximumStep / step) - 1e-12));
        return maximumStep * Math.Pow(2.0, -(double)level / levelsPerOctave);
    }

    private static double TransientErrorRatio(
        Deck deck,
        TransientContext context,
        SimulationPoint coarse,
        SimulationPoint fine)
    {
        var coarseSolution = coarse.InternalSolution!;
        var fineSolution = fine.InternalSolution!;
        var maximum = 0.0;
        for (var index = 0; index < coarseSolution.Length; index++)
        {
            if (index >= deck.Nodes.Count && context.BranchElements[index - deck.Nodes.Count].Kind != 'L')
                continue;
            var absoluteTolerance = index < deck.Nodes.Count
                ? deck.VoltageTolerance
                : deck.CurrentTolerance;
            var tolerance = absoluteTolerance + deck.RelativeTolerance *
                Math.Max(Math.Abs(coarseSolution[index]), Math.Abs(fineSolution[index]));
            var ratio = Math.Abs(fineSolution[index] - coarseSolution[index]) / (3.0 * tolerance);
            maximum = Math.Max(maximum, ratio);
        }
        return maximum;
    }

    private static void InitializeStoredState(Deck deck, TransientContext context, SimulationPoint point)
    {
        var solution = point.InternalSolution!;
        foreach (var capacitor in context.CapacitorElements)
        {
            var state = capacitor.TransientStateIndex;
            var voltage = NodeValue(solution, capacitor.NodeIndices[0]) -
                NodeValue(solution, capacitor.NodeIndices[1]);
            context.Capacitors[state] = voltage;
            context.CapacitorPreviousVoltages[state] = voltage;
            context.CapacitorOlderVoltages[state] = voltage;
            context.CapacitorCurrents[state] = 0.0;
        }
        foreach (var inductor in context.InductorElements)
        {
            var state = inductor.TransientStateIndex;
            var current = solution[context.BranchIndex[inductor.Name]];
            context.Inductors[state] = current;
            context.InductorPreviousCurrents[state] = current;
            context.InductorOlderCurrents[state] = current;
            context.InductorVoltages[state] =
                NodeValue(solution, inductor.NodeIndices[0]) -
                NodeValue(solution, inductor.NodeIndices[1]);
        }
        foreach (var diode in context.DiodeElements)
        {
            var state = diode.TransientStateIndex;
            var voltage = NodeValue(solution, diode.NodeIndices[0]) -
                NodeValue(solution, diode.NodeIndices[1]);
            var charge = EvaluateDiode(
                deck.DiodeModels[diode.ModelName!],
                diode.Diode!,
                voltage).Charge;
            context.DiodeCharges[state] = charge;
            context.DiodePreviousCharges[state] = charge;
            context.DiodeOlderCharges[state] = charge;
            context.DiodeDisplacementCurrents[state] = 0.0;
        }
        foreach (var bjt in context.BjtElements)
        {
            var state = bjt.TransientStateIndex;
            var evaluation = EvaluateBjt(
                deck.BjtModels[bjt.ModelName!],
                bjt.Bjt!,
                NodeValue(solution, bjt.NodeIndices[0]),
                NodeValue(solution, bjt.NodeIndices[1]),
                NodeValue(solution, bjt.NodeIndices[2]));
            context.BjtCharges[state] = evaluation.Charge;
            context.BjtPreviousCharges[state] = evaluation.Charge;
            context.BjtOlderCharges[state] = evaluation.Charge;
            context.BjtDisplacementCurrents[state] = BjtTerminalVector.Zero;
        }
        foreach (var mos in context.MosElements)
        {
            var state = mos.TransientStateIndex;
            var model = deck.MosModels[mos.ModelName!];
            var instance = mos.Mos!;
            var drainVoltage = NodeValue(solution, mos.NodeIndices[0]);
            var gateVoltage = NodeValue(solution, mos.NodeIndices[1]);
            var sourceVoltage = NodeValue(solution, mos.NodeIndices[2]);
            var bulkVoltage = NodeValue(solution, mos.NodeIndices[3]);
            var evaluation = EvaluateMos(
                model,
                instance,
                drainVoltage,
                gateVoltage,
                sourceVoltage,
                bulkVoltage);
            var gateVoltageLinks = MosGateVoltages(
                drainVoltage,
                gateVoltage,
                sourceVoltage,
                bulkVoltage);
            var gateCapacitance = MosOverlapCapacitances(model, instance) +
                2.0 * evaluation.MeyerHalfCapacitance;
            var gateCharge = gateCapacitance.Multiply(gateVoltageLinks);
            var charge = evaluation.JunctionCharge + MosGateTerminalCharge(gateCharge);
            context.MosCharges[state] = charge;
            context.MosPreviousCharges[state] = charge;
            context.MosOlderCharges[state] = charge;
            context.MosDisplacementCurrents[state] = MosTerminalVector.Zero;
            context.MosGateCharges[state] = gateCharge;
            context.MosGateVoltages[state] = gateVoltageLinks;
            context.MosMeyerHalfCapacitances[state] = evaluation.MeyerHalfCapacitance;
        }
        context.PreviousAcceptedStep = 0.0;
        context.OlderAcceptedStep = 0.0;
        context.AcceptedHistoryDepth = 0;
    }

    private static void UpdateStoredState(Deck deck, TransientContext context, SimulationPoint point)
    {
        var solution = point.InternalSolution!;
        var bdf = context.UsesBdfIntegration
            ? context.BdfCoefficients()
            : default;
        foreach (var capacitor in context.CapacitorElements)
        {
            var state = capacitor.TransientStateIndex;
            var voltage = NodeValue(solution, capacitor.NodeIndices[0]) -
                NodeValue(solution, capacitor.NodeIndices[1]);
            var current = context.UsesBdfIntegration
                ? capacitor.Value * (
                    bdf.A0 * voltage +
                    bdf.A1 * context.Capacitors[state] +
                    bdf.A2 * context.CapacitorPreviousVoltages[state])
                : 2.0 * capacitor.Value / context.Step *
                    (voltage - context.Capacitors[state]) -
                    context.CapacitorCurrents[state];
            context.CapacitorOlderVoltages[state] = context.CapacitorPreviousVoltages[state];
            context.CapacitorPreviousVoltages[state] = context.Capacitors[state];
            context.Capacitors[state] = voltage;
            context.CapacitorCurrents[state] = current;
        }
        foreach (var inductor in context.InductorElements)
        {
            var state = inductor.TransientStateIndex;
            context.InductorOlderCurrents[state] = context.InductorPreviousCurrents[state];
            context.InductorPreviousCurrents[state] = context.Inductors[state];
            context.Inductors[state] = solution[context.BranchIndex[inductor.Name]];
            context.InductorVoltages[state] =
                NodeValue(solution, inductor.NodeIndices[0]) -
                NodeValue(solution, inductor.NodeIndices[1]);
        }
        foreach (var diode in context.DiodeElements)
        {
            var state = diode.TransientStateIndex;
            var voltage = NodeValue(solution, diode.NodeIndices[0]) -
                NodeValue(solution, diode.NodeIndices[1]);
            var charge = EvaluateDiode(
                deck.DiodeModels[diode.ModelName!],
                diode.Diode!,
                voltage).Charge;
            var current = context.UsesBdfIntegration
                ? bdf.A0 * charge +
                    bdf.A1 * context.DiodeCharges[state] +
                    bdf.A2 * context.DiodePreviousCharges[state]
                : 2.0 * (charge - context.DiodeCharges[state]) / context.Step -
                    context.DiodeDisplacementCurrents[state];
            context.DiodeOlderCharges[state] = context.DiodePreviousCharges[state];
            context.DiodePreviousCharges[state] = context.DiodeCharges[state];
            context.DiodeCharges[state] = charge;
            context.DiodeDisplacementCurrents[state] = current;
        }
        foreach (var bjt in context.BjtElements)
        {
            var state = bjt.TransientStateIndex;
            var evaluation = EvaluateBjt(
                deck.BjtModels[bjt.ModelName!],
                bjt.Bjt!,
                NodeValue(solution, bjt.NodeIndices[0]),
                NodeValue(solution, bjt.NodeIndices[1]),
                NodeValue(solution, bjt.NodeIndices[2]));
            var charge = evaluation.Charge;
            var current = context.UsesBdfIntegration
                ? bdf.A0 * charge +
                    bdf.A1 * context.BjtCharges[state] +
                    bdf.A2 * context.BjtPreviousCharges[state]
                : (2.0 / context.Step) * (charge - context.BjtCharges[state]) -
                    context.BjtDisplacementCurrents[state];
            context.BjtOlderCharges[state] = context.BjtPreviousCharges[state];
            context.BjtPreviousCharges[state] = context.BjtCharges[state];
            context.BjtCharges[state] = charge;
            context.BjtDisplacementCurrents[state] = current;
        }
        foreach (var mos in context.MosElements)
        {
            var state = mos.TransientStateIndex;
            var model = deck.MosModels[mos.ModelName!];
            var instance = mos.Mos!;
            var drainVoltage = NodeValue(solution, mos.NodeIndices[0]);
            var gateVoltage = NodeValue(solution, mos.NodeIndices[1]);
            var sourceVoltage = NodeValue(solution, mos.NodeIndices[2]);
            var bulkVoltage = NodeValue(solution, mos.NodeIndices[3]);
            var evaluation = EvaluateMos(
                model,
                instance,
                drainVoltage,
                gateVoltage,
                sourceVoltage,
                bulkVoltage);
            var dynamicCharge = EvaluateMosDynamicCharge(
                model,
                instance,
                evaluation,
                drainVoltage,
                gateVoltage,
                sourceVoltage,
                bulkVoltage,
                context.MosGateCharges[state],
                context.MosGateVoltages[state],
                context.MosMeyerHalfCapacitances[state]);
            var charge = dynamicCharge.Charge;
            var current = context.UsesBdfIntegration
                ? bdf.A0 * charge +
                    bdf.A1 * context.MosCharges[state] +
                    bdf.A2 * context.MosPreviousCharges[state]
                : (2.0 / context.Step) * (charge - context.MosCharges[state]) -
                    context.MosDisplacementCurrents[state];
            context.MosOlderCharges[state] = context.MosPreviousCharges[state];
            context.MosPreviousCharges[state] = context.MosCharges[state];
            context.MosCharges[state] = charge;
            context.MosDisplacementCurrents[state] = current;
            context.MosGateCharges[state] = dynamicCharge.GateCharge;
            context.MosGateVoltages[state] = dynamicCharge.GateVoltage;
            context.MosMeyerHalfCapacitances[state] = evaluation.MeyerHalfCapacitance;
        }
        context.OlderAcceptedStep = context.PreviousAcceptedStep;
        context.PreviousAcceptedStep = context.Step;
        context.AcceptedHistoryDepth = Math.Min(3, context.AcceptedHistoryDepth + 1);
    }

    private static SimulationPoint SolvePoint(
        Deck deck,
        string kind,
        double x,
        string? sweepSource,
        double? frequency,
        TransientContext? transient,
        double[]? transientOutputStorage = null,
        int transientOutputOffset = 0,
        LinearContext? linear = null,
        bool captureInternal = false,
        double[]? nonlinearGuess = null,
        SimulationStatistics? statistics = null,
        double? sourceEvaluationTime = null,
        SparseFactorizationCache? factorizationCache = null)
    {
        if (deck.HasNonlinearDevices && nonlinearGuess is null)
            return SolveNonlinearPoint(
                deck,
                kind,
                x,
                sweepSource,
                frequency,
                transient,
                transientOutputStorage,
                transientOutputOffset,
                linear,
                captureInternal,
                statistics,
                sourceEvaluationTime,
                factorizationCache ?? transient?.SparseFactorizationCache ?? linear?.SparseFactorizationCache);
        var nodeIndex = transient?.NodeIndex ?? linear?.NodeIndex ?? deck.Nodes.Select((node, index) => (node, index)).ToDictionary(pair => pair.node, pair => pair.index, StringComparer.OrdinalIgnoreCase);
        var branchElements = transient?.BranchElements ?? linear?.BranchElements ?? deck.Elements.Where(element => element.Kind is 'V' or 'L' or 'E' or 'H').ToList();
        var size = deck.Nodes.Count + branchElements.Count;
        var activeFactorizationCache = factorizationCache ?? transient?.SparseFactorizationCache;
        var reusableFactorization = transient?.Factorization ??
            (activeFactorizationCache is null ? linear?.Factorization : null);
        var buildMatrix = nonlinearGuess is not null || reusableFactorization is null;
        var matrixAssemblyReplayed = false;
        SparseMatrix? matrix = null;
        if (buildMatrix)
        {
            if (activeFactorizationCache is null)
            {
                matrix = new SparseMatrix(size);
            }
            else
            {
                var affineParameter = kind == "ac" && deck.RfmInstances.Count == 0
                    ? frequency
                    : null;
                matrix = activeFactorizationCache.RentMatrix(
                    size,
                    affineParameter,
                    out matrixAssemblyReplayed);
                if (matrixAssemblyReplayed && statistics is not null)
                    statistics.AcMatrixAssemblyReplays++;
            }
        }
        var rightHandSide = activeFactorizationCache?.RentRightHandSide(size) ?? new Complex[size];
        int Index(string node) => node.Equals("0", StringComparison.OrdinalIgnoreCase) ? -1 : nodeIndex[node];
        void Stamp(int row, int column, Complex value)
        {
            if (matrix is null || matrixAssemblyReplayed || row < 0 || column < 0)
                return;
            if (activeFactorizationCache is not null)
                activeFactorizationCache.AddMatrixValue(matrix, row, column, value);
            else
                matrix.Add(row, column, value);
        }
        void StampBranch(int[] nodes, int branch, Complex diagonal, Complex source)
        {
            var positive = nodes[0];
            var negative = nodes[1];
            Stamp(positive, branch, 1.0);
            Stamp(negative, branch, -1.0);
            Stamp(branch, positive, 1.0);
            Stamp(branch, negative, -1.0);
            Stamp(branch, branch, diagonal);
            rightHandSide[branch] += source;
        }
        void StampAdmittance(int[] nodes, Complex admittance)
        {
            var positive = nodes[0];
            var negative = nodes[1];
            Stamp(positive, positive, admittance);
            Stamp(negative, negative, admittance);
            Stamp(positive, negative, -admittance);
            Stamp(negative, positive, -admittance);
        }
        void StampCurrent(int[] nodes, Complex current)
        {
            var positive = nodes[0];
            var negative = nodes[1];
            if (positive >= 0) rightHandSide[positive] -= current;
            if (negative >= 0) rightHandSide[negative] += current;
        }
        void StampTerminalCurrent(int node, Complex current)
        {
            if (node >= 0)
                rightHandSide[node] -= current;
        }
        void StampTerminalMatrix(
            int collector,
            int @base,
            int emitter,
            BjtTerminalMatrix values,
            Complex scale)
        {
            Stamp(collector, collector, scale * values.Cc);
            Stamp(collector, @base, scale * values.Cb);
            Stamp(collector, emitter, scale * values.Ce);
            Stamp(@base, collector, scale * values.Bc);
            Stamp(@base, @base, scale * values.Bb);
            Stamp(@base, emitter, scale * values.Be);
            Stamp(emitter, collector, scale * values.Ec);
            Stamp(emitter, @base, scale * values.Eb);
            Stamp(emitter, emitter, scale * values.Ee);
        }
        void StampMosTerminalMatrix(
            int drain,
            int gate,
            int source,
            int bulk,
            MosTerminalMatrix values,
            Complex scale)
        {
            Stamp(drain, drain, scale * values.Dd);
            Stamp(drain, gate, scale * values.Dg);
            Stamp(drain, source, scale * values.Ds);
            Stamp(drain, bulk, scale * values.Db);
            Stamp(gate, drain, scale * values.Gd);
            Stamp(gate, gate, scale * values.Gg);
            Stamp(gate, source, scale * values.Gs);
            Stamp(gate, bulk, scale * values.Gb);
            Stamp(source, drain, scale * values.Sd);
            Stamp(source, gate, scale * values.Sg);
            Stamp(source, source, scale * values.Ss);
            Stamp(source, bulk, scale * values.Sb);
            Stamp(bulk, drain, scale * values.Bd);
            Stamp(bulk, gate, scale * values.Bg);
            Stamp(bulk, source, scale * values.Bs);
            Stamp(bulk, bulk, scale * values.Bb);
        }
        void StampNport(RfmInstance instance, Complex[,]? admittance, IReadOnlyList<double>? offset = null)
        {
            var reference = Index(instance.Reference);
            for (var row = 0; row < instance.Model.Nports; row++)
            {
                var positiveRow = Index(instance.Ports[row]);
                if (admittance is not null)
                {
                    for (var column = 0; column < instance.Model.Nports; column++)
                    {
                        var positiveColumn = Index(instance.Ports[column]);
                        var value = admittance[row, column];
                        Stamp(positiveRow, positiveColumn, value);
                        Stamp(positiveRow, reference, -value);
                        Stamp(reference, positiveColumn, -value);
                        Stamp(reference, reference, value);
                    }
                }
                if (offset is null)
                    continue;
                if (positiveRow >= 0) rightHandSide[positiveRow] -= offset[row];
                if (reference >= 0) rightHandSide[reference] += offset[row];
            }
        }

        var branchIndex = transient?.BranchIndex ?? linear?.BranchIndex ?? branchElements
            .Select((element, offset) => (element.Name, Index: deck.Nodes.Count + offset))
            .ToDictionary(pair => pair.Name, pair => pair.Index, StringComparer.OrdinalIgnoreCase);
        var bdf = transient?.UsesBdfIntegration == true
            ? transient.BdfCoefficients()
            : default;
        var elements = (!buildMatrix || matrixAssemblyReplayed) && linear is not null
            ? linear.SourceElements
            : deck.Elements;
        foreach (var element in elements)
        {
            var value = element.Name.Equals(sweepSource, StringComparison.OrdinalIgnoreCase)
                ? x
                : kind == "tran"
                    ? element.ValueAt(sourceEvaluationTime ?? x, transient?.DefaultSourceTransition ?? 0.0)
                    : element.Value;
            switch (element.Kind)
            {
                case 'R':
                    if (value == 0.0) throw new InvalidDataException($"{element.Name} resistance must be non-zero");
                    StampAdmittance(element.NodeIndices, 1.0 / value);
                    break;
                case 'G':
                    {
                        var outputPositive = element.NodeIndices[0];
                        var outputNegative = element.NodeIndices[1];
                        var controlPositive = element.NodeIndices[2];
                        var controlNegative = element.NodeIndices[3];
                        Stamp(outputPositive, controlPositive, value);
                        Stamp(outputNegative, controlNegative, value);
                        Stamp(outputPositive, controlNegative, -value);
                        Stamp(outputNegative, controlPositive, -value);
                        break;
                    }
                case 'E':
                    {
                        var branch = branchIndex[element.Name];
                        StampBranch(element.NodeIndices, branch, Complex.Zero, Complex.Zero);
                        Stamp(branch, element.NodeIndices[2], -value);
                        Stamp(branch, element.NodeIndices[3], value);
                        break;
                    }
                case 'F':
                    {
                        var control = branchIndex[element.ControlName!];
                        Stamp(element.NodeIndices[0], control, value);
                        Stamp(element.NodeIndices[1], control, -value);
                        break;
                    }
                case 'H':
                    {
                        var branch = branchIndex[element.Name];
                        StampBranch(element.NodeIndices, branch, Complex.Zero, Complex.Zero);
                        Stamp(branch, branchIndex[element.ControlName!], -value);
                        break;
                    }
                case 'I':
                    StampCurrent(element.NodeIndices, kind == "ac" ? AcValue(element) : value);
                    break;
                case 'V':
                    StampBranch(element.NodeIndices, branchIndex[element.Name], Complex.Zero, kind == "ac" ? AcValue(element) : value);
                    break;
                case 'C':
                    if (kind == "ac")
                        StampAdmittance(element.NodeIndices, Complex.ImaginaryOne * frequency!.Value * 2.0 * Math.PI * value);
                    else if (transient is not null)
                    {
                        var state = element.TransientStateIndex;
                        var conductance = transient.UsesBdfIntegration
                            ? value * bdf.A0
                            : 2.0 * value / transient.Step;
                        var historyCurrent = transient.UsesBdfIntegration
                            ? value * (
                                bdf.A1 * transient.Capacitors[state] +
                                bdf.A2 * transient.CapacitorPreviousVoltages[state])
                            : -conductance * transient.Capacitors[state] -
                                transient.CapacitorCurrents[state];
                        StampAdmittance(element.NodeIndices, conductance);
                        StampCurrent(element.NodeIndices, historyCurrent);
                    }
                    break;
                case 'D':
                    {
                        var model = deck.DiodeModels[element.ModelName!];
                        var instance = element.Diode!;
                        var positive = element.NodeIndices[0];
                        var negative = element.NodeIndices[1];
                        var voltage = (positive >= 0 ? nonlinearGuess![positive] : 0.0) -
                            (negative >= 0 ? nonlinearGuess![negative] : 0.0);
                        var evaluation = EvaluateDiode(model, instance, voltage);
                        var conductance = evaluation.Conductance;
                        if (kind == "ac")
                        {
                            StampAdmittance(
                                element.NodeIndices,
                                conductance + Complex.ImaginaryOne * frequency!.Value * 2.0 * Math.PI *
                                    evaluation.Capacitance);
                        }
                        else
                        {
                            var equivalentCurrent = evaluation.Current - conductance * voltage;
                            if (transient is not null)
                            {
                                var state = element.TransientStateIndex;
                                var companionConductance = transient.UsesBdfIntegration
                                    ? bdf.A0 * evaluation.Capacitance
                                    : 2.0 * evaluation.Capacitance / transient.Step;
                                conductance += companionConductance;
                                equivalentCurrent += transient.UsesBdfIntegration
                                    ? bdf.A0 * (evaluation.Charge - evaluation.Capacitance * voltage) +
                                        bdf.A1 * transient.DiodeCharges[state] +
                                        bdf.A2 * transient.DiodePreviousCharges[state]
                                    : 2.0 * (evaluation.Charge - transient.DiodeCharges[state]) / transient.Step -
                                        transient.DiodeDisplacementCurrents[state] - companionConductance * voltage;
                            }
                            StampAdmittance(element.NodeIndices, conductance);
                            StampCurrent(element.NodeIndices, equivalentCurrent);
                        }
                        break;
                    }
                case 'Q':
                    {
                        var model = deck.BjtModels[element.ModelName!];
                        var collector = element.NodeIndices[0];
                        var @base = element.NodeIndices[1];
                        var emitter = element.NodeIndices[2];
                        var collectorVoltage = collector >= 0 ? nonlinearGuess![collector] : 0.0;
                        var baseVoltage = @base >= 0 ? nonlinearGuess![@base] : 0.0;
                        var emitterVoltage = emitter >= 0 ? nonlinearGuess![emitter] : 0.0;
                        var evaluation = EvaluateBjt(
                            model,
                            element.Bjt!,
                            collectorVoltage,
                            baseVoltage,
                            emitterVoltage);

                        Stamp(collector, collector, evaluation.Jcc);
                        Stamp(collector, @base, evaluation.Jcb);
                        Stamp(collector, emitter, evaluation.Jce);
                        Stamp(@base, collector, evaluation.Jbc);
                        Stamp(@base, @base, evaluation.Jbb);
                        Stamp(@base, emitter, evaluation.Jbe);
                        Stamp(emitter, collector, evaluation.Jec);
                        Stamp(emitter, @base, evaluation.Jeb);
                        Stamp(emitter, emitter, evaluation.Jee);
                        if (kind == "ac")
                        {
                            StampTerminalMatrix(
                                collector,
                                @base,
                                emitter,
                                evaluation.Capacitance,
                                Complex.ImaginaryOne * frequency!.Value * 2.0 * Math.PI);
                        }
                        if (kind != "ac")
                        {
                            StampTerminalCurrent(
                                collector,
                                evaluation.CollectorCurrent -
                                evaluation.Jcc * collectorVoltage -
                                evaluation.Jcb * baseVoltage -
                                evaluation.Jce * emitterVoltage);
                            StampTerminalCurrent(
                                @base,
                                evaluation.BaseCurrent -
                                evaluation.Jbc * collectorVoltage -
                                evaluation.Jbb * baseVoltage -
                                evaluation.Jbe * emitterVoltage);
                            StampTerminalCurrent(
                                emitter,
                                evaluation.EmitterCurrent -
                                evaluation.Jec * collectorVoltage -
                                evaluation.Jeb * baseVoltage -
                                evaluation.Jee * emitterVoltage);
                            if (transient is not null)
                            {
                                var state = element.TransientStateIndex;
                                var derivativeScale = transient.UsesBdfIntegration
                                    ? bdf.A0
                                    : 2.0 / transient.Step;
                                StampTerminalMatrix(
                                    collector,
                                    @base,
                                    emitter,
                                    evaluation.Capacitance,
                                    derivativeScale);
                                var linearizedCharge = evaluation.Charge -
                                    evaluation.Capacitance.Multiply(
                                        collectorVoltage,
                                        baseVoltage,
                                        emitterVoltage);
                                var history = transient.UsesBdfIntegration
                                    ? bdf.A1 * transient.BjtCharges[state] +
                                        bdf.A2 * transient.BjtPreviousCharges[state]
                                    : (-derivativeScale) * transient.BjtCharges[state] -
                                        transient.BjtDisplacementCurrents[state];
                                var equivalentCurrent = derivativeScale * linearizedCharge + history;
                                StampTerminalCurrent(collector, equivalentCurrent.Collector);
                                StampTerminalCurrent(@base, equivalentCurrent.Base);
                                StampTerminalCurrent(emitter, equivalentCurrent.Emitter);
                            }
                        }
                        break;
                    }
                case 'M':
                    {
                        var drain = element.NodeIndices[0];
                        var gate = element.NodeIndices[1];
                        var source = element.NodeIndices[2];
                        var bulk = element.NodeIndices[3];
                        var drainVoltage = drain >= 0 ? nonlinearGuess![drain] : 0.0;
                        var gateVoltage = gate >= 0 ? nonlinearGuess![gate] : 0.0;
                        var sourceVoltage = source >= 0 ? nonlinearGuess![source] : 0.0;
                        var bulkVoltage = bulk >= 0 ? nonlinearGuess![bulk] : 0.0;
                        var model = deck.MosModels[element.ModelName!];
                        var instance = element.Mos!;
                        var evaluation = EvaluateMos(
                            model,
                            instance,
                            drainVoltage,
                            gateVoltage,
                            sourceVoltage,
                            bulkVoltage);
                        StampMosTerminalMatrix(
                            drain,
                            gate,
                            source,
                            bulk,
                            evaluation.Conductance,
                            Complex.One);
                        if (kind == "ac")
                        {
                            StampMosTerminalMatrix(
                                drain,
                                gate,
                                source,
                                bulk,
                                MosAcCapacitance(model, instance, evaluation),
                                Complex.ImaginaryOne * frequency!.Value * 2.0 * Math.PI);
                            break;
                        }

                        var equivalentCurrent = evaluation.Current -
                            evaluation.Conductance.Multiply(
                                drainVoltage,
                                gateVoltage,
                                sourceVoltage,
                                bulkVoltage);
                        StampTerminalCurrent(drain, equivalentCurrent.Drain);
                        StampTerminalCurrent(gate, equivalentCurrent.Gate);
                        StampTerminalCurrent(source, equivalentCurrent.Source);
                        StampTerminalCurrent(bulk, equivalentCurrent.Bulk);
                        if (transient is not null)
                        {
                            var state = element.TransientStateIndex;
                            var dynamicCharge = EvaluateMosDynamicCharge(
                                model,
                                instance,
                                evaluation,
                                drainVoltage,
                                gateVoltage,
                                sourceVoltage,
                                bulkVoltage,
                                transient.MosGateCharges[state],
                                transient.MosGateVoltages[state],
                                transient.MosMeyerHalfCapacitances[state]);
                            var derivativeScale = transient.UsesBdfIntegration
                                ? bdf.A0
                                : 2.0 / transient.Step;
                            StampMosTerminalMatrix(
                                drain,
                                gate,
                                source,
                                bulk,
                                dynamicCharge.Capacitance,
                                derivativeScale);
                            var linearizedCharge = dynamicCharge.Charge -
                                dynamicCharge.Capacitance.Multiply(
                                    drainVoltage,
                                    gateVoltage,
                                    sourceVoltage,
                                    bulkVoltage);
                            var history = transient.UsesBdfIntegration
                                ? bdf.A1 * transient.MosCharges[state] +
                                    bdf.A2 * transient.MosPreviousCharges[state]
                                : (-derivativeScale) * transient.MosCharges[state] -
                                    transient.MosDisplacementCurrents[state];
                            var transientEquivalentCurrent = derivativeScale * linearizedCharge + history;
                            StampTerminalCurrent(drain, transientEquivalentCurrent.Drain);
                            StampTerminalCurrent(gate, transientEquivalentCurrent.Gate);
                            StampTerminalCurrent(source, transientEquivalentCurrent.Source);
                            StampTerminalCurrent(bulk, transientEquivalentCurrent.Bulk);
                        }
                        break;
                    }
                case 'L':
                    {
                        var branch = branchIndex[element.Name];
                        if (kind == "ac")
                            StampBranch(element.NodeIndices, branch, -Complex.ImaginaryOne * frequency!.Value * 2.0 * Math.PI * value, Complex.Zero);
                        else if (transient is not null)
                        {
                            var state = element.TransientStateIndex;
                            var impedance = transient.UsesBdfIntegration
                                ? value * bdf.A0
                                : 2.0 * value / transient.Step;
                            var historyVoltage = transient.UsesBdfIntegration
                                ? value * (
                                    bdf.A1 * transient.Inductors[state] +
                                    bdf.A2 * transient.InductorPreviousCurrents[state])
                                : -impedance * transient.Inductors[state] -
                                    transient.InductorVoltages[state];
                            StampBranch(
                                element.NodeIndices,
                                branch,
                                -impedance,
                                historyVoltage);
                        }
                        else
                            StampBranch(element.NodeIndices, branch, Complex.Zero, Complex.Zero);
                        break;
                    }
            }
        }

        foreach (var instance in deck.RfmInstances)
        {
            if (kind == "ac")
            {
                StampNport(instance, instance.Model.Admittance(Complex.ImaginaryOne * 2.0 * Math.PI * frequency!.Value));
                continue;
            }
            if (transient is null)
            {
                if (buildMatrix)
                    StampNport(instance, instance.Model.DcAdmittance());
                continue;
            }
            var companion = instance.Model.BuildCompanion(
                transient.RfmStates[instance.Name],
                transient.Step,
                transient.UsesBdfIntegration ? bdf : null);
            StampNport(instance, buildMatrix ? ToComplex(companion.Conductance, instance.Model.Nports) : null, companion.Offset);
        }

        SolutionVector solution;
        SolutionVector SolveFactorization(IComplexFactorization factorization) =>
            factorization is IRealFactorization real
                ? new SolutionVector(real.SolveReal(rightHandSide))
                : new SolutionVector(factorization.Solve(rightHandSide));
        if (nonlinearGuess is not null)
        {
            solution = new SolutionVector(LinearAlgebra.Solve(
                matrix!,
                rightHandSide,
                activeFactorizationCache,
                statistics));
        }
        else if (transient is not null)
        {
            transient.Factorization ??= LinearAlgebra.Factorize(
                matrix!,
                optimizeRepeatedSolve: true,
                cache: transient.SparseFactorizationCache,
                statistics: statistics);
            solution = SolveFactorization(transient.Factorization);
        }
        else if (activeFactorizationCache is not null)
        {
            solution = new SolutionVector(LinearAlgebra.Solve(
                matrix!,
                rightHandSide,
                activeFactorizationCache,
                statistics));
        }
        else if (linear is not null)
        {
            linear.Factorization ??= LinearAlgebra.Factorize(matrix!, linear.OptimizeRepeatedSolve);
            solution = SolveFactorization(linear.Factorization);
        }
        else
        {
            solution = new SolutionVector(LinearAlgebra.Solve(
                matrix!,
                rightHandSide,
                activeFactorizationCache,
                statistics));
        }
        double[]? internalSolution = captureInternal ? new double[size] : null;
        if (internalSolution is not null)
            for (var index = 0; index < size; index++)
                internalSolution[index] = solution.Real(index);
        string[] valueNames;
        double[] values;
        string[] complexNames;
        ComplexSample[] complexValues;
        if (transient is not null)
        {
            valueNames = transientOutputStorage is null ? [] : transient.OutputNames;
            values = transientOutputStorage ?? [];
            for (var index = 0; index < valueNames.Length; index++)
                values[transientOutputOffset + index] = solution.Real(transient.OutputProbes[index].Index);
            complexNames = [];
            complexValues = [];
        }
        else
        {
            if (linear is not null && internalSolution is null)
            {
                var probes = linear.OutputProbes[kind];
                valueNames = linear.OutputNames[kind];
                values = new double[probes.Length];
                complexNames = kind == "ac" ? valueNames : [];
                complexValues = kind == "ac" ? new ComplexSample[probes.Length] : [];
                for (var index = 0; index < probes.Length; index++)
                {
                    var value = solution.Complex(probes[index].Index);
                    values[index] = value.Real;
                    if (kind == "ac")
                        complexValues[index] = new ComplexSample(value.Real, value.Imaginary);
                }
                return new SimulationPoint(
                    kind,
                    x,
                    valueNames,
                    values,
                    0,
                    complexNames,
                    complexValues,
                    null);
            }
            var selectedNames = new List<string>();
            var selectedValues = new List<double>();
            var selectedComplex = new List<ComplexSample>();
            for (var index = 0; index < deck.Nodes.Count; index++)
            {
                var name = deck.Nodes[index];
                if (!RequestedOutput(deck, kind, name))
                    continue;
                selectedNames.Add(name);
                selectedValues.Add(solution.Real(index));
                if (kind == "ac")
                {
                    var complex = solution.Complex(index);
                    selectedComplex.Add(new ComplexSample(complex.Real, complex.Imaginary));
                }
            }
            foreach (var branch in branchElements)
            {
                var value = solution.Complex(branchIndex[branch.Name]);
                if (!RequestedOutput(deck, kind, branch.Name))
                    continue;
                selectedNames.Add(branch.Name);
                selectedValues.Add(value.Real);
                if (kind == "ac")
                    selectedComplex.Add(new ComplexSample(value.Real, value.Imaginary));
            }
            valueNames = selectedNames.ToArray();
            values = selectedValues.ToArray();
            complexNames = kind == "ac" ? valueNames : [];
            complexValues = selectedComplex.ToArray();
        }
        var point = new SimulationPoint(
            kind,
            x,
            valueNames,
            values,
            transientOutputOffset,
            complexNames,
            complexValues,
            internalSolution);
        if (transient is not null && nonlinearGuess is null)
        {
            foreach (var instance in deck.RfmInstances)
            {
                var state = transient.RfmStates[instance.Name];
                FillPortVoltages(solution, nodeIndex, instance, state.PortVoltages);
                state.Companion!.Commit(state, state.PortVoltages);
            }
            UpdateStoredState(deck, transient, point);
        }
        return point;
    }

    private static SimulationPoint SolveNonlinearPoint(
        Deck deck,
        string kind,
        double x,
        string? sweepSource,
        double? frequency,
        TransientContext? transient,
        double[]? transientOutputStorage,
        int transientOutputOffset,
        LinearContext? linear,
        bool captureInternal,
        SimulationStatistics? statistics,
        double? sourceEvaluationTime,
        SparseFactorizationCache? factorizationCache)
    {
        var nodeIndex = transient?.NodeIndex ?? linear?.NodeIndex ?? deck.Nodes
            .Select((node, index) => (node, index))
            .ToDictionary(pair => pair.node, pair => pair.index, StringComparer.OrdinalIgnoreCase);
        var branchElements = transient?.BranchElements ?? linear?.BranchElements ?? deck.Elements
            .Where(element => element.Kind is 'V' or 'L' or 'E' or 'H')
            .ToList();
        var branchIndex = transient?.BranchIndex ?? linear?.BranchIndex ?? branchElements
            .Select((element, offset) => (element.Name, Index: deck.Nodes.Count + offset))
            .ToDictionary(pair => pair.Name, pair => pair.Index, StringComparer.OrdinalIgnoreCase);
        var size = deck.Nodes.Count + branchElements.Count;
        double[] guess;
        if (transient is not null && deck.UseTransientPredictor)
        {
            guess = transient.PredictNonlinearGuess(out var usedPrediction);
            if (guess.Length == 0)
                guess = new double[size];
            if (usedPrediction && statistics is not null)
                statistics.PredictorInitializations++;
        }
        else
        {
            guess = (transient?.NonlinearGuess ?? linear?.NonlinearGuess ?? new double[size]).ToArray();
        }
        ApplyIndependentVoltageSourceBias(
            deck,
            kind,
            x,
            sweepSource,
            sourceEvaluationTime,
            transient?.DefaultSourceTransition ?? 0.0,
            nodeIndex,
            guess);
        SimulationPoint convergedPoint = default;
        var converged = false;
        var lastConvergenceRatio = double.PositiveInfinity;
        var lastResidualRatio = double.PositiveInfinity;
        var lastAlpha = 1.0;

        for (var iteration = 0; iteration < 100; iteration++)
        {
            if (statistics is not null)
                statistics.NewtonIterations++;
            var point = SolvePoint(
                deck,
                kind,
                x,
                sweepSource,
                frequency,
                transient,
                transientOutputStorage,
                transientOutputOffset,
                linear,
                captureInternal: true,
                nonlinearGuess: guess,
                statistics: statistics,
                sourceEvaluationTime: sourceEvaluationTime,
                factorizationCache: factorizationCache);
            var candidate = ExtractSolution(point);
            var alpha = JunctionLimitScale(deck, nodeIndex, guess, candidate);
            lastConvergenceRatio = ConvergenceRatio(deck, guess, candidate);
            var candidateResidual = NonlinearResidualRatio(
                deck,
                kind,
                x,
                sweepSource,
                transient,
                nodeIndex,
                branchIndex,
                candidate,
                sourceEvaluationTime);
            if (alpha == 1.0 && candidateResidual <= 1.0)
            {
                if (statistics is not null)
                    statistics.MaximumConvergedResidualRatio = Math.Max(
                        statistics.MaximumConvergedResidualRatio,
                        candidateResidual);
                guess = candidate;
                convergedPoint = point;
                converged = true;
                break;
            }

            // Let the first linearized solve establish independent-source bias before
            // applying the residual line search. Junction limiting still guards unsafe
            // exponential voltage steps.
            if (iteration == 0 && alpha == 1.0 && guess.All(value => value == 0.0))
            {
                guess = candidate;
                lastAlpha = 1.0;
                lastResidualRatio = candidateResidual;
                continue;
            }

            var currentResidual = NonlinearResidualRatio(
                deck,
                kind,
                x,
                sweepSource,
                transient,
                nodeIndex,
                branchIndex,
                guess,
                sourceEvaluationTime);
            if (alpha == 1.0 && currentResidual <= 1.0)
            {
                guess = candidate;
                lastAlpha = 1.0;
                lastResidualRatio = candidateResidual;
                continue;
            }
            var bestResidual = double.PositiveInfinity;
            var bestAlpha = alpha;
            var bestGuess = new double[size];
            var trial = new double[size];
            for (var backtrack = 0; backtrack < 12; backtrack++)
            {
                for (var index = 0; index < size; index++)
                    trial[index] = guess[index] + alpha * (candidate[index] - guess[index]);
                var trialResidual = NonlinearResidualRatio(
                    deck,
                    kind,
                    x,
                    sweepSource,
                    transient,
                    nodeIndex,
                    branchIndex,
                    trial,
                    sourceEvaluationTime);
                if (trialResidual < bestResidual)
                {
                    bestResidual = trialResidual;
                    bestAlpha = alpha;
                    trial.CopyTo(bestGuess, 0);
                }
                if (trialResidual <= currentResidual * (1.0 - 1e-4 * alpha) || alpha <= 1e-6)
                    break;
                alpha *= 0.5;
                if (statistics is not null)
                    statistics.LineSearchBacktracks++;
            }
            guess = bestGuess;
            lastAlpha = bestAlpha;
            lastResidualRatio = bestResidual;
        }
        if (!converged)
            throw new NonlinearConvergenceException(
                $"nonlinear Newton-Raphson did not converge for {kind} at {x:G17} after 100 iterations " +
                $"(normalized update={lastConvergenceRatio:G6}, residual={lastResidualRatio:G6}, " +
                $"damping={lastAlpha:G6})");

        if (transient is not null)
        {
            transient.AdvanceNonlinearGuess(guess);
            foreach (var instance in deck.RfmInstances)
            {
                var state = transient.RfmStates[instance.Name];
                FillPortVoltages(convergedPoint, transient.NodeIndex, instance, state.PortVoltages);
                state.Companion!.Commit(state, state.PortVoltages);
            }
            UpdateStoredState(deck, transient, convergedPoint);
        }
        if (linear is not null)
            linear.NonlinearGuess = guess;
        return new SimulationPoint(
            convergedPoint.Analysis,
            convergedPoint.X,
            convergedPoint.ValueNames,
            convergedPoint.Values,
            convergedPoint.ValueOffset,
            convergedPoint.ComplexNames,
            convergedPoint.Complex,
            captureInternal ? convergedPoint.InternalSolution : null);
    }

    private static double[] ExtractSolution(SimulationPoint point) => point.InternalSolution!;

    private static void ApplyIndependentVoltageSourceBias(
        Deck deck,
        string kind,
        double x,
        string? sweepSource,
        double? sourceEvaluationTime,
        double defaultSourceTransition,
        IReadOnlyDictionary<string, int> nodeIndex,
        double[] guess)
    {
        foreach (var source in deck.Elements.Where(element => element.Kind == 'V'))
        {
            var value = source.Name.Equals(sweepSource, StringComparison.OrdinalIgnoreCase)
                ? x
                : kind == "tran"
                    ? source.ValueAt(sourceEvaluationTime ?? x, defaultSourceTransition)
                    : source.Value;
            var positiveGround = source.Nodes[0].Equals("0", StringComparison.OrdinalIgnoreCase);
            var negativeGround = source.Nodes[1].Equals("0", StringComparison.OrdinalIgnoreCase);
            if (positiveGround && negativeGround)
                continue;
            if (negativeGround)
            {
                guess[nodeIndex[source.Nodes[0]]] = value;
                continue;
            }
            if (positiveGround)
            {
                guess[nodeIndex[source.Nodes[1]]] = -value;
                continue;
            }
            var positive = nodeIndex[source.Nodes[0]];
            var negative = nodeIndex[source.Nodes[1]];
            var correction = value - (guess[positive] - guess[negative]);
            guess[positive] += correction * 0.5;
            guess[negative] -= correction * 0.5;
        }
    }

    private static MosEvaluation EvaluateMos(
        MosModel model,
        MosInstanceParameters instance,
        double drainVoltage,
        double gateVoltage,
        double sourceVoltage,
        double bulkVoltage)
    {
        var drain = Dual4.Variable(drainVoltage, 0);
        var gate = Dual4.Variable(gateVoltage, 1);
        var source = Dual4.Variable(sourceVoltage, 2);
        var bulk = Dual4.Variable(bulkVoltage, 3);
        var normalizedDrain = model.Polarity * drain;
        var normalizedGate = model.Polarity * gate;
        var normalizedSource = model.Polarity * source;
        var normalizedBulk = model.Polarity * bulk;
        var normalizedBulkDrain = normalizedBulk - normalizedDrain;
        var normalizedBulkSource = normalizedBulk - normalizedSource;
        var temperature = instance.TemperatureParameters;
        var thermalVoltage = temperature.ThermalVoltage;
        var drainSaturationCurrent = temperature.JunctionSaturationCurrentDensity > 0.0 &&
            instance.DrainArea > 0.0
            ? temperature.JunctionSaturationCurrentDensity * instance.Multiplicity * instance.DrainArea
            : temperature.JunctionSaturationCurrent * instance.Multiplicity;
        var sourceSaturationCurrent = temperature.JunctionSaturationCurrentDensity > 0.0 &&
            instance.SourceArea > 0.0
            ? temperature.JunctionSaturationCurrentDensity * instance.Multiplicity * instance.SourceArea
            : temperature.JunctionSaturationCurrent * instance.Multiplicity;
        var bulkDrainCurrent = drainSaturationCurrent *
            (Dual4.ExpClamped(normalizedBulkDrain / thermalVoltage) - 1.0);
        var bulkSourceCurrent = sourceSaturationCurrent *
            (Dual4.ExpClamped(normalizedBulkSource / thermalVoltage) - 1.0);

        var normalMode = normalizedDrain.Value >= normalizedSource.Value;
        var channelDrain = normalMode ? normalizedDrain : normalizedSource;
        var channelSource = normalMode ? normalizedSource : normalizedDrain;
        var channelGateSource = normalizedGate - channelSource;
        var channelBulkSource = normalizedBulk - channelSource;
        var squareRootPhi = Math.Sqrt(temperature.SurfacePotential);
        Dual4 squareRootBodyPotential;
        if (channelBulkSource.Value <= 0.0)
        {
            squareRootBodyPotential = Dual4.Sqrt(temperature.SurfacePotential - channelBulkSource);
        }
        else
        {
            squareRootBodyPotential = squareRootPhi -
                channelBulkSource / (2.0 * squareRootPhi);
            if (squareRootBodyPotential.Value < 0.0)
                squareRootBodyPotential = 0.0;
        }
        var threshold = model.Polarity * temperature.ThresholdVoltage +
            temperature.BodyEffectCoefficient * (squareRootBodyPotential - squareRootPhi);
        var gateOverdrive = channelGateSource - threshold;
        var channelVoltage = channelDrain - channelSource;
        var effectiveLength = instance.Length - 2.0 * model.LateralDiffusion;
        if (effectiveLength <= 0.0)
            throw new InvalidDataException(
                $"MOS1 effective length must be positive for model '{model.Name}'");
        var beta = temperature.Transconductance * instance.Multiplicity * instance.Width /
            effectiveLength;
        Dual4 channelCurrent = 0.0;
        if (gateOverdrive.Value > 0.0)
        {
            var modulation = 1.0 + model.ChannelLengthModulation * channelVoltage;
            channelCurrent = gateOverdrive.Value <= channelVoltage.Value
                ? 0.5 * beta * gateOverdrive * gateOverdrive * modulation
                : beta * channelVoltage *
                    (gateOverdrive - 0.5 * channelVoltage) * modulation;
        }
        var normalizedDrainChannelCurrent = normalMode ? channelCurrent : -channelCurrent;
        var normalizedSourceChannelCurrent = -normalizedDrainChannelCurrent;
        var drainCurrent = model.Polarity *
            (normalizedDrainChannelCurrent - bulkDrainCurrent);
        Dual4 gateCurrent = 0.0;
        var sourceCurrent = model.Polarity *
            (normalizedSourceChannelCurrent - bulkSourceCurrent);
        var bulkCurrent = model.Polarity * (bulkDrainCurrent + bulkSourceCurrent);

        var bulkDrainBottomCapacitance = instance.Multiplicity *
            (temperature.BulkDrainCapacitance +
                temperature.BulkCapacitanceFactor * instance.DrainArea);
        var bulkSourceBottomCapacitance = instance.Multiplicity *
            (temperature.BulkSourceCapacitance +
                temperature.BulkCapacitanceFactor * instance.SourceArea);
        var bulkDrainSidewallCapacitance = instance.Multiplicity *
            temperature.SidewallCapacitanceFactor * instance.DrainPerimeter;
        var bulkSourceSidewallCapacitance = instance.Multiplicity *
            temperature.SidewallCapacitanceFactor * instance.SourcePerimeter;
        var bulkDrainCharge = JunctionChargeDual(
            bulkDrainBottomCapacitance,
            temperature.BulkJunctionPotential,
            model.BulkJunctionGradingCoefficient,
            model.ForwardBiasCoefficient,
            normalizedBulkDrain) + JunctionChargeDual(
                bulkDrainSidewallCapacitance,
                temperature.BulkJunctionPotential,
                model.SidewallJunctionGradingCoefficient,
                model.ForwardBiasCoefficient,
                normalizedBulkDrain);
        var bulkSourceCharge = JunctionChargeDual(
            bulkSourceBottomCapacitance,
            temperature.BulkJunctionPotential,
            model.BulkJunctionGradingCoefficient,
            model.ForwardBiasCoefficient,
            normalizedBulkSource) + JunctionChargeDual(
                bulkSourceSidewallCapacitance,
                temperature.BulkJunctionPotential,
                model.SidewallJunctionGradingCoefficient,
                model.ForwardBiasCoefficient,
                normalizedBulkSource);
        var drainCharge = -model.Polarity * bulkDrainCharge;
        Dual4 gateCharge = 0.0;
        var sourceCharge = -model.Polarity * bulkSourceCharge;
        var bulkCharge = model.Polarity * (bulkDrainCharge + bulkSourceCharge);
        var meyerHalfCapacitance = MosMeyerHalfCapacitance(
            model,
            instance,
            normalMode,
            normalizedDrain.Value,
            normalizedGate.Value,
            normalizedSource.Value,
            normalizedBulk.Value,
            threshold.Value,
            gateOverdrive.Value);

        return new MosEvaluation(
            MosVector(drainCurrent, gateCurrent, sourceCurrent, bulkCurrent),
            MosMatrix(drainCurrent, gateCurrent, sourceCurrent, bulkCurrent),
            MosVector(drainCharge, gateCharge, sourceCharge, bulkCharge),
            MosMatrix(drainCharge, gateCharge, sourceCharge, bulkCharge),
            meyerHalfCapacitance);
    }

    private static MosGateVector MosMeyerHalfCapacitance(
        MosModel model,
        MosInstanceParameters instance,
        bool normalMode,
        double normalizedDrain,
        double normalizedGate,
        double normalizedSource,
        double normalizedBulk,
        double threshold,
        double gateOverdrive)
    {
        if (model.OxideThickness <= 0.0)
            return MosGateVector.Zero;
        const double siliconDioxidePermittivity = 3.9 * 8.854214871e-12;
        var effectiveLength = instance.Length - 2.0 * model.LateralDiffusion;
        var oxideCapacitance = siliconDioxidePermittivity / model.OxideThickness *
            effectiveLength * instance.Width * instance.Multiplicity;
        var orientedSource = normalMode ? normalizedSource : normalizedDrain;
        var orientedDrain = normalMode ? normalizedDrain : normalizedSource;
        var gateSource = normalizedGate - orientedSource;
        var gateDrain = normalizedGate - orientedDrain;
        var gateBulk = normalizedGate - normalizedBulk;
        var (sourceHalf, drainHalf, bulkHalf) = MeyerHalfCapacitances(
            gateSource,
            gateDrain,
            gateBulk,
            threshold,
            Math.Max(gateOverdrive, 0.0),
            instance.TemperatureParameters.SurfacePotential,
            oxideCapacitance);
        return normalMode
            ? new MosGateVector(drainHalf, sourceHalf, bulkHalf)
            : new MosGateVector(sourceHalf, drainHalf, bulkHalf);
    }

    private static (double GateSource, double GateDrain, double GateBulk) MeyerHalfCapacitances(
        double gateSource,
        double gateDrain,
        double gateBulk,
        double threshold,
        double saturationVoltage,
        double surfacePotential,
        double oxideCapacitance)
    {
        const double minimumSaturationVoltage = 0.025;
        var gateOverdrive = gateSource - threshold;
        saturationVoltage = Math.Max(saturationVoltage, minimumSaturationVoltage);
        double source = 0.0;
        double drain = 0.0;
        double bulk;
        if (gateOverdrive <= -surfacePotential)
        {
            bulk = 0.5 * oxideCapacitance;
        }
        else if (gateOverdrive <= -0.5 * surfacePotential)
        {
            bulk = -gateOverdrive * oxideCapacitance / (2.0 * surfacePotential);
        }
        else if (gateOverdrive <= 0.0)
        {
            bulk = -gateOverdrive * oxideCapacitance / (2.0 * surfacePotential);
            source = gateOverdrive * oxideCapacitance / (1.5 * surfacePotential) +
                oxideCapacitance / 3.0;
            var drainSource = gateSource - gateDrain;
            if (drainSource < saturationVoltage)
            {
                var denominator = 2.0 * saturationVoltage - drainSource;
                var drainDifference = saturationVoltage - drainSource;
                drain = source * (1.0 -
                    saturationVoltage * saturationVoltage / (denominator * denominator));
                source *= 1.0 -
                    drainDifference * drainDifference / (denominator * denominator);
            }
        }
        else
        {
            bulk = 0.0;
            var drainSource = gateSource - gateDrain;
            if (drainSource >= saturationVoltage)
            {
                source = oxideCapacitance / 3.0;
            }
            else
            {
                var denominator = 2.0 * saturationVoltage - drainSource;
                var drainDifference = saturationVoltage - drainSource;
                drain = oxideCapacitance * (1.0 -
                    saturationVoltage * saturationVoltage / (denominator * denominator)) / 3.0;
                source = oxideCapacitance * (1.0 -
                    drainDifference * drainDifference / (denominator * denominator)) / 3.0;
            }
        }
        _ = gateBulk;
        return (source, drain, bulk);
    }

    private static MosGateVector MosOverlapCapacitances(
        MosModel model,
        MosInstanceParameters instance)
    {
        var effectiveLength = instance.Length - 2.0 * model.LateralDiffusion;
        return new MosGateVector(
            model.GateDrainOverlapCapacitanceFactor * instance.Width * instance.Multiplicity,
            model.GateSourceOverlapCapacitanceFactor * instance.Width * instance.Multiplicity,
            model.GateBulkOverlapCapacitanceFactor * effectiveLength * instance.Multiplicity);
    }

    private static MosGateVector MosGateVoltages(
        double drainVoltage,
        double gateVoltage,
        double sourceVoltage,
        double bulkVoltage) =>
        new(
            gateVoltage - drainVoltage,
            gateVoltage - sourceVoltage,
            gateVoltage - bulkVoltage);

    private static MosTerminalVector MosGateTerminalCharge(MosGateVector charge) =>
        new(
            -charge.GateDrain,
            charge.GateDrain + charge.GateSource + charge.GateBulk,
            -charge.GateSource,
            -charge.GateBulk);

    private static MosTerminalMatrix MosGateCapacitanceMatrix(MosGateVector capacitance) =>
        new(
            capacitance.GateDrain,
            -capacitance.GateDrain,
            0.0,
            0.0,
            -capacitance.GateDrain,
            capacitance.GateDrain + capacitance.GateSource + capacitance.GateBulk,
            -capacitance.GateSource,
            -capacitance.GateBulk,
            0.0,
            -capacitance.GateSource,
            capacitance.GateSource,
            0.0,
            0.0,
            -capacitance.GateBulk,
            0.0,
            capacitance.GateBulk);

    private static MosTerminalMatrix MosAcCapacitance(
        MosModel model,
        MosInstanceParameters instance,
        MosEvaluation evaluation) =>
        evaluation.JunctionCapacitance + MosGateCapacitanceMatrix(
            MosOverlapCapacitances(model, instance) +
            2.0 * evaluation.MeyerHalfCapacitance);

    private static MosDynamicChargeEvaluation EvaluateMosDynamicCharge(
        MosModel model,
        MosInstanceParameters instance,
        MosEvaluation evaluation,
        double drainVoltage,
        double gateVoltage,
        double sourceVoltage,
        double bulkVoltage,
        MosGateVector previousGateCharge,
        MosGateVector previousGateVoltage,
        MosGateVector previousMeyerHalfCapacitance)
    {
        var gateVoltageLinks = MosGateVoltages(
            drainVoltage,
            gateVoltage,
            sourceVoltage,
            bulkVoltage);
        var effectiveGateCapacitance = MosOverlapCapacitances(model, instance) +
            evaluation.MeyerHalfCapacitance + previousMeyerHalfCapacitance;
        var gateCharge = previousGateCharge + effectiveGateCapacitance.Multiply(
            gateVoltageLinks - previousGateVoltage);
        return new MosDynamicChargeEvaluation(
            evaluation.JunctionCharge + MosGateTerminalCharge(gateCharge),
            evaluation.JunctionCapacitance +
                MosGateCapacitanceMatrix(effectiveGateCapacitance),
            gateCharge,
            gateVoltageLinks);
    }

    private static Dual4 JunctionChargeDual(
        double zeroBiasCapacitance,
        double junctionPotential,
        double gradingCoefficient,
        double forwardBiasCoefficient,
        Dual4 voltage)
    {
        var charge = JunctionCharge(
            zeroBiasCapacitance,
            junctionPotential,
            gradingCoefficient,
            forwardBiasCoefficient,
            voltage.Value);
        var capacitance = JunctionCapacitance(
            zeroBiasCapacitance,
            junctionPotential,
            gradingCoefficient,
            forwardBiasCoefficient,
            voltage.Value);
        return new Dual4(
            charge,
            capacitance * voltage.Drain,
            capacitance * voltage.Gate,
            capacitance * voltage.Source,
            capacitance * voltage.Bulk);
    }

    private static MosTerminalVector MosVector(Dual4 drain, Dual4 gate, Dual4 source, Dual4 bulk) =>
        new(drain.Value, gate.Value, source.Value, bulk.Value);

    private static MosTerminalMatrix MosMatrix(Dual4 drain, Dual4 gate, Dual4 source, Dual4 bulk) =>
        new(
            drain.Drain,
            drain.Gate,
            drain.Source,
            drain.Bulk,
            gate.Drain,
            gate.Gate,
            gate.Source,
            gate.Bulk,
            source.Drain,
            source.Gate,
            source.Source,
            source.Bulk,
            bulk.Drain,
            bulk.Gate,
            bulk.Source,
            bulk.Bulk);

    private static BjtEvaluation EvaluateBjt(
        BjtModel model,
        BjtInstanceParameters instance,
        double collectorVoltage,
        double baseVoltage,
        double emitterVoltage)
    {
        var temperature = instance.TemperatureParameters;
        var normalizedBaseEmitter = model.Polarity * (baseVoltage - emitterVoltage);
        var normalizedBaseCollector = model.Polarity * (baseVoltage - collectorVoltage);
        var forwardThermalVoltage = temperature.ThermalVoltage * model.ForwardEmissionCoefficient;
        var reverseThermalVoltage = temperature.ThermalVoltage * model.ReverseEmissionCoefficient;
        var (forwardCurrent, forwardConductance) = JunctionCurrent(
            temperature.SaturationCurrent,
            normalizedBaseEmitter,
            forwardThermalVoltage);
        var (reverseCurrent, reverseConductance) = JunctionCurrent(
            temperature.SaturationCurrent,
            normalizedBaseCollector,
            reverseThermalVoltage);
        var (baseEmitterLeakageCurrent, baseEmitterLeakageConductance) = JunctionCurrent(
            temperature.BaseEmitterLeakageSaturationCurrent,
            normalizedBaseEmitter,
            temperature.ThermalVoltage * model.BaseEmitterLeakageEmissionCoefficient);
        var (baseCollectorLeakageCurrent, baseCollectorLeakageConductance) = JunctionCurrent(
            temperature.BaseCollectorLeakageSaturationCurrent,
            normalizedBaseCollector,
            temperature.ThermalVoltage * model.BaseCollectorLeakageEmissionCoefficient);

        var earlyDenominator = Math.Max(
            1e-12,
            1.0 - temperature.InverseForwardEarlyVoltage * normalizedBaseCollector -
            temperature.InverseReverseEarlyVoltage * normalizedBaseEmitter);
        var inverseEarlyDenominator = 1.0 / earlyDenominator;
        var highInjectionArgument = Math.Max(
            0.0,
            1.0 + 4.0 * (
                temperature.InverseForwardRollOffCurrent * forwardCurrent +
                temperature.InverseReverseRollOffCurrent * reverseCurrent));
        var highInjectionRoot = highInjectionArgument > 0.0
            ? Math.Sqrt(highInjectionArgument)
            : 1.0;
        var baseCharge = inverseEarlyDenominator * (1.0 + highInjectionRoot) / 2.0;
        var inverseBaseCharge = 1.0 / Math.Max(baseCharge, 1e-30);
        var inverseEarlyBaseEmitterDerivative =
            inverseEarlyDenominator * inverseEarlyDenominator *
            temperature.InverseReverseEarlyVoltage;
        var inverseEarlyBaseCollectorDerivative =
            inverseEarlyDenominator * inverseEarlyDenominator *
            temperature.InverseForwardEarlyVoltage;
        var highInjectionBaseEmitterDerivative =
            2.0 * temperature.InverseForwardRollOffCurrent * forwardConductance /
            highInjectionRoot;
        var highInjectionBaseCollectorDerivative =
            2.0 * temperature.InverseReverseRollOffCurrent * reverseConductance /
            highInjectionRoot;
        var baseChargeBaseEmitterDerivative =
            inverseEarlyBaseEmitterDerivative * (1.0 + highInjectionRoot) / 2.0 +
            inverseEarlyDenominator * highInjectionBaseEmitterDerivative / 2.0;
        var baseChargeBaseCollectorDerivative =
            inverseEarlyBaseCollectorDerivative * (1.0 + highInjectionRoot) / 2.0 +
            inverseEarlyDenominator * highInjectionBaseCollectorDerivative / 2.0;
        var transportNumerator = forwardCurrent - reverseCurrent;
        var transportCurrent = transportNumerator * inverseBaseCharge;
        var transportBaseEmitterDerivative =
            forwardConductance * inverseBaseCharge -
            transportNumerator * baseChargeBaseEmitterDerivative *
                inverseBaseCharge * inverseBaseCharge;
        var transportBaseCollectorDerivative =
            -reverseConductance * inverseBaseCharge -
            transportNumerator * baseChargeBaseCollectorDerivative *
                inverseBaseCharge * inverseBaseCharge;
        var normalizedCollectorCurrent = transportCurrent -
            reverseCurrent / temperature.ReverseBeta - baseCollectorLeakageCurrent;
        var normalizedBaseCurrent = forwardCurrent / temperature.ForwardBeta +
            baseEmitterLeakageCurrent + reverseCurrent / temperature.ReverseBeta +
            baseCollectorLeakageCurrent;
        var normalizedEmitterCurrent = -normalizedCollectorCurrent - normalizedBaseCurrent;

        var collectorBaseEmitterDerivative = transportBaseEmitterDerivative;
        var collectorBaseCollectorDerivative = transportBaseCollectorDerivative -
            reverseConductance / temperature.ReverseBeta - baseCollectorLeakageConductance;
        var baseBaseEmitterDerivative = forwardConductance / temperature.ForwardBeta +
            baseEmitterLeakageConductance;
        var baseBaseCollectorDerivative = reverseConductance / temperature.ReverseBeta +
            baseCollectorLeakageConductance;
        var emitterBaseEmitterDerivative =
            -collectorBaseEmitterDerivative - baseBaseEmitterDerivative;
        var emitterBaseCollectorDerivative =
            -collectorBaseCollectorDerivative - baseBaseCollectorDerivative;

        static (double Collector, double Base, double Emitter) TerminalDerivatives(
            double baseEmitterDerivative,
            double baseCollectorDerivative) => (
                -baseCollectorDerivative,
                baseEmitterDerivative + baseCollectorDerivative,
                -baseEmitterDerivative);

        var collector = TerminalDerivatives(
            collectorBaseEmitterDerivative,
            collectorBaseCollectorDerivative);
        var @base = TerminalDerivatives(
            baseBaseEmitterDerivative,
            baseBaseCollectorDerivative);
        var emitter = TerminalDerivatives(
            emitterBaseEmitterDerivative,
            emitterBaseCollectorDerivative);

        var baseEmitterDepletionCharge = JunctionCharge(
            temperature.BaseEmitterCapacitance,
            temperature.BaseEmitterPotential,
            model.BaseEmitterGradingCoefficient,
            model.ForwardBiasCoefficient,
            normalizedBaseEmitter);
        var baseCollectorDepletionCharge = JunctionCharge(
            temperature.BaseCollectorCapacitance,
            temperature.BaseCollectorPotential,
            model.BaseCollectorGradingCoefficient,
            model.ForwardBiasCoefficient,
            normalizedBaseCollector);
        var forwardChargeUsesBaseCharge = normalizedBaseEmitter > 0.0;
        var forwardDiffusionCurrent = forwardChargeUsesBaseCharge
            ? forwardCurrent * inverseBaseCharge
            : forwardCurrent;
        var forwardDiffusionBaseEmitterDerivative = forwardChargeUsesBaseCharge
            ? forwardConductance * inverseBaseCharge -
                forwardCurrent * baseChargeBaseEmitterDerivative *
                    inverseBaseCharge * inverseBaseCharge
            : forwardConductance;
        var forwardDiffusionBaseCollectorDerivative = forwardChargeUsesBaseCharge
            ? -forwardCurrent * baseChargeBaseCollectorDerivative *
                inverseBaseCharge * inverseBaseCharge
            : 0.0;
        var normalizedBaseEmitterCharge = baseEmitterDepletionCharge +
            temperature.ForwardTransitTime * forwardDiffusionCurrent;
        var normalizedBaseCollectorCharge = baseCollectorDepletionCharge +
            temperature.ReverseTransitTime * reverseCurrent;
        var baseEmitterChargeDerivative = JunctionCapacitance(
            temperature.BaseEmitterCapacitance,
            temperature.BaseEmitterPotential,
            model.BaseEmitterGradingCoefficient,
            model.ForwardBiasCoefficient,
            normalizedBaseEmitter) + temperature.ForwardTransitTime *
            forwardDiffusionBaseEmitterDerivative;
        var baseEmitterChargeBaseCollectorDerivative =
            temperature.ForwardTransitTime * forwardDiffusionBaseCollectorDerivative;
        var baseCollectorChargeDerivative = JunctionCapacitance(
            temperature.BaseCollectorCapacitance,
            temperature.BaseCollectorPotential,
            model.BaseCollectorGradingCoefficient,
            model.ForwardBiasCoefficient,
            normalizedBaseCollector) + temperature.ReverseTransitTime * reverseConductance;

        var charge = new BjtTerminalVector(
            -model.Polarity * normalizedBaseCollectorCharge,
            model.Polarity * (normalizedBaseEmitterCharge + normalizedBaseCollectorCharge),
            -model.Polarity * normalizedBaseEmitterCharge);
        var capacitance = new BjtTerminalMatrix(
            baseCollectorChargeDerivative,
            -baseCollectorChargeDerivative,
            0.0,
            -(baseEmitterChargeBaseCollectorDerivative + baseCollectorChargeDerivative),
            baseEmitterChargeDerivative + baseEmitterChargeBaseCollectorDerivative +
                baseCollectorChargeDerivative,
            -baseEmitterChargeDerivative,
            baseEmitterChargeBaseCollectorDerivative,
            -(baseEmitterChargeDerivative + baseEmitterChargeBaseCollectorDerivative),
            baseEmitterChargeDerivative);
        var scale = instance.Multiplicity;
        return new BjtEvaluation(
            scale * model.Polarity * normalizedCollectorCurrent,
            scale * model.Polarity * normalizedBaseCurrent,
            scale * model.Polarity * normalizedEmitterCurrent,
            scale * collector.Collector,
            scale * collector.Base,
            scale * collector.Emitter,
            scale * @base.Collector,
            scale * @base.Base,
            scale * @base.Emitter,
            scale * emitter.Collector,
            scale * emitter.Base,
            scale * emitter.Emitter,
            scale * charge,
            Scale(capacitance, scale));

        static BjtTerminalMatrix Scale(BjtTerminalMatrix matrix, double factor) => new(
            factor * matrix.Cc,
            factor * matrix.Cb,
            factor * matrix.Ce,
            factor * matrix.Bc,
            factor * matrix.Bb,
            factor * matrix.Be,
            factor * matrix.Ec,
            factor * matrix.Eb,
            factor * matrix.Ee);

        static (double Current, double Conductance) JunctionCurrent(
            double saturationCurrent,
            double voltage,
            double emissionVoltage)
        {
            if (saturationCurrent == 0.0)
                return (0.0, 0.0);
            if (voltage >= -3.0 * emissionVoltage)
            {
                var exponential = Math.Exp(Math.Clamp(voltage / emissionVoltage, -80.0, 40.0));
                return (
                    saturationCurrent * (exponential - 1.0),
                    saturationCurrent * exponential / emissionVoltage);
            }

            var argument = 3.0 * emissionVoltage / (voltage * Math.E);
            argument = argument * argument * argument;
            return (
                -saturationCurrent * (1.0 + argument),
                saturationCurrent * 3.0 * argument / voltage);
        }
    }

    private static double JunctionCharge(
        double zeroBiasCapacitance,
        double junctionPotential,
        double gradingCoefficient,
        double forwardBiasCoefficient,
        double voltage)
    {
        if (zeroBiasCapacitance == 0.0)
            return 0.0;
        var junctionVoltage = forwardBiasCoefficient * junctionPotential;
        var oneMinusForwardCoefficient = 1.0 - forwardBiasCoefficient;
        var oneMinusGrading = 1.0 - gradingCoefficient;
        var chargeAtJunction = Math.Abs(oneMinusGrading) < 1e-12
            ? -zeroBiasCapacitance * junctionPotential * Math.Log(oneMinusForwardCoefficient)
            : zeroBiasCapacitance * junctionPotential *
                (1.0 - Math.Pow(oneMinusForwardCoefficient, oneMinusGrading)) / oneMinusGrading;
        if (voltage < junctionVoltage)
        {
            var depletion = 1.0 - voltage / junctionPotential;
            return Math.Abs(oneMinusGrading) < 1e-12
                ? -zeroBiasCapacitance * junctionPotential * Math.Log(depletion)
                : zeroBiasCapacitance * junctionPotential *
                    (1.0 - Math.Pow(depletion, oneMinusGrading)) / oneMinusGrading;
        }
        var scale = zeroBiasCapacitance /
            Math.Pow(oneMinusForwardCoefficient, 1.0 + gradingCoefficient);
        var slopeOffset = 1.0 - forwardBiasCoefficient * (1.0 + gradingCoefficient);
        return chargeAtJunction + scale * (
            slopeOffset * (voltage - junctionVoltage) +
            gradingCoefficient *
            (voltage * voltage - junctionVoltage * junctionVoltage) /
            (2.0 * junctionPotential));
    }

    private static double JunctionCapacitance(
        double zeroBiasCapacitance,
        double junctionPotential,
        double gradingCoefficient,
        double forwardBiasCoefficient,
        double voltage)
    {
        if (zeroBiasCapacitance == 0.0)
            return 0.0;
        var normalizedVoltage = voltage / junctionPotential;
        if (normalizedVoltage < forwardBiasCoefficient)
            return zeroBiasCapacitance * Math.Pow(1.0 - normalizedVoltage, -gradingCoefficient);
        var oneMinusForwardCoefficient = 1.0 - forwardBiasCoefficient;
        var slopeOffset = 1.0 - forwardBiasCoefficient * (1.0 + gradingCoefficient);
        return zeroBiasCapacitance /
            Math.Pow(oneMinusForwardCoefficient, 1.0 + gradingCoefficient) *
            (slopeOffset + gradingCoefficient * normalizedVoltage);
    }

    private static DiodeEvaluation EvaluateDiode(
        DiodeModel model,
        DiodeInstanceParameters instance,
        double voltage)
    {
        const double e = Math.E;
        var temperature = instance.TemperatureParameters;
        var saturationCurrent = temperature.SaturationCurrent;
        var emissionThermalVoltage = model.EmissionCoefficient * temperature.ThermalVoltage;
        double current;
        double conductance;
        if (voltage >= -3.0 * emissionThermalVoltage)
        {
            var exponential = Math.Exp(Math.Clamp(
                voltage / emissionThermalVoltage,
                -80.0,
                40.0));
            current = saturationCurrent * (exponential - 1.0);
            conductance = saturationCurrent * exponential / emissionThermalVoltage;
        }
        else if (!temperature.BreakdownVoltage.HasValue ||
            voltage >= -temperature.BreakdownVoltage.Value)
        {
            var argument = 3.0 * emissionThermalVoltage / (voltage * e);
            argument = argument * argument * argument;
            current = -saturationCurrent * (1.0 + argument);
            conductance = saturationCurrent * 3.0 * argument / voltage;
        }
        else
        {
            var breakdownThermalVoltage =
                model.BreakdownEmissionCoefficient * temperature.ThermalVoltage;
            var reverseExponential = Math.Exp(Math.Clamp(
                -(temperature.BreakdownVoltage.Value + voltage) / breakdownThermalVoltage,
                -80.0,
                80.0));
            current = -saturationCurrent * reverseExponential;
            conductance = saturationCurrent * reverseExponential / breakdownThermalVoltage;
        }

        var charge = JunctionCharge(
            temperature.ZeroBiasJunctionCapacitance,
            temperature.JunctionPotential,
            model.GradingCoefficient,
            model.ForwardBiasCoefficient,
            voltage);
        var capacitance = JunctionCapacitance(
            temperature.ZeroBiasJunctionCapacitance,
            temperature.JunctionPotential,
            model.GradingCoefficient,
            model.ForwardBiasCoefficient,
            voltage);
        if (temperature.TransitTime > 0.0)
        {
            charge += temperature.TransitTime * current;
            capacitance += temperature.TransitTime * conductance;
        }
        return new DiodeEvaluation(current, conductance, charge, capacitance);
    }

    private static double NonlinearResidualRatio(
        Deck deck,
        string kind,
        double x,
        string? sweepSource,
        TransientContext? transient,
        IReadOnlyDictionary<string, int> nodeIndex,
        IReadOnlyDictionary<string, int> branchIndex,
        IReadOnlyList<double> solution,
        double? sourceEvaluationTime)
    {
        var residual = ArrayPool<double>.Shared.Rent(solution.Count);
        var scale = ArrayPool<double>.Shared.Rent(solution.Count);
        Array.Clear(residual, 0, solution.Count);
        Array.Clear(scale, 0, solution.Count);
        try
        {
            int Index(string node) => node.Equals("0", StringComparison.OrdinalIgnoreCase) ? -1 : nodeIndex[node];
            double Voltage(string node)
            {
                var index = Index(node);
                return index < 0 ? 0.0 : solution[index];
            }
            void AddEquationTerm(int index, double value)
            {
                if (index < 0)
                    return;
                residual[index] += value;
                scale[index] += Math.Abs(value);
            }
            void AddScaledEquationTerm(int index, double value, double equationScale)
            {
                if (index < 0)
                    return;
                residual[index] += value;
                scale[index] += equationScale;
            }
            void AddCurrent(IReadOnlyList<string> nodes, double current)
            {
                AddEquationTerm(Index(nodes[0]), current);
                AddEquationTerm(Index(nodes[1]), -current);
            }
            void AddCurrentBetween(string positive, string negative, double current)
            {
                AddEquationTerm(Index(positive), current);
                AddEquationTerm(Index(negative), -current);
            }
            void SetBranchResidual(string name, double value, double equationScale)
            {
                var index = branchIndex[name];
                residual[index] = value;
                scale[index] = equationScale;
            }

            var bdf = transient?.UsesBdfIntegration == true
                ? transient.BdfCoefficients()
                : default;

            foreach (var element in deck.Elements)
            {
                var value = element.Name.Equals(sweepSource, StringComparison.OrdinalIgnoreCase)
                    ? x
                    : kind == "tran"
                        ? element.ValueAt(sourceEvaluationTime ?? x, transient?.DefaultSourceTransition ?? 0.0)
                        : element.Value;
                var voltage = Voltage(element.Nodes[0]) - Voltage(element.Nodes[1]);
                switch (element.Kind)
                {
                    case 'R':
                        AddCurrent(element.Nodes, voltage / value);
                        break;
                    case 'G':
                        AddCurrent(
                            element.Nodes,
                            value * (Voltage(element.Nodes[2]) - Voltage(element.Nodes[3])));
                        break;
                    case 'E':
                        {
                            var branchCurrent = solution[branchIndex[element.Name]];
                            var controlVoltage = Voltage(element.Nodes[2]) - Voltage(element.Nodes[3]);
                            AddCurrent(element.Nodes, branchCurrent);
                            SetBranchResidual(
                                element.Name,
                                voltage - value * controlVoltage,
                                Math.Abs(voltage) + Math.Abs(value * controlVoltage));
                            break;
                        }
                    case 'F':
                        AddCurrent(
                            element.Nodes,
                            value * solution[branchIndex[element.ControlName!]]);
                        break;
                    case 'H':
                        {
                            var branchCurrent = solution[branchIndex[element.Name]];
                            var controlCurrent = solution[branchIndex[element.ControlName!]];
                            AddCurrent(element.Nodes, branchCurrent);
                            SetBranchResidual(
                                element.Name,
                                voltage - value * controlCurrent,
                                Math.Abs(voltage) + Math.Abs(value * controlCurrent));
                            break;
                        }
                    case 'I':
                        AddCurrent(element.Nodes, value);
                        break;
                    case 'V':
                        {
                            var branchCurrent = solution[branchIndex[element.Name]];
                            AddCurrent(element.Nodes, branchCurrent);
                            SetBranchResidual(
                                element.Name,
                                voltage - value,
                                Math.Abs(voltage) + Math.Abs(value));
                            break;
                        }
                    case 'C':
                        if (transient is not null)
                        {
                            var state = element.TransientStateIndex;
                            var current = transient.UsesBdfIntegration
                                ? value * (
                                    bdf.A0 * voltage +
                                    bdf.A1 * transient.Capacitors[state] +
                                    bdf.A2 * transient.CapacitorPreviousVoltages[state])
                                : 2.0 * value / transient.Step *
                                    (voltage - transient.Capacitors[state]) -
                                    transient.CapacitorCurrents[state];
                            AddCurrent(element.Nodes, current);
                        }
                        break;
                    case 'D':
                        {
                            var model = deck.DiodeModels[element.ModelName!];
                            var evaluation = EvaluateDiode(model, element.Diode!, voltage);
                            var current = evaluation.Current;
                            if (transient is not null)
                            {
                                var state = element.TransientStateIndex;
                                current += transient.UsesBdfIntegration
                                    ? bdf.A0 * evaluation.Charge +
                                        bdf.A1 * transient.DiodeCharges[state] +
                                        bdf.A2 * transient.DiodePreviousCharges[state]
                                    : 2.0 * (evaluation.Charge - transient.DiodeCharges[state]) / transient.Step -
                                        transient.DiodeDisplacementCurrents[state];
                            }
                            AddCurrent(element.Nodes, current);
                            break;
                        }
                    case 'Q':
                        {
                            var evaluation = EvaluateBjt(
                                deck.BjtModels[element.ModelName!],
                                element.Bjt!,
                                Voltage(element.Nodes[0]),
                                Voltage(element.Nodes[1]),
                                Voltage(element.Nodes[2]));
                            AddEquationTerm(Index(element.Nodes[0]), evaluation.CollectorCurrent);
                            AddEquationTerm(Index(element.Nodes[1]), evaluation.BaseCurrent);
                            AddEquationTerm(Index(element.Nodes[2]), evaluation.EmitterCurrent);
                            if (transient is not null)
                            {
                                var state = element.TransientStateIndex;
                                var currentCharge = evaluation.Charge;
                                var previousCharge = transient.BjtCharges[state];
                                var olderCharge = transient.BjtPreviousCharges[state];
                                var previousCurrent = transient.BjtDisplacementCurrents[state];
                                BjtTerminalVector displacementCurrent;
                                BjtTerminalVector displacementScale;
                                if (transient.UsesBdfIntegration)
                                {
                                    displacementCurrent = bdf.A0 * currentCharge +
                                        bdf.A1 * previousCharge + bdf.A2 * olderCharge;
                                    displacementScale = new BjtTerminalVector(
                                        Math.Abs(bdf.A0 * currentCharge.Collector) +
                                            Math.Abs(bdf.A1 * previousCharge.Collector) +
                                            Math.Abs(bdf.A2 * olderCharge.Collector),
                                        Math.Abs(bdf.A0 * currentCharge.Base) +
                                            Math.Abs(bdf.A1 * previousCharge.Base) +
                                            Math.Abs(bdf.A2 * olderCharge.Base),
                                        Math.Abs(bdf.A0 * currentCharge.Emitter) +
                                            Math.Abs(bdf.A1 * previousCharge.Emitter) +
                                            Math.Abs(bdf.A2 * olderCharge.Emitter));
                                }
                                else
                                {
                                    var derivativeScale = 2.0 / transient.Step;
                                    displacementCurrent = derivativeScale *
                                        (currentCharge - previousCharge) - previousCurrent;
                                    displacementScale = new BjtTerminalVector(
                                        Math.Abs(derivativeScale * currentCharge.Collector) +
                                            Math.Abs(derivativeScale * previousCharge.Collector) +
                                            Math.Abs(previousCurrent.Collector),
                                        Math.Abs(derivativeScale * currentCharge.Base) +
                                            Math.Abs(derivativeScale * previousCharge.Base) +
                                            Math.Abs(previousCurrent.Base),
                                        Math.Abs(derivativeScale * currentCharge.Emitter) +
                                            Math.Abs(derivativeScale * previousCharge.Emitter) +
                                            Math.Abs(previousCurrent.Emitter));
                                }
                                AddScaledEquationTerm(
                                    Index(element.Nodes[0]),
                                    displacementCurrent.Collector,
                                    displacementScale.Collector);
                                AddScaledEquationTerm(
                                    Index(element.Nodes[1]),
                                    displacementCurrent.Base,
                                    displacementScale.Base);
                                AddScaledEquationTerm(
                                    Index(element.Nodes[2]),
                                    displacementCurrent.Emitter,
                                    displacementScale.Emitter);
                            }
                            break;
                        }
                    case 'M':
                        {
                            var drainVoltage = Voltage(element.Nodes[0]);
                            var gateVoltage = Voltage(element.Nodes[1]);
                            var sourceVoltage = Voltage(element.Nodes[2]);
                            var bulkVoltage = Voltage(element.Nodes[3]);
                            var model = deck.MosModels[element.ModelName!];
                            var instance = element.Mos!;
                            var evaluation = EvaluateMos(
                                model,
                                instance,
                                drainVoltage,
                                gateVoltage,
                                sourceVoltage,
                                bulkVoltage);
                            AddEquationTerm(Index(element.Nodes[0]), evaluation.Current.Drain);
                            AddEquationTerm(Index(element.Nodes[1]), evaluation.Current.Gate);
                            AddEquationTerm(Index(element.Nodes[2]), evaluation.Current.Source);
                            AddEquationTerm(Index(element.Nodes[3]), evaluation.Current.Bulk);
                            if (transient is not null)
                            {
                                var state = element.TransientStateIndex;
                                var currentCharge = EvaluateMosDynamicCharge(
                                    model,
                                    instance,
                                    evaluation,
                                    drainVoltage,
                                    gateVoltage,
                                    sourceVoltage,
                                    bulkVoltage,
                                    transient.MosGateCharges[state],
                                    transient.MosGateVoltages[state],
                                    transient.MosMeyerHalfCapacitances[state]).Charge;
                                var previousCharge = transient.MosCharges[state];
                                var olderCharge = transient.MosPreviousCharges[state];
                                var previousCurrent = transient.MosDisplacementCurrents[state];
                                MosTerminalVector displacementCurrent;
                                MosTerminalVector displacementScale;
                                if (transient.UsesBdfIntegration)
                                {
                                    displacementCurrent = bdf.A0 * currentCharge +
                                        bdf.A1 * previousCharge + bdf.A2 * olderCharge;
                                    displacementScale = new MosTerminalVector(
                                        Math.Abs(bdf.A0 * currentCharge.Drain) +
                                            Math.Abs(bdf.A1 * previousCharge.Drain) +
                                            Math.Abs(bdf.A2 * olderCharge.Drain),
                                        Math.Abs(bdf.A0 * currentCharge.Gate) +
                                            Math.Abs(bdf.A1 * previousCharge.Gate) +
                                            Math.Abs(bdf.A2 * olderCharge.Gate),
                                        Math.Abs(bdf.A0 * currentCharge.Source) +
                                            Math.Abs(bdf.A1 * previousCharge.Source) +
                                            Math.Abs(bdf.A2 * olderCharge.Source),
                                        Math.Abs(bdf.A0 * currentCharge.Bulk) +
                                            Math.Abs(bdf.A1 * previousCharge.Bulk) +
                                            Math.Abs(bdf.A2 * olderCharge.Bulk));
                                }
                                else
                                {
                                    var derivativeScale = 2.0 / transient.Step;
                                    displacementCurrent = derivativeScale *
                                        (currentCharge - previousCharge) - previousCurrent;
                                    displacementScale = new MosTerminalVector(
                                        Math.Abs(derivativeScale * currentCharge.Drain) +
                                            Math.Abs(derivativeScale * previousCharge.Drain) +
                                            Math.Abs(previousCurrent.Drain),
                                        Math.Abs(derivativeScale * currentCharge.Gate) +
                                            Math.Abs(derivativeScale * previousCharge.Gate) +
                                            Math.Abs(previousCurrent.Gate),
                                        Math.Abs(derivativeScale * currentCharge.Source) +
                                            Math.Abs(derivativeScale * previousCharge.Source) +
                                            Math.Abs(previousCurrent.Source),
                                        Math.Abs(derivativeScale * currentCharge.Bulk) +
                                            Math.Abs(derivativeScale * previousCharge.Bulk) +
                                            Math.Abs(previousCurrent.Bulk));
                                }
                                AddScaledEquationTerm(
                                    Index(element.Nodes[0]),
                                    displacementCurrent.Drain,
                                    displacementScale.Drain);
                                AddScaledEquationTerm(
                                    Index(element.Nodes[1]),
                                    displacementCurrent.Gate,
                                    displacementScale.Gate);
                                AddScaledEquationTerm(
                                    Index(element.Nodes[2]),
                                    displacementCurrent.Source,
                                    displacementScale.Source);
                                AddScaledEquationTerm(
                                    Index(element.Nodes[3]),
                                    displacementCurrent.Bulk,
                                    displacementScale.Bulk);
                            }
                            break;
                        }
                    case 'L':
                        {
                            var branchCurrent = solution[branchIndex[element.Name]];
                            AddCurrent(element.Nodes, branchCurrent);
                            if (transient is null)
                            {
                                SetBranchResidual(element.Name, voltage, Math.Abs(voltage));
                            }
                            else
                            {
                                var state = element.TransientStateIndex;
                                var impedance = transient.UsesBdfIntegration
                                    ? value * bdf.A0
                                    : 2.0 * value / transient.Step;
                                var historyVoltage = transient.UsesBdfIntegration
                                    ? value * (
                                        bdf.A1 * transient.Inductors[state] +
                                        bdf.A2 * transient.InductorPreviousCurrents[state])
                                    : -impedance * transient.Inductors[state] -
                                        transient.InductorVoltages[state];
                                var branchResidual = voltage - impedance * branchCurrent +
                                    -historyVoltage;
                                SetBranchResidual(
                                    element.Name,
                                    branchResidual,
                                    Math.Abs(voltage) + Math.Abs(impedance * branchCurrent) +
                                    Math.Abs(historyVoltage));
                            }
                            break;
                        }
                }
            }

            foreach (var instance in deck.RfmInstances)
            {
                var referenceVoltage = Voltage(instance.Reference);
                if (transient is null)
                {
                    var admittance = instance.Model.DcAdmittance();
                    for (var row = 0; row < instance.Model.Nports; row++)
                    {
                        var current = 0.0;
                        for (var column = 0; column < instance.Model.Nports; column++)
                            current += admittance[row, column].Real *
                                (Voltage(instance.Ports[column]) - referenceVoltage);
                        AddCurrentBetween(instance.Ports[row], instance.Reference, current);
                    }
                    continue;
                }

                var companion = transient.RfmStates[instance.Name].Companion!;
                for (var row = 0; row < instance.Model.Nports; row++)
                {
                    var current = companion.Offset[row];
                    for (var column = 0; column < instance.Model.Nports; column++)
                        current += companion.Conductance[row * instance.Model.Nports + column] *
                            (Voltage(instance.Ports[column]) - referenceVoltage);
                    AddCurrentBetween(instance.Ports[row], instance.Reference, current);
                }
            }

            var maximum = 0.0;
            var relativeTolerance = Math.Min(deck.RelativeTolerance, 1e-6);
            for (var index = 0; index < solution.Count; index++)
            {
                var absoluteTolerance = index < deck.Nodes.Count
                    ? Math.Min(deck.CurrentTolerance, 1e-12)
                    : Math.Min(deck.VoltageTolerance, 1e-9);
                var tolerance = absoluteTolerance + relativeTolerance * scale[index];
                maximum = Math.Max(maximum, Math.Abs(residual[index]) / tolerance);
            }
            return maximum;
        }
        finally
        {
            ArrayPool<double>.Shared.Return(residual);
            ArrayPool<double>.Shared.Return(scale);
        }
    }

    private static double JunctionLimitScale(
        Deck deck,
        IReadOnlyDictionary<string, int> nodeIndex,
        IReadOnlyList<double> previous,
        IReadOnlyList<double> candidate)
    {
        static double Voltage(IReadOnlyList<double> values, IReadOnlyDictionary<string, int> indices, string node) =>
            node.Equals("0", StringComparison.OrdinalIgnoreCase) ? 0.0 : values[indices[node]];

        var alpha = 1.0;
        void LimitJunction(
            string positiveNode,
            string negativeNode,
            int polarity,
            double saturationCurrent,
            double emissionCoefficient)
        {
            var thermalVoltage = 0.025864925786 * emissionCoefficient;
            var criticalVoltage = thermalVoltage * Math.Log(thermalVoltage / (Math.Sqrt(2.0) * saturationCurrent));
            var oldVoltage = polarity * (
                Voltage(previous, nodeIndex, positiveNode) - Voltage(previous, nodeIndex, negativeNode));
            var newVoltage = polarity * (
                Voltage(candidate, nodeIndex, positiveNode) - Voltage(candidate, nodeIndex, negativeNode));
            var delta = newVoltage - oldVoltage;
            if (newVoltage <= criticalVoltage || Math.Abs(delta) <= 2.0 * thermalVoltage)
                return;
            double limited;
            if (oldVoltage > 0.0)
            {
                var argument = 1.0 + delta / thermalVoltage;
                limited = argument > 0.0
                    ? oldVoltage + thermalVoltage * Math.Log(argument)
                    : criticalVoltage;
            }
            else
            {
                limited = thermalVoltage * Math.Log(Math.Max(newVoltage / thermalVoltage, 1.0));
            }
            var scale = (limited - oldVoltage) / delta;
            if (scale > 0.0)
                alpha = Math.Min(alpha, scale);
        }

        foreach (var diode in deck.Elements.Where(element => element.Kind == 'D'))
        {
            var model = deck.DiodeModels[diode.ModelName!];
            var temperature = diode.Diode!.TemperatureParameters;
            LimitJunction(
                diode.Nodes[0],
                diode.Nodes[1],
                1,
                temperature.SaturationCurrent,
                model.EmissionCoefficient * temperature.ThermalVoltage / 0.025864925786);
        }
        foreach (var bjt in deck.Elements.Where(element => element.Kind == 'Q'))
        {
            var model = deck.BjtModels[bjt.ModelName!];
            var temperature = bjt.Bjt!.TemperatureParameters;
            LimitJunction(
                bjt.Nodes[1],
                bjt.Nodes[2],
                model.Polarity,
                temperature.SaturationCurrent,
                model.ForwardEmissionCoefficient * temperature.ThermalVoltage / 0.025864925786);
            LimitJunction(
                bjt.Nodes[1],
                bjt.Nodes[0],
                model.Polarity,
                temperature.SaturationCurrent,
                model.ReverseEmissionCoefficient * temperature.ThermalVoltage / 0.025864925786);
        }
        foreach (var mos in deck.Elements.Where(element => element.Kind == 'M'))
        {
            var model = deck.MosModels[mos.ModelName!];
            var instance = mos.Mos!;
            var temperature = instance.TemperatureParameters;
            var drainSaturationCurrent = temperature.JunctionSaturationCurrentDensity > 0.0 &&
                instance.DrainArea > 0.0
                ? temperature.JunctionSaturationCurrentDensity * instance.Multiplicity * instance.DrainArea
                : temperature.JunctionSaturationCurrent * instance.Multiplicity;
            var sourceSaturationCurrent = temperature.JunctionSaturationCurrentDensity > 0.0 &&
                instance.SourceArea > 0.0
                ? temperature.JunctionSaturationCurrentDensity * instance.Multiplicity * instance.SourceArea
                : temperature.JunctionSaturationCurrent * instance.Multiplicity;
            LimitJunction(
                mos.Nodes[3],
                mos.Nodes[0],
                model.Polarity,
                drainSaturationCurrent,
                temperature.ThermalVoltage / 0.025864925786);
            LimitJunction(
                mos.Nodes[3],
                mos.Nodes[2],
                model.Polarity,
                sourceSaturationCurrent,
                temperature.ThermalVoltage / 0.025864925786);
        }
        return Math.Clamp(alpha, 1e-4, 1.0);
    }

    private static double ConvergenceRatio(
        Deck deck,
        IReadOnlyList<double> previous,
        IReadOnlyList<double> candidate)
    {
        var maximum = 0.0;
        var relativeTolerance = Math.Min(deck.RelativeTolerance, 1e-6);
        for (var index = 0; index < previous.Count; index++)
        {
            var absoluteTolerance = index < deck.Nodes.Count
                ? Math.Min(deck.VoltageTolerance, 1e-9)
                : Math.Min(deck.CurrentTolerance, 1e-12);
            var tolerance = absoluteTolerance + relativeTolerance *
                Math.Max(Math.Abs(previous[index]), Math.Abs(candidate[index]));
            maximum = Math.Max(maximum, Math.Abs(candidate[index] - previous[index]) / tolerance);
        }
        return maximum;
    }

    private static Complex AcValue(Element element) => Complex.FromPolarCoordinates(element.AcAmplitude, element.AcPhaseDegrees * Math.PI / 180.0);

    private static Complex[,] ToComplex(double[] values, int size)
    {
        var result = new Complex[size, size];
        for (var row = 0; row < size; row++)
            for (var column = 0; column < size; column++) result[row, column] = values[row * size + column];
        return result;
    }

    private static void FillPortVoltages(
        SimulationPoint point,
        IReadOnlyDictionary<string, int> nodeIndex,
        RfmInstance instance,
        double[] voltages)
    {
        var solution = point.InternalSolution!;
        var reference = instance.Reference.Equals("0", StringComparison.OrdinalIgnoreCase)
            ? 0.0
            : solution[nodeIndex[instance.Reference]];
        for (var index = 0; index < voltages.Length; index++)
            voltages[index] = solution[nodeIndex[instance.Ports[index]]] - reference;
    }

    private static void FillPortVoltages(
        SolutionVector solution,
        IReadOnlyDictionary<string, int> nodeIndex,
        RfmInstance instance,
        double[] voltages)
    {
        var reference = NodeValue(solution, nodeIndex, instance.Reference);
        for (var index = 0; index < voltages.Length; index++)
            voltages[index] = NodeValue(solution, nodeIndex, instance.Ports[index]) - reference;
    }

    internal static bool RequestedOutput(Deck deck, string analysis, string name) =>
        !deck.InternalNodes.Contains(name) &&
        (!deck.Outputs.TryGetValue(analysis, out var outputs) || outputs.Count == 0 || outputs.Contains(name));

    private static double NodeValue(double[] solution, int index) => index < 0 ? 0.0 : solution[index];

    private static double NodeValue(
        SolutionVector solution,
        IReadOnlyDictionary<string, int> nodeIndex,
        string node) => node.Equals("0", StringComparison.OrdinalIgnoreCase) ? 0.0 : solution.Real(nodeIndex[node]);
}
