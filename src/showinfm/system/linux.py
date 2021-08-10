# Copyright (c) 2016-2021 Damon Lynch
# SPDX - License - Identifier: MIT

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016-2021, Damon Lynch"

from enum import Enum
import os
import shlex
import shutil
import subprocess
from typing import Optional, Tuple

try:
    from xdg.DesktopEntry import DesktopEntry
    from xdg import BaseDirectory
    import xdg
except ImportError:
    pass

from ..constants import FileManagerType

_linux_desktop = None


def get_stock_linux_file_manager() -> str:
    """
    Get stock (system default) file manager for the desktop environment.

    Looks up value only if the the desktop environment can be determined.

    All exceptions are raised.

    :return: executable name
    """

    global _linux_desktop
    if _linux_desktop is None:
        _linux_desktop = get_linux_desktop()

    try:
        desktop = _linux_desktop.name
        desktop = LinuxDesktopFamily.get(desktop) or desktop

        return StandardLinuxFileManager[desktop]
    except KeyError:
        raise Exception("The desktop {} is unknown".format(desktop))


def get_user_linux_file_manager() -> str:
    """
    Determine the file manager for this desktop as set by the user.

    xdg-mime is used to get a .desktop file, from which the executable name is extracted.
    The executable is not examined to see if it is valid or if it even exists.

    All exceptions are raised.

    :return: executable name
    """

    xdg_cmd = 'xdg-mime query default inode/directory'
    cmd = shlex.split(xdg_cmd)
    try:
        desktop_file = subprocess.check_output(cmd, universal_newlines=True)  # type: str
    except:
        raise Exception("Could not determine file manager using {}".format(xdg_cmd))

    # Remove new line character from output
    desktop_file = desktop_file[:-1]
    if desktop_file.endswith(';'):
        desktop_file = desktop_file[:-1]

    for desktop_path in (os.path.join(d, 'applications') for d in BaseDirectory.xdg_data_dirs):
        path = os.path.join(desktop_path, desktop_file)
        if os.path.exists(path):
            try:
                desktop_entry = DesktopEntry(path)
            except:
                raise Exception("Could not open desktop entry at {}".format(path))
            try:
                desktop_entry.parse(path)
            except xdg.Exceptions.ParsingError:
                raise Exception("Could not parse desktop entry at {}".format(path))
            except:
                raise Exception("Desktop entry at {} might be malformed".format(path))

            fm = desktop_entry.getExec()

            # Strip away any extraneous arguments
            fm_cmd = fm.split()[0]
            # Strip away any path information
            fm_cmd = os.path.split(fm_cmd)[1]
            # Strip away any quotes
            fm_cmd = fm_cmd.replace('"', '')
            fm_cmd = fm_cmd.replace("'", '')

            return fm_cmd

    return ''


def get_valid_linux_file_manager() -> str:
    """
    Get user's file manager, falling back to using sensible defaults for the particular desktop environment.

    All exceptions are caught.

    :return: If the user's default file manager is set and it is known by this module, then
    return it. Otherwise return the stock file manager, if it exists.
    """

    try:
        stock = get_stock_linux_file_manager()
    except:
        stock = ''

    try:
        user_fm = get_user_linux_file_manager()
    except:
        user_fm = ''
    else:
        if user_fm not in get_known_linux_file_managers():
            user_fm = ''

    if not (user_fm and stock):
        return ''

    if not user_fm:
        fm = stock
    else:
        fm = user_fm

    if fm and shutil.which(fm):
        return fm
    else:
        return ''


def get_known_linux_file_managers() -> Tuple[str]:
    """
    Generate a collection of Linux file managers this module knows about

    :return: tuple of executable names
    """

    return tuple(StandardLinuxFileManager.values())


def get_linux_file_manager_type(file_manager: str) -> FileManagerType:
    """
    Determine the type of command line arguments the Linux file manager expects
    :param file_manager: executable name
    :return: FileManagerType matching with the executable name, else FileManagerType.regular as a fallback
    """

    return LinuxFileManagerBehavior.get(file_manager, FileManagerType.regular)


def wsl_path_is_directory(path: str) -> bool:
    # Simple case: Linux path
    if os.path.isdir(path):
        return True
    # Simple case: Linux file
    if os.path.isfile(path):
        return False
    # Potential windows path: let's try convert it from a Windows path to a WSL path
    try:
        linux_path = subprocess.run(
            ['wslpath', '-u', path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
        ).stdout.decode().strip()
    except subprocess.CalledProcessError:
        return False
    return os.path.isdir(linux_path)



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
    unknown = 18


LinuxDesktopFamily = dict(
    ubuntugnome='gnome',
    popgnome='gnome',
    zorin='gnome',
    unity='gnome',
 )


StandardLinuxFileManager = dict(
    gnome='nautilus',
    kde='dolphin',
    cinnamon='nemo',
    mate='caja',
    xfce='thunar',
    lxde='pcmanfm',
    lxqt='pcmanfm-qt',
    deepin='dde-file-manager',
    pantheon='io.elementary.files',
    ukui='peony',
    enlightenment='pcmanfm',
    wsl='explorer.exe',
    wsl2='explorer.exe'
)


LinuxFileManagerBehavior = dict(
    nautilus=FileManagerType.select,
    dolphin=FileManagerType.select,
    caja=FileManagerType.dir_only_uri,
    thunar=FileManagerType.dir_only_uri,
    nemo=FileManagerType.regular,
    pcmanfm=FileManagerType.dir_only_uri,
    peony=FileManagerType.show_items,
)
LinuxFileManagerBehavior['pcmanfm-qt'] = FileManagerType.dir_only_uri
LinuxFileManagerBehavior['dde-file-manager'] = FileManagerType.show_item
LinuxFileManagerBehavior['io.elementary.files'] = FileManagerType.regular


def wsl_version() -> Optional[LinuxDesktop]:
    with open('/proc/version') as f:
        p = f.read()
    if p.find('microsoft') > 0 and p.find('WSL2'):
        return LinuxDesktop.wsl2
    if p.find('Microsoft') > 0:
        return LinuxDesktop.wsl
    return None


def detect_wsl() -> bool:
    with open('/proc/version') as f:
        p = f.read()
    return p.lower().find('microsoft') > 0


def get_linux_desktop() -> LinuxDesktop:
    """
    Determine Linux desktop environment

    :return: enum representing desktop environment, Desktop.unknown if unknown.
    """

    try:
        env = os.getenv('XDG_CURRENT_DESKTOP').lower()
    except AttributeError:
        wsl = wsl_version()
        if wsl is not None:
            return wsl
        else:
            raise Exception("The value for XDG_CURRENT_DESKTOP is not set")

    if env == 'unity:unity7':
        env = 'unity'
    elif env == 'x-cinnamon':
        env = 'cinnamon'
    elif env == 'ubuntu:gnome':
        env = 'ubuntugnome'
    elif env == 'pop:gnome':
        env = 'popgnome'
    elif env == 'gnome-classic:gnome':
        env = 'gnome'
    elif env == 'budgie:gnome':
        env = 'gnome'
    elif env == 'zorin:gnome':
        env = 'zorin'

    try:
        return LinuxDesktop[env]
    except KeyError:
        raise Exception("The desktop environment {} is unknown".format(env))


