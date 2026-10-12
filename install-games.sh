#!/usr/bin/env bash
# Install every release (or the ones named) from the images in isos/ into
# games/<name>/, as each game's own setup program would; an SDK, only when
# named, goes in sdk/<name>/. Run ./fetch-isos.sh first. See README.md, and
# `tools/install.py --list` for the releases.
#
#   ./install-games.sh [--force] [name...]   install (and check) releases
#   ./install-games.sh --verify [name...]    re-check installed ones
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
make -s -C "$ROOT/tools/unshield"
if [ "${1:-}" = "--verify" ]; then
    shift
    exec python3 -I "$ROOT/tools/install.py" --verify "$ROOT/games" "$@"
fi
exec python3 -I "$ROOT/tools/install.py" "$ROOT/games" "$@"
