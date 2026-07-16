using System.Text.Json.Serialization;

namespace AgentSpice.Engine;

internal sealed record ExecutionSummary(bool Ok, int WaveformRows);

[JsonSourceGenerationOptions(
    PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase,
    WriteIndented = false)]
[JsonSerializable(typeof(SimulationResult))]
[JsonSerializable(typeof(ExecutionSummary))]
internal partial class AgentSpiceJsonContext : JsonSerializerContext;
