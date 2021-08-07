import os
import platform
import shlex
import subprocess
import sys
from typing import Optional, Tuple, Union, Sequence
from enum import Enum
import urllib.parse
import shutil
import argparse
import pathlib

try:
    from xdg.DesktopEntry import DesktopEntry
    from xdg import BaseDirectory
    import xdg
except ImportError:
    pass


__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2011-2021, Damon Lynch"
__title__ = "Show in File Manager"
__summary__ = "Platform independent way for a Python script to open the system file manager and optionally select " \
              "files to highlight in it."

__version__ = '0.0.1'


_default_file_manager_probed = False
_default_file_manager = None
_default_file_manager_type = None


class FileManagerType(Enum):
    regular = 1         # file_manager "File1" "File2"
    select = 2          # file_manager --select
    dir_only_uri = 3    # cannot select files
    show_item = 4       # file_manager --show-item
    show_items = 5      # file_manager --show-items
    win_select = 6      # explorer.exe /select


# Linux specific routines

_linux_desktop = None


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
    unknown = 15


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
    ukui='peony'
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


def get_linux_desktop() -> LinuxDesktop:
    """
    Determine Linux desktop environment
    :return: enum representing desktop environment, Desktop.unknown if unknown.
    """

    try:
        env = os.getenv('XDG_CURRENT_DESKTOP').lower()
    except AttributeError:
        # Occurs when there is no value set
        return LinuxDesktop.unknown

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
        return LinuxDesktop.unknown


def _set_linux_desktop() -> None:
    global _linux_desktop
    _linux_desktop = get_linux_desktop()


def standard_linux_file_manager_for_desktop() -> Tuple[Optional[str], Optional[FileManagerType]]:
    """
    If default file manager cannot be determined using system tools, guess
    based on desktop environment.

    :return: file manager command (without path), and type; if not detected, (None, None)
    """

    if _linux_desktop is None:
        _set_linux_desktop()

    try:
        desktop = _linux_desktop.name
        desktop = LinuxDesktopFamily.get(desktop) or desktop

        fm = StandardLinuxFileManager[desktop]
        assert shutil.which(fm)
        t = LinuxFileManagerBehavior[fm]
        return fm, t
    except KeyError:
        return None, None
    except AssertionError:
        return None, None


def determine_linux_file_manager(force_standard: bool = False) -> Tuple[Optional[str], Optional[FileManagerType]]:
    """
    Attempt to determine the default file manager for the system.

    :param force_standard: if file manager does not match expectations for current desktop environment,
    return the standard file manager for that desktop.  The file manager will always exist, regardless.
    :return: file manager command (without path), and type; if not detected, (None, None)
    """

    assert sys.platform.startswith('linux')
    cmd = shlex.split('xdg-mime query default inode/directory')
    try:
        desktop_file = subprocess.check_output(cmd, universal_newlines=True)  # type: str
    except:
        return standard_linux_file_manager_for_desktop()

    # Remove new line character from output
    desktop_file = desktop_file[:-1]
    if desktop_file.endswith(';'):
        desktop_file = desktop_file[:-1]

    for desktop_path in (os.path.join(d, 'applications') for d in BaseDirectory.xdg_data_dirs):
        path = os.path.join(desktop_path, desktop_file)
        if os.path.exists(path):
            try:
                desktop_entry = DesktopEntry(path)
            except xdg.Exceptions.ParsingError:
                return standard_linux_file_manager_for_desktop()
            try:
                desktop_entry.parse(path)
            except:
                return standard_linux_file_manager_for_desktop()

            fm = desktop_entry.getExec()

            # Strip away any extraneous arguments
            fm_cmd = fm.split()[0]
            # Strip away any path information
            fm_cmd = os.path.split(fm_cmd)[1]
            # Strip away any quotes
            fm_cmd = fm_cmd.replace('"', '')
            fm_cmd = fm_cmd.replace("'", '')

            if force_standard and _linux_desktop != LinuxDesktop.unknown:
                try:
                    standard = StandardLinuxFileManager[_linux_desktop.name]
                except KeyError:
                    return standard_linux_file_manager_for_desktop()
                else:
                    if standard != fm_cmd:
                        return standard_linux_file_manager_for_desktop()

            # Nonexistent file managers
            if shutil.which(fm_cmd) is None:
                return standard_linux_file_manager_for_desktop()

            try:
                file_manager_type = LinuxFileManagerBehavior[fm_cmd]
            except KeyError:
                file_manager_type = FileManagerType.regular

            return fm_cmd, file_manager_type

    # Special case: no base dirs set, e.g. LXQt
    return standard_linux_file_manager_for_desktop()


def probe_system_file_manager(force_standard: bool = False) -> None:
    """
    Determine file manager used in this operating system.

    On Windows, this will always be explorer.exe.

    :param force_standard: if file manager does not match expectations for current desktop environment or platform,
    return the standard file manager. The file manager will always exist, regardless.
    :return: file manager command, and what type of mechanism it provides for selecting files
    """

    global _default_file_manager_probed
    global _default_file_manager
    global _default_file_manager_type

    if not _default_file_manager_probed:
        system = platform.system()
        if system == 'Windows':
            _default_file_manager = 'explorer.exe'
            _default_file_manager_type = FileManagerType.win_select
            assert shutil.which(_default_file_manager) is not None
            _default_file_manager_probed = True

        elif system == 'Linux':
            _default_file_manager, _default_file_manager_type = \
                determine_linux_file_manager(force_standard=force_standard)
            _default_file_manager_probed = True
        elif system == 'Darwin':
            raise NotImplementedError
        else:
            raise NotImplementedError


def show_in_file_manager(path_or_uri: Optional[Union[str, Sequence]] = None) -> None:
    """
    Open the system file manager and display optional directory or items in the  directory.

    :param path_or_uri: zero or more files or directories to open, specified as a single URI
     or valid path, or a sequence of URIs/paths.
    """

    if not _default_file_manager_probed:
        probe_system_file_manager()

    if _default_file_manager is None:
        raise Exception("A file manager could not be determined")

    if path_or_uri is None:
        arg = ''
        uris = ''
    else:
        if isinstance(path_or_uri, str):
            path_or_uri = path_or_uri,

        uris = ''
        for pu in path_or_uri:
            # Were we passed a URI or simple path?
            parse_result = urllib.parse.urlparse(pu)
            if parse_result.scheme:
                uri = pu
            else:
                # Convert the path to a URI
                uri = pathlib.Path(os.path.abspath(pu)).as_uri()
                parse_result = None

            if _default_file_manager_type == FileManagerType.dir_only_uri:
                # Show only the directory; do not attempt to select the file
                if parse_result is None:
                    parse_result = urllib.parse.urlparse(uri)
                uri = urllib.parse.urlunparse(parse_result._replace(path=os.path.dirname(parse_result.path)))

            uris = '{} {}'.format(uris, uri)

        arg = ''
        if _default_file_manager_type == FileManagerType.select:
            arg = '--select '
        elif _default_file_manager_type == FileManagerType.show_item:
            arg = '--show-item '
        elif _default_file_manager_type == FileManagerType.show_items:
            arg = '--show-items '
        elif _default_file_manager_type == FileManagerType.win_select:
            arg = '/select,'

    if _default_file_manager in ('explorer.exe', 'pcmanfm'):
        uris = uris.split() or ['']
    else:
        uris = [uris]

    for u in uris:
        cmd = '{} {}{}'.format(_default_file_manager, arg, u)
        if platform.system() != "Windows":
            args = shlex.split(cmd)
        else:
            args = cmd
        subprocess.Popen(args)


def parser_options(formatter_class=argparse.HelpFormatter):
    parser = argparse.ArgumentParser(
        prog=__title__, description=__summary__, formatter_class=formatter_class
    )

    parser.add_argument(
        '--version', action='version', version='%(prog)s {}'.format(__version__)
    )

    parser.add_argument('path', nargs='*')

    return parser


if __name__ == '__main__':
    parser = parser_options()

    args = parser.parse_args()

    show_in_file_manager(path_or_uri=args.path)
