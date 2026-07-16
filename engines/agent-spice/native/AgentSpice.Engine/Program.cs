using System.Text.Json;
using System.Diagnostics;

namespace AgentSpice.Engine;

internal static class Program
{
    private static int Main(string[] args)
    {
        try
        {
            var timer = Stopwatch.StartNew();
            var options = CommandLine.Parse(args);
            var rfm = options.RfmPath is null ? null : RfmModel.Parse(options.RfmPath);
            var deck = Deck.Parse(
                File.ReadAllText(options.DeckPath),
                rfm,
                options.RfmSubcircuit,
                options.DeckPath);
            var parseSeconds = timer.Elapsed.TotalSeconds;
            var result = Simulator.Run(deck);
            var simulationSeconds = timer.Elapsed.TotalSeconds - parseSeconds;
            var waveformRows = 0;
            if (options.OutputJsonPath is null)
            {
                var json = JsonSerializer.Serialize(result, AgentSpiceJsonContext.Default.SimulationResult);
                Console.WriteLine(json);
            }
            else
            {
                using (var output = File.Create(options.OutputJsonPath))
                    JsonSerializer.Serialize(output, result, AgentSpiceJsonContext.Default.SimulationResult);
                if (options.WaveformCsvPath is not null)
                    waveformRows = WaveformWriter.Write(result, options.WaveformCsvPath);
                Console.WriteLine(JsonSerializer.Serialize(
                    new ExecutionSummary(true, waveformRows),
                    AgentSpiceJsonContext.Default.ExecutionSummary));
            }
            var serializationSeconds = timer.Elapsed.TotalSeconds - parseSeconds - simulationSeconds;
            if (Environment.GetEnvironmentVariable("AGENT_SPICE_NATIVE_TIMING") == "1")
                Console.Error.WriteLine(
                    $"timing parse={parseSeconds:F6}s simulate={simulationSeconds:F6}s " +
                    $"serialize={serializationSeconds:F6}s total={timer.Elapsed.TotalSeconds:F6}s");
            if (result.Statistics.CollectSparseFactorProfile)
                Console.Error.WriteLine(result.Statistics.SparseFactorProfileSummary());
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine(Environment.GetEnvironmentVariable("AGENT_SPICE_NATIVE_STACKTRACE") == "1"
                ? error.ToString()
                : $"agent-spice-engine: {error.Message}");
            return 1;
        }
    }
}

internal sealed record CommandLine(
    string DeckPath,
    string? RfmPath,
    string RfmSubcircuit,
    string? OutputJsonPath,
    string? WaveformCsvPath)
{
    internal static CommandLine Parse(string[] args)
    {
        if (args.Length == 0)
            throw new ArgumentException(
                "usage: AgentSpice.Engine <deck> [--rfm <model.rfm>] [--rfm-subckt <name>] " +
                "[--output-json <result.json>] [--waveform-csv <waveform.csv>]");

        string? rfmPath = null;
        var subcircuit = "rfm_direct";
        string? outputJsonPath = null;
        string? waveformCsvPath = null;
        for (var index = 1; index < args.Length; index++)
        {
            if (index + 1 >= args.Length)
                throw new ArgumentException($"missing value for '{args[index]}'");
            switch (args[index])
            {
                case "--rfm": rfmPath = args[++index]; break;
                case "--rfm-subckt": subcircuit = args[++index]; break;
                case "--output-json": outputJsonPath = args[++index]; break;
                case "--waveform-csv": waveformCsvPath = args[++index]; break;
                default: throw new ArgumentException($"unknown option '{args[index]}'");
            }
        }
        if (waveformCsvPath is not null && outputJsonPath is null)
            throw new ArgumentException("--waveform-csv requires --output-json");
        return new CommandLine(
            Path.GetFullPath(args[0]),
            rfmPath is null ? null : Path.GetFullPath(rfmPath),
            subcircuit,
            outputJsonPath is null ? null : Path.GetFullPath(outputJsonPath),
            waveformCsvPath is null ? null : Path.GetFullPath(waveformCsvPath));
    }
}
