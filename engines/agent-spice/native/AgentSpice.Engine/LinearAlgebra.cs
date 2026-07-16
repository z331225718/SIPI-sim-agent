using System.Numerics;
using System.Diagnostics;

namespace AgentSpice.Engine;

internal interface IComplexFactorization
{
    int Size { get; }
    Complex[] Solve(IReadOnlyList<Complex> sourceRightHandSide);
}

internal interface IRealFactorization : IComplexFactorization
{
    double[] SolveReal(IReadOnlyList<Complex> sourceRightHandSide);
}

internal interface IFactorizationSnapshot
{
    IComplexFactorization Snapshot();
}

internal readonly struct SolutionVector
{
    private readonly double[]? _real;
    private readonly Complex[]? _complex;

    internal SolutionVector(double[] values)
    {
        _real = values;
        _complex = null;
    }

    internal SolutionVector(Complex[] values)
    {
        _real = null;
        _complex = values;
    }

    internal double Real(int index) => _real is not null ? _real[index] : _complex![index].Real;
    internal Complex Complex(int index) => _complex is not null ? _complex[index] : new Complex(_real![index], 0.0);
}

internal sealed class SparseMatrix
{
    private readonly Dictionary<int, Complex>[] _rows;
    private bool _preservePattern;
    private int[][]? _frozenColumns;
    private int[]? _frozenRowOffsets;
    private Complex[]? _frozenValues;
    private Dictionary<int, int>[]? _frozenPositions;

    internal int Size { get; }
    internal int NonZeros { get; private set; }
    internal int PatternVersion { get; private set; }
    internal bool IsReal { get; private set; } = true;
    internal IReadOnlyList<Dictionary<int, Complex>> Rows
    {
        get
        {
            MaterializeRows();
            return _rows;
        }
    }

    internal SparseMatrix(int size)
    {
        if (size <= 0)
            throw new ArgumentOutOfRangeException(nameof(size));
        Size = size;
        _rows = Enumerable.Range(0, size).Select(_ => new Dictionary<int, Complex>()).ToArray();
    }

    internal void Add(int row, int column, Complex value)
    {
        if (value == Complex.Zero)
            return;
        if (value.Imaginary != 0.0)
            IsReal = false;
        if (_frozenValues is not null)
        {
            if (_frozenPositions![row].TryGetValue(column, out var position))
            {
                _frozenValues[position] += value;
                return;
            }
            MaterializeRows();
        }
        var entries = _rows[row];
        if (!entries.TryGetValue(column, out var existing))
        {
            entries[column] = value;
            NonZeros++;
            PatternVersion++;
            _frozenColumns = null;
            return;
        }
        var updated = existing + value;
        if (updated == Complex.Zero)
        {
            if (_preservePattern)
                entries[column] = Complex.Zero;
            else
            {
                entries.Remove(column);
                NonZeros--;
                PatternVersion++;
            }
        }
        else
        {
            entries[column] = updated;
        }
    }

    internal void FreezePattern()
    {
        _preservePattern = true;
        if (_frozenValues is not null)
            return;
        _frozenColumns = new int[Size][];
        _frozenRowOffsets = new int[Size + 1];
        _frozenPositions = new Dictionary<int, int>[Size];
        for (var row = 0; row < Size; row++)
            _frozenRowOffsets[row + 1] = checked(_frozenRowOffsets[row] + _rows[row].Count);
        _frozenValues = new Complex[_frozenRowOffsets[^1]];
        for (var row = 0; row < Size; row++)
        {
            var columns = _rows[row].Keys.ToArray();
            Array.Sort(columns);
            var positions = new Dictionary<int, int>(columns.Length);
            for (var index = 0; index < columns.Length; index++)
            {
                var position = _frozenRowOffsets[row] + index;
                _frozenValues[position] = _rows[row][columns[index]];
                positions[columns[index]] = position;
            }
            _frozenColumns[row] = columns;
            _frozenPositions[row] = positions;
        }
    }

    internal void ClearValues()
    {
        if (!_preservePattern)
            throw new InvalidOperationException("sparse matrix pattern must be frozen before reuse");
        if (_frozenColumns is null || _frozenValues is null)
            throw new InvalidOperationException("sparse matrix pattern changed without being refrozen");
        IsReal = true;
        Array.Clear(_frozenValues);
    }

    internal bool TryGetFrozenPosition(int row, int column, out int position)
    {
        if (_frozenPositions is null)
        {
            position = -1;
            return false;
        }
        return _frozenPositions[row].TryGetValue(column, out position);
    }

    internal void AddFrozen(int position, Complex value)
    {
        if (_frozenValues is null)
            throw new InvalidOperationException("sparse matrix values are not frozen");
        if (value.Imaginary != 0.0)
            IsReal = false;
        _frozenValues[position] += value;
    }

    internal Complex[] CloneFrozenValues()
    {
        if (_frozenValues is null)
            throw new InvalidOperationException("sparse matrix values are not frozen");
        return _frozenValues.ToArray();
    }

    internal void SetFrozenAffineValues(Complex[] constant, Complex[] slope, double parameter)
    {
        if (_frozenValues is null)
            throw new InvalidOperationException("sparse matrix values are not frozen");
        if (constant.Length != _frozenValues.Length || slope.Length != _frozenValues.Length)
            throw new ArgumentException("affine sparse matrix template pattern does not match matrix");
        IsReal = true;
        for (var index = 0; index < _frozenValues.Length; index++)
        {
            var value = constant[index] + slope[index] * parameter;
            _frozenValues[index] = value;
            if (value.Imaginary != 0.0)
                IsReal = false;
        }
    }

    internal bool TryGetFrozenData(out int[] rowOffsets, out Complex[] values)
    {
        if (_frozenRowOffsets is null || _frozenValues is null)
        {
            rowOffsets = [];
            values = [];
            return false;
        }
        rowOffsets = _frozenRowOffsets;
        values = _frozenValues;
        return true;
    }

    internal void GetRowData(int row, out int[] columns, out Complex[] values)
    {
        if (_frozenValues is not null)
        {
            columns = _frozenColumns![row];
            var offset = _frozenRowOffsets![row];
            values = new Complex[_frozenRowOffsets[row + 1] - offset];
            Array.Copy(_frozenValues, offset, values, 0, values.Length);
            return;
        }
        columns = _rows[row].Keys.ToArray();
        values = new Complex[columns.Length];
        for (var index = 0; index < columns.Length; index++)
            values[index] = _rows[row][columns[index]];
    }

    private void MaterializeRows()
    {
        if (_frozenValues is null)
            return;
        for (var row = 0; row < Size; row++)
            for (var index = 0; index < _frozenColumns![row].Length; index++)
                _rows[row][_frozenColumns[row][index]] = _frozenValues[_frozenRowOffsets![row] + index];
        _frozenColumns = null;
        _frozenRowOffsets = null;
        _frozenValues = null;
        _frozenPositions = null;
    }

    internal Complex[,] ToDense()
    {
        var result = new Complex[Size, Size];
        if (_frozenValues is not null)
        {
            for (var row = 0; row < Size; row++)
                for (var index = 0; index < _frozenColumns![row].Length; index++)
                    result[row, _frozenColumns[row][index]] = _frozenValues[_frozenRowOffsets![row] + index];
            return result;
        }
        for (var row = 0; row < Size; row++)
            foreach (var (column, value) in _rows[row]) result[row, column] = value;
        return result;
    }

}

internal sealed class SparseLuPlan
{
    private readonly Dictionary<int, int>[] _positions;
    private readonly int[][] _sourceColumns;
    private readonly int[][] _sourcePositions;

    internal int Size { get; }
    internal int[] Pivots { get; }
    internal int[] RowOrigins { get; }
    internal int[] RowOffsets { get; }
    internal int[] FlatColumns { get; }
    internal int[] DiagonalPositions { get; }
    internal int[] ActiveOffsets { get; }
    internal int[] ActivePositions { get; }
    internal int[] TargetOffsets { get; }
    internal int[] TargetFactorPositions { get; }
    internal int[] TargetUpdateOffsets { get; }
    internal int[] PivotUpdatePositions { get; }
    internal int[] TargetUpdatePositions { get; }
    internal int FactorCount => FlatColumns.Length;

    private SparseLuPlan(
        int size,
        int[] pivots,
        int[] rowOrigins,
        Dictionary<int, int>[] positions,
        int[][] sourceColumns,
        int[][] sourcePositions,
        int[] rowOffsets,
        int[] flatColumns,
        int[] diagonalPositions,
        int[] activeOffsets,
        int[] activePositions,
        int[] targetOffsets,
        int[] targetFactorPositions,
        int[] targetUpdateOffsets,
        int[] pivotUpdatePositions,
        int[] targetUpdatePositions)
    {
        Size = size;
        Pivots = pivots;
        RowOrigins = rowOrigins;
        _positions = positions;
        _sourceColumns = sourceColumns;
        _sourcePositions = sourcePositions;
        RowOffsets = rowOffsets;
        FlatColumns = flatColumns;
        DiagonalPositions = diagonalPositions;
        ActiveOffsets = activeOffsets;
        ActivePositions = activePositions;
        TargetOffsets = targetOffsets;
        TargetFactorPositions = targetFactorPositions;
        TargetUpdateOffsets = targetUpdateOffsets;
        PivotUpdatePositions = pivotUpdatePositions;
        TargetUpdatePositions = targetUpdatePositions;
    }

    internal static SparseLuPlan Create(
        SparseMatrix source,
        IReadOnlyList<int> pivots,
        IReadOnlyList<int[]> factorColumns)
    {
        if (pivots.Count != source.Size)
            throw new ArgumentException("pivot count does not match matrix size", nameof(pivots));
        if (factorColumns.Count != source.Size)
            throw new ArgumentException("factor row count does not match matrix size", nameof(factorColumns));

        var originalColumns = new int[source.Size][];
        for (var row = 0; row < source.Size; row++)
        {
            source.GetRowData(row, out var columns, out _);
            originalColumns[row] = columns.ToArray();
            Array.Sort(originalColumns[row]);
        }
        var rowOrigins = Enumerable.Range(0, source.Size).ToArray();
        for (var column = 0; column < source.Size; column++)
        {
            var pivot = pivots[column];
            if (pivot < column || pivot >= source.Size)
                throw new ArgumentException("invalid sparse pivot sequence", nameof(pivots));
            if (pivot != column)
                (rowOrigins[column], rowOrigins[pivot]) = (rowOrigins[pivot], rowOrigins[column]);
        }

        var rowColumns = new int[source.Size][];
        var positions = new Dictionary<int, int>[source.Size];
        var columnRows = Enumerable.Range(0, source.Size).Select(_ => new List<int>()).ToArray();
        for (var row = 0; row < source.Size; row++)
        {
            var columns = factorColumns[row].ToArray();
            Array.Sort(columns);
            rowColumns[row] = columns;
            var rowPositions = new Dictionary<int, int>(columns.Length);
            for (var index = 0; index < columns.Length; index++)
            {
                rowPositions[columns[index]] = index;
                columnRows[columns[index]].Add(row);
            }
            if (!rowPositions.ContainsKey(row))
                throw new InvalidOperationException("sparse pivot is absent from the symbolic pattern");
            positions[row] = rowPositions;
        }

        var rowOffsets = new int[source.Size + 1];
        for (var row = 0; row < source.Size; row++)
            rowOffsets[row + 1] = checked(rowOffsets[row] + rowColumns[row].Length);
        var flatColumns = new int[rowOffsets[^1]];
        var diagonalPositions = new int[source.Size];
        for (var row = 0; row < source.Size; row++)
        {
            rowColumns[row].CopyTo(flatColumns, rowOffsets[row]);
            diagonalPositions[row] = rowOffsets[row] + positions[row][row];
        }
        int FlatPosition(int row, int column) => rowOffsets[row] + positions[row][column];

        var sourceColumns = new int[source.Size][];
        var sourcePositions = new int[source.Size][];
        for (var row = 0; row < source.Size; row++)
        {
            var columns = originalColumns[rowOrigins[row]];
            sourceColumns[row] = columns;
            var mapped = new int[columns.Length];
            for (var index = 0; index < columns.Length; index++)
                mapped[index] = FlatPosition(row, columns[index]);
            sourcePositions[row] = mapped;
        }

        var activeOffsets = new int[source.Size + 1];
        var activePositions = new List<int>();
        var targetOffsets = new int[source.Size + 1];
        var targetFactorPositions = new List<int>();
        var targetUpdateOffsets = new List<int> { 0 };
        var pivotUpdatePositions = new List<int>();
        var targetUpdatePositions = new List<int>();
        for (var column = 0; column < source.Size; column++)
        {
            foreach (var row in columnRows[column])
                if (row >= column) activePositions.Add(FlatPosition(row, column));
            activeOffsets[column + 1] = activePositions.Count;

            foreach (var row in columnRows[column])
            {
                if (row <= column)
                    continue;
                targetFactorPositions.Add(FlatPosition(row, column));
                foreach (var upperColumn in rowColumns[column])
                {
                    if (upperColumn <= column)
                        continue;
                    pivotUpdatePositions.Add(FlatPosition(column, upperColumn));
                    targetUpdatePositions.Add(FlatPosition(row, upperColumn));
                }
                targetUpdateOffsets.Add(pivotUpdatePositions.Count);
            }
            targetOffsets[column + 1] = targetFactorPositions.Count;
        }
        return new SparseLuPlan(
            source.Size,
            pivots.ToArray(),
            rowOrigins,
            positions,
            sourceColumns,
            sourcePositions,
            rowOffsets,
            flatColumns,
            diagonalPositions,
            activeOffsets,
            activePositions.ToArray(),
            targetOffsets,
            targetFactorPositions.ToArray(),
            targetUpdateOffsets.ToArray(),
            pivotUpdatePositions.ToArray(),
            targetUpdatePositions.ToArray());
    }

    internal bool Supports(SparseMatrix source)
    {
        if (source.Size != Size)
            return false;
        for (var row = 0; row < Size; row++)
        {
            source.GetRowData(RowOrigins[row], out var columns, out _);
            foreach (var column in columns)
                if (!_positions[row].ContainsKey(column)) return false;
        }
        return true;
    }

    internal int Position(int row, int column) => _positions[row][column];

    internal int[] SourcePositions(int row, int[] columns)
    {
        if (columns.AsSpan().SequenceEqual(_sourceColumns[row]))
            return _sourcePositions[row];
        var positions = new int[columns.Length];
        for (var index = 0; index < columns.Length; index++)
            positions[index] = RowOffsets[row] + Position(row, columns[index]);
        return positions;
    }

    internal int[] CachedSourcePositions(int row) => _sourcePositions[row];
}

internal sealed class SparsePlanRejectedException : InvalidOperationException
{
    internal SparsePlanRejectedException(string message) : base(message)
    {
    }
}

internal sealed class ComplexLu : IComplexFactorization
{
    private readonly Complex[,] _factors;
    private readonly int[] _pivots;
    private readonly double[] _rowScales;

    public int Size => _pivots.Length;

    internal ComplexLu(Complex[,] source)
    {
        var size = source.GetLength(0);
        if (source.GetLength(1) != size)
            throw new ArgumentException("linear system matrix must be square");
        _factors = (Complex[,])source.Clone();
        _pivots = new int[size];
        _rowScales = new double[size];
        for (var row = 0; row < size; row++)
        {
            var scale = 0.0;
            for (var column = 0; column < size; column++)
                scale = Math.Max(scale, Complex.Abs(_factors[row, column]));
            if (!double.IsFinite(scale) || scale < 1e-30)
                throw new InvalidOperationException("singular or ill-conditioned matrix");
            _rowScales[row] = scale;
            for (var column = 0; column < size; column++)
                _factors[row, column] /= scale;
        }

        for (var column = 0; column < size; column++)
        {
            var pivot = column;
            for (var row = column + 1; row < size; row++)
                if (Complex.Abs(_factors[row, column]) > Complex.Abs(_factors[pivot, column])) pivot = row;
            var pivotMagnitude = Complex.Abs(_factors[pivot, column]);
            if (!double.IsFinite(pivotMagnitude) || pivotMagnitude < 1e-30)
                throw new InvalidOperationException("singular or ill-conditioned matrix");
            _pivots[column] = pivot;
            if (pivot != column)
                for (var index = 0; index < size; index++)
                    (_factors[column, index], _factors[pivot, index]) = (_factors[pivot, index], _factors[column, index]);
            for (var row = column + 1; row < size; row++)
            {
                _factors[row, column] /= _factors[column, column];
                for (var index = column + 1; index < size; index++)
                    _factors[row, index] -= _factors[row, column] * _factors[column, index];
            }
        }
    }

    public Complex[] Solve(IReadOnlyList<Complex> sourceRightHandSide)
    {
        if (sourceRightHandSide.Count != Size)
            throw new ArgumentException("right-hand side length does not match matrix");
        var result = new Complex[Size];
        for (var index = 0; index < Size; index++)
            result[index] = sourceRightHandSide[index] / _rowScales[index];
        for (var column = 0; column < Size; column++)
            if (_pivots[column] != column)
                (result[column], result[_pivots[column]]) = (result[_pivots[column]], result[column]);
        for (var row = 1; row < Size; row++)
            for (var column = 0; column < row; column++)
                result[row] -= _factors[row, column] * result[column];
        for (var row = Size - 1; row >= 0; row--)
        {
            for (var column = row + 1; column < Size; column++)
                result[row] -= _factors[row, column] * result[column];
            result[row] /= _factors[row, row];
        }
        return result;
    }
}

internal sealed class SparseRealLu : IRealFactorization
{
    private readonly Dictionary<int, double>[] _factors;
    private readonly HashSet<int>[] _columnRows;
    private readonly int[] _pivots;
    private readonly int[][] _solveColumns;
    private readonly double[][] _solveValues;
    private readonly double[] _diagonal;
    private readonly double[] _rowScales;

    public int Size => _pivots.Length;
    internal IReadOnlyList<int> Pivots => _pivots;

    internal SparseRealLu(SparseMatrix source, bool optimizeRepeatedSolve)
    {
        _factors = new Dictionary<int, double>[source.Size];
        _rowScales = new double[source.Size];
        for (var row = 0; row < source.Size; row++)
        {
            var converted = new Dictionary<int, double>(source.Rows[row].Count);
            foreach (var (column, value) in source.Rows[row]) converted[column] = value.Real;
            var scale = converted.Values.Select(Math.Abs).DefaultIfEmpty(0.0).Max();
            if (!double.IsFinite(scale) || scale < 1e-30)
                throw new InvalidOperationException("singular or ill-conditioned matrix");
            _rowScales[row] = scale;
            foreach (var column in converted.Keys.ToArray())
                converted[column] /= scale;
            _factors[row] = converted;
        }
        _columnRows = Enumerable.Range(0, source.Size).Select(_ => new HashSet<int>()).ToArray();
        for (var row = 0; row < source.Size; row++)
            foreach (var column in _factors[row].Keys) _columnRows[column].Add(row);
        _pivots = new int[source.Size];
        for (var column = 0; column < Size; column++)
        {
            var maximumMagnitude = 0.0;
            foreach (var row in _columnRows[column])
            {
                if (row < column)
                    continue;
                maximumMagnitude = Math.Max(maximumMagnitude, Math.Abs(_factors[row][column]));
            }
            if (!double.IsFinite(maximumMagnitude) || maximumMagnitude < 1e-30)
                throw new InvalidOperationException("singular or ill-conditioned matrix");

            var pivot = -1;
            var pivotActiveEntries = int.MaxValue;
            var pivotMagnitude = 0.0;
            var stableMagnitude = maximumMagnitude * 1e-3;
            foreach (var row in _columnRows[column])
            {
                if (row < column)
                    continue;
                var magnitude = Math.Abs(_factors[row][column]);
                if (magnitude < stableMagnitude)
                    continue;
                var activeEntries = 0;
                foreach (var index in _factors[row].Keys)
                    if (index >= column) activeEntries++;
                if (activeEntries > pivotActiveEntries ||
                    (activeEntries == pivotActiveEntries && magnitude <= pivotMagnitude))
                    continue;
                pivot = row;
                pivotActiveEntries = activeEntries;
                pivotMagnitude = magnitude;
            }
            if (pivot < 0)
                throw new InvalidOperationException("singular or ill-conditioned matrix");
            _pivots[column] = pivot;
            if (pivot != column)
                SwapRows(column, pivot);

            var pivotRow = _factors[column];
            var pivotValue = pivotRow[column];
            foreach (var row in _columnRows[column])
            {
                if (row <= column)
                    continue;
                var target = _factors[row];
                if (!target.TryGetValue(column, out var entry))
                    continue;
                var factor = entry / pivotValue;
                target[column] = factor;
                foreach (var (index, value) in pivotRow)
                {
                    if (index <= column)
                        continue;
                    var updated = target.GetValueOrDefault(index) - factor * value;
                    if (!target.ContainsKey(index))
                        _columnRows[index].Add(row);
                    target[index] = updated;
                }
            }
        }

        if (optimizeRepeatedSolve)
        {
            _solveColumns = new int[Size][];
            _solveValues = new double[Size][];
            _diagonal = new double[Size];
            for (var row = 0; row < Size; row++)
            {
                var columns = _factors[row].Keys.ToArray();
                Array.Sort(columns);
                var values = new double[columns.Length];
                for (var index = 0; index < columns.Length; index++)
                    values[index] = _factors[row][columns[index]];
                _solveColumns[row] = columns;
                _solveValues[row] = values;
                _diagonal[row] = _factors[row][row];
            }
        }
        else
        {
            _solveColumns = [];
            _solveValues = [];
            _diagonal = [];
        }
    }

    internal int[][] CaptureFactorColumns()
    {
        var result = new int[Size][];
        for (var row = 0; row < Size; row++)
        {
            result[row] = _factors[row].Keys.ToArray();
            Array.Sort(result[row]);
        }
        return result;
    }

    private void SwapRows(int first, int second)
    {
        var firstColumns = _factors[first].Keys.ToArray();
        var secondColumns = _factors[second].Keys.ToArray();
        foreach (var column in firstColumns)
        {
            if (_factors[second].ContainsKey(column))
                continue;
            _columnRows[column].Remove(first);
            _columnRows[column].Add(second);
        }
        foreach (var column in secondColumns)
        {
            if (_factors[first].ContainsKey(column))
                continue;
            _columnRows[column].Remove(second);
            _columnRows[column].Add(first);
        }
        (_factors[first], _factors[second]) = (_factors[second], _factors[first]);
    }

    public Complex[] Solve(IReadOnlyList<Complex> sourceRightHandSide)
    {
        if (sourceRightHandSide.Count != Size)
            throw new ArgumentException("right-hand side length does not match matrix");
        var realRightHandSide = true;
        for (var index = 0; index < Size; index++)
            if (sourceRightHandSide[index].Imaginary != 0.0) realRightHandSide = false;
        if (realRightHandSide)
        {
            var real = SolveReal(sourceRightHandSide);
            var converted = new Complex[Size];
            for (var index = 0; index < Size; index++) converted[index] = new Complex(real[index], 0.0);
            return converted;
        }
        var result = new Complex[Size];
        for (var index = 0; index < Size; index++)
            result[index] = sourceRightHandSide[index] / _rowScales[index];
        for (var column = 0; column < Size; column++)
            if (_pivots[column] != column)
                (result[column], result[_pivots[column]]) = (result[_pivots[column]], result[column]);
        for (var row = 1; row < Size; row++)
            foreach (var (column, value) in _factors[row])
                if (column < row) result[row] -= value * result[column];
        for (var row = Size - 1; row >= 0; row--)
        {
            foreach (var (column, value) in _factors[row])
                if (column > row) result[row] -= value * result[column];
            result[row] /= _factors[row][row];
        }
        return result;
    }

    public double[] SolveReal(IReadOnlyList<Complex> sourceRightHandSide)
    {
        if (sourceRightHandSide.Count != Size)
            throw new ArgumentException("right-hand side length does not match matrix");
        var real = new double[Size];
        for (var index = 0; index < Size; index++)
        {
            if (sourceRightHandSide[index].Imaginary != 0.0)
                throw new ArgumentException("real factorization requires a real right-hand side");
            real[index] = sourceRightHandSide[index].Real / _rowScales[index];
        }
        for (var column = 0; column < Size; column++)
            if (_pivots[column] != column)
                (real[column], real[_pivots[column]]) = (real[_pivots[column]], real[column]);
        if (_solveColumns.Length == 0)
        {
            for (var row = 1; row < Size; row++)
                foreach (var (column, value) in _factors[row])
                    if (column < row) real[row] -= value * real[column];
            for (var row = Size - 1; row >= 0; row--)
            {
                foreach (var (column, value) in _factors[row])
                    if (column > row) real[row] -= value * real[column];
                real[row] /= _factors[row][row];
            }
            return real;
        }
        for (var row = 1; row < Size; row++)
        {
            var columns = _solveColumns[row];
            var values = _solveValues[row];
            for (var index = 0; index < columns.Length && columns[index] < row; index++)
                real[row] -= values[index] * real[columns[index]];
        }
        for (var row = Size - 1; row >= 0; row--)
        {
            var columns = _solveColumns[row];
            var values = _solveValues[row];
            for (var index = columns.Length - 1; index >= 0 && columns[index] > row; index--)
                real[row] -= values[index] * real[columns[index]];
            real[row] /= _diagonal[row];
        }
        return real;
    }
}

internal sealed class SparseComplexLu : IComplexFactorization
{
    private Dictionary<int, Complex>[] _factors;
    private HashSet<int>[] _columnRows;
    private readonly int[] _pivots;
    private readonly int[][] _solveColumns;
    private readonly Complex[][] _solveValues;
    private readonly Complex[] _diagonal;
    private readonly double[] _rowScales;

    public int Size => _pivots.Length;
    internal IReadOnlyList<int> Pivots => _pivots;

    internal SparseComplexLu(SparseMatrix source, bool optimizeRepeatedSolve)
    {
        _factors = source.Rows.Select(row => new Dictionary<int, Complex>(row)).ToArray();
        _rowScales = new double[source.Size];
        for (var row = 0; row < source.Size; row++)
        {
            var scale = _factors[row].Values.Select(Complex.Abs).DefaultIfEmpty(0.0).Max();
            if (!double.IsFinite(scale) || scale < 1e-30)
                throw new InvalidOperationException("singular or ill-conditioned matrix");
            _rowScales[row] = scale;
            foreach (var column in _factors[row].Keys.ToArray())
                _factors[row][column] /= scale;
        }
        _columnRows = Enumerable.Range(0, source.Size).Select(_ => new HashSet<int>()).ToArray();
        for (var row = 0; row < source.Size; row++)
            foreach (var column in _factors[row].Keys) _columnRows[column].Add(row);
        _pivots = new int[source.Size];
        for (var column = 0; column < Size; column++)
        {
            var maximumMagnitude = 0.0;
            foreach (var row in _columnRows[column])
            {
                if (row < column)
                    continue;
                maximumMagnitude = Math.Max(maximumMagnitude, Complex.Abs(_factors[row][column]));
            }
            if (!double.IsFinite(maximumMagnitude) || maximumMagnitude < 1e-30)
                throw new InvalidOperationException("singular or ill-conditioned matrix");

            var pivot = -1;
            var pivotActiveEntries = int.MaxValue;
            var pivotMagnitude = 0.0;
            var stableMagnitude = maximumMagnitude * 1e-3;
            foreach (var row in _columnRows[column])
            {
                if (row < column)
                    continue;
                var magnitude = Complex.Abs(_factors[row][column]);
                if (magnitude < stableMagnitude)
                    continue;
                var activeEntries = 0;
                foreach (var index in _factors[row].Keys)
                    if (index >= column) activeEntries++;
                if (activeEntries > pivotActiveEntries ||
                    (activeEntries == pivotActiveEntries && magnitude <= pivotMagnitude))
                    continue;
                pivot = row;
                pivotActiveEntries = activeEntries;
                pivotMagnitude = magnitude;
            }
            if (pivot < 0)
                throw new InvalidOperationException("singular or ill-conditioned matrix");
            _pivots[column] = pivot;
            if (pivot != column)
                SwapRows(column, pivot);

            var pivotRow = _factors[column];
            var pivotValue = pivotRow[column];
            foreach (var row in _columnRows[column])
            {
                if (row <= column)
                    continue;
                var target = _factors[row];
                if (!target.TryGetValue(column, out var entry))
                    continue;
                var factor = entry / pivotValue;
                target[column] = factor;
                foreach (var (index, value) in pivotRow)
                {
                    if (index <= column)
                        continue;
                    var updated = target.GetValueOrDefault(index) - factor * value;
                    if (!target.ContainsKey(index))
                        _columnRows[index].Add(row);
                    target[index] = updated;
                }
            }
        }

        if (optimizeRepeatedSolve)
        {
            _solveColumns = new int[Size][];
            _solveValues = new Complex[Size][];
            _diagonal = new Complex[Size];
            for (var row = 0; row < Size; row++)
            {
                var columns = _factors[row].Keys.ToArray();
                Array.Sort(columns);
                var values = new Complex[columns.Length];
                for (var index = 0; index < columns.Length; index++)
                    values[index] = _factors[row][columns[index]];
                _solveColumns[row] = columns;
                _solveValues[row] = values;
                _diagonal[row] = _factors[row][row];
            }
            _factors = [];
            _columnRows = [];
        }
        else
        {
            _solveColumns = [];
            _solveValues = [];
            _diagonal = [];
        }
    }

    internal int[][] CaptureFactorColumns()
    {
        if (_factors.Length == 0)
            return _solveColumns.Select(columns => columns.ToArray()).ToArray();
        var result = new int[Size][];
        for (var row = 0; row < Size; row++)
        {
            result[row] = _factors[row].Keys.ToArray();
            Array.Sort(result[row]);
        }
        return result;
    }

    private void SwapRows(int first, int second)
    {
        var firstColumns = _factors[first].Keys.ToArray();
        var secondColumns = _factors[second].Keys.ToArray();
        foreach (var column in firstColumns)
        {
            if (_factors[second].ContainsKey(column))
                continue;
            _columnRows[column].Remove(first);
            _columnRows[column].Add(second);
        }
        foreach (var column in secondColumns)
        {
            if (_factors[first].ContainsKey(column))
                continue;
            _columnRows[column].Remove(second);
            _columnRows[column].Add(first);
        }
        (_factors[first], _factors[second]) = (_factors[second], _factors[first]);
    }

    public Complex[] Solve(IReadOnlyList<Complex> sourceRightHandSide)
    {
        if (sourceRightHandSide.Count != Size)
            throw new ArgumentException("right-hand side length does not match matrix");
        var result = new Complex[Size];
        for (var index = 0; index < Size; index++)
            result[index] = sourceRightHandSide[index] / _rowScales[index];
        for (var column = 0; column < Size; column++)
            if (_pivots[column] != column)
                (result[column], result[_pivots[column]]) = (result[_pivots[column]], result[column]);
        if (_solveColumns.Length == 0)
        {
            for (var row = 1; row < Size; row++)
                foreach (var (column, value) in _factors[row])
                    if (column < row) result[row] -= value * result[column];
            for (var row = Size - 1; row >= 0; row--)
            {
                foreach (var (column, value) in _factors[row])
                    if (column > row) result[row] -= value * result[column];
                result[row] /= _factors[row][row];
            }
            return result;
        }
        for (var row = 1; row < Size; row++)
        {
            var columns = _solveColumns[row];
            var values = _solveValues[row];
            for (var index = 0; index < columns.Length && columns[index] < row; index++)
                result[row] -= values[index] * result[columns[index]];
        }
        for (var row = Size - 1; row >= 0; row--)
        {
            var columns = _solveColumns[row];
            var values = _solveValues[row];
            for (var index = columns.Length - 1; index >= 0 && columns[index] > row; index--)
                result[row] -= values[index] * result[columns[index]];
            result[row] /= _diagonal[row];
        }
        return result;
    }
}

internal sealed class PlannedSparseRealLu : IRealFactorization, IFactorizationSnapshot
{
    private readonly SparseLuPlan _plan;
    private readonly double[] _factors;
    private readonly double[] _inverseRowScales;
    private readonly double[] _realSolution;
    private readonly Complex[] _complexSolution;
    private readonly SimulationStatistics? _statistics;

    public int Size => _plan.Size;

    internal PlannedSparseRealLu(
        SparseMatrix source,
        SparseLuPlan plan,
        bool validatePattern,
        SimulationStatistics? statistics)
    {
        _plan = plan;
        _statistics = statistics;
        _factors = new double[plan.FactorCount];
        _inverseRowScales = new double[source.Size];
        _realSolution = new double[source.Size];
        _complexSolution = new Complex[source.Size];
        Refactorize(source, validatePattern);
    }

    private PlannedSparseRealLu(
        SparseLuPlan plan,
        double[] factors,
        double[] inverseRowScales,
        SimulationStatistics? statistics)
    {
        _plan = plan;
        _factors = factors;
        _inverseRowScales = inverseRowScales;
        _realSolution = new double[plan.Size];
        _complexSolution = new Complex[plan.Size];
        _statistics = statistics;
    }

    IComplexFactorization IFactorizationSnapshot.Snapshot() => new PlannedSparseRealLu(
        _plan,
        _factors.ToArray(),
        _inverseRowScales.ToArray(),
        _statistics);

    internal PlannedSparseRealLu Refactorize(SparseMatrix source, bool validatePattern)
    {
        var profile = _statistics?.CollectSparseFactorProfile == true;
        var copyStarted = profile ? Stopwatch.GetTimestamp() : 0;
        if (!source.IsReal)
            throw new ArgumentException("real sparse factorization requires a real matrix", nameof(source));
        if (validatePattern && !_plan.Supports(source))
            throw new SparsePlanRejectedException("matrix pattern is not covered by the cached sparse plan");
        Array.Clear(_factors);
        if (!validatePattern && source.TryGetFrozenData(out var rowOffsets, out var flatValues))
        {
            for (var row = 0; row < Size; row++)
            {
                var sourceRow = _plan.RowOrigins[row];
                var sourceStart = rowOffsets[sourceRow];
                var sourceEnd = rowOffsets[sourceRow + 1];
                var scale = 0.0;
                for (var sourcePosition = sourceStart; sourcePosition < sourceEnd; sourcePosition++)
                    scale = Math.Max(scale, Math.Abs(flatValues[sourcePosition].Real));
                if (!double.IsFinite(scale) || scale < 1e-30)
                    throw new SparsePlanRejectedException("singular or ill-conditioned matrix");
                var inverseScale = 1.0 / scale;
                _inverseRowScales[sourceRow] = inverseScale;
                var factorPositions = _plan.CachedSourcePositions(row);
                for (var index = 0; index < factorPositions.Length; index++)
                    _factors[factorPositions[index]] = flatValues[sourceStart + index].Real * inverseScale;
            }
            if (profile)
                _statistics!.SparseCopyScaleTicks += Stopwatch.GetTimestamp() - copyStarted;
            var eliminationStarted = profile ? Stopwatch.GetTimestamp() : 0;
            Factorize();
            if (profile)
                _statistics!.SparseEliminationTicks += Stopwatch.GetTimestamp() - eliminationStarted;
            return this;
        }
        for (var row = 0; row < Size; row++)
        {
            var sourceRow = _plan.RowOrigins[row];
            source.GetRowData(sourceRow, out var columns, out var sourceValues);
            var scale = 0.0;
            for (var index = 0; index < sourceValues.Length; index++)
                scale = Math.Max(scale, Math.Abs(sourceValues[index].Real));
            if (!double.IsFinite(scale) || scale < 1e-30)
                throw new SparsePlanRejectedException("singular or ill-conditioned matrix");
            var inverseScale = 1.0 / scale;
            _inverseRowScales[sourceRow] = inverseScale;
            var positions = validatePattern
                ? _plan.SourcePositions(row, columns)
                : _plan.CachedSourcePositions(row);
            for (var index = 0; index < columns.Length; index++)
                _factors[positions[index]] = sourceValues[index].Real * inverseScale;
        }
        if (profile)
            _statistics!.SparseCopyScaleTicks += Stopwatch.GetTimestamp() - copyStarted;
        var slowEliminationStarted = profile ? Stopwatch.GetTimestamp() : 0;
        Factorize();
        if (profile)
            _statistics!.SparseEliminationTicks += Stopwatch.GetTimestamp() - slowEliminationStarted;
        return this;
    }

    private void Factorize()
    {
        for (var column = 0; column < Size; column++)
        {
            var maximumMagnitude = 0.0;
            for (var index = _plan.ActiveOffsets[column]; index < _plan.ActiveOffsets[column + 1]; index++)
                maximumMagnitude = Math.Max(maximumMagnitude, Math.Abs(_factors[_plan.ActivePositions[index]]));
            var pivotValue = _factors[_plan.DiagonalPositions[column]];
            var pivotMagnitude = Math.Abs(pivotValue);
            if (!double.IsFinite(maximumMagnitude) || maximumMagnitude < 1e-30 ||
                !double.IsFinite(pivotMagnitude) || pivotMagnitude < maximumMagnitude * 1e-10)
            {
                _statistics?.RecordSparsePivotRejection(column, pivotMagnitude / maximumMagnitude);
                throw new SparsePlanRejectedException("cached sparse pivot sequence is no longer numerically stable");
            }
            for (var target = _plan.TargetOffsets[column]; target < _plan.TargetOffsets[column + 1]; target++)
            {
                var factorPosition = _plan.TargetFactorPositions[target];
                var factor = _factors[factorPosition] / pivotValue;
                _factors[factorPosition] = factor;
                if (factor == 0.0)
                    continue;
                for (var update = _plan.TargetUpdateOffsets[target];
                    update < _plan.TargetUpdateOffsets[target + 1];
                    update++)
                {
                    _factors[_plan.TargetUpdatePositions[update]] -=
                        factor * _factors[_plan.PivotUpdatePositions[update]];
                }
            }
        }
    }

    public Complex[] Solve(IReadOnlyList<Complex> sourceRightHandSide)
    {
        if (sourceRightHandSide.Count != Size)
            throw new ArgumentException("right-hand side length does not match matrix");
        var realRightHandSide = true;
        for (var index = 0; index < Size; index++)
            if (sourceRightHandSide[index].Imaginary != 0.0) realRightHandSide = false;
        if (realRightHandSide)
        {
            var real = SolveReal(sourceRightHandSide);
            for (var index = 0; index < Size; index++)
                _complexSolution[index] = new Complex(real[index], 0.0);
            return _complexSolution;
        }
        var profile = _statistics?.CollectSparseFactorProfile == true;
        var solveStarted = profile ? Stopwatch.GetTimestamp() : 0;
        for (var index = 0; index < Size; index++)
            _complexSolution[index] = sourceRightHandSide[index] * _inverseRowScales[index];
        ApplyPivots(_complexSolution);
        for (var row = 1; row < Size; row++)
            for (var position = _plan.RowOffsets[row]; position < _plan.DiagonalPositions[row]; position++)
                _complexSolution[row] -= _factors[position] * _complexSolution[_plan.FlatColumns[position]];
        for (var row = Size - 1; row >= 0; row--)
        {
            for (var position = _plan.DiagonalPositions[row] + 1; position < _plan.RowOffsets[row + 1]; position++)
                _complexSolution[row] -= _factors[position] * _complexSolution[_plan.FlatColumns[position]];
            _complexSolution[row] /= _factors[_plan.DiagonalPositions[row]];
        }
        if (profile)
            _statistics!.SparseTriangularSolveTicks += Stopwatch.GetTimestamp() - solveStarted;
        return _complexSolution;
    }

    public double[] SolveReal(IReadOnlyList<Complex> sourceRightHandSide)
    {
        var profile = _statistics?.CollectSparseFactorProfile == true;
        var solveStarted = profile ? Stopwatch.GetTimestamp() : 0;
        if (sourceRightHandSide.Count != Size)
            throw new ArgumentException("right-hand side length does not match matrix");
        for (var index = 0; index < Size; index++)
        {
            if (sourceRightHandSide[index].Imaginary != 0.0)
                throw new ArgumentException("real factorization requires a real right-hand side");
            _realSolution[index] = sourceRightHandSide[index].Real * _inverseRowScales[index];
        }
        ApplyPivots(_realSolution);
        for (var row = 1; row < Size; row++)
            for (var position = _plan.RowOffsets[row]; position < _plan.DiagonalPositions[row]; position++)
                _realSolution[row] -= _factors[position] * _realSolution[_plan.FlatColumns[position]];
        for (var row = Size - 1; row >= 0; row--)
        {
            for (var position = _plan.DiagonalPositions[row] + 1; position < _plan.RowOffsets[row + 1]; position++)
                _realSolution[row] -= _factors[position] * _realSolution[_plan.FlatColumns[position]];
            _realSolution[row] /= _factors[_plan.DiagonalPositions[row]];
        }
        if (profile)
            _statistics!.SparseTriangularSolveTicks += Stopwatch.GetTimestamp() - solveStarted;
        return _realSolution;
    }

    private void ApplyPivots<T>(T[] values)
    {
        for (var column = 0; column < Size; column++)
            if (_plan.Pivots[column] != column)
                (values[column], values[_plan.Pivots[column]]) = (values[_plan.Pivots[column]], values[column]);
    }
}

internal sealed class PlannedSparseComplexLu : IComplexFactorization, IFactorizationSnapshot
{
    private readonly SparseLuPlan _plan;
    private readonly double[] _factorReal;
    private readonly double[] _factorImaginary;
    private readonly double[] _inverseRowScales;
    private readonly double[] _solutionReal;
    private readonly double[] _solutionImaginary;
    private readonly Complex[] _solution;
    private readonly SimulationStatistics? _statistics;

    public int Size => _plan.Size;

    internal PlannedSparseComplexLu(
        SparseMatrix source,
        SparseLuPlan plan,
        bool validatePattern,
        SimulationStatistics? statistics)
    {
        _plan = plan;
        _statistics = statistics;
        _factorReal = new double[plan.FactorCount];
        _factorImaginary = new double[plan.FactorCount];
        _inverseRowScales = new double[source.Size];
        _solutionReal = new double[source.Size];
        _solutionImaginary = new double[source.Size];
        _solution = new Complex[source.Size];
        Refactorize(source, validatePattern);
    }

    private PlannedSparseComplexLu(
        SparseLuPlan plan,
        double[] factorReal,
        double[] factorImaginary,
        double[] inverseRowScales,
        SimulationStatistics? statistics)
    {
        _plan = plan;
        _factorReal = factorReal;
        _factorImaginary = factorImaginary;
        _inverseRowScales = inverseRowScales;
        _solutionReal = new double[plan.Size];
        _solutionImaginary = new double[plan.Size];
        _solution = new Complex[plan.Size];
        _statistics = statistics;
    }

    IComplexFactorization IFactorizationSnapshot.Snapshot() => new PlannedSparseComplexLu(
        _plan,
        _factorReal.ToArray(),
        _factorImaginary.ToArray(),
        _inverseRowScales.ToArray(),
        _statistics);

    internal PlannedSparseComplexLu Refactorize(SparseMatrix source, bool validatePattern)
    {
        var profile = _statistics?.CollectSparseFactorProfile == true;
        var copyStarted = profile ? Stopwatch.GetTimestamp() : 0;
        if (validatePattern && !_plan.Supports(source))
            throw new SparsePlanRejectedException("matrix pattern is not covered by the cached sparse plan");
        Array.Clear(_factorReal);
        Array.Clear(_factorImaginary);
        if (!validatePattern && source.TryGetFrozenData(out var rowOffsets, out var flatValues))
        {
            for (var row = 0; row < Size; row++)
            {
                var sourceRow = _plan.RowOrigins[row];
                var sourceStart = rowOffsets[sourceRow];
                var sourceEnd = rowOffsets[sourceRow + 1];
                var scaleSquared = 0.0;
                for (var sourcePosition = sourceStart; sourcePosition < sourceEnd; sourcePosition++)
                    scaleSquared = Math.Max(scaleSquared, MagnitudeSquared(flatValues[sourcePosition]));
                if (!double.IsFinite(scaleSquared) || scaleSquared < 1e-60)
                    throw new SparsePlanRejectedException("singular or ill-conditioned matrix");
                var inverseScale = 1.0 / Math.Sqrt(scaleSquared);
                _inverseRowScales[sourceRow] = inverseScale;
                var factorPositions = _plan.CachedSourcePositions(row);
                for (var index = 0; index < factorPositions.Length; index++)
                {
                    var value = flatValues[sourceStart + index];
                    var factorPosition = factorPositions[index];
                    _factorReal[factorPosition] = value.Real * inverseScale;
                    _factorImaginary[factorPosition] = value.Imaginary * inverseScale;
                }
            }
            if (profile)
                _statistics!.SparseCopyScaleTicks += Stopwatch.GetTimestamp() - copyStarted;
            var eliminationStarted = profile ? Stopwatch.GetTimestamp() : 0;
            Factorize();
            if (profile)
                _statistics!.SparseEliminationTicks += Stopwatch.GetTimestamp() - eliminationStarted;
            return this;
        }
        for (var row = 0; row < Size; row++)
        {
            var sourceRow = _plan.RowOrigins[row];
            source.GetRowData(sourceRow, out var columns, out var sourceValues);
            var scaleSquared = 0.0;
            for (var index = 0; index < sourceValues.Length; index++)
                scaleSquared = Math.Max(scaleSquared, MagnitudeSquared(sourceValues[index]));
            if (!double.IsFinite(scaleSquared) || scaleSquared < 1e-60)
                throw new SparsePlanRejectedException("singular or ill-conditioned matrix");
            var inverseScale = 1.0 / Math.Sqrt(scaleSquared);
            _inverseRowScales[sourceRow] = inverseScale;
            var positions = validatePattern
                ? _plan.SourcePositions(row, columns)
                : _plan.CachedSourcePositions(row);
            for (var index = 0; index < columns.Length; index++)
            {
                _factorReal[positions[index]] = sourceValues[index].Real * inverseScale;
                _factorImaginary[positions[index]] = sourceValues[index].Imaginary * inverseScale;
            }
        }
        if (profile)
            _statistics!.SparseCopyScaleTicks += Stopwatch.GetTimestamp() - copyStarted;
        var slowEliminationStarted = profile ? Stopwatch.GetTimestamp() : 0;
        Factorize();
        if (profile)
            _statistics!.SparseEliminationTicks += Stopwatch.GetTimestamp() - slowEliminationStarted;
        return this;
    }

    private void Factorize()
    {
        for (var column = 0; column < Size; column++)
        {
            var maximumMagnitudeSquared = 0.0;
            for (var index = _plan.ActiveOffsets[column]; index < _plan.ActiveOffsets[column + 1]; index++)
                maximumMagnitudeSquared = Math.Max(
                    maximumMagnitudeSquared,
                    MagnitudeSquared(
                        _factorReal[_plan.ActivePositions[index]],
                        _factorImaginary[_plan.ActivePositions[index]]));
            var pivotPosition = _plan.DiagonalPositions[column];
            var pivotReal = _factorReal[pivotPosition];
            var pivotImaginary = _factorImaginary[pivotPosition];
            var pivotMagnitudeSquared = MagnitudeSquared(pivotReal, pivotImaginary);
            if (!double.IsFinite(maximumMagnitudeSquared) || maximumMagnitudeSquared < 1e-60 ||
                !double.IsFinite(pivotMagnitudeSquared) || pivotMagnitudeSquared < maximumMagnitudeSquared * 1e-20)
            {
                _statistics?.RecordSparsePivotRejection(
                    column,
                    Math.Sqrt(pivotMagnitudeSquared / maximumMagnitudeSquared));
                throw new SparsePlanRejectedException("cached sparse pivot sequence is no longer numerically stable");
            }
            for (var target = _plan.TargetOffsets[column]; target < _plan.TargetOffsets[column + 1]; target++)
            {
                var factorPosition = _plan.TargetFactorPositions[target];
                var targetReal = _factorReal[factorPosition];
                var targetImaginary = _factorImaginary[factorPosition];
                var factorReal = (targetReal * pivotReal + targetImaginary * pivotImaginary) /
                    pivotMagnitudeSquared;
                var factorImaginary = (targetImaginary * pivotReal - targetReal * pivotImaginary) /
                    pivotMagnitudeSquared;
                _factorReal[factorPosition] = factorReal;
                _factorImaginary[factorPosition] = factorImaginary;
                if (factorReal == 0.0 && factorImaginary == 0.0)
                    continue;
                for (var update = _plan.TargetUpdateOffsets[target];
                    update < _plan.TargetUpdateOffsets[target + 1];
                    update++)
                {
                    var upperPosition = _plan.PivotUpdatePositions[update];
                    var upperReal = _factorReal[upperPosition];
                    var upperImaginary = _factorImaginary[upperPosition];
                    var targetPosition = _plan.TargetUpdatePositions[update];
                    _factorReal[targetPosition] -= factorReal * upperReal - factorImaginary * upperImaginary;
                    _factorImaginary[targetPosition] -= factorReal * upperImaginary + factorImaginary * upperReal;
                }
            }
        }
    }

    public Complex[] Solve(IReadOnlyList<Complex> sourceRightHandSide)
    {
        var profile = _statistics?.CollectSparseFactorProfile == true;
        var solveStarted = profile ? Stopwatch.GetTimestamp() : 0;
        if (sourceRightHandSide.Count != Size)
            throw new ArgumentException("right-hand side length does not match matrix");
        for (var index = 0; index < Size; index++)
        {
            _solutionReal[index] = sourceRightHandSide[index].Real * _inverseRowScales[index];
            _solutionImaginary[index] = sourceRightHandSide[index].Imaginary * _inverseRowScales[index];
        }
        for (var column = 0; column < Size; column++)
            if (_plan.Pivots[column] != column)
            {
                var pivot = _plan.Pivots[column];
                (_solutionReal[column], _solutionReal[pivot]) = (_solutionReal[pivot], _solutionReal[column]);
                (_solutionImaginary[column], _solutionImaginary[pivot]) = (_solutionImaginary[pivot], _solutionImaginary[column]);
            }
        for (var row = 1; row < Size; row++)
            for (var position = _plan.RowOffsets[row]; position < _plan.DiagonalPositions[row]; position++)
            {
                var column = _plan.FlatColumns[position];
                var valueReal = _solutionReal[column];
                var valueImaginary = _solutionImaginary[column];
                _solutionReal[row] -= _factorReal[position] * valueReal - _factorImaginary[position] * valueImaginary;
                _solutionImaginary[row] -= _factorReal[position] * valueImaginary + _factorImaginary[position] * valueReal;
            }
        for (var row = Size - 1; row >= 0; row--)
        {
            for (var position = _plan.DiagonalPositions[row] + 1; position < _plan.RowOffsets[row + 1]; position++)
            {
                var column = _plan.FlatColumns[position];
                var valueReal = _solutionReal[column];
                var valueImaginary = _solutionImaginary[column];
                _solutionReal[row] -= _factorReal[position] * valueReal - _factorImaginary[position] * valueImaginary;
                _solutionImaginary[row] -= _factorReal[position] * valueImaginary + _factorImaginary[position] * valueReal;
            }
            var diagonalPosition = _plan.DiagonalPositions[row];
            var diagonalReal = _factorReal[diagonalPosition];
            var diagonalImaginary = _factorImaginary[diagonalPosition];
            var denominator = MagnitudeSquared(diagonalReal, diagonalImaginary);
            var numeratorReal = _solutionReal[row];
            var numeratorImaginary = _solutionImaginary[row];
            _solutionReal[row] = (numeratorReal * diagonalReal + numeratorImaginary * diagonalImaginary) / denominator;
            _solutionImaginary[row] = (numeratorImaginary * diagonalReal - numeratorReal * diagonalImaginary) / denominator;
        }
        for (var index = 0; index < Size; index++)
            _solution[index] = new Complex(_solutionReal[index], _solutionImaginary[index]);
        if (profile)
            _statistics!.SparseTriangularSolveTicks += Stopwatch.GetTimestamp() - solveStarted;
        return _solution;
    }

    private static double MagnitudeSquared(Complex value) => MagnitudeSquared(value.Real, value.Imaginary);

    private static double MagnitudeSquared(double real, double imaginary) => real * real + imaginary * imaginary;
}

internal readonly record struct MatrixStampCoordinate(int Row, int Column);
internal readonly record struct MatrixStampSlot(int Row, int Column, int Position);

internal sealed class CachedRealSparsePlan(SparseLuPlan plan, int patternVersion)
{
    internal SparseLuPlan Plan { get; } = plan;
    internal int PatternVersion { get; set; } = patternVersion;
    internal PlannedSparseRealLu? Factorization { get; set; }
}

internal sealed class CachedComplexSparsePlan(SparseLuPlan plan, int patternVersion)
{
    internal SparseLuPlan Plan { get; } = plan;
    internal int PatternVersion { get; set; } = patternVersion;
    internal PlannedSparseComplexLu? Factorization { get; set; }
}

internal sealed class SparseFactorizationCache
{
    private const int MaximumNumericPlans = 8;
    private readonly bool _reuseDisabled =
        Environment.GetEnvironmentVariable("AGENT_SPICE_NATIVE_DISABLE_SYMBOLIC_REUSE") == "1";
    private readonly List<CachedRealSparsePlan> _realPlans = [];
    private readonly List<CachedComplexSparsePlan> _complexPlans = [];
    private SparseMatrix? _matrixWorkspace;
    private List<MatrixStampCoordinate>? _stampCoordinates;
    private MatrixStampSlot[]? _stampSlots;
    private int _stampCursor;
    private bool _stampPatternComplete;
    private bool _stampReplayDisabled;
    private Complex[]? _rightHandSideWorkspace;
    private double? _currentAffineParameter;
    private double? _lastCompletedAffineParameter;
    private double? _affineFirstParameter;
    private Complex[]? _affineConstant;
    private Complex[]? _affineSlope;
    private bool _affineReplayActive;

    internal SparseMatrix RentMatrix(int size) => RentMatrix(size, null, out _);

    internal Complex[] RentRightHandSide(int size)
    {
        if (_reuseDisabled)
            return new Complex[size];
        if (_rightHandSideWorkspace is null || _rightHandSideWorkspace.Length != size)
            _rightHandSideWorkspace = new Complex[size];
        else
            Array.Clear(_rightHandSideWorkspace);
        return _rightHandSideWorkspace;
    }

    internal SparseMatrix RentMatrix(int size, double? affineParameter, out bool assemblyReplayed)
    {
        assemblyReplayed = false;
        _currentAffineParameter = affineParameter;
        _affineReplayActive = false;
        if (_reuseDisabled)
            return new SparseMatrix(size);
        if (_matrixWorkspace is null || _matrixWorkspace.Size != size)
        {
            _matrixWorkspace = new SparseMatrix(size);
            _realPlans.Clear();
            _complexPlans.Clear();
            _stampCoordinates = [];
            _stampSlots = null;
            _stampCursor = 0;
            _stampPatternComplete = false;
            _stampReplayDisabled = false;
            _rightHandSideWorkspace = null;
            ResetAffineAssembly();
            _currentAffineParameter = affineParameter;
            return _matrixWorkspace;
        }
        if (!affineParameter.HasValue)
            ResetAffineAssembly();
        else if (_affineConstant is not null && _affineSlope is not null)
        {
            _matrixWorkspace.ClearValues();
            _matrixWorkspace.SetFrozenAffineValues(_affineConstant, _affineSlope, affineParameter.Value);
            _stampCursor = 0;
            _affineReplayActive = true;
            assemblyReplayed = true;
            return _matrixWorkspace;
        }
        else if (_affineConstant is null && _lastCompletedAffineParameter.HasValue)
        {
            _affineConstant = _matrixWorkspace.CloneFrozenValues();
            _affineFirstParameter = _lastCompletedAffineParameter;
        }
        if (_stampPatternComplete && !_stampReplayDisabled && _stampSlots is null)
            CompileStampSlots(_matrixWorkspace);
        _matrixWorkspace.ClearValues();
        _stampCursor = 0;
        return _matrixWorkspace;
    }

    internal void AddMatrixValue(SparseMatrix matrix, int row, int column, Complex value)
    {
        if (_reuseDisabled)
        {
            matrix.Add(row, column, value);
            return;
        }
        if (_stampSlots is not null)
        {
            if (_stampCursor >= _stampSlots.Length ||
                _stampSlots[_stampCursor].Row != row ||
                _stampSlots[_stampCursor].Column != column)
            {
                DisableStampReplay();
            }
            else
            {
                var slot = _stampSlots[_stampCursor++];
                if (slot.Position >= 0)
                {
                    matrix.AddFrozen(slot.Position, value);
                    return;
                }
                if (value == Complex.Zero)
                    return;
                DisableStampReplay();
            }
        }
        if (!_stampPatternComplete && !_stampReplayDisabled)
            _stampCoordinates!.Add(new MatrixStampCoordinate(row, column));
        if (value == Complex.Zero)
            return;
        matrix.Add(row, column, value);
    }

    internal void CompleteStamping()
    {
        if (_reuseDisabled)
            return;
        if (_affineReplayActive)
        {
            _lastCompletedAffineParameter = _currentAffineParameter;
            return;
        }
        if (_stampReplayDisabled)
            return;
        if (_stampSlots is not null && _stampCursor != _stampSlots.Length)
        {
            DisableStampReplay();
            return;
        }
        _stampPatternComplete = true;
        TryCompileAffineAssembly();
        _lastCompletedAffineParameter = _currentAffineParameter;
    }

    private void TryCompileAffineAssembly()
    {
        if (_matrixWorkspace is null || _affineConstant is null ||
            !_affineFirstParameter.HasValue || !_currentAffineParameter.HasValue)
            return;
        var delta = _currentAffineParameter.Value - _affineFirstParameter.Value;
        if (delta == 0.0 || !double.IsFinite(delta))
            return;
        if (!_matrixWorkspace.TryGetFrozenData(out _, out var current) ||
            _affineConstant.Length != current.Length)
        {
            ResetAffineAssembly();
            return;
        }
        var slope = new Complex[current.Length];
        for (var index = 0; index < current.Length; index++)
        {
            slope[index] = (current[index] - _affineConstant[index]) / delta;
            _affineConstant[index] -= slope[index] * _affineFirstParameter.Value;
        }
        _affineSlope = slope;
    }

    private void CompileStampSlots(SparseMatrix matrix)
    {
        var coordinates = _stampCoordinates!;
        var slots = new MatrixStampSlot[coordinates.Count];
        for (var index = 0; index < coordinates.Count; index++)
        {
            var coordinate = coordinates[index];
            if (!matrix.TryGetFrozenPosition(coordinate.Row, coordinate.Column, out var position))
                position = -1;
            slots[index] = new MatrixStampSlot(coordinate.Row, coordinate.Column, position);
        }
        _stampSlots = slots;
    }

    private void DisableStampReplay()
    {
        _stampReplayDisabled = true;
        _stampCoordinates = null;
        _stampSlots = null;
        _stampCursor = 0;
        ResetAffineAssembly();
    }

    private void ResetAffineAssembly()
    {
        _currentAffineParameter = null;
        _lastCompletedAffineParameter = null;
        _affineFirstParameter = null;
        _affineConstant = null;
        _affineSlope = null;
        _affineReplayActive = false;
    }

    internal IComplexFactorization Factorize(
        SparseMatrix matrix,
        bool useRealSparse,
        bool optimizeRepeatedSolve,
        SimulationStatistics? statistics)
    {
        if (useRealSparse)
        {
            for (var index = 0; index < _realPlans.Count; index++)
            {
                var cached = _realPlans[index];
                try
                {
                    var validatePattern = matrix.PatternVersion != cached.PatternVersion;
                    cached.Factorization = cached.Factorization is null
                        ? new PlannedSparseRealLu(matrix, cached.Plan, validatePattern, statistics)
                        : cached.Factorization.Refactorize(matrix, validatePattern);
                    cached.PatternVersion = matrix.PatternVersion;
                    if (index > 0)
                    {
                        _realPlans.RemoveAt(index);
                        _realPlans.Insert(0, cached);
                    }
                    if (statistics is not null)
                        statistics.SparseNumericRefactorizations++;
                    return cached.Factorization;
                }
                catch (SparsePlanRejectedException)
                {
                    cached.Factorization = null;
                }
            }
            if (_realPlans.Count > 0 && statistics is not null)
                statistics.SparsePlanFallbacks++;
            var profile = statistics?.CollectSparseFactorProfile == true;
            var freshStarted = profile ? Stopwatch.GetTimestamp() : 0;
            var fresh = new SparseRealLu(matrix, optimizeRepeatedSolve);
            if (profile)
                statistics!.SparseFreshFactorTicks += Stopwatch.GetTimestamp() - freshStarted;
            var planStarted = profile ? Stopwatch.GetTimestamp() : 0;
            var plan = SparseLuPlan.Create(matrix, fresh.Pivots, fresh.CaptureFactorColumns());
            if (profile)
                statistics!.SparsePlanBuildTicks += Stopwatch.GetTimestamp() - planStarted;
            _realPlans.Insert(0, new CachedRealSparsePlan(plan, matrix.PatternVersion));
            if (_realPlans.Count > MaximumNumericPlans)
                _realPlans.RemoveAt(_realPlans.Count - 1);
            if (statistics is not null)
                statistics.SparseSymbolicFactorizations++;
            return fresh;
        }

        for (var index = 0; index < _complexPlans.Count; index++)
        {
            var cached = _complexPlans[index];
            try
            {
                var validatePattern = matrix.PatternVersion != cached.PatternVersion;
                cached.Factorization = cached.Factorization is null
                    ? new PlannedSparseComplexLu(matrix, cached.Plan, validatePattern, statistics)
                    : cached.Factorization.Refactorize(matrix, validatePattern);
                cached.PatternVersion = matrix.PatternVersion;
                if (index > 0)
                {
                    _complexPlans.RemoveAt(index);
                    _complexPlans.Insert(0, cached);
                }
                if (statistics is not null)
                    statistics.SparseNumericRefactorizations++;
                return cached.Factorization;
            }
            catch (SparsePlanRejectedException)
            {
                cached.Factorization = null;
            }
        }
        if (_complexPlans.Count > 0 && statistics is not null)
            statistics.SparsePlanFallbacks++;
        var complexProfile = statistics?.CollectSparseFactorProfile == true;
        var complexStarted = complexProfile ? Stopwatch.GetTimestamp() : 0;
        var complex = new SparseComplexLu(matrix, optimizeRepeatedSolve);
        if (complexProfile)
            statistics!.SparseFreshFactorTicks += Stopwatch.GetTimestamp() - complexStarted;
        var complexPlanStarted = complexProfile ? Stopwatch.GetTimestamp() : 0;
        var complexPlan = SparseLuPlan.Create(matrix, complex.Pivots, complex.CaptureFactorColumns());
        if (complexProfile)
            statistics!.SparsePlanBuildTicks += Stopwatch.GetTimestamp() - complexPlanStarted;
        _complexPlans.Insert(0, new CachedComplexSparsePlan(complexPlan, matrix.PatternVersion));
        if (_complexPlans.Count > MaximumNumericPlans)
            _complexPlans.RemoveAt(_complexPlans.Count - 1);
        if (statistics is not null)
            statistics.SparseSymbolicFactorizations++;
        return complex;
    }
}

internal static class LinearAlgebra
{
    internal static Complex[] Solve(Complex[,] matrix, Complex[] rightHandSide) => new ComplexLu(matrix).Solve(rightHandSide);

    internal static IComplexFactorization Factorize(
        SparseMatrix matrix,
        bool optimizeRepeatedSolve = false,
        SparseFactorizationCache? cache = null,
        SimulationStatistics? statistics = null)
    {
        var useSparse = matrix.Size >= 64 && matrix.NonZeros * 5L <= (long)matrix.Size * matrix.Size;
        var useRealSparse = matrix.IsReal && useSparse && optimizeRepeatedSolve;
        var timer = Stopwatch.StartNew();
        cache?.CompleteStamping();
        var useCachedPlan = cache is not null && useSparse &&
            Environment.GetEnvironmentVariable("AGENT_SPICE_NATIVE_DISABLE_SYMBOLIC_REUSE") != "1";
        IComplexFactorization result;
        if (useCachedPlan)
            result = cache!.Factorize(matrix, useRealSparse, optimizeRepeatedSolve, statistics);
        else
            result = (useRealSparse, useSparse) switch
            {
                (true, true) => new SparseRealLu(matrix, optimizeRepeatedSolve),
                (false, true) => new SparseComplexLu(matrix, optimizeRepeatedSolve),
                (false, false) => new ComplexLu(matrix.ToDense()),
                _ => throw new InvalidOperationException("invalid matrix solver selection"),
            };
        if (cache is not null)
            matrix.FreezePattern();
        if (Environment.GetEnvironmentVariable("AGENT_SPICE_NATIVE_MATRIX_TIMING") == "1")
            Console.Error.WriteLine(
                $"matrix size={matrix.Size} nnz={matrix.NonZeros} solver={(useSparse ? "sparse" : "dense")}-{(useRealSparse ? "real" : "complex")} " +
                $"symbolic={(useCachedPlan ? "cached" : "fresh")} factor={timer.Elapsed.TotalSeconds:F6}s");
        return result;
    }

    internal static Complex[] Solve(
        SparseMatrix matrix,
        Complex[] rightHandSide,
        SparseFactorizationCache? cache = null,
        SimulationStatistics? statistics = null) =>
        Factorize(matrix, cache: cache, statistics: statistics).Solve(rightHandSide);

    internal static Complex[,] Invert(Complex[,] matrix)
    {
        var factorization = new ComplexLu(matrix);
        var inverse = new Complex[factorization.Size, factorization.Size];
        for (var column = 0; column < factorization.Size; column++)
        {
            var basis = new Complex[factorization.Size];
            basis[column] = Complex.One;
            var solution = factorization.Solve(basis);
            for (var row = 0; row < factorization.Size; row++)
                inverse[row, column] = solution[row];
        }
        return inverse;
    }
}
