# Copyright (c) 2016-2021 Damon Lynch
# SPDX - License - Identifier: MIT


from enum import Enum
import functools
import os
from pathlib import Path, PureWindowsPath
import re
import shlex
import shutil
import subprocess
from typing import Optional, Tuple, NamedTuple
from urllib.parse import urlparse, unquote
import urllib.request

import packaging.version

try:
    from xdg.DesktopEntry import DesktopEntry
    from xdg import BaseDirectory
    import xdg
except ImportError:
    pass

from ..constants import FileManagerType

_linux_desktop = None


def stock_linux_file_manager() -> str:
    """
    Get stock (system default) file manager for the desktop environment.

    Looks up value only if the the desktop environment can be determined.

    All exceptions are raised.

    :return: executable name
    """

    global _linux_desktop
    if _linux_desktop is None:
        _linux_desktop = linux_desktop()

    try:
        desktop = _linux_desktop.name
        desktop = LinuxDesktopFamily.get(desktop) or desktop

        return StandardLinuxFileManager[desktop]
    except KeyError:
        raise Exception("The desktop {} is unknown".format(desktop))


def user_linux_file_manager() -> str:
    """
    Determine the file manager for this desktop as set by the user.

    xdg-mime is used to get a .desktop file, from which the executable name is extracted.
    The executable is not examined to see if it is valid or if it even exists.

    All exceptions are raised.

    :return: executable name
    """

    xdg_cmd = "xdg-mime query default inode/directory"
    cmd = shlex.split(xdg_cmd)
    try:
        desktop_file = subprocess.check_output(
            cmd, universal_newlines=True
        )  # type: str
    except:
        raise Exception("Could not determine file manager using {}".format(xdg_cmd))

    # Remove new line character from output
    desktop_file = desktop_file[:-1]
    if desktop_file.endswith(";"):
        desktop_file = desktop_file[:-1]

    for desktop_path in (Path(d) / "applications" for d in BaseDirectory.xdg_data_dirs):
        path = desktop_path / desktop_file
        if path.exists():
            p = str(path)
            try:
                desktop_entry = DesktopEntry(p)
            except:
                raise Exception("Could not open desktop entry at {}".format(p))
            try:
                desktop_entry.parse(p)
            except xdg.Exceptions.ParsingError:
                raise Exception("Could not parse desktop entry at {}".format(p))
            except:
                raise Exception("Desktop entry at {} might be malformed".format(p))

            fm = desktop_entry.getExec()

            # Strip away any extraneous arguments
            fm_cmd = fm.split()[0]
            # Strip away any path information
            fm_cmd = Path(fm_cmd).name
            # Strip away any quotes
            fm_cmd = fm_cmd.replace('"', "")
            fm_cmd = fm_cmd.replace("'", "")

            return fm_cmd

    return ""


def valid_linux_file_manager() -> str:
    """
    Get user's file manager, falling back to using sensible defaults for the particular
    desktop environment.

    All exceptions are caught.

    :return: If the user's default file manager is set and it is known by this module,
     then return it. Otherwise return the stock file manager, if it exists.
    """

    try:
        stock = stock_linux_file_manager()
    except:
        stock = ""

    try:
        user_fm = user_linux_file_manager()
    except:
        user_fm = ""
    else:
        if user_fm not in known_linux_file_managers():
            user_fm = ""

    if not (user_fm or stock):
        return ""

    if not user_fm:
        fm = stock
    else:
        fm = user_fm

    if fm and shutil.which(fm):
        return fm
    else:
        return ""


def known_linux_file_managers() -> Tuple[str]:
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


def caja_version() -> Optional[packaging.version.Version]:
    """
    Get the version of Caja via a command line switch
    :return: parsed ver
    """

    try:
        version_string = (
            subprocess.run(["caja", "--version"], stdout=subprocess.PIPE, check=True)
            .stdout.decode()
            .strip()
        )
    except subprocess.CalledProcessError:
        raise Exception("Failed to get version number from caja")

    result = re.search("\d", version_string)
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

    Uses subprocesss. Exceptions not caught.

    :param path: path to convert in string format
    :param from_windows_to_wsl: whether to translate from Windows to WSL (True),
     or WSL to Windows (False)
    :return: the translated path
    """
    if from_windows_to_wsl:
        arg = "-u"
    else:
        arg = "-w"
    return (
        subprocess.run(
            ["wslpath", arg, path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        .stdout.decode()
        .strip()
    )


def wsl_path_is_for_windows(path_or_uri: str) -> bool:
    """
    When running in WSL, detect if the path being passed is in Windows or Linux

    Reference: https://docs.microsoft.com/en-us/windows/wsl/filesystems

    :param path_or_uri:
    :return:
    """

    if path_or_uri.startswith("file://"):
        # Assume valid URI
        # Look for drive letter, windows style
        if path_or_uri[3:4].isalpha() and path_or_uri[4:5] == ":":
            return True
        # Look for UNC host name: anything that does not start with a leading /
        elif path_or_uri[7].isalpha():
            return True
        return False
    else:
        drive = PureWindowsPath(path_or_uri).drive
        if drive:
            # C:\
            if drive[0].isalpha() and drive[1] == ":":
                return True
            # UNC share
            if drive[:2] == r"\\":
                return True
        # Assume anything under /mnt is Windows
        return path_or_uri.startswith("/mnt")


class WSLTransformPathURI(NamedTuple):
    is_win_location: bool
    win_uri: str
    win_path: str
    linux_path: str
    is_dir: bool
    exists: bool


def wsl_transform_path_uri(
    path_or_uri: str, generate_win_path: bool
) -> WSLTransformPathURI:
    r"""
    Transforms URI or path into path and URI suitable for working with WSL.

    Detects if working with path or URI, and whether it is POSIX or Windows
    Assumes all paths mounted on /mnt are located in Windows.

    :param path_or_uri: path or URI to examine
    :param generate_win_path: if passed a Linux path, generate path and URI for use in
     Windows. Will do so anyway if path is located in Windows, not the Linux instance.
    :return: Named Tuple containing values in WSLTranformPathURI

    >>> import platform
    >>> assert platform.system() == "Linux"
    >>> r = wsl_transform_path_uri("file:///c:/Program%20Files/Common%20Files/", True)
    >>> r.win_path
    'C:\\Program Files\\Common Files'
    >>> r.is_win_location
    True
    >>> r.linux_path
    '/mnt/c/Program Files/Common Files'
    >>> r.win_uri
    'file:///c:/Program%20Files/Common%20Files/'
    >>> r.is_win_location
    True
    >>> r.is_dir if r.exists else True
    True
    >>> r = wsl_transform_path_uri("file:///c:/Program%20Files/Common%20Files", True)
    >>> r.win_uri
    'file:///c:/Program%20Files/Common%20Files/'
    >>> r = wsl_transform_path_uri("file:///c:/Program Files/Common Files", True)
    >>> r.win_uri
    'file:///c:/Program%20Files/Common%20Files/'
    >>> r = wsl_transform_path_uri("file:///c:/Program%20Files/Barrier/barrier.conf", True)
    >>> r.win_path
    'C:\\Program Files\\Barrier\\barrier.conf'
    >>> r.is_win_location
    True
    >>> r.linux_path
    '/mnt/c/Program Files/Barrier/barrier.conf'
    >>> r.is_dir if r.exists else False
    False
    >>> r.win_uri
    'file:///c:/Program%20Files/Barrier/barrier.conf'
    >>> from pathlib import Path
    >>> home = Path.home()
    >>> r = wsl_transform_path_uri(f"file://localhost{home}/.bashrc", True)
    >>> r.is_dir if r.exists else False
    False
    >>> r.is_win_location
    False
    >>> r.linux_path # doctest: +ELLIPSIS
    '/home/.../.bashrc'
    >>> r.win_path  # doctest: +ELLIPSIS
    '\\\\...\\...\\home\\...\\.bashrc'
    >>> r.win_uri  # doctest: +ELLIPSIS
    'file://.../.../home/.../.bashrc'
    >>> r = wsl_transform_path_uri(f"file://{home}/.bashrc", True)
    >>> r.is_dir
    False
    >>> r.is_win_location
    False
    >>> r.linux_path # doctest: +ELLIPSIS
    '/home/.../.bashrc'
    >>> r.win_path  # doctest: +ELLIPSIS
    '\\\\...\\...\\home\\...\\.bashrc'
    >>> r.win_uri  # doctest: +ELLIPSIS
    'file://.../.../home/.../.bashrc'
    >>> r = wsl_transform_path_uri(f"file://localhost{home}/my%20file.txt", True)
    >>> r.is_dir if r.exists else False
    False
    >>> r.win_path if r.exists else r'\\wsl.localhost\Ubuntu-20.04\home\damon\my file.txt' # doctest: +ELLIPSIS
    '\\\\...\\...\\home\\...\\my file.txt'
    >>> r.is_win_location
    False
    >>> r.win_uri if r.exists else 'file://wsl$/Ubuntu-20.04/home/damon/my%20file.txt' # doctest: +ELLIPSIS
    'file://.../.../home/.../my%20file.txt'
    >>> r = wsl_transform_path_uri("file:///etc/fstab", True)
    >>> r.exists
    True
    >>> r.is_dir
    False
    >>> r.linux_path
    '/etc/fstab'
    >>> r.is_win_location
    False
    >>> r.win_path  # doctest: +ELLIPSIS
    '\\\\...\\...\\etc\\fstab'
    >>> r.win_uri  # doctest: +ELLIPSIS
    'file://.../.../etc/fstab'
    >>> r = wsl_transform_path_uri("file:/etc/fstab", True)
    >>> r.exists
    True
    >>> r.is_dir
    False
    >>> r.linux_path
    '/etc/fstab'
    >>> r.is_win_location
    False
    >>> r.win_path  # doctest: +ELLIPSIS
    '\\\\...\\...\\etc\\fstab'
    >>> r.win_uri  # doctest: +ELLIPSIS
    'file://.../.../etc/fstab'
    >>> r = wsl_transform_path_uri("file:///etc", True)
    >>> r.exists
    True
    >>> r.is_dir
    True
    >>> r.linux_path
    '/etc'
    >>> r.is_win_location
    False
    >>> r.win_path  # doctest: +ELLIPSIS
    '\\\\...\\...\\etc'
    >>> r.win_uri  # doctest: +ELLIPSIS
    'file://.../.../etc/'
    >>> r = wsl_transform_path_uri("file:///etc", False)
    >>> r.win_path
    >>> r.win_uri
    >>> r = wsl_transform_path_uri(f"file://{home}/dir with spaces", True)
    >>> r.is_dir if r.exists else True
    True
    >>> r.linux_path  # doctest: +ELLIPSIS
    '/home/.../dir with spaces'
    >>> r.is_win_location
    False
    >>> r.win_path if r.exists else '\\\\wsl.localhost\\openSUSE-Leap-15.3\\home\\damon\\dir with spaces'  # doctest: +ELLIPSIS
    '\\\\...\\...\\home\\...\\dir with spaces'
    >>> r.win_uri if r.exists else 'file://wsl.localhost/openSUSE-Leap-15.3/home/damon/dir%20with%20spaces/'  # doctest: +ELLIPSIS
    'file://.../.../home/.../dir%20with%20spaces/'
    >>> r = wsl_transform_path_uri("file:///c:/Program%20Files/Common%20Files", True)
    >>> r.is_win_location
    True
    >>> r.win_path
    'C:\\Program Files\\Common Files'
    >>> r.linux_path
    '/mnt/c/Program Files/Common Files'
    >>> r = wsl_transform_path_uri("file:///mnt/c/Program%20Files/", True)
    >>> r.is_win_location
    True
    >>> r.exists
    True
    >>> r.is_dir
    True
    >>> r.win_path
    'C:\\Program Files'
    >>> r.linux_path
    '/mnt/c/Program Files'
    >>> r.win_uri
    'file:///c:/Program%20Files/'
    >>> r = wsl_transform_path_uri(r"C:\Program Files", True)
    >>> r.is_win_location
    True
    >>> r.exists
    True
    >>> r.is_dir
    True
    >>> r.win_path
    'C:\\Program Files'
    >>> r.linux_path
    '/mnt/c/Program Files'
    >>> r.win_uri
    'file:///c:/Program%20Files/'
    >>> import os
    >>> import pwd
    >>> user = pwd.getpwuid(os.getuid())[0]
    >>> r = wsl_transform_path_uri(f"\\\\wsl.localhost\\openSUSE-Leap-15.3\\home\\{user}\\My Photos", True)
    >>> r.is_win_location if r.exists else False
    False
    >>> r.win_path # doctest: +ELLIPSIS
    '\\\\wsl.localhost\\openSUSE-Leap-15.3\\home\\...\\My Photos'
    >>> r.win_uri  # doctest: +ELLIPSIS
    'file://wsl.localhost/openSUSE-Leap-15.3/home/.../My%20Photos...'
    >>> r.linux_path if r.exists else "/home/damon/My Photos"  # doctest: +ELLIPSIS
    '/home/.../My Photos'
    >>> r = wsl_transform_path_uri("/mnt/c/Program Files/", True)
    >>> r.is_win_location
    True
    >>> r.exists
    True
    >>> r.is_dir
    True
    >>> r.win_path
    'C:\\Program Files'
    >>> r.linux_path
    '/mnt/c/Program Files'
    >>> r.win_uri
    'file:///c:/Program%20Files/'
    >>> r = wsl_transform_path_uri(str(home), True)
    >>> r.is_win_location
    False
    >>> r.exists
    True
    >>> r.is_dir
    True
    >>> r.win_path  # doctest: +ELLIPSIS
    '\\\\...\\...\\home\\...'
    >>> r.linux_path  # doctest: +ELLIPSIS
    '/home/...'
    >>> r.win_uri   # doctest: +ELLIPSIS
    'file://.../.../home/.../'
    >>> r = wsl_transform_path_uri(f"{home}/dir with spaces", True)
    >>> r.is_win_location
    False
    >>> r.is_dir if r.exists else True
    True
    >>> r.linux_path  # doctest: +ELLIPSIS
    '/home/.../dir with spaces'
    >>> r.win_path if r.exists else '\\\\wsl.localhost\\openSUSE-Leap-15.3\\home\\damon\\dir with spaces'  # doctest: +ELLIPSIS
    '\\\\...\\...\\home\\...\dir with spaces'
    >>> r.win_uri  if r.exists else 'file://wsl.localhost/openSUSE-Leap-15.3/home/damon/dir%20with%20spaces/'  # doctest: +ELLIPSIS
    'file://.../.../home/.../dir%20with%20spaces/'
    >>> r = wsl_transform_path_uri(f"{home}/.bashrc", True)
    >>> r.is_win_location
    False
    >>> r.is_dir if r.exists else False
    False
    >>> r.linux_path  # doctest: +ELLIPSIS
    '/home/.../.bashrc'
    >>> r.win_path  # doctest: +ELLIPSIS
    '\\\\...\\...\\home\\...\.bashrc'
    >>> r.win_uri  # doctest: +ELLIPSIS
    'file://.../.../home/.../.bashrc'
    >>> cwd = os.getcwd()
    >>> os.chdir(home)
    >>> r = wsl_transform_path_uri(".bashrc", True)
    >>> r.linux_path   # doctest: +ELLIPSIS
    '/home/.../.bashrc'
    >>> r.win_path  # doctest: +ELLIPSIS
    '\\\\...\\...\\home\\...\.bashrc'
    >>> r.is_dir if r.exists else False
    False
    >>> r.is_win_location
    False
    >>> r.win_uri  # doctest: +ELLIPSIS
    'file://.../.../home/.../.bashrc'
    >>> os.chdir(cwd)
    """

    win_uri = None
    win_path = None
    linux_path = None
    is_dir = None
    exists = None
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
            is_win_uri = True

        if is_win_uri:
            win_uri = path_or_uri.replace(" ", "%20")
            win_path = path
            try:
                linux_path = translate_wsl_path(path, from_windows_to_wsl=True)
            except subprocess.CalledProcessError as e:
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
                except subprocess.CalledProcessError as e:
                    exists = False

                # Generate Windows URI
                if is_unc:
                    wuri = urllib.request.pathname2url(path.replace("\\", "/"))
                    win_uri = f"file:{wuri}"
                else:
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
                except subprocess.CalledProcessError as e:
                    exists = False
                if win_path and not win_uri:
                    if not is_win_location:
                        wuri = urllib.request.pathname2url(win_path.replace("\\", "/"))
                        win_uri = f"file:{wuri}"
                    else:
                        win_uri = wsl_path_to_uri_for_windows_explorer(linux_path)

    if is_dir:
        if linux_path is not None:
            if linux_path[-1] == "/":
                linux_path = linux_path[:-1]
        if win_path is not None:
            if win_path[-1] == "\\":
                win_path = win_path[:-1]
        if win_uri is not None:
            if win_uri[-1] != "/":
                win_uri = f"{win_uri}/"

    return WSLTransformPathURI(
        is_win_location=is_win_location,
        win_uri=win_uri,
        win_path=win_path,
        linux_path=linux_path,
        is_dir=is_dir,
        exists=exists,
    )


def wsl_path_to_uri_for_windows_explorer(path: str) -> str:
    r"""
    Convert a path to a URI accepted by Windows Explorer.

    Windows URIs are different from Linux URIs. As Wikipedia points out, Window
    specifies file:///c:/path/to/the%20file.txt
    (note the three slashes after file:), and
    file://hostname/path/to/the%20file.txt

    :param path: path format like '/mnt/c/some/path', '/home/user', 'C:\some\path'
    :return: a file URI accepted by Windows Explorer
    """

    assert not path.startswith("\\\\")
    assert path.startswith("/mnt/")

    path = urllib.request.pathname2url(path)
    # Remove the /mnt portion, keep the drive letter, and insert a colon
    return f"file://{path[4:6]}:{path[6:]}"


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


LinuxDesktopHumanize = dict(
    gnome="Gnome",
    unity="Unity",
    cinnamon="Cinnamon",
    kde="KDE",
    xfce="XFCE",
    mate="Mate",
    lxde="LXDE",
    lxqt="LxQt",
    ubuntugnome="Ubuntu Gnome",
    popgnome="Pop Gnome",
    deepin="Deepin",
    zorin="Zorin",
    ukui="UKUI",
    pantheon="Pantheon",
    enlightenment="Enlightenment",
    wsl="WSL1",
    wsl2="WSL2",
    cutefish="Cutefish",
    lumina="Lumina",
    unknown="Unknown",
)


LinuxDesktopFamily = dict(
    ubuntugnome="gnome",
    popgnome="gnome",
    zorin="gnome",
    unity="gnome",
)


StandardLinuxFileManager = dict(
    gnome="nautilus",
    kde="dolphin",
    cinnamon="nemo",
    mate="caja",
    xfce="thunar",
    lxde="pcmanfm",
    lxqt="pcmanfm-qt",
    deepin="dde-file-manager",
    pantheon="io.elementary.files",
    ukui="peony",
    enlightenment="pcmanfm",
    wsl="explorer.exe",
    wsl2="explorer.exe",
    cutefish="cutefish-filemanager",
    lumina="lumina-fm",
)


LinuxFileManagerBehavior = dict(
    nautilus=FileManagerType.select,
    dolphin=FileManagerType.select,
    caja=FileManagerType.dir_only_uri,
    thunar=FileManagerType.dir_only_uri,
    nemo=FileManagerType.regular,
    pcmanfm=FileManagerType.dir_only_uri,
    peony=FileManagerType.show_items,
    index=FileManagerType.dir_only_uri,
    doublecmd=FileManagerType.dual_panel,
    krusader=FileManagerType.dir_only_uri,
    spacefm=FileManagerType.dir_only_uri,
    fman=FileManagerType.dual_panel,
)
LinuxFileManagerBehavior["pcmanfm-qt"] = FileManagerType.dir_only_uri
LinuxFileManagerBehavior["dde-file-manager"] = FileManagerType.show_item
LinuxFileManagerBehavior["io.elementary.files"] = FileManagerType.regular
LinuxFileManagerBehavior["cutefish-filemanager"] = FileManagerType.dir_only_uri
LinuxFileManagerBehavior["lumina-fm"] = FileManagerType.dir_only_uri


def wsl_version() -> Optional[LinuxDesktop]:
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


@functools.lru_cache(maxsize=None)
def linux_desktop() -> LinuxDesktop:
    """
    Determine Linux desktop environment

    :return: enum representing desktop environment, Desktop.unknown if unknown.
    """

    try:
        env = os.getenv("XDG_CURRENT_DESKTOP").lower()
    except AttributeError:
        wsl = wsl_version()
        if wsl is not None:
            return wsl
        else:
            raise Exception("The value for XDG_CURRENT_DESKTOP is not set")

    if env == "unity:unity7":
        env = "unity"
    elif env == "x-cinnamon":
        env = "cinnamon"
    elif env == "ubuntu:gnome":
        env = "ubuntugnome"
    elif env == "pop:gnome":
        env = "popgnome"
    elif env == "gnome-classic:gnome":
        env = "gnome"
    elif env == "budgie:gnome":
        env = "gnome"
    elif env == "zorin:gnome":
        env = "zorin"

    try:
        return LinuxDesktop[env]
    except KeyError:
        raise Exception("The desktop environment {} is unknown".format(env))


def linux_desktop_humanize(desktop: LinuxDesktop) -> str:
    """
    Make LinuxDesktop name human readable.
    :return: desktop name spelled out
    """

    return LinuxDesktopHumanize[desktop.name]
