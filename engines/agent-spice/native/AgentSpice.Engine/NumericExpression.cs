using System.Globalization;

namespace AgentSpice.Engine;

internal sealed class ParameterScope
{
    private readonly ParameterScope? _parent;
    private readonly Dictionary<string, string> _definitions;
    private readonly Dictionary<string, double> _values = new(StringComparer.OrdinalIgnoreCase);
    private readonly HashSet<string> _active = new(StringComparer.OrdinalIgnoreCase);

    internal ParameterScope(
        ParameterScope? parent = null,
        IReadOnlyDictionary<string, string>? definitions = null)
    {
        _parent = parent;
        _definitions = definitions is null
            ? new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
            : new Dictionary<string, string>(definitions, StringComparer.OrdinalIgnoreCase);
    }

    internal double Evaluate(string expression) => NumericExpression.Evaluate(expression, Resolve);

    internal double Resolve(string name)
    {
        if (_values.TryGetValue(name, out var value))
            return value;
        if (!_definitions.TryGetValue(name, out var expression))
        {
            if (_parent is not null)
                return _parent.Resolve(name);
            throw new InvalidDataException($"undefined parameter '{name}'");
        }
        if (!_active.Add(name))
            throw new InvalidDataException($"cyclic parameter definition involving '{name}'");
        try
        {
            value = Evaluate(expression);
            if (!double.IsFinite(value))
                throw new InvalidDataException($"parameter '{name}' evaluated to a non-finite value");
            _values[name] = value;
            return value;
        }
        finally
        {
            _active.Remove(name);
        }
    }
}

internal static class NumericExpression
{
    internal static double Evaluate(string expression, Func<string, double> resolveParameter)
    {
        var text = Unwrap(expression.Trim().TrimEnd(','));
        if (text.Length == 0)
            throw new InvalidDataException("empty numeric expression");
        var parser = new Parser(text, resolveParameter);
        var value = parser.ParseConditional();
        parser.RequireEnd();
        return value;
    }

    private static string Unwrap(string text)
    {
        while (text.Length >= 2 &&
            ((text[0] == '{' && text[^1] == '}') ||
             (text[0] == '\'' && text[^1] == '\'') ||
             (text[0] == '"' && text[^1] == '"')))
        {
            text = text[1..^1].Trim();
        }
        return text;
    }

    private sealed class Parser
    {
        private readonly string _text;
        private readonly Func<string, double> _resolveParameter;
        private int _position;

        internal Parser(string text, Func<string, double> resolveParameter)
        {
            _text = text;
            _resolveParameter = resolveParameter;
        }

        internal double ParseConditional()
        {
            var condition = ParseLogicalOr();
            SkipWhiteSpace();
            if (!Consume("?"))
                return condition;
            var whenTrue = ParseConditional();
            Require(":");
            var whenFalse = ParseConditional();
            return IsTrue(condition) ? whenTrue : whenFalse;
        }

        internal void RequireEnd()
        {
            SkipWhiteSpace();
            if (_position != _text.Length)
                throw Error($"unexpected token '{_text[_position..]}'");
        }

        private double ParseLogicalOr()
        {
            var value = ParseLogicalAnd();
            while (Consume("||"))
            {
                var right = ParseLogicalAnd();
                value = IsTrue(value) || IsTrue(right) ? 1.0 : 0.0;
            }
            return value;
        }

        private double ParseLogicalAnd()
        {
            var value = ParseEquality();
            while (Consume("&&"))
            {
                var right = ParseEquality();
                value = IsTrue(value) && IsTrue(right) ? 1.0 : 0.0;
            }
            return value;
        }

        private double ParseEquality()
        {
            var value = ParseComparison();
            while (true)
            {
                if (Consume("=="))
                    value = value == ParseComparison() ? 1.0 : 0.0;
                else if (Consume("!="))
                    value = value != ParseComparison() ? 1.0 : 0.0;
                else
                    return value;
            }
        }

        private double ParseComparison()
        {
            var value = ParseAdditive();
            while (true)
            {
                if (Consume("<="))
                    value = value <= ParseAdditive() ? 1.0 : 0.0;
                else if (Consume(">="))
                    value = value >= ParseAdditive() ? 1.0 : 0.0;
                else if (Consume("<"))
                    value = value < ParseAdditive() ? 1.0 : 0.0;
                else if (Consume(">"))
                    value = value > ParseAdditive() ? 1.0 : 0.0;
                else
                    return value;
            }
        }

        private double ParseAdditive()
        {
            var value = ParseMultiplicative();
            while (true)
            {
                if (Consume("+"))
                    value += ParseMultiplicative();
                else if (Consume("-"))
                    value -= ParseMultiplicative();
                else
                    return value;
            }
        }

        private double ParseMultiplicative()
        {
            var value = ParseUnary();
            while (true)
            {
                if (Peek("**"))
                    return value;
                if (Consume("*"))
                    value *= ParseUnary();
                else if (Consume("/"))
                    value /= ParseUnary();
                else if (Consume("%"))
                    value %= ParseUnary();
                else
                    return value;
            }
        }

        private double ParsePower()
        {
            var value = ParsePrimary();
            if (Consume("**") || Consume("^"))
                value = Math.Pow(value, ParseUnary());
            return value;
        }

        private double ParseUnary()
        {
            if (Consume("+"))
                return ParseUnary();
            if (Consume("-"))
                return -ParseUnary();
            if (Consume("!"))
                return IsTrue(ParseUnary()) ? 0.0 : 1.0;
            return ParsePower();
        }

        private double ParsePrimary()
        {
            SkipWhiteSpace();
            if (Consume("("))
            {
                var value = ParseConditional();
                Require(")");
                return value;
            }
            if (_position < _text.Length &&
                (char.IsDigit(_text[_position]) || _text[_position] == '.'))
            {
                return ParseNumber();
            }
            var identifier = ParseIdentifier();
            SkipWhiteSpace();
            if (!Consume("("))
            {
                if (identifier.Equals("pi", StringComparison.OrdinalIgnoreCase))
                    return Math.PI;
                if (identifier.Equals("e", StringComparison.OrdinalIgnoreCase))
                    return Math.E;
                if (identifier.Equals("true", StringComparison.OrdinalIgnoreCase))
                    return 1.0;
                if (identifier.Equals("false", StringComparison.OrdinalIgnoreCase))
                    return 0.0;
                return _resolveParameter(identifier);
            }

            var arguments = new List<double>();
            SkipWhiteSpace();
            if (!Consume(")"))
            {
                while (true)
                {
                    arguments.Add(ParseConditional());
                    if (Consume(")"))
                        break;
                    Require(",");
                }
            }
            return EvaluateFunction(identifier, arguments);
        }

        private double ParseNumber()
        {
            var start = _position;
            var seenExponent = false;
            while (_position < _text.Length)
            {
                var character = _text[_position];
                if (char.IsDigit(character) || character == '.')
                {
                    _position++;
                    continue;
                }
                if ((character is 'e' or 'E' or 'd' or 'D') && !seenExponent)
                {
                    seenExponent = true;
                    _position++;
                    if (_position < _text.Length && _text[_position] is '+' or '-')
                        _position++;
                    continue;
                }
                break;
            }
            while (_position < _text.Length && char.IsLetter(_text[_position]))
                _position++;
            var token = _text[start.._position];
            try
            {
                return Deck.ParseNumber(token);
            }
            catch (FormatException exception)
            {
                throw Error($"invalid number '{token}'", exception);
            }
        }

        private string ParseIdentifier()
        {
            SkipWhiteSpace();
            if (_position >= _text.Length ||
                !(char.IsLetter(_text[_position]) || _text[_position] == '_'))
            {
                throw Error("expected a number, parameter, or function");
            }
            var start = _position++;
            while (_position < _text.Length &&
                (char.IsLetterOrDigit(_text[_position]) || _text[_position] is '_' or '$'))
            {
                _position++;
            }
            return _text[start.._position];
        }

        private static double EvaluateFunction(string name, IReadOnlyList<double> arguments)
        {
            double Unary(Func<double, double> function)
            {
                RequireArgumentCount(name, arguments, 1);
                return function(arguments[0]);
            }

            return name.ToLowerInvariant() switch
            {
                "abs" => Unary(Math.Abs),
                "sqrt" => Unary(Math.Sqrt),
                "exp" => Unary(Math.Exp),
                "ln" or "log" => Unary(Math.Log),
                "log10" => Unary(Math.Log10),
                "sin" => Unary(Math.Sin),
                "cos" => Unary(Math.Cos),
                "tan" => Unary(Math.Tan),
                "asin" => Unary(Math.Asin),
                "acos" => Unary(Math.Acos),
                "atan" => Unary(Math.Atan),
                "floor" => Unary(Math.Floor),
                "ceil" => Unary(Math.Ceiling),
                "int" => Unary(Math.Truncate),
                "min" => Aggregate(name, arguments, values => values.Min()),
                "max" => Aggregate(name, arguments, values => values.Max()),
                "pow" or "pwr" => Binary(name, arguments, Math.Pow),
                "limit" => Ternary(name, arguments, (value, minimum, maximum) => Math.Clamp(value, minimum, maximum)),
                "if" => Ternary(name, arguments, (condition, whenTrue, whenFalse) => IsTrue(condition) ? whenTrue : whenFalse),
                _ => throw new InvalidDataException($"unsupported numeric function '{name}'")
            };
        }

        private static double Binary(
            string name,
            IReadOnlyList<double> arguments,
            Func<double, double, double> function)
        {
            RequireArgumentCount(name, arguments, 2);
            return function(arguments[0], arguments[1]);
        }

        private static double Ternary(
            string name,
            IReadOnlyList<double> arguments,
            Func<double, double, double, double> function)
        {
            RequireArgumentCount(name, arguments, 3);
            return function(arguments[0], arguments[1], arguments[2]);
        }

        private static double Aggregate(
            string name,
            IReadOnlyList<double> arguments,
            Func<IEnumerable<double>, double> function)
        {
            if (arguments.Count == 0)
                throw new InvalidDataException($"function '{name}' requires at least one argument");
            return function(arguments);
        }

        private static void RequireArgumentCount(
            string name,
            IReadOnlyCollection<double> arguments,
            int expected)
        {
            if (arguments.Count != expected)
                throw new InvalidDataException($"function '{name}' requires {expected} argument(s)");
        }

        private bool Peek(string token)
        {
            SkipWhiteSpace();
            return _text.AsSpan(_position).StartsWith(token, StringComparison.Ordinal);
        }

        private bool Consume(string token)
        {
            if (!Peek(token))
                return false;
            _position += token.Length;
            return true;
        }

        private void Require(string token)
        {
            if (!Consume(token))
                throw Error($"expected '{token}'");
        }

        private void SkipWhiteSpace()
        {
            while (_position < _text.Length && char.IsWhiteSpace(_text[_position]))
                _position++;
        }

        private InvalidDataException Error(string message, Exception? inner = null) =>
            new($"invalid numeric expression '{_text}' at column {_position + 1}: {message}", inner);
    }

    private static bool IsTrue(double value) => value != 0.0 && !double.IsNaN(value);

    internal static string Format(double value) => value.ToString("G17", CultureInfo.InvariantCulture);
}
