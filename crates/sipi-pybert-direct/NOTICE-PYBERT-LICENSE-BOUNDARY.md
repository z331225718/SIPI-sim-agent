# PyBERT native-core license boundary

This quarantined migration crate contains exact copies of nineteen Rust source
files from `native/pybert-core/src` at PyBERT Git commit
`5bf6d7ea0ace261891aaeb611ffc1c267e160afe` (tree
`5faef6bdb341d444ad65d82a11c0018b15805e24`). The exact source paths, Git blob
identities, content hashes, and destination paths are recorded in
`SOURCE-MAP.md` and `docs/baselines/pb-02-direct-port.v1.yaml`.

The pinned `native/pybert-core/Cargo.toml` declares `license = "MIT"`, but the
pinned tree does not contain a separate MIT license text inside
`native/pybert-core`. The pinned repository root `LICENSE` is the following
BSD-3-Clause text (SHA-256
`4ca68aea5b8f43e0d7337b182fbc277e02dae37d85b04196d92a80e9344926c1`):

```text
Copyright 2014 David Banas

Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

    1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
    2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
    3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

The Cargo MIT declaration and repository BSD-3-Clause text are conflicting
metadata for this copied native-core scope; this notice does not resolve that
conflict or grant redistribution permission. For that reason this crate remains
non-distributed and outside the product workspace. Promotion requires an
explicit license-owner decision covering the copied native-core paths and the
required notice text.
