#!/usr/bin/env python3
"""Minimal ISO9660 (+ Joliet) reader/extractor. No dependencies.

Usage:
  isoextract.py list  <image.iso> [path-prefix]
  isoextract.py x     <image.iso> <outdir> [path-prefix]
"""
import struct
import sys
from pathlib import Path

SECTOR = 2048


class Iso:
    def __init__(self, path):
        self.f = open(path, "rb")
        self.joliet = False
        self.root = self._find_root()

    def _find_root(self):
        pvd_root = None
        svd_root = None
        lba = 16
        while True:
            self.f.seek(lba * SECTOR)
            vd = self.f.read(SECTOR)
            vtype = vd[0]
            if vd[1:6] != b"CD001":
                break
            if vtype == 1 and pvd_root is None:
                pvd_root = vd[156:190]
            elif vtype == 2:
                # Joliet escape sequences: %/@ %/C %/E
                esc = vd[88:120]
                if esc[:3] in (b"%/@", b"%/C", b"%/E"):
                    svd_root = vd[156:190]
            elif vtype == 255:
                break
            lba += 1
        if svd_root is not None:
            self.joliet = True
            return svd_root
        if pvd_root is None:
            raise RuntimeError("no primary volume descriptor found")
        return pvd_root

    def _decode_name(self, raw):
        if self.joliet:
            name = raw.decode("utf-16-be", "replace")
        else:
            name = raw.decode("ascii", "replace")
        return name.split(";")[0].rstrip(".")

    def _read_dir(self, extent, size):
        """Yield (name, is_dir, extent, size) for one directory."""
        self.f.seek(extent * SECTOR)
        data = self.f.read(size)
        off = 0
        while off < len(data):
            rec_len = data[off]
            if rec_len == 0:
                # rest of this sector is padding; jump to next sector
                off = (off // SECTOR + 1) * SECTOR
                continue
            rec = data[off : off + rec_len]
            ext = struct.unpack_from("<I", rec, 2)[0]
            sz = struct.unpack_from("<I", rec, 10)[0]
            flags = rec[25]
            name_len = rec[32]
            raw = rec[33 : 33 + name_len]
            off += rec_len
            if raw in (b"\x00", b"\x01"):
                continue  # . and ..
            yield self._decode_name(raw), bool(flags & 2), ext, sz

    def walk(self, extent=None, size=None, prefix=""):
        """Yield (path, extent, size) for every file on the image."""
        if extent is None:
            extent = struct.unpack_from("<I", self.root, 2)[0]
            size = struct.unpack_from("<I", self.root, 10)[0]
        for name, is_dir, ext, sz in self._read_dir(extent, size):
            p = f"{prefix}{name}"
            if is_dir:
                yield from self.walk(ext, sz, p + "/")
            else:
                yield p, ext, sz

    def read_file(self, extent, size, out):
        self.f.seek(extent * SECTOR)
        left = size
        while left:
            chunk = self.f.read(min(left, 1 << 20))
            if not chunk:
                raise RuntimeError("short read")
            out.write(chunk)
            left -= len(chunk)


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd, image = sys.argv[1], sys.argv[2]
    iso = Iso(image)
    if cmd == "list":
        want = sys.argv[3].lower() if len(sys.argv) > 3 else ""
        for path, _, sz in iso.walk():
            if want in path.lower():
                print(f"{sz:>12} {path}")
    elif cmd == "x":
        outdir = Path(sys.argv[3])
        want = sys.argv[4].lower() if len(sys.argv) > 4 else ""
        n = 0
        for path, ext, sz in iso.walk():
            if want not in path.lower():
                continue
            dest = outdir / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as out:
                iso.read_file(ext, sz, out)
            n += 1
        print(f"extracted {n} files to {outdir}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
