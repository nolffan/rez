#!/usr/bin/env bash
# Install every release (or the ones named) from the images in isos/ into
# games/<name>/, as each game's own setup program would. Run ./fetch-isos.sh
# first. See README.md, and `tools/install.py --list` for the releases.
#
#   ./install-games.sh [--force] [name...]
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
make -s -C "$ROOT/tools/unshield"
exec python3 -I "$ROOT/tools/install.py" "$ROOT/games" "$@"
