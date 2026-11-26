#  SPDX-FileCopyrightText: 2016-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT


import functools
import os
import re
import shlex
import shutil
import subprocess
from enum import Enum
from pathlib import Path, PureWindowsPath
from typing import NamedTuple, Optional
from urllib.parse import quote, unquote, urlparse

import packaging.version

try:
    import xdg  # type: ignore
    from xdg import BaseDirectory
    from xdg.DesktopEntry import DesktopEntry  # type: ignore

    have_xdg = True
except ImportError:
    have_xdg = False

from showinfm.constants import FileManagerType
from showinfm.exceptions import (
    DesktopEntryError,
    DesktopEnvironmentUnknownError,
    LinuxFileManagerError,
    XdgQueryError,
    XdgUnavailableError,
)

_linux_desktop: Optional["LinuxDesktop"] = None


def stock_linux_file_manager() -> str:
    """
    Get stock (system default) file manager for the desktop environment.

    Looks up value only if the desktop environment can be determined.

    All exceptions are raised.

    :return: executable name
    """

    global _linux_desktop
    if _linux_desktop is None:
        _linux_desktop = linux_desktop()

    desktop = _linux_desktop.name
    try:
        desktop = LinuxDesktopFamily.get(desktop) or desktop

        return StandardLinuxFileManager[desktop]
    except KeyError as err:
        msg = f"The desktop {desktop} is unknown"
        raise DesktopEnvironmentUnknownError(msg) from err


def user_linux_file_manager() -> str:
    """
    Determine the file manager for this desktop as set by the user.

    xdg-mime is used to get a .desktop file, from which the executable name is
    extracted. The executable is not examined to see if it is valid or if it even
    exists.

    Where several handlers are registered for directories, xdg-mime lists them
    semicolon separated in order of preference. The first entry whose .desktop file
    is present and names an executable is the one used: an entry that names a program
    which has since been uninstalled still counts as the user's choice here, and it is
    valid_linux_file_manager() that rejects a choice which is not installed. Each
    handler is looked for in every data directory before the next one is tried, so
    which directory a file manager installed its entry into does not override that
    order. An empty answer means nothing is registered, which is reported as no choice
    at all.

    All exceptions are raised.

    :return: executable name, or an empty string if there is no user choice
    """

    if not have_xdg:
        msg = "xdg utilities and/or the python binding for xdg are not installed"
        raise XdgUnavailableError(msg)

    xdg_cmd = "xdg-mime query default inode/directory"
    cmd = shlex.split(xdg_cmd)
    try:
        desktop_file: str = subprocess.check_output(cmd, universal_newlines=True)
    except Exception as err:
        msg = f"Could not determine file manager using {xdg_cmd}"
        raise XdgQueryError(msg) from err

    # Where more than one handler is registered, xdg-mime lists them in order of
    # preference
    for handler in desktop_file.strip().split(";"):
        if not handler:
            # An empty answer splits to one empty name, which must not be used as a
            # filename: that would test the applications directory itself, which
            # exists, and report it as an unreadable desktop entry
            continue
        for desktop_path in (
            Path(d) / "applications" for d in BaseDirectory.xdg_data_dirs
        ):
            path = desktop_path / handler
            if not path.exists():
                continue
            fm_cmd = _executable_from_desktop_entry(str(path))
            if fm_cmd:
                return fm_cmd

    return ""


def _executable_from_desktop_entry(path: str) -> str:
    """
    Read a .desktop entry and return the executable it names.

    An entry with no Exec key, or an empty one, returns an empty string rather than
    raising, because it names nothing: the caller takes that as this handler deciding
    nothing and moves on to the next one. An entry that cannot be read or parsed does
    raise, since a broken file is not the same as an absent choice. Whether the named
    program is installed is not examined here.

    :param path: full path of the .desktop file to read
    :return: the executable name, or an empty string when the entry names none
    """

    try:
        desktop_entry = DesktopEntry(path)
    except Exception as err:
        msg = f"Could not open desktop entry at {path}"
        raise DesktopEntryError(msg) from err
    try:
        desktop_entry.parse(path)
    except xdg.Exceptions.ParsingError as err:
        msg = f"Could not parse desktop entry at {path}"
        raise DesktopEntryError(msg) from err
    except Exception as err:
        msg = f"Desktop entry at {path} might be malformed"
        raise DesktopEntryError(msg) from err

    fm = desktop_entry.getExec()
    if not fm:
        return ""

    # Strip away any extraneous arguments
    fm_cmd = fm.split()[0]
    # Strip away any path information
    fm_cmd = Path(fm_cmd).name
    # Strip away any quotes
    return fm_cmd.replace('"', "").replace("'", "")


def valid_linux_file_manager() -> str:
    """
    Get user's file manager, falling back to using sensible defaults for the particular
    desktop environment.

    The user's choice and the stock manager are both tried, in that order, and the
    first that is installed is returned.

    All exceptions are caught.

    :return: the user's default file manager if this module knows it and it is
     installed, else the stock file manager if that is installed, else an empty string
    """

    try:
        stock = stock_linux_file_manager()
    except Exception:
        stock = ""

    try:
        user_fm = user_linux_file_manager()
    except Exception:
        user_fm = ""
    else:
        if user_fm not in known_linux_file_managers():
            user_fm = ""

    for fm in (user_fm, stock):
        if fm and shutil.which(fm):
            return fm

    return ""


def known_linux_file_managers() -> tuple[str, ...]:
    """
    Generate a collection of Linux file managers this module knows about

    :return: tuple of executable names
    """

    return tuple(LinuxFileManagerBehavior.keys())


def linux_file_manager_type(file_manager: str) -> FileManagerType:
    """
    Determine the type of command line arguments the Linux file manager expects
    :param file_manager: executable name
    :return: FileManagerType matching with the executable name, else
     FileManagerType.regular as a fallback
    """

    if file_manager == "caja" and caja_supports_select():
        return FileManagerType.select
    return LinuxFileManagerBehavior.get(file_manager, FileManagerType.regular)


def caja_version() -> packaging.version.Version | None:
    """
    Get the version of Caja via a command line switch

    The version is read from the first digit in the output to its end, which depends
    on Caja printing no earlier digits and printing the version last, as it does in
    MATE caja 1.26.4. Output that continues after the version is not parseable, and
    caja_supports_select() treats that failure as absent support for --select, so Caja
    opens the folder without selecting the file rather than reporting an error.

    :return: parsed ver
    """

    try:
        version_string = (
            subprocess.run(["caja", "--version"], stdout=subprocess.PIPE, check=True)
            .stdout.decode()
            .strip()
        )
    except subprocess.CalledProcessError as err:
        msg = "Failed to get version number from caja"
        raise LinuxFileManagerError(msg) from err

    result = re.search(r"\d", version_string)
    if result is None:
        return None

    version = version_string[result.start() :]
    return packaging.version.parse(version)


def caja_supports_select() -> bool:
    """
    Determine if caja supports --select command line switch.

    :return: True if caja version is >= version 1.26
    """

    try:
        version = caja_version()
    except Exception:
        return False
    if version is None:
        return False
    return version >= packaging.version.Version("1.26")


def translate_wsl_path(path: str, from_windows_to_wsl: bool) -> str:
    """
    Use the WSL command wslpath to translate between Windows and WSL paths.

    Uses subprocesss. Exceptions are not caught.

    :param path: path to convert in string format
    :param from_windows_to_wsl: whether to translate from Windows to WSL (True),
     or WSL to Windows (False)
    :return: the translated path
    """
    arg = "-u" if from_windows_to_wsl else "-w"
    return (
        subprocess.run(["wslpath", arg, path], capture_output=True, check=True)
        .stdout.decode()
        .strip()
    )


class WSLTransformPathURI(NamedTuple):
    is_win_location: bool | None
    win_uri: str | None
    win_path: str | None
    linux_path: str | None
    is_dir: bool | None
    exists: bool


def _wsl_share(uri: str) -> WSLTransformPathURI:
    r"""
    Describe a network share given as a URI that carries a server.

    Windows names a share \\server\share, so the authority and the path together
    make the Windows path. wslpath is deliberately not asked: measured on WSL2 it
    refuses a UNC outright (exit 1), and given a path with no drive in it, it
    resolves the remainder against the *current* drive, so file://server/share/x
    became /mnt/d/share/x, which names a local folder that has nothing to do with
    the share. A share that is not mapped to a drive letter has no /mnt entry at
    all, so existence is left to Windows to judge. Measured, an unreachable
    server makes Explorer do nothing rather than open something else, which is the
    safer of the two answers from here.

    :param uri: a file: URI whose authority names the server
    :return: the details of the location for Windows
    """

    parsed = urlparse(url=uri)
    unc = str(PureWindowsPath(f"\\\\{parsed.netloc}{unquote(parsed.path)}"))
    return WSLTransformPathURI(
        win_uri=uri.replace(" ", "%20"),
        win_path=unc,
        linux_path=None,
        is_dir=None,
        exists=True,
        is_win_location=True,
    )


def wsl_transform_path_uri(
    path_or_uri: str, generate_win_path: bool
) -> WSLTransformPathURI:
    r"""
    Transforms URI or path into path and URI suitable for working with WSL.

    Detects if working with path or URI, and whether it is POSIX or Windows
    Assumes all paths mounted on /mnt are located in Windows.

    :param path_or_uri: path or URI to examine
    :param generate_win_path: if passed a Linux path, generate path and URI for use in
     Windows. Will do so anyway if the path is located in Windows, not the Linux
     instance.
    :return: Named Tuple containing values in WSLTranformPathURI:
      is_win_location: if the path/URI is located within a Windows file system
      win_uri is: the URI as it appears to Windows
      win_path: the path as it appears to Windows
      linux_path: the path as it appears to Linux
      is_dir: whether the path/URI is a directory
      exists: whether the path/URI exists
    """

    # Imported here rather than at the top of the module: showinfm.system imports
    # this module before it has worked out current_platform, and tools reads that
    # name as it is imported, so a module-level import fails at startup.
    from showinfm.system import tools

    is_smb_uri = tools.is_smb_uri

    win_uri: str | None = None
    win_path: str | None = None
    linux_path: str | None = None
    is_dir: bool | None = None
    exists: bool = False

    if is_smb_uri(path_or_uri):
        if generate_win_path:
            # Explorer has no handler for smb:, but the same share is a file: URI
            # carrying the server, which is what _wsl_share expects.
            return _wsl_share("file:" + path_or_uri[len("smb:") :])
        # Asked by a Linux file manager, which opens shares of this kind itself
        # and needs nothing done to the URI.
        return WSLTransformPathURI(
            win_uri=None,
            win_path=None,
            linux_path=None,
            is_dir=None,
            exists=True,
            is_win_location=False,
        )

    if path_or_uri.startswith("file:/"):
        is_win_uri = False
        parsed = urlparse(url=path_or_uri)
        path = unquote(parsed.path)
        netloc = parsed.netloc
        if len(path) > 2 and path[0] == "/" and path[1].isalpha() and path[2] == ":":
            is_win_uri = True
            # Remove first forward slash from e.g. /c:/Program Files
            path = path[1:]
        elif netloc and netloc != "localhost":
            return _wsl_share(path_or_uri)

        if is_win_uri:
            win_uri = path_or_uri.replace(" ", "%20")
            win_path = path
            try:
                linux_path = translate_wsl_path(path, from_windows_to_wsl=True)
            except subprocess.CalledProcessError:
                exists = False
        else:
            linux_path = path

    else:
        path = path_or_uri
        if path.startswith("/") and not path.startswith("/mnt"):
            linux_path = path
        else:
            # Path must be either a Windows style path, or a relative path on Posix.
            # First, check if the path is Windows style, e.g. C:\Program Files
            # Note that UNC shares are also considered drives
            drive = PureWindowsPath(path).drive
            is_unc = drive.startswith("\\\\")
            if (drive and drive[0].isalpha() and drive[1] == ":") or is_unc:
                win_path = path
                try:
                    linux_path = translate_wsl_path(path=path, from_windows_to_wsl=True)
                except subprocess.CalledProcessError:
                    exists = False

                # Generate Windows URI
                if is_unc:
                    win_uri = "file:" + _quote_path_for_uri(path.replace("\\", "/"))
                elif linux_path is not None:
                    win_uri = wsl_path_to_uri_for_windows_explorer(linux_path)
            else:
                # relative path was passed
                linux_path = str(Path(path).resolve())

    if linux_path is None:
        is_win_location = None
    else:
        lpath = Path(linux_path)
        exists = lpath.exists()

        is_win_location = linux_path.startswith("/mnt/")

        if exists:
            is_dir = lpath.is_dir()
            if generate_win_path or is_win_location:
                try:
                    win_path = translate_wsl_path(
                        path=linux_path, from_windows_to_wsl=False
                    )
                except subprocess.CalledProcessError:
                    exists = False
                if win_path and not win_uri:
                    if not is_win_location:
                        win_uri = "file:" + _quote_path_for_uri(
                            win_path.replace("\\", "/")
                        )
                    else:
                        win_uri = wsl_path_to_uri_for_windows_explorer(linux_path)

    if is_dir:
        if linux_path is not None and linux_path[-1] == "/":
            linux_path = linux_path[:-1]
        if win_path is not None and win_path[-1] == "\\":
            win_path = win_path[:-1]
        if win_uri is not None and win_uri[-1] != "/":
            win_uri = f"{win_uri}/"

    if linux_path is not None:
        assert is_win_location is not None
    if win_uri is not None:
        assert win_path is not None
    if exists:
        assert is_dir is not None

    return WSLTransformPathURI(
        is_win_location=is_win_location,
        win_uri=win_uri,
        win_path=win_path,
        linux_path=linux_path,
        is_dir=is_dir,
        exists=exists,
    )


def _quote_path_for_uri(slash_path: str) -> str:
    r"""
    Percent encode a slash separated path, leaving its slashes alone.

    urllib.request.pathname2url() is deliberately not used. It now inserts an empty
    authority in front of an absolute path, so '/mnt/c/x' comes back as '///mnt/c/x'
    and '//wsl.localhost/x' as '////wsl.localhost/x', and which of those happens
    depends on the interpreter: the two-slash form changed in Python 3.12 and the
    one-slash form in 3.14. Windows Explorer needs those slashes exactly as they are,
    so only the encoding is wanted here.

    :param slash_path: Windows path written with forward slashes
    :return: the path percent encoded, its slashes untouched
    """

    return quote(slash_path, safe="/")


def wsl_path_to_uri_for_windows_explorer(path: str) -> str:
    r"""
    Convert a path to a URI accepted by Windows Explorer.

    Windows URIs are different from Linux URIs. As Wikipedia points out, Window
    specifies file:///c:/path/to/the%20file.txt
    (note the three slashes after file:), and
    file://hostname/path/to/the%20file.txt

    The drive letter is split away from the rest of the path before encoding
    because a colon would otherwise be percent encoded.

    :param path: path format like '/mnt/c/some/path', '/home/user', 'C:\some\path'
    :return: a file URI accepted by Windows Explorer
    """

    assert not path.startswith("\\\\")
    assert path.startswith("/mnt/")

    # Under WSL the drive letter sits in the path where a share name would be
    drive, _, remainder = path[len("/mnt/") :].partition("/")
    return f"file:///{drive}:{_quote_path_for_uri('/' + remainder)}"


class LinuxDesktop(Enum):
    gnome = 1
    unity = 2
    cinnamon = 3
    kde = 4
    xfce = 5
    mate = 6
    lxde = 7
    lxqt = 8
    ubuntugnome = 9
    popgnome = 10
    deepin = 11
    zorin = 12
    ukui = 13  # Kylin
    pantheon = 14
    enlightenment = 15
    wsl = 16
    wsl2 = 17
    cutefish = 18
    lumina = 19
    unknown = 20
    cosmic = 21


LinuxDesktopHumanize = {
    "gnome": "Gnome",
    "unity": "Unity",
    "cinnamon": "Cinnamon",
    "kde": "KDE",
    "xfce": "XFCE",
    "mate": "Mate",
    "lxde": "LXDE",
    "lxqt": "LxQt",
    "ubuntugnome": "Ubuntu Gnome",
    "popgnome": "Pop Gnome",
    "deepin": "Deepin",
    "zorin": "Zorin",
    "ukui": "UKUI",
    "pantheon": "Pantheon",
    "enlightenment": "Enlightenment",
    "wsl": "WSL1",
    "wsl2": "WSL2",
    "cutefish": "Cutefish",
    "lumina": "Lumina",
    "unknown": "Unknown",
    "cosmic": "Cosmic",
}

LinuxDesktopFamily = {
    "ubuntugnome": "gnome",
    "popgnome": "gnome",
    "zorin": "gnome",
    "unity": "gnome",
}

StandardLinuxFileManager = {
    "gnome": "nautilus",
    "kde": "dolphin",
    "cinnamon": "nemo",
    "mate": "caja",
    "xfce": "thunar",
    "lxde": "pcmanfm",
    "lxqt": "pcmanfm-qt",
    "deepin": "dde-file-manager",
    "pantheon": "io.elementary.files",
    "ukui": "peony",
    "enlightenment": "pcmanfm",
    "wsl": "explorer.exe",
    "wsl2": "explorer.exe",
    "cutefish": "cutefish-filemanager",
    "lumina": "lumina-fm",
    "cosmic": "cosmic-files",
}

LinuxFileManagerBehavior = {
    "nautilus": FileManagerType.select,
    "dolphin": FileManagerType.select,
    "caja": FileManagerType.dir_only_uri,
    "thunar": FileManagerType.dir_only_uri,
    "nemo": FileManagerType.regular,
    "pcmanfm": FileManagerType.dir_only_uri,
    "peony": FileManagerType.show_items,
    "index": FileManagerType.dir_only_uri,
    "doublecmd": FileManagerType.dual_panel,
    "krusader": FileManagerType.dir_only_uri,
    "spacefm": FileManagerType.dir_only_uri,
    "fman": FileManagerType.dual_panel,
}
LinuxFileManagerBehavior["pcmanfm-qt"] = FileManagerType.dir_only_uri
LinuxFileManagerBehavior["dde-file-manager"] = FileManagerType.show_item
LinuxFileManagerBehavior["io.elementary.files"] = FileManagerType.regular
LinuxFileManagerBehavior["cutefish-filemanager"] = FileManagerType.dir_only_uri
LinuxFileManagerBehavior["lumina-fm"] = FileManagerType.dir_only_uri
LinuxFileManagerBehavior["cosmic-files"] = FileManagerType.regular


def wsl_version() -> LinuxDesktop | None:
    with open("/proc/version") as f:
        p = f.read()
    if p.find("microsoft") > 0 and p.find("WSL2"):
        return LinuxDesktop.wsl2
    if p.find("Microsoft") > 0:
        return LinuxDesktop.wsl
    return None


def detect_wsl() -> bool:
    with open("/proc/version") as f:
        p = f.read()
    return p.lower().find("microsoft") > 0


@functools.cache
def linux_desktop() -> LinuxDesktop:
    """
    Determine Linux desktop environment

    :return: enum representing desktop environment, Desktop.unknown if unknown.
    """

    try:
        env = os.getenv("XDG_CURRENT_DESKTOP").lower()  # type: ignore
    except AttributeError as err:
        wsl = wsl_version()
        if wsl is not None:
            return wsl
        msg = "The value for XDG_CURRENT_DESKTOP is not set"
        raise DesktopEnvironmentUnknownError(msg) from err

    if env in ("unity:unity7", "unity:unity7:ubuntu"):
        env = "unity"
    elif env == "x-cinnamon":
        env = "cinnamon"
    elif env == "ubuntu:gnome":
        env = "ubuntugnome"
    elif env == "pop:gnome":
        env = "popgnome"
    elif env in ("gnome-classic:gnome", "budgie:gnome"):
        env = "gnome"
    elif env == "zorin:gnome":
        env = "zorin"
    elif env == "kde:plasma":
        env = "kde"

    try:
        return LinuxDesktop[env]
    except KeyError as err:
        msg = f"The desktop environment {env} is unknown"
        raise DesktopEnvironmentUnknownError(msg) from err


def linux_desktop_humanize(desktop: LinuxDesktop) -> str:
    """
    Make LinuxDesktop name human readable.
    :return: desktop name spelled out
    """

    return LinuxDesktopHumanize[desktop.name]
