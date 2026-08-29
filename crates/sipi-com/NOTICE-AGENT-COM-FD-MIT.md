# Agent-COM FD attribution

This crate contains a direct Rust port of the portable R4.80 frequency-domain
final-metric functions from Agent-COM.  The upstream source is MIT licensed
and remains external; no Python source, workbook, touchstone, MATLAB runtime,
or golden result artifact is bundled here.

Pinned upstream: commit
`5272ffe74702cd585054d975559b06f8afae7b6e`, tree
`7094ab6e84989b218730c52432c70da10261f8ea`.

The exact source path, Git blob, byte count, raw content hash, and license
object are recorded in `SOURCE-MAP-COM-FD.md`.  This attribution applies to
the source-derived code in `src/fd_metrics_v1.rs`; the surrounding SIPI code
retains the repository's existing MIT license.

## MIT License

Copyright (c) 2026 z331225718

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
