#!/usr/bin/env python3
"""Unpack the Microsoft cabinet inside an InstallShield self-extracting exe.

The NOLF2 and Contract J.A.C.K. updates are InstallShield 6 setups wrapped
in a self-extractor: a small PE whose overlay is one Microsoft cabinet
(MSCF) holding the setup's Disk1 folder -- setup.exe, data1.hdr, the
InstallShield cabinets dataN.cab, ... Only MSZIP and uncompressed folders
are handled, which is what those updates use.

  sfxcab.py <setup.exe> <outdir>    extract every file of the cabinet
  sfxcab.py --list <setup.exe>      list them
"""
import os
import struct
import sys
import zlib


def find_cabinet(data):
    """Offset of the cabinet: the first MSCF header whose fields hold up
    (the stub's code contains the four bytes too)."""
    pos = 0
    while True:
        pos = data.find(b"MSCF\0\0\0\0", pos)
        if pos < 0:
            raise ValueError("no Microsoft cabinet in this file")
        size, = struct.unpack_from("<I", data, pos + 8)
        minor, major, nfolders, nfiles = struct.unpack_from("<BBHH", data, pos + 24)
        if major == 1 and 0 < nfolders < 64 and 0 < nfiles < 65536 and pos + size <= len(data):
            return pos
        pos += 4


def read_cabinet(data):
    """[(name, bytes)] of every file in the cabinet `data` carries."""
    base = find_cabinet(data)
    files_off, = struct.unpack_from("<I", data, base + 16)
    nfolders, nfiles, flags = struct.unpack_from("<HHH", data, base + 26)
    pos = base + 36
    folder_res = data_res = 0
    if flags & 4:                       # cfhdrRESERVE_PRESENT
        hdr_res, folder_res, data_res = struct.unpack_from("<HBB", data, pos)
        pos += 4 + hdr_res
    folders = []
    for _ in range(nfolders):
        off, nblocks, kind = struct.unpack_from("<IHH", data, pos)
        pos += 8 + folder_res
        folders.append((off, nblocks, kind & 0xF))
    unpacked = []
    for off, nblocks, kind in folders:
        if kind not in (0, 1):
            raise ValueError(f"folder compression {kind} is not handled (MSZIP or none only)")
        p, out, window = base + off, bytearray(), b""
        for _ in range(nblocks):
            _csum, cb, cu = struct.unpack_from("<IHH", data, p)
            p += 8 + data_res
            block = data[p:p + cb]
            p += cb
            if kind == 0:
                piece = block
            else:
                # MSZIP: "CK" and a deflate stream whose history is the
                # previous block's output.
                if block[:2] != b"CK":
                    raise ValueError("bad MSZIP block")
                z = zlib.decompressobj(-15, zdict=window) if window else zlib.decompressobj(-15)
                piece = z.decompress(block[2:]) + z.flush()
            if len(piece) != cu:
                raise ValueError("block size mismatch")
            out += piece
            window = bytes(piece[-32768:])
        unpacked.append(bytes(out))
    pos = base + files_off
    result = []
    for _ in range(nfiles):
        size, off, folder = struct.unpack_from("<IIH", data, pos)
        end = data.index(b"\0", pos + 16)
        name = data[pos + 16:end].decode("latin-1").replace("\\", "/").lstrip("/")
        pos = end + 1
        result.append((name, unpacked[folder][off:off + size]))
    return result


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "--list":
        for name, blob in read_cabinet(open(args[1], "rb").read()):
            print(f"{len(blob):10} {name}")
        return
    if len(args) != 2:
        sys.exit(__doc__)
    for name, blob in read_cabinet(open(args[0], "rb").read()):
        dest = os.path.join(args[1], name)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        with open(dest, "wb") as f:
            f.write(blob)


if __name__ == "__main__":
    main()
