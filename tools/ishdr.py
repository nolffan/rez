#!/usr/bin/env python3
"""Read what an InstallShield 6/7 setup installs from its data1.hdr.

Aliens versus Predator 2, Primal Hunt and Tron 2.0 lay out their setups in
data1.hdr: setup types, which name components, which hold file groups,
whose files are either compressed into the dataN.cab cabinets (unpacked
with tools/unshield) or uncompressed, linked to the disc (unshield skips
those). This reads the part of the header unshield does not show:

  setup types   at cab descriptor + 0x276: u32 count, u32 table of
                descriptor offsets; a descriptor is u32 name, description
                and display name, u32 count, u32 table of component names.
  components    as in unshield: u32 name, 0x6b bytes, u16 group count,
                u32 table of group names.
  file groups   u32 name; +0x16 first and +0x1a last file index; +0x1e the
                disc folder the uncompressed files are in; +0x26 language
                ("0009" English, "0010" Italian; "0" or none for all);
                +0x3a the destination (<TARGETDIR>[\\sub], <WINSYSDIR>,
                <SUPPORTDIR>, <szStartMenu>, ...).
  files         0x57-byte descriptors (u16 flags: 4 compressed, 8 invalid;
                u64 size; u32 name; u16 directory).

All offsets are relative to the cab descriptor, as the strings are.

  ishdr.py <data1.hdr>     list setup types, components and file groups
"""
import struct
import sys

FILE_COMPRESSED = 4
FILE_INVALID = 8
MAX_LIST = 71           # entries in each of the hash tables of groups, components


class Header:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.d = f.read()
        self.cd, = struct.unpack_from("<I", self.d, 12)
        (fto, _a, _b, _c, ndir, _d, _e, nfile, fto2) = struct.unpack_from("<9I", self.d, self.cd + 0xc)
        self.fto, self.fto2 = fto, fto2
        table = [self.u32(fto + 4 * i) for i in range(ndir + nfile)]
        self.dirs = [self.str(fto + table[i]) for i in range(ndir)]
        self.groups = {}
        for desc in self.chain(0x3e):
            g = self.group(desc)
            self.groups[g["name"]] = g
        self.components = {}
        for desc in self.chain(0x3e + 4 * MAX_LIST):
            name = self.str(self.u32(desc))
            n, = struct.unpack_from("<H", self.d, self.cd + desc + 4 + 0x6b)
            tab = self.u32(desc + 4 + 0x6b + 2)
            self.components[name] = [self.str(self.u32(tab + 4 * i)) for i in range(n)]
        self.setup_types = {}
        count, tab = self.u32(self.u32(0x276)), self.u32(self.u32(0x276) + 4)
        for i in range(count):
            desc = self.u32(tab + 4 * i)
            n, ctab = self.u32(desc + 12), self.u32(desc + 16)
            self.setup_types[self.str(self.u32(desc))] = [self.str(self.u32(ctab + 4 * j)) for j in range(n)]

    def u32(self, off):
        return struct.unpack_from("<I", self.d, self.cd + off)[0]

    def str(self, off):
        o = self.cd + off
        return self.d[o:self.d.index(b"\0", o)].decode("latin-1")

    def chain(self, base):
        """Descriptor offsets of the linked lists hashed into the table at base."""
        out = []
        for i in range(MAX_LIST):
            node = self.u32(base + 4 * i)
            while node:
                _name, desc, node = struct.unpack_from("<III", self.d, self.cd + node)
                out.append(desc)
        return out

    def opt(self, off):
        """The string a descriptor field points at, or "" for none."""
        v = self.u32(off)
        return self.str(v) if v else ""

    def group(self, desc):
        first, last = struct.unpack_from("<II", self.d, self.cd + desc + 0x16)
        files = []
        for i in range(first, last + 1):
            p = self.cd + self.fto + self.fto2 + i * 0x57
            flags, size = struct.unpack_from("<HQ", self.d, p)
            name_off, di = struct.unpack_from("<IH", self.d, p + 0x3a)
            if flags & FILE_INVALID:
                continue
            path = self.dirs[di] + "\\" + self.str(self.fto + name_off) if self.dirs[di] \
                else self.str(self.fto + name_off)
            files.append({"path": path, "size": size, "compressed": bool(flags & FILE_COMPRESSED)})
        return {"name": self.str(self.u32(desc)), "source": self.opt(desc + 0x1e),
                "language": self.opt(desc + 0x26), "target": self.opt(desc + 0x3a), "files": files}


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    h = Header(sys.argv[1])
    for name, comps in h.setup_types.items():
        print(f"setup type {name}: " + ", ".join(comps))
    for name, groups in sorted(h.components.items()):
        if groups and not name.startswith("<Support>"):
            print(f"component {name}: " + ", ".join(groups))
    for name, g in sorted(h.groups.items()):
        if name.startswith("<"):
            continue
        print(f"group {name} -> {g['target']} (source {g['source'] or '-'}, language {g['language'] or '-'})")
        for f in g["files"]:
            print(f"   {'c' if f['compressed'] else 'u'} {f['size']:11} {f['path']}")


if __name__ == "__main__":
    main()
