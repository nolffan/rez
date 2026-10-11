#!/usr/bin/env bash
# Fetch the redump images of No One Lives Forever, NOLF2 and Contract J.A.C.K.
# from https://archive.org/details/nolf-pc-redump into isos/, check them
# against isos/SHA256SUMS, and turn each zipped .bin/.cue into a plain
# 2048-byte-sector .iso beside it.
#
#   ./fetch-isos.sh            fetch whatever is missing, verify, convert
#   ./fetch-isos.sh --verify   only check the zips against SHA256SUMS
#
# A rerun downloads nothing that is already there (and resumes partial files).
set -euo pipefail

ROOT=$(cd "$(dirname "$0")" && pwd)
ISOS="$ROOT/isos"
BASE="https://archive.org/download/nolf-pc-redump/NOLF-PC-REDUMP"
JOBS=${JOBS:-4}

die() { echo "fetch-isos: $*" >&2; exit 1; }
for t in curl sha256sum python3; do
    command -v "$t" >/dev/null || die "$t is required"
done

# The zips, in SHA256SUMS order; the names are the item's own.
mapfile -t ZIPS < <(sed -n 's/^[0-9a-f]\{64\}  //p' "$ISOS/SHA256SUMS")
[ ${#ZIPS[@]} -gt 0 ] || die "no entries in $ISOS/SHA256SUMS"

verify() {
    echo "== checking zips against SHA256SUMS"
    (cd "$ISOS" && sha256sum -c --quiet SHA256SUMS) || die "checksum mismatch (delete the bad zip and rerun)"
    echo "== all ${#ZIPS[@]} zips OK"
}

if [ "${1:-}" = "--verify" ]; then verify; exit 0; fi

urlencode() { python3 -I -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$1"; }

fetch_one() {
    local z="$1" url
    [ -f "$ISOS/$z" ] && return 0
    url="$BASE/$(urlencode "$z")"
    echo "-> $z"
    curl -fsSL --retry 10 --retry-delay 5 -C - -o "$ISOS/$z.part" "$url"
    mv "$ISOS/$z.part" "$ISOS/$z"
    echo "<- $z"
}
export -f fetch_one urlencode
export ISOS BASE

echo "== fetching ${#ZIPS[@]} zips into $ISOS ($JOBS at a time)"
printf '%s\0' "${ZIPS[@]}" | xargs -0 -n1 -P "$JOBS" bash -c 'fetch_one "$1"' _
verify

echo "== converting .bin/.cue to .iso"
for z in "${ZIPS[@]}"; do
    iso="$ISOS/${z%.zip}.iso"
    [ -f "$iso" ] && continue
    python3 -I "$ROOT/tools/bin2iso.py" "$ISOS/$z" "$iso.part"
    mv "$iso.part" "$iso"
    echo "   $(basename "$iso")"
done
echo "== isos ready"
