#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Import libraries
import hashlib
import json
import os
import queue
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid

# Import PIP packages
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtCore import QEvent
from PyQt6.QtCore import QPropertyAnimation
from PyQt6.QtCore import Qt
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtGui import QIcon
from PyQt6.QtGui import QPixmap
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QCheckBox
from PyQt6.QtWidgets import QDialog
from PyQt6.QtWidgets import QDialogButtonBox
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtWidgets import QFormLayout
from PyQt6.QtWidgets import QGraphicsOpacityEffect
from PyQt6.QtWidgets import QHBoxLayout
from PyQt6.QtWidgets import QHeaderView
from PyQt6.QtWidgets import QLabel
from PyQt6.QtWidgets import QLineEdit
from PyQt6.QtWidgets import QMenu
from PyQt6.QtWidgets import QMenuBar
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtWidgets import QProgressBar
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QTableWidget
from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtWidgets import QTabWidget
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QWidget
from typing import cast
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import Request
from urllib.request import urlopen

# Define 'VERSION'
VERSION = "v1.2.5"

# Define 'APPNAME'
APPNAME = "MediaSane"

# Define 'WEBSITEURL'
WEBSITEURL = "https://neoslab.com/"

# Define 'CONFIGPATH'
CONFIGPATH = Path.home() / ".config" / "mediasane"

# Define 'CONFIGFILE'
CONFIGFILE = CONFIGPATH / "mediasane.conf"

# Define 'ALLOWIMG'
ALLOWIMG = set("jpg jpeg png gif tif tiff bmp webp heic heif".split())

# Define 'ALLOWVID'
ALLOWVID = set("mp4 mov m4v avi mkv 3gp webm".split())


# Class 'SysUtils'
class SysUtils:
    """
    Utility class providing system-level helper functions for file operations.
    Includes methods for file extension handling, command existence checking,
    EXIF data extraction, date formatting, and secure file movement operations.
    """

    # Define 'lowerext'
    @staticmethod
    def lowerext(p: Path) -> str:
        """
        Extract and return the lowercase file extension from a Path object.
        Removes the leading dot from the extension string before returning.
        Returns empty string if the file has no extension.
        """
        ext = p.suffix[1:]
        return ext.lower()

    # Define 'cmdexists'
    @staticmethod
    def cmdexists(cmd: str) -> bool:
        """
        Check if a command exists and is executable in the system PATH.
        Returns False for empty commands or those containing path separators.
        Searches all directories in PATH for the specified executable.
        """
        if not cmd or "/" in cmd:
            return False

        for directory in os.environ.get("PATH", "").split(os.pathsep):
            candidate = Path(directory) / cmd
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return True
        return False

    # Define 'classify'
    @staticmethod
    def classify(extlc: str, prefs: "ExecPrefs") -> str:
        """
        Classify a file as image or video based on its lowercase extension.
        Returns the appropriate prefix (IMG- for images, VID- for videos).
        Returns empty string if the extension is not supported.
        """
        if extlc in ALLOWIMG:
            return prefs.imgprefix
        if extlc in ALLOWVID:
            return prefs.vidprefix
        return ""

    # Define 'exifdate'
    @staticmethod
    def exifdate(path: Path, timeouts: int = 10) -> str:
        """
        Extract the date from EXIF metadata using exiftool command-line tool.
        Returns date in YYYYMMDD format from DateTimeOriginal or other tags.
        Returns empty string if exiftool is unavailable or extraction fails.
        """
        if not SysUtils.cmdexists("exiftool"):
            return ""
        try:
            proc = subprocess.run(
                [
                    "exiftool", "-s", "-S", "-q", "-q", "-m",
                    "-api", "LargeFileSupport=1", "-fast2",
                    "-d", "%Y%m%d",
                    "-DateTimeOriginal", "-CreateDate", "-MediaCreateDate", "-FileModifyDate",
                    "--", str(path)
                ],
                capture_output=True, text=True, timeout=timeouts
            )
            if proc.returncode == 0:
                line = (proc.stdout.splitlines() or [""])[0].strip()
                if len(line) == 8 and line.isdigit():
                    return line
            return ""
        except subprocess.TimeoutExpired:
            return ""
        except (OSError, subprocess.SubprocessError, ValueError):
            return ""

    # Define 'epochdate'
    @staticmethod
    def epochdate(epoch: float) -> str:
        """
        Convert a Unix timestamp (epoch) to a formatted date string.
        Returns date in YYYYMMDD format using the system local timezone.
        Provides consistent date formatting across different file operations.
        """
        return datetime.fromtimestamp(epoch).strftime("%Y%m%d")

    # Define 'datename'
    @staticmethod
    def datename(name: str) -> str:
        """
        Extract a potential date string from the beginning of a filename.
        Returns the first 8 characters if they are all digits (YYYYMMDD).
        Returns empty string if the filename doesn't start with a valid date.
        """
        if len(name) >= 8 and name[:8].isdigit():
            return name[:8]
        return ""

    # Define 'datetime'
    @staticmethod
    def datetime(path: Path) -> str:
        """
        Get the last modification time of a file as a formatted date string.
        Returns date in YYYYMMDD format using the file's modification timestamp.
        Handles OSError exceptions by returning an empty string on failure.
        """
        try:
            return SysUtils.epochdate(path.stat().st_mtime)
        except (OSError, ValueError):
            return ""

    # Define 'datetoday'
    @staticmethod
    def datetoday() -> str:
        """
        Get the current system date as a formatted string.
        Returns today's date in YYYYMMDD format for fallback naming.
        Used when no other date information can be extracted from a file.
        """
        return datetime.now().strftime("%Y%m%d")

    # Define 'hashkey'
    @staticmethod
    def hashkey(path: Path, hash_budget_s: int = 60, quick_prefix_bytes: int = 1024 * 1024) -> Tuple[str, bool]:
        """
        Generate a hash key for file deduplication with timeout protection.
        Returns a tuple containing the hash string and a timeout flag.
        Uses SHA-256 for complete hashing and Blake2b for fast prefix hashing.
        """
        try:
            st = path.stat()
            size = st.st_size
            mtime = int(st.st_mtime)
        except OSError:
            size = 0
            mtime = 0

        t0 = time.monotonic()
        sha = hashlib.sha256()
        timeout = False
        try:
            with path.open("rb", buffering=1024 * 1024) as fh:
                while True:
                    chunk = fh.read(1024 * 1024)
                    if not chunk:
                        break
                    sha.update(chunk)
                    if time.monotonic() - t0 > hash_budget_s:
                        timeout = True
                        break
        except (OSError, IOError):
            timeout = True

        if timeout:
            return f"weak-{size}@{mtime}", True

        quick = b""
        try:
            with path.open("rb") as fh2:
                quick = fh2.read(quick_prefix_bytes)
        except (OSError, IOError):
            quick = b""
        bl = hashlib.blake2b(quick).hexdigest()
        return f"sha256:{sha.hexdigest()}|b2b1M:{bl}", False

    # Define 'safemove'
    @staticmethod
    def safemove(src: Path, dst: Path) -> bool:
        """
        Safely move a file from source to destination with fallback copy strategy.
        Creates parent directories if they don't exist before moving.
        Falls back to copy+delete if rename operation fails (cross-device moves).
        """
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
            return True
        except OSError:
            try:
                shutil.copy2(src, dst)
                src.unlink(missing_ok=True)
                return True
            except (OSError, IOError):
                return False


# Class 'ExecPrefs'
@dataclass
class ExecPrefs:
    """
    Data class for storing user preferences for file naming conventions.
    Contains prefix strings for images and videos used during renaming.
    Provides methods for dictionary conversion and object reconstruction.
    """

    # Define 'imgprefix'
    imgprefix: str = "IMG-"

    # Define 'vidprefix'
    vidprefix: str = "VID-"

    # Function 'todict'
    def todict(self) -> Dict[str, str]:
        """
        Convert the ExecPrefs object to a dictionary for serialization.
        Returns a dictionary with 'imgprefix' and 'vidprefix' keys.
        Used when saving preferences to configuration files.
        """
        return {"imgprefix": self.imgprefix, "vidprefix": self.vidprefix}

    # Function 'fromdict'
    @staticmethod
    def fromdict(d: Dict[str, str]) -> "ExecPrefs":
        """
        Create an ExecPrefs object from a dictionary of configuration values.
        Uses default values if specific keys are missing from the dictionary.
        Provides safe reconstruction of preferences from serialized data.
        """
        return ExecPrefs(
            imgprefix=str(d.get("imgprefix", "IMG-")),
            vidprefix=str(d.get("vidprefix", "VID-")),
        )


# Class 'ConfigManager'
class ConfigManager:
    """
    Manages loading and saving of application configuration to disk.
    Handles reading/writing key-value pairs from a plain text configuration file.
    Ensures proper directory creation and error handling during I/O operations.
    """

    # Function 'load'
    @staticmethod
    def load() -> Dict[str, str]:
        """
        Load configuration from the config file into a dictionary.
        Ignores empty lines, comments starting with '#', and malformed entries.
        Returns an empty dictionary if the config file doesn't exist or is invalid.
        """
        data: Dict[str, str] = {}
        try:
            if CONFIGFILE.is_file():
                for line in CONFIGFILE.read_text(encoding="utf-8").splitlines():
                    strip = line.strip()
                    if not strip or strip.startswith("#") or "=" not in strip:
                        continue
                    k, v = strip.split("=", 1)
                    data[k.strip()] = v.strip()
        except (OSError, UnicodeDecodeError):
            pass
        return data

    # Function 'save'
    @staticmethod
    def save(prefs: ExecPrefs, other: Dict[str, str]):
        """
        Save application preferences and other settings to the config file.
        Creates the config directory if it doesn't exist before writing.
        Writes configuration in key=value format, one entry per line.
        """
        try:
            CONFIGPATH.mkdir(parents=True, exist_ok=True)
            lines = [f"imgprefix={prefs.imgprefix}", f"vidprefix={prefs.vidprefix}"]
            for k, v in other.items():
                lines.append(f"{k}={v}")
            CONFIGFILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except (OSError, PermissionError):
            pass


# Class 'ExecOptions'
@dataclass
class ExecOptions:
    """
    Data class for storing runtime execution options for the renamer.
    Contains source/output directories, duplicate handling, and timeout settings.
    Provides configuration parameters for dry-run and processing behavior.
    """

    # Define 'srcdir'
    srcdir: str = ""

    # Define 'outdir'
    outdir: str = ""

    # Define 'keepdupes'
    keepdupes: bool = False

    # Define 'dryrun'
    dryrun: bool = False

    # Define 'metatimeout'
    metatimeout: int = 10

    # Define 'hashtimeout'
    hashtimeout: int = 60


# Class 'MediaRenamer'
class MediaRenamer:
    """
    Core class that handles the file renaming and deduplication logic.
    Processes media files by extracting dates, generating new names, and managing duplicates.
    Implements threading-safe operations with cancellation support and progress reporting.
    """

    # Define '__init__'
    def __init__(self, opts: ExecOptions, prefs: ExecPrefs, rowsink: queue.Queue):
        """
        Initialize the MediaRenamer with execution options and preferences.
        Sets up internal data structures for tracking files and results.
        Creates a queue for sending progress updates to the GUI thread.
        """
        self.opts = opts
        self.prefs = prefs
        self.rowsink = rowsink
        self.stopflag = False

        self.hashseen: Dict[str, Path] = {}
        self.actdupes: List[Tuple[Path, str, Optional[Path]]] = []
        self.actrenames: List[Tuple[Path, Path, Path]] = []
        self.results: List[Tuple[str, str]] = []

    # Define 'cancel'
    def cancel(self):
        """
        Signal the renaming operation to stop as soon as possible.
        Sets a flag that is checked periodically during processing.
        Allows graceful cancellation of long-running operations.
        """
        self.stopflag = True

    # Define 'checkstop'
    def checkstop(self):
        """
        Check if the operation has been cancelled and raise an exception if so.
        Called at safe points during processing to enable cancellation.
        Raises RuntimeError with 'Cancelled' message when stop flag is set.
        """
        if self.stopflag:
            raise RuntimeError("Cancelled")

    # Define 'enumfiles'
    @staticmethod
    def enumfiles(root: Path) -> List[Path]:
        """
        Recursively enumerate all supported media files in a directory tree.
        Skips the '.duplicates' folder to avoid processing already moved files.
        Returns a list of Path objects for all images and videos found.
        """
        files: List[Path] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != ".duplicates"]
            for fname in filenames:
                file_path = Path(dirpath) / fname
                ext = SysUtils.lowerext(file_path)
                if ext in ALLOWIMG or ext in ALLOWVID:
                    files.append(file_path)
        return files

    # Define 'resolvedate'
    def resolvedate(self, path_in: Path) -> str:
        """
        Resolve the best available date for a file using multiple strategies.
        Tries filename date, EXIF metadata, file modification time, and today's date.
        Returns the date as a YYYYMMDD string for use in the new filename.
        """
        d = SysUtils.datename(path_in.stem)
        if not d:
            d = SysUtils.exifdate(path_in, timeouts=self.opts.metatimeout)
        if not d:
            d = SysUtils.datetime(path_in)
        if not d:
            d = SysUtils.datetoday()
        return d

    # Define 'parsefilename'
    def parsefilename(self, path: Path) -> Optional[Tuple[str, str, int]]:
        """
        Parse a filename to extract prefix, date, and sequence number.
        Expects format like IMG-20241201-00001.jpg or VID-20241201-00001.mp4.
        Returns a tuple of (prefix, date, sequence) or None if format doesn't match.
        """
        stem = path.stem
        for pfx in (self.prefs.imgprefix, self.prefs.vidprefix):
            base_len = len(pfx)
            if not stem.startswith(pfx):
                continue
            if len(stem) < base_len + 9:
                continue
            date_part = stem[base_len:base_len + 8]
            if not date_part.isdigit():
                continue
            if stem[base_len + 8] != "-":
                continue
            seq_part = stem[base_len + 9:]
            if len(seq_part) == 5 and seq_part.isdigit():
                return pfx, date_part, int(seq_part)
        return None

    # Define 'groupdate'
    def groupdate(self, out: Path) -> Dict[Tuple[str, str], List[Path]]:
        """
        Group files in the output directory by their prefix and date.
        Walks through the directory tree excluding the .duplicates folder.
        Returns a dictionary mapping (prefix, date) keys to lists of file paths.
        """
        groups: Dict[Tuple[str, str], List[Path]] = {}
        try:
            for dirpath, dirnames, filenames in os.walk(out):
                if ".duplicates" in dirnames:
                    dirnames.remove(".duplicates")
                for fname in filenames:
                    path_obj = Path(dirpath) / fname
                    parsed = self.parsefilename(path_obj)
                    if not parsed:
                        continue
                    key = (parsed[0], parsed[1])
                    groups.setdefault(key, []).append(path_obj)
        except (OSError, PermissionError):
            pass
        return groups

    # Define 'allseq'
    def allseq(self, out: Path):
        """
        Renumber all files in the output directory to ensure sequential ordering.
        Groups files by prefix and date, then reassigns sequence numbers in order.
        Uses temporary filenames to avoid conflicts during the renumbering process.
        """
        groups = self.groupdate(out)
        for key, paths in groups.items():
            self.checkstop()
            try:
                paths.sort(key=lambda x: (x.stat().st_mtime, x.name))
            except OSError:
                paths.sort(key=lambda x: x.name)

            prefix, date = key
            targets: Dict[Path, Path] = {}
            for idx, srcpath in enumerate(paths, start=1):
                extlc = SysUtils.lowerext(srcpath)
                dest = out / f"{prefix}{date}-{idx:05d}.{extlc}"
                if dest != srcpath:
                    targets[srcpath] = dest

            if not targets:
                continue

            tmpmap: Dict[Path, Path] = {}
            for src in list(targets.keys()):
                tmp = src.with_name(src.name + f".reseq-{uuid.uuid4().hex[:8]}")
                try:
                    src.rename(tmp)
                except OSError:
                    try:
                        shutil.copy2(src, tmp)
                        src.unlink(missing_ok=True)
                    except (OSError, IOError):
                        continue
                tmpmap[src] = tmp

            for src, final in targets.items():
                tmp = tmpmap.get(src)
                if not tmp:
                    continue
                final.parent.mkdir(parents=True, exist_ok=True)
                cand = final
                while cand.exists():
                    stem = cand.stem
                    j = stem.rfind("-")
                    num = int(stem[j + 1:]) + 1 if j != -1 else 1
                    cand = cand.with_name(stem[:j + 1] + f"{num:05d}" + cand.suffix)
                try:
                    tmp.rename(cand)
                except OSError:
                    try:
                        shutil.copy2(tmp, cand)
                        tmp.unlink(missing_ok=True)
                    except (OSError, IOError):
                        continue
                self.rowsink.put((str(src), str(cand)))

    # Define 'plandup'
    def plandup(self):
        """
        Plan duplicate detection and file renaming operations.
        Scans source directory, identifies duplicates using hash keys.
        Prepares lists of actions for duplicate handling and file renaming.
        """
        src = Path(self.opts.srcdir)
        out = Path(self.opts.outdir) if self.opts.outdir else src

        candidates: List[Tuple[str, float, str, Path, str]] = []
        files = self.enumfiles(src)

        for fpath in files:
            self.checkstop()
            extlc = SysUtils.lowerext(fpath)
            prefix = SysUtils.classify(extlc, self.prefs)
            if not prefix:
                self.results.append((str(fpath), "(unsupported)"))
                continue

            hk, _ = SysUtils.hashkey(fpath, hash_budget_s=self.opts.hashtimeout)
            if hk in self.hashseen:
                if self.opts.keepdupes:
                    dupdir = out / ".duplicates"
                    base = fpath.name
                    dest = dupdir / base
                    n = 0
                    while dest.exists():
                        n += 1
                        dest = dupdir / f"{base}.{n}"
                    self.actdupes.append((fpath, "move", dest))
                    self.results.append((str(fpath), str(dest)))
                else:
                    self.actdupes.append((fpath, "delete", None))
                    self.results.append((str(fpath), "(deleted)"))
                continue
            else:
                self.hashseen[hk] = fpath

            d = self.resolvedate(fpath)
            mt = fpath.stat().st_mtime if fpath.exists() else 0.0
            candidates.append((d, mt, fpath.name, fpath, prefix))

        candidates.sort(key=lambda t: (t[0], t[1], t[2]))
        countdate: Dict[str, int] = {}

        for (d, _mt, _nm, fpath, prefix) in candidates:
            self.checkstop()
            seq = countdate.get(d, 0) + 1
            countdate[d] = seq
            enddst = (out / f"{prefix}{d}-{seq:05d}.{SysUtils.lowerext(fpath)}")
            tmpdst = enddst.with_suffix(enddst.suffix + f".tmp-{uuid.uuid4().hex[:8]}")
            self.actrenames.append((fpath, tmpdst, enddst))
            self.results.append((str(fpath), str(enddst)))

    # Define 'planexec'
    def planexec(self):
        """
        Execute the planned renaming and duplicate handling operations.
        Processes duplicates first, then performs file renames with temporary files.
        Updates the progress queue and performs resequencing after all moves.
        """
        totalrenames = len(self.actrenames)
        self.rowsink.put(("__TOTAL__", str(totalrenames)))

        if self.opts.dryrun:
            for old, new in self.results:
                self.checkstop()
                self.rowsink.put((old, new))
            out = Path(self.opts.outdir) if self.opts.outdir else Path(self.opts.srcdir)
            self.allseq(out)
            return

        for srcpath, action, destpath in self.actdupes:
            self.checkstop()
            if action == "move":
                assert destpath is not None
                destpath.parent.mkdir(parents=True, exist_ok=True)
                SysUtils.safemove(srcpath, destpath)
                self.rowsink.put((str(srcpath), str(destpath)))
            elif action == "delete":
                try:
                    srcpath.unlink(missing_ok=True)
                except (OSError, PermissionError):
                    pass
                self.rowsink.put((str(srcpath), "(deleted)"))

        processed = 0
        for srcpath, tmpdst, final in self.actrenames:
            self.checkstop()

            tmpdst.parent.mkdir(parents=True, exist_ok=True)
            if srcpath.exists():
                SysUtils.safemove(srcpath, tmpdst)

            cand = final
            while cand.exists():
                stem = cand.stem
                i = stem.rfind("-")
                if i == -1 or not stem[i + 1:].isdigit() or len(stem[i + 1:]) != 5:
                    break
                num = int(stem[i + 1:]) + 1
                cand = cand.with_name(stem[:i + 1] + f"{num:05d}" + cand.suffix)

            try:
                if tmpdst.exists():
                    tmpdst.rename(cand)
                else:
                    if srcpath.exists():
                        shutil.copy2(srcpath, cand)
                        srcpath.unlink(missing_ok=True)
            except OSError:
                try:
                    if tmpdst.exists():
                        shutil.copy2(tmpdst, cand)
                        tmpdst.unlink(missing_ok=True)
                except (OSError, IOError):
                    pass

            self.rowsink.put((str(srcpath), str(cand)))
            processed += 1
            self.rowsink.put(("__COUNT__", f"{processed}"))

        out = Path(self.opts.outdir) if self.opts.outdir else Path(self.opts.srcdir)
        self.allseq(out)

    # Function 'streamrun'
    def streamrun(self):
        """
        Execute the complete renaming pipeline in streaming mode.
        First plans duplicate handling and renaming operations.
        Then executes the planned operations while streaming progress updates.
        """
        self.plandup()
        self.planexec()

    # Define 'run'
    def run(self):
        """
        Main entry point for executing the media renaming process.
        Initiates the streaming execution of all renaming operations.
        Designed to be called from a separate thread for responsive GUI.
        """
        self.streamrun()


# Class 'DialogPrefs'
class DialogPrefs(QDialog):
    """
    Dialog window for editing user preferences and naming conventions.
    Provides interface for modifying image and video file prefixes.
    Saves changes when user confirms with OK button, discards on Cancel.
    """

    # Define '__init__'
    def __init__(self, parent: QWidget, prefs: ExecPrefs):
        """
        Initialize the preferences dialog with current preference values.
        Creates input fields for image and video prefixes in a tab widget.
        Sets up OK and Cancel buttons with appropriate dialog actions.
        """
        super().__init__(parent)
        self.setWindowTitle("Preferences")
        self.setModal(True)
        self.resize(520, 240)

        self.prefs = ExecPrefs.fromdict(prefs.todict())
        tabs = QTabWidget(self)

        wnaming = QWidget()
        g = QFormLayout(wnaming)
        self.editimg = QLineEdit(self.prefs.imgprefix)
        self.edited = QLineEdit(self.prefs.vidprefix)
        g.addRow(QLabel("Image prefix:"), self.editimg)
        g.addRow(QLabel("Video prefix:"), self.edited)
        tabs.addTab(wnaming, "Naming")

        btns = QDialogButtonBox(parent=self)
        btnok = QPushButton("OK", self)
        btncancel = QPushButton("Cancel", self)
        btns.addButton(btnok, QDialogButtonBox.ButtonRole.AcceptRole)
        btns.addButton(btncancel, QDialogButtonBox.ButtonRole.RejectRole)
        btnok.clicked.connect(self.accept)
        btncancel.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(btns)

    # Define 'values'
    def values(self) -> ExecPrefs:
        """
        Retrieve the modified preference values from the dialog inputs.
        Strips whitespace and ensures non-empty values default to standard prefixes.
        Returns a new ExecPrefs object with the current dialog settings.
        """
        self.prefs.imgprefix = self.editimg.text().strip() or "IMG-"
        self.prefs.vidprefix = self.edited.text().strip() or "VID-"
        return self.prefs


# Custom 'DialogAbout'
class DialogAbout(QDialog):
    """
    About dialog displaying application information and credits.
    Shows the application logo, version number, website link, and description.
    Provides a simple OK button to close the dialog after viewing.
    """

    # Function '__init__'
    def __init__(self, parent: Optional[QWidget], version: str, website: str):
        """
        Initialize the about dialog with application metadata.
        Loads and displays the application icon from system paths.
        Creates clickable website link and formatted version information.
        """
        super().__init__(parent)
        self.setWindowTitle(f"About {APPNAME}")
        self.setModal(True)
        self.setMinimumSize(520, 360)

        logolabel = QLabel()
        logolabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logopath = [
            Path("/usr/share/pixmaps/mediasane.png")
        ]

        pixmap: Optional[QPixmap] = None
        for pth in logopath:
            if pth.is_file():
                tmp = QPixmap(str(pth))
                if not tmp.isNull():
                    pixmap = tmp
                    break

        if pixmap:
            logolabel.setPixmap(
                pixmap.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        title = QLabel(f"<b>{APPNAME}</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 22px;")

        ver = QLabel(f"Version: {version}")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)

        link = QLabel(f'<a href="{website}">{website}</a>')
        link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        link.setTextFormat(Qt.TextFormat.RichText)
        link.setOpenExternalLinks(True)

        msg = QLabel(
            "Media organizer and renamer\n"
            "De-duplicate, and safely move photos/videos")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)
        msg.setStyleSheet("color: #999;")

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, parent=self)
        btns.accepted.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(logolabel)
        layout.addWidget(title)
        layout.addWidget(ver)
        layout.addWidget(msg)
        layout.addWidget(link)
        layout.addStretch(1)
        layout.addWidget(btns)


# Custom 'DialogCompleted'
class DialogCompleted(QDialog):
    """
    Completion dialog shown after renaming operations finish.
    Displays success or failure message with appropriate icon.
    Allows user to acknowledge the completion of the operation.
    """

    # Function '__init__'
    def __init__(self, parent: Optional[QWidget], error_message: Optional[str] = None):
        """
        Initialize the completion dialog with success or error state.
        Loads success or error icon based on whether an error message is provided.
        Displays appropriate title and message text for the operation result.
        """
        super().__init__(parent)
        self.setWindowTitle("Cleanup Completed" if not error_message else "Cleanup Failed")
        self.setModal(True)
        self.setMinimumSize(420, 280)

        iconlabel = QLabel()
        iconlabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        iconpath = [
            Path("/usr/share/mediasane/icons/success.png")
        ] if not error_message else [
            Path("/usr/share/mediasane/icons/error.png")
        ]

        pix: Optional[QPixmap] = None
        for pth in iconpath:
            if pth.is_file():
                tmp = QPixmap(str(pth))
                if not tmp.isNull():
                    pix = tmp
                    break
        if pix:
            iconlabel.setPixmap(
                pix.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        title = QLabel("<b>Renaming finished successfully</b>" if not error_message else "<b>Renaming failed</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg = QLabel(
            "All selected files have been processed\n"
            "You can safely close this window"
            if not error_message else
            f"{error_message}\nPlease review logs or try again"
        )
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        layout.addWidget(iconlabel)
        layout.addSpacing(10)
        layout.addWidget(title)
        layout.addWidget(msg)
        layout.addStretch(1)
        layout.addSpacing(10)
        layout.addWidget(btns)

    # Function 'showcenter'
    def showcenter(self):
        """
        Display the dialog centered relative to its parent widget.
        Adjusts dialog size before centering for proper alignment.
        Executes the dialog modally, blocking until user closes it.
        """
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            center = parent.geometry().center()
            self.move(center - self.rect().center())
        self.exec()


# Class 'MediaSane'
class MediaSane(QWidget):
    """
    Main application window for the MediaSane GUI.
    Provides interface for selecting source/output directories and running operations.
    Handles threading, progress updates, and user interaction with the renamer.
    """

    completed = pyqtSignal(bool, str)

    # Define '__init__'
    def __init__(self):
        """
        Initialize the main application window and UI components.
        Sets up the menu bar, file selection controls, and results table.
        Loads saved preferences and connects signal/slot connections.
        """
        super().__init__()
        iconpath = Path("/usr/share/pixmaps/mediasane.png")
        if iconpath.is_file():
            appicon = QIcon(str(iconpath))
            self.setWindowIcon(appicon)
            appinstance = QApplication.instance()
            if appinstance is not None:
                app = cast(QApplication, appinstance)
                app.setWindowIcon(appicon)

        self.setWindowTitle(f"{APPNAME} {VERSION} - Media Rename GUI")
        self.resize(1000, 700)

        self.workerthread: Optional[threading.Thread] = None
        self.worker: Optional[MediaRenamer] = None
        self.rowqueue: "queue.Queue[Tuple[str,str]]" = queue.Queue()

        self.totalfiles: int = 0
        self.namecount: int = 0
        self.rowindex: Dict[str, int] = {}

        menubar = QMenuBar(self)
        mfile = cast(QMenu, menubar.addMenu("File"))
        actquit = QAction("Quit", self)
        actquit.triggered.connect(QApplication.quit)
        mfile.addAction(actquit)

        medit = cast(QMenu, menubar.addMenu("Edit"))
        actprefs = QAction("Preferences", self)
        actprefs.triggered.connect(self.onprefs)
        medit.addAction(actprefs)

        mhelp = cast(QMenu, menubar.addMenu("Help"))
        actabout = QAction("About", self)
        actabout.triggered.connect(self.onabout)
        mhelp.addAction(actabout)

        self.redis = QLineEdit()
        self.srcbtn = QPushButton("Browse…")
        self.srcbtn.clicked.connect(lambda: self.pickdir(self.redis))

        self.outedit = QLineEdit()
        self.outbtn = QPushButton("Browse…")
        self.outbtn.clicked.connect(lambda: self.pickdir(self.outedit))

        self.srclabel = QLabel("Source:")
        self.outlabel = QLabel("Output:")

        labelwidth = max(self.srclabel.sizeHint().width(), self.outlabel.sizeHint().width())
        self.srclabel.setFixedWidth(labelwidth)
        self.outlabel.setFixedWidth(labelwidth)

        srcrow = QHBoxLayout()
        srcrow.addWidget(self.srclabel)
        srcrow.addWidget(self.redis, 1)
        srcrow.addWidget(self.srcbtn)

        outrow = QHBoxLayout()
        outrow.addWidget(self.outlabel)
        outrow.addWidget(self.outedit, 1)
        outrow.addWidget(self.outbtn)

        self.checkdupes = QCheckBox("Keep duplicates (move to .duplicates)")
        optrow = QHBoxLayout()
        optrow.addWidget(self.checkdupes)
        optrow.addStretch()

        self.btndry = QPushButton("Dry-Run")
        self.btnrun = QPushButton("Run")
        self.btnstop = QPushButton("Stop")
        self.btnstop.setEnabled(False)
        self.btndry.clicked.connect(lambda: self.onrun(dry=True))
        self.btnrun.clicked.connect(lambda: self.onrun(dry=False))
        self.btnstop.clicked.connect(self.onstop)

        btns = QHBoxLayout()
        btns.addWidget(self.btndry)
        btns.addWidget(self.btnrun)
        btns.addWidget(self.btnstop)
        btns.addStretch()

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Original Path", "New Path / Result"])
        header = cast(QHeaderView, self.table.horizontalHeader())
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        vertical = cast(QHeaderView, self.table.verticalHeader())
        vertical.setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setShowGrid(True)

        root = QVBoxLayout()
        root.setMenuBar(menubar)
        root.addLayout(srcrow)
        root.addLayout(outrow)
        root.addLayout(optrow)
        root.addLayout(btns)
        root.addWidget(self.table, 1)
        root.addWidget(self.progress)
        self.setLayout(root)

        self.counterbox = QWidget(self)
        self.counterbox.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        v = QVBoxLayout(self.counterbox)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        self.countertitle = QLabel("Files", self.counterbox)
        self.countertitle.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.countertitle.setStyleSheet("font-weight: 600;")
        self.countervalue = QLabel("0/0", self.counterbox)
        self.countervalue.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.countervalue.setStyleSheet("font-weight: 600;")
        v.addWidget(self.countertitle)
        v.addWidget(self.countervalue)
        self.counterbox.adjustSize()
        self.installEventFilter(self)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.flushrows)
        self.timer.start(50)

        cfg = ConfigManager.load()
        self.prefs = ExecPrefs.fromdict(cfg)
        self.redis.setText("")
        self.outedit.setText("")
        self.redis.editingFinished.connect(self.populatetext)

        self.completed.connect(self.showhandler)
        self.fadeanimation: Optional[QPropertyAnimation] = None

    # Function 'ensureposition'
    def ensureposition(self):
        """
        Position the file counter overlay in the top-right corner of the window.
        Calculates position relative to the output directory input field.
        Ensures the counter stays visible and properly positioned on resize events.
        """
        right_margin = 10
        top_offset = self.outedit.geometry().bottom() + 6
        x = self.width() - self.counterbox.width() - right_margin
        y = top_offset
        self.counterbox.move(max(0, x), max(0, y))
        self.counterbox.raise_()

    # Function 'populatetext'
    def populatetext(self):
        """
        Populate the results table with files from the source directory.
        Triggered when the source directory input field loses focus.
        Updates the table display to show all media files in the selected directory.
        """
        srcpath = self.redis.text().strip()
        if srcpath and Path(srcpath).is_dir():
            self.populatetable(srcpath)

    # Function 'populatetable'
    def populatetable(self, directory: str):
        """
        Fill the table widget with all media files from the specified directory.
        Clears existing rows and rebuilds the table with sorted file paths.
        Updates the file counter and prepares for renaming operations.
        """
        self.table.setRowCount(0)
        self.rowindex.clear()
        try:
            paths = MediaRenamer.enumfiles(Path(directory))
        except (OSError, PermissionError):
            paths = []
        paths.sort(key=lambda p: str(p))
        for fpath in paths:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(str(fpath)))
            self.table.setItem(r, 1, QTableWidgetItem(""))
            self.rowindex[str(fpath)] = r
        self.totalfiles = len(paths)
        self.namecount = 0
        self.countervalue.setText(f"{self.namecount}/{self.totalfiles}")
        self.counterbox.adjustSize()
        self.ensureposition()

    # Function 'eventFilter'
    def eventFilter(self, obj, ev: QEvent):
        """
        Handle window resize and show events to reposition the counter overlay.
        Filters events for the main window to maintain counter positioning.
        Ensures the counter stays visible during window size changes.
        """
        if obj is self and ev.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.ensureposition()
        return super().eventFilter(obj, ev)

    # Function 'pickdir'
    def pickdir(self, edit: QLineEdit):
        """
        Open a directory selection dialog and update the specified input field.
        Saves the last used source and output directories to configuration.
        If updating source directory, refreshes the file table display.
        """
        d = QFileDialog.getExistingDirectory(self, "Choose Directory", edit.text() or str(Path.home()))
        if d:
            edit.setText(d)
            other = {
                "lastsrc": self.redis.text().strip(),
                "lastout": self.outedit.text().strip(),
            }
            ConfigManager.save(self.prefs, other)
            if edit is self.redis:
                self.populatetable(d)

    # Function 'flushrows'
    def flushrows(self):
        """
        Process queued updates from the worker thread to update the GUI table.
        Handles special message types for total file count and progress updates.
        Updates table rows with original and new file paths as they become available.
        """
        try:
            while True:
                old, new = self.rowqueue.get_nowait()
                if old == "__TOTAL__":
                    try:
                        self.totalfiles = int(new)
                    except ValueError:
                        pass
                    self.namecount = 0
                    self.countervalue.setText(f"{self.namecount}/{self.totalfiles}")
                    self.counterbox.adjustSize()
                    self.ensureposition()
                    continue

                if old == "__COUNT__":
                    try:
                        self.namecount = int(new)
                    except ValueError:
                        pass
                    self.countervalue.setText(f"{self.namecount}/{self.totalfiles}")
                    self.counterbox.adjustSize()
                    self.ensureposition()
                    continue

                if old in self.rowindex:
                    r = self.rowindex[old]
                    self.table.setItem(r, 1, QTableWidgetItem(new))
                else:
                    r = self.table.rowCount()
                    self.table.insertRow(r)
                    self.table.setItem(r, 0, QTableWidgetItem(old))
                    self.table.setItem(r, 1, QTableWidgetItem(new))
                    self.rowindex[old] = r
        except queue.Empty:
            pass

    # Function 'onabout'
    def onabout(self):
        """
        Show the about dialog when the About menu item is clicked.
        Displays application information including version and website.
        Modal dialog that blocks until user closes it.
        """
        dlg = DialogAbout(self, VERSION, WEBSITEURL)
        dlg.exec()

    # Function 'onprefs'
    def onprefs(self):
        """
        Open the preferences dialog for editing naming conventions.
        If user accepts changes, updates preferences and saves to configuration.
        Preserves last used directory paths when saving new preferences.
        """
        dlg = DialogPrefs(self, self.prefs)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.prefs = dlg.values()
            other = {
                "lastsrc": self.redis.text().strip(),
                "lastout": self.outedit.text().strip(),
            }
            ConfigManager.save(self.prefs, other)

    # Function 'onstop'
    def onstop(self):
        """
        Cancel the currently running renaming operation.
        Disables the stop button to prevent multiple cancellation requests.
        Signals the worker thread to stop at the next safe checkpoint.
        """
        if self.worker:
            self.worker.cancel()
            self.btnstop.setEnabled(False)

    # Function 'onrun'
    def onrun(self, dry: bool):
        """
        Start the renaming operation with the specified dry-run setting.
        Validates source directory existence and creates output directory if needed.
        Launches worker thread to perform renaming without blocking the GUI.
        """
        src = self.redis.text().strip()
        out = self.outedit.text().strip()

        if not src:
            QMessageBox.warning(self, "Missing", "Please pick a source directory.")
            return

        if not Path(src).is_dir():
            QMessageBox.critical(self, "Error", "Source directory does not exist.")
            return

        if out and not Path(out).exists():
            try:
                Path(out).mkdir(parents=True, exist_ok=True)
            except (OSError, PermissionError):
                QMessageBox.critical(self, "Error", "Cannot create output directory.")
                return

        if self.table.rowCount() == 0:
            self.populatetable(src)

        self.progress.setVisible(True)
        self.btnstop.setEnabled(True)
        self.btnrun.setEnabled(False)
        self.btndry.setEnabled(False)

        opts = ExecOptions(
            srcdir=src,
            outdir=out,
            keepdupes=self.checkdupes.isChecked(),
            dryrun=dry,
            metatimeout=10,
            hashtimeout=60,
        )

        worker = MediaRenamer(opts, self.prefs, self.rowqueue)
        self.worker = worker

        # Function 'workload'
        def workload():
            """
            Worker function executed in a separate thread to perform renaming.
            Catches exceptions and emits completion signal with status.
            Restores button states and hides progress bar when finished.
            """
            success = True
            errmsg = ""

            try:
                worker.run()
            except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as e:
                success = False
                errmsg = f"{e}"
                self.rowqueue.put(("ERROR", str(e)))
            finally:
                self.progress.setVisible(False)
                self.btnstop.setEnabled(False)
                self.btnrun.setEnabled(True)
                self.btndry.setEnabled(True)

                try:
                    self.completed.emit(success, errmsg)
                except RuntimeError:
                    pass

        workerthread = threading.Thread(target=workload, daemon=True)
        self.workerthread = workerthread
        workerthread.start()

    # Function 'showhandler'
    def showhandler(self, success: bool, errmsg: str):
        """
        Handle the completion signal from the worker thread.
        Shows completion dialog unless in dry-run mode.
        Triggers fade animation for the results table after dry-run completion.
        """
        if self.worker and self.worker.opts.dryrun:
            return
        dlg = DialogCompleted(self, error_message=(errmsg if not success else None))
        dlg.showcenter()
        self.fadecleaner()

    # Function 'fadecleaner'
    def fadecleaner(self):
        """
        Apply a fade-out animation to clear the results table.
        Creates opacity effect and animates transition from visible to invisible.
        Clears table rows after animation completes to indicate fresh state.
        """
        if self.table.rowCount() == 0:
            return

        effect = QGraphicsOpacityEffect(self.table)
        self.table.setGraphicsEffect(effect)
        effect.setOpacity(1.0)

        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(700)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)

        # Function 'fadeafter'
        def fadeafter():
            """
            Callback to clear the table after fade animation completes.
            Removes all table rows and removes the graphics effect.
            Called when the opacity animation finishes.
            """
            self.table.setRowCount(0)
            self.table.setGraphicsEffect(None)

        anim.finished.connect(fadeafter)
        self.fadeanimation = anim
        anim.start()


# Class 'UpdateChecker'
class UpdateChecker:
    """
    Checks for application updates from GitHub releases.
    Compares current version with latest available release.
    Shows notification dialog when newer version is available.
    """

    # Function '__init__'
    def __init__(self, parent: QWidget, appname: str, currvers: str, gitrepo: str, logopaths: Optional[List[Path]] = None):
        """
        Initializes update checker with application metadata and GitHub repository.
        Stores parent widget reference for dialog display.
        Configures paths for loading application icon in notification dialog.
        """
        self.parent = parent
        self.appname = appname
        self.currvers = currvers
        self.gitrepo = gitrepo
        self.logopaths = logopaths or [
            Path(f"/usr/share/pixmaps/{appname.lower()}.png")
        ]

    # Function 'versionparser'
    @staticmethod
    def versionparser(ver: str) -> Tuple[int, ...]:
        """
        Parses version string into tuple of integers for comparison.
        Strips leading 'v' or 'V' characters from version string.
        Returns tuple with parts converted to integers for lexicographic comparison.
        """
        v = ver.strip()
        if v.startswith(("v", "V")):
            v = v[1:]
        parts: List[int] = []
        for part in v.split("."):
            try:
                parts.append(int(part))
            except ValueError:
                break
        return tuple(parts) or (0,)

    # Function 'checknewer'
    def checknewer(self, current: str, latest: str) -> bool:
        """
        Compares two version strings to determine if latest is newer.
        Normalizes version length by padding with zeros.
        Returns True if latest version is greater than current version.
        """
        c = self.versionparser(current)
        l = self.versionparser(latest)
        ln = max(len(c), len(l))
        c = c + (0,) * (ln - len(c))
        l = l + (0,) * (ln - len(l))
        return c < l

    # Function 'checknotify'
    def checknotify(self, timeout: int = 3):
        """
        Checks for updates and shows notification if newer version exists.
        Fetches latest version from GitHub and compares with current.
        Shows update dialog when newer release is available.
        """
        latest = self.fetchtag(timeout=timeout)
        if not latest:
            return
        if not self.checknewer(self.currvers, latest):
            return
        url = f"https://github.com/{self.gitrepo}/releases/tag/{latest}"
        self.showupdate(latest, url)

    # Function 'fetchtag'
    def fetchtag(self, timeout: int = 3) -> Optional[str]:
        """
        Fetches latest release tag name from GitHub API.
        Makes HTTP request with timeout to prevent UI freezing.
        Returns tag name string or None if request fails.
        """
        try:
            url = f"https://api.github.com/repos/{self.gitrepo}/releases/latest"
            req = Request(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": self.appname,
                },
            )
            with urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", "ignore"))

            tag = str(data.get("tag_name") or "").strip()
            return tag or None

        except (HTTPError, URLError, socket.timeout, ValueError, OSError):
            return None

    # Function 'showupdate'
    def showupdate(self, latest: str, url: str):
        """
        Displays update notification dialog with version information.
        Shows current version, latest version, and download link.
        Provides OK button to dismiss dialog after reading.
        """
        dlg = QDialog(self.parent)
        dlg.setWindowTitle("Update Available")
        dlg.setModal(True)
        dlg.setMinimumSize(520, 360)

        logolabel = QLabel()
        logolabel.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pix: Optional[QPixmap] = None
        for pth in self.logopaths:
            if pth.is_file():
                tmp = QPixmap(str(pth))
                if not tmp.isNull():
                    pix = tmp
                    break
        if pix:
            logolabel.setPixmap(
                pix.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        title = QLabel(f"<b>A new version of {self.appname} is available</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 20px;")

        ver = QLabel(f"Current version {self.currvers}\nLatest version {latest}")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)

        msg = QLabel(
            "A newer release is available on GitHub.\n"
            "Please download the latest version from the link below."
        )
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setWordWrap(True)
        msg.setStyleSheet("color: #999;")

        link = QLabel(f'<a href="{url}">{url}</a>')
        link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        link.setTextFormat(Qt.TextFormat.RichText)
        link.setOpenExternalLinks(True)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok, parent=dlg)
        btns.accepted.connect(dlg.accept)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(logolabel)
        layout.addSpacing(10)
        layout.addWidget(title)
        layout.addWidget(ver)
        layout.addWidget(msg)
        layout.addWidget(link)
        layout.addStretch(1)
        layout.addSpacing(10)
        layout.addWidget(btns)
        dlg.exec()


# Class 'AppEntry'
class AppEntry:
    """
    Application entry point class that initializes and starts the MediaSane GUI.
    Sets up Qt application with proper environment and signal handling.
    Creates main window, checks for updates, and starts the event loop.
    """

    # Function 'main'
    @staticmethod
    def main():
        """
        Main entry point function that launches the entire application.
        Configures Qt logging, sets up application name and icon.
        Creates main window, starts update checker, and executes application loop.
        """
        os.environ["QT_LOGGING_RULES"] = "qt.qpa.*=false"
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        app = QApplication(sys.argv)

        if hasattr(QGuiApplication, "setDesktopFileName"):
            QGuiApplication.setDesktopFileName("mediasane")

        app.setApplicationName(f"{APPNAME}")
        app.setWindowIcon(QIcon("/usr/share/pixmaps/mediasane.png"))

        win = MediaSane()
        win.show()
        checker = UpdateChecker(
            parent=win,
            appname=APPNAME,
            currvers=VERSION,
            gitrepo="neoslab/mediasane",
            logopaths=[Path("/usr/share/pixmaps/mediasane.png")],
        )

        win.updatecheck = checker
        QTimer.singleShot(1500, checker.checknotify)
        sys.exit(app.exec())


# Callback
if __name__ == "__main__":
    AppEntry.main()