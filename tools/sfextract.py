#!/usr/bin/env python3
"""Unpack an Indigo Rose Setup Factory 6 installer (Tron 2.0 Editing Tools
v1.2a), every file CRC-checked.

The overlay after the PE image starts with 8 magic bytes (E0..E7) and a
count of "header" files (the setup engine irsetup.exe, its script
irsetup.dat, language files, and files the author put in the header for
setup to run), each a 260-byte name, the compressed size, the CRC-32 of the
data, and the data as a PKWARE DCL implode stream. The payload files follow
with no headers of their own, one implode stream each (or stored, if the
author chose not to compress one), in the script's order.

irsetup.dat has a record per payload file, in the payload's order: 01 00
00 00, the file's length-prefixed source path on the author's machine, its
length-prefixed base name, source directory and extension, its size, and
later its destination folder (%AppDir%\\..., or %WinDir% ...) and name
(empty for the base name), its stream's size and the file's CRC-32. Each stream is checked against its record: an implode stream
(tools/blast decodes it), or, if the author chose not to compress the
file, the file stored as it is.

  sfextract.py <setup.exe> <outdir>    extract: payload files at their
                                       destinations (%AppDir% -> outdir,
                                       %WinDir% and the like -> outdir too),
                                       header files in outdir/_header/
  sfextract.py --list <setup.exe>      list them
"""
import os
import re
import struct
import subprocess
import sys
import tempfile
import zlib

BLAST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blast", "blast")
MAGIC = bytes(range(0xe0, 0xe8))


def overlay_start(d):
    pe, = struct.unpack_from("<I", d, 0x3c)
    ns, = struct.unpack_from("<H", d, pe + 6)
    opt, = struct.unpack_from("<H", d, pe + 20)
    end = 0
    for i in range(ns):
        raw, ptr = struct.unpack_from("<II", d, pe + 24 + opt + 40 * i + 16)
        end = max(end, ptr + raw)
    return end


def blast(path, off, tmp):
    """Decode the implode stream at `off` of file `path` into `tmp`; the
    number of input bytes it took, or None if it is not one."""
    r = subprocess.run([BLAST, path, str(off), tmp], capture_output=True, text=True)
    if r.returncode:
        return None
    return int(r.stdout.split()[0])


RECORD = re.compile(rb"\x01\x00\x00\x00([\x03-\xff])(?=[A-Za-z]:\\)")
DEST = re.compile(rb"([\x01-\x7f])(%[A-Za-z]+%[\x20-\x7e]*)")


def records(script):
    """[(offset, source path, size, folder, destination)] of irsetup.dat's
    payload records, in the script's order: folder is the destination's
    variable (%AppDir%, %WinDir%, ...), destination the path under it, with
    / separators."""
    out = []
    for m in RECORD.finditer(script):
        e = m.end()
        src = script[e:e + m.group(1)[0]]
        e += len(src)
        base = src.rsplit(b"\\", 1)[1]
        if script[e] != len(base) or script[e + 1:e + 1 + len(base)] != base:
            continue                    # not a record after all
        e += 1 + len(base)
        e += 1 + script[e]              # source directory
        e += 1 + script[e]              # extension
        size, = struct.unpack_from("<I", script, e + 1)
        # The destination folder is the first length-prefixed %...% string
        # after the record's fixed fields, followed (5 bytes on) by the
        # destination name, empty to keep the base name.
        dm = DEST.search(script, e, e + 120)
        if not dm or dm.group(1)[0] != len(dm.group(2)):
            raise ValueError(f"no destination for {src.decode('latin-1')}")
        folder = dm.group(2).decode("latin-1")
        n = dm.end() + 5
        name = script[n + 1:n + 1 + script[n]].decode("latin-1") or base.decode("latin-1")
        var, _, sub = folder.partition("\\")
        dest = "/".join(p for p in sub.split("\\") + [name] if p)
        out.append((m.start(), src.decode("latin-1"), size, var, dest))
    return out


def read_setup(path):
    """Yield ("header", name, data) for each header file, then
    ("payload", (folder, destination), data) for each payload file (as
    records() gives them); raises ValueError on a CRC mismatch or a stream
    that does not fit its record."""
    with open(path, "rb") as f:
        d = f.read()
    o = overlay_start(d)
    if d[o:o + 8] != MAGIC:
        raise ValueError("not a Setup Factory 6 installer")
    n, = struct.unpack_from("<I", d, o + 8)
    o += 12
    fd, tmp = tempfile.mkstemp()
    os.close(fd)
    try:
        script = None
        for _ in range(n):
            name = d[o:o + 260].split(b"\0")[0].decode("latin-1")
            size, crc = struct.unpack_from("<II", d, o + 260)
            o += 268
            data = b""
            if size:
                if blast(path, o, tmp) is None:
                    raise ValueError(f"header file {name}: bad stream")
                with open(tmp, "rb") as f:
                    data = f.read()
            if zlib.crc32(data) != crc:
                raise ValueError(f"header file {name}: CRC mismatch")
            if name.lower() == "irsetup.dat":
                script = data
            yield "header", name, data
            o += size
        recs = records(script)
        ends = [r[0] for r in recs[1:]] + [len(script)]
        for rec, end in zip(recs, ends):
            # The streams are in the records' order. Each record holds its
            # stream's size and the CRC-32 of the file: an implode stream,
            # or the file stored as it is.
            region = script[rec[0]:end]
            used = blast(path, o, tmp)
            data = None
            if used is not None:
                with open(tmp, "rb") as f:
                    data = f.read()
            if data is None or struct.pack("<II", used, zlib.crc32(data)) not in region:
                used, data = rec[2], d[o:o + rec[2]]
                if struct.pack("<II", used, zlib.crc32(data)) not in region:
                    raise ValueError(f"{rec[1]}: the stream at {o:#x} does not match its record")
            yield "payload", rec[3:5], data
            o += used
        if o != len(d):
            raise ValueError(f"{len(d) - o} bytes after the last payload file")
    finally:
        os.unlink(tmp)


def main():
    args = sys.argv[1:]
    if args[:1] == ["--list"] and len(args) == 2:
        for kind, name, data in read_setup(args[1]):
            print(f"{kind:7} {len(data):10} " + (name if kind == "header" else "\\".join(p for p in name if p)))
        return
    if len(args) != 2:
        sys.exit(__doc__)
    for kind, name, data in read_setup(args[0]):
        dest = os.path.join(args[1], "_header", name) if kind == "header" else os.path.join(args[1], name[1])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)


if __name__ == "__main__":
    main()
