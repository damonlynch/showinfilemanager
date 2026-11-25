#  SPDX-FileCopyrightText: 2016-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

import atexit
import os
import platform
import shlex
import subprocess
import sys
import urllib.parse
from collections.abc import Sequence
from os import PathLike, fspath
from pathlib import Path
from typing import NamedTuple

from showinfm.constants import FileManagerType, Platform, single_file_only
from showinfm.system import (
    current_platform,
    is_wsl,
    is_wsl1,
    is_wsl2,
    linux,
    tools,
    windows,
)

PathOrUri = str | os.PathLike[str] | Sequence[str | os.PathLike[str]]


class ProcessPathOrUri(NamedTuple):
    fully_processed: bool
    path: Path | None
    uri: str | None


# The file managers this package starts are not waited for: they must outlive the
# call, since opening a file manager and then blocking the caller would be useless.
#
# CPython reports a Popen finalised with no exit status noted as "still running", and
# it does so before checking, so the report describes an unread status rather than a
# running program. Reading the status is what keeps that honest, which is what the
# list below is for: each launch notes the status of the earlier ones, and the exit
# hook does the last one.
#
# A manager that is still running when the interpreter exits has no status to note,
# and no later launch to read one, so it would be reported on the way out however
# carefully the list is kept. That report is wrong for this package: it is the whole
# intention that the file manager outlives the call. So the finalizer is replaced with
# one that does nothing, for objects started here, and the subclass is built at launch
# rather than at import so that a scenario replacing subprocess.Popen still stands in
# for it. Nothing is detached and no status is invented: assigning None to __del__ is
# not the way to remove a finalizer, it makes CPython call None on the way out.
_PROCESSES: list[subprocess.Popen] = []

_NO_FINALIZER: dict[type, type] = {}


def _quiet_finalizer(self: subprocess.Popen) -> None:
    """Nothing to report: this child is meant to outlive us."""


def _start_process(args: str | list[str]) -> subprocess.Popen:
    """
    Start a file manager, with no finalizer to report it.

    Returns a process object of the same kind the current subprocess.Popen would
    give, but silent when it is collected: for a program expected to outlive this
    one the report is not about a mistake.
    """

    base = subprocess.Popen
    if getattr(base, "__del__", None) is None:
        # Nothing to turn off: a stand-in without a finalizer, so no subclass and
        # no reason to make one.
        return base(args)

    quiet = _NO_FINALIZER.get(base)
    if quiet is None:
        quiet = type("FireAndForgetParent", (base,), {"__del__": _quiet_finalizer})
        _NO_FINALIZER[base] = quiet
    return quiet(args)


def _reap_processes() -> None:
    """
    Note down the exit status of any started file manager that has finished.

    Called on each launch, so the list holds only the children still running, and
    at exit for the last one, which no later launch would otherwise report. With no
    finalizer to do it, this is the only thing that reads a status, so an object
    that never reaches the list is left unreaped for the life of this process.
    """

    for process in _PROCESSES:
        process.poll()
    _PROCESSES[:] = [p for p in _PROCESSES if p.returncode is None]


atexit.register(_reap_processes)


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


class FileManager:
    def __init__(self) -> None:
        self._valid_file_manager_probed: bool = False
        self._valid_file_manager: str | None = None
        self._valid_file_manager_type: FileManagerType | None = None

        self.file_manager: str | None
        self.file_manager_type: FileManagerType | None

        # Used for directories when open_not_select_directory is True
        self.directories: list[str]

        # Target locations
        self.locations: list[str]

        # Used for paths that will be opened in Windows explorer called from WSL2
        self.wsl_windows_paths: list[str]
        self.wsl_windows_directories: list[str]

        # Argument to pass to a file manager on the command line
        self.arg: str = ""

        # whether to print command to be executed before launching the file manager
        self.verbose: bool
        self.debug: bool

        self.file_manager_specified: bool
        self.open_not_select_directory: bool
        self.allow_conversion: bool

    def _launch_file_manager(self, uris_or_paths: list[str]) -> None:
        """
        Launch the file manager

        :param uris_or_paths: list of URIs, or a list of a single empty string
        """

        for u in uris_or_paths:
            cmd = f"{self.file_manager} {self.arg}{u}"
            if self.verbose:
                print("Executing", cmd)
            # Do not check current_platform here, it makes no sense
            args = shlex.split(cmd) if platform.system() != "Windows" else cmd
            proc = _start_process(args)
            # Registered before anything else can raise: with no finalizer, an
            # object that never reaches the list is never reaped either.
            _PROCESSES.append(proc)
            _reap_processes()
            if is_wsl2 and self.file_manager == "explorer.exe":
                # explorer.exe returns immediately under WSL2, and waiting is what
                # keeps its output from mangling the terminal.
                proc.wait()

    def _set_valid_file_manager(self) -> None:
        """
        Set class level global variables to set a valid file manager for this user
        in this desktop environment.
        """

        if not self._valid_file_manager_probed:
            fm = valid_file_manager()
            if fm:
                self._valid_file_manager = fm
                self._valid_file_manager_type = _file_manager_type(fm)
            self._valid_file_manager_probed = True

    def show_in_file_manager(
        self,
        path_or_uri: PathOrUri | None = None,
        open_not_select_directory: bool = True,
        file_manager: str | None = None,
        allow_conversion: bool = True,
        verbose: bool = False,
        debug: bool = False,
    ) -> None:
        self.file_manager = file_manager
        self.verbose = verbose
        self.debug = debug
        self.open_not_select_directory = open_not_select_directory
        self.allow_conversion = allow_conversion

        self.file_manager_specified = self.file_manager is not None

        if not self.file_manager:
            self._set_valid_file_manager()
            self.file_manager_type = self._valid_file_manager_type
            self.file_manager = self._valid_file_manager
        else:
            try:
                self.file_manager_type = _file_manager_type(self.file_manager)
            except Exception:
                self.file_manager_type = None

        if not self.file_manager:
            # There is no file manager -- there is nothing to be done
            return

        self.arg = ""
        self.locations = []
        self.directories = []

        # Set these WSL2 specific values even if not running it --
        # it makes the launch process simpler.
        self.wsl_windows_paths = []
        self.wsl_windows_directories = []

        if not path_or_uri and current_platform == Platform.macos:
            # macOS finder requires a path to be able to launch it from the
            # command line
            path_or_uri = "file:///"

        if path_or_uri:
            self._process_path_or_uri(path_or_uri)

        self._set_file_manager_argument()
        self._launch()

    def _process_path_or_uri_wsl(self, pu: str) -> ProcessPathOrUri:
        """
        Process the path or URI when running under WSL1 or WSL2.
        Is the path on the Windows file system, or
        alternately is Windows explorer going to be used to view the
        files? Also, what kind of path or URI has been passed?
        :param pu: path or URI to process
        :return: A tuple indicating whether the path or URI has been fully processed,
         and if not, a Path or URI to process further
        """

        require_win_path = self.file_manager == "explorer.exe"
        wsl_details = linux.wsl_transform_path_uri(pu, require_win_path)
        if not wsl_details.exists:
            if self.debug:
                print(f"Path does not exist: '{pu}'", file=sys.stderr)
            return ProcessPathOrUri(fully_processed=True, path=None, uri=None)
        use_windows_explorer_via_wsl = (
            wsl_details.is_win_location and not self.file_manager_specified
        ) or self.file_manager == "explorer.exe"
        if use_windows_explorer_via_wsl:
            if wsl_details.win_uri is None:
                if self.debug:
                    print(
                        f"Unable to convert '{pu}' into a Windows URI",
                        file=sys.stderr,
                    )
                return ProcessPathOrUri(fully_processed=True, path=None, uri=None)
            if self.debug:
                print(
                    f"Converted '{pu}' to '{wsl_details.win_uri}'",
                    file=sys.stderr,
                )
            if not (wsl_details.is_dir and self.open_not_select_directory):
                self.wsl_windows_paths.append(wsl_details.win_uri)
            else:
                self.wsl_windows_directories.append(wsl_details.win_uri)
            return ProcessPathOrUri(fully_processed=True, path=None, uri=None)
        else:
            if wsl_details.linux_path is None and tools.is_smb_uri(pu):
                # A share URI this route deliberately left alone: the Linux file
                # managers open this scheme themselves, exactly as they do when
                # not running under WSL. The spaces are encoded because this
                # string goes into a command line, where a raw one would split
                # the URI in two.
                return ProcessPathOrUri(
                    fully_processed=False, path=None, uri=pu.replace(" ", "%20")
                )
            if wsl_details.linux_path is None:
                if self.debug:
                    print(
                        f"Unable to convert '{pu}' into a Linux path",
                        file=sys.stderr,
                    )
                return ProcessPathOrUri(fully_processed=True, path=None, uri=None)
            assert self.file_manager
            if tools.filemanager_requires_path(file_manager=self.file_manager):
                path = Path(wsl_details.linux_path).resolve()
                uri = None
            else:
                path = None
                uri = Path(wsl_details.linux_path).resolve().as_uri()
            return ProcessPathOrUri(fully_processed=False, path=path, uri=uri)

    def _process_path_or_uri_non_wsl(self, pu: str) -> ProcessPathOrUri:
        """
        Process the path or URI when not running under WSL1 or WSL2.

        :param pu: path or URI to process
        :return: A tuple indicating whether the path or URI has been fully processed,
         and if not, a Path or URI to process further
        """

        assert self.file_manager
        if tools.is_uri(pu):
            if (
                tools.filemanager_requires_path(file_manager=self.file_manager)
                and self.allow_conversion
            ):
                if tools.is_file_uri(pu):
                    # Convert URI to a regular path
                    uri = None
                    path = Path(tools.file_uri_to_path(pu))
                elif current_platform == Platform.windows and tools.is_smb_uri(pu):
                    # Windows has no smb: handler, but it has a way to name the
                    # same share: the UNC path. Elsewhere the file managers speak
                    # smb:// themselves and the URI is left as it arrived.
                    uri = None
                    path = Path(tools.smb_uri_to_unc(pu))
                elif (
                    current_platform == Platform.windows
                    and self.file_manager == "explorer.exe"
                ):
                    # Explorer is driven through the shell API, which takes
                    # filesystem items only: a URI it cannot turn into an item
                    # comes back as a COM error, so there is nothing to show.
                    if self.debug:
                        print(
                            f"Cannot show a {pu.split(':', 1)[0]}:// URI in"
                            f" Windows Explorer: '{pu}'",
                            file=sys.stderr,
                        )
                    return ProcessPathOrUri(fully_processed=True, path=None, uri=None)
                else:
                    # A manager that was given a URI takes it as it stands, but a
                    # raw space is not valid in a URI and would split the command
                    # line it goes into, so it is encoded. The same is done to
                    # Windows URIs in linux.wsl_transform_path_uri().
                    uri = pu.replace(" ", "%20")
                    path = None
            else:
                uri = pu.replace(" ", "%20")
                path = None
        else:
            if (
                tools.filemanager_requires_path(file_manager=self.file_manager)
                or not self.allow_conversion
            ):
                path = Path(pu)
                uri = None
            else:
                uri = Path(pu).resolve().as_uri()
                path = None

        return ProcessPathOrUri(fully_processed=False, path=path, uri=uri)

    def _process_path_or_uri_no_select(
        self, path: Path | None, uri: str | None
    ) -> None:
        """
        Process the path or URI when using a file manager that cannot select files
        or directories.
        """

        assert current_platform != Platform.windows
        # Show only the directory: do not attempt to select the file,
        # because the file manager cannot handle it.

        if uri and not tools.is_file_uri(uri):
            # Not a filesystem location, so there is no parent directory to
            # show. The manager is given the URI it was sent, unchanged.
            self.locations.append(uri)
            return

        if uri:
            # Do not use tools.file_url_to_path() here, because we need the
            # parse_result, and file_url_to_path() assumes file:// URIs.
            # In any case, this code block is not run under Windows, so
            # there is no need to use tools.file_url_to_path() to handle the
            # file:/// case that urllib.parse.urlparse fails with.
            parse_result = urllib.parse.urlparse(uri)
            path = Path(urllib.parse.unquote(parse_result.path))
        else:
            parse_result = None

        assert path is not None

        if not (path.is_dir() and self.open_not_select_directory):
            path = path.parent

        if parse_result is not None:
            quoted = urllib.parse.quote(str(path))
            location = str(urllib.parse.urlunparse(parse_result._replace(path=quoted)))
        else:
            location = tools.quote_path(path=path)
        self.locations.append(location)

    def _process_path_or_uri_can_select(
        self, path: Path | None, uri: str | None
    ) -> None:
        """
        Process the path or URI when using a file manager that can select files
        and potentially directories.
        """

        # Whether to open a directory or select it depends on file manager capabilities
        # and the option open_not_select_directory
        open_directory = False

        if (
            self.open_not_select_directory
            and self.file_manager_type != FileManagerType.dual_panel
            or self.file_manager_type == FileManagerType.regular
        ):
            if uri:
                if tools.is_file_uri(uri):
                    path = Path(tools.file_uri_to_path(uri=uri))
                    open_directory = path.is_dir()
                else:
                    # A URI from another scheme names something this process
                    # cannot examine, so it cannot be treated as a directory:
                    # it goes to the file manager as the URI it arrived as.
                    open_directory = False
            else:
                assert path is not None
                open_directory = path.is_dir()
            if open_directory:
                # Only a path that was examined can be a directory, so this is
                # never None here; a URI of another scheme sets open_directory
                # to False instead of inventing a path to examine.
                assert path is not None
                if (
                    self.file_manager_type == FileManagerType.regular
                    and not self.open_not_select_directory
                ):
                    # This type of file manager cannot select directories,
                    # because it provides no mechanism
                    # to distinguish between selecting and opening a
                    # directory.
                    # So open the parent instead.
                    path = path.parent
                    if uri:
                        uri = path.as_uri()
                if uri is not None:
                    location = uri
                elif self.file_manager == "explorer.exe":
                    location = str(path)
                else:
                    location = tools.quote_path(path=path)
                self.directories.append(location)
        if not open_directory:
            if uri is not None:
                location = uri
            else:
                assert path is not None
                if self.file_manager == "explorer.exe":
                    location = str(path)
                else:
                    location = tools.quote_path(path=path)
            self.locations.append(location)

    def _process_path_or_uri(self, path_or_uri: PathOrUri) -> None:
        """
        Examines the path or URI and processes it according to the needs of the
        file manager.

        :param path_or_uri: path or URI to process
        """

        # PathLike and fspath are imported by name rather than reached through
        # os, because tests replace this module's os with a recorder for
        # startfile, and turning arguments into strings must not depend on that.
        if isinstance(path_or_uri, (str, PathLike)):
            # turn the single path / URI into a Sequence
            path_or_uri = (path_or_uri,)

        # The rest of this layer works on strings, since what gets built is a
        # command line. A Path is resolved here rather than deeper in, because
        # it is only ever a string with an iterator it does not have.
        filtered_path_or_uri = (fspath(p_or_u) for p_or_u in path_or_uri if p_or_u)
        for pu in filtered_path_or_uri:
            if is_wsl:
                p = self._process_path_or_uri_wsl(pu)
            else:
                p = self._process_path_or_uri_non_wsl(pu)

            if p.fully_processed:
                continue

            path = p.path
            uri = p.uri
            assert path is not None or uri is not None

            if self.file_manager_type == FileManagerType.dir_only_uri:
                self._process_path_or_uri_no_select(path, uri)
            else:
                self._process_path_or_uri_can_select(path, uri)

    def _set_file_manager_argument(self) -> None:
        self.arg = ""
        if self.file_manager_type == FileManagerType.win_select:
            self.arg = "/select,"  # no trailing space is necessary on Windows
        elif self.file_manager_type == FileManagerType.select:
            self.arg = "--select "  # trailing space is necessary
        elif self.file_manager_type == FileManagerType.show_item:
            self.arg = "--show-item "  # trailing space is necessary
        elif self.file_manager_type == FileManagerType.show_items:
            self.arg = "--show-items "  # trailing space is necessary
        elif self.file_manager_type == FileManagerType.reveal:
            self.arg = "--reveal "  # trailing space is necessary

    def _launch(self) -> None:
        if (
            current_platform == Platform.windows
            and not is_wsl
            and self.file_manager == "explorer.exe"
        ):
            if self.locations:
                windows.launch_file_explorer(self.locations, self.verbose)
            for d in self.directories:
                if self.verbose:
                    print("Executing Windows shell to open", d)
                os.startfile(d)  # type: ignore[attr-defined]
        else:
            if self.locations:
                # Some file managers must be passed only one or zero paths / URIs
                if self.file_manager not in single_file_only:
                    self.locations = [" ".join(self.locations)]

                self._launch_file_manager(uris_or_paths=self.locations)
            if self.directories:
                if self.file_manager not in single_file_only:
                    self.directories = [" ".join(self.directories)]
                self.arg = ""
                self._launch_file_manager(uris_or_paths=self.directories)
            if self.wsl_windows_paths:
                self.arg = "/select,"
                self.file_manager = "explorer.exe"
                self._launch_file_manager(uris_or_paths=self.wsl_windows_paths)
            if self.wsl_windows_directories:
                self.arg = ""
                self.file_manager = "explorer.exe"
                self._launch_file_manager(uris_or_paths=self.wsl_windows_directories)

        if (
            not self.locations
            and not self.directories
            and not self.wsl_windows_paths
            and not self.wsl_windows_directories
        ):
            self.arg = ""
            self._launch_file_manager(uris_or_paths=[""])
