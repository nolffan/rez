#!/usr/bin/env bash
# Install every LithTech dev tool release (or the ones named) into
# installed/devtools/<name>/, as each one's own installer would: those
# released on a game disc off the images in isos/ (run ./fetch-isos.sh
# <name> first), the others off the archives in devtools/ (assembled from
# their chunks as needed). See README.md, and `tools/install.py --list` for
# the releases.
#
#   ./install-devtools.sh [--force] [name...]   install (and check) releases
#   ./install-devtools.sh --verify [name...]    re-check installed ones
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
make -s -C "$ROOT/tools/unshield"
make -s -C "$ROOT/tools/blast"
if [ "${1:-}" = "--verify" ]; then
    shift
    exec python3 -I "$ROOT/tools/install.py" --verify --devtools "$ROOT/installed/devtools" "$@"
fi
exec python3 -I "$ROOT/tools/install.py" --devtools "$ROOT/installed/devtools" "$@"
