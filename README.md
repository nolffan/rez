# rez — the No One Lives Forever discs, installed

Fetches the redump images of every PC release of *The Operative: No One
Lives Forever*, *No One Lives Forever 2* and *Contract J.A.C.K.* from
[archive.org/details/nolf-pc-redump](https://archive.org/details/nolf-pc-redump),
and of the Mac releases of NOLF and NOLF2, and installs each release from
them the way its own setup program would: one directory per release,
holding everything the game runs with. It also fetches the discs of NOLF's
PlayStation 2 port, which are kept as images only.

```sh
./fetch-isos.sh        # ~18.0 GB of zips -> isos/, checked, converted to .iso
./install-games.sh     # -> games/<release>/ (~17 GB for all twelve), each checked
```

Both scripts take release names (the table below) to work on just those.
`./fetch-isos.sh nolf-eu-goty && ./install-games.sh nolf-eu-goty` downloads
only that release's two discs and installs it. Both are re-runnable: a
finished step is not repeated, and an interrupted download resumes.
`--force` reinstalls a release that is already installed, and
`./install-games.sh --verify [name...]` re-checks installed ones (by default,
every one in `games/`). `tools/install.py --list` shows each release's discs.

Requirements: `bash`, `curl`, `sha256sum`, `python3`, and a C compiler,
`make` and zlib headers for `tools/unshield`.

## isos/

`isos/SHA256SUMS` lists the 25 zips exactly as archive.org serves them.
`fetch-isos.sh` checks every zip against it before using it. Each PC zip
holds a redump `.bin`/`.cue` with raw 2352-byte sectors. `tools/bin2iso.py` reads the
data track straight out of the zip and writes a plain 2048-byte-sector `.iso`
beside it, under the same name.

### PlayStation 2

The PS2 port's redump images come from
[PS2-Redump-2024-Individual-Games-Part11](https://archive.org/details/PS2-Redump-2024-Individual-Games-Part11).
The [CG_Sony_PlayStation_2](https://archive.org/details/CG_Sony_PlayStation_2)
item has only box and disc scans. They are kept in `isos/ps2/`. Each zip
holds a plain DVD `.iso`, which `bin2iso.py` copies out unchanged; both
match redump's SHA-1. There is nothing to install, so `install-games.sh`
refuses these names.

| Name | Disc |
|---|---|
| `nolf-ps2-usa` | Operative, The - No One Lives Forever (USA) |
| `nolf-ps2-eu` | Operative, The - No One Lives Forever (Europe) (En,Fr,De,Es,It) |

`./fetch-isos.sh nolf-ps2-usa nolf-ps2-eu` fetches just these two.

### Mac

The MacPlay releases' redump images come from
[REDUMP_Apple_-_Macintosh](https://archive.org/details/REDUMP_Apple_-_Macintosh)
and are kept in `isos/mac/`. Redump names them like PC discs, and NOLF2's
are named exactly like the PC NOLF2 USA ones, hence the subdirectory. They
are `.bin`/`.cue` like the PC zips and are converted the same way. The
`.iso` is then the disc's plain data, but not an ISO 9660 filesystem: each
disc has an Apple partition map with one volume, classic HFS on NOLF's and
HFS+ (wrapped in HFS) on NOLF2's. `tools/hfsextract.py` reads them. Every
image's `.bin` matches redump's SHA-1. Redump has only NOLF's game disc,
and no European Mac discs. They are installed as `nolf-mac-usa` and
`nolf2-mac-usa` (below).

## games/

| Release | Discs | Installer |
|---|---|---|
| `nolf-usa` | NOLF (USA) 1 + 2 | InstallShield 5 |
| `nolf-eu` | NOLF (Europe) (En,Fr,De,Es,Sv) 1 + 2, English | InstallShield 5 |
| `nolf-usa-goty` | NOLF GOTY (USA) 1 + GOTY (USA, Europe) 2 | InstallShield 6, linked folders |
| `nolf-eu-goty` | NOLF GOTY (Europe) 1 + GOTY (USA, Europe) 2 | InstallShield 6, linked folders |
| `nolf-it` | NOLF (Italy) Covermount 1 + GOTY (USA, Europe) 2 | InstallShield 6, linked folders |
| `nolf2-usa` | NOLF2 (USA) 1 + 2 | InstallShield 6 cabinets |
| `nolf2-eu` | NOLF2 (Europe) 1 + 2 | InstallShield 6 cabinets |
| `nolf2-de` | NOLF2 (Germany) 1 + 2 | InstallShield 6 cabinets |
| `contract-jack-us` | Contract J.A.C.K. (USA) 1 + 2 | InstallShield 6 cabinets |
| `contract-jack-eu` | Contract J.A.C.K. (Europe) 1 + 2 | InstallShield 6 cabinets |
| `nolf-mac-usa` | NOLF (USA) Mac game disc | Installer VISE |
| `nolf2-mac-usa` | NOLF2 (USA) Mac 1 + 2 | Installer VISE, two segments |

`nolf-eu-fr`, `nolf-eu-de`, `nolf-eu-es` and `nolf-eu-sv` are the other
languages of the European NOLF discs. They are installed only when named.

Each directory also has a `MANIFEST.txt`, recording which image and path every
file came from. A PC release also has an `install.reg` with the registry
values setup writes, pointing at the directory's own path through Wine's
`Z:` drive. Import it with `wine regedit install.reg`. It writes both the
native and the `Wow6432Node` view, so it works in 32- and 64-bit prefixes.

`games.sha256` holds the SHA-256 of every installed file of every release
except `install.reg`, which contains the directory's path. A symbolic link
(the Mac releases have some) is recorded by the SHA-256 of its target. Each install is
checked against it before it is moved into place. Every recorded file must be
present with its hash, and there must be no other files. A release that does
not match is left in `games/.<name>.tmp`, and the script fails. Playing the
game changes its directory (the engine rewrites `autoexec.cfg` and writes
saves), so `--verify` will then report those files.

### What each installer does

Nothing on the discs is executed. What gets copied, and where, was read from
each setup's own script and media.

- **InstallShield 5** (NOLF, 2000) uses a compiled `SETUP.INS` script. On the
  European disc there is one script per language under `Setup\<language>`.
  A "Normal Install" copies:
  - disc 1 `GAME\*.*` → install dir;
  - on the European disc, also `GAME\<language>\*.*` → install dir (the
    localised `NOLF.exe` / `NolfServ.exe`);
  - `README.TXT` and `*.URL` → install dir;
  - `EREG` → `eReg\`;
  - `MOVIES` → `Movies\`;
  - from disc 2: `DATA\NOLF2.REZ`, `DATA\NOLFDLL.REZ` and, except in
    English, `DATA\<language>\NOLFL.REZ`;
  - from disc 1: `DATA\NOLF.REZ`.

  The registry value is `WorkingDirectory`.
- **InstallShield 6, linked folders** (NOLF Game of the Year) has a
  `data1.cab` that holds only setup's own support files. The data file
  groups use dynamic file linking: they are empty in `data1.hdr` and take
  whole folders off the discs at install time.
  - From disc 2: `Game`, `Movies` and `EReg`, plus `Data\NOLF.REZ`.
  - From disc 1: the `Data` folder's rez files (`NOLF2.REZ`, the 1.003
    update and the GOTY rez).

  The registry values are `WorkingDirectory` and `Update Command Line` (the
  extra `-rez` arguments the launcher appends).
- **InstallShield 6 cabinets** (NOLF2, Contract J.A.C.K.) span both discs.
  The "Recommended" install unpacks the `Program Files` and `Resources` file
  groups into the install directory, using `tools/unshield`. NOLF2 also
  copies two uncompressed files off disc 1: its launcher `NOLF2.exe` and
  `Data\GAME.REZ`.

  Setup installs the C/MFC runtime DLLs into `<WINSYSDIR>`: MFC42, MFC42U,
  MSVCP60 and MSVCRT for NOLF2; MFC71, MSVCP71 and MSVCR71 for Contract
  J.A.C.K. These are put in the game directory instead, where Windows and
  Wine look first; the manifest marks them. The registry values are
  `InstallDir` and `NetRegionCode`, taken from the setup's string table.

- **Installer VISE** (the Mac releases, MacPlay) is a single application
  whose data fork is a compressed archive; NOLF2's continues in `NOLF2
  Install Data` on disc 2. Each has one package, "Easy Install", which
  installs the whole archive: its top folder (`No One Lives Forever`, `No
  One Lives Forever 2`) is the install directory. `tools/hfsextract.py`
  reads the installer off the disc and `tools/viseextract.py` unpacks it,
  checking every file against the CRC-32 the archive records. There is no
  registry; the manifest notes each file's archive path.

  Mac files have two forks and Finder info (type, creator, flags). A file's
  resource fork, or its type and creator, goes beside it in an AppleDouble
  `._<name>` file, as Mac OS X itself writes them on volumes without forks.
  Mac OS X symbolic links (stored as files of type `slnk`, creator `rhap`)
  are made as links. Six of NOLF2's point at its developers' machines
  (`/Users/Shared/Omni/...`) and dangle, as they would on a Mac.

Left out: the DirectX, GameSpy Arcade, Windows Media and audio-codec
installers that setup offers to run, and the Start-menu shortcuts.

### The Mac releases

Both are PowerPC builds, which no current Mac runs.

- NOLF (2002, Hyperion's port) is Carbon CFM, for Mac OS 9 (with
  CarbonLib) and Mac OS X. `NOLF/LithTech` is the engine, a PEF
  application with an OpenGL (AGL) renderer, which the `No one lives
  forever.app` launcher starts. The game modules (`cshell.dll`,
  `object.lto`, ...) are PEF code too. CodeWarrior left each function's
  name in its traceback table, so the engine's ~5,000 functions are named.
  The game data is `NOLF/NOLF.REZ` and the loose `NOLF/NOLF/` folder.
  `NolfServ` comes with its `.xSYM` debug symbols.
- NOLF2 (2003) is Mach-O, for Mac OS X: `NOLF2.app/Contents/MacOS/NOLF2` is
  the engine, linked against `OpenGL.framework`, with The Omni Group's
  display code (`OGLDisplay` and friends, and the Omni frameworks beside
  it). The game modules are bundles in `Contents/Resources` (`CShell.dll`,
  `Object.lto`, ...). None of them is stripped: the engine has ~19,500
  symbols, `Object.lto` ~23,000 and `CShell.dll` ~17,000. The data is
  `data/*.REZ`.

### Notes on the discs

- The Italian covermount's disc 1 is the GOTY install disc; its only
  difference is an Italian manual. The item has no Italian disc 2, so
  `nolf-it` uses the GOTY play disc. The three GOTY installs are
  byte-identical.
- The German NOLF disc 2 is file-for-file the European one, so it adds no
  release.
- Between regions, NOLF2 and Contract J.A.C.K. differ only in their `.url`
  shortcuts.
- The NOLF2 USA disc 2 comes in two dumps (`(Disc 2)` and `(Disc 2) (Alt)`).
  `nolf2-usa` uses `(Disc 2)`; the installed game does not depend on that
  disc's contents.
- `~/src/nolfsrc/ISOS`'s `NOLF1-CD1.iso` and `NOLF1-CD2.iso` contain the same
  files as the GOTY (Europe) disc 1 and the GOTY disc 2 here. Only the
  images' padding differs, so their image hashes do not match.

### Copy protection

The retail executables are as shipped:
- `NOLF.exe` (the launcher) of the 2000 release is SafeDisc-wrapped.
- NOLF2's `Lithtech.exe` is SecuROM, and so is Contract J.A.C.K.'s.
- The GOTY binaries and the 2000 release's `lithtech.exe` are unprotected.

Both NOLF1 trees were checked under Wine 9 (in `~/src/nolfsrc`'s build
container). `lithtech.exe` loads `Worlds\T01S01` and keeps running. The
2000 engine takes its arguments on the command line, because it has no
`-cmdfile`:

```sh
wine lithtech.exe -rez nolf.rez -rez nolf2.rez -rez nolfdll.rez -rez nolfl.rez -rez custom \
    ++windowed 1 +runworld 'Worlds\T01S01'
```

## Demos, patches and map packs

`demos/`, `patches/` and `mappacks/` hold the released demos, updates and
map packs. Each one (an installer `.exe`, or an unpacked map pack's folder)
is kept as a `.tar.xz` split into chunks of at most 45,000,000 bytes:
`<item>.tar.xz.c001`, `.c002`, and so on. The chunks are what is committed.

```sh
./assemble-artifacts.sh                 # every archive -> artifacts/<category>/<item>.tar.xz
./assemble-artifacts.sh demos           # one category, or one item: si_nolf2_demo.exe
tar -xJf artifacts/demos/si_nolf2_demo.exe.tar.xz -C <dir>
```

Each assembled archive is checked against `artifacts/SHA256SUMS`. A missing
or damaged chunk fails the check and nothing is written.
`tools/pack-artifacts.sh <item>...` makes the chunks for a new or changed
item and records its archive's hash. The archives carry no owner names, and
every file in them is dated 1970-01-01, so they say nothing about who
packed them or when. Packing an item again gives the same bytes.

## tools/

| Tool | |
|---|---|
| `bin2iso.py` | redump `.zip`/`.cue` → `.iso` (the first data track's user data, or a zipped `.iso` as is) |
| `isoextract.py` | ISO 9660 / Joliet reader, from `~/src/nolfsrc/tools` |
| `hfsextract.py` | HFS / HFS+ reader for the Mac images (`--list`, or extract with AppleDouble `._` files) |
| `viseextract.py` | Installer VISE 8 archive reader (`--list`, or extract, CRC-checked); its docstring describes the format |
| `install.py` | the installers above; `--list` shows the releases and their discs |
| `pack-artifacts.sh` | an item of `demos/`, `patches/` or `mappacks/` → chunked `.tar.xz` (above) |
| `unshield/` | [unshield](https://github.com/twogood/unshield) 1.5.1 (MIT), vendored with a plain Makefile in place of CMake |
