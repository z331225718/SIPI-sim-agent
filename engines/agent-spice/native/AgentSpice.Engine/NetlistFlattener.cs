using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;

namespace AgentSpice.Engine;

internal sealed record SubcircuitDefinition(
    string Name,
    string[] Pins,
    IReadOnlyDictionary<string, string> Defaults,
    IReadOnlyDictionary<string, string> LocalParameters,
    IReadOnlySet<string> LocalModels,
    string[] Body);

internal static partial class NetlistFlattener
{
    private static readonly StringComparer Names = StringComparer.OrdinalIgnoreCase;
    private static readonly StringComparer Paths = OperatingSystem.IsWindows()
        ? StringComparer.OrdinalIgnoreCase
        : StringComparer.Ordinal;

    internal static string Flatten(
        string text,
        RfmModel? rfm,
        string rfmSubcircuit,
        string? sourcePath)
    {
        var logicalLines = NormalizeLines(text);
        var dependencyStack = new HashSet<string>(Paths);
        string? rootPath = null;
        if (sourcePath is not null)
        {
            rootPath = Path.GetFullPath(sourcePath);
            dependencyStack.Add(rootPath);
        }
        logicalLines = ResolveDependencies(logicalLines, rootPath, dependencyStack);
        var subcircuits = new Dictionary<string, SubcircuitDefinition>(Names);
        var topLevel = CollectSubcircuits(logicalLines, subcircuits);
        var globalDefinitions = new Dictionary<string, string>(Names);
        foreach (var line in topLevel)
        {
            if (Head(line) == ".param")
                MergeAssignments(globalDefinitions, DirectiveBody(line));
        }
        var globalNodes = topLevel
            .Where(line => Head(line) == ".global")
            .SelectMany(line => Tokenize(line)[1..])
            .ToHashSet(Names);
        var globalScope = new ParameterScope(definitions: globalDefinitions);
        var output = new List<string>();
        ExpandLines(
            topLevel,
            globalScope,
            path: "",
            new Dictionary<string, string>(Names),
            globalNodes,
            new Dictionary<string, string>(Names),
            subcircuits,
            rfm,
            rfmSubcircuit,
            [],
            output,
            topLevel: true);
        return string.Join('\n', output) + '\n';
    }

    private static string[] ResolveDependencies(
        IReadOnlyList<string> lines,
        string? sourcePath,
        ISet<string> dependencyStack)
    {
        var output = new List<string>();
        foreach (var line in lines)
        {
            var head = Head(line);
            if (head is not (".include" or ".inc" or ".lib"))
            {
                if (head == ".endl")
                    throw new InvalidDataException($"unexpected .endl in '{sourcePath ?? "in-memory deck"}'");
                output.Add(line);
                continue;
            }
            var tokens = Tokenize(line);
            if (head == ".lib" && tokens.Length < 3)
                throw new InvalidDataException(
                    $"inline .lib section declarations are not supported in '{sourcePath ?? "in-memory deck"}'");
            if (tokens.Length < 2)
                throw new InvalidDataException($"{tokens[0]} requires a file path");
            if (sourcePath is null)
                throw new InvalidDataException($"cannot resolve {tokens[0]} without a source file path");

            var dependencyPath = ResolveDependencyPath(sourcePath, tokens[1]);
            if (!File.Exists(dependencyPath))
                throw new FileNotFoundException(
                    $"dependency '{tokens[1]}' referenced by '{sourcePath}' was not found",
                    dependencyPath);
            if (!dependencyStack.Add(dependencyPath))
            {
                var chain = string.Join(" -> ", dependencyStack.Append(dependencyPath));
                throw new InvalidDataException($"recursive netlist dependency detected: {chain}");
            }
            try
            {
                var dependencyLines = NormalizeLines(File.ReadAllText(dependencyPath));
                if (head == ".lib")
                    dependencyLines = SelectLibrarySection(dependencyLines, tokens[2], dependencyPath);
                if (dependencyLines.Any(dependencyLine => Head(dependencyLine) == ".end"))
                    throw new InvalidDataException($"included dependency '{dependencyPath}' must not contain .end");
                output.AddRange(ResolveDependencies(dependencyLines, dependencyPath, dependencyStack));
            }
            finally
            {
                dependencyStack.Remove(dependencyPath);
            }
        }
        return output.ToArray();
    }

    private static string ResolveDependencyPath(string sourcePath, string token)
    {
        var path = token.Trim().Trim('\'', '"');
        if (path.Length == 0)
            throw new InvalidDataException("empty include/library path");
        return Path.GetFullPath(
            Path.IsPathRooted(path)
                ? path
                : Path.Combine(Path.GetDirectoryName(sourcePath)!, path));
    }

    private static string[] SelectLibrarySection(
        IReadOnlyList<string> lines,
        string requestedSection,
        string libraryPath)
    {
        var selected = new List<string>();
        var inside = false;
        var found = false;
        foreach (var line in lines)
        {
            var tokens = Tokenize(line);
            if (tokens.Length == 0)
                continue;
            var head = tokens[0].ToLowerInvariant();
            if (head == ".lib" && tokens.Length == 2)
            {
                if (inside)
                    throw new InvalidDataException($"nested .lib section in '{libraryPath}'");
                inside = tokens[1].Equals(requestedSection, StringComparison.OrdinalIgnoreCase);
                found |= inside;
                continue;
            }
            if (head == ".endl")
            {
                if (inside && tokens.Length > 1 &&
                    !tokens[1].Equals(requestedSection, StringComparison.OrdinalIgnoreCase))
                {
                    throw new InvalidDataException(
                        $".endl '{tokens[1]}' does not match .lib '{requestedSection}' in '{libraryPath}'");
                }
                inside = false;
                continue;
            }
            if (inside)
                selected.Add(line);
        }
        if (!found)
            throw new InvalidDataException(
                $"library section '{requestedSection}' was not found in '{libraryPath}'");
        if (inside)
            throw new InvalidDataException(
                $"library section '{requestedSection}' in '{libraryPath}' has no matching .endl");
        return selected.ToArray();
    }

    private static string[] NormalizeLines(string text)
    {
        var lines = new List<string>();
        foreach (var raw in text.Replace("\r", "", StringComparison.Ordinal).Split('\n'))
        {
            var line = raw.Trim();
            if (line.Length == 0)
                continue;
            if (line.StartsWith('+'))
            {
                if (lines.Count == 0)
                    throw new InvalidDataException("netlist continuation has no preceding line");
                lines[^1] += " " + line[1..].TrimStart();
                continue;
            }
            lines.Add(line);
        }
        return lines.ToArray();
    }

    private static string[] CollectSubcircuits(
        IReadOnlyList<string> lines,
        IDictionary<string, SubcircuitDefinition> subcircuits)
    {
        var topLevel = new List<string>();
        for (var index = 0; index < lines.Count; index++)
        {
            var line = lines[index];
            var head = Head(line);
            if (head == ".end")
            {
                topLevel.Add(line);
                break;
            }
            if (head != ".subckt")
            {
                topLevel.Add(line);
                continue;
            }

            var header = Tokenize(line);
            if (header.Length < 3)
                throw new InvalidDataException($"invalid .subckt header '{line}'");
            var parameterStart = FindParameterStart(header, 2);
            var pinEnd = parameterStart >= 0 ? parameterStart : header.Length;
            var pins = header[2..pinEnd];
            if (pins.Length == 0)
                throw new InvalidDataException($"subcircuit '{header[1]}' must declare at least one pin");
            if (pins.Distinct(Names).Count() != pins.Length)
                throw new InvalidDataException($"subcircuit '{header[1]}' has duplicate pins");
            var defaults = parameterStart >= 0
                ? ParseAssignments(string.Join(' ', header[SkipParamsMarker(header, parameterStart)..]))
                : new Dictionary<string, string>(Names);
            var body = new List<string>();
            var foundEnd = false;
            while (++index < lines.Count)
            {
                var bodyLine = lines[index];
                var bodyHead = Head(bodyLine);
                if (bodyHead == ".subckt")
                    throw new InvalidDataException("nested .subckt declarations are not supported");
                if (bodyHead == ".ends")
                {
                    var endTokens = Tokenize(bodyLine);
                    if (endTokens.Length > 1 && !endTokens[1].Equals(header[1], StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException($".ends '{endTokens[1]}' does not match .subckt '{header[1]}'");
                    foundEnd = true;
                    break;
                }
                body.Add(bodyLine);
            }
            if (!foundEnd)
                throw new InvalidDataException($"subcircuit '{header[1]}' has no matching .ends");

            var localParameters = new Dictionary<string, string>(Names);
            var localModels = new HashSet<string>(Names);
            foreach (var bodyLine in body)
            {
                if (Head(bodyLine) == ".param")
                    MergeAssignments(localParameters, DirectiveBody(bodyLine));
                var model = ModelHeaderPattern().Match(bodyLine);
                if (model.Success)
                    localModels.Add(model.Groups[1].Value);
            }
            var definition = new SubcircuitDefinition(
                header[1],
                pins,
                defaults,
                localParameters,
                localModels,
                body.ToArray());
            if (!subcircuits.TryAdd(definition.Name, definition))
                throw new InvalidDataException($"duplicate subcircuit '{definition.Name}'");
        }
        return topLevel.ToArray();
    }

    private static void ExpandLines(
        IReadOnlyList<string> lines,
        ParameterScope scope,
        string path,
        IReadOnlyDictionary<string, string> pinMap,
        IReadOnlySet<string> globalNodes,
        IReadOnlyDictionary<string, string> modelMap,
        IReadOnlyDictionary<string, SubcircuitDefinition> subcircuits,
        RfmModel? rfm,
        string rfmSubcircuit,
        IReadOnlyList<string> expansionStack,
        ICollection<string> output,
        bool topLevel)
    {
        var firstLine = topLevel;
        foreach (var line in lines)
        {
            if (firstLine)
            {
                firstLine = false;
                if (line.StartsWith('*') || line.StartsWith(';') || IsTitle(line, subcircuits, rfm, rfmSubcircuit))
                {
                    output.Add(line);
                    continue;
                }
            }
            if (line.StartsWith('*') || line.StartsWith(';'))
                continue;
            var head = Head(line);
            if (head == ".param")
                continue;
            if (head == ".ends" || head == ".subckt")
                throw new InvalidDataException($"unexpected directive '{head}' during subcircuit expansion");

            var tokens = Tokenize(line);
            if (tokens.Length == 0)
                continue;
            if (char.ToUpperInvariant(tokens[0][0]) == 'X' &&
                TryExpandSubcircuit(
                    tokens,
                    scope,
                    path,
                    pinMap,
                    globalNodes,
                    modelMap,
                    subcircuits,
                    rfm,
                    rfmSubcircuit,
                    expansionStack,
                    output))
            {
                continue;
            }
            output.Add(tokens[0].StartsWith('.')
                ? RewriteDirective(line, scope, path, pinMap, globalNodes, modelMap)
                : RewriteElement(tokens, scope, path, pinMap, globalNodes, modelMap, rfm, rfmSubcircuit));
        }
    }

    private static bool TryExpandSubcircuit(
        string[] tokens,
        ParameterScope callerScope,
        string callerPath,
        IReadOnlyDictionary<string, string> callerPinMap,
        IReadOnlySet<string> globalNodes,
        IReadOnlyDictionary<string, string> callerModelMap,
        IReadOnlyDictionary<string, SubcircuitDefinition> subcircuits,
        RfmModel? rfm,
        string rfmSubcircuit,
        IReadOnlyList<string> expansionStack,
        ICollection<string> output)
    {
        // An explicitly bound RFM instance is a native device even when the
        // staged ngspice deck also includes its XSPICE wrapper subcircuit.
        if (rfm is not null && tokens[^1].Equals(rfmSubcircuit, StringComparison.OrdinalIgnoreCase))
            return false;

        var parameterStart = FindParameterStart(tokens, 1);
        var subcircuitIndex = (parameterStart >= 0 ? parameterStart : tokens.Length) - 1;
        if (subcircuitIndex < 2 || !subcircuits.TryGetValue(tokens[subcircuitIndex], out var definition))
            return false;
        if (expansionStack.Contains(definition.Name, Names))
            throw new InvalidDataException($"recursive subcircuit expansion detected for '{definition.Name}'");
        var actualNodes = tokens[1..subcircuitIndex];
        if (actualNodes.Length != definition.Pins.Length)
            throw new InvalidDataException(
                $"{tokens[0]} supplies {actualNodes.Length} node(s), but subcircuit '{definition.Name}' requires {definition.Pins.Length}");

        var childPath = callerPath.Length == 0 ? tokens[0] : $"{callerPath}.{tokens[0]}";
        var childPinMap = new Dictionary<string, string>(Names);
        for (var index = 0; index < definition.Pins.Length; index++)
            childPinMap[definition.Pins[index]] = MapNode(actualNodes[index], callerPath, callerPinMap, globalNodes);

        var childDefinitions = new Dictionary<string, string>(definition.Defaults, Names);
        foreach (var (name, expression) in definition.LocalParameters)
            childDefinitions[name] = expression;
        if (parameterStart >= 0)
        {
            var overrideStart = SkipParamsMarker(tokens, parameterStart);
            var overrides = ParseAssignments(string.Join(' ', tokens[overrideStart..]));
            foreach (var (name, expression) in overrides)
            {
                if (!definition.Defaults.ContainsKey(name) && !definition.LocalParameters.ContainsKey(name))
                    throw new InvalidDataException($"{tokens[0]} overrides unknown parameter '{name}' of '{definition.Name}'");
                childDefinitions[name] = NumericExpression.Format(callerScope.Evaluate(expression));
            }
        }
        var childScope = new ParameterScope(callerScope, childDefinitions);
        var childModelMap = new Dictionary<string, string>(callerModelMap, Names);
        foreach (var model in definition.LocalModels)
            childModelMap[model] = QualifyModel(model, childPath);
        var childStack = expansionStack.Append(definition.Name).ToArray();
        ExpandLines(
            definition.Body,
            childScope,
            childPath,
            childPinMap,
            globalNodes,
            childModelMap,
            subcircuits,
            rfm,
            rfmSubcircuit,
            childStack,
            output,
            topLevel: false);
        return true;
    }

    private static string RewriteDirective(
        string line,
        ParameterScope scope,
        string path,
        IReadOnlyDictionary<string, string> pinMap,
        IReadOnlySet<string> globalNodes,
        IReadOnlyDictionary<string, string> modelMap)
    {
        var tokens = Tokenize(line);
        var head = tokens[0].ToLowerInvariant();
        switch (head)
        {
            case ".model":
                return RewriteModel(line, scope, path, modelMap);
            case ".dc":
                Require(tokens, 5, ".dc source start stop step");
                return $".dc {QualifyElement(tokens[1], path)} {Evaluate(scope, tokens[2])} {Evaluate(scope, tokens[3])} {Evaluate(scope, tokens[4])}";
            case ".ac":
                Require(tokens, 5, ".ac lin|dec|oct points start stop");
                return $".ac {tokens[1]} {Evaluate(scope, tokens[2])} {Evaluate(scope, tokens[3])} {Evaluate(scope, tokens[4])}";
            case ".tran":
                Require(tokens, 3, ".tran step stop [start]");
                return tokens.Length >= 4
                    ? $".tran {Evaluate(scope, tokens[1])} {Evaluate(scope, tokens[2])} {Evaluate(scope, tokens[3])}"
                    : $".tran {Evaluate(scope, tokens[1])} {Evaluate(scope, tokens[2])}";
            case ".options":
            case ".option":
                {
                    var rewritten = new List<string> { tokens[0] };
                    foreach (var token in tokens[1..])
                    {
                        var pair = token.Trim(',').Split('=', 2);
                        if (pair.Length != 2 || pair[0].Equals("method", StringComparison.OrdinalIgnoreCase))
                            rewritten.Add(token);
                        else
                            rewritten.Add($"{pair[0]}={Evaluate(scope, pair[1])}");
                    }
                    return string.Join(' ', rewritten);
                }
            case ".print":
            case ".probe":
                return path.Length == 0 ? line : RewriteOutputDirective(line, path, pinMap, globalNodes);
            default:
                return line;
        }
    }

    private static string RewriteModel(
        string line,
        ParameterScope scope,
        string path,
        IReadOnlyDictionary<string, string> modelMap)
    {
        var match = ModelHeaderPattern().Match(line);
        if (!match.Success)
            throw new InvalidDataException($"unsupported .model syntax '{line}'");
        var sourceName = match.Groups[1].Value;
        var name = modelMap.TryGetValue(sourceName, out var mapped)
            ? mapped
            : path.Length == 0 ? sourceName : QualifyModel(sourceName, path);
        var modelType = match.Groups[2].Value;
        var body = match.Groups[3].Value.Trim().TrimStart('(').TrimEnd(')');
        if (body.Length == 0)
            return $".model {name} {modelType}";
        var parameters = ParseAssignments(body);
        return $".model {name} {modelType} ({string.Join(' ', parameters.Select(pair => $"{pair.Key}={Evaluate(scope, pair.Value)}"))})";
    }

    private static string RewriteElement(
        string[] tokens,
        ParameterScope scope,
        string path,
        IReadOnlyDictionary<string, string> pinMap,
        IReadOnlySet<string> globalNodes,
        IReadOnlyDictionary<string, string> modelMap,
        RfmModel? rfm,
        string rfmSubcircuit)
    {
        var kind = char.ToUpperInvariant(tokens[0][0]);
        var name = QualifyElement(tokens[0], path);
        string Node(int index) => MapNode(tokens[index], path, pinMap, globalNodes);
        switch (kind)
        {
            case 'R':
            case 'C':
            case 'L':
                Require(tokens, 4, $"{kind} element");
                return $"{name} {Node(1)} {Node(2)} {Evaluate(scope, tokens[3])}";
            case 'V':
            case 'I':
                Require(tokens, 4, $"{kind} source");
                return RewriteSource(tokens, scope, name, Node(1), Node(2));
            case 'G':
            case 'E':
                Require(tokens, 6, $"{kind} element");
                return $"{name} {Node(1)} {Node(2)} {Node(3)} {Node(4)} {Evaluate(scope, tokens[5])}";
            case 'F':
            case 'H':
                Require(tokens, 5, $"{kind} element");
                return $"{name} {Node(1)} {Node(2)} {QualifyElement(tokens[3], path)} {Evaluate(scope, tokens[4])}";
            case 'D':
                {
                    Require(tokens, 4, "D element");
                    var rewritten = new List<string>
                    {
                        name,
                        Node(1),
                        Node(2),
                        MapModel(tokens[3], modelMap)
                    };
                    foreach (var parameter in tokens[4..])
                    {
                        var pair = parameter.Split('=', 2);
                        rewritten.Add(pair.Length == 2
                            ? $"{pair[0]}={Evaluate(scope, pair[1])}"
                            : parameter.Equals("off", StringComparison.OrdinalIgnoreCase)
                                ? parameter
                                : Evaluate(scope, parameter));
                    }
                    return string.Join(' ', rewritten);
                }
            case 'Q':
                {
                    Require(tokens, 5, "Q element");
                    var rewritten = new List<string>
                    {
                        name,
                        Node(1),
                        Node(2),
                        Node(3),
                        MapModel(tokens[4], modelMap)
                    };
                    foreach (var parameter in tokens[5..])
                    {
                        var pair = parameter.Split('=', 2);
                        rewritten.Add(pair.Length == 2
                            ? $"{pair[0]}={Evaluate(scope, pair[1])}"
                            : parameter.Equals("off", StringComparison.OrdinalIgnoreCase)
                                ? parameter
                                : Evaluate(scope, parameter));
                    }
                    return string.Join(' ', rewritten);
                }
            case 'M':
                {
                    Require(tokens, 6, "M element");
                    var rewritten = new List<string>
                    {
                        name,
                        Node(1),
                        Node(2),
                        Node(3),
                        Node(4),
                        MapModel(tokens[5], modelMap)
                    };
                    foreach (var parameter in tokens[6..])
                    {
                        var pair = parameter.Split('=', 2);
                        if (pair.Length != 2)
                            throw new InvalidDataException(
                                $"invalid MOS1 instance parameter '{parameter}' on '{tokens[0]}'");
                        rewritten.Add($"{pair[0]}={Evaluate(scope, pair[1])}");
                    }
                    return string.Join(' ', rewritten);
                }
            case 'X':
                if (rfm is null || !tokens[^1].Equals(rfmSubcircuit, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException($"unsupported subcircuit instance '{tokens[0]}'");
                if (tokens.Length != rfm.Nports + 3)
                    throw new InvalidDataException($"{tokens[0]} has invalid RFM port count");
                return string.Join(' ', new[] { name }
                    .Concat(tokens[1..^1].Select((_, index) => Node(index + 1)))
                    .Append(tokens[^1]));
            default:
                return string.Join(' ', tokens);
        }
    }

    private static string RewriteSource(
        string[] tokens,
        ParameterScope scope,
        string name,
        string positive,
        string negative)
    {
        var source = new List<string> { name, positive, negative };
        var transientIndex = Array.FindIndex(tokens, 3, token => TransientFunctionName(token) is not null);
        var dcIndex = Array.FindIndex(tokens, 3, token => token.Equals("dc", StringComparison.OrdinalIgnoreCase));
        if (dcIndex >= 0 && dcIndex + 1 >= tokens.Length)
            throw new InvalidDataException($"{tokens[0]} DC source requires a value");
        if (transientIndex >= 0)
        {
            var function = TransientFunctionName(tokens[transientIndex])!;
            var arguments = FunctionArguments(tokens[transientIndex], function);
            ValidateTransientArgumentCount(function, arguments.Count);
            source.Add("dc");
            source.Add(dcIndex >= 0
                ? Evaluate(scope, tokens[dcIndex + 1])
                : "0");
            source.Add($"{function}({string.Join(' ', arguments.Select(argument => Evaluate(scope, argument)))})");
        }
        else if (tokens[3].Equals("ac", StringComparison.OrdinalIgnoreCase))
        {
            source.Add("dc");
            source.Add("0");
        }
        else if (dcIndex >= 0)
        {
            Require(tokens[dcIndex..], 2, "source DC value");
            source.Add("dc");
            source.Add(Evaluate(scope, tokens[dcIndex + 1]));
        }
        else
        {
            source.Add(Evaluate(scope, tokens[3]));
        }

        var acIndex = Array.FindIndex(tokens, 3, token => token.Equals("ac", StringComparison.OrdinalIgnoreCase));
        if (acIndex >= 0)
        {
            if (acIndex + 1 >= tokens.Length)
                throw new InvalidDataException($"{tokens[0]} AC source requires an amplitude");
            source.Add("ac");
            source.Add(Evaluate(scope, tokens[acIndex + 1]));
            if (acIndex + 2 < tokens.Length && TransientFunctionName(tokens[acIndex + 2]) is null)
                source.Add(Evaluate(scope, tokens[acIndex + 2]));
        }
        return string.Join(' ', source);
    }

    private static string RewriteOutputDirective(
        string line,
        string path,
        IReadOnlyDictionary<string, string> pinMap,
        IReadOnlySet<string> globalNodes) =>
        OutputReferencePattern().Replace(line, match =>
        {
            var kind = match.Groups[1].Value;
            var target = match.Groups[2].Value;
            var mapped = kind.Equals("v", StringComparison.OrdinalIgnoreCase)
                ? MapNode(target, path, pinMap, globalNodes)
                : QualifyElement(target, path);
            return $"{kind}({mapped}";
        });

    private static string MapNode(
        string node,
        string path,
        IReadOnlyDictionary<string, string> pinMap,
        IReadOnlySet<string> globalNodes)
    {
        if (node.Equals("0", StringComparison.OrdinalIgnoreCase))
            return "0";
        if (globalNodes.Contains(node))
            return node;
        if (pinMap.TryGetValue(node, out var mapped))
            return mapped;
        return path.Length == 0 ? node : $"{path}.{node}";
    }

    private static string MapModel(string model, IReadOnlyDictionary<string, string> modelMap) =>
        modelMap.TryGetValue(model, out var mapped) ? mapped : model;

    private static string QualifyElement(string name, string path) =>
        path.Length == 0 ? name : $"{name}:{path}";

    private static string QualifyModel(string name, string path) => $"{name}:{path}";

    private static string Evaluate(ParameterScope scope, string expression) =>
        NumericExpression.Format(scope.Evaluate(expression));

    private static bool IsTitle(
        string line,
        IReadOnlyDictionary<string, SubcircuitDefinition> subcircuits,
        RfmModel? rfm,
        string rfmSubcircuit)
    {
        if (line.StartsWith('.'))
            return false;
        var tokens = Tokenize(line);
        if (tokens.Length == 0)
            return true;
        return char.ToUpperInvariant(tokens[0][0]) switch
        {
            'R' or 'C' or 'L' => tokens.Length < 4 || !LooksLikeValue(tokens[3]),
            'V' or 'I' => tokens.Length < 4 ||
                !(LooksLikeValue(tokens[3]) ||
                  tokens[3].Equals("dc", StringComparison.OrdinalIgnoreCase) ||
                  tokens[3].Equals("ac", StringComparison.OrdinalIgnoreCase) ||
                  TransientFunctionName(tokens[3]) is not null),
            'D' or 'Q' or 'M' => true,
            'F' or 'H' => tokens.Length < 5 || !LooksLikeValue(tokens[4]),
            'G' or 'E' => tokens.Length < 6 || !LooksLikeValue(tokens[5]),
            'X' => !LooksLikeSubcircuit(tokens, subcircuits, rfm, rfmSubcircuit),
            _ => true
        };
    }

    private static bool LooksLikeValue(string token)
    {
        if ((token.StartsWith('{') && token.EndsWith('}')) ||
            (token.StartsWith('\'') && token.EndsWith('\'')) ||
            (token.StartsWith('"') && token.EndsWith('"')))
        {
            return true;
        }
        try
        {
            _ = Deck.ParseNumber(token);
            return true;
        }
        catch (FormatException)
        {
            return false;
        }
    }

    private static bool LooksLikeSubcircuit(
        string[] tokens,
        IReadOnlyDictionary<string, SubcircuitDefinition> subcircuits,
        RfmModel? rfm,
        string rfmSubcircuit)
    {
        var parameterStart = FindParameterStart(tokens, 1);
        var index = (parameterStart >= 0 ? parameterStart : tokens.Length) - 1;
        return index >= 2 && (subcircuits.ContainsKey(tokens[index]) ||
            (rfm is not null && tokens[^1].Equals(rfmSubcircuit, StringComparison.OrdinalIgnoreCase)));
    }

    private static string Head(string line)
    {
        var tokens = Tokenize(line);
        return tokens.Length == 0 ? "" : tokens[0].ToLowerInvariant();
    }

    private static string DirectiveBody(string line)
    {
        var index = line.IndexOfAny([' ', '\t']);
        return index < 0 ? "" : line[(index + 1)..];
    }

    private static int FindParameterStart(IReadOnlyList<string> tokens, int start)
    {
        for (var index = start; index < tokens.Count; index++)
        {
            if (tokens[index].Equals("params:", StringComparison.OrdinalIgnoreCase) ||
                tokens[index].Equals("param:", StringComparison.OrdinalIgnoreCase) ||
                AssignmentStartPattern().IsMatch(tokens[index]))
            {
                return index;
            }
        }
        return -1;
    }

    private static int SkipParamsMarker(IReadOnlyList<string> tokens, int index) =>
        tokens[index].EndsWith(':') ? index + 1 : index;

    private static Dictionary<string, string> ParseAssignments(string text)
    {
        var result = new Dictionary<string, string>(Names);
        var position = 0;
        while (position < text.Length)
        {
            SkipSeparators(text, ref position);
            if (position >= text.Length)
                break;
            if (text.AsSpan(position).StartsWith("params:", StringComparison.OrdinalIgnoreCase))
            {
                position += "params:".Length;
                continue;
            }
            if (text.AsSpan(position).StartsWith("param:", StringComparison.OrdinalIgnoreCase))
            {
                position += "param:".Length;
                continue;
            }
            var nameStart = position;
            if (!(char.IsLetter(text[position]) || text[position] == '_'))
                throw new InvalidDataException($"invalid parameter assignment near '{text[position..]}'");
            position++;
            while (position < text.Length &&
                (char.IsLetterOrDigit(text[position]) || text[position] is '_' or '$'))
            {
                position++;
            }
            var name = text[nameStart..position];
            while (position < text.Length && char.IsWhiteSpace(text[position]))
                position++;
            if (position >= text.Length || text[position] != '=')
                throw new InvalidDataException($"parameter '{name}' is missing '='");
            position++;
            var expressionStart = position;
            var parenthesisDepth = 0;
            var braceDepth = 0;
            var quote = '\0';
            while (position < text.Length)
            {
                var character = text[position];
                if (quote != '\0')
                {
                    if (character == quote)
                        quote = '\0';
                    position++;
                    continue;
                }
                if (character is '\'' or '"')
                {
                    quote = character;
                    position++;
                    continue;
                }
                if (character == '(') parenthesisDepth++;
                else if (character == ')') parenthesisDepth--;
                else if (character == '{') braceDepth++;
                else if (character == '}') braceDepth--;
                if (parenthesisDepth < 0 || braceDepth < 0)
                    throw new InvalidDataException($"unbalanced parameter expression for '{name}'");
                if (parenthesisDepth == 0 && braceDepth == 0 &&
                    (character == ',' || char.IsWhiteSpace(character)))
                {
                    var candidate = position;
                    while (candidate < text.Length && (text[candidate] == ',' || char.IsWhiteSpace(text[candidate])))
                        candidate++;
                    if (candidate >= text.Length || AssignmentStartPattern().IsMatch(text[candidate..]))
                        break;
                }
                position++;
            }
            if (parenthesisDepth != 0 || braceDepth != 0 || quote != '\0')
                throw new InvalidDataException($"unbalanced parameter expression for '{name}'");
            var expression = text[expressionStart..position].Trim().TrimEnd(',');
            if (expression.Length == 0)
                throw new InvalidDataException($"parameter '{name}' has an empty expression");
            result[name] = expression;
        }
        return result;
    }

    private static void MergeAssignments(IDictionary<string, string> destination, string text)
    {
        foreach (var (name, expression) in ParseAssignments(text))
            destination[name] = expression;
    }

    private static void SkipSeparators(string text, ref int position)
    {
        while (position < text.Length && (char.IsWhiteSpace(text[position]) || text[position] == ','))
            position++;
    }

    private static string[] Tokenize(string line)
    {
        var result = new List<string>();
        var token = new StringBuilder();
        var parenthesisDepth = 0;
        var braceDepth = 0;
        var quote = '\0';
        foreach (var character in line)
        {
            if (quote != '\0')
            {
                token.Append(character);
                if (character == quote)
                    quote = '\0';
                continue;
            }
            if (character is '\'' or '"')
            {
                quote = character;
                token.Append(character);
                continue;
            }
            if (character == '(') parenthesisDepth++;
            else if (character == ')') parenthesisDepth--;
            else if (character == '{') braceDepth++;
            else if (character == '}') braceDepth--;
            if (char.IsWhiteSpace(character) && parenthesisDepth == 0 && braceDepth == 0)
            {
                if (token.Length > 0)
                {
                    result.Add(token.ToString());
                    token.Clear();
                }
                continue;
            }
            token.Append(character);
        }
        if (quote != '\0' || parenthesisDepth != 0 || braceDepth != 0)
            throw new InvalidDataException($"unbalanced netlist line '{line}'");
        if (token.Length > 0)
            result.Add(token.ToString());
        return result.ToArray();
    }

    private static IReadOnlyList<string> FunctionArguments(string token, string function)
    {
        var open = token.IndexOf('(');
        if (open < 0 || !token[..open].Trim().Equals(function, StringComparison.OrdinalIgnoreCase) || !token.EndsWith(')'))
            throw new InvalidDataException($"invalid {function} syntax '{token}'");
        var body = token[(open + 1)..^1];
        var result = new List<string>();
        var start = 0;
        var parenthesisDepth = 0;
        var braceDepth = 0;
        var quote = '\0';
        for (var index = 0; index <= body.Length; index++)
        {
            var character = index < body.Length ? body[index] : ',';
            if (quote != '\0')
            {
                if (character == quote)
                    quote = '\0';
                continue;
            }
            if (character is '\'' or '"')
            {
                quote = character;
                continue;
            }
            if (character == '(') parenthesisDepth++;
            else if (character == ')') parenthesisDepth--;
            else if (character == '{') braceDepth++;
            else if (character == '}') braceDepth--;
            if ((character == ',' || char.IsWhiteSpace(character) || index == body.Length) &&
                parenthesisDepth == 0 && braceDepth == 0)
            {
                var value = body[start..index].Trim();
                if (value.Length > 0)
                    result.Add(value);
                start = index + 1;
            }
        }
        return result;
    }

    private static string? TransientFunctionName(string token)
    {
        var open = token.IndexOf('(');
        if (open <= 0)
            return null;
        var name = token[..open];
        return name.Equals("pulse", StringComparison.OrdinalIgnoreCase) ? "PULSE" :
            name.Equals("pwl", StringComparison.OrdinalIgnoreCase) ? "PWL" :
            name.Equals("sin", StringComparison.OrdinalIgnoreCase) ? "SIN" :
            name.Equals("exp", StringComparison.OrdinalIgnoreCase) ? "EXP" :
            null;
    }

    private static void ValidateTransientArgumentCount(string function, int count)
    {
        var valid = function switch
        {
            "PULSE" => count == 7,
            "PWL" => count >= 4 && count % 2 == 0,
            "SIN" => count is >= 3 and <= 6,
            "EXP" => count == 6,
            _ => false
        };
        if (!valid)
            throw new InvalidDataException($"{function} has an invalid argument count ({count})");
    }

    private static void Require(string[] tokens, int count, string syntax)
    {
        if (tokens.Length < count)
            throw new InvalidDataException($"invalid {syntax}: '{string.Join(' ', tokens)}'");
    }

    [GeneratedRegex(@"^\.model\s+(\S+)\s+([^\s(]+)\s*(.*)$", RegexOptions.IgnoreCase)]
    private static partial Regex ModelHeaderPattern();

    [GeneratedRegex(@"^[A-Za-z_][A-Za-z0-9_$]*\s*=")]
    private static partial Regex AssignmentStartPattern();

    [GeneratedRegex(@"\b([vi])\(\s*([^\s,)]+)", RegexOptions.IgnoreCase)]
    private static partial Regex OutputReferencePattern();
}
