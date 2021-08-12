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
from typing import Optional, Union, Sequence, List
import urllib.parse


from . import __about__
from .constants import FileManagerType, Platform, single_file_only
from .system import current_platform, is_wsl
from .system import linux, tools

_valid_file_manager_probed = False
_valid_file_manager = None
_valid_file_manager_type = None


def get_stock_file_manager() -> str:
    """
    Get stock file manager for this operating system / desktop.

    On Windows the default is `explorer.exe`. On Linux the first step
    is to determine which desktop is running, and from that lookup its
    default file manager. On macOS, the default is finder, accessed
    via the command 'open'.

    Exceptions are not caught.

    :return: executable name
    """

    if current_platform == Platform.windows:
        file_manager = 'explorer.exe'
    elif current_platform == Platform.linux:
        file_manager = linux.get_stock_linux_file_manager()
    elif current_platform == Platform.macos:
        file_manager = 'open'
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
    elif current_platform == Platform.macos:
        file_manager = 'open'
    else:
        raise NotImplementedError

    assert shutil.which(file_manager) is not None
    return file_manager


def get_valid_file_manager() -> str:
    """
    Get user's file manager, falling back to using sensible defaults for the desktop / OS.

    The user's choice of file manager is the default choice. However, this is not always
    set correctly. On Linux, it most likely is because the user's distro has not correctly
    set the default file manager. If the user's choice is unrecognized by this package,
    then reject it and choose the standard file manager for the detected desktop
    environment.

    All exceptions are caught, except those if this platform is not supported by this package.

    :return: If the user's default file manager is set and it is known by this package, then
    return it. Otherwise return the stock file manager, if it exists.
    """

    if current_platform == Platform.windows:
        file_manager = 'explorer.exe'
    elif current_platform == Platform.linux:
        file_manager = linux.get_valid_linux_file_manager()
    elif current_platform == Platform.macos:
        file_manager = 'open'
    else:
        raise NotImplementedError
    return file_manager


def show_in_file_manager(path_or_uri: Optional[Union[str, Sequence[str]]] = None,
                         open_not_select_directory: Optional[bool] = True,
                         file_manager: Optional[str] = None) -> None:
    """
    Open the file manager and show zero or more directories or files in it.

    The path_or_uri is a sequence of items, or a single item. An item can
    be regular path, or a URI.

    On non-Windows platforms, regular paths will be converted to URIs
    when passed as command line arguments to the file manager, because
    some file mangers do not handle regular paths correctly.

    On Windows or WSL, regular paths are not converted to URIs, but they
    are quoted.

    The most common use of this function is to call it without specifying
    the file manager to use, which defaults to the value returned by
    get_valid_file_manager()

    For file managers unable to select files to display, the file manager
    will instead display the contents of the path.

    For file managers that can handle file selections, but only one at time,
    multiple file manager windows will be opened.

    If you specify a file manager executable and this package does not
    recognize it, it will be called with the files as the only command line
    arguments.

    :param path_or_uri: zero or more files or directories to open, specified
     as a single URI or valid path, or a sequence of URIs/paths.
    :param open_not_select_directory: if the URI or path is a directory and
     not a file, open the directory itself in the file manager, rather than
     selecting it and displaying it in its parent directory.
    :param file_manager: executable name to use. If not specified, then
     get_valid_file_manager() will determine which file manager to use.
    """

    global _valid_file_manager
    global _valid_file_manager_type

    if not file_manager:
        _set_valid_file_manager()
        file_manager = _valid_file_manager

    if not file_manager:
        return

    directories = []  # Used for directories when open_not_select_directory is True

    if not path_or_uri:
        if current_platform == Platform.macos:
            # macOS finder requires a path to be able to launch it from the command line
            path_or_uri = 'file:///'
        else:
            arg = ''
            uris_and_paths = []
    if path_or_uri:
        if isinstance(path_or_uri, str):
            # turn the single path / URI into a Tuple
            path_or_uri = path_or_uri,

        uris_and_paths = []
        for pu in path_or_uri:
            # Were we passed a URI or simple path?
            if pu:
                if tools.is_uri(pu):
                    uri = pu
                    path = None
                else:
                    if current_platform == Platform.windows:
                        # Do not convert the path to a URI, as that can mess things up on WSL
                        path = pu
                        uri = None
                    else:
                        uri = pathlib.Path(os.path.abspath(pu)).as_uri()
                        path = None

                if _valid_file_manager_type == FileManagerType.dir_only_uri:
                    # Show only the directory; do not attempt to select the file
                    if uri:
                        parse_result = urllib.parse.urlparse(uri)
                        path = parse_result.path

                    path = os.path.dirname(path)
                    if uri:
                        uri = urllib.parse.urlunparse(parse_result._replace(path=path))
                    else:
                        path = tools.quote_path(path)

                    uris_and_paths.append(uri or path)
                else:
                    is_dir = False
                    if open_not_select_directory:
                        if uri:
                            parse_result = urllib.parse.urlparse(uri)
                            path = parse_result.path
                            is_dir = os.path.isdir(path)
                        elif is_wsl:
                            is_dir = linux.wsl_path_is_directory(path)
                        else:
                            is_dir = os.path.isdir(path)
                        if is_dir:
                            if uri is None:
                                path = tools.quote_path(path)
                            directories.append(uri or path)
                    if not is_dir:
                        if uri is None:
                            path = tools.quote_path(path)
                        uris_and_paths.append(uri or path)

        arg = ''
        if _valid_file_manager_type == FileManagerType.win_select:
            arg = '/select,'  # no trailing space is necessary on Windows
        elif _valid_file_manager_type == FileManagerType.select:
            arg = '--select '  # trailing space is necessary
        elif _valid_file_manager_type == FileManagerType.show_item:
            arg = '--show-item '  # trailing space is necessary
        elif _valid_file_manager_type == FileManagerType.show_items:
            arg = '--show-items '  # trailing space is necessary
        elif _valid_file_manager_type == FileManagerType.reveal:
            arg = '--reveal '  # trailing space is necessary

    if uris_and_paths:
        # Some file managers must be passed only one or zero paths / URIs
        if file_manager not in single_file_only:
            uris_and_paths = [' '.join(uris_and_paths)]

        _launch_file_manager(uris_or_paths=uris_and_paths, arg=arg, file_manager=file_manager)

    if directories:
        if file_manager not in single_file_only:
            directories = [' '.join(directories)]
        _launch_file_manager(uris_or_paths=directories, arg='', file_manager=file_manager)

    if not uris_and_paths and not directories:
        _launch_file_manager(uris_or_paths=[''], arg='', file_manager=file_manager)


def _launch_file_manager(uris_or_paths: List[str], arg: str, file_manager: str) -> None:
    """
    Launch the file manager

    :param uris_or_paths: list of URIs, or a list of a single empty string
    :param arg: arg to pass the file manager
    :param file_manager: file manager executable name
    """

    for u in uris_or_paths:
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
            elif current_platform == Platform.macos:
                _valid_file_manager_type = FileManagerType.reveal
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

    if args.verbose:  # or __about__.__version__ < '0.1.0':
        print(Diagnostics())

    show_in_file_manager(path_or_uri=args.path)


