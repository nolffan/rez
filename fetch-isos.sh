#!/usr/bin/env bash
# Fetch the redump images of No One Lives Forever, NOLF2 and Contract J.A.C.K.
# into isos/, check them against isos/SHA256SUMS, and turn each zipped
# .bin/.cue into a plain 2048-byte-sector .iso beside it. The PC discs come
# from https://archive.org/details/nolf-pc-redump; NOLF's PlayStation 2 discs
# (isos/ps2/, whose zips hold an .iso that is just copied out) from
# https://archive.org/details/PS2-Redump-2024-Individual-Games-Part11; and the
# Mac discs of NOLF and NOLF2 (isos/mac/) from
# https://archive.org/details/REDUMP_Apple_-_Macintosh.
#
#   ./fetch-isos.sh [name...]            fetch whatever is missing, verify, convert
#   ./fetch-isos.sh --verify [name...]   only check the zips against SHA256SUMS
#
# With no names, every zip in SHA256SUMS; with release names (as
# ./install-games.sh takes them, e.g. nolf-eu-goty -- `tools/install.py
# --list` lists them), only the discs those releases are installed from.
#
# A rerun downloads nothing that is already there (and resumes partial files).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")" && pwd)
ISOS="$ROOT/isos"
BASE="https://archive.org/download/nolf-pc-redump/NOLF-PC-REDUMP"
PS2_BASE="https://archive.org/download/PS2-Redump-2024-Individual-Games-Part11"
MAC_BASE="https://archive.org/download/REDUMP_Apple_-_Macintosh"
JOBS=${JOBS:-4}

die() { echo "fetch-isos: $*" >&2; exit 1; }
for t in curl sha256sum python3; do
    command -v "$t" >/dev/null || die "$t is required"
done

VERIFY_ONLY=0
if [ "${1:-}" = "--verify" ]; then VERIFY_ONLY=1; shift; fi

# The zips, in SHA256SUMS order; the names are the item's own.
mapfile -t ZIPS < <(sed -n 's/^[0-9a-f]\{64\}  //p' "$ISOS/SHA256SUMS")
[ ${#ZIPS[@]} -gt 0 ] || die "no entries in $ISOS/SHA256SUMS"
if [ $# -gt 0 ]; then
    discs=$(python3 -I "$ROOT/tools/install.py" --discs "$@") || exit 1
    mapfile -t ZIPS < <(printf '%s\n' "$discs" | sed 's/$/.zip/')
fi

# The SHA256SUMS lines of the zips in ZIPS (each line is "<hash>  <name>").
sums() {
    printf '%s\n' "${ZIPS[@]}" | awk 'NR == FNR { want[$0]; next } substr($0, 67) in want' - "$ISOS/SHA256SUMS"
}

verify() {
    [ "$(sums | wc -l)" = ${#ZIPS[@]} ] || die "a requested zip is not in $ISOS/SHA256SUMS"
    echo "== checking ${#ZIPS[@]} zips against SHA256SUMS"
    (cd "$ISOS" && sums | sha256sum -c --quiet -) || die "checksum mismatch (delete the bad zip and rerun)"
    echo "== all ${#ZIPS[@]} zips OK"
}

if [ $VERIFY_ONLY = 1 ]; then verify; exit 0; fi

urlencode() { python3 -I -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$1"; }

fetch_one() {
    local z="$1" url
    [ -f "$ISOS/$z" ] && return 0
    case "$z" in
        ps2/*) url="$PS2_BASE/$(urlencode "${z#*/}")" ;;
        mac/*) url="$MAC_BASE/$(urlencode "${z#*/}")" ;;
        *)     url="$BASE/$(urlencode "$z")" ;;
    esac
    mkdir -p "$(dirname "$ISOS/$z")"
    echo "-> $z"
    curl -fsSL --retry 10 --retry-delay 5 -C - -o "$ISOS/$z.part" "$url"
    mv "$ISOS/$z.part" "$ISOS/$z"
    echo "<- $z"
}
export -f fetch_one urlencode
export ISOS BASE PS2_BASE MAC_BASE

echo "== fetching ${#ZIPS[@]} zips into $ISOS ($JOBS at a time)"
printf '%s\0' "${ZIPS[@]}" | xargs -0 -n1 -P "$JOBS" bash -c 'fetch_one "$1"' _
verify

echo "== converting to .iso"
for z in "${ZIPS[@]}"; do
    iso="$ISOS/${z%.zip}.iso"
    [ -f "$iso" ] && continue
    python3 -I "$ROOT/tools/bin2iso.py" "$ISOS/$z" "$iso.part"
    mv "$iso.part" "$iso"
    echo "   $(basename "$iso")"
done
echo "== isos ready"
