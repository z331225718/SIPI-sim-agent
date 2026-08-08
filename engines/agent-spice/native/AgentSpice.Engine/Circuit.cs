using System.Globalization;
using System.Text.RegularExpressions;

namespace AgentSpice.Engine;

internal sealed record Element(
    string Name,
    char Kind,
    string[] Nodes,
    double Value,
    double AcAmplitude = 0.0,
    double AcPhaseDegrees = 0.0,
    TransientSource? Transient = null,
    string? ModelName = null,
    string? ControlName = null,
    MosInstanceParameters? Mos = null,
    DiodeInstanceParameters? Diode = null,
    BjtInstanceParameters? Bjt = null)
{
    internal int[] NodeIndices { get; set; } = [];
    internal int TransientStateIndex { get; set; } = -1;

    internal double ValueAt(double time, double defaultTransition = 0.0) =>
        Transient?.ValueAt(time, defaultTransition) ?? Value;
}

internal abstract record TransientSource
{
    internal abstract bool HasInitialBreakpoint { get; }
    internal abstract double ValueAt(double time, double defaultTransition = 0.0);
    internal abstract double NextBreakpointAfter(double time, double tolerance, double defaultTransition = 0.0);
    internal virtual double CharacteristicTime(double defaultTransition = 0.0) => double.PositiveInfinity;
    internal virtual double TransitionStepLimit(double time, double defaultTransition = 0.0) =>
        double.PositiveInfinity;

    internal virtual bool IsDiscontinuityAt(double time, double defaultTransition = 0.0)
    {
        var left = ValueAt(Math.BitDecrement(time), defaultTransition);
        var right = ValueAt(time, defaultTransition);
        return Math.Abs(right - left) > 1e-9 *
            (1.0 + Math.Max(Math.Abs(left), Math.Abs(right)));
    }

    internal virtual bool IsTransitioningAt(double time, double defaultTransition = 0.0) => false;
}

internal sealed record PulseSource(
    double Initial,
    double Pulsed,
    double Delay,
    double Rise,
    double Fall,
    double Width,
    double Period) : TransientSource
{
    internal override bool HasInitialBreakpoint => Delay == 0.0;

    internal override double CharacteristicTime(double defaultTransition = 0.0)
    {
        var rise = Rise > 0.0 ? Rise : defaultTransition;
        var fall = Fall > 0.0 ? Fall : defaultTransition;
        return Math.Min(
            rise > 0.0 ? rise : double.PositiveInfinity,
            fall > 0.0 ? fall : double.PositiveInfinity);
    }

    internal override double TransitionStepLimit(double time, double defaultTransition = 0.0)
    {
        if (time < Delay)
            return double.PositiveInfinity;
        var rise = Rise > 0.0 ? Rise : defaultTransition;
        var fall = Fall > 0.0 ? Fall : defaultTransition;
        var local = time - Delay;
        if (Period > 0.0)
            local %= Period;
        if (Rise == 0.0 && rise > 0.0 && local < rise)
            return rise / 16.0;
        local -= rise + Width;
        if (Fall == 0.0 && fall > 0.0 && local >= 0.0 && local < fall)
            return fall / 16.0;
        return double.PositiveInfinity;
    }

    internal override double ValueAt(double time, double defaultTransition = 0.0)
    {
        var rise = Rise > 0.0 ? Rise : defaultTransition;
        var fall = Fall > 0.0 ? Fall : defaultTransition;
        if (time < Delay)
            return Initial;
        var local = time - Delay;
        if (Period > 0.0)
            local %= Period;
        if (rise > 0.0 && local < rise)
            return Initial + (Pulsed - Initial) * local / rise;
        local -= rise;
        if (local < Width)
            return Pulsed;
        local -= Width;
        if (fall > 0.0 && local < fall)
            return Pulsed + (Initial - Pulsed) * local / fall;
        return Initial;
    }

    internal override double NextBreakpointAfter(double time, double tolerance, double defaultTransition = 0.0)
    {
        var rise = Rise > 0.0 ? Rise : defaultTransition;
        var fall = Fall > 0.0 ? Fall : defaultTransition;
        var best = double.PositiveInfinity;
        void Consider(double candidate)
        {
            if (candidate > time + tolerance && candidate < best)
                best = candidate;
        }

        void ConsiderCycle(double cycleStart, bool constrainToPeriod)
        {
            Consider(cycleStart);
            if (!constrainToPeriod || rise < Period)
                Consider(cycleStart + rise);
            if (!constrainToPeriod || rise + Width < Period)
                Consider(cycleStart + rise + Width);
            if (!constrainToPeriod || rise + Width + fall < Period)
                Consider(cycleStart + rise + Width + fall);
        }

        if (Period <= 0.0)
        {
            ConsiderCycle(Delay, constrainToPeriod: false);
            return best;
        }

        var cycle = time < Delay
            ? 0L
            : Math.Max(0L, (long)Math.Floor((time - Delay) / Period));
        for (var cycleOffset = 0; cycleOffset <= 1; cycleOffset++)
        {
            var cycleStart = Delay + (cycle + cycleOffset) * Period;
            ConsiderCycle(cycleStart, constrainToPeriod: true);
        }
        return best;
    }

    internal override bool IsTransitioningAt(double time, double defaultTransition = 0.0)
    {
        var rise = Rise > 0.0 ? Rise : defaultTransition;
        var fall = Fall > 0.0 ? Fall : defaultTransition;
        if (time < Delay)
            return false;
        var local = time - Delay;
        if (Period > 0.0)
            local %= Period;
        if (rise > 0.0 && local < rise)
            return true;
        local -= rise + Width;
        return fall > 0.0 && local >= 0.0 && local < fall;
    }
}

internal sealed record PwlSource(double[] Times, double[] Values) : TransientSource
{
    internal override bool HasInitialBreakpoint => Times[0] == 0.0;

    internal override double CharacteristicTime(double defaultTransition = 0.0)
    {
        var minimum = double.PositiveInfinity;
        for (var index = 1; index < Times.Length; index++)
            if (Values[index] != Values[index - 1] && Times[index] > Times[index - 1])
                minimum = Math.Min(minimum, Times[index] - Times[index - 1]);
        return minimum;
    }

    internal override double ValueAt(double time, double defaultTransition = 0.0)
    {
        if (time < Times[0])
            return Values[0];
        var left = 0;
        while (left + 1 < Times.Length && Times[left + 1] <= time)
            left++;
        if (left + 1 >= Times.Length)
            return Values[left];
        var interval = Times[left + 1] - Times[left];
        if (interval <= 0.0)
            return Values[left + 1];
        var fraction = (time - Times[left]) / interval;
        return Values[left] + fraction * (Values[left + 1] - Values[left]);
    }

    internal override double NextBreakpointAfter(
        double time,
        double tolerance,
        double defaultTransition = 0.0)
    {
        foreach (var candidate in Times)
            if (candidate > time + tolerance)
                return candidate;
        return double.PositiveInfinity;
    }

    internal override bool IsTransitioningAt(double time, double defaultTransition = 0.0)
    {
        if (time < Times[0] || time >= Times[^1])
            return false;
        var left = 0;
        while (left + 1 < Times.Length && Times[left + 1] <= time)
            left++;
        return left + 1 < Times.Length &&
            Times[left + 1] > Times[left] &&
            Values[left + 1] != Values[left];
    }
}

internal sealed record SinSource(
    double Offset,
    double Amplitude,
    double Frequency,
    double Delay,
    double Damping,
    double PhaseDegrees) : TransientSource
{
    internal override bool HasInitialBreakpoint => Delay == 0.0;

    internal override double CharacteristicTime(double defaultTransition = 0.0) =>
        Frequency > 0.0 ? 1.0 / Frequency : double.PositiveInfinity;

    internal override double ValueAt(double time, double defaultTransition = 0.0)
    {
        if (time < Delay)
            return Offset;
        var local = time - Delay;
        var phase = PhaseDegrees * Math.PI / 180.0;
        return Offset + Amplitude * Math.Exp(-Damping * local) *
            Math.Sin(2.0 * Math.PI * Frequency * local + phase);
    }

    internal override double NextBreakpointAfter(
        double time,
        double tolerance,
        double defaultTransition = 0.0) =>
        Delay > time + tolerance ? Delay : double.PositiveInfinity;
}

internal sealed record ExpSource(
    double Initial,
    double Pulsed,
    double RiseDelay,
    double RiseTimeConstant,
    double FallDelay,
    double FallTimeConstant) : TransientSource
{
    internal override bool HasInitialBreakpoint => RiseDelay == 0.0;

    internal override double CharacteristicTime(double defaultTransition = 0.0) =>
        Math.Min(RiseTimeConstant, FallTimeConstant);

    internal override double ValueAt(double time, double defaultTransition = 0.0)
    {
        if (time <= RiseDelay)
            return Initial;
        var value = Initial + (Pulsed - Initial) *
            (1.0 - Math.Exp(-(time - RiseDelay) / RiseTimeConstant));
        if (time > FallDelay)
            value += (Initial - Pulsed) *
                (1.0 - Math.Exp(-(time - FallDelay) / FallTimeConstant));
        return value;
    }

    internal override double NextBreakpointAfter(
        double time,
        double tolerance,
        double defaultTransition = 0.0)
    {
        if (RiseDelay > time + tolerance)
            return RiseDelay;
        if (FallDelay > time + tolerance)
            return FallDelay;
        return double.PositiveInfinity;
    }
}

internal sealed record Analysis(string Kind, double A = 0.0, double B = 0.0, double C = 0.0, string Mode = "");

internal enum IntegrationMethod
{
    Trapezoidal,
    Gear
}

internal sealed record RfmInstance(string Name, string[] Ports, string Reference, RfmModel Model);
internal sealed record DiodeModel(
    string Name,
    double SaturationCurrent,
    double EmissionCoefficient,
    double SeriesResistance,
    double ZeroBiasJunctionCapacitance,
    double JunctionPotential,
    double GradingCoefficient,
    double TransitTime,
    double ForwardBiasCoefficient,
    double? BreakdownVoltage,
    double BreakdownCurrent,
    double BreakdownEmissionCoefficient,
    double? NominalTemperatureCelsius,
    double ActivationEnergy,
    double SaturationCurrentTemperatureExponent,
    double DefaultArea);

internal sealed record DiodeInstanceParameters(
    double? Area,
    double Multiplicity,
    double? TemperatureCelsius,
    double DeltaTemperatureCelsius)
{
    internal double EffectiveArea(DiodeModel model) =>
        (Area ?? model.DefaultArea) * Multiplicity;
    internal DiodeTemperatureParameters TemperatureParameters { get; set; } = null!;
}

internal sealed record DiodeTemperatureParameters(
    double TemperatureKelvin,
    double ThermalVoltage,
    double SaturationCurrent,
    double ZeroBiasJunctionCapacitance,
    double JunctionPotential,
    double TransitTime,
    double? BreakdownVoltage);
internal sealed record BjtModel(
    string Name,
    int Polarity,
    double SaturationCurrent,
    double ForwardBeta,
    double ReverseBeta,
    double ForwardEmissionCoefficient,
    double ReverseEmissionCoefficient,
    double BaseEmitterLeakageSaturationCurrent,
    double BaseCollectorLeakageSaturationCurrent,
    double BaseEmitterLeakageEmissionCoefficient,
    double BaseCollectorLeakageEmissionCoefficient,
    double ForwardEarlyVoltage,
    double ReverseEarlyVoltage,
    double BaseEmitterCapacitance,
    double BaseEmitterPotential,
    double BaseEmitterGradingCoefficient,
    double ForwardTransitTime,
    double BaseCollectorCapacitance,
    double BaseCollectorPotential,
    double BaseCollectorGradingCoefficient,
    double ReverseTransitTime,
    double ForwardBiasCoefficient,
    double ForwardRollOffCurrent,
    double ReverseRollOffCurrent,
    double CollectorResistance,
    double BaseResistance,
    double EmitterResistance,
    double? NominalTemperatureCelsius,
    double ActivationEnergy,
    double SaturationCurrentTemperatureExponent,
    double BetaTemperatureExponent)
{
    internal bool HasDynamicCharge =>
        BaseEmitterCapacitance > 0.0 || BaseCollectorCapacitance > 0.0 ||
        ForwardTransitTime > 0.0 || ReverseTransitTime > 0.0;
}

internal sealed record BjtInstanceParameters(
    double Area,
    double Multiplicity,
    double? TemperatureCelsius,
    double DeltaTemperatureCelsius)
{
    internal BjtTemperatureParameters TemperatureParameters { get; set; } = null!;
}

internal sealed record BjtTemperatureParameters(
    double TemperatureKelvin,
    double ThermalVoltage,
    double SaturationCurrent,
    double BaseEmitterLeakageSaturationCurrent,
    double BaseCollectorLeakageSaturationCurrent,
    double ForwardBeta,
    double ReverseBeta,
    double InverseForwardEarlyVoltage,
    double InverseReverseEarlyVoltage,
    double InverseForwardRollOffCurrent,
    double InverseReverseRollOffCurrent,
    double BaseEmitterCapacitance,
    double BaseEmitterPotential,
    double BaseCollectorCapacitance,
    double BaseCollectorPotential,
    double ForwardTransitTime,
    double ReverseTransitTime);

internal sealed record MosInstanceParameters(
    double Length,
    double Width,
    double DrainArea,
    double SourceArea,
    double DrainPerimeter,
    double SourcePerimeter,
    double DrainSquares,
    double SourceSquares,
    double Multiplicity,
    double? TemperatureCelsius,
    double DeltaTemperatureCelsius)
{
    internal MosTemperatureParameters TemperatureParameters { get; set; } = null!;
}

internal sealed record MosTemperatureParameters(
    double TemperatureKelvin,
    double ThermalVoltage,
    double ThresholdVoltage,
    double Transconductance,
    double BodyEffectCoefficient,
    double SurfacePotential,
    double JunctionSaturationCurrent,
    double JunctionSaturationCurrentDensity,
    double BulkJunctionPotential,
    double BulkDrainCapacitance,
    double BulkSourceCapacitance,
    double BulkCapacitanceFactor,
    double SidewallCapacitanceFactor);

internal sealed record MosSubstrateModelParameters(
    bool ThresholdVoltageGiven,
    bool BodyEffectCoefficientGiven,
    bool SurfacePotentialGiven,
    double? SubstrateDoping,
    int? GateType,
    double? SurfaceStateDensity);

internal sealed record MosModel(
    string Name,
    int Polarity,
    double ThresholdVoltage,
    double Transconductance,
    double BodyEffectCoefficient,
    double SurfacePotential,
    double ChannelLengthModulation,
    double LateralDiffusion,
    double? DrainResistance,
    double? SourceResistance,
    double? SheetResistance,
    double OxideThickness,
    double SurfaceMobility,
    double? NominalTemperatureCelsius,
    MosSubstrateModelParameters Substrate,
    double JunctionSaturationCurrent,
    double JunctionSaturationCurrentDensity,
    double BulkJunctionPotential,
    double BulkDrainCapacitance,
    double BulkSourceCapacitance,
    double BulkCapacitanceFactor,
    double BulkJunctionGradingCoefficient,
    double SidewallCapacitanceFactor,
    double SidewallJunctionGradingCoefficient,
    double GateSourceOverlapCapacitanceFactor,
    double GateDrainOverlapCapacitanceFactor,
    double GateBulkOverlapCapacitanceFactor,
    double ForwardBiasCoefficient)
{
    internal bool HasDynamicCharge =>
        OxideThickness > 0.0 ||
        BulkDrainCapacitance > 0.0 || BulkSourceCapacitance > 0.0 ||
        BulkCapacitanceFactor > 0.0 || SidewallCapacitanceFactor > 0.0 ||
        GateSourceOverlapCapacitanceFactor > 0.0 ||
        GateDrainOverlapCapacitanceFactor > 0.0 ||
        GateBulkOverlapCapacitanceFactor > 0.0;
}

internal sealed class Deck
{
    private static readonly Regex PulsePattern = new(@"PULSE\s*\(([^)]*)\)", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex PwlPattern = new(@"PWL\s*\(([^)]*)\)", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex SinPattern = new(@"SIN\s*\(([^)]*)\)", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex ExpPattern = new(@"EXP\s*\(([^)]*)\)", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex OutputPattern = new(@"[vi]\(\s*([^\s,)]+)", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex ModelPattern = new(@"^\.model\s+(\S+)\s+([^\s(]+)\s*(.*)$", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private readonly HashSet<string> _nodeNames = new(StringComparer.OrdinalIgnoreCase);

    internal List<Element> Elements { get; } = [];
    internal List<RfmInstance> RfmInstances { get; } = [];
    internal Dictionary<string, DiodeModel> DiodeModels { get; } = new(StringComparer.OrdinalIgnoreCase);
    internal Dictionary<string, BjtModel> BjtModels { get; } = new(StringComparer.OrdinalIgnoreCase);
    internal Dictionary<string, MosModel> MosModels { get; } = new(StringComparer.OrdinalIgnoreCase);
    internal List<string> Nodes { get; } = [];
    internal HashSet<string> InternalNodes { get; } = new(StringComparer.OrdinalIgnoreCase);
    internal List<Analysis> Analyses { get; } = [];
    internal Dictionary<string, HashSet<string>> Outputs { get; } = new(StringComparer.OrdinalIgnoreCase);
    internal bool HasDiodes => Elements.Any(element => element.Kind == 'D');
    internal bool HasNonlinearDevices => Elements.Any(element => element.Kind is 'D' or 'Q' or 'M');
    internal double RelativeTolerance { get; private set; } = 1e-3;
    internal double VoltageTolerance { get; private set; } = 1e-6;
    internal double CurrentTolerance { get; private set; } = 1e-12;
    internal double ChargeTolerance { get; private set; } = 1e-14;
    internal double TruncationTolerance { get; private set; } = 7.0;
    internal double TemperatureCelsius { get; private set; } = 27.0;
    internal double NominalTemperatureCelsius { get; private set; } = 27.0;
    internal bool UseTransientPredictor { get; private set; } = true;
    internal IntegrationMethod TransientIntegrationMethod { get; private set; } = IntegrationMethod.Trapezoidal;

    internal static Deck Parse(
        string text,
        RfmModel? rfm = null,
        string rfmSubcircuit = "rfm_direct",
        string? sourcePath = null)
    {
        text = NetlistFlattener.Flatten(text, rfm, rfmSubcircuit, sourcePath);
        var deck = new Deck();
        var firstPhysicalLine = true;
        foreach (var raw in text.Split('\n'))
        {
            var line = raw.Trim();
            if (line.Length == 0)
                continue;
            var tokens = line.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
            if (firstPhysicalLine)
            {
                firstPhysicalLine = false;
                if (!line.StartsWith('*') && !line.StartsWith(';') && !tokens[0].StartsWith('.') && !LooksLikeElement(tokens, line, rfm, rfmSubcircuit))
                    continue;
            }
            if (line.StartsWith('*') || line.StartsWith(';'))
                continue;

            var head = tokens[0].ToLowerInvariant();
            if (head == ".end")
                break;
            if (head == ".model")
            {
                deck.ParseModel(line);
                continue;
            }
            if (head is ".options" or ".option")
            {
                deck.ParseOptions(tokens[1..]);
                continue;
            }
            if (head == ".temp")
            {
                Require(tokens, 2, ".temp temperature");
                if (tokens.Length != 2)
                    throw new InvalidDataException("native .temp accepts one operating temperature");
                deck.TemperatureCelsius = ParseTemperature(tokens[1], ".temp");
                continue;
            }
            if (head == ".op")
            {
                deck.Analyses.Add(new Analysis("op"));
                continue;
            }
            if (head == ".dc")
            {
                Require(tokens, 5, ".dc source start stop step");
                deck.Analyses.Add(new Analysis("dc", ParseNumber(tokens[2]), ParseNumber(tokens[3]), ParseNumber(tokens[4]), tokens[1]));
                continue;
            }
            if (head == ".ac")
            {
                Require(tokens, 5, ".ac lin|dec|oct points start stop");
                var mode = tokens[1].ToLowerInvariant();
                if (mode is not ("lin" or "dec" or "oct"))
                    throw new InvalidDataException($"unsupported .ac mode '{tokens[1]}'");
                deck.Analyses.Add(new Analysis("ac", ParseNumber(tokens[2]), ParseNumber(tokens[3]), ParseNumber(tokens[4]), mode));
                continue;
            }
            if (head == ".tran")
            {
                Require(tokens, 3, ".tran step stop [start]");
                deck.Analyses.Add(new Analysis("tran", ParseNumber(tokens[1]), ParseNumber(tokens[2]), tokens.Length >= 4 ? ParseNumber(tokens[3]) : 0.0));
                continue;
            }
            if (head == ".print" || head == ".probe")
            {
                Require(tokens, 3, ".print analysis expression");
                if (!deck.Outputs.TryGetValue(tokens[1], out var outputs))
                {
                    outputs = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                    deck.Outputs[tokens[1]] = outputs;
                }
                foreach (Match match in OutputPattern.Matches(line))
                    outputs.Add(match.Groups[1].Value);
                continue;
            }
            if (head.StartsWith('.'))
                continue;

            var kind = char.ToUpperInvariant(tokens[0][0]);
            if (kind == 'X')
            {
                if (rfm is null || !tokens[^1].Equals(rfmSubcircuit, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException($"unsupported subcircuit instance '{tokens[0]}'");
                var expected = rfm.Nports + 3;
                if (tokens.Length != expected)
                    throw new InvalidDataException($"{tokens[0]} requires {rfm.Nports} port node(s), one reference node, and model '{rfmSubcircuit}'");
                var ports = tokens[1..(rfm.Nports + 1)];
                var reference = tokens[rfm.Nports + 1];
                deck.RfmInstances.Add(new RfmInstance(tokens[0], ports, reference, rfm));
                foreach (var node in ports.Append(reference))
                    deck.AddNode(node);
                continue;
            }

            var required = kind switch
            {
                'R' or 'C' or 'L' or 'V' or 'I' => 4,
                'D' => 4,
                'Q' => 5,
                'M' => 6,
                'G' or 'E' => 6,
                'F' or 'H' => 5,
                _ => throw new InvalidDataException($"unsupported element '{tokens[0]}'")
            };
            Require(tokens, required, $"{kind} element");
            var nodeCount = kind switch
            {
                'G' or 'E' => 4,
                'M' => 4,
                'Q' => 3,
                _ => 2
            };
            var nodes = tokens[1..(nodeCount + 1)];
            var valueIndex = nodeCount + 1;
            if (kind is 'D' or 'Q' or 'M')
            {
                var mos = kind == 'M'
                    ? ParseMosInstance(tokens[0], tokens[(valueIndex + 1)..])
                    : null;
                var diode = kind == 'D'
                    ? ParseDiodeInstance(tokens[0], tokens[(valueIndex + 1)..])
                    : null;
                var bjt = kind == 'Q'
                    ? ParseBjtInstance(tokens[0], tokens[(valueIndex + 1)..])
                    : null;
                deck.Elements.Add(new Element(
                    tokens[0],
                    kind,
                    nodes,
                    0.0,
                    ModelName: tokens[valueIndex],
                    Mos: mos,
                    Diode: diode,
                    Bjt: bjt));
                foreach (var node in nodes)
                    deck.AddNode(node);
                continue;
            }
            if (kind is 'F' or 'H')
            {
                deck.Elements.Add(new Element(
                    tokens[0],
                    kind,
                    nodes,
                    ParseNumber(tokens[4]),
                    ControlName: tokens[3]));
                foreach (var node in nodes)
                    deck.AddNode(node);
                continue;
            }
            var value = 0.0;
            TransientSource? transientSource = null;
            if (kind is 'V' or 'I')
            {
                (value, transientSource) = ParseSource(line, tokens, valueIndex);
            }
            else
            {
                value = ParseNumber(tokens[valueIndex]);
            }
            var acAmplitude = 0.0;
            var acPhase = 0.0;
            for (var index = valueIndex; index + 1 < tokens.Length; index++)
            {
                if (!tokens[index].Equals("ac", StringComparison.OrdinalIgnoreCase))
                    continue;
                acAmplitude = ParseNumber(tokens[index + 1]);
                acPhase = index + 2 < tokens.Length ? ParseNumber(tokens[index + 2].TrimEnd(')')) : 0.0;
                break;
            }
            deck.Elements.Add(new Element(tokens[0], kind, nodes, value, acAmplitude, acPhase, transientSource));
            foreach (var node in nodes)
                deck.AddNode(node);
        }
        if (deck.Elements.Count == 0 && deck.RfmInstances.Count == 0)
            throw new InvalidDataException("deck contains no supported elements");
        if (deck.Analyses.Count == 0)
            deck.Analyses.Add(new Analysis("op"));
        foreach (var diode in deck.Elements.Where(element => element.Kind == 'D'))
            if (!deck.DiodeModels.ContainsKey(diode.ModelName!))
                throw new InvalidDataException($"{diode.Name} references undefined diode model '{diode.ModelName}'");
        foreach (var bjt in deck.Elements.Where(element => element.Kind == 'Q'))
            if (!deck.BjtModels.ContainsKey(bjt.ModelName!))
                throw new InvalidDataException($"{bjt.Name} references undefined BJT model '{bjt.ModelName}'");
        foreach (var mos in deck.Elements.Where(element => element.Kind == 'M'))
        {
            if (!deck.MosModels.ContainsKey(mos.ModelName!))
                throw new InvalidDataException($"{mos.Name} references undefined MOS model '{mos.ModelName}'");
            if (mos.Mos is not null &&
                mos.Mos.Length <= 2.0 * deck.MosModels[mos.ModelName!].LateralDiffusion)
                throw new InvalidDataException($"{mos.Name} MOS1 effective length must be positive");
        }
        deck.InitializeDiodeTemperatureParameters();
        deck.ExpandDiodeSeriesResistances();
        deck.InitializeBjtTemperatureParameters();
        deck.ExpandBjtSeriesResistances();
        deck.InitializeMosTemperatureParameters();
        deck.ExpandMosSeriesResistances();
        var elementNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var element in deck.Elements)
            if (!elementNames.Add(element.Name))
                throw new InvalidDataException($"duplicate element '{element.Name}'");
        var controllingVoltageSourceNames = deck.Elements
            .Where(element => element.Kind is 'V' or 'E' or 'H')
            .Select(element => element.Name)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (var controlled in deck.Elements.Where(element => element.Kind is 'F' or 'H'))
            if (!controllingVoltageSourceNames.Contains(controlled.ControlName!))
                throw new InvalidDataException(
                    $"{controlled.Name} references undefined controlling voltage source '{controlled.ControlName}'");
        deck.ApplyReverseCuthillMcKeeOrdering();
        var nodeIndices = deck.Nodes
            .Select((node, index) => (node, index))
            .ToDictionary(pair => pair.node, pair => pair.index, StringComparer.OrdinalIgnoreCase);
        foreach (var element in deck.Elements)
            element.NodeIndices = element.Nodes
                .Select(node => node.Equals("0", StringComparison.OrdinalIgnoreCase) ? -1 : nodeIndices[node])
                .ToArray();
        return deck;
    }

    private void ApplyReverseCuthillMcKeeOrdering()
    {
        if (Nodes.Count < 64 ||
            Environment.GetEnvironmentVariable("AGENT_SPICE_NATIVE_DISABLE_NODE_ORDERING") == "1")
            return;
        var nodeIndices = Nodes
            .Select((node, index) => (node, index))
            .ToDictionary(pair => pair.node, pair => pair.index, StringComparer.OrdinalIgnoreCase);
        var adjacency = Enumerable.Range(0, Nodes.Count).Select(_ => new HashSet<int>()).ToArray();
        void Connect(IEnumerable<string> names)
        {
            var indices = names
                .Where(name => !name.Equals("0", StringComparison.OrdinalIgnoreCase))
                .Select(name => nodeIndices[name])
                .Distinct()
                .ToArray();
            for (var left = 0; left < indices.Length; left++)
                for (var right = left + 1; right < indices.Length; right++)
                {
                    adjacency[indices[left]].Add(indices[right]);
                    adjacency[indices[right]].Add(indices[left]);
                }
        }
        foreach (var element in Elements)
            Connect(element.Nodes);
        foreach (var instance in RfmInstances)
            Connect(instance.Ports.Append(instance.Reference));

        var visited = new bool[Nodes.Count];
        var traversal = new List<int>(Nodes.Count);
        var starts = Enumerable.Range(0, Nodes.Count)
            .OrderBy(index => adjacency[index].Count)
            .ThenBy(index => index)
            .ToArray();
        var queue = new Queue<int>();
        foreach (var start in starts)
        {
            if (visited[start])
                continue;
            visited[start] = true;
            queue.Enqueue(start);
            while (queue.Count > 0)
            {
                var current = queue.Dequeue();
                traversal.Add(current);
                foreach (var neighbor in adjacency[current]
                    .Where(index => !visited[index])
                    .OrderBy(index => adjacency[index].Count)
                    .ThenBy(index => index))
                {
                    visited[neighbor] = true;
                    queue.Enqueue(neighbor);
                }
            }
        }
        traversal.Reverse();
        var orderedNodes = traversal.Select(index => Nodes[index]).ToArray();
        Nodes.Clear();
        Nodes.AddRange(orderedNodes);
    }

    private void ParseModel(string line)
    {
        var match = ModelPattern.Match(line);
        if (!match.Success)
            throw new InvalidDataException($"unsupported .model syntax '{line}'");
        var name = match.Groups[1].Value;
        var modelType = match.Groups[2].Value.ToLowerInvariant();
        if (DiodeModels.ContainsKey(name) || BjtModels.ContainsKey(name) || MosModels.ContainsKey(name))
            throw new InvalidDataException($"duplicate model '{name}'");
        var parameters = match.Groups[3].Value.Trim().TrimStart('(').TrimEnd(')')
            .Split([',', ' ', '\t'], StringSplitOptions.RemoveEmptyEntries);
        if (modelType is "npn" or "pnp")
        {
            ParseBjtModel(name, modelType == "npn" ? 1 : -1, parameters);
            return;
        }
        if (modelType is "nmos" or "pmos")
        {
            ParseMosModel(name, modelType == "nmos" ? 1 : -1, parameters);
            return;
        }
        if (modelType != "d")
            throw new InvalidDataException($"unsupported model type '{match.Groups[2].Value}'");
        var saturationCurrent = 1e-14;
        var emissionCoefficient = 1.0;
        var seriesResistance = 0.0;
        var zeroBiasJunctionCapacitance = 0.0;
        var junctionPotential = 1.0;
        var gradingCoefficient = 0.5;
        var transitTime = 0.0;
        var forwardBiasCoefficient = 0.5;
        double? breakdownVoltage = null;
        var breakdownCurrent = 1e-3;
        double? breakdownEmissionCoefficient = null;
        double? nominalTemperatureCelsius = null;
        var activationEnergy = 1.11;
        var saturationCurrentTemperatureExponent = 3.0;
        var defaultArea = 1.0;
        foreach (var parameter in parameters)
        {
            var pair = parameter.Split('=', 2);
            if (pair.Length != 2)
                throw new InvalidDataException($"invalid diode model parameter '{parameter}'");
            switch (pair[0].ToLowerInvariant())
            {
                case "is": saturationCurrent = ParseNumber(pair[1]); break;
                case "n": emissionCoefficient = ParseNumber(pair[1]); break;
                case "rs": seriesResistance = ParseNumber(pair[1]); break;
                case "cjo" or "cj0": zeroBiasJunctionCapacitance = ParseNumber(pair[1]); break;
                case "vj": junctionPotential = ParseNumber(pair[1]); break;
                case "m": gradingCoefficient = ParseNumber(pair[1]); break;
                case "tt": transitTime = ParseNumber(pair[1]); break;
                case "fc": forwardBiasCoefficient = ParseNumber(pair[1]); break;
                case "bv": breakdownVoltage = ParseNumber(pair[1]); break;
                case "ibv": breakdownCurrent = ParseNumber(pair[1]); break;
                case "nbv": breakdownEmissionCoefficient = ParseNumber(pair[1]); break;
                case "tnom": nominalTemperatureCelsius = ParseTemperature(pair[1], $"diode model '{name}' TNOM"); break;
                case "eg": activationEnergy = ParseNumber(pair[1]); break;
                case "xti": saturationCurrentTemperatureExponent = ParseNumber(pair[1]); break;
                case "area": defaultArea = ParseNumber(pair[1]); break;
                default: throw new InvalidDataException($"unsupported diode model parameter '{pair[0]}'");
            }
        }
        if (saturationCurrent <= 0.0 || emissionCoefficient <= 0.0 || junctionPotential <= 0.0)
            throw new InvalidDataException("diode IS, N, and VJ must be positive");
        if (seriesResistance < 0.0 || zeroBiasJunctionCapacitance < 0.0 || transitTime < 0.0)
            throw new InvalidDataException("diode RS, CJO, and TT must be non-negative");
        if (gradingCoefficient < 0.0 || gradingCoefficient >= 1.0)
            throw new InvalidDataException("diode M must be in the range [0, 1)");
        if (forwardBiasCoefficient <= 0.0 || forwardBiasCoefficient >= 1.0)
            throw new InvalidDataException("diode FC must be in the range (0, 1)");
        if ((breakdownVoltage.HasValue && breakdownVoltage.Value <= 0.0) ||
            breakdownCurrent <= 0.0 ||
            (breakdownEmissionCoefficient.HasValue && breakdownEmissionCoefficient.Value <= 0.0))
            throw new InvalidDataException("diode BV, IBV, and NBV must be positive");
        if (activationEnergy < 0.1 || defaultArea <= 0.0)
            throw new InvalidDataException("diode EG must be at least 0.1 and AREA must be positive");
        DiodeModels[name] = new DiodeModel(
            name,
            saturationCurrent,
            emissionCoefficient,
            seriesResistance,
            zeroBiasJunctionCapacitance,
            junctionPotential,
            gradingCoefficient,
            transitTime,
            forwardBiasCoefficient,
            breakdownVoltage,
            breakdownCurrent,
            breakdownEmissionCoefficient ?? emissionCoefficient,
            nominalTemperatureCelsius,
            activationEnergy,
            saturationCurrentTemperatureExponent,
            defaultArea);
    }

    private void ParseBjtModel(string name, int polarity, IEnumerable<string> parameters)
    {
        var saturationCurrent = 1e-16;
        var forwardBeta = 100.0;
        var reverseBeta = 1.0;
        var forwardEmissionCoefficient = 1.0;
        var reverseEmissionCoefficient = 1.0;
        var baseEmitterLeakageSaturationCurrent = 0.0;
        var baseCollectorLeakageSaturationCurrent = 0.0;
        var baseEmitterLeakageEmissionCoefficient = 1.5;
        var baseCollectorLeakageEmissionCoefficient = 2.0;
        var forwardEarlyVoltage = 0.0;
        var reverseEarlyVoltage = 0.0;
        var baseEmitterCapacitance = 0.0;
        var baseEmitterPotential = 0.75;
        var baseEmitterGradingCoefficient = 0.33;
        var forwardTransitTime = 0.0;
        var baseCollectorCapacitance = 0.0;
        var baseCollectorPotential = 0.75;
        var baseCollectorGradingCoefficient = 0.33;
        var reverseTransitTime = 0.0;
        var forwardBiasCoefficient = 0.5;
        var forwardRollOffCurrent = 0.0;
        var reverseRollOffCurrent = 0.0;
        var collectorResistance = 0.0;
        var baseResistance = 0.0;
        var emitterResistance = 0.0;
        double? nominalTemperatureCelsius = null;
        var activationEnergy = 1.11;
        var saturationCurrentTemperatureExponent = 3.0;
        var betaTemperatureExponent = 0.0;
        foreach (var parameter in parameters)
        {
            var pair = parameter.Split('=', 2);
            if (pair.Length != 2)
                throw new InvalidDataException($"invalid BJT model parameter '{parameter}'");
            switch (pair[0].ToLowerInvariant())
            {
                case "is": saturationCurrent = ParseNumber(pair[1]); break;
                case "bf": forwardBeta = ParseNumber(pair[1]); break;
                case "br": reverseBeta = ParseNumber(pair[1]); break;
                case "nf": forwardEmissionCoefficient = ParseNumber(pair[1]); break;
                case "nr": reverseEmissionCoefficient = ParseNumber(pair[1]); break;
                case "ise": baseEmitterLeakageSaturationCurrent = ParseNumber(pair[1]); break;
                case "isc": baseCollectorLeakageSaturationCurrent = ParseNumber(pair[1]); break;
                case "ne": baseEmitterLeakageEmissionCoefficient = ParseNumber(pair[1]); break;
                case "nc": baseCollectorLeakageEmissionCoefficient = ParseNumber(pair[1]); break;
                case "vaf" or "va": forwardEarlyVoltage = ParseNumber(pair[1]); break;
                case "var" or "vb": reverseEarlyVoltage = ParseNumber(pair[1]); break;
                case "cje": baseEmitterCapacitance = ParseNumber(pair[1]); break;
                case "vje" or "pe": baseEmitterPotential = ParseNumber(pair[1]); break;
                case "mje" or "me": baseEmitterGradingCoefficient = ParseNumber(pair[1]); break;
                case "tf": forwardTransitTime = ParseNumber(pair[1]); break;
                case "cjc": baseCollectorCapacitance = ParseNumber(pair[1]); break;
                case "vjc" or "pc": baseCollectorPotential = ParseNumber(pair[1]); break;
                case "mjc" or "mc": baseCollectorGradingCoefficient = ParseNumber(pair[1]); break;
                case "tr": reverseTransitTime = ParseNumber(pair[1]); break;
                case "fc": forwardBiasCoefficient = ParseNumber(pair[1]); break;
                case "ikf" or "ik": forwardRollOffCurrent = ParseNumber(pair[1]); break;
                case "ikr": reverseRollOffCurrent = ParseNumber(pair[1]); break;
                case "rc": collectorResistance = ParseNumber(pair[1]); break;
                case "rb": baseResistance = ParseNumber(pair[1]); break;
                case "re": emitterResistance = ParseNumber(pair[1]); break;
                case "tnom": nominalTemperatureCelsius = ParseTemperature(pair[1], $"BJT model '{name}' TNOM"); break;
                case "eg": activationEnergy = ParseNumber(pair[1]); break;
                case "xti": saturationCurrentTemperatureExponent = ParseNumber(pair[1]); break;
                case "xtb": betaTemperatureExponent = ParseNumber(pair[1]); break;
                default: throw new InvalidDataException($"unsupported BJT model parameter '{pair[0]}'");
            }
        }
        if (saturationCurrent <= 0.0 || forwardBeta <= 0.0 || reverseBeta <= 0.0 ||
            forwardEmissionCoefficient <= 0.0 || reverseEmissionCoefficient <= 0.0)
            throw new InvalidDataException("BJT IS, BF, BR, NF, and NR must be positive");
        if (baseEmitterLeakageSaturationCurrent < 0.0 ||
            baseCollectorLeakageSaturationCurrent < 0.0)
            throw new InvalidDataException("BJT ISE and ISC must be non-negative");
        if (baseEmitterLeakageEmissionCoefficient <= 0.0 ||
            baseCollectorLeakageEmissionCoefficient <= 0.0)
            throw new InvalidDataException("BJT NE and NC must be positive");
        if (forwardEarlyVoltage < 0.0 || reverseEarlyVoltage < 0.0)
            throw new InvalidDataException("BJT VAF and VAR must be non-negative");
        if (baseEmitterCapacitance < 0.0 || baseCollectorCapacitance < 0.0 ||
            forwardTransitTime < 0.0 || reverseTransitTime < 0.0)
            throw new InvalidDataException("BJT CJE, CJC, TF, and TR must be non-negative");
        if (baseEmitterPotential <= 0.0 || baseCollectorPotential <= 0.0)
            throw new InvalidDataException("BJT VJE and VJC must be positive");
        if (baseEmitterGradingCoefficient < 0.0 || baseEmitterGradingCoefficient >= 1.0 ||
            baseCollectorGradingCoefficient < 0.0 || baseCollectorGradingCoefficient >= 1.0)
            throw new InvalidDataException("BJT MJE and MJC must be in the range [0, 1)");
        if (forwardBiasCoefficient <= 0.0 || forwardBiasCoefficient >= 1.0)
            throw new InvalidDataException("BJT FC must be in the range (0, 1)");
        if (forwardRollOffCurrent < 0.0 || reverseRollOffCurrent < 0.0 ||
            collectorResistance < 0.0 || baseResistance < 0.0 || emitterResistance < 0.0)
            throw new InvalidDataException("BJT IKF, IKR, RC, RB, and RE must be non-negative");
        if (activationEnergy < 0.1)
            throw new InvalidDataException("BJT EG must be at least 0.1");
        BjtModels[name] = new BjtModel(
            name,
            polarity,
            saturationCurrent,
            forwardBeta,
            reverseBeta,
            forwardEmissionCoefficient,
            reverseEmissionCoefficient,
            baseEmitterLeakageSaturationCurrent,
            baseCollectorLeakageSaturationCurrent,
            baseEmitterLeakageEmissionCoefficient,
            baseCollectorLeakageEmissionCoefficient,
            forwardEarlyVoltage,
            reverseEarlyVoltage,
            baseEmitterCapacitance,
            baseEmitterPotential,
            baseEmitterGradingCoefficient,
            forwardTransitTime,
            baseCollectorCapacitance,
            baseCollectorPotential,
            baseCollectorGradingCoefficient,
            reverseTransitTime,
            forwardBiasCoefficient,
            forwardRollOffCurrent,
            reverseRollOffCurrent,
            collectorResistance,
            baseResistance,
            emitterResistance,
            nominalTemperatureCelsius,
            activationEnergy,
            saturationCurrentTemperatureExponent,
            betaTemperatureExponent);
    }

    private void ParseMosModel(string name, int polarity, IEnumerable<string> parameters)
    {
        var thresholdVoltage = 0.0;
        var thresholdVoltageGiven = false;
        var transconductance = 2e-5;
        var transconductanceGiven = false;
        var bodyEffectCoefficient = 0.0;
        var bodyEffectCoefficientGiven = false;
        var surfacePotential = 0.6;
        var surfacePotentialGiven = false;
        var channelLengthModulation = 0.0;
        var lateralDiffusion = 0.0;
        double? drainResistance = null;
        double? sourceResistance = null;
        double? sheetResistance = null;
        var oxideThickness = 0.0;
        var surfaceMobility = 600.0;
        double? nominalTemperatureCelsius = null;
        double? substrateDoping = null;
        int? gateType = null;
        double? surfaceStateDensity = null;
        var junctionSaturationCurrent = 1e-14;
        var junctionSaturationCurrentDensity = 0.0;
        var bulkJunctionPotential = 0.8;
        var bulkDrainCapacitance = 0.0;
        var bulkSourceCapacitance = 0.0;
        var bulkCapacitanceFactor = 0.0;
        var bulkJunctionGradingCoefficient = 0.5;
        var sidewallCapacitanceFactor = 0.0;
        var sidewallJunctionGradingCoefficient = 0.5;
        var gateSourceOverlapCapacitanceFactor = 0.0;
        var gateDrainOverlapCapacitanceFactor = 0.0;
        var gateBulkOverlapCapacitanceFactor = 0.0;
        var forwardBiasCoefficient = 0.5;
        foreach (var parameter in parameters)
        {
            var pair = parameter.Split('=', 2);
            if (pair.Length != 2)
                throw new InvalidDataException($"invalid MOS1 model parameter '{parameter}'");
            var value = ParseNumber(pair[1]);
            switch (pair[0].ToLowerInvariant())
            {
                case "level":
                    if (value != 1.0)
                        throw new InvalidDataException($"MOS model '{name}' requires LEVEL=1");
                    break;
                case "vto" or "vt0":
                    thresholdVoltage = value;
                    thresholdVoltageGiven = true;
                    break;
                case "kp":
                    transconductance = value;
                    transconductanceGiven = true;
                    break;
                case "gamma":
                    bodyEffectCoefficient = value;
                    bodyEffectCoefficientGiven = true;
                    break;
                case "phi":
                    surfacePotential = value;
                    surfacePotentialGiven = true;
                    break;
                case "lambda": channelLengthModulation = value; break;
                case "ld": lateralDiffusion = value; break;
                case "rd": drainResistance = value; break;
                case "rs": sourceResistance = value; break;
                case "rsh": sheetResistance = value; break;
                case "tox": oxideThickness = value; break;
                case "uo" or "u0": surfaceMobility = value; break;
                case "tnom": nominalTemperatureCelsius = value; break;
                case "nsub": substrateDoping = value; break;
                case "tpg":
                    if (value is not (-1.0 or 0.0 or 1.0))
                        throw new InvalidDataException("MOS1 TPG must be -1, 0, or 1");
                    gateType = (int)value;
                    break;
                case "nss": surfaceStateDensity = value; break;
                case "is": junctionSaturationCurrent = value; break;
                case "js": junctionSaturationCurrentDensity = value; break;
                case "pb": bulkJunctionPotential = value; break;
                case "cbd": bulkDrainCapacitance = value; break;
                case "cbs": bulkSourceCapacitance = value; break;
                case "cj": bulkCapacitanceFactor = value; break;
                case "mj": bulkJunctionGradingCoefficient = value; break;
                case "cjsw": sidewallCapacitanceFactor = value; break;
                case "mjsw": sidewallJunctionGradingCoefficient = value; break;
                case "cgso": gateSourceOverlapCapacitanceFactor = value; break;
                case "cgdo": gateDrainOverlapCapacitanceFactor = value; break;
                case "cgbo": gateBulkOverlapCapacitanceFactor = value; break;
                case "fc": forwardBiasCoefficient = value; break;
                default: throw new InvalidDataException($"unsupported MOS1 model parameter '{pair[0]}'");
            }
        }
        if (!transconductanceGiven && oxideThickness > 0.0)
        {
            const double siliconDioxidePermittivity = 3.9 * 8.854214871e-12;
            transconductance = surfaceMobility *
                (siliconDioxidePermittivity / oxideThickness) * 1e-4;
        }
        if (transconductance <= 0.0 || surfacePotential <= 0.0 ||
            surfaceMobility <= 0.0 || junctionSaturationCurrent <= 0.0 ||
            bulkJunctionPotential <= 0.0)
            throw new InvalidDataException("MOS1 KP, UO, PHI, IS, and PB must be positive");
        if (bodyEffectCoefficient < 0.0 || channelLengthModulation < 0.0 || lateralDiffusion < 0.0 ||
            junctionSaturationCurrentDensity < 0.0)
            throw new InvalidDataException("MOS1 GAMMA, LAMBDA, LD, and JS must be non-negative");
        if (drainResistance < 0.0 || sourceResistance < 0.0 || sheetResistance < 0.0 ||
            oxideThickness < 0.0)
            throw new InvalidDataException("MOS1 RD, RS, RSH, and TOX must be non-negative");
        if (nominalTemperatureCelsius <= -273.15)
            throw new InvalidDataException("MOS1 TNOM must be above absolute zero");
        if (substrateDoping <= 0.0 || surfaceStateDensity < 0.0)
            throw new InvalidDataException("MOS1 NSUB must be positive and NSS must be non-negative");
        if (bulkDrainCapacitance < 0.0 || bulkSourceCapacitance < 0.0 ||
            bulkCapacitanceFactor < 0.0 || sidewallCapacitanceFactor < 0.0 ||
            gateSourceOverlapCapacitanceFactor < 0.0 ||
            gateDrainOverlapCapacitanceFactor < 0.0 ||
            gateBulkOverlapCapacitanceFactor < 0.0)
            throw new InvalidDataException("MOS1 capacitance parameters must be non-negative");
        if (bulkJunctionGradingCoefficient < 0.0 || bulkJunctionGradingCoefficient >= 1.0 ||
            sidewallJunctionGradingCoefficient < 0.0 || sidewallJunctionGradingCoefficient >= 1.0)
            throw new InvalidDataException("MOS1 MJ and MJSW must be in the range [0, 1)");
        if (forwardBiasCoefficient <= 0.0 || forwardBiasCoefficient >= 1.0)
            throw new InvalidDataException("MOS1 FC must be in the range (0, 1)");
        MosModels[name] = new MosModel(
            name,
            polarity,
            thresholdVoltage,
            transconductance,
            bodyEffectCoefficient,
            surfacePotential,
            channelLengthModulation,
            lateralDiffusion,
            drainResistance,
            sourceResistance,
            sheetResistance,
            oxideThickness,
            surfaceMobility,
            nominalTemperatureCelsius,
            new MosSubstrateModelParameters(
                thresholdVoltageGiven,
                bodyEffectCoefficientGiven,
                surfacePotentialGiven,
                substrateDoping,
                gateType,
                surfaceStateDensity),
            junctionSaturationCurrent,
            junctionSaturationCurrentDensity,
            bulkJunctionPotential,
            bulkDrainCapacitance,
            bulkSourceCapacitance,
            bulkCapacitanceFactor,
            bulkJunctionGradingCoefficient,
            sidewallCapacitanceFactor,
            sidewallJunctionGradingCoefficient,
            gateSourceOverlapCapacitanceFactor,
            gateDrainOverlapCapacitanceFactor,
            gateBulkOverlapCapacitanceFactor,
            forwardBiasCoefficient);
    }

    private static BjtInstanceParameters ParseBjtInstance(
        string name,
        IEnumerable<string> parameters)
    {
        var area = 1.0;
        var areaGiven = false;
        var multiplicity = 1.0;
        double? temperatureCelsius = null;
        var deltaTemperatureCelsius = 0.0;
        foreach (var parameter in parameters)
        {
            var pair = parameter.Split('=', 2);
            if (pair.Length == 1)
            {
                if (parameter.Equals("off", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException(
                        $"unsupported BJT instance parameter 'OFF' on '{name}'");
                if (areaGiven)
                    throw new InvalidDataException(
                        $"multiple positional BJT AREA values on '{name}'");
                area = ParseNumber(parameter);
                areaGiven = true;
                continue;
            }
            var value = pair[0].Equals("temp", StringComparison.OrdinalIgnoreCase)
                ? ParseTemperature(pair[1], $"BJT instance '{name}' TEMP")
                : ParseNumber(pair[1]);
            switch (pair[0].ToLowerInvariant())
            {
                case "area": area = value; areaGiven = true; break;
                case "m": multiplicity = value; break;
                case "temp": temperatureCelsius = value; break;
                case "dtemp": deltaTemperatureCelsius = value; break;
                default:
                    throw new InvalidDataException(
                    $"unsupported BJT instance parameter '{pair[0]}' on '{name}'");
            }
        }
        if (area <= 0.0 || multiplicity <= 0.0)
            throw new InvalidDataException($"BJT AREA and M must be positive on '{name}'");
        return new BjtInstanceParameters(
            area,
            multiplicity,
            temperatureCelsius,
            deltaTemperatureCelsius);
    }

    private static DiodeInstanceParameters ParseDiodeInstance(
        string name,
        IEnumerable<string> parameters)
    {
        double? area = null;
        var multiplicity = 1.0;
        double? temperatureCelsius = null;
        var deltaTemperatureCelsius = 0.0;
        foreach (var parameter in parameters)
        {
            var pair = parameter.Split('=', 2);
            if (pair.Length == 1)
            {
                if (parameter.Equals("off", StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException(
                        $"unsupported diode instance parameter 'OFF' on '{name}'");
                if (area.HasValue)
                    throw new InvalidDataException(
                        $"multiple positional diode AREA values on '{name}'");
                area = ParseNumber(parameter);
                continue;
            }
            var value = pair[0].Equals("temp", StringComparison.OrdinalIgnoreCase)
                ? ParseTemperature(pair[1], $"diode instance '{name}' TEMP")
                : ParseNumber(pair[1]);
            switch (pair[0].ToLowerInvariant())
            {
                case "area": area = value; break;
                case "m": multiplicity = value; break;
                case "temp": temperatureCelsius = value; break;
                case "dtemp": deltaTemperatureCelsius = value; break;
                default:
                    throw new InvalidDataException(
                    $"unsupported diode instance parameter '{pair[0]}' on '{name}'");
            }
        }
        if ((area.HasValue && area.Value <= 0.0) || multiplicity <= 0.0)
            throw new InvalidDataException($"diode AREA and M must be positive on '{name}'");
        return new DiodeInstanceParameters(
            area,
            multiplicity,
            temperatureCelsius,
            deltaTemperatureCelsius);
    }

    private static MosInstanceParameters ParseMosInstance(string name, IEnumerable<string> parameters)
    {
        var length = 100e-6;
        var width = 100e-6;
        var drainArea = 0.0;
        var sourceArea = 0.0;
        var drainPerimeter = 0.0;
        var sourcePerimeter = 0.0;
        var drainSquares = 1.0;
        var sourceSquares = 1.0;
        var multiplicity = 1.0;
        double? temperatureCelsius = null;
        var deltaTemperatureCelsius = 0.0;
        foreach (var parameter in parameters)
        {
            var pair = parameter.Split('=', 2);
            if (pair.Length != 2)
                throw new InvalidDataException($"invalid MOS1 instance parameter '{parameter}' on '{name}'");
            var value = ParseNumber(pair[1]);
            switch (pair[0].ToLowerInvariant())
            {
                case "l": length = value; break;
                case "w": width = value; break;
                case "ad": drainArea = value; break;
                case "as": sourceArea = value; break;
                case "pd": drainPerimeter = value; break;
                case "ps": sourcePerimeter = value; break;
                case "nrd": drainSquares = value; break;
                case "nrs": sourceSquares = value; break;
                case "m": multiplicity = value; break;
                case "temp": temperatureCelsius = value; break;
                case "dtemp": deltaTemperatureCelsius = value; break;
                default: throw new InvalidDataException($"unsupported MOS1 instance parameter '{pair[0]}'");
            }
        }
        if (length <= 0.0 || width <= 0.0 || multiplicity <= 0.0)
            throw new InvalidDataException($"MOS1 L, W, and M must be positive on '{name}'");
        if (drainArea < 0.0 || sourceArea < 0.0 || drainPerimeter < 0.0 ||
            sourcePerimeter < 0.0 || drainSquares < 0.0 || sourceSquares < 0.0)
            throw new InvalidDataException($"MOS1 AD, AS, PD, PS, NRD, and NRS must be non-negative on '{name}'");
        if (temperatureCelsius <= -273.15)
            throw new InvalidDataException($"MOS1 TEMP must be above absolute zero on '{name}'");
        return new MosInstanceParameters(
            length,
            width,
            drainArea,
            sourceArea,
            drainPerimeter,
            sourcePerimeter,
            drainSquares,
            sourceSquares,
            multiplicity,
            temperatureCelsius,
            deltaTemperatureCelsius);
    }

    private void InitializeDiodeTemperatureParameters()
    {
        foreach (var diode in Elements.Where(element => element.Kind == 'D'))
        {
            var model = DiodeModels[diode.ModelName!];
            var instance = diode.Diode!;
            var nominalTemperature = (model.NominalTemperatureCelsius ??
                NominalTemperatureCelsius) + 273.15;
            var operatingTemperature = (instance.TemperatureCelsius ??
                (TemperatureCelsius + instance.DeltaTemperatureCelsius)) + 273.15;
            if (operatingTemperature <= 0.0)
                throw new InvalidDataException(
                    $"diode operating temperature must be above absolute zero on '{diode.Name}'");
            instance.TemperatureParameters = EvaluateDiodeTemperature(
                model,
                instance.EffectiveArea(model),
                nominalTemperature,
                operatingTemperature,
                RelativeTolerance);
        }
    }

    private void InitializeBjtTemperatureParameters()
    {
        foreach (var bjt in Elements.Where(element => element.Kind == 'Q'))
        {
            var model = BjtModels[bjt.ModelName!];
            var instance = bjt.Bjt!;
            var nominalTemperature = (model.NominalTemperatureCelsius ??
                NominalTemperatureCelsius) + 273.15;
            var operatingTemperature = (instance.TemperatureCelsius ??
                (TemperatureCelsius + instance.DeltaTemperatureCelsius)) + 273.15;
            if (operatingTemperature <= 0.0)
                throw new InvalidDataException(
                    $"BJT operating temperature must be above absolute zero on '{bjt.Name}'");
            instance.TemperatureParameters = EvaluateBjtTemperature(
                model,
                instance.Area,
                nominalTemperature,
                operatingTemperature);
        }
    }

    private static BjtTemperatureParameters EvaluateBjtTemperature(
        BjtModel model,
        double area,
        double nominalTemperature,
        double operatingTemperature)
    {
        const double referenceTemperature = 300.15;
        const double boltzmannConstant = 1.380649e-23;
        const double electronCharge = 1.602176634e-19;
        const double boltzmannOverCharge = boltzmannConstant / electronCharge;

        static double PotentialCorrection(double temperature, double thermalVoltage)
        {
            const double referenceTemperature = 300.15;
            const double boltzmannConstant = 1.380649e-23;
            const double electronCharge = 1.602176634e-19;
            var bandgap = 1.16 - 7.02e-4 * temperature * temperature / (temperature + 1108.0);
            var argument = -bandgap / (2.0 * boltzmannConstant * temperature) +
                1.1150877 / (2.0 * boltzmannConstant * referenceTemperature);
            return -2.0 * thermalVoltage * (
                1.5 * Math.Log(temperature / referenceTemperature) +
                electronCharge * argument);
        }

        var nominalThermalVoltage = boltzmannOverCharge * nominalTemperature;
        var thermalVoltage = boltzmannOverCharge * operatingTemperature;
        var temperatureRatio = operatingTemperature / nominalTemperature;
        var ratioLog = Math.Log(temperatureRatio);
        var saturationExponent = (temperatureRatio - 1.0) * model.ActivationEnergy /
            thermalVoltage + model.SaturationCurrentTemperatureExponent * ratioLog;
        var saturationCurrent = model.SaturationCurrent * area *
            Math.Exp(Math.Clamp(saturationExponent, -700.0, 700.0));
        var betaScale = Math.Exp(Math.Clamp(
            ratioLog * model.BetaTemperatureExponent,
            -700.0,
            700.0));
        var baseEmitterLeakageSaturationCurrent =
            model.BaseEmitterLeakageSaturationCurrent * area / betaScale *
            Math.Exp(Math.Clamp(
                saturationExponent / model.BaseEmitterLeakageEmissionCoefficient,
                -700.0,
                700.0));
        var baseCollectorLeakageSaturationCurrent =
            model.BaseCollectorLeakageSaturationCurrent * area / betaScale *
            Math.Exp(Math.Clamp(
                saturationExponent / model.BaseCollectorLeakageEmissionCoefficient,
                -700.0,
                700.0));
        var nominalPotentialCorrection = PotentialCorrection(
            nominalTemperature,
            nominalThermalVoltage);
        var operatingPotentialCorrection = PotentialCorrection(
            operatingTemperature,
            thermalVoltage);
        var nominalFactor = nominalTemperature / referenceTemperature;
        var operatingFactor = operatingTemperature / referenceTemperature;

        (double Capacitance, double Potential) ScaleJunction(
            double modelCapacitance,
            double modelPotential,
            double gradingCoefficient)
        {
            var basePotential = (modelPotential - nominalPotentialCorrection) / nominalFactor;
            var nominalShift = (modelPotential - basePotential) / basePotential;
            var capacitance = modelCapacitance * area /
                (1.0 + gradingCoefficient * (
                    4e-4 * (nominalTemperature - referenceTemperature) - nominalShift));
            var potential = operatingFactor * basePotential + operatingPotentialCorrection;
            var operatingShift = (potential - basePotential) / basePotential;
            capacitance *= 1.0 + gradingCoefficient * (
                4e-4 * (operatingTemperature - referenceTemperature) - operatingShift);
            if (potential <= 0.0 || capacitance < 0.0)
                throw new InvalidDataException(
                    $"BJT temperature adjustment is invalid for model '{model.Name}'");
            return (capacitance, potential);
        }

        var baseEmitter = ScaleJunction(
            model.BaseEmitterCapacitance,
            model.BaseEmitterPotential,
            model.BaseEmitterGradingCoefficient);
        var baseCollector = ScaleJunction(
            model.BaseCollectorCapacitance,
            model.BaseCollectorPotential,
            model.BaseCollectorGradingCoefficient);
        return new BjtTemperatureParameters(
            operatingTemperature,
            thermalVoltage,
            saturationCurrent,
            baseEmitterLeakageSaturationCurrent,
            baseCollectorLeakageSaturationCurrent,
            model.ForwardBeta * betaScale,
            model.ReverseBeta * betaScale,
            model.ForwardEarlyVoltage > 0.0 ? 1.0 / model.ForwardEarlyVoltage : 0.0,
            model.ReverseEarlyVoltage > 0.0 ? 1.0 / model.ReverseEarlyVoltage : 0.0,
            model.ForwardRollOffCurrent > 0.0
                ? 1.0 / (model.ForwardRollOffCurrent * area)
                : 0.0,
            model.ReverseRollOffCurrent > 0.0
                ? 1.0 / (model.ReverseRollOffCurrent * area)
                : 0.0,
            baseEmitter.Capacitance,
            baseEmitter.Potential,
            baseCollector.Capacitance,
            baseCollector.Potential,
            model.ForwardTransitTime,
            model.ReverseTransitTime);
    }

    private void ExpandBjtSeriesResistances()
    {
        var occupiedElementNames = Elements
            .Select(element => element.Name)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        var originalCount = Elements.Count;
        for (var index = 0; index < originalCount; index++)
        {
            var bjt = Elements[index];
            if (bjt.Kind != 'Q')
                continue;
            var model = BjtModels[bjt.ModelName!];
            var instance = bjt.Bjt!;
            var nodes = bjt.Nodes.ToArray();
            AddSeriesResistance(0, "collector", model.CollectorResistance);
            AddSeriesResistance(1, "base", model.BaseResistance);
            AddSeriesResistance(2, "emitter", model.EmitterResistance);
            Elements[index] = bjt with { Nodes = nodes };

            void AddSeriesResistance(int terminal, string terminalName, double resistance)
            {
                if (resistance <= 0.0)
                    return;
                var externalNode = nodes[terminal];
                var internalNode = UniqueInternalName(
                    $"__agent_spice_{bjt.Name}_{terminalName}",
                    _nodeNames);
                _nodeNames.Add(internalNode);
                Nodes.Add(internalNode);
                InternalNodes.Add(internalNode);
                nodes[terminal] = internalNode;
                var resistorName = UniqueInternalName(
                    $"__agent_spice_{bjt.Name}_r{terminalName[0]}",
                    occupiedElementNames);
                occupiedElementNames.Add(resistorName);
                Elements.Add(new Element(
                    resistorName,
                    'R',
                    [externalNode, internalNode],
                    resistance / (instance.Area * instance.Multiplicity)));
            }
        }
    }

    private static DiodeTemperatureParameters EvaluateDiodeTemperature(
        DiodeModel model,
        double effectiveArea,
        double nominalTemperature,
        double operatingTemperature,
        double relativeTolerance)
    {
        const double referenceTemperature = 300.15;
        const double boltzmannConstant = 1.380649e-23;
        const double electronCharge = 1.602176634e-19;
        const double boltzmannOverCharge = boltzmannConstant / electronCharge;

        static double PotentialCorrection(double temperature, double thermalVoltage)
        {
            const double referenceTemperature = 300.15;
            const double boltzmannConstant = 1.380649e-23;
            const double electronCharge = 1.602176634e-19;
            var bandgap = 1.16 - 7.02e-4 * temperature * temperature / (temperature + 1108.0);
            var argument = -bandgap / (2.0 * boltzmannConstant * temperature) +
                1.1150877 / (2.0 * boltzmannConstant * referenceTemperature);
            return -2.0 * thermalVoltage * (
                1.5 * Math.Log(temperature / referenceTemperature) +
                electronCharge * argument);
        }

        var nominalThermalVoltage = boltzmannOverCharge * nominalTemperature;
        var thermalVoltage = boltzmannOverCharge * operatingTemperature;
        var temperatureRatio = operatingTemperature / nominalTemperature;
        var saturationExponent =
            (temperatureRatio - 1.0) * model.ActivationEnergy /
                (model.EmissionCoefficient * thermalVoltage) +
            model.SaturationCurrentTemperatureExponent / model.EmissionCoefficient *
                Math.Log(temperatureRatio);
        var saturationCurrent = model.SaturationCurrent * effectiveArea *
            Math.Exp(Math.Clamp(saturationExponent, -700.0, 700.0));

        var nominalFactor = nominalTemperature / referenceTemperature;
        var operatingFactor = operatingTemperature / referenceTemperature;
        var nominalPotentialCorrection = PotentialCorrection(
            nominalTemperature,
            nominalThermalVoltage);
        var operatingPotentialCorrection = PotentialCorrection(
            operatingTemperature,
            thermalVoltage);
        var basePotential = (model.JunctionPotential - nominalPotentialCorrection) /
            nominalFactor;
        var nominalShift = (model.JunctionPotential - basePotential) / basePotential;
        var junctionCapacitance = model.ZeroBiasJunctionCapacitance * effectiveArea /
            (1.0 + model.GradingCoefficient * (
                4e-4 * (nominalTemperature - referenceTemperature) - nominalShift));
        var junctionPotential = operatingPotentialCorrection + operatingFactor * basePotential;
        var operatingShift = (junctionPotential - basePotential) / basePotential;
        junctionCapacitance *= 1.0 + model.GradingCoefficient * (
            4e-4 * (operatingTemperature - referenceTemperature) - operatingShift);
        if (junctionPotential <= 0.0 || junctionCapacitance < 0.0)
            throw new InvalidDataException(
                $"diode temperature adjustment is invalid for model '{model.Name}'");

        double? breakdownVoltage = null;
        if (model.BreakdownVoltage.HasValue)
        {
            var specifiedBreakdownVoltage = model.BreakdownVoltage.Value;
            var breakdownCurrent = model.BreakdownCurrent;
            var adjustedBreakdownVoltage = specifiedBreakdownVoltage;
            if (breakdownCurrent >= saturationCurrent * specifiedBreakdownVoltage / thermalVoltage)
            {
                var breakdownThermalVoltage =
                    model.BreakdownEmissionCoefficient * thermalVoltage;
                adjustedBreakdownVoltage = specifiedBreakdownVoltage -
                    breakdownThermalVoltage * Math.Log(1.0 + breakdownCurrent / saturationCurrent);
                var tolerance = relativeTolerance * breakdownCurrent;
                for (var iteration = 0; iteration < 25; iteration++)
                {
                    var argument = breakdownCurrent / saturationCurrent + 1.0 -
                        adjustedBreakdownVoltage / thermalVoltage;
                    if (argument <= 0.0)
                        break;
                    adjustedBreakdownVoltage = specifiedBreakdownVoltage -
                        breakdownThermalVoltage * Math.Log(argument);
                    var matchedCurrent = saturationCurrent * (
                        Math.Exp(Math.Clamp(
                            (specifiedBreakdownVoltage - adjustedBreakdownVoltage) /
                                breakdownThermalVoltage,
                            -700.0,
                            700.0)) -
                        1.0 + adjustedBreakdownVoltage / thermalVoltage);
                    if (Math.Abs(matchedCurrent - breakdownCurrent) <= tolerance)
                        break;
                }
            }
            breakdownVoltage = adjustedBreakdownVoltage;
        }

        return new DiodeTemperatureParameters(
            operatingTemperature,
            thermalVoltage,
            saturationCurrent,
            junctionCapacitance,
            junctionPotential,
            model.TransitTime,
            breakdownVoltage);
    }

    private void ExpandDiodeSeriesResistances()
    {
        var occupiedElementNames = Elements
            .Select(element => element.Name)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        var originalCount = Elements.Count;
        for (var index = 0; index < originalCount; index++)
        {
            var diode = Elements[index];
            if (diode.Kind != 'D')
                continue;
            var model = DiodeModels[diode.ModelName!];
            if (model.SeriesResistance <= 0.0)
                continue;
            var nodes = diode.Nodes.ToArray();
            var externalNode = nodes[0];
            var internalNode = UniqueInternalName(
                $"__agent_spice_{diode.Name}_anode",
                _nodeNames);
            _nodeNames.Add(internalNode);
            Nodes.Add(internalNode);
            InternalNodes.Add(internalNode);
            nodes[0] = internalNode;
            Elements[index] = diode with { Nodes = nodes };
            var resistorName = UniqueInternalName(
                $"__agent_spice_{diode.Name}_ra",
                occupiedElementNames);
            occupiedElementNames.Add(resistorName);
            Elements.Add(new Element(
                resistorName,
                'R',
                [externalNode, internalNode],
                model.SeriesResistance / diode.Diode!.EffectiveArea(model)));
        }
    }

    private void InitializeMosTemperatureParameters()
    {
        foreach (var mos in Elements.Where(element => element.Kind == 'M'))
        {
            var model = MosModels[mos.ModelName!];
            var instance = mos.Mos!;
            var nominalTemperature = (model.NominalTemperatureCelsius ??
                NominalTemperatureCelsius) + 273.15;
            var operatingTemperature = (instance.TemperatureCelsius ??
                (TemperatureCelsius + instance.DeltaTemperatureCelsius)) + 273.15;
            if (operatingTemperature <= 0.0)
                throw new InvalidDataException(
                    $"MOS1 operating temperature must be above absolute zero on '{mos.Name}'");
            instance.TemperatureParameters = EvaluateMosTemperature(
                model,
                nominalTemperature,
                operatingTemperature);
        }
    }

    private static MosTemperatureParameters EvaluateMosTemperature(
        MosModel model,
        double nominalTemperature,
        double operatingTemperature)
    {
        const double referenceTemperature = 300.15;
        const double boltzmannConstant = 1.380649e-23;
        const double electronCharge = 1.602176634e-19;
        const double boltzmannOverCharge = boltzmannConstant / electronCharge;

        static double Bandgap(double temperature) =>
            1.16 - 7.02e-4 * temperature * temperature / (temperature + 1108.0);

        static double PotentialCorrection(
            double temperature,
            double bandgap,
            double thermalVoltage)
        {
            const double referenceTemperature = 300.15;
            const double boltzmannConstant = 1.380649e-23;
            const double electronCharge = 1.602176634e-19;
            var argument = -bandgap / (2.0 * boltzmannConstant * temperature) +
                1.1150877 / (2.0 * boltzmannConstant * referenceTemperature);
            return -2.0 * thermalVoltage * (
                1.5 * Math.Log(temperature / referenceTemperature) +
                electronCharge * argument);
        }

        var nominalThermalVoltage = nominalTemperature * boltzmannOverCharge;
        var operatingThermalVoltage = operatingTemperature * boltzmannOverCharge;
        var nominalBandgap = Bandgap(nominalTemperature);
        var operatingBandgap = Bandgap(operatingTemperature);
        var nominalPotentialCorrection = PotentialCorrection(
            nominalTemperature,
            nominalBandgap,
            nominalThermalVoltage);
        var operatingPotentialCorrection = PotentialCorrection(
            operatingTemperature,
            operatingBandgap,
            operatingThermalVoltage);
        var nominalFactor = nominalTemperature / referenceTemperature;
        var operatingFactor = operatingTemperature / referenceTemperature;
        var temperatureRatio = operatingTemperature / nominalTemperature;
        var nominalThresholdVoltage = model.ThresholdVoltage;
        var nominalBodyEffectCoefficient = model.BodyEffectCoefficient;
        var nominalSurfacePotential = model.SurfacePotential;
        if (model.OxideThickness > 0.0 && model.Substrate.SubstrateDoping.HasValue)
        {
            const double vacuumPermittivity = 8.854214871e-12;
            var substrateDoping = model.Substrate.SubstrateDoping.Value * 1e6;
            if (substrateDoping <= 1.45e16)
                throw new InvalidDataException(
                    $"MOS1 NSUB must exceed intrinsic carrier concentration for model '{model.Name}'");
            var oxideCapacitanceFactor = 3.9 * vacuumPermittivity / model.OxideThickness;
            if (!model.Substrate.SurfacePotentialGiven)
                nominalSurfacePotential = Math.Max(
                    0.1,
                    2.0 * nominalThermalVoltage * Math.Log(substrateDoping / 1.45e16));
            var substrateFermiPotential =
                model.Polarity * 0.5 * nominalSurfacePotential;
            var gateWorkFunction = 3.2;
            var gateType = model.Substrate.GateType ?? 1;
            if (gateType != 0)
            {
                var gateFermiPotential =
                    model.Polarity * gateType * 0.5 * nominalBandgap;
                gateWorkFunction = 3.25 + 0.5 * nominalBandgap - gateFermiPotential;
            }
            var gateSubstrateWorkFunction = gateWorkFunction -
                (3.25 + 0.5 * nominalBandgap + substrateFermiPotential);
            if (!model.Substrate.BodyEffectCoefficientGiven)
                nominalBodyEffectCoefficient = Math.Sqrt(
                    2.0 * 11.70 * vacuumPermittivity * electronCharge * substrateDoping) /
                    oxideCapacitanceFactor;
            if (!model.Substrate.ThresholdVoltageGiven)
            {
                var flatBandVoltage = gateSubstrateWorkFunction -
                    model.Substrate.SurfaceStateDensity.GetValueOrDefault() * 1e4 *
                    electronCharge / oxideCapacitanceFactor;
                nominalThresholdVoltage = flatBandVoltage + model.Polarity * (
                    nominalBodyEffectCoefficient * Math.Sqrt(nominalSurfacePotential) +
                    nominalSurfacePotential);
            }
        }
        var surfacePotentialAtReference =
            (nominalSurfacePotential - nominalPotentialCorrection) / nominalFactor;
        var surfacePotential = operatingFactor * surfacePotentialAtReference +
            operatingPotentialCorrection;
        if (surfacePotential <= 0.0)
            throw new InvalidDataException(
                $"MOS1 temperature-adjusted PHI is not positive for model '{model.Name}'");
        var builtInVoltage = nominalThresholdVoltage -
            model.Polarity * nominalBodyEffectCoefficient * Math.Sqrt(nominalSurfacePotential) +
            0.5 * (nominalBandgap - operatingBandgap) +
            model.Polarity * 0.5 * (surfacePotential - nominalSurfacePotential);
        var thresholdVoltage = builtInVoltage + model.Polarity *
            nominalBodyEffectCoefficient * Math.Sqrt(surfacePotential);
        var saturationExponent = Math.Clamp(
            -operatingBandgap / operatingThermalVoltage +
            nominalBandgap / nominalThermalVoltage,
            -700.0,
            700.0);
        var saturationScale = Math.Exp(saturationExponent);
        var bulkPotentialAtReference =
            (model.BulkJunctionPotential - nominalPotentialCorrection) / nominalFactor;
        var nominalBulkShift =
            (model.BulkJunctionPotential - bulkPotentialAtReference) /
            bulkPotentialAtReference;
        var bulkJunctionPotential = operatingFactor * bulkPotentialAtReference +
            operatingPotentialCorrection;
        if (bulkJunctionPotential <= 0.0)
            throw new InvalidDataException(
                $"MOS1 temperature-adjusted PB is not positive for model '{model.Name}'");
        var operatingBulkShift =
            (bulkJunctionPotential - bulkPotentialAtReference) /
            bulkPotentialAtReference;

        double ScaleCapacitance(double value, double gradingCoefficient)
        {
            var nominalScale = 1.0 / (
                1.0 + gradingCoefficient * (
                    4e-4 * (nominalTemperature - referenceTemperature) - nominalBulkShift));
            var operatingScale = 1.0 + gradingCoefficient * (
                4e-4 * (operatingTemperature - referenceTemperature) - operatingBulkShift);
            return value * nominalScale * operatingScale;
        }

        return new MosTemperatureParameters(
            operatingTemperature,
            operatingThermalVoltage,
            thresholdVoltage,
            model.Transconductance / (temperatureRatio * Math.Sqrt(temperatureRatio)),
            nominalBodyEffectCoefficient,
            surfacePotential,
            model.JunctionSaturationCurrent * saturationScale,
            model.JunctionSaturationCurrentDensity * saturationScale,
            bulkJunctionPotential,
            ScaleCapacitance(model.BulkDrainCapacitance, model.BulkJunctionGradingCoefficient),
            ScaleCapacitance(model.BulkSourceCapacitance, model.BulkJunctionGradingCoefficient),
            ScaleCapacitance(model.BulkCapacitanceFactor, model.BulkJunctionGradingCoefficient),
            ScaleCapacitance(model.SidewallCapacitanceFactor, model.SidewallJunctionGradingCoefficient));
    }

    private void ExpandMosSeriesResistances()
    {
        var occupiedElementNames = Elements
            .Select(element => element.Name)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        var originalCount = Elements.Count;
        for (var index = 0; index < originalCount; index++)
        {
            var mos = Elements[index];
            if (mos.Kind != 'M')
                continue;
            var model = MosModels[mos.ModelName!];
            var instance = mos.Mos!;
            var nodes = mos.Nodes.ToArray();
            AddSeriesResistance(
                0,
                "drain",
                model.DrainResistance,
                model.SheetResistance,
                instance.DrainSquares,
                instance.Multiplicity);
            AddSeriesResistance(
                2,
                "source",
                model.SourceResistance,
                model.SheetResistance,
                instance.SourceSquares,
                instance.Multiplicity);
            Elements[index] = mos with { Nodes = nodes };

            void AddSeriesResistance(
                int terminal,
                string terminalName,
                double? directResistance,
                double? sheetResistance,
                double squares,
                double multiplicity)
            {
                var createInternalNode = directResistance.GetValueOrDefault() > 0.0 ||
                    (sheetResistance.GetValueOrDefault() > 0.0 && squares > 0.0);
                if (!createInternalNode)
                    return;
                var externalNode = nodes[terminal];
                var internalNode = UniqueInternalName($"__agent_spice_{mos.Name}_{terminalName}", _nodeNames);
                _nodeNames.Add(internalNode);
                Nodes.Add(internalNode);
                InternalNodes.Add(internalNode);
                nodes[terminal] = internalNode;
                var resistorName = UniqueInternalName(
                    $"__agent_spice_{mos.Name}_r{terminalName[0]}",
                    occupiedElementNames);
                occupiedElementNames.Add(resistorName);
                var resistance = EffectiveSeriesResistance(
                    directResistance,
                    sheetResistance,
                    squares,
                    multiplicity);
                if (resistance > 0.0)
                    Elements.Add(new Element(
                        resistorName,
                        'R',
                        [externalNode, internalNode],
                        resistance));
            }
        }
    }

    private static double EffectiveSeriesResistance(
        double? directResistance,
        double? sheetResistance,
        double squares,
        double multiplicity)
    {
        if (directResistance.HasValue)
            return directResistance.Value > 0.0
                ? directResistance.Value / multiplicity
                : 0.0;
        return sheetResistance.GetValueOrDefault() * squares / multiplicity;
    }

    private static string UniqueInternalName(string prefix, HashSet<string> occupied)
    {
        var candidate = prefix;
        for (var suffix = 2; occupied.Contains(candidate); suffix++)
            candidate = $"{prefix}_{suffix}";
        return candidate;
    }

    private void ParseOptions(IEnumerable<string> tokens)
    {
        foreach (var token in tokens)
        {
            if (token.Equals("predictor", StringComparison.OrdinalIgnoreCase))
            {
                UseTransientPredictor = true;
                continue;
            }
            if (token.Equals("nopredictor", StringComparison.OrdinalIgnoreCase))
            {
                UseTransientPredictor = false;
                continue;
            }
            var pair = token.Trim(',').Split('=', 2);
            if (pair.Length != 2)
                continue;
            if (pair[0].Equals("method", StringComparison.OrdinalIgnoreCase))
            {
                TransientIntegrationMethod = pair[1].ToLowerInvariant() switch
                {
                    "trap" or "trapezoidal" => IntegrationMethod.Trapezoidal,
                    "gear" => IntegrationMethod.Gear,
                    _ => throw new InvalidDataException($"unsupported integration method '{pair[1]}'")
                };
                continue;
            }
            var value = ParseNumber(pair[1]);
            switch (pair[0].ToLowerInvariant())
            {
                case "reltol": RelativeTolerance = PositiveOption(pair[0], value); break;
                case "vntol" or "vabstol": VoltageTolerance = PositiveOption(pair[0], value); break;
                case "abstol" or "iabstol": CurrentTolerance = PositiveOption(pair[0], value); break;
                case "chgtol": ChargeTolerance = PositiveOption(pair[0], value); break;
                case "trtol": TruncationTolerance = PositiveOption(pair[0], value); break;
                case "temp": TemperatureCelsius = ParseTemperature(pair[1], pair[0]); break;
                case "tnom": NominalTemperatureCelsius = ParseTemperature(pair[1], pair[0]); break;
            }
        }
    }

    private static double ParseTemperature(string token, string name)
    {
        var value = ParseNumber(token);
        if (value <= -273.15)
            throw new InvalidDataException($"{name} must be above absolute zero");
        return value;
    }

    private static double PositiveOption(string name, double value)
    {
        if (value <= 0.0 || !double.IsFinite(value))
            throw new InvalidDataException($".options {name} must be positive and finite");
        return value;
    }

    private static (double Value, TransientSource? Transient) ParseSource(
        string line,
        string[] tokens,
        int valueIndex)
    {
        var dcIndex = Array.FindIndex(
            tokens,
            valueIndex,
            token => token.Equals("dc", StringComparison.OrdinalIgnoreCase));
        if (dcIndex >= 0)
            Require(tokens[dcIndex..], 2, "source DC value");
        var dcValue = dcIndex >= 0
            ? ParseNumber(tokens[dcIndex + 1])
            : 0.0;
        var pulseMatch = PulsePattern.Match(line);
        if (pulseMatch.Success)
        {
            var values = ParseSourceArguments(pulseMatch);
            if (values.Length != 7)
                throw new InvalidDataException("PULSE requires seven values: initial pulsed delay rise fall width period");
            if (values[2] < 0.0 || values[3] < 0.0 || values[4] < 0.0 ||
                values[5] < 0.0 || values[6] < 0.0)
                throw new InvalidDataException("PULSE delay, rise, fall, width, and period must be non-negative");
            var pulse = new PulseSource(values[0], values[1], values[2], values[3], values[4], values[5], values[6]);
            return (dcValue, pulse);
        }
        var pwlMatch = PwlPattern.Match(line);
        if (pwlMatch.Success)
        {
            var values = ParseSourceArguments(pwlMatch);
            if (values.Length < 4 || values.Length % 2 != 0)
                throw new InvalidDataException("PWL requires at least two time/value pairs");
            var times = values.Where((_, index) => index % 2 == 0).ToArray();
            var samples = values.Where((_, index) => index % 2 != 0).ToArray();
            if (times[0] < 0.0 || times.Zip(times.Skip(1)).Any(pair => pair.First > pair.Second))
                throw new InvalidDataException("PWL times must be non-negative and non-decreasing");
            return (dcValue, new PwlSource(times, samples));
        }
        var sinMatch = SinPattern.Match(line);
        if (sinMatch.Success)
        {
            var values = ParseSourceArguments(sinMatch);
            if (values.Length < 3 || values.Length > 6)
                throw new InvalidDataException("SIN requires offset, amplitude, frequency, and optional delay, damping, phase");
            var delay = values.Length > 3 ? values[3] : 0.0;
            var damping = values.Length > 4 ? values[4] : 0.0;
            var phase = values.Length > 5 ? values[5] : 0.0;
            if (values[2] < 0.0 || delay < 0.0 || damping < 0.0)
                throw new InvalidDataException("SIN frequency, delay, and damping must be non-negative");
            return (dcValue, new SinSource(values[0], values[1], values[2], delay, damping, phase));
        }
        var expMatch = ExpPattern.Match(line);
        if (expMatch.Success)
        {
            var values = ParseSourceArguments(expMatch);
            if (values.Length != 6)
                throw new InvalidDataException("EXP requires initial, pulsed, rise delay/time constant, and fall delay/time constant");
            if (values[2] < 0.0 || values[3] <= 0.0 || values[4] < values[2] || values[5] <= 0.0)
                throw new InvalidDataException("EXP delays must be ordered and non-negative; time constants must be positive");
            return (dcValue, new ExpSource(values[0], values[1], values[2], values[3], values[4], values[5]));
        }
        if (tokens[valueIndex].Equals("ac", StringComparison.OrdinalIgnoreCase))
            return (0.0, null);
        if (dcIndex >= 0)
            return (dcValue, null);
        return (ParseNumber(tokens[valueIndex]), null);
    }

    private static double[] ParseSourceArguments(Match match) =>
        match.Groups[1].Value
            .Split([',', ' ', '\t'], StringSplitOptions.RemoveEmptyEntries)
            .Select(ParseNumber)
            .ToArray();

    private static bool LooksLikeElement(string[] tokens, string line, RfmModel? rfm, string rfmSubcircuit)
    {
        var kind = char.ToUpperInvariant(tokens[0][0]);
        if (kind == 'X')
            return rfm is not null && tokens.Length == rfm.Nports + 3 && tokens[^1].Equals(rfmSubcircuit, StringComparison.OrdinalIgnoreCase);
        if (kind is 'G' or 'E')
            return tokens.Length >= 6 && IsNumber(tokens[5]);
        if (kind is 'F' or 'H')
            return tokens.Length >= 5 && IsNumber(tokens[4]);
        if (kind is 'R' or 'C' or 'L')
            return tokens.Length >= 4 && IsNumber(tokens[3]);
        if (kind is 'D' or 'Q' or 'M')
            return false;
        if (kind is not ('V' or 'I') || tokens.Length < 4)
            return false;
        return tokens[3].Equals("ac", StringComparison.OrdinalIgnoreCase)
            || tokens[3].Equals("dc", StringComparison.OrdinalIgnoreCase)
            || PulsePattern.IsMatch(line)
            || PwlPattern.IsMatch(line)
            || SinPattern.IsMatch(line)
            || ExpPattern.IsMatch(line)
            || IsNumber(tokens[3]);
    }

    private static bool IsNumber(string token)
    {
        try
        {
            ParseNumber(token);
            return true;
        }
        catch (FormatException)
        {
            return false;
        }
    }

    private void AddNode(string node)
    {
        if (!node.Equals("0", StringComparison.OrdinalIgnoreCase) && _nodeNames.Add(node))
            Nodes.Add(node);
    }

    private static void Require(string[] tokens, int count, string syntax)
    {
        if (tokens.Length < count)
            throw new InvalidDataException($"invalid {syntax}: '{string.Join(' ', tokens)}'");
    }

    internal static double ParseNumber(string token)
    {
        var text = token.Trim().TrimEnd(',');
        var suffixes = new (string Suffix, double Scale)[]
        {
            ("meg", 1e6), ("mil", 25.4e-6), ("t", 1e12), ("g", 1e9),
            ("k", 1e3), ("m", 1e-3), ("u", 1e-6), ("n", 1e-9),
            ("p", 1e-12), ("f", 1e-15)
        };
        foreach (var (suffix, scale) in suffixes)
        {
            if (text.EndsWith(suffix, StringComparison.OrdinalIgnoreCase))
                return double.Parse(text[..^suffix.Length], CultureInfo.InvariantCulture) * scale;
        }
        return double.Parse(text.Replace('D', 'E').Replace('d', 'e'), CultureInfo.InvariantCulture);
    }
}
