# rez — the No One Lives Forever discs, installed

Fetches the redump images of every PC release of *The Operative: No One
Lives Forever*, *No One Lives Forever 2* and *Contract J.A.C.K.* from
[archive.org/details/nolf-pc-redump](https://archive.org/details/nolf-pc-redump),
and installs each release from them the way its own setup program would:
one directory per release, holding everything the game runs with.

```sh
./fetch-isos.sh        # ~10.6 GB of zips -> isos/, checked, converted to .iso
./install-games.sh     # -> games/<release>/ (~14 GB for all ten), each checked
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

`isos/SHA256SUMS` lists the 20 zips exactly as archive.org serves them.
`fetch-isos.sh` checks every zip against it before using it. Each zip holds a
redump `.bin`/`.cue` with raw 2352-byte sectors. `tools/bin2iso.py` reads the
data track straight out of the zip and writes a plain 2048-byte-sector `.iso`
beside it, under the same name.

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

`nolf-eu-fr`, `nolf-eu-de`, `nolf-eu-es` and `nolf-eu-sv` are the other
languages of the European NOLF discs. They are installed only when named.

Each directory also has a `MANIFEST.txt`, recording which image and path every
file came from. It also has an `install.reg` with the registry values setup
writes, pointing at the directory's own path through Wine's `Z:` drive.
Import it with `wine regedit install.reg`. It writes both the native and the
`Wow6432Node` view, so it works in 32- and 64-bit prefixes.

`games.sha256` holds the SHA-256 of every installed file of every release
except `install.reg`, which contains the directory's path. Each install is
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

Left out: the DirectX, GameSpy Arcade, Windows Media and audio-codec
installers that setup offers to run, and the Start-menu shortcuts.

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

## tools/

| Tool | |
|---|---|
| `bin2iso.py` | redump `.zip`/`.cue` → `.iso` (the first data track's user data) |
| `isoextract.py` | ISO 9660 / Joliet reader, from `~/src/nolfsrc/tools` |
| `install.py` | the installers above; `--list` shows the releases and their discs |
| `unshield/` | [unshield](https://github.com/twogood/unshield) 1.5.1 (MIT), vendored with a plain Makefile in place of CMake |
