# rez — the No One Lives Forever discs, and other LithTech games, installed

Fetches the redump images of every PC release of *The Operative: No One
Lives Forever*, *No One Lives Forever 2* and *Contract J.A.C.K.* from
[archive.org/details/nolf-pc-redump](https://archive.org/details/nolf-pc-redump),
and of the Mac releases of NOLF and NOLF2, and installs each release from
them the way its own setup program would: one directory per release,
holding everything the game runs with. The other LithTech games are
installed the same way: *Aliens versus Predator 2* and its expansion
*Primal Hunt* (below), and *Tron 2.0*. It also fetches the discs of NOLF's
PlayStation 2 port and AvP2's demo disc, which are kept as images only.
Beside the games, it fetches the LithTech Jupiter SDK, NOLF2's engine
generation, and installs its source into `sdk/` (below).

```sh
./fetch-isos.sh        # ~23.7 GB of zips -> isos/, checked, converted to .iso
./install-games.sh     # -> games/<release>/ (~28 GB for all twenty-one), each checked
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

`isos/SHA256SUMS` lists the 38 zips, and the SDK's image (`isos/sdk/`,
below), exactly as archive.org serves them. `fetch-isos.sh` checks every
one against it before using it. Each PC zip
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

### Aliens versus Predator 2 and Tron 2.0

AvP2's and Primal Hunt's redump images come from
[archive.org/details/avp-pc-redump](https://archive.org/details/avp-pc-redump),
and Tron 2.0's from
[archive.org/details/tron20usa](https://archive.org/details/tron20usa). Each
zip's SHA-1 matches the one archive.org lists. They are PC `.bin`/`.cue`
zips, kept in `isos/` beside NOLF's, and are converted the same way. Of the
AvP item, only the LithTech games are fetched: AvP2 (USA, Europe, Italy),
Primal Hunt (USA, its Alt dump, Europe, Italy) and the AvP2 demo disc. The
16 discs of the first *Aliens Versus Predator* (1999, Rebellion's engine)
are left out.

The demo disc (`avp2-demo-usa`) holds two demo installers
(`avp2spdemo.exe`, `avp2mpdemo2.exe`) and is kept as an image only, like
the PS2 discs. `./fetch-isos.sh avp2-demo-usa` fetches it.

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
| `nolf2-eu-1.3` | NOLF2 (Europe) 1 + 2, with the English 1.3 update | `nolf2-eu`, then `patches/nolf2-update_1x3.exe` |
| `contract-jack-us` | Contract J.A.C.K. (USA) 1 + 2 | InstallShield 6 cabinets |
| `contract-jack-eu` | Contract J.A.C.K. (Europe) 1 + 2 | InstallShield 6 cabinets |
| `contract-jack-eu-1.1` | Contract J.A.C.K. (Europe) 1 + 2, with the English 1.1 update | `contract-jack-eu`, then `patches/contractjack_update_en_10_11.exe` |
| `nolf-mac-usa` | NOLF (USA) Mac game disc | Installer VISE |
| `nolf2-mac-usa` | NOLF2 (USA) Mac 1 + 2 | Installer VISE, two segments |
| `avp2-usa` | AvP2 (USA) 1 + (USA, Asia) 2 | InstallShield 6 cabinets, setup type "Typical" |
| `avp2-eu` | AvP2 (Europe) 1 + 2 | InstallShield 6 cabinets, setup type "Typical" |
| `avp2-it` | AvP2 (Italy) 1 + 2 | InstallShield 6 cabinets, setup type "Typical", Italian |
| `avp2-ph-usa` | AvP2: Primal Hunt (USA) | InstallShield 6 cabinets, setup type "Typical" |
| `avp2-ph-eu` | AvP2: Primal Hunt (Europe) | InstallShield 6 cabinets, setup type "Typical" |
| `avp2-ph-it` | AvP2: Primal Hunt (Italy) | InstallShield 6 cabinets, setup type "Typical", Italian |
| `tron2-usa` | Tron 2.0 (USA) 1 + 2 | InstallShield 6 cabinets, "Recommended" |

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

- **An update over a release** (`nolf2-eu-1.3`, `contract-jack-eu-1.1`): the base release's
  install, then the update's files. NOLF2's 1.3 update
  (`patches/nolf2-update_1x3.exe`) is an InstallShield 6 setup inside a
  self-extractor, whose payload is one Microsoft cabinet holding the setup's
  `Disk1` folder; `tools/sfxcab.py` unpacks it (MSZIP), and `tools/unshield`
  takes the update's own file group, `PatchEN`, out of its `data1.hdr`. Its
  14 files go over the install: a new engine (`Lithtech.exe`, `server.dll`,
  `ServerDir.dll`, `SndDrv.dll`, `ltmsg.dll`), launcher and dedicated
  server, `Update_v1x3.rez` (the 1.3 game DLLs and data), `autoexec.cfg`,
  `Profiles\Default.prf`, readmes and Sierra updater configs. A file it
  replaces keeps the name it was installed under, as on Windows (its
  `SndDrv.dll` overwrites `snddrv.dll`). Setup adds the update to the
  registry: `UpdateNum` (a DWORD, 2) and `UpdateCommandLine1`
  (`-rez Update_v1x3.rez`), which the launcher appends to the command line.
  The update is read from its assembled archive in `artifacts/patches/`
  (`./assemble-artifacts.sh` runs if it is not there).

  Contract J.A.C.K.'s 1.1 update (`contract-jack-eu-1.1`,
  `patches/contractjack_update_en_10_11.exe`) is packed the same way. Its
  file group is `Program Files`, eight files: a new engine (`Lithtech.exe`,
  `server.dll`), launcher, dedicated server, `GameSpy.dll`,
  `Update_v1x1.rez` (the 1.1 game DLLs and data) and readmes. Its setup
  writes `UpdateNum` (1) and `UpdateCommandLine0` (`-rez Update_v1x1.rez`).

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

- **InstallShield 6 cabinets by setup type** (AvP2, Primal Hunt, Tron 2.0)
  keep what they install in `data1.hdr`. Setup types name components,
  components name file groups, and each file group has a destination
  (`<TARGETDIR>`, a folder under it, `<WINSYSDIR>`, the Start menu or
  setup's own support directory) and a language. A group's files are
  either compressed into the `dataN.cab` cabinets or uncompressed and
  linked to the disc: AvP2's `AVP2.exe` and world REZ files
  (`ALIEN.REZ`, `MARINE.REZ`, `PREDATOR.REZ`, `MULTI.REZ`) on disc 1's root,
  Primal Hunt's launcher and its `Tools`, `Updates` and `Trailers` folders,
  and Tron's `Tron.exe`, `TRON.chm` and `MFC42.DLL`. unshield does not show
  the setup types, the destinations or the uncompressed files, so
  `tools/ishdr.py` reads them. `install.py` installs each group of the
  setup type's components into its folder: compressed files with
  `tools/unshield`, uncompressed ones off the disc. Groups for another
  language are skipped (the Italian releases take the Italian ones), and
  so are the Start-menu and support-directory ones.
  - AvP2 and Primal Hunt are installed as "Typical", the setup type that
    copies everything, worlds included ("Compact" leaves them on the CD).
    Primal Hunt's "Typical" also copies the disc's `Tools` (the AvP2 tools
    installers), `Updates` (AvP2's patches, 0.92 to 0.96 and the SP/MP
    packs) and `Trailers` (a NOLF2 trailer) folders into the install.
  - Tron's setup types name only its registration component. Its script
    picks the rest, as "Recommended" (every resource on the hard drive;
    "Minimum" leaves some on the first CD). That is `TRON_COMPONENTS` in `install.py`: Program
    Files, Resources, Optional Resources, the uncompressed files and EREG,
    and the MFC 6 runtime (MFC42, MFC42U, MSVCP60, MSVCRT), which setup puts
    in `<WINSYSDIR>` and which goes beside the game, as for NOLF2. "Disc 2
    Files" (disc 2's DirectX and Windows Media audio codec installers) is
    not installed.

  The registry value is `InstallDir`, under `Monolith Productions\Aliens
  vs. Predator 2\1.0`, `Third Law Interactive\Aliens versus Predator 2:
  Primal Hunt\1.0` and `Monolith Productions\Tron 2.0\1.0`. Tron also gets
  `NetRegionCode` (`EN`), as NOLF2 does.

  Primal Hunt is an expansion, and its setup refuses AvP2's directory, so
  it is a release of its own. Its launcher (`PrimalHunt.exe`) reads AvP2's
  `InstallDir` and adds AvP2's REZ files (`AVP2.REZ`, `SOUNDS.REZ`, ...)
  from there to the engine's command line. Import both releases' `install.reg` to
  play it: an `avp2-*` and the matching `avp2-ph-*`.

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
- Between regions, AvP2 Europe differs from the USA release only in
  `EULA.txt` and `readme.txt`, and Primal Hunt Europe only in
  `license.txt`. The Italian releases are localised: their own launcher,
  server and REZ files (AvP2's `AVP2.REZ`, `SOUNDS.REZ`, `AVP2DLL.REZ` and
  `AVP2L.REZ`; Primal Hunt's `AVP2L.REZ` and `DIALOGUE.REZ`), and Italian
  patches in Primal Hunt's `Updates`. The engine is the same.
- The Primal Hunt USA disc comes in two dumps (`(USA)` and `(USA) (Alt)`).
  Both install byte-identical files, so `avp2-ph-usa` uses `(USA)`, and
  the Alt image is only fetched.
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
- AvP2's launcher `AVP2.exe` and Primal Hunt's `PrimalHunt.exe` are SecuROM
  (`.cms_t`/`.cms_d` sections). Their engines (`lithtech.exe`) are not.
- Tron 2.0's `Lithtech.exe` is SecuROM (setup's own messages say so). Its
  launcher `Tron.exe` is not.

Both NOLF1 trees were checked under Wine 9 (in `~/src/nolfsrc`'s build
container). `lithtech.exe` loads `Worlds\T01S01` and keeps running. The
2000 engine takes its arguments on the command line, because it has no
`-cmdfile`:

```sh
wine lithtech.exe -rez nolf.rez -rez nolf2.rez -rez nolfdll.rez -rez nolfl.rez -rez custom \
    ++windowed 1 +runworld 'Worlds\T01S01'
```

## sdk/

The LithTech Jupiter SDK (build 51, March 2002) is the engine's licensee
SDK: engine headers and libraries, tools, documentation, and the game code
and libraries of NOLF2 as it then stood. Its CD image, `LithEngine.iso` (an
InstallShield 6 setup), comes from
[archive.org/details/lithengine](https://archive.org/details/lithengine)
into `isos/sdk/`, checked against `isos/SHA256SUMS` like the discs; it is
already a plain `.iso`, so nothing is converted. Its SHA-1 matches the one
archive.org lists, `74d60e5e1a64718f11bd3787095bce19a15caabd`.

```sh
./fetch-isos.sh lithtech-jupiter-51 && ./install-games.sh lithtech-jupiter-51
```

`install.py`'s `sdk` installer unpacks the setup's "Source Code" file group
with `tools/unshield` into `sdk/lithtech-jupiter-51/` (`Engine/`, `Game/`,
`Libs/`: 3,303 files, 59 MB), as the cabinets lay it out, plus
`MANIFEST.txt`. The setup's other groups (the engine binaries, tools,
documentation) are not installed. It is checked against `sdk.sha256`, as a
game is against `games.sha256`, and `--verify` re-checks it. An SDK is not
a release: `./install-games.sh` with no names leaves it out, and it never
goes in `games/`.

The SDK was licensed to the engine's licensees, not released. archive.org
labels the item public domain, but nothing in the SDK says so: its
`Engine/sdk/Legal.txt` is the copyright notice of LithTech, Inc. Treat it
as you would the disc images.

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
| `install.py` | the installers above (and the SDK's); `--list` shows the releases and their discs |
| `ishdr.py` | an InstallShield 6/7 `data1.hdr`'s setup types, components and file groups, with each group's destination, language and files (compressed or on the disc) |
| `sfxcab.py` | the Microsoft cabinet inside an InstallShield self-extractor (MSZIP or stored) → its files (`--list`, or extract) |
| `pack-artifacts.sh` | an item of `demos/`, `patches/` or `mappacks/` → chunked `.tar.xz` (above) |
| `unshield/` | [unshield](https://github.com/twogood/unshield) 1.5.1 (MIT), vendored with a plain Makefile in place of CMake |
