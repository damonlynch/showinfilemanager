# Copyright (c) 2016-2021 Damon Lynch
# SPDX - License - Identifier: MIT

"""
Show in File Manager

Open the system file manager and optionally select files in it.
"""

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2016-2021, Damon Lynch"

import argparse
import os
import pathlib
import platform
import shlex
import shutil
import subprocess
from typing import Optional, Union, Sequence
import urllib.parse


from . import __about__
from .constants import FileManagerType, Platform
from .system import current_platform
from .system import linux

_valid_file_manager_probed = False
_valid_file_manager = None
_valid_file_manager_type = None


def get_stock_file_manager() -> str:
    """
    Get stock file manager for this operating system / desktop.

    Exceptions are not caught.

    :return: executable name
    """

    if current_platform == Platform.windows:
        file_manager = 'explorer.exe'
    elif current_platform == Platform.linux:
        file_manager = linux.get_stock_linux_file_manager()
    else:
        raise NotImplementedError

    assert shutil.which(file_manager) is not None
    return file_manager


def get_user_file_manager() -> str:
    """
    Get the file manager as set by the user.

    The file manager executable is tested to see if it exists.

    Exceptions are not caught.

    :return: executable name
    """

    if current_platform == Platform.windows:
        file_manager = 'explorer.exe'
    elif current_platform == Platform.linux:
        file_manager = linux.get_user_linux_file_manager()
    else:
        raise NotImplementedError

    assert shutil.which(file_manager) is not None
    return file_manager


def get_valid_file_manager() -> str:
    """
    Get user's file manager, falling back to using sensible defaults for the desktop / OS.

    The user's choice of file manager is the default choice. However, this is not always
    set correctly, most likely because the user's distro has not correctly set the default
    file manager. If the user's choice is unrecognized by this package, then reject it and
    choose the standard file manager for the detected desktop environment.

    All exceptions are caught, except those if this platform is not supported by this package.

    :return: If the user's default file manager is set and it is known by this package, then
    return it. Otherwise return the stock file manager, if it exists.
    """

    if current_platform == Platform.windows:
        file_manager = 'explorer.exe'
    elif current_platform == Platform.linux:
        file_manager = linux.get_valid_linux_file_manager()
    else:
        raise NotImplementedError
    return file_manager


def show_in_file_manager(path_or_uri: Optional[Union[str, Sequence[str]]] = None,
                         file_manager: Optional[str] = None) -> None:
    """
    Open the system file manager and display an optional directory, or items in the  directory.

    If there is no valid file manager found on the system, do nothing. A valid file manager
    is a file manager this package knows about.

    :param path_or_uri: zero or more files or directories to open, specified as a single URI
     or valid path, or a sequence of URIs/paths.
    :param file_manager: executable name to use. If not specified, then get_valid_file_manager()
     will determine which file manager to use.
    """

    global _valid_file_manager
    global _valid_file_manager_type

    if not file_manager:
        _set_valid_file_manager()
        file_manager = _valid_file_manager

    if not file_manager:
        return

    if not path_or_uri:
        arg = ''
        uris = ''
    else:
        if isinstance(path_or_uri, str):
            # turn the single path / URI into a Tuple
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

            if _valid_file_manager_type == FileManagerType.dir_only_uri:
                # Show only the directory; do not attempt to select the file
                if parse_result is None:
                    parse_result = urllib.parse.urlparse(uri)
                uri = urllib.parse.urlunparse(parse_result._replace(path=os.path.dirname(parse_result.path)))

            uris = '{} {}'.format(uris, uri)

        arg = ''
        if _valid_file_manager_type == FileManagerType.win_select:
            arg = '/select,'  # no trailing space is necessary on Windows
        elif _valid_file_manager_type == FileManagerType.select:
            arg = '--select '  # trailing space is necessary for this and subsequent entries
        elif _valid_file_manager_type == FileManagerType.show_item:
            arg = '--show-item '
        elif _valid_file_manager_type == FileManagerType.show_items:
            arg = '--show-items '

    # Some file managers must be passed only one or zero paths / URIs
    if file_manager in ('explorer.exe', 'pcmanfm'):
        uris = uris.split() or ['']
    else:
        uris = [uris]

    for u in uris:
        cmd = '{} {}{}'.format(file_manager, arg, u)
        print("Executing", cmd)
        # Do not check current_platform here, it makes no sense
        if platform.system() != "Windows":
            args = shlex.split(cmd)
        else:
            args = cmd
        subprocess.Popen(args)


def _set_valid_file_manager() -> None:
    """
    Set module level global variables to set a valid file manager for this user in this desktop environment.
    """

    global _valid_file_manager_probed
    global _valid_file_manager
    global _valid_file_manager_type

    if not _valid_file_manager_probed:
        fm = get_valid_file_manager()
        if fm:
            _valid_file_manager = fm
            if current_platform == Platform.windows:
                _valid_file_manager_type = FileManagerType.win_select
            elif current_platform == Platform.linux:
                _valid_file_manager_type = linux.get_linux_file_manager_type(fm)
            else:
                raise NotImplementedError
        _valid_file_manager_probed = True


class Diagnostics:
    """
    Collect basic diagnostics information for this package.
    """

    def __init__(self) -> None:
        try:
            self.stock_file_manager = get_stock_file_manager()
        except Exception as e:
            self.stock_file_manager = str(e)
        try:
            self.user_file_manager = get_user_file_manager()
        except Exception as e:
            self.user_file_manager = str(e)
        try:
            self.valid_file_manager = get_valid_file_manager()
        except Exception as e:
            self.valid_file_manager = str(e)

        if current_platform == Platform.linux:
            try:
                self.desktop = linux.get_linux_desktop()
            except:
                self.desktop = linux.LinuxDesktop.unknown
        else:
            self.desktop = ''

    def __str__(self) -> str:
        desktop = "Linux Desktop: {}\n".format(self.desktop.name) if self.desktop else ""
        file_managers = "Stock: {}\nUser's choice: {}\nValid: {}".format(
                    self.stock_file_manager,
                    self.user_file_manager,
                    self.valid_file_manager
        )
        return desktop + file_managers


def parser_options(formatter_class=argparse.HelpFormatter):
    """
    Parse command line options for this script

    :param formatter_class: one of 4 argparse formatting classes
    :return: argparse.ArgumentParser
    """

    parser = argparse.ArgumentParser(
        prog=__about__.__title__, description=__about__.__summary__, formatter_class=formatter_class
    )

    parser.add_argument(
        '--version', action='version', version='%(prog)s {}'.format(__about__.__version__)
    )

    parser.add_argument('--verbose', action='store_true')

    parser.add_argument('path', nargs='*')

    return parser


def main() -> None:
    parser = parser_options()

    args = parser.parse_args()

    if args.verbose or __about__.__version__ < '0.1.0':
        print(Diagnostics())

    show_in_file_manager(path_or_uri=args.path)


