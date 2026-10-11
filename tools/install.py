#!/usr/bin/env python3
"""Install the games off the disc images in isos/, as their setup programs
would, into one directory per release.

  install.py [--force] <outdir> [name...]   install (default: every release)
  install.py --verify <outdir> [name...]    check installed releases (default:
                                            every one present in <outdir>)
  install.py --list                         list the releases and their discs
  install.py --discs name...                the disc images those releases
                                            use (one per line; fetch-isos.sh)

Each release is written to <outdir>/<name>/ (built in <outdir>/.<name>.tmp
and renamed when complete, so a finished directory is always whole; an
existing one is left alone unless --force). Nothing is run from the discs:
files are read straight out of the ISO 9660 images, and InstallShield
cabinets are unpacked with tools/unshield.

Four installers are reproduced -- each by what its own script and media
say it copies (see README.md for how that was read off the discs):

  is5     NOLF (2000). InstallShield 5. "Normal Install": the disc 1 GAME
          folder (and GAME\\<language> on the multi-language discs), the
          readme and web links, eReg, MOVIES -> Movies, then NOLF2.REZ,
          NOLFDLL.REZ and DATA\\<language>\\NOLFL.REZ off disc 2 and NOLF.REZ
          off disc 1.
  goty    NOLF Game of the Year Edition. InstallShield 6 with every data
          file group linked to a folder of the discs: disc 2's Game, Movies
          and EReg and Data\\NOLF.REZ, and disc 1's Data (the 1.003 update,
          the GOTY rez and the GOTY string-resource rez).
  cab     NOLF2 and Contract J.A.C.K. InstallShield 6 cabinets spanning
          both discs ("Recommended" install): the "Program Files" and
          "Resources" groups, the system DLLs setup puts in <WINSYSDIR>
          (copied beside the game instead, where Windows -- and Wine --
          look first), and the uncompressed files linked to disc 1 (NOLF2's
          launcher and Data\\GAME.REZ).

A new install is checked against games.sha256 before it is renamed into
place: every file recorded for the release must be there with its recorded
hash, and nothing else may be (install.reg, which holds the directory's own
path, is not recorded). A release that fails is left in .<name>.tmp; one
with nothing recorded yet is installed with a warning.

Every directory gets MANIFEST.txt (where each file came from) and
install.reg: the registry values setup writes, for `wine regedit install.reg`.

  vise    The Mac releases (MacPlay): an Installer VISE archive in the disc's
          installer application (NOLF2's continued on disc 2 in "NOLF2
          Install Data"), whose single "Easy Install" package installs the
          whole archive. It is read off the HFS / HFS+ disc with
          tools/hfsextract.py and unpacked with tools/viseextract.py: the
          archive's top folder is the install directory. Resource forks and
          Finder info go in AppleDouble ._ files; symbolic links are made.

A Mac install gets MANIFEST.txt only. nolf-ps2-usa and nolf-ps2-eu (the
PlayStation 2 discs) are listed only so that fetch-isos.sh can fetch them by
name; they are not installed.

games.sha256 records a symbolic link by the SHA-256 of its target.
"""
import fnmatch
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path, PureWindowsPath

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hfsextract import Volume  # noqa: E402
from isoextract import Iso  # noqa: E402
from viseextract import Archive  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ISOS = ROOT / "isos"
UNSHIELD = ROOT / "tools" / "unshield" / "unshield"
SUMS = ROOT / "games.sha256"

NOLF1_USA_1 = "Operative, The - No One Lives Forever (USA) (Disc 1)"
NOLF1_USA_2 = "Operative, The - No One Lives Forever (USA) (Disc 2)"
NOLF1_EU_1 = "Operative, The - No One Lives Forever (Europe) (En,Fr,De,Es,Sv) (Disc 1)"
NOLF1_EU_2 = "Operative, The - No One Lives Forever (Europe) (En,Fr,De,Es,Sv) (Disc 2)"
GOTY_USA_1 = "Operative, The - No One Lives Forever (USA) (Disc 1) (Game of the Year Edition)"
GOTY_EU_1 = "Operative, The - No One Lives Forever (Europe) (Disc 1) (Game of the Year Edition)"
GOTY_IT_1 = "Operative, The - No One Lives Forever (Italy) (Disc 1) (Covermount)"
GOTY_2 = "Operative, The - No One Lives Forever (USA, Europe) (Disc 2) (Game of the Year Edition)"
NOLF2_USA = ["No One Lives Forever 2 - A Spy in H.A.R.M.'s Way (USA) (Disc 1)",
             "No One Lives Forever 2 - A Spy in H.A.R.M.'s Way (USA) (Disc 2)"]
NOLF2_EU = ["No One Lives Forever 2 - A Spy in H.A.R.M.'s Way (Europe) (Disc 1)",
            "No One Lives Forever 2 - A Spy in H.A.R.M.'s Way (Europe) (Disc 2)"]
NOLF2_DE = ["No One Lives Forever 2 - Agentin in geheimer Mission (Germany) (Disc 1)",
            "No One Lives Forever 2 - Agentin in geheimer Mission (Germany) (Disc 2)"]
CJ_USA = ["Contract J.A.C.K. (USA) (Disc 1)", "Contract J.A.C.K. (USA) (Disc 2)"]
CJ_EU = ["Contract J.A.C.K. (Europe) (Disc 1)", "Contract J.A.C.K. (Europe) (Disc 2)"]
# Other platforms' images live in their own subdirectory of isos/ (their
# redump names can be the same as the PC discs').
PS2_USA = "ps2/Operative, The - No One Lives Forever (USA)"
PS2_EU = "ps2/Operative, The - No One Lives Forever (Europe) (En,Fr,De,Es,It)"
MAC_NOLF1 = "mac/Operative, The - No One Lives Forever (USA) (Disc 1) (Game Disc)"
MAC_NOLF2 = ["mac/No One Lives Forever 2 - A Spy in H.A.R.M.'s Way (USA) (Disc 1)",
             "mac/No One Lives Forever 2 - A Spy in H.A.R.M.'s Way (USA) (Disc 2)"]

NOLF1_KEY = r"Software\Monolith Productions\No One Lives Forever\1.0"
NOLF2_KEY = r"SOFTWARE\Monolith Productions\No One Lives Forever 2\1.0"
CJ_KEY = r"SOFTWARE\Monolith Productions\Contract Jack\1.0"

# The GOTY setup's registry set (data1.hdr, "NOLF Registry Settings").
GOTY_UPDATE = "-rez Nolfu003.rez -rez Nolfcres003.rez -rez NolfGoty.rez"

# name -> (installer, [disc images], options). The first group is the
# releases the repository is about; the nolf-eu-<lang> ones are the other
# languages of the multi-language European disc, built only when named.
RELEASES = {
    "nolf-usa":         ("is5", [NOLF1_USA_1, NOLF1_USA_2], {}),
    "nolf-eu":          ("is5", [NOLF1_EU_1, NOLF1_EU_2], {"lang": "English"}),
    "nolf-usa-goty":    ("goty", [GOTY_USA_1, GOTY_2], {}),
    "nolf-eu-goty":     ("goty", [GOTY_EU_1, GOTY_2], {}),
    # The Italian covermount's disc 1 is the GOTY install disc with an
    # Italian manual; the item has no disc 2 of its own, so it is paired
    # with the GOTY play disc. What it installs is nolf-eu-goty's.
    "nolf-it":          ("goty", [GOTY_IT_1, GOTY_2], {}),
    "nolf2-usa":        ("cab", NOLF2_USA, {"key": NOLF2_KEY, "region": "EN", "nolf2": True}),
    "nolf2-eu":         ("cab", NOLF2_EU, {"key": NOLF2_KEY, "region": "EN", "nolf2": True}),
    "nolf2-de":         ("cab", NOLF2_DE, {"key": NOLF2_KEY, "region": "DE", "nolf2": True}),
    "contract-jack-us": ("cab", CJ_USA, {"key": CJ_KEY, "region": "EN"}),
    "contract-jack-eu": ("cab", CJ_EU, {"key": CJ_KEY, "region": "EN"}),
    "nolf-mac-usa":     ("vise", [MAC_NOLF1], {"segments": ["NOLF Installer"]}),
    "nolf2-mac-usa":    ("vise", MAC_NOLF2, {"segments": ["Install No One Lives Forever 2",
                                                         "NOLF2 Install Data"]}),
}
EXTRA = {
    f"nolf-eu-{code}": ("is5", [NOLF1_EU_1, NOLF1_EU_2], {"lang": lang})
    for code, lang in (("fr", "French"), ("de", "German"), ("es", "Spanish"), ("sv", "Swedish"))
}
# The PlayStation 2 port, one DVD each. There is nothing to install: these
# only name the images for fetch-isos.sh.
OTHER_PLATFORMS = {
    "nolf-ps2-usa": ("ps2", [PS2_USA], {}),
    "nolf-ps2-eu":  ("ps2", [PS2_EU], {}),
}
ALL = {**RELEASES, **EXTRA, **OTHER_PLATFORMS}


class Disc:
    """One disc image; paths are matched case-insensitively, as on Windows."""

    def __init__(self, name):
        self.name = name
        path = ISOS / f"{name}.iso"
        if not path.exists():
            sys.exit(f"install: missing {path} -- run ./fetch-isos.sh")
        self.iso = Iso(str(path))
        self.files = {p.lower(): (p, ext, sz) for p, ext, sz in self.iso.walk()}

    def has(self, path):
        return path.lower() in self.files

    def listdir(self, folder, pattern="*", recursive=False):
        """Disc paths of the files in `folder` (relative to it, as on disc)."""
        pre = folder.lower().rstrip("/") + "/" if folder else ""
        out = []
        for low, (p, _e, _s) in sorted(self.files.items()):
            if not low.startswith(pre):
                continue
            rel = p[len(pre):]
            if (recursive or "/" not in rel) and fnmatch.fnmatch(rel.rsplit("/", 1)[-1].lower(), pattern.lower()):
                out.append(rel)
        return out

    def copy(self, path, dest):
        p, ext, sz = self.files[path.lower()]
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as out:
            self.iso.read_file(ext, sz, out)
        return p


class MacDisc:
    """One Mac disc image: an HFS or HFS+ volume."""

    def __init__(self, name):
        self.name = name
        path = ISOS / f"{name}.iso"
        if not path.exists():
            sys.exit(f"install: missing {path} -- run ./fetch-isos.sh")
        self.files = {e.path: e for e in Volume(str(path)).walk() if not e.is_dir}

    def open(self, path):
        """A file's data fork, as a seekable file object."""
        return self.files[path].data.open()


class Install:
    def __init__(self, name, target):
        self.name, self.target = name, target
        self.manifest = {}

    def put(self, disc, src, rel):
        """Copy disc file `src` to `rel` inside the install."""
        p = disc.copy(src, self.target / rel)
        self.manifest[rel] = f"{disc.name}.iso:{p}"

    def copy_folder(self, disc, folder, dest="", pattern="*", recursive=False):
        files = disc.listdir(folder, pattern, recursive)
        for rel in files:
            self.put(disc, f"{folder}/{rel}" if folder else rel, f"{dest}/{rel}" if dest else rel)
        return len(files)

    def write_manifest(self):
        with open(self.target / "MANIFEST.txt", "w") as f:
            f.write(f"# {self.name}: where each file came from (<image>:<path>)\n")
            for rel in sorted(self.manifest, key=str.lower):
                f.write(f"{rel}\t{self.manifest[rel]}\n")

    def write_extras(self, values, key):
        """MANIFEST.txt, and install.reg with `values` under HKLM\\`key` --
        both the native and the 32-bit (Wow6432Node) view, so it works in a
        32- or 64-bit Wine prefix alike."""
        self.write_manifest()
        # Wine maps / to Z:, so this is the directory's own path.
        winpath = "Z:" + str(PureWindowsPath(self.target.parent.resolve() / self.name))
        lines = ["Windows Registry Editor Version 5.00", ""]
        for view in (key, key.replace("\\", "\\Wow6432Node\\", 1)):
            lines.append(f"[HKEY_LOCAL_MACHINE\\{view}]")
            for k, v in values.items():
                v = winpath if v is None else v
                lines.append('"%s"="%s"' % (k, v.replace("\\", "\\\\").replace('"', '\\"')))
            lines.append("")
        (self.target / "install.reg").write_text("\r\n".join(lines) + "\r\n", encoding="utf-16")


def install_is5(inst, discs, lang=None, **_):
    d1, d2 = discs
    n = inst.copy_folder(d1, "Game")
    if lang:
        n += inst.copy_folder(d1, f"Game/{lang}")
    # The multi-language disc keeps each language's readme with its setup
    # script (Setup\<language>); the single-language one on the root.
    n += inst.copy_folder(d1, f"Setup/{lang}" if lang else "", pattern="readme.txt")
    n += inst.copy_folder(d1, "", pattern="*.url")
    for disc in (d1, d2):       # eReg is not on every pressing
        if disc.listdir("EReg"):
            n += inst.copy_folder(disc, "EReg", "eReg", recursive=True)
            break
    n += inst.copy_folder(d1, "Movies", "Movies")
    for src in ("Data/NOLF2.REZ", "Data/NOLFDLL.REZ", f"Data/{lang}/NOLFL.REZ" if lang else None):
        if src and d2.has(src):
            inst.put(d2, src, src.rsplit("/", 1)[-1])
            n += 1
    inst.put(d1, "Data/NOLF.REZ", "NOLF.REZ")
    inst.write_extras({"WorkingDirectory": None}, NOLF1_KEY)
    return n + 1


def install_goty(inst, discs, **_):
    d1, d2 = discs
    n = inst.copy_folder(d2, "Game")
    n += inst.copy_folder(d2, "Movies", "Movies")
    n += inst.copy_folder(d2, "EReg", "EReg", recursive=True)
    inst.put(d2, "Data/NOLF.REZ", "NOLF.REZ")
    n += 1 + inst.copy_folder(d1, "Data", pattern="*.rez")
    inst.write_extras({"WorkingDirectory": None, "Update Command Line": GOTY_UPDATE}, NOLF1_KEY)
    return n


# Which cabinet file groups are installed, and where: groups whose name ends
# in <WINSYSDIR>_<n> are the runtime DLLs setup puts in the system directory.
CAB_GROUPS = ("Program Files", "Resources", "System Files")


def install_cab(inst, discs, key, region, nolf2=False, **_):
    if not UNSHIELD.exists():
        sys.exit(f"install: {UNSHIELD} is not built -- run `make -C tools/unshield`")
    work = inst.target.parent / f".{inst.name}.cab"
    shutil.rmtree(work, ignore_errors=True)
    cab = work / "cab"
    cab.mkdir(parents=True)
    # The cabinet set spans both discs: stage data1.hdr and every dataN.cab.
    for disc in discs:
        for rel in disc.listdir("", "data*.*"):
            if rel.lower().endswith((".cab", ".hdr")):
                disc.copy(rel, cab / rel.lower())
    hdr = str(cab / "data1.hdr")
    groups = subprocess.run([str(UNSHIELD), "g", hdr], check=True, capture_output=True,
                            text=True).stdout.splitlines()
    wanted = [g for g in groups if g in CAB_GROUPS or "<WINSYSDIR>" in g]
    n = 0
    for g in wanted:
        out = work / "x"
        shutil.rmtree(out, ignore_errors=True)
        subprocess.run([str(UNSHIELD), "-d", str(out), "-g", g, "x", hdr], check=True,
                       stdout=subprocess.DEVNULL)
        for top in out.iterdir():          # unshield writes <dir>/<group>/...
            for f in sorted(top.rglob("*")):
                if f.is_file():
                    rel = str(f.relative_to(top))
                    dest = inst.target / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(f), dest)
                    where = "<WINSYSDIR>" if "<WINSYSDIR>" in g else "<TARGETDIR>"
                    inst.manifest[rel] = f"{discs[0].name}/data1.hdr:[{g}] ({where})"
                    n += 1
    shutil.rmtree(work)
    if nolf2:
        # The uncompressed groups: the (SecuROM) launcher on the disc's root,
        # and, for the "Recommended" install, the Data folder's GAME.REZ.
        d1 = discs[0]
        inst.put(d1, "NOLF2.exe", "NOLF2.exe")
        n += 1 + inst.copy_folder(d1, "Data", pattern="*.rez")
    inst.write_extras({"InstallDir": None, "NetRegionCode": region}, key)
    return n


def install_vise(inst, discs, segments):
    """Unpack the Installer VISE archive whose segments are the data forks
    of `segments` (on the release's discs, in order); everything in the
    archive's top folder goes into the install directory."""
    forks = []
    for name in segments:
        disc = next((d for d in discs if name in d.files), None)
        if disc is None:
            sys.exit(f"install: {name} is on none of {inst.name}'s discs")
        forks.append((disc, name))
    arc = Archive([disc.open(name) for disc, name in forks])
    source = f"{forks[0][0].name}.iso:{forks[0][1]}"
    tops = {e.path.split("/", 1)[0] for e in arc.entries}
    if len(tops) != 1:
        sys.exit(f"install: {source}: the archive has {len(tops)} top folders")
    top = tops.pop() + "/"
    n = 0
    for e in arc.entries:
        if not e.path.startswith(top):
            continue
        rel = e.path[len(top):]
        dest = inst.target / rel
        if e.is_dir:
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        arc.extract(e, str(dest))
        inst.manifest[rel] = f"{source}[{e.path}]" + (" (symbolic link)" if e.is_symlink else "")
        side = dest.with_name("._" + dest.name)
        if side.exists():
            inst.manifest[str(side.relative_to(inst.target))] = \
                f"{source}[{e.path}] (resource fork, Finder info)"
        n += 1
    inst.write_manifest()
    return n


INSTALLERS = {"is5": install_is5, "goty": install_goty, "cab": install_cab, "vise": install_vise}


def recorded(name):
    """{path inside the release: sha256} from games.sha256."""
    out = {}
    with open(SUMS) as f:
        for line in f:
            digest, path = line.rstrip("\n").split("  ", 1)
            if path.startswith(name + "/"):
                out[path[len(name) + 1:]] = digest
    return out


def sha256(path):
    """A file's SHA-256; a symbolic link's is that of its target path."""
    if os.path.islink(path):
        return hashlib.sha256(os.readlink(path).encode()).hexdigest()
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def installed(d):
    """The files and symbolic links in install directory d, relative to it."""
    return {str(f.relative_to(d)) for f in d.rglob("*")
            if f.is_symlink() or f.is_file()} - {"install.reg"}


def verify(name, d):
    """Check directory `d` (an install of `name`) against games.sha256: the
    same files, byte for byte. Prints what differs; True if nothing does,
    None if nothing is recorded for `name` (a release added since)."""
    want = recorded(name)
    if not want:
        print(f"   {name}: no hashes recorded in {SUMS.name} -- NOT verified")
        return None
    have = installed(d)
    problems = [f"missing  {p}" for p in sorted(want.keys() - have)]
    problems += [f"extra    {p}" for p in sorted(have - want.keys())]
    problems += [f"changed  {p}" for p in sorted(want.keys() & have) if sha256(d / p) != want[p]]
    for line in problems:
        print(f"   {name}: {line}")
    if not problems:
        print(f"   {name}: all {len(want)} files match {SUMS.name}")
    return not problems


def main():
    args = sys.argv[1:]
    if args == ["--list"]:
        for name, (kind, discs, _o) in ALL.items():
            print(f"{name:<18} {kind:<5} " + " + ".join(discs))
        return
    if args[:1] == ["--discs"]:
        out = []
        for name in args[1:]:
            if name not in ALL:
                sys.exit(f"install: unknown release {name} (see --list)")
            out += [d for d in ALL[name][1] if d not in out]
        print("\n".join(out))
        return
    if args[:1] == ["--verify"]:
        if len(args) < 2:
            sys.exit(__doc__)
        outdir = Path(args[1])
        names = args[2:] or [n for n in ALL if (outdir / n).is_dir()]
        if any(n in OTHER_PLATFORMS for n in names):
            sys.exit("install: the PlayStation 2 discs are not installed")
        if not names:
            sys.exit(f"install: nothing installed in {outdir}")
        bad = 0
        for name in names:
            if name not in ALL:
                sys.exit(f"install: unknown release {name} (see --list)")
            if not (outdir / name).is_dir():
                print(f"   {name}: not installed in {outdir}")
                bad += 1
            elif verify(name, outdir / name) is not True:
                bad += 1
        sys.exit(1 if bad else 0)
    force = "--force" in args
    args = [a for a in args if a != "--force"]
    if not args:
        sys.exit(__doc__)
    outdir = Path(args[0])
    names = args[1:] or list(RELEASES)
    for name in names:
        if name not in ALL:
            sys.exit(f"install: unknown release {name} (see --list)")
        if name in OTHER_PLATFORMS:
            sys.exit(f"install: {name} is a PlayStation 2 disc; there is nothing to install")
    outdir.mkdir(parents=True, exist_ok=True)
    for name in names:
        final = outdir / name
        if final.exists() and not force:
            print(f"== {name}: already installed ({final}); --force to redo")
            continue
        kind, disc_names, opts = ALL[name]
        tmp = outdir / f".{name}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir()
        print(f"== {name} ({kind}: {' + '.join(disc_names)})", flush=True)
        inst = Install(name, tmp)
        disc_class = MacDisc if kind == "vise" else Disc
        n = INSTALLERS[kind](inst, [disc_class(d) for d in disc_names], **opts)
        if verify(name, tmp) is False:
            sys.exit(f"install: {name} does not match {SUMS.name}; left in {tmp}")
        # install.reg names the final path, not the .tmp one.
        if final.exists():
            shutil.rmtree(final)
        tmp.rename(final)
        print(f"   {n} files -> {final}")


if __name__ == "__main__":
    main()
