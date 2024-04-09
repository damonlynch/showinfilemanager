# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch
# SPDX-License-Identifier: MIT

"""
Show in File Manager

Open the system file manager and optionally select files in it.
"""

import shutil
import sys
from typing import Optional, Sequence, Union

import showinfm.filemanager
from showinfm.argumentsparse import get_parser
from showinfm.constants import Platform
from showinfm.system import current_platform, is_wsl, is_wsl1, is_wsl2, linux, windows

_file_manager = showinfm.filemanager.FileManager()


def stock_file_manager() -> str:
    """
    Get stock file manager for this operating system / desktop.

    On Windows the default is `explorer.exe`. On Linux the first step
    is to determine which desktop is running, and from that lookup its
    default file manager. On macOS, the default is finder, accessed
    via the command 'open'.

    Exceptions are not caught.

    :return: executable name
    """

    if current_platform == Platform.windows or is_wsl1:
        file_manager = "explorer.exe"
    elif current_platform == Platform.linux:
        file_manager = linux.stock_linux_file_manager()
    elif current_platform == Platform.macos:
        file_manager = "open"
    else:
        raise NotImplementedError

    assert shutil.which(file_manager) is not None
    return file_manager


def user_file_manager() -> str:
    """
    Get the file manager as set by the user.

    The file manager executable is tested to see if it exists.

    Exceptions are not caught.

    :return: executable name
    """

    if current_platform == Platform.windows or is_wsl1:
        file_manager = "explorer.exe"
    elif current_platform == Platform.linux:
        file_manager = linux.user_linux_file_manager()
    elif current_platform == Platform.macos:
        file_manager = "open"
    else:
        raise NotImplementedError

    assert shutil.which(file_manager) is not None
    return file_manager


def valid_file_manager() -> str:
    """
    Get user's file manager, falling back to using sensible defaults.

    The user's choice of file manager is the default choice. However, this is
    not always set correctly. On Linux, it most likely is because the user's
    distro has not correctly set the default file manager. If the user's choice
    is unrecognized by this package, then reject it and choose the standard file
    manager for the detected desktop environment.

    All exceptions are caught, except those if this platform is not supported by
    this package.

    :return: If the user's default file manager is set and it is recognized
     as valid by this package, then return it. Otherwise return the stock file
     manager, if it exists.
    """

    return showinfm.filemanager.valid_file_manager()


def show_in_file_manager(
    path_or_uri: Optional[Union[str, Sequence[str]]] = None,
    open_not_select_directory: bool = True,
    file_manager: Optional[str] = None,
    allow_conversion: bool = True,
    verbose: bool = False,
    debug: bool = False,
) -> None:
    """
    Open the file manager and show zero or more directories or files in it.

    The path_or_uri is a sequence of items, or a single item. An item can
    be a regular path, or a URI.

    On non-Windows platforms, regular paths will be converted to URIs when
    passed as command line arguments to the file manager, because some file
    managers do not handle regular paths correctly. However, URIs will be
    convereted to paths to handle file managers that do not accept URIs.

    On Windows, Explorer is called using the Win32 API.

    On WSL1, all paths are opened using Windows Explorer. URIs can be
    specified using Linux or Windows formats. All formats are automatically
    converted to use the Windows URI format.

    WSL2 functions the same as WSL1, except if the WSL2 instance has a Linux
    file manager installed. On these systems, if a path on Linux is
    specified, that file manager will be used instead of Windows Explorer.
    Override this default behavior by using the parameter file_manager.

    The most common use of this function is to call it without specifying
    the file manager to use, which defaults to the value returned by
    valid_file_manager()

    For file managers unable to select files to display, the file manager
    will instead display the contents of the path.

    For file managers that can handle file selections, but only one at a time,
    multiple file manager windows will be opened.

    If a file manager executable is specified and this package does not
    recognize it, the executable will be called with the files as the only command
    line arguments.

    :param path_or_uri: zero or more files or directories to open, specified
     as a single URI or valid path, or a sequence of URIs/paths.
    :param open_not_select_directory: if the URI or path is a directory and
     not a file, open the directory itself in the file manager, rather than
     selecting it and displaying it in its parent directory.
    :param file_manager: executable name to use. If not specified, then
     valid_file_manager() will determine which file manager to use.
    :param allow_conversion: allow this function to automatically convert paths
     and URIs to the format needed by the file manager that will be called. Set
     to False if passing non-standard URIs. Ignored when running under WSL.
    :param verbose: if True print command to be executed before launching
     it
    :param debug: if True print debugging information to stderr
    """

    global _file_manager

    _file_manager.show_in_file_manager(
        path_or_uri,
        open_not_select_directory,
        file_manager,
        allow_conversion,
        verbose,
        debug,
    )


class Diagnostics:
    """
    Collect basic diagnostics information for this package.
    """

    def __init__(self) -> None:
        self.desktop: Optional[linux.LinuxDesktop]
        self.wsl_version: str

        try:
            self.stock_file_manager = stock_file_manager()
        except Exception as e:
            self.stock_file_manager = str(e)
        try:
            self.user_file_manager = user_file_manager()
        except Exception as e:
            self.user_file_manager = str(e)
        try:
            self.valid_file_manager = valid_file_manager()
        except Exception as e:
            self.valid_file_manager = str(e)

        if current_platform == Platform.linux:
            try:
                self.desktop = linux.linux_desktop()
            except Exception:
                self.desktop = linux.LinuxDesktop.unknown
        else:
            self.desktop = None

        if is_wsl:
            if is_wsl2:
                self.wsl_version = "2"
            else:
                self.wsl_version = "1"
        else:
            self.wsl_version = ""

    def __str__(self) -> str:
        desktop = f"Linux Desktop: {self.desktop.name}\n" if self.desktop else ""
        wsl = f"WSL version {self.wsl_version}\n" if self.wsl_version else ""
        file_managers = (
            f"Stock: {self.stock_file_manager}\n"
            f"User's choice: {self.user_file_manager}\n"
            f"Valid: {self.valid_file_manager}"
        )
        return desktop + wsl + file_managers


def main() -> None:
    parser = get_parser()

    args = parser.parse_args()

    verbose = args.verbose
    debug = args.debug
    if debug:
        print(Diagnostics())
        verbose = True

    if current_platform == Platform.windows and not is_wsl:
        path_or_uri = windows.parse_command_line_arguments(args.path)
    else:
        path_or_uri = args.path

    open_not_select_directory = not args.select_folder

    try:
        show_in_file_manager(
            file_manager=args.file_manager,
            path_or_uri=path_or_uri,
            verbose=verbose,
            open_not_select_directory=open_not_select_directory,
            debug=debug,
        )
    except Exception as e:
        sys.stderr.write(str(e))
        if args.debug:
            raise
