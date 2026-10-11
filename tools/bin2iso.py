#!/usr/bin/env python3
"""Turn the data track of a redump .bin/.cue into a plain ISO 9660 image.

  bin2iso.py <image.zip|image.cue> <out.iso>

Given a .zip (as archive.org serves them), the .cue and .bin are read
straight out of it; nothing is unpacked to disk. A zip that holds a plain
.iso instead (redump's DVD images, such as the PlayStation 2 discs) has
that .iso copied out as it is.

Redump images keep raw 2352-byte sectors (sync, header, user data, EDC/ECC).
An .iso is just the 2048 bytes of user data of each sector of the first data
track, which is what tools/isoextract.py and every other ISO reader expect.
Audio tracks (none of these discs keep game data in one) are ignored.
"""
import os
import re
import shutil
import sys
import zipfile

# Where the 2048 user-data bytes start in a sector, by cue track mode.
MODES = {
    "MODE1/2352": (2352, 16),
    "MODE2/2352": (2352, 24),   # XA Form 1: 8-byte subheader after the header
    "MODE1/2048": (2048, 0),
    "MODE2/2336": (2336, 8),
}


def first_data_track(cue_text, where):
    """(bin file name, mode) of the first data track the cue names."""
    cur = None
    for line in cue_text.splitlines():
        m = re.match(r'\s*FILE\s+"(.*)"\s+\S+', line) or re.match(r"\s*FILE\s+(\S+)\s+\S+", line)
        if m:
            cur = m.group(1)
            continue
        m = re.match(r"\s*TRACK\s+(\d+)\s+(\S+)", line)
        if m and m.group(2).upper() != "AUDIO":
            mode = m.group(2).upper()
            if mode not in MODES:
                sys.exit(f"bin2iso: {where}: unsupported track mode {mode}")
            return cur, mode
    sys.exit(f"bin2iso: {where}: no data track")


def convert(src, size, mode, out, where):
    """Copy the user data of every sector of `src` (a binary file) to `out`.
    Redump cues have one FILE per track, so this is exactly the data track."""
    sector, skip = MODES[mode]
    if size % sector:
        sys.exit(f"bin2iso: {where}: {size} bytes is not a whole number of {sector}-byte sectors")
    batch = 512
    with open(out, "wb") as dst:
        while True:
            buf = src.read(sector * batch)
            if not buf:
                break
            if len(buf) % sector:   # zip streams may return short reads
                buf += src.read(sector - len(buf) % sector)
            dst.write(b"".join(buf[i + skip:i + skip + 2048] for i in range(0, len(buf), sector)))


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    image, out = sys.argv[1], sys.argv[2]
    if zipfile.is_zipfile(image):
        with zipfile.ZipFile(image) as z:
            isos = [n for n in z.namelist() if n.lower().endswith(".iso")]
            if len(isos) == 1 and len(z.namelist()) == 1:
                with z.open(isos[0]) as src, open(out, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
                return
            cues = [n for n in z.namelist() if n.lower().endswith(".cue")]
            if len(cues) != 1:
                sys.exit(f"bin2iso: {image}: expected one .cue, found {len(cues)}")
            name, mode = first_data_track(z.read(cues[0]).decode("latin-1"), image)
            name = os.path.join(os.path.dirname(cues[0]), name)
            with z.open(name) as src:
                convert(src, z.getinfo(name).file_size, mode, out, f"{image}:{name}")
    else:
        with open(image, encoding="latin-1") as f:
            name, mode = first_data_track(f.read(), image)
        path = os.path.join(os.path.dirname(os.path.abspath(image)), name)
        with open(path, "rb") as src:
            convert(src, os.path.getsize(path), mode, out, path)


if __name__ == "__main__":
    main()
