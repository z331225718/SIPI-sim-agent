using System.Globalization;

namespace AgentSpice.Engine;

internal static class WaveformWriter
{
    internal static int Write(SimulationResult result, string path)
    {
        if (result.Points.Count == 0)
            return 0;

        var analysis = result.Points[0].Analysis;
        var names = analysis == "ac" ? result.Points[0].ComplexNames : result.Points[0].ValueNames;
        using var writer = new StreamWriter(path, false, new System.Text.UTF8Encoding(false));
        if (analysis == "ac")
        {
            writer.Write("frequency");
            foreach (var name in names)
                writer.Write($",real({name}),imag({name})");
        }
        else
        {
            writer.Write(analysis == "tran" ? "time" : "sweep");
            foreach (var name in names)
                writer.Write($",{name}");
        }
        writer.WriteLine();

        var count = 0;
        foreach (var point in result.Points)
        {
            if (point.Analysis != analysis)
                continue;
            WriteNumber(writer, point.X);
            if (analysis == "ac")
            {
                for (var index = 0; index < names.Length; index++)
                {
                    writer.Write(',');
                    WriteNumber(writer, point.Complex[index].Re);
                    writer.Write(',');
                    WriteNumber(writer, point.Complex[index].Im);
                }
            }
            else
            {
                for (var index = 0; index < names.Length; index++)
                {
                    writer.Write(',');
                    WriteNumber(writer, point.Values[point.ValueOffset + index]);
                }
            }
            writer.WriteLine();
            count++;
        }
        return count;
    }

    private static void WriteNumber(TextWriter writer, double value) =>
        writer.Write(value.ToString("R", CultureInfo.InvariantCulture));
}
