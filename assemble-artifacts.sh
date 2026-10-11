#!/usr/bin/env bash
# Put the demo, patch and map-pack archives back together from their chunks
# (demos/, patches/ and mappacks/ hold <item>.tar.xz.c001, .c002, ...), as
# artifacts/<category>/<item>.tar.xz, and check each against
# artifacts/SHA256SUMS. tools/pack-artifacts.sh makes the chunks.
#
#   ./assemble-artifacts.sh [name...]
#
# With no names, every archive; a name is an item (si_nolf2_demo.exe), its
# path (demos/si_nolf2_demo.exe) or a category (demos, patches, mappacks).
# An archive already assembled and matching is left alone. Unpack one with
# e.g. `tar -xJf artifacts/demos/si_nolf2_demo.exe.tar.xz -C <dir>`.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")" && pwd)
SUMS="$ROOT/artifacts/SHA256SUMS"

die() { echo "assemble-artifacts: $*" >&2; exit 1; }
[ -s "$SUMS" ] || die "no entries in $SUMS"

# Does name $1 pick archive $2 ("<category>/<item>.tar.xz")?
matches() {
    local name=${1%/} path=$2 item=${2%.tar.xz}
    [ "$name" = "$path" ] || [ "$name" = "${path#*/}" ] || [ "$name" = "$item" ] ||
        [ "$name" = "${item#*/}" ] ||
        [ "$name" = "${path%%/*}" ]
}

# SHA256SUMS lines are "<hash>  <category>/<item>.tar.xz".
mapfile -t LINES < "$SUMS"
for name in "$@"; do
    found=0
    for line in "${LINES[@]}"; do matches "$name" "${line:66}" && found=1; done
    [ $found = 1 ] || die "$name: no such archive in $SUMS"
done
want() {
    local name
    [ ${#NAMES[@]} -eq 0 ] && return 0
    for name in "${NAMES[@]}"; do matches "$name" "$1" && return 0; done
    return 1
}
NAMES=("$@")

n=0
for line in "${LINES[@]}"; do
    hash=${line:0:64} path=${line:66}
    want "$path" || continue
    n=$((n + 1))
    out="$ROOT/artifacts/$path"
    if [ -f "$out" ] && [ "$(sha256sum < "$out" | cut -c1-64)" = "$hash" ]; then
        echo "== $path: already assembled"
        continue
    fi
    # The chunks must run .c001, .c002, ... with none missing.
    chunks=("$ROOT/$path".c[0-9][0-9][0-9])
    [ -e "${chunks[0]}" ] || die "$path: no chunks ($path.c001 ...)"
    for i in "${!chunks[@]}"; do
        [ "${chunks[$i]}" = "$ROOT/$path.c$(printf '%03d' $((i + 1)))" ] ||
            die "$path: chunk .c$(printf '%03d' $((i + 1))) is missing"
    done
    mkdir -p "$(dirname "$out")"
    cat -- "${chunks[@]}" > "$out.part"
    got=$(sha256sum < "$out.part" | cut -c1-64)
    [ "$got" = "$hash" ] || { rm -f "$out.part"; die "$path: checksum mismatch (got $got)"; }
    mv "$out.part" "$out"
    echo "== $path: ${#chunks[@]} chunk(s) -> artifacts/$path"
done
echo "== $n archive(s) ready in artifacts/"
