#!/usr/bin/env bash
# Fetch and build nneonneo/2048-ai (MIT, https://github.com/nneonneo/2048-ai) as the shared
# library player.py loads. Pinned to one commit so results stay reproducible.
set -euo pipefail
cd "$(dirname "$0")"
here="$(pwd)"
commit=41e298f4571a9505e421e3a19af7a1cb372a368c
[ -d 2048-ai ] || git clone -q https://github.com/nneonneo/2048-ai.git 2048-ai
git -C 2048-ai checkout -q "$commit"
cd 2048-ai
# quiet.h only silences the library's per-move debug printing; the search itself is unchanged
./configure CXXFLAGS="-O3 -include $here/quiet.h" > /dev/null
make > /dev/null
echo "built $(pwd)/bin/2048.so"
