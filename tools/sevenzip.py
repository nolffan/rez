#!/usr/bin/env python3
"""Read a 7z archive with Python's lzma module (no 7-Zip needed).

Only what lzma can decode is supported: folders whose coders form a single
chain of copy, LZMA, LZMA2, BCJ (x86) and delta. That is what the LithTech
FTP dump uses; anything else (BCJ2, PPMd, BZip2, Deflate, AES) is refused.
Every file is checked against the CRC-32 the archive records.

The layout (7-Zip's doc/7zFormat.txt): a 32-byte signature header gives
the offset, size and CRC of the "next header", which is either the header
itself (0x01) or an "encoded header" (0x17): streams info for a folder
whose unpacked data is the header. The header holds the main streams info
(pack sizes; folders, i.e. coder chains, and their unpack sizes; and how
each folder's output splits into files, with their CRCs) and the files'
properties (names, which are empty or directories, times, attributes).

  sevenzip.py <archive.7z> <outdir>    extract every file
  sevenzip.py --list <archive.7z>      list them
"""
import lzma
import os
import struct
import sys
import zlib

SIGNATURE = b"7z\xbc\xaf\x27\x1c"

(K_END, K_HEADER, K_ARCHIVE_PROPERTIES, K_ADDITIONAL_STREAMS, K_MAIN_STREAMS,
 K_FILES_INFO, K_PACK_INFO, K_UNPACK_INFO, K_SUBSTREAMS_INFO, K_SIZE, K_CRC,
 K_FOLDER, K_CODERS_UNPACK_SIZE, K_NUM_UNPACK_STREAM, K_EMPTY_STREAM,
 K_EMPTY_FILE, K_ANTI, K_NAME, K_CTIME, K_ATIME, K_MTIME, K_WIN_ATTRIBUTES,
 K_COMMENT, K_ENCODED_HEADER, K_START_POS, K_DUMMY) = range(26)

COPY, LZMA2, DELTA, BCJ, LZMA = b"\x00", b"\x21", b"\x03", b"\x03\x03\x01\x03", b"\x03\x01\x01"


class Reader:
    def __init__(self, data, pos=0):
        self.d, self.p = data, pos

    def byte(self):
        self.p += 1
        return self.d[self.p - 1]

    def bytes(self, n):
        self.p += n
        return self.d[self.p - n:self.p]

    def number(self):
        """7z's variable-length number: the leading 1 bits of the first
        byte say how many more bytes follow."""
        first = self.byte()
        mask, value = 0x80, 0
        for i in range(8):
            if not first & mask:
                return value | (first & (mask - 1)) << (8 * i)
            value |= self.byte() << (8 * i)
            mask >>= 1
        return value

    def bits(self, n):
        out, b, mask = [], 0, 0
        for _ in range(n):
            if not mask:
                b, mask = self.byte(), 0x80
            out.append(bool(b & mask))
            mask >>= 1
        return out

    def defined(self, n):
        """An 'all defined' byte, or a bit vector."""
        return [True] * n if self.byte() else self.bits(n)


def read_pack_info(r):
    pos, n = r.number(), r.number()
    sizes = []
    while True:
        t = r.byte()
        if t == K_END:
            return pos, sizes
        if t == K_SIZE:
            sizes = [r.number() for _ in range(n)]
        elif t == K_CRC:
            defined = r.defined(n)
            [r.bytes(4) for d in defined if d]
        else:
            raise ValueError(f"pack info: property {t}")


def read_folder(r):
    coders = []
    for _ in range(r.number()):
        flags = r.byte()
        method = r.bytes(flags & 0x0f)
        if flags & 0x10:
            raise ValueError("complex coders (several streams) are not supported")
        props = r.bytes(r.number()) if flags & 0x20 else b""
        if flags & 0x80:
            raise ValueError("alternative methods are not supported")
        coders.append((method, props))
    # A single chain: n coders, n - 1 bind pairs (in index, out index), and
    # one packed stream, which the archive then leaves implicit.
    pairs = [(r.number(), r.number()) for _ in range(len(coders) - 1)]
    return {"coders": coders, "pairs": pairs}


def read_unpack_info(r):
    if r.byte() != K_FOLDER:
        raise ValueError("unpack info: no folders")
    n = r.number()
    if r.byte():
        raise ValueError("external folders are not supported")
    folders = [read_folder(r) for _ in range(n)]
    if r.byte() != K_CODERS_UNPACK_SIZE:
        raise ValueError("unpack info: no unpack sizes")
    for f in folders:
        f["sizes"] = [r.number() for _ in f["coders"]]
    while True:
        t = r.byte()
        if t == K_END:
            return folders
        if t == K_CRC:
            defined = r.defined(n)
            for f, d in zip(folders, defined):
                f["crc"] = struct.unpack("<I", r.bytes(4))[0] if d else None
        else:
            raise ValueError(f"unpack info: property {t}")


def read_substreams(r, folders):
    for f in folders:
        f["streams"] = 1
    t = r.byte()
    if t == K_NUM_UNPACK_STREAM:
        for f in folders:
            f["streams"] = r.number()
        t = r.byte()
    for f in folders:
        f["file_sizes"] = []
        if not f["streams"]:
            continue
        total = 0
        if t == K_SIZE:
            for _ in range(f["streams"] - 1):
                f["file_sizes"].append(r.number())
                total += f["file_sizes"][-1]
        f["file_sizes"].append(unpack_size(f) - total)
    if t == K_SIZE:
        t = r.byte()
    # CRCs of the files whose folder does not already give theirs.
    want = [(f, i) for f in folders for i in range(f["streams"])
            if not (f["streams"] == 1 and f.get("crc") is not None)]
    for f in folders:
        f["file_crcs"] = [f.get("crc")] if f["streams"] == 1 else [None] * f["streams"]
    while t != K_END:
        if t == K_CRC:
            defined = r.defined(len(want))
            for (f, i), d in zip(want, defined):
                if d:
                    f["file_crcs"][i] = struct.unpack("<I", r.bytes(4))[0]
        else:
            raise ValueError(f"substreams info: property {t}")
        t = r.byte()


def read_streams_info(r):
    pack_pos, pack_sizes, folders = 0, [], []
    while True:
        t = r.byte()
        if t == K_END:
            break
        if t == K_PACK_INFO:
            pack_pos, pack_sizes = read_pack_info(r)
        elif t == K_UNPACK_INFO:
            folders = read_unpack_info(r)
        elif t == K_SUBSTREAMS_INFO:
            read_substreams(r, folders)
        else:
            raise ValueError(f"streams info: property {t}")
    for f in folders:
        if "streams" not in f:
            f["streams"], f["file_sizes"], f["file_crcs"] = 1, [unpack_size(f)], [f.get("crc")]
    return pack_pos, pack_sizes, folders


def unpack_size(folder):
    """The size of the folder's final output: the coder whose output is
    not bound to another coder's input."""
    bound = {out for _in, out in folder["pairs"]}
    final = [i for i in range(len(folder["coders"])) if i not in bound]
    return folder["sizes"][final[0]]


def filters(folder):
    """The folder's coders as an lzma filter chain (output side first)."""
    coders, pairs = folder["coders"], dict(folder["pairs"])   # in index -> out index
    bound = set(pairs.values())
    i = next(i for i in range(len(coders)) if i not in bound)  # the final output's coder
    chain = []
    while True:
        method, props = coders[i]
        if method == LZMA:
            lc_lp_pb, dict_size = props[0], struct.unpack("<I", props[1:5])[0]
            chain.append({"id": lzma.FILTER_LZMA1, "dict_size": dict_size, "lc": lc_lp_pb % 9,
                          "lp": lc_lp_pb // 9 % 5, "pb": lc_lp_pb // 45})
        elif method == LZMA2:
            p = props[0]
            dict_size = 0xffffffff if p == 40 else (2 | p & 1) << (p // 2 + 11)
            chain.append({"id": lzma.FILTER_LZMA2, "dict_size": dict_size})
        elif method == BCJ:
            chain.append({"id": lzma.FILTER_X86})
        elif method == DELTA:
            chain.append({"id": lzma.FILTER_DELTA, "dist": props[0] + 1})
        elif method != COPY:
            raise ValueError(f"coder {method.hex()} is not supported")
        if i not in pairs:      # this coder reads the packed stream
            return chain
        i = pairs[i]


def unpack(data, pack_pos, pack_sizes, folder, index):
    start = 32 + pack_pos + sum(pack_sizes[:index])
    packed = data[start:start + pack_sizes[index]]
    chain = filters(folder)
    size = unpack_size(folder)
    if not chain:
        out = packed
    else:
        out = lzma.LZMADecompressor(lzma.FORMAT_RAW, filters=chain).decompress(packed, size)
    if len(out) != size:
        raise ValueError(f"folder {index}: unpacked {len(out)} bytes, not {size}")
    if folder.get("crc") is not None and zlib.crc32(out) != folder["crc"]:
        raise ValueError(f"folder {index}: CRC mismatch")
    return out


def read_files_info(r):
    n = r.number()
    files = [{"name": None, "empty": False, "dir": False, "mtime": None} for _ in range(n)]
    empty = []
    while True:
        t = r.byte()
        if t == K_END:
            return files
        size = r.number()
        end = r.p + size
        if t == K_EMPTY_STREAM:
            empty = r.bits(n)
            for f, e in zip(files, empty):
                f["empty"] = f["dir"] = e
        elif t == K_EMPTY_FILE:
            idx = [i for i, e in enumerate(empty) if e]
            for i, e in zip(idx, r.bits(len(idx))):
                files[i]["dir"] = not e
        elif t == K_NAME:
            if r.byte():
                raise ValueError("external names are not supported")
            names = r.bytes(end - r.p).decode("utf-16-le").split("\0")
            for f, name in zip(files, names):
                f["name"] = name
        elif t == K_MTIME:
            defined = r.defined(n)
            if r.byte():
                raise ValueError("external times are not supported")
            for f, d in zip(files, defined):
                if d:
                    f["mtime"] = struct.unpack("<Q", r.bytes(8))[0]
        r.p = end


def entries(path):
    """[(name, is_dir, data or None)] of every entry, CRC-checked."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:6] != SIGNATURE:
        raise ValueError("not a 7z archive")
    start_crc, = struct.unpack_from("<I", data, 8)
    if zlib.crc32(data[12:32]) != start_crc:
        raise ValueError("signature header CRC mismatch")
    off, size, crc = struct.unpack_from("<QQI", data, 12)
    header = data[32 + off:32 + off + size]
    if zlib.crc32(header) != crc:
        raise ValueError("next header CRC mismatch")
    r = Reader(header)
    t = r.byte()
    if t == K_ENCODED_HEADER:
        pack_pos, pack_sizes, folders = read_streams_info(r)
        r = Reader(unpack(data, pack_pos, pack_sizes, folders[0], 0))
        t = r.byte()
    if t != K_HEADER:
        raise ValueError(f"header: type {t}")
    pack_pos, pack_sizes, folders, files = 0, [], [], []
    while True:
        t = r.byte()
        if t == K_END:
            break
        if t == K_MAIN_STREAMS:
            pack_pos, pack_sizes, folders = read_streams_info(r)
        elif t == K_FILES_INFO:
            files = read_files_info(r)
        else:
            raise ValueError(f"header: property {t}")
    # The non-empty files take the folders' streams in order.
    streams = []
    for i, f in enumerate(folders):
        out = unpack(data, pack_pos, pack_sizes, f, i)
        pos = 0
        for size, crc in zip(f["file_sizes"], f["file_crcs"]):
            piece = out[pos:pos + size]
            pos += size
            if crc is not None and zlib.crc32(piece) != crc:
                raise ValueError(f"folder {i}: a file's CRC does not match")
            streams.append(piece)
    result, k = [], 0
    for f in files:
        if f["empty"]:
            result.append((f["name"], f["dir"], None if f["dir"] else b""))
        else:
            result.append((f["name"], False, streams[k]))
            k += 1
    if k != len(streams):
        raise ValueError(f"{len(streams) - k} streams without a file")
    return result


def main():
    args = sys.argv[1:]
    if args[:1] == ["--list"] and len(args) == 2:
        for name, is_dir, data in entries(args[1]):
            print(f"{'dir' if is_dir else len(data):>10} {name}")
        return
    if len(args) != 2:
        sys.exit(__doc__)
    for name, is_dir, data in entries(args[0]):
        dest = os.path.join(args[1], *name.replace("\\", "/").split("/"))
        if is_dir:
            os.makedirs(dest, exist_ok=True)
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(data)


if __name__ == "__main__":
    main()
