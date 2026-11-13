#!/usr/bin/env python3
"""Install the games off the disc images in isos/, as their setup programs
would, into one directory per release; and the LithTech dev tools (DEVTOOLS,
below), off the discs and the archives in devtools/.

  install.py [--force] [--devtools] <outdir> [name...]
                                            install (default: every game
                                            release, or with --devtools every
                                            dev tool release)
  install.py --verify [--devtools] <outdir> [name...]
                                            check installed releases (default:
                                            every one present)
  install.py --list                         list the releases and their discs
  install.py --discs name...                the disc images those releases
                                            use (one per line; fetch-isos.sh)

Everything is installed under installed/: a game in <outdir> (install-games.sh
passes installed/games), an SDK in installed/sdk, a dev tool release in
installed/devtools. games/ and sdk/, where they used to be, are links into
installed/ (a directory still there is moved into it first, by an install;
--verify changes nothing, and fails a release with no hashes recorded). Each release is
written to <dir>/<name>/ (built in <dir>/.<name>.tmp and renamed when
complete, so a finished directory is always whole; an existing one is left
alone unless --force). Nothing is run from the discs:
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

  update  A release with an update applied: the base release's install,
          then the update's files over it, as its setup copies them. The
          NOLF2 and Contract J.A.C.K. updates are InstallShield 6 setups in
          a self-extractor (tools/sfxcab.py unpacks its cabinet); their
          files are one cabinet file group (PatchEN, ...), and setup adds
          the update's command line to the registry (install.reg). The
          update is read from the archive assemble-artifacts.sh rebuilds
          from patches/ (run here if it is not there yet).

  vise    The Mac releases (MacPlay): an Installer VISE archive in the disc's
          installer application (NOLF2's continued on disc 2 in "NOLF2
          Install Data"), whose single "Easy Install" package installs the
          whole archive. It is read off the HFS / HFS+ disc with
          tools/hfsextract.py and unpacked with tools/viseextract.py: the
          archive's top folder is the install directory. Resource forks and
          Finder info go in AppleDouble ._ files; symbolic links are made.

  setup   Aliens versus Predator 2, Primal Hunt and Tron 2.0. InstallShield
          cabinets whose setup type ("Typical"; Tron's script picks its
          own components, "Recommended") names the components installed;
          tools/ishdr.py reads them, and their file groups, out of
          data1.hdr. A group's compressed files are unpacked with
          tools/unshield; its uncompressed ones are copied off the disc.
          Groups for another language, the Start menu or setup's own
          support directory are left out; <WINSYSDIR> ones go beside the
          game, as for cab.

  sdk     The LithTech Jupiter SDK: one InstallShield 6 file group of the
          SDK's CD image ("Source Code"), unpacked with tools/unshield as
          the cabinets lay it out. It goes in sdk/<name>/, not <outdir>,
          and is checked against sdk.sha256; it has no install.reg.

The dev tool releases are installed the same way, by what their own
installers say they copy, and get MANIFEST.txt only:

  toolsetup  An InstallShield 6/7 setup (on a disc, in a self-extractor
             tools/sfxcab.py unpacks, or in a zip): its setup type's
             components, as for setup; one may go over another's install,
             as an update does (base).
  toolzip    A zip (or a folder of one) that is the release itself.
  sfactory   A Setup Factory 6 installer (tools/sfextract.py): its payload
             files at their destinations; %WinDir% ones go beside them.
  sevenzip   A 7z archive (tools/sevenzip.py), with the zips in it unpacked
             into folders of their names.

A Mac install gets MANIFEST.txt only. nolf-ps2-usa and nolf-ps2-eu (the
PlayStation 2 discs), avp2-demo-usa (AvP2's demo disc) and kiss-bonus-usa
(KISS's F.A.K.K. 2 bonus disc) are listed only so that fetch-isos.sh can
fetch them by name; they are not installed.

games.sha256 records a symbolic link by the SHA-256 of its target.
"""
import fnmatch
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path, PureWindowsPath

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hfsextract import Volume  # noqa: E402
from ishdr import Header  # noqa: E402
from isoextract import Iso  # noqa: E402
from sevenzip import entries as sevenzip_entries  # noqa: E402
from sfextract import read_setup as sfactory_files  # noqa: E402
from sfxcab import read_cabinet  # noqa: E402
from viseextract import Archive  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ISOS = ROOT / "isos"
UNSHIELD = ROOT / "tools" / "unshield" / "unshield"
ARTIFACTS = ROOT / "artifacts"
SUMS = ROOT / "games.sha256"
INSTALLED = ROOT / "installed"
# The SDKs (SDKS, below) and dev tools (DEVTOOLS) are installed beside the
# games, not among them.
SDK_DIR = INSTALLED / "sdk"
SDK_SUMS = ROOT / "sdk.sha256"
DEVTOOLS_DIR = INSTALLED / "devtools"
DEVTOOLS_SUMS = ROOT / "devtools.sha256"

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
JUPITER_SDK = "sdk/LithEngine"
AVP2_USA = ["Aliens Versus Predator 2 (USA) (Disc 1)", "Aliens Versus Predator 2 (USA, Asia) (Disc 2)"]
AVP2_EU = ["Aliens Versus Predator 2 (Europe) (Disc 1)", "Aliens Versus Predator 2 (Europe) (Disc 2)"]
AVP2_IT = ["Aliens Versus Predator 2 (Italy) (Disc 1)", "Aliens Versus Predator 2 (Italy) (Disc 2)"]
AVP2_DEMO = "Aliens Versus Predator 2 (USA) (Demo)"
AVP2PH_USA = "Aliens Versus Predator 2 - Primal Hunt (USA)"
AVP2PH_EU = "Aliens Versus Predator 2 - Primal Hunt (Europe)"
AVP2PH_IT = "Aliens Versus Predator 2 - Primal Hunt (Italy)"
TRON_USA = ["Tron 2.0 (USA) (Disc 1)", "Tron 2.0 (USA) (Disc 2)"]
KISS_EU = "KISS Psycho Circus - The Nightmare Child (Europe)"
KISS_DE = "KISS Psycho Circus - The Nightmare Child (Germany)"
KISS_IT = "KISS Psycho Circus - The Nightmare Child (Italy) (Covermount)"
KISS_USA = "KISS Psycho Circus - The Nightmare Child (USA)"
KISS_BONUS = "KISS Psycho Circus - The Nightmare Child & Heavy Metal - F.A.K.K. 2 - Bonus Disc! (USA)"
BLOOD2_EU = "Blood II - The Chosen (Europe)"
BLOOD2_HU = "Blood II - The Chosen (Hungary)"
BLOOD2_USA = "Blood II - The Chosen (USA)"
BLOOD2_USA_1 = "Blood II - The Chosen (USA) (Rev 1)"
BLOOD2_NL_EU = "Blood II - The Chosen - The Nightmare Levels (Europe)"
BLOOD2_NL_USA = "Blood II - The Chosen - The Nightmare Levels (USA)"
MAC_NOLF1 = "mac/Operative, The - No One Lives Forever (USA) (Disc 1) (Game Disc)"
MAC_NOLF2 = ["mac/No One Lives Forever 2 - A Spy in H.A.R.M.'s Way (USA) (Disc 1)",
             "mac/No One Lives Forever 2 - A Spy in H.A.R.M.'s Way (USA) (Disc 2)"]

NOLF1_KEY = r"Software\Monolith Productions\No One Lives Forever\1.0"
NOLF2_KEY = r"SOFTWARE\Monolith Productions\No One Lives Forever 2\1.0"
CJ_KEY = r"SOFTWARE\Monolith Productions\Contract Jack\1.0"
AVP2_KEY = r"SOFTWARE\Monolith Productions\Aliens vs. Predator 2\1.0"
AVP2PH_KEY = r"SOFTWARE\Third Law Interactive\Aliens versus Predator 2: Primal Hunt\1.0"
TRON_KEY = r"SOFTWARE\Monolith Productions\Tron 2.0\1.0"
# KISS's launcher reads its registry set under HKEY_CURRENT_USER.
KISS_KEY = r"Software\Third Law Interactive\Psycho Circus Launcher\1.0"
KISS_VALUES = {"RezInstalled": "1", "MusicInstalled": "1", "MoviesInstalled": "1"}
BLOOD2_KEY = r"Software\Monolith Productions\Blood2\1.0"

# Tron 2.0's "Recommended" install: its script, not its setup types (which
# name only EREG), picks the components. All of the game's are installed;
# DirectX and "Disc 2 Files" (the DirectX and Windows Media audio codec
# installers setup runs) are not.
TRON_COMPONENTS = [r"<Data>\Program Files", r"<Data>\Resources", r"<Data>\Optional Resources",
                   r"<Data>\Uncompressed Files", r"<Data>\EREG",
                   r"<Data>\System Files\MFC 6.2 Runtime\MFC Runtime",
                   r"<Data>\System Files\MFC 6.2 Runtime\MFC Ansi",
                   r"<Data>\System Files\MFC 6.2 Runtime\MFC Unicode"]

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
    # NOLF2 (Europe, English) at its last update, 1.3 (the English one):
    # what Monolith's source release is.
    "nolf2-eu-1.3":     ("update", NOLF2_EU, {"base": "nolf2-eu",
                                               "patch": "patches/nolf2-update_1x3.exe",
                                               "group": "PatchEN",
                                               "values": {"UpdateNum": 2,
                                                          "UpdateCommandLine1": "-rez Update_v1x3.rez"}}),
    "contract-jack-us": ("cab", CJ_USA, {"key": CJ_KEY, "region": "EN"}),
    "contract-jack-eu": ("cab", CJ_EU, {"key": CJ_KEY, "region": "EN"}),
    # Contract J.A.C.K. (Europe) at its one update, 1.1 (the English one).
    "contract-jack-eu-1.1": ("update", CJ_EU, {"base": "contract-jack-eu",
                                               "patch": "patches/contractjack_update_en_10_11.exe",
                                               "group": "Program Files",
                                               "values": {"UpdateNum": 1,
                                                          "UpdateCommandLine0": "-rez Update_v1x1.rez"}}),
    "nolf-mac-usa":     ("vise", [MAC_NOLF1], {"segments": ["NOLF Installer"]}),
    "nolf2-mac-usa":    ("vise", MAC_NOLF2, {"segments": ["Install No One Lives Forever 2",
                                                         "NOLF2 Install Data"]}),
    # Aliens versus Predator 2 ("Typical") and its expansion Primal Hunt,
    # which setup puts in a directory of its own; its launcher finds AvP2's
    # through AvP2's registry key.
    "avp2-usa":         ("setup", AVP2_USA, {"type": "Typical", "lang": "0009", "key": AVP2_KEY}),
    "avp2-eu":          ("setup", AVP2_EU, {"type": "Typical", "lang": "0009", "key": AVP2_KEY}),
    "avp2-it":          ("setup", AVP2_IT, {"type": "Typical", "lang": "0010", "key": AVP2_KEY}),
    # AvP2 (Europe, English) at its last patch, 1.0.9.6, which includes the
    # earlier ones.
    "avp2-eu-1.0.9.6":  ("update", AVP2_EU, {"base": "avp2-eu", "patch": "patches/avp2_en_096.exe",
                                             "group": "Update Files",
                                             "values": {"Update Command Line": "-rez AVP2P1.REZ"}}),
    "avp2-ph-usa":      ("setup", [AVP2PH_USA], {"type": "Typical", "lang": "0009", "key": AVP2PH_KEY}),
    "avp2-ph-eu":       ("setup", [AVP2PH_EU], {"type": "Typical", "lang": "0009", "key": AVP2PH_KEY}),
    "avp2-ph-it":       ("setup", [AVP2PH_IT], {"type": "Typical", "lang": "0010", "key": AVP2PH_KEY}),
    "tron2-usa":        ("setup", TRON_USA, {"components": TRON_COMPONENTS, "lang": "0009", "key": TRON_KEY,
                                             "values": {"NetRegionCode": "EN"}}),
    # Tron 2.0 at its Update 2, v1.030 (the "complete" one, for a 1.010
    # install): its common files and the English ones.
    "tron2-usa-1.030":  ("update", TRON_USA, {"base": "tron2-usa",
                                              "patch": "patches/tron-update_v1x2_complete.exe",
                                              "group": ["Common Complete", "Patch Files EN Complete"],
                                              "values": {"UpdateNum": 2,
                                                         "UpdateCommandLine0": "-rez gamep3.rez",
                                                         "UpdateCommandLine1": "-rez gamep4.rez"}}),
    # KISS Psycho Circus (Third Law): the "Complete" install, everything
    # linked to the disc's Psycho and StrategyGuide folders.
    "kiss-eu":          ("setup", [KISS_EU], {"type": "Complete", "lang": "0009", "key": KISS_KEY,
                                              "values": KISS_VALUES, "path_value": "InstallPath",
                                              "root": "HKEY_CURRENT_USER"}),
    "kiss-de":          ("setup", [KISS_DE], {"type": "Complete", "lang": "0009", "key": KISS_KEY,
                                              "values": KISS_VALUES, "path_value": "InstallPath",
                                              "root": "HKEY_CURRENT_USER"}),
    "kiss-it":          ("setup", [KISS_IT], {"type": "Complete", "lang": "0009", "key": KISS_KEY,
                                              "values": KISS_VALUES, "path_value": "InstallPath",
                                              "root": "HKEY_CURRENT_USER"}),
    "kiss-usa":         ("setup", [KISS_USA], {"type": "Complete", "lang": "0009", "key": KISS_KEY,
                                               "values": KISS_VALUES, "path_value": "InstallPath",
                                               "root": "HKEY_CURRENT_USER"}),
    # Blood II ("Normal Install": the GAME and DATA folders), and The
    # Nightmare Levels, which its setup puts into Blood II's directory.
    "blood2-eu":        ("folders", [BLOOD2_EU], {"folders": [(0, "GAME"), (0, "DATA")], "key": BLOOD2_KEY}),
    "blood2-hu":        ("folders", [BLOOD2_HU], {"folders": [(0, "GAME"), (0, "DATA")], "key": BLOOD2_KEY}),
    "blood2-usa":       ("folders", [BLOOD2_USA], {"folders": [(0, "GAME"), (0, "DATA")], "key": BLOOD2_KEY}),
    # Rev 1 has a new BLOOD2.REZ, SOUND.REZ and help file.
    "blood2-usa-rev1":  ("folders", [BLOOD2_USA_1], {"folders": [(0, "GAME"), (0, "DATA")], "key": BLOOD2_KEY}),
    "blood2-eu-nightmares":  ("folders", [BLOOD2_EU, BLOOD2_NL_EU],
                              {"base": "blood2-eu", "folders": [(1, "GAME"), (1, "DATA")],
                               "key": BLOOD2_KEY, "values": {"Nightmares": 1}}),
    "blood2-usa-nightmares": ("folders", [BLOOD2_USA_1, BLOOD2_NL_USA],
                              {"base": "blood2-usa-rev1", "folders": [(1, "GAME"), (1, "DATA")],
                               "key": BLOOD2_KEY, "values": {"Nightmares": 1}}),
}
EXTRA = {
    f"nolf-eu-{code}": ("is5", [NOLF1_EU_1, NOLF1_EU_2], {"lang": lang})
    for code, lang in (("fr", "French"), ("de", "German"), ("es", "Spanish"), ("sv", "Swedish"))
}
# Images kept as they are: NOLF's PlayStation 2 port, one DVD each, and
# AvP2's demo disc (two demo installers). There is nothing to install: these
# only name the images for fetch-isos.sh.
IMAGES_ONLY = {
    "nolf-ps2-usa": ("ps2", [PS2_USA], {}),
    "nolf-ps2-eu":  ("ps2", [PS2_EU], {}),
    "avp2-demo-usa": ("demo", [AVP2_DEMO], {}),
    "kiss-bonus-usa": ("bonus", [KISS_BONUS], {}),
}
# The LithTech Jupiter SDK (build 51, March 2002), the engine licensees' SDK:
# its "Source Code" file group (NOLF2's game code and libraries as they then
# stood, with WONAPI and ServerDir, which the source release lacks). Installed
# into sdk/<name>/, not games/, and checked against sdk.sha256.
SDKS = {
    "lithtech-jupiter-51": ("sdk", [JUPITER_SDK], {"group": "Source Code"}),
}
# The LithTech dev tools, as their installers install them. Those released
# on a game disc are read off it (the European pressing where there is one);
# the others are the archives in devtools/ (assemble-artifacts.sh).
NOLF2_TOOLKIT = {"artifact": "devtools/si_nolf2_tools_en_10.exe", "member": "si_nolf2_tools_en_10.exe"}
TRON_TOOLS = {"artifact": "devtools/tron2-tools-1.2a", "member": "tron2-tools-1.2a/tron_tools.zip"}
TRON_TOOLS_12A = {"artifact": "devtools/tron2-tools-1.2a",
                  "member": "tron2-tools-1.2a/tron20_tools_v1x2a_setup.zip",
                  "inner": "tron20_tools_v1x2a_setup.exe"}
JUPITER_B69 = {"artifact": "devtools/Jupiter System Enterprise Edition.zip",
               "member": "Jupiter System Enterprise Edition.zip"}
FTP_DUMP = {"artifact": "devtools/LithTech FTP Dump.7z", "member": "LithTech FTP Dump.7z"}
TRON_DEVBUILD = {"artifact": "devtools/Tron devbuild.zip", "member": "Tron devbuild.zip"}
DEVTOOLS = {
    # NOLF Tools 001 (Jan 2001): setup copies the zip's Tools folder into
    # NOLF's TOOLS; here it is the release.
    "nolf-tools-001":     ("toolzip", [GOTY_2], {"source": {"file": "Game/NOLFTools001.exe"},
                                                 "folder": "Tools"}),
    # AvP2 Editing Tools v1.0 (Dec 2001), then Update 1 and Update 2 over it.
    "avp2-tools":         ("toolsetup", [AVP2PH_EU], {"source": {"file": "Tools/avp2tools.exe"},
                                                      "sfx": True, "type": "Typical"}),
    "avp2-tools-update1": ("toolsetup", [AVP2PH_EU], {"source": {"file": "Tools/avp2tools_update.exe"},
                                                      "sfx": True, "type": "Typical",
                                                      "base": "avp2-tools"}),
    "avp2-tools-update2": ("toolsetup", [AVP2PH_EU], {"source": {"file": "Tools/avp2tools_update2.exe"},
                                                      "sfx": True, "type": "Typical",
                                                      "base": "avp2-tools-update1"}),
    # The LithTech Jupiter SDK, build 51 (Mar 2002): the whole "Typical"
    # install (sdk/lithtech-jupiter-51 is only its source).
    "jupiter-b51":        ("toolsetup", [JUPITER_SDK], {"type": "Typical"}),
    "nolf2-toolkit":      ("toolsetup", [], {"source": NOLF2_TOOLKIT, "sfx": True, "type": "Patch"}),
    "tron2-tools":        ("toolzip", [], {"source": TRON_TOOLS}),
    "tron2-tools-1.2a":   ("sfactory", [], {"source": TRON_TOOLS_12A}),
    # Contract J.A.C.K. Public Tools (Oct 2003), on CJ's disc 1.
    "cjack-tools":        ("toolsetup", [CJ_EU[0]], {"source": {"file": "PublicToolsSetup.exe"},
                                                     "sfx": True, "type": "Typical"}),
    # Jupiter System Enterprise Edition, build 69 (2006): the tools' source.
    "jupiter-b69":        ("toolsetup", [], {"source": JUPITER_B69, "folder": "nolf2_gpl_src",
                                             "type": "Typical"}),
    "lithtech-ftp-dump":  ("sevenzip", [], {"source": FTP_DUMP}),
    # A Tron 2.0 developer build (2003-08-05; archive.org "tron-devbuild"):
    # the game as Monolith ran it in-house, unprotected, with its console;
    # its zip's TRON DEVBUILD folder is the release.
    "tron2-devbuild":     ("toolzip", [], {"source": TRON_DEVBUILD, "folder": "TRON DEVBUILD"}),
}
ALL = {**RELEASES, **EXTRA, **IMAGES_ONLY, **SDKS, **DEVTOOLS}


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

    def origin(self, path):
        """What MANIFEST.txt says a file of this disc came from."""
        return f"{self.name}.iso:{path}"


class Folder(Disc):
    """An unpacked installer's files, read like a disc's; `name` is where
    the installer came from."""

    def __init__(self, root, name):
        self.name, self.root = name, Path(root)
        self.files = {}
        for f in sorted(self.root.rglob("*")):
            if f.is_file():
                rel = f.relative_to(self.root).as_posix()
                self.files[rel.lower()] = (rel, f, f.stat().st_size)

    def copy(self, path, dest):
        p, src, _sz = self.files[path.lower()]
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        return p

    def origin(self, path):
        return f"{self.name}:{path}"


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
        # With fold_case, a path differing only in case from one already
        # installed is that one, as on Windows (an update over a release).
        self.fold_case = False
        self.names = {}

    def place(self, rel):
        """The path `rel` is installed as (see fold_case)."""
        out = []
        for part in rel.split("/"):
            path = "/".join(out + [part])
            known = self.names.setdefault(path.lower(), path)
            out = (known if self.fold_case else path).split("/")
        return "/".join(out)

    def put(self, disc, src, rel):
        """Copy disc file `src` to `rel` inside the install."""
        rel = self.place(rel)
        p = disc.copy(src, self.target / rel)
        self.manifest[rel] = disc.origin(p)

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

    def write_extras(self, values, key, root="HKEY_LOCAL_MACHINE"):
        """MANIFEST.txt, and install.reg with `values` under HKLM\\`key` --
        both the native and the 32-bit (Wow6432Node) view, so it works in a
        32- or 64-bit Wine prefix alike -- or under HKCU\\`key` (`root`),
        which has one view. A value that is an int is a DWORD; None is the
        directory's own path."""
        self.values, self.key, self.root = dict(values), key, root
        self.write_manifest()
        # Wine maps / to Z:, so this is the directory's own path.
        winpath = "Z:" + str(PureWindowsPath(self.target.parent.resolve() / self.name))
        lines = ["Windows Registry Editor Version 5.00", ""]
        views = [key]
        if root == "HKEY_LOCAL_MACHINE":
            views.append(key.replace("\\", "\\Wow6432Node\\", 1))
        for view in views:
            lines.append(f"[{root}\\{view}]")
            for k, v in values.items():
                if isinstance(v, int):
                    lines.append('"%s"=dword:%08x' % (k, v))
                    continue
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


def stage_cabinets(inst, discs):
    """Copy the discs' InstallShield cabinet set (data1.hdr and every
    dataN.cab, which may span discs) into a work directory beside the
    install; returns (work directory, data1.hdr, the cabinets' file groups)."""
    if not UNSHIELD.exists():
        sys.exit(f"install: {UNSHIELD} is not built -- run `make -C tools/unshield`")
    work = inst.target.parent / f".{inst.name}.cab"
    shutil.rmtree(work, ignore_errors=True)
    cab = work / "cab"
    cab.mkdir(parents=True)
    for disc in discs:
        for rel in disc.listdir("", "data*.*"):
            if rel.lower().endswith((".cab", ".hdr")):
                disc.copy(rel, cab / rel.lower())
    hdr = str(cab / "data1.hdr")
    groups = subprocess.run([str(UNSHIELD), "g", hdr], check=True, capture_output=True,
                            text=True).stdout.splitlines()
    return work, hdr, groups


def extract_group(inst, work, hdr, group, origin, dest=""):
    """Unpack cabinet file group `group` into the install (its folder
    `dest`); `origin` is what MANIFEST.txt says each file came from.
    Returns the number of files."""
    out = work / "x"
    shutil.rmtree(out, ignore_errors=True)
    subprocess.run([str(UNSHIELD), "-d", str(out), "-g", group, "x", hdr], check=True,
                   stdout=subprocess.DEVNULL)
    n = 0
    for top in out.iterdir():              # unshield writes <dir>/<group>/...
        for f in sorted(top.rglob("*")):
            if f.is_file():
                rel = inst.place(str(Path(dest) / f.relative_to(top)))
                to = inst.target / rel
                to.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(f), to)
                inst.manifest[rel] = origin
                n += 1
    return n


def install_cab(inst, discs, key, region, nolf2=False, **_):
    work, hdr, groups = stage_cabinets(inst, discs)
    wanted = [g for g in groups if g in CAB_GROUPS or "<WINSYSDIR>" in g]
    n = 0
    for g in wanted:
        where = "<WINSYSDIR>" if "<WINSYSDIR>" in g else "<TARGETDIR>"
        n += extract_group(inst, work, hdr, g, f"{discs[0].name}/data1.hdr:[{g}] ({where})")
    shutil.rmtree(work)
    if nolf2:
        # The uncompressed groups: the (SecuROM) launcher on the disc's root,
        # and, for the "Recommended" install, the Data folder's GAME.REZ.
        d1 = discs[0]
        inst.put(d1, "NOLF2.exe", "NOLF2.exe")
        n += 1 + inst.copy_folder(d1, "Data", pattern="*.rez")
    inst.write_extras({"InstallDir": None, "NetRegionCode": region}, key)
    return n


def install_setup(inst, discs, lang, key, type=None, components=None, values=None,
                  path_value="InstallDir", root="HKEY_LOCAL_MACHINE"):
    """The components of setup type `type` (or the list `components`), each
    file group into the folder data1.hdr gives it: compressed files out of
    the cabinets, uncompressed ones off the discs. A file installed twice
    (two groups can carry it) is copied over, as setup would. install.reg
    has the directory's path as `path_value` and `values` under `root`\\`key`;
    with no `key`, there is no install.reg."""
    work, hdr, _groups = stage_cabinets(inst, discs)
    h = Header(hdr)
    origin = f"{discs[0].name}/data1.hdr"
    for comp in (h.setup_types[type] if type else components):
        for name in h.components[comp]:
            g = h.groups[name]
            if g["language"] not in ("", "0", lang):
                continue
            where, _, sub = g["target"].partition("\\")
            if where not in ("<TARGETDIR>", "<WINSYSDIR>"):
                continue                # Start menu, setup's support files
            if where == "<WINSYSDIR>":
                sub = ""                # beside the game (see install_cab)
            sub = sub.replace("\\", "/")
            if any(f["compressed"] for f in g["files"]):
                extract_group(inst, work, hdr, name, f"{origin}:[{name}] ({where})", sub)
            for f in g["files"]:
                if f["compressed"]:
                    continue
                src = "/".join(p for p in (g["source"], f["path"].replace("\\", "/")) if p)
                disc = next((d for d in discs if d.has(src)), None)
                if disc is None:
                    sys.exit(f"install: {name}: {src} is on none of {inst.name}'s discs")
                inst.put(disc, src, str(Path(sub) / f["path"].replace("\\", "/")))
    shutil.rmtree(work)
    if key:
        inst.write_extras({path_value: None, **(values or {})}, key, root)
    else:
        inst.write_manifest()
    return len(inst.manifest)


def install_folders(inst, discs, folders, key, values=None, base=None):
    """InstallShield 5 scripts that copy whole folders of the disc into the
    install directory (Blood II, The Nightmare Levels): each (disc index,
    folder) of `folders`, subfolders and all, into its root. install.reg has
    WorkingDirectory and `values` under `key`; with `base`, the folders go
    over that release's install and the values join its."""
    if base:
        install_into(inst, base)
        inst.fold_case = True
        values = {**inst.values, **(values or {})}
    else:
        values = {"WorkingDirectory": None, **(values or {})}
    for i, folder in folders:
        inst.copy_folder(discs[i], folder, recursive=True)
    inst.write_extras(values, key)
    return len(inst.manifest)


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


def install_update(inst, discs, base, patch, group, values):
    """The base release, then the update's file group `group` (or groups,
    in order) over it."""
    kind, _discs, opts = RELEASES[base]
    n = INSTALLERS[kind](inst, discs, **opts)
    archive = ARTIFACTS / f"{patch}.tar.xz"
    if not archive.exists():
        subprocess.run([str(ROOT / "assemble-artifacts.sh"), patch], check=True)
    work = inst.target.parent / f".{inst.name}.update"
    shutil.rmtree(work, ignore_errors=True)
    setup = work / "setup"
    with tarfile.open(archive, "r:xz") as tar:
        members = [m for m in tar.getmembers() if m.isfile()]
        if len(members) != 1:
            sys.exit(f"install: {archive.name}: expected one file, found {len(members)}")
        exe = tar.extractfile(members[0]).read()
    for name, blob in read_cabinet(exe):
        dest = setup / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(blob)
    hdr = next(setup.rglob("data1.hdr"))
    m = 0
    for g in [group] if isinstance(group, str) else group:
        out = work / "x"
        shutil.rmtree(out, ignore_errors=True)
        subprocess.run([str(UNSHIELD), "-d", str(out), "-g", g, "x", str(hdr)], check=True,
                       stdout=subprocess.DEVNULL)
        # Names match as on Windows: a file the update replaces keeps the
        # name it was installed under (the update's SndDrv.dll is snddrv.dll).
        present = {str(p.relative_to(inst.target)).lower(): str(p.relative_to(inst.target))
                   for p in inst.target.rglob("*") if p.is_file()}
        for top in out.iterdir():           # unshield writes <dir>/<group>/...
            for f in sorted(top.rglob("*")):
                if f.is_file():
                    rel = str(f.relative_to(top))
                    rel = present.get(rel.lower(), rel)
                    dest = inst.target / rel
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if dest.exists():
                        dest.unlink()
                    else:
                        n += 1
                    shutil.move(str(f), dest)
                    inst.manifest[rel] = f"{patch}:[{g}]"
                    m += 1
    shutil.rmtree(work)
    inst.write_extras({**inst.values, **values}, inst.key, inst.root)
    print(f"   {patch}: {m} files over {base}")
    return n


def install_sdk(inst, discs, group):
    """One file group of an SDK's InstallShield 6 cabinets, as it is laid
    out in the cabinets (no setup script is followed: an SDK is installed
    to be read, not run); MANIFEST.txt, and no install.reg."""
    work, hdr, groups = stage_cabinets(inst, discs)
    if group not in groups:
        sys.exit(f"install: {discs[0].name}: no file group {group!r}")
    n = extract_group(inst, work, hdr, group, f"{discs[0].name}.iso:data1.hdr:[{group}]")
    shutil.rmtree(work)
    inst.write_manifest()
    return n


def tool_source(inst, discs, file=None, artifact=None, member=None, inner=None):
    """A dev tool release's installer, as a file in a work directory beside
    the install, and what MANIFEST.txt says it came from: `file` on the
    release's disc, or `member` of the devtools/ archive `artifact`
    (assembled first if need be); `inner` is a file in that zip."""
    work = inst.target.parent / f".{inst.name}.src"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir()
    if file:
        dest = work / Path(file).name
        origin = discs[0].origin(discs[0].copy(file, dest))
    else:
        archive = ARTIFACTS / f"{artifact}.tar.xz"
        if not archive.exists():
            subprocess.run([str(ROOT / "assemble-artifacts.sh"), artifact], check=True)
        dest = work / Path(member).name
        with tarfile.open(archive, "r:xz") as tar, tar.extractfile(member) as src, open(dest, "wb") as out:
            shutil.copyfileobj(src, out, 1 << 20)
        origin = f"{artifact}:{member}"
    if inner:
        with zipfile.ZipFile(dest) as z, z.open(inner) as src, open(work / inner, "wb") as out:
            shutil.copyfileobj(src, out, 1 << 20)
        dest, origin = work / inner, f"{origin}[{inner}]"
    return work, dest, origin


def install_toolsetup(inst, discs, type, source=None, sfx=False, folder=None, base=None):
    """An InstallShield setup's `type`: on the disc itself, or in the
    self-extractor or zip (its `folder`) that is `source`; with `base`, over
    that release's install."""
    if base:
        install_into(inst, base)
        inst.fold_case = True
    if not source:
        return install_setup(inst, discs, "0009", None, type=type)
    work, path, origin = tool_source(inst, discs, **source)
    media = work / "setup"
    if sfx:
        for name, blob in read_cabinet(path.read_bytes()):
            dest = media / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
        media = next(media.rglob("data1.hdr")).parent
    else:
        with zipfile.ZipFile(path) as z:
            z.extractall(media)
        path.unlink()
        media = media / folder
    n = install_setup(inst, [Folder(media, origin)], "0009", None, type=type)
    shutil.rmtree(work)
    return n


def install_toolzip(inst, discs, source, folder=None):
    """The zip `source`, or its `folder`, as it is."""
    work, path, origin = tool_source(inst, discs, **source)
    pre = folder + "/" if folder else ""
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            if info.is_dir() or not info.filename.startswith(pre):
                continue
            rel = inst.place(info.filename[len(pre):])
            dest = inst.target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out, 1 << 20)
            inst.manifest[rel] = f"{origin}[{info.filename}]"
    shutil.rmtree(work)
    inst.write_manifest()
    return len(inst.manifest)


def install_sfactory(inst, discs, source):
    """A Setup Factory 6 installer's payload files at their destinations
    (%AppDir% is the install; %WinDir% and the like go beside it). The
    header files are setup's own, and what it runs as it installs."""
    work, path, origin = tool_source(inst, discs, **source)
    for kind, name, data in sfactory_files(str(path)):
        if kind != "payload":
            continue
        folder, dest = name
        rel = inst.place(dest)
        (inst.target / rel).parent.mkdir(parents=True, exist_ok=True)
        (inst.target / rel).write_bytes(data)
        inst.manifest[rel] = f"{origin}[{folder}\\{dest.replace('/', chr(92))}]"
    shutil.rmtree(work)
    inst.write_manifest()
    return len(inst.manifest)


def install_sevenzip(inst, discs, source):
    """A 7z archive's files, each zip in it unpacked into a folder of its
    name (without .zip)."""
    work, path, origin = tool_source(inst, discs, **source)
    for name, is_dir, data in sevenzip_entries(str(path)):
        name = name.replace("\\", "/")
        if is_dir:
            continue
        if not name.lower().endswith(".zip"):
            rel = inst.place(name)
            (inst.target / rel).parent.mkdir(parents=True, exist_ok=True)
            (inst.target / rel).write_bytes(data)
            inst.manifest[rel] = f"{origin}[{name}]"
            continue
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                rel = inst.place(f"{name[:-4]}/{info.filename.replace(chr(92), '/')}")
                (inst.target / rel).parent.mkdir(parents=True, exist_ok=True)
                (inst.target / rel).write_bytes(z.read(info))
                inst.manifest[rel] = f"{origin}[{name}][{info.filename}]"
    shutil.rmtree(work)
    inst.write_manifest()
    return len(inst.manifest)


def install_into(inst, name):
    """Install release `name` into `inst`; the number of files."""
    kind, disc_names, opts = ALL[name]
    disc_class = MacDisc if kind == "vise" else Disc
    return INSTALLERS[kind](inst, [disc_class(d) for d in disc_names], **opts)


INSTALLERS = {"is5": install_is5, "goty": install_goty, "cab": install_cab, "vise": install_vise,
              "update": install_update, "sdk": install_sdk, "setup": install_setup,
              "folders": install_folders,
              "toolsetup": install_toolsetup, "toolzip": install_toolzip,
              "sfactory": install_sfactory, "sevenzip": install_sevenzip}


def sums(name):
    """The hash list a release is checked against: games.sha256, or
    sdk.sha256 for an SDK, devtools.sha256 for a dev tool release."""
    return SDK_SUMS if name in SDKS else DEVTOOLS_SUMS if name in DEVTOOLS else SUMS


def home(outdir, name):
    """The directory a release is installed in: <outdir>, or installed/sdk
    for an SDK, installed/devtools for a dev tool release."""
    return SDK_DIR if name in SDKS else DEVTOOLS_DIR if name in DEVTOOLS else outdir


def layout():
    """installed/ and the links games -> installed/games and sdk ->
    installed/sdk; a games/ or sdk/ directory from before is moved there.
    The links keep the old paths working, install.reg's among them."""
    for name in ("games", "sdk"):
        old, new = ROOT / name, INSTALLED / name
        if old.is_dir() and not old.is_symlink() and not new.exists():
            new.parent.mkdir(parents=True, exist_ok=True)
            old.rename(new)
            print(f"== moved {name}/ to installed/{name}/")
        new.mkdir(parents=True, exist_ok=True)
        if not old.is_symlink() and not old.exists():
            old.symlink_to(Path("installed") / name)


def recorded(name):
    """{path inside the release: sha256} from its hash list (sums())."""
    out = {}
    if not sums(name).exists():
        return out
    with open(sums(name)) as f:
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
    """Check directory `d` (an install of `name`) against its hash list: the
    same files, byte for byte. Prints what differs; True if nothing does,
    None if nothing is recorded for `name` (a release added since)."""
    want = recorded(name)
    if not want:
        print(f"   {name}: no hashes recorded in {sums(name).name} -- NOT verified")
        return None
    have = installed(d)
    problems = [f"missing  {p}" for p in sorted(want.keys() - have)]
    problems += [f"extra    {p}" for p in sorted(have - want.keys())]
    problems += [f"changed  {p}" for p in sorted(want.keys() & have) if sha256(d / p) != want[p]]
    for line in problems:
        print(f"   {name}: {line}")
    if not problems:
        print(f"   {name}: all {len(want)} files match {sums(name).name}")
    return not problems


def main():
    args = sys.argv[1:]
    if args == ["--list"]:
        for name, (kind, discs, opts) in ALL.items():
            src = opts.get("source", {})
            what = " + ".join(discs) + (f": {src['file']}" if "file" in src else "")
            what = what or src["artifact"] + (f": {src['member']}" if "/" in src["member"] else "")
            print(f"{name:<20} {kind:<9} {what}")
        return
    if args[:1] == ["--discs"]:
        out = []
        for name in args[1:]:
            if name not in ALL:
                sys.exit(f"install: unknown release {name} (see --list)")
            out += [d for d in ALL[name][1] if d not in out]
        print("\n".join(out))
        return
    tools = "--devtools" in args
    args = [a for a in args if a != "--devtools"]
    if args[:1] == ["--verify"]:
        # A check changes nothing: no layout() here. An SDK still in the
        # old sdk/ directory (not yet moved into installed/) is checked
        # where it is.
        global SDK_DIR
        if not SDK_DIR.is_dir() and (ROOT / "sdk").is_dir():
            SDK_DIR = ROOT / "sdk"
        if len(args) < 2:
            sys.exit(__doc__)
        outdir = Path(args[1])
        if not outdir.is_dir() and outdir.name == "games" and (ROOT / "games").is_dir():
            outdir = ROOT / "games"
        names = args[2:] or [n for n in ALL if (n in DEVTOOLS) == tools and (home(outdir, n) / n).is_dir()]
        if any(n in IMAGES_ONLY for n in names):
            sys.exit("install: the PlayStation 2, demo and bonus discs are not installed")
        if not names:
            sys.exit(f"install: nothing installed in {outdir}")
        bad = 0
        for name in names:
            if name not in ALL:
                sys.exit(f"install: unknown release {name} (see --list)")
            d = home(outdir, name) / name
            if not d.is_dir():
                print(f"   {name}: not installed in {d.parent}")
                bad += 1
            elif verify(name, d) is not True:
                bad += 1
        sys.exit(1 if bad else 0)
    force = "--force" in args
    args = [a for a in args if a != "--force"]
    if not args:
        sys.exit(__doc__)
    layout()
    outdir = Path(args[0])
    names = args[1:] or list(DEVTOOLS if tools else RELEASES)
    for name in names:
        if name not in ALL:
            sys.exit(f"install: unknown release {name} (see --list)")
        if name in IMAGES_ONLY:
            sys.exit(f"install: {name} is kept as an image only; there is nothing to install")
    for name in names:
        where = home(outdir, name)
        where.mkdir(parents=True, exist_ok=True)
        final = where / name
        if final.exists() and not force:
            print(f"== {name}: already installed ({final}); --force to redo")
            continue
        kind, disc_names, opts = ALL[name]
        tmp = where / f".{name}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir()
        print(f"== {name} ({kind}: {' + '.join(disc_names) or opts['source']['artifact']})", flush=True)
        inst = Install(name, tmp)
        n = install_into(inst, name)
        if verify(name, tmp) is False:
            sys.exit(f"install: {name} does not match {sums(name).name}; left in {tmp}")
        # install.reg names the final path, not the .tmp one.
        if final.exists():
            shutil.rmtree(final)
        tmp.rename(final)
        print(f"   {n} files -> {final}")


if __name__ == "__main__":
    main()
