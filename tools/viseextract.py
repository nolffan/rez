#!/usr/bin/env python3
"""Read MindVision Installer VISE archives (the Mac installers of NOLF and
NOLF2). No dependencies.

  viseextract.py <segment>... --list      list the archive's files
  viseextract.py <segment>... <outdir>    extract every file, checked

The segments are the archive's files in order: the installer application's
data fork first (it holds the catalog), then any "Install Data" files. Each
file of the archive is written to <outdir>/<path>. A resource fork, or a type
and creator, goes beside it in an AppleDouble "._<name>", as
tools/hfsextract.py writes them; a symbolic link (a file of type slnk,
creator rhap, as Mac OS X keeps them on HFS+) is made as one. Every file is
checked against the CRC-32 the catalog records.

The format, as read off these archives (Installer VISE 8, archive versions
0x8001030c and 0x8001030d; ScummVM's common/compression/vise.cpp reads the
older 3.x "Lite" layout this grew from):

  segment header (44 bytes): "SVCT", segment number, payload length (the
    segment's data runs from offset 44 to 44 + that), archive id, version,
    segment count, ..., catalog offset at +36 (0 if not in this segment).
  catalog: "CVCT", its length, ..., entry count at +16, seven section tags
    (PACK BBrd CODE BDIR PROJ INDN DfIL) and offsets; from +0x64 the body,
    byte-swapped in 16-bit words and raw-deflated. The body starts with one
    record per folder ("DVCT") and file ("FVCT"), depth-first, then the
    installer's own sections (packages, scripts, ...).
  DVCT: 0xa0 fixed bytes, then the name (MacRoman, length at +0x50) and the
    Mac OS X long name (UTF-8, length at +0x4f), if any. The depth below the
    archive root is the high 16 bits at +0x48.
  FVCT: 0xc6 fixed bytes, then the name (length at +0x7a) and long name
    (length at +0xb9). Finder info (type, creator, flags) at +0x2c; created
    and modified dates at +0x3c (seconds since 1904); compressed and
    uncompressed sizes of the data and resource forks at +0x44; CRC-32 of
    the data fork followed by the resource fork at +0x54; depth and segment
    at +0x60; position in that segment at +0x64; offset in its group at
    +0x68.
  data: each stream is raw deflate, byte-swapped in 16-bit words and then
    put through a fixed substitution table. A file of its own has its data
    fork and resource fork compressed separately, one after the other. Small
    files share one stream (a group: every member has the same position, and
    the stream's compressed length is a member's data + resource sizes);
    each member's data fork and then resource fork sit at its group offset
    in the inflated stream. A stream that reaches the end of a segment's
    payload carries on at the start of the next segment's.
  deflate: standard, except that the decoder reads 16 bits at a time, so a
    stored block starts, and the block after one resumes, on an even byte.
    zlib copes unless that differs from its own byte alignment; such a
    stream is inflated here, in Python, instead.
"""
import os
import struct
import sys
import zlib

# The byte substitution undone after the word swap (ScummVM's
# vl3DeobfuscationTable).
TABLE = bytes.fromhex(
    "6ab736ec15d9c873e8389adf2125d0ccfddc16d7e34305c58f48daf23f10236c"
    "777cf9a0a3e9ed468bd8ac54ce2d195e6d7d875dfa5b9be0c7ee9f52a9b90ad1"
    "fe78764a3d445a96901f269d581b8e5759c30b6bfc1de6a27f924f40b406724d"
    "f434aad249adef221ab5babf296889933e3204f5dee16ffb67e47e08aff0ab41"
    "82ea500f2ac635b3a8cae54c458a97aed6662753c91c3c0399c1092e69378d2f"
    "60c2a6184e7ab8cfa73a17d59ef184510da464c41eb13098bb7901f6620eb263"
    "91cbff8071e7d400db752cbd393394bc8c3bb6208524882b70836e7b9cbe1447"
    "654b5681f8121128eb5574a131f7b01386dd5f42d30261950c5ca5cdc007e2f3")

HEADER = 44


def unswap(b):
    """Swap the bytes of each 16-bit word (a trailing odd byte stays)."""
    b = bytearray(b)
    n = len(b) & ~1
    b[0:n:2], b[1:n:2] = b[1:n:2], b[0:n:2]
    return bytes(b)


class Entry:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    @property
    def type(self):
        return self.finfo[0:4]

    @property
    def creator(self):
        return self.finfo[4:8]

    @property
    def is_symlink(self):
        """Mac OS X keeps a symbolic link on HFS+ as a file of type slnk,
        creator rhap, whose data fork is the target; VISE archives it so."""
        return self.finfo[0:8] == b"slnkrhap"


class Archive:
    def __init__(self, segments):
        """segments: the segment files in order, as paths or as open,
        seekable binary file objects."""
        self.files = [open(p, "rb") if isinstance(p, (str, os.PathLike)) else p
                      for p in segments]
        names = [getattr(f, "name", f"segment {i + 1}") for i, f in enumerate(self.files)]
        self.ends = []
        catalog = None
        for i, f in enumerate(self.files):
            f.seek(0)
            h = f.read(HEADER)
            if h[:4] != b"SVCT":
                raise ValueError(f"viseextract: {names[i]}: not a VISE archive segment")
            number, length = struct.unpack(">II", h[4:12])
            if i == 0:          # only the first segment records the count
                self.version, count = struct.unpack(">II", h[16:24])
            at = struct.unpack(">I", h[36:40])[0]
            if number != i + 1:
                raise ValueError(f"viseextract: {names[i]} is segment {number}, not {i + 1}")
            f.seek(0, 2)
            end = min(f.tell(), HEADER + length)
            if at:
                catalog = (f, at)
                end = min(end, at)
            self.ends.append(end)
        if count != len(self.files):
            raise ValueError(f"viseextract: the archive has {count} segments; {len(self.files)} given")
        if catalog is None:
            raise ValueError("viseextract: no segment holds the catalog")
        self.entries = self._catalog(*catalog)
        self._group_key = None

    def _catalog(self, f, at):
        f.seek(at)
        head = f.read(0x64)
        if head[:4] != b"CVCT":
            raise ValueError("viseextract: no catalog where the header says")
        length = struct.unpack(">I", head[4:8])[0]
        count = struct.unpack(">H", head[16:18])[0]
        body = zlib.decompressobj(-15).decompress(unswap(f.read(length)))
        entries, stack, pos = [], [], 0
        while len(entries) < count:
            tag = body[pos:pos + 4]
            if tag == b"DVCT":
                fixed, short, long, depth_at = 0xa0, body[pos + 0x50], body[pos + 0x4f], 0x48
            elif tag == b"FVCT":
                fixed, short, long, depth_at = 0xc6, body[pos + 0x7a], body[pos + 0xb9], 0x60
            else:
                raise ValueError(f"viseextract: unknown catalog record {tag!r}")
            r = body[pos:pos + fixed]
            name = (body[pos + fixed + short:pos + fixed + short + long].decode("utf-8")
                    or body[pos + fixed:pos + fixed + short].decode("mac_roman")).replace("/", ":")
            pos += fixed + short + long
            depth = struct.unpack(">H", r[depth_at:depth_at + 2])[0]
            if depth > len(stack):
                raise ValueError(f"viseextract: {name}: the catalog's depth jumps")
            del stack[depth:]
            path = "/".join(stack + [name])
            if tag == b"DVCT":
                stack.append(name)
                entries.append(Entry(path=path, is_dir=True))
                continue
            cd, ud, cr, ur, crc = struct.unpack(">5I", r[0x44:0x58])
            entries.append(Entry(
                path=path, is_dir=False, finfo=r[0x2c:0x3c],
                created=struct.unpack(">I", r[0x3c:0x40])[0],
                modified=struct.unpack(">I", r[0x40:0x44])[0],
                data_csize=cd, data_size=ud, rsrc_csize=cr, rsrc_size=ur, crc=crc,
                seg=struct.unpack(">H", r[0x62:0x64])[0],
                at=struct.unpack(">I", r[0x64:0x68])[0],
                offset=struct.unpack(">I", r[0x68:0x6c])[0]))
        self.extra = body[pos:]         # the installer's own sections (PACK ...)
        groups = {}
        for e in entries:
            if not e.is_dir:
                groups.setdefault((e.seg, e.at), []).append(e)
        for members in groups.values():
            for e in members:
                e.grouped = len(members) > 1
        return entries

    # -- data ---------------------------------------------------------------

    def _raw(self, seg, at, length, bufsize=1 << 22):
        """Yield length bytes of archive data from segment seg (1-based) at
        offset at, carrying on into the next segments' payloads."""
        i = seg - 1
        while length:
            if at >= self.ends[i]:
                i += 1
                if i >= len(self.files):
                    raise IOError("viseextract: data runs past the last segment")
                at = HEADER
                continue
            n = min(length, self.ends[i] - at, bufsize)
            self.files[i].seek(at)
            buf = self.files[i].read(n)
            if len(buf) != n:
                raise IOError("viseextract: a segment is truncated")
            yield buf
            at += n
            length -= n

    def _skip(self, seg, at, n):
        """Where the archive data n bytes after (seg, at) is."""
        i = seg - 1
        while at + n > self.ends[i]:
            n -= self.ends[i] - at
            i += 1
            at = HEADER
        return i + 1, at + n

    def _stream(self, seg, at, csize):
        """Yield the compressed stream at (seg, at), unswapped and
        substituted, ready for inflating."""
        carry = b""
        for buf in self._raw(seg, at, csize):
            buf = carry + buf
            n = len(buf) & ~1
            carry = buf[n:]
            yield unswap(buf[:n]).translate(TABLE)
        if carry:
            yield carry.translate(TABLE)

    def _inflate(self, seg, at, csize, slow=False):
        """Yield the inflated bytes of the stream at (seg, at): with zlib,
        or (slow) all in Python."""
        if slow:
            yield inflate(b"".join(self._stream(seg, at, csize)))
        else:
            yield from inflate_zlib(self._stream(seg, at, csize))

    def _forks(self, e, slow=False):
        """Yield ("data" | "rsrc", bytes) pieces of a file's forks."""
        if e.grouped:
            key = (e.seg, e.at, slow)
            if self._group_key != key:
                csize = e.data_csize + e.rsrc_csize
                self._group = b"".join(self._inflate(e.seg, e.at, csize, slow))
                self._group_key = key
            blob = self._group[e.offset:e.offset + e.data_size + e.rsrc_size]
            yield "data", blob[:e.data_size]
            yield "rsrc", blob[e.data_size:]
            return
        if e.data_size:
            for chunk in self._inflate(e.seg, e.at, e.data_csize, slow):
                yield "data", chunk
        if e.rsrc_size:
            seg, at = self._skip(e.seg, e.at, e.data_csize)
            for chunk in self._inflate(seg, at, e.rsrc_csize, slow):
                yield "rsrc", chunk

    def extract(self, e, dest):
        """Write a file's data fork to dest and, if it has a resource fork or
        a type and creator, an AppleDouble ._ file beside it; check sizes and
        CRC. A symbolic link is made as one. Should zlib's output not check
        out, the file is inflated again in Python."""
        try:
            self._extract(e, dest)
        except (zlib.error, IOError):
            self._extract(e, dest, slow=True)

    def _extract(self, e, dest, slow=False):
        side = os.path.join(os.path.dirname(dest), "._" + os.path.basename(dest))
        if e.is_symlink:
            target = b"".join(c for _, c in self._forks(e, slow))
            if len(target) != e.data_size or zlib.crc32(target) != e.crc:
                raise IOError(f"viseextract: {e.path}: CRC-32 mismatch")
            if os.path.lexists(dest):
                os.remove(dest)
            os.symlink(target.decode("utf-8"), dest)
            return
        crc, sizes = 0, {"data": 0, "rsrc": 0}
        rsrc = []
        with open(dest, "wb") as out:
            for kind, chunk in self._forks(e, slow):
                crc = zlib.crc32(chunk, crc)
                sizes[kind] += len(chunk)
                if kind == "data":
                    out.write(chunk)
                else:
                    rsrc.append(chunk)
        if (sizes["data"], sizes["rsrc"]) != (e.data_size, e.rsrc_size):
            raise IOError(f"viseextract: {e.path}: inflated to the wrong size")
        if crc != e.crc:
            raise IOError(f"viseextract: {e.path}: CRC-32 mismatch")
        if e.rsrc_size or e.finfo[:8].strip(b"\0"):       # a resource fork, or a type/creator
            with open(side, "wb") as out:
                out.write(appledouble(e.finfo[:16], e.rsrc_size))
                out.writelines(rsrc)
        elif os.path.exists(side):
            os.remove(side)


def appledouble(finfo, rsrc_size):
    """The header of an AppleDouble file holding Finder info (32 bytes:
    FInfo and an empty FXInfo) and then a resource fork of rsrc_size bytes."""
    entries = [(9, 32)] + ([(2, rsrc_size)] if rsrc_size else [])
    head = struct.pack(">II16sH", 0x00051607, 0x00020000, b"Mac OS X".ljust(16), len(entries))
    offset = len(head) + 12 * len(entries)
    for eid, length in entries:
        head += struct.pack(">III", eid, offset, length)
        offset += length
    return head + finfo.ljust(32, b"\0")


# -- deflate, VISE flavour ----------------------------------------------------

LBASE = [3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59,
         67, 83, 99, 115, 131, 163, 195, 227, 258]
LEXT = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0]
DBASE = [1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769,
         1025, 1537, 2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577]
DEXT = [0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11,
        12, 12, 13, 13]
ORDER = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15]


STEP = 1 << 15


def inflate_zlib(chunks):
    """Yield the inflated bytes of a VISE deflate stream (given in pieces),
    using zlib. zlib places a stored block on the next byte, VISE on the next
    even byte, and resumes after one there too; where the two differ, VISE
    left a padding byte that zlib reads as part of the block's lengths (or,
    after a block, as the next block's header) and fails within four bytes.
    So when zlib fails, the input is replayed from a checkpoint to find the
    byte it failed on, the padding byte (the odd-placed one of the four and
    five bytes before it) is dropped, and zlib carries on. When the padding
    was before a stored block's lengths, the block's end is known, and the
    padding after it, if any, is dropped as zlib gets there. A wrong guess
    shows up in the file's CRC-32; the caller then inflates it in Python."""
    pieces = iter(chunks)
    buf = bytearray()           # stream bytes from offset `start`
    start = pos = 0             # pos: offset of the next byte for zlib
    d = zlib.decompressobj(-15)
    marks, outs = [], []        # zlib's state at, and output since, the last steps
    skip = None                 # the offset of padding known to be ahead
    while not d.eof:
        if pos == skip:
            pos, skip = pos + 1, None
            yield from outs     # (a checkpoint must not reach back over it)
            marks, outs = [], []
        while len(buf) < pos - start + STEP:
            more = next(pieces, None)
            if more is None:
                break
            buf += more
        end = pos - start + STEP if skip is None else min(skip, pos + STEP) - start
        piece = bytes(buf[pos - start:end])
        if not piece:
            raise zlib.error("the stream ends early")
        marks.append((pos, d.copy()))
        try:
            outs.append(d.decompress(piece))
            pos += len(piece)
        except zlib.error:
            # Find the shortest input from the oldest checkpoint that fails.
            at, state = marks[0]
            region = bytes(buf[at - start:pos - start + len(piece)])

            def fails(n):
                try:
                    state.copy().decompress(region[:n])
                    return False
                except zlib.error:
                    return True
            lo, hi = 0, len(region)
            while lo < hi:
                mid = (lo + hi) // 2
                if fails(mid):
                    hi = mid
                else:
                    lo = mid + 1
            k = lo - 1
            pad = next((i for i in (k - 3, k - 4) if i >= 0 and (at + i) & 1), None)
            if pad is None:
                raise
            d = state.copy()
            yield d.decompress(region[:pad])
            pos = at + pad + 1
            marks, outs = [], []
            if pad == k - 3 and len(region) >= pad + 3:
                # The padding came before a stored block's lengths: the
                # block ends after them and its data, then pads to even.
                end = pos + 4 + (region[pad + 1] | region[pad + 2] << 8)
                if end & 1:
                    skip = end
            continue
        if len(marks) > 2:              # older output can no longer change
            marks.pop(0)
            yield outs.pop(0)
            del buf[:marks[0][0] - start]
            start = marks[0][0]
    yield from outs
    yield d.flush()


def _huffman(lengths):
    """Canonical Huffman code as (count per length, symbols by code)."""
    counts = [0] * 16
    for n in lengths:
        counts[n] += 1
    counts[0] = 0
    offs = [0] * 16
    for i in range(1, 16):
        offs[i] = offs[i - 1] + counts[i - 1]
    symbols = [0] * len(lengths)
    for s, n in enumerate(lengths):
        if n:
            symbols[offs[n]] = s
            offs[n] += 1
    return counts, symbols


def inflate(src):
    """Inflate raw deflate whose stored blocks, and the blocks after them,
    start on an even byte. Slow, but needed only for those streams."""
    out = bytearray()
    pos = buf = cnt = 0

    def bits(n):
        nonlocal pos, buf, cnt
        while cnt < n:
            if pos >= len(src):
                raise IOError("viseextract: deflate stream runs out")
            buf |= src[pos] << cnt
            pos += 1
            cnt += 8
        v = buf & ((1 << n) - 1)
        buf >>= n
        cnt -= n
        return v

    def decode(code_table):
        counts, symbols = code_table
        code = first = index = 0
        for n in range(1, 16):
            code |= bits(1)
            count = counts[n]
            if code - count < first:
                return symbols[index + code - first]
            index += count
            first = (first + count) << 1
            code <<= 1
        raise IOError("viseextract: bad deflate code")

    fixed = None
    while True:
        last, kind = bits(1), bits(2)
        if kind == 0:
            pos -= cnt // 8                 # bytes read ahead go back
            pos += pos & 1                  # stored blocks start on an even byte
            buf = cnt = 0
            n, check = struct.unpack("<HH", src[pos:pos + 4])
            if n != check ^ 0xFFFF:
                raise IOError("viseextract: bad stored block")
            out += src[pos + 4:pos + 4 + n]
            pos += 4 + n
            if pos > len(src):
                raise IOError("viseextract: deflate stream runs out")
            pos += pos & 1                  # and so does the block after one
        elif kind == 1 or kind == 2:
            if kind == 1:
                if fixed is None:
                    fixed = (_huffman([8] * 144 + [9] * 112 + [7] * 24 + [8] * 8),
                             _huffman([5] * 30))
                lit, dist = fixed
            else:
                nlen, ndist, ncode = bits(5) + 257, bits(5) + 1, bits(4) + 4
                lengths = [0] * 19
                for i in range(ncode):
                    lengths[ORDER[i]] = bits(3)
                code_lengths = _huffman(lengths)
                lengths = []
                while len(lengths) < nlen + ndist:
                    s = decode(code_lengths)
                    if s < 16:
                        lengths.append(s)
                    elif s == 16:
                        lengths += [lengths[-1]] * (3 + bits(2))
                    elif s == 17:
                        lengths += [0] * (3 + bits(3))
                    else:
                        lengths += [0] * (11 + bits(7))
                lit, dist = _huffman(lengths[:nlen]), _huffman(lengths[nlen:])
            while True:
                s = decode(lit)
                if s < 256:
                    out.append(s)
                elif s == 256:
                    break
                else:
                    s -= 257
                    n = LBASE[s] + bits(LEXT[s])
                    d = decode(dist)
                    d = DBASE[d] + bits(DEXT[d])
                    if d > len(out):
                        raise IOError("viseextract: deflate distance too far back")
                    if d >= n:
                        out += out[len(out) - d:len(out) - d + n]
                    else:
                        for _ in range(n):
                            out.append(out[-d])
        else:
            raise IOError("viseextract: bad deflate block type")
        if last:
            return bytes(out)


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        sys.exit(__doc__)
    arc = Archive(args[:-1])
    if args[-1] == "--list":
        for e in arc.entries:
            if not e.is_dir:
                t, c = (x.decode("mac_roman").replace("\0", " ") for x in (e.type, e.creator))
                print(f"{t:4} {c:4} {e.data_size:>11} {e.rsrc_size:>9}  {e.path}")
        return
    outdir = args[-1]
    n = 0
    for e in arc.entries:
        dest = os.path.join(outdir, e.path)
        if e.is_dir:
            os.makedirs(dest, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            arc.extract(e, dest)
            n += 1
    print(f"{n} files -> {outdir}, all matching their CRC-32")


if __name__ == "__main__":
    main()
