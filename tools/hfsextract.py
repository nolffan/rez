#!/usr/bin/env python3
"""Minimal HFS / HFS+ reader/extractor for Mac CD images. No dependencies.

  hfsextract.py <image> --list          list every file (type, creator, fork sizes)
  hfsextract.py <image> <outdir>        extract every file

The image is a 2048-byte-sector .iso as tools/bin2iso.py writes it. Mac
discs of this era carry an Apple partition map, and the volume is in its
Apple_HFS partition; a bare volume (no map) works too. Both classic HFS and
HFS+ are read, including an HFS+ volume wrapped in an HFS one (as on
NOLF2's discs), and forks fragmented into the extents-overflow file.

A file's data fork is written under its own name. If it has a resource fork
or a type and creator, those and the rest of its Finder info (flags) go
beside it in an AppleDouble file "._<name>", as Mac OS X writes them on
volumes without forks; most Mac tools read them back. Names are MacRoman (HFS) or Unicode
(HFS+, stored decomposed; written here in NFC), with "/" written as ":".
"""
import io
import os
import struct
import sys
import unicodedata

APPLE_HFS = b"Apple_HFS"


class Fork:
    """A data or resource fork: its logical size and its extents (start
    block, block count), read relative to the volume's allocation blocks."""

    def __init__(self, vol, size, extents):
        self.vol, self.size, self.extents = vol, size, extents

    def chunks(self, bufsize=1 << 20):
        """Yield the fork's bytes in order, at most bufsize at a time."""
        left = self.size
        for start, count in self.extents:
            pos = self.vol.alloc_base + start * self.vol.block_size
            n = min(left, count * self.vol.block_size)
            left -= n
            while n:
                self.vol.f.seek(pos)
                buf = self.vol.f.read(min(n, bufsize))
                if not buf:
                    raise IOError("hfsextract: image is truncated")
                yield buf
                pos += len(buf)
                n -= len(buf)
            if not left:
                return
        if left:
            raise IOError(f"hfsextract: fork is {left} bytes short of its extents")

    def read(self):
        return b"".join(self.chunks())

    def open(self):
        """The fork as a read-only, seekable file object."""
        return io.BufferedReader(ForkFile(self), 1 << 16)

    def pread(self, offset, length):
        """Read length bytes at offset (for the B-tree files)."""
        out = []
        pos = 0
        for start, count in self.extents:
            span = count * self.vol.block_size
            if offset < pos + span and length:
                a = offset - pos
                n = min(length, span - a)
                self.vol.f.seek(self.vol.alloc_base + start * self.vol.block_size + a)
                out.append(self.vol.f.read(n))
                offset += n
                length -= n
            pos += span
        return b"".join(out)


class ForkFile(io.RawIOBase):
    """Random access to a fork, for Fork.open()."""

    def __init__(self, fork):
        self.fork, self.pos = fork, 0
        # (offset in the fork, byte offset in the image, length) per extent
        self.spans, at = [], 0
        for start, count in fork.extents:
            n = min(count * fork.vol.block_size, fork.size - at)
            if n <= 0:
                break
            self.spans.append((at, fork.vol.alloc_base + start * fork.vol.block_size, n))
            at += n

    def readable(self):
        return True

    def seekable(self):
        return True

    def seek(self, offset, whence=0):
        self.pos = {0: 0, 1: self.pos, 2: self.fork.size}[whence] + offset
        return self.pos

    def tell(self):
        return self.pos

    def readinto(self, b):
        for at, image, n in self.spans:
            if at <= self.pos < at + n:
                k = min(len(b), at + n - self.pos)
                self.fork.vol.f.seek(image + self.pos - at)
                got = self.fork.vol.f.readinto(memoryview(b)[:k])
                self.pos += got
                return got
        return 0


class Entry:
    """A file or folder on the volume."""

    def __init__(self, path, is_dir, cnid, finfo=b"\0" * 16, data=None, rsrc=None):
        self.path, self.is_dir, self.cnid = path, is_dir, cnid
        self.finfo = finfo                  # the 16-byte FInfo / FileInfo
        self.data, self.rsrc = data, rsrc

    @property
    def type(self):
        return self.finfo[0:4]

    @property
    def creator(self):
        return self.finfo[4:8]


class Volume:
    def __init__(self, path):
        self.f = open(path, "rb")
        start = self._partition_start()
        self.f.seek(start + 1024)
        sig = self.f.read(2)
        if sig == b"BD":
            self._open_hfs(start)
        elif sig in (b"H+", b"HX"):
            self._open_hfsplus(start)
        else:
            raise ValueError(f"hfsextract: {path}: no HFS volume")

    def _partition_start(self):
        """Byte offset of the Apple_HFS partition, or 0 for a bare volume."""
        self.f.seek(0)
        ddm = self.f.read(4)
        if ddm[:2] != b"ER":
            return 0
        bs = struct.unpack(">H", ddm[2:4])[0]
        self.f.seek(bs)
        entry = self.f.read(bs)
        if entry[:2] != b"PM":
            return 0
        count = struct.unpack(">I", entry[4:8])[0]
        for i in range(count):
            self.f.seek(bs * (i + 1))
            entry = self.f.read(bs)
            if entry[48:80].rstrip(b"\0") == APPLE_HFS:
                return struct.unpack(">I", entry[8:12])[0] * bs
        raise ValueError("hfsextract: the partition map has no Apple_HFS partition")

    # -- classic HFS --------------------------------------------------------

    def _open_hfs(self, start):
        self.f.seek(start + 1024)
        mdb = self.f.read(162)
        self.block_size = struct.unpack(">I", mdb[0x14:0x18])[0]
        first = struct.unpack(">H", mdb[0x1C:0x1E])[0]     # drAlBlSt, in 512-byte sectors
        if mdb[0x7C:0x7E] == b"H+":                        # an HFS+ volume wrapped in HFS
            embed_start = struct.unpack(">H", mdb[0x7E:0x80])[0]
            self._open_hfsplus(start + first * 512 + embed_start * self.block_size)
            return
        self.plus = False
        self.alloc_base = start + first * 512
        self.name = mdb[0x25:0x25 + mdb[0x24]].decode("mac_roman")

        def mdb_fork(size_at, ext_at):
            size = struct.unpack(">I", mdb[size_at:size_at + 4])[0]
            return Fork(self, size, self._hfs_extents(mdb[ext_at:ext_at + 12]))

        self.overflow = {}
        xt = mdb_fork(0x82, 0x86)
        for key, rec in self._leaf_records(xt):
            # key: keyLength, forkType, fileID, startBlock (HFSExtentKey)
            fork_type, file_id, start_block = struct.unpack(">BIH", key[1:8])
            self.overflow[(file_id, fork_type, start_block)] = self._hfs_extents(rec[:12])
        self.catalog = mdb_fork(0x92, 0x96)
        self._extend(self.catalog, 4, 0)

    @staticmethod
    def _hfs_extents(raw):
        return [e for e in struct.iter_unpack(">HH", raw) if e[1]]

    # -- HFS+ ---------------------------------------------------------------

    def _open_hfsplus(self, start):
        self.plus = True
        self.f.seek(start + 1024)
        vh = self.f.read(512)
        if vh[:2] not in (b"H+", b"HX"):
            raise ValueError("hfsextract: bad HFS+ volume header")
        self.block_size = struct.unpack(">I", vh[40:44])[0]
        self.alloc_base = start
        self.name = None
        self.overflow = {}
        xt = self._plus_fork(vh, 0xC0)
        for key, rec in self._leaf_records(xt):
            # key: keyLength(2), forkType, pad, fileID, startBlock (HFSPlusExtentKey)
            fork_type, file_id, start_block = struct.unpack(">BxII", key[2:12])
            self.overflow[(file_id, fork_type, start_block)] = self._plus_extents(rec[:64])
        self.catalog = self._plus_fork(vh, 0x110)
        self._extend(self.catalog, 4, 0)

    @staticmethod
    def _plus_extents(raw):
        return [e for e in struct.iter_unpack(">II", raw) if e[1]]

    def _plus_fork(self, raw, at):
        size = struct.unpack(">Q", raw[at:at + 8])[0]
        return Fork(self, size, self._plus_extents(raw[at + 16:at + 80]))

    # -- B-trees, forks -----------------------------------------------------

    def _extend(self, fork, file_id, fork_type):
        """Add a fork's extents from the extents-overflow file."""
        need = -(-fork.size // self.block_size)
        have = sum(c for _, c in fork.extents)
        while have < need:
            more = self.overflow.get((file_id, fork_type, have))
            if not more:
                raise IOError(f"hfsextract: file {file_id}: extents missing from block {have}")
            fork.extents = fork.extents + more
            have += sum(c for _, c in more)

    def _leaf_records(self, fork):
        """Yield (key, record) for every leaf record of a B-tree file."""
        if not fork.size:
            return
        header = fork.pread(0, 512)
        first_leaf = struct.unpack(">I", header[24:28])[0]
        node_size = struct.unpack(">H", header[32:34])[0]
        node = first_leaf
        while node:
            raw = fork.pread(node * node_size, node_size)
            flink, _blink, kind, _height, nrec = struct.unpack(">IIbBH", raw[:12])
            if kind != -1:
                raise IOError("hfsextract: B-tree leaf chain reaches a non-leaf node")
            offs = struct.unpack(f">{nrec + 1}H", raw[node_size - 2 * (nrec + 1):])[::-1]
            for i in range(nrec):
                rec = raw[offs[i]:offs[i + 1]]
                if self.plus:
                    klen = 2 + struct.unpack(">H", rec[:2])[0]
                else:
                    klen = 1 + rec[0]
                    klen += klen & 1                 # HFS keys are padded to even
                yield rec[:klen], rec[klen:]
            node = flink

    def walk(self):
        """Every file and folder, as Entry objects, folders before their contents."""
        folders = {}        # folder id -> (parent id, name)
        files = []
        for key, rec in self._leaf_records(self.catalog):
            if self.plus:
                parent = struct.unpack(">I", key[2:6])[0]
                n = struct.unpack(">H", key[6:8])[0]
                name = unicodedata.normalize("NFC", key[8:8 + 2 * n].decode("utf-16-be"))
                kind = struct.unpack(">h", rec[:2])[0]
            else:
                parent = struct.unpack(">I", key[2:6])[0]
                name = key[7:7 + key[6]].decode("mac_roman")
                kind = rec[0]
            if kind == 1:
                cnid = struct.unpack(">I", rec[8:12] if self.plus else rec[6:10])[0]
                folders[cnid] = (parent, name)
            elif kind == 2:
                files.append((parent, name, rec))

        def path_of(cnid):
            """The folder's path components; None inside HFS+'s hidden
            metadata folders, whose names start with NULs."""
            parts = []
            while cnid in folders and folders[cnid][0] != 1:   # 1 is the root's parent
                cnid, name = folders[cnid][0], folders[cnid][1]
                if "\0" in name:
                    return None
                parts.append(name.replace("/", ":"))
            return parts[::-1]

        dirs = sorted((p, c) for c in folders if folders[c][0] != 1
                      for p in [path_of(c)] if p is not None)
        for parts, cnid in dirs:
            yield Entry("/".join(parts), True, cnid)
        files = [(path_of(parent), name, rec) for parent, name, rec in files]
        for parts, name, rec in sorted((t for t in files if t[0] is not None),
                                       key=lambda t: (t[0], t[1])):
            path = "/".join(parts + [name.replace("/", ":")])
            if self.plus:
                cnid = struct.unpack(">I", rec[8:12])[0]
                finfo = rec[48:64]
                data, rsrc = self._plus_fork(rec, 88), self._plus_fork(rec, 168)
            else:
                cnid = struct.unpack(">I", rec[20:24])[0]
                finfo = rec[4:20]
                data = Fork(self, struct.unpack(">I", rec[26:30])[0], self._hfs_extents(rec[74:86]))
                rsrc = Fork(self, struct.unpack(">I", rec[36:40])[0], self._hfs_extents(rec[86:98]))
            self._extend(data, cnid, 0)
            self._extend(rsrc, cnid, 0xFF)
            yield Entry(path, False, cnid, finfo, data, rsrc)


def appledouble(finfo, rsrc_size):
    """The header of an AppleDouble file holding Finder info (32 bytes:
    FInfo + an empty FXInfo) and then a resource fork of rsrc_size bytes."""
    entries = [(9, 32)] + ([(2, rsrc_size)] if rsrc_size else [])
    head = struct.pack(">II16sH", 0x00051607, 0x00020000, b"Mac OS X".ljust(16), len(entries))
    offset = len(head) + 12 * len(entries)
    for eid, length in entries:
        head += struct.pack(">III", eid, offset, length)
        offset += length
    return head + finfo.ljust(32, b"\0")


def extract(entry, dest):
    """Write a file's data fork to dest and, if it has a resource fork or a
    type and creator, an AppleDouble ._ file (with the Finder info) beside it."""
    with open(dest, "wb") as out:
        for buf in entry.data.chunks():
            out.write(buf)
    if entry.rsrc.size or entry.finfo[:8].strip(b"\0"):     # a resource fork, or a type/creator
        side = os.path.join(os.path.dirname(dest), "._" + os.path.basename(dest))
        with open(side, "wb") as out:
            out.write(appledouble(entry.finfo, entry.rsrc.size))
            for buf in entry.rsrc.chunks():
                out.write(buf)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    vol = Volume(sys.argv[1])
    if sys.argv[2] == "--list":
        for e in vol.walk():
            if not e.is_dir:
                t, c = (x.decode("mac_roman").replace("\0", " ") for x in (e.type, e.creator))
                print(f"{t:4} {c:4} {e.data.size:>11} {e.rsrc.size:>9}  {e.path}")
        return
    outdir = sys.argv[2]
    n = 0
    for e in vol.walk():
        dest = os.path.join(outdir, e.path)
        if e.is_dir:
            os.makedirs(dest, exist_ok=True)
        else:
            os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
            extract(e, dest)
            n += 1
    print(f"{n} files -> {outdir}")


if __name__ == "__main__":
    main()
