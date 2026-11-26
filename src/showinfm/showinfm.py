#  SPDX-FileCopyrightText: 2016-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

"""
Show in File Manager

Open the system file manager and optionally select files in it.
"""

import shutil
import sys

import showinfm.filemanager
from showinfm.argumentsparse import get_parser
from showinfm.constants import Platform
from showinfm.exceptions import WindowsShellUnavailableError
from showinfm.filemanager import PathOrUri
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
    path_or_uri: PathOrUri | None = None,
    open_not_select_directory: bool = True,
    file_manager: str | None = None,
    allow_conversion: bool = True,
    verbose: bool = False,
    debug: bool = False,
) -> None:
    """
    Open the file manager and show zero or more directories or files in it.

    The path_or_uri is a sequence of items, or a single item. An item can
    be a regular path, a URI, or any object implementing os.PathLike, such
    as a pathlib.Path.

    On non-Windows platforms, regular paths will be converted to URIs when
    passed as command line arguments to the file manager, because some file
    managers do not handle regular paths correctly. However, a file: URI will
    be converted to a path to handle file managers that do not accept URIs.
    On Windows an smb:// URI becomes the UNC path for the same share, since
    Windows has no handler for that scheme, and the same happens under WSL when
    the file manager is explorer.exe. Any other scheme is passed along as it
    stands: no path names what such a URI points at, and rewriting one opens
    somewhere the caller never asked for.

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
     as a single URI, valid path or os.PathLike, or a sequence of those.
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
    :raises WindowsShellUnavailableError: if files are to be selected in Windows
     Explorer on this system and win32com.shell is not available
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
        self.desktop: linux.LinuxDesktop | None
        self.wsl_version: str
        self.windows_shell_status: str | None

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

        # Only reported on Windows, where the Win32 shell API is what selects
        # files in Explorer. Elsewhere it is never imported, so there is
        # nothing useful to report.
        if current_platform == Platform.windows:
            self.windows_shell_status = windows.windows_shell_status()
        else:
            self.windows_shell_status = None

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
        win_shell = (
            f"Windows shell: {self.windows_shell_status}\n"
            if self.windows_shell_status
            else ""
        )
        file_managers = (
            f"Stock: {self.stock_file_manager}\n"
            f"User's choice: {self.user_file_manager}\n"
            f"Valid: {self.valid_file_manager}"
        )
        return desktop + wsl + win_shell + file_managers


def main() -> None:
    parser = get_parser()

    args = parser.parse_args()

    verbose = args.verbose
    debug = args.debug
    if debug:
        print(Diagnostics())
        verbose = True

    open_not_select_directory = not args.select_folder

    try:
        if current_platform == Platform.windows and not is_wsl:
            # The raw arguments are globbed and normalised here, before anything is
            # launched, so this belongs inside the handler below: what the parser
            # cannot make of an argument should reach the user as its message rather
            # than as a traceback, the same promise every other failure here makes.
            path_or_uri = windows.parse_command_line_arguments(args.path, debug=debug)
        else:
            path_or_uri = args.path

        show_in_file_manager(
            file_manager=args.file_manager,
            path_or_uri=path_or_uri,
            verbose=verbose,
            open_not_select_directory=open_not_select_directory,
            debug=debug,
        )
    except WindowsShellUnavailableError as e:
        # Aborting with the remediation steps is the point of this error, so it
        # is reported on its own rather than as an unhandled exception.
        sys.stderr.write(f"{e}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(str(e))
        if args.debug:
            raise
