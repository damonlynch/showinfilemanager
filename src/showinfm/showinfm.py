# Copyright (c) 2016-2021 Damon Lynch
# SPDX - License - Identifier: MIT

"""
Show in File Manager

Open the system file manager and optionally select files in it.
"""

import argparse
try:
    import importlib.metadata as importlib_metadata
except ImportError:
    import importlib_metadata
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
from typing import Optional, Union, Sequence, List
import urllib.parse


from .constants import FileManagerType, Platform, single_file_only, cannot_open_uris
from .system import current_platform, is_wsl, is_wsl2, is_wsl1
from .system import linux, tools, windows

_valid_file_manager_probed = False
_valid_file_manager = None
_valid_file_manager_type = None


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

    if current_platform == Platform.windows or is_wsl1:
        file_manager = "explorer.exe"
    elif current_platform == Platform.linux:
        file_manager = linux.valid_linux_file_manager()
    elif current_platform == Platform.macos:
        file_manager = "open"
    else:
        raise NotImplementedError
    return file_manager


def show_in_file_manager(
    path_or_uri: Optional[Union[str, Sequence[str]]] = None,
    open_not_select_directory: Optional[bool] = True,
    file_manager: Optional[str] = None,
    allow_conversion: bool = True,
    verbose: bool = False,
    debug: bool = False,
) -> None:
    """
    Open the file manager and show zero or more directories or files in it.

    The path_or_uri is a sequence of items, or a single item. An item can
    be regular path, or a URI.

    On non-Windows platforms, regular paths will be converted to URIs when
    passed as command line arguments to the file manager, because some file
    managers do not handle regular paths correctly. However, URIs will be
    convereted to paths to handle file managers that do not accepts URIs.

    On Windows, Explorer is called using the Win32 API.

    On WSL1, all paths are opened using Windows Explorer. URIs and can be
    specified using Linux or Windows formats. All formats are automatically
    converted to use the Windows URI format.

    WSL2 functions the same as WSL1, except if the WSL2 instance has a Linux
    file manager installed. On these systems, if a path on Linux is
    specified, that file manager will be used instead of Windows Explorer. You
    can override this default behavior by using the parameter file_manager.

    The most common use of this function is to call it without specifying
    the file manager to use, which defaults to the value returned by
    valid_file_manager()

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
     valid_file_manager() will determine which file manager to use.
    :param allow_conversion: allow this function to automatically convert paths
     and URIs to the format needed by the file manager that will be called. Set
     to False if passing non-standard URIs. Ignored when running under WSL.
    :param verbose: if True print command to be executed before launching
     it
    :param debug: if True print debugging information to stderr
    """

    global _valid_file_manager
    global _valid_file_manager_type

    file_manager_specified = file_manager is not None

    if not file_manager:
        _set_valid_file_manager()
        file_manager_type = _valid_file_manager_type
        file_manager = _valid_file_manager
    else:
        try:
            file_manager_type = _file_manager_type(file_manager)
        except:
            file_manager_type = None

    if not (file_manager or is_wsl2):
        # We are not running WSL2 and there is no file manager: there is nothing
        # to be done
        return

    # Used for directories when open_not_select_directory is True
    directories = []
    # Used for paths that will be opened in Windows explorer called from WSL2
    wsl_windows_paths = []
    wsl_windows_directories = []

    if not path_or_uri:
        if current_platform == Platform.macos:
            # macOS finder requires a path to be able to launch it from the command line
            path_or_uri = "file:///"
        else:
            arg = ""
            uris_and_paths = []
    if path_or_uri:
        if isinstance(path_or_uri, str):
            # turn the single path / URI into a Tuple
            path_or_uri = (path_or_uri,)

        uris_and_paths = []
        for pu in path_or_uri:
            # Were we passed a URI or simple path?
            if pu:
                uri = path = ""
                # target_platform = current_platform
                if is_wsl:
                    # Running WSL1 or WSL2. Is the path on the Windows file system, or
                    # alternately is Windows explorer going to be used to view the
                    # files? Also, what kind of path or URI has been passed?
                    require_win_path = file_manager == "explorer.exe"
                    wsl_details = linux.wsl_transform_path_uri(pu, require_win_path)
                    if not wsl_details.exists:
                        continue
                    use_windows_explorer_via_wsl = (
                        wsl_details.is_win_location and not file_manager_specified
                    ) or file_manager == "explorer.exe"
                    if use_windows_explorer_via_wsl:
                        if debug:
                            print(
                                f"Converted '{pu}' to '{wsl_details.win_uri}'",
                                file=sys.stderr,
                            )
                        if not (wsl_details.is_dir and open_not_select_directory):
                            wsl_windows_paths.append(wsl_details.win_uri)
                        else:
                            wsl_windows_directories.append(wsl_details.win_uri)
                        continue
                    else:
                        if tools.filemanager_requires_path(file_manager=file_manager):
                            path = Path(wsl_details.linux_path).resolve()
                            uri = None
                        else:
                            path = None
                            uri = Path(wsl_details.linux_path).resolve().as_uri()
                else:
                    if tools.is_uri(pu):
                        if (
                            tools.filemanager_requires_path(file_manager=file_manager)
                            and allow_conversion
                        ):
                            # Convert URI to regular path
                            uri = None
                            path = Path(path or tools.file_uri_to_path(pu))
                        else:
                            uri = pu
                            path = None
                    else:
                        if (
                            tools.filemanager_requires_path(file_manager=file_manager)
                            or not allow_conversion
                        ):
                            path = Path(pu)
                            uri = None
                        else:
                            uri = Path(pu).resolve().as_uri()
                            path = None

                if file_manager_type == FileManagerType.dir_only_uri:
                    assert current_platform != Platform.windows
                    # Show only the directory: do not attempt to select the file,
                    # because the file manager cannot handle it.
                    if uri:
                        # Do not use tools.file_url_to_path() here, because we need the
                        # parse_result, and file_url_to_path() assumes file:// URIs.
                        # In any case, this code block is not run under Windows, so
                        # there is no need to use tools.file_url_to_path() to handle the
                        # file:/// case that urllib.parse.urlparse fails with.
                        parse_result = urllib.parse.urlparse(uri)
                        path = Path(parse_result.path)

                    if not (path.is_dir() and open_not_select_directory):
                        path = path.parent
                    if uri:
                        uri = urllib.parse.urlunparse(
                            parse_result._replace(path=str(path))
                        )
                    else:
                        path = tools.quote_path(path=path)
                    uris_and_paths.append(uri or str(path))
                else:
                    # whether to open the directory, or
                    # select it (depends on file manager capabilities and option
                    # open_not_select_directory):
                    open_directory = False

                    if (
                        open_not_select_directory
                        and file_manager_type != FileManagerType.dual_panel
                        or file_manager_type == FileManagerType.regular
                    ):
                        if uri:
                            path = tools.file_uri_to_path(uri=uri)
                            path = Path(path)
                            open_directory = path.is_dir()
                        else:
                            open_directory = path.is_dir()
                        if open_directory:
                            if (
                                file_manager_type == FileManagerType.regular
                                and not open_not_select_directory
                            ):
                                # This type of file manger cannot select directories,
                                # because it provides no mechanism
                                # to distinguish between selecting and opening a
                                # directory.
                                # So open the parent instead.
                                path = path.parent
                                if uri:
                                    uri = path.as_uri()
                            if uri is None:
                                path = tools.quote_path(path=path)
                            directories.append(uri or str(path))
                    if not open_directory:
                        if uri is None and file_manager != "explorer.exe":
                            path = tools.quote_path(path=path)
                        uris_and_paths.append(uri or str(path))

        arg = ""
        if file_manager_type == FileManagerType.win_select:
            arg = "/select,"  # no trailing space is necessary on Windows
        elif file_manager_type == FileManagerType.select:
            arg = "--select "  # trailing space is necessary
        elif file_manager_type == FileManagerType.show_item:
            arg = "--show-item "  # trailing space is necessary
        elif file_manager_type == FileManagerType.show_items:
            arg = "--show-items "  # trailing space is necessary
        elif file_manager_type == FileManagerType.reveal:
            arg = "--reveal "  # trailing space is necessary

    if (
        current_platform == Platform.windows
        and not is_wsl
        and file_manager == "explorer.exe"
    ):
        if uris_and_paths:
            windows.launch_file_explorer(uris_and_paths, verbose)
        for d in directories:
            if verbose:
                print("Executing Windows shell to open", d)
            os.startfile(d)
    else:
        if uris_and_paths:
            # Some file managers must be passed only one or zero paths / URIs
            if file_manager not in single_file_only:
                uris_and_paths = [" ".join(uris_and_paths)]

            _launch_file_manager(
                uris_or_paths=uris_and_paths,
                arg=arg,
                file_manager=file_manager,
                verbose=verbose,
            )
        if directories:
            if file_manager not in single_file_only:
                directories = [" ".join(directories)]
            _launch_file_manager(
                uris_or_paths=directories,
                arg="",
                file_manager=file_manager,
                verbose=verbose,
            )
        if wsl_windows_paths:
            _launch_file_manager(
                uris_or_paths=wsl_windows_paths,
                arg="/select,",
                file_manager="explorer.exe",
                verbose=verbose,
            )
        if wsl_windows_directories:
            _launch_file_manager(
                uris_or_paths=wsl_windows_directories,
                arg="",
                file_manager="explorer.exe",
                verbose=verbose,
            )

    if (
        not uris_and_paths
        and not directories
        and not wsl_windows_paths
        and not wsl_windows_directories
    ):
        _launch_file_manager(
            uris_or_paths=[""],
            arg="",
            file_manager=file_manager,
            verbose=verbose,
        )


def _launch_file_manager(
    uris_or_paths: List[str], arg: str, file_manager: str, verbose: bool
) -> None:
    """
    Launch the file manager

    :param uris_or_paths: list of URIs, or a list of a single empty string
    :param arg: arg to pass the file manager
    :param file_manager: file manager executable name
    :param verbose: if True print command to be executed before launching
     it
    """

    for u in uris_or_paths:
        cmd = "{} {}{}".format(file_manager, arg, u)
        if verbose:
            print("Executing", cmd)
        # Do not check current_platform here, it makes no sense
        if platform.system() != "Windows":
            args = shlex.split(cmd)
        else:
            args = cmd
        proc = subprocess.Popen(args)
        if is_wsl2 and file_manager == "explorer.exe":
            proc.wait()


def _file_manager_type(fm: str) -> FileManagerType:
    """
    Determine file manager type via the executable name
    :param fm: executable name
    :return:
    """

    if current_platform == Platform.windows or is_wsl1:
        return windows.windows_file_manager_type(fm)
    elif current_platform == Platform.linux:
        return linux.linux_file_manager_type(fm)
    elif current_platform == Platform.macos:
        return FileManagerType.reveal
    else:
        raise NotImplementedError


def _set_valid_file_manager() -> None:
    """
    Set module level global variables to set a valid file manager for this user in this
    desktop environment.
    """

    global _valid_file_manager_probed
    global _valid_file_manager
    global _valid_file_manager_type

    if not _valid_file_manager_probed:
        fm = valid_file_manager()
        if fm:
            _valid_file_manager = fm
            _valid_file_manager_type = _file_manager_type(fm)
        _valid_file_manager_probed = True


class Diagnostics:
    """
    Collect basic diagnostics information for this package.
    """

    def __init__(self) -> None:
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
            except:
                self.desktop = linux.LinuxDesktop.unknown
        else:
            self.desktop = ""

        if is_wsl:
            if is_wsl2:
                self.wsl_version = "2"
            else:
                self.wsl_version = "1"
        else:
            self.wsl_version = ""

    def __str__(self) -> str:
        desktop = (
            "Linux Desktop: {}\n".format(self.desktop.name) if self.desktop else ""
        )
        wsl = "WSL version {}\n".format(self.wsl_version) if self.wsl_version else ""
        file_managers = "Stock: {}\nUser's choice: {}\nValid: {}".format(
            self.stock_file_manager, self.user_file_manager, self.valid_file_manager
        )
        return desktop + wsl + file_managers


def package_metadata():
    """
    Get Python package metadata

    :return: version number and package summary
    """

    try:
        version = importlib_metadata.version("show-in-file-manager")
    except:
        version = "Unknown version"
        summary = (
            "Platform independent Python module to open the system file manager "
            "and optionally select files in it "
        )

    else:
        metadata = importlib_metadata.metadata("show-in-file-manager")
        summary = metadata["summary"]

    return version, summary


def parser_options(formatter_class=argparse.HelpFormatter):
    """
    Parse command line options for this script

    :param formatter_class: one of 4 argparse formatting classes
    :return: argparse.ArgumentParser
    """

    version, summary = package_metadata()

    parser = argparse.ArgumentParser(
        prog="showinfilemanager", description=summary, formatter_class=formatter_class
    )

    parser.add_argument(
        "--version", action="version", version="%(prog)s {}".format(version)
    )

    parser.add_argument("-f", "--file-manager", help="file manager to run")

    parser.add_argument(
        "-s",
        "--select-folder",
        action="store_true",
        help="select folder instead of displaying its contents",
    )

    parser.add_argument(
        "--verbose", action="store_true", help="display command being run to stdout"
    )

    parser.add_argument(
        "--debug", action="store_true", help="output debugging information to stdout"
    )

    parser.add_argument(
        "path", nargs="*", help="zero or more URIs or paths of files or directories"
    )

    return parser


def main() -> None:
    parser = parser_options()

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
