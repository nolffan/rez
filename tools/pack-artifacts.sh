#!/usr/bin/env bash
# Pack items (a file or a directory under demos/, patches/ or mappacks/) for
# committing: each becomes one .tar.xz in artifacts/, recorded in
# artifacts/SHA256SUMS, and split into chunks of at most 45,000,000 bytes
# beside the item (<item>.tar.xz.c001, .c002, ...), which are what git keeps.
# ./assemble-artifacts.sh puts the archives back together from the chunks.
#
#   tools/pack-artifacts.sh <item>...      e.g. demos/si_nolf2_demo.exe
#
# The archives say nothing about who made them or when: no owner names or
# ids, every file dated 1970-01-01, and fixed permissions. Entries are in a
# fixed order and xz runs single-threaded, so packing the same item again
# gives the same bytes.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SUMS="$ROOT/artifacts/SHA256SUMS"
CHUNK=45000000

die() { echo "pack-artifacts: $*" >&2; exit 1; }
[ $# -gt 0 ] || die "usage: tools/pack-artifacts.sh <item>..."

pack() {
    local item="${1%/}" rel archive
    rel=$(realpath --relative-to="$ROOT" "$item")
    case "$rel" in demos/*/* | patches/*/* | mappacks/*/*) die "$rel: pack the top-level item, not something inside it" ;;
                   demos/* | patches/* | mappacks/*) ;;
                   *) die "$rel: not in demos/, patches/ or mappacks/" ;; esac
    [ -e "$ROOT/$rel" ] || die "$rel: no such file or directory"
    archive="$ROOT/artifacts/$rel.tar.xz"
    mkdir -p "$(dirname "$archive")"
    tar -C "$ROOT/$(dirname "$rel")" -cf - --format=gnu --sort=name \
        --owner=0 --group=0 --numeric-owner --mtime=@0 --mode='a=rX,u+w' \
        -- "$(basename "$rel")" | xz -9 -T1 > "$archive.part"
    mv "$archive.part" "$archive"
    rm -f -- "$ROOT/$rel.tar.xz".c[0-9][0-9][0-9]
    split -b $CHUNK -a 3 --numeric-suffixes=1 -- "$archive" "$ROOT/$rel.tar.xz.c"
    echo "$(sha256sum < "$archive" | cut -c1-64)  $rel.tar.xz"
}

JOBS=${JOBS:-4}    # xz -9 needs ~700 MB of memory per job
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
i=0
for item in "$@"; do
    i=$((i + 1))
    [ "$(jobs -rp | wc -l)" -lt "$JOBS" ] || wait -n
    pack "$item" > "$tmp/$i" &
done
while [ "$(jobs -rp | wc -l)" -gt 0 ]; do wait -n || die "packing failed"; done
[ "$(cat "$tmp"/* | wc -l)" = $# ] || die "packing failed"

# Replace these archives' lines (or add them), keeping the file sorted.
touch "$SUMS"
cat "$tmp"/* | awk 'NR == FNR { new[substr($0, 67)] = $0; next }
                    !(substr($0, 67) in new)' - "$SUMS" > "$tmp/keep"
cat "$tmp/keep" "$tmp"/[0-9]* | LC_ALL=C sort -t ' ' -k3 > "$SUMS.new"
mv "$SUMS.new" "$SUMS"
cat "$tmp"/[0-9]* | while IFS= read -r line; do
    path=${line:66}
    n=$(ls -- "$ROOT/$path".c[0-9][0-9][0-9] | wc -l)
    echo "== $path: $n chunk(s)"
done
