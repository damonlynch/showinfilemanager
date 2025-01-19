# SPDX-FileCopyrightText: Copyright 2016-2024 Damon Lynch
# SPDX-License-Identifier: MIT

import os
import platform
import shlex
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import List, NamedTuple, Optional, Sequence, Union

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

PathOrUri = Union[str, Sequence[str]]


class ProcessPathOrUri(NamedTuple):
    fully_processed: bool
    path: Optional[Path]
    uri: Optional[str]


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
        self._valid_file_manager: Optional[str] = None
        self._valid_file_manager_type: Optional[FileManagerType] = None

        self.file_manager: Optional[str]
        self.file_manager_type: Optional[FileManagerType]

        # Used for directories when open_not_select_directory is True
        self.directories: List[str]

        # Target locations
        self.locations: List[str]

        # Used for paths that will be opened in Windows explorer called from WSL2
        self.wsl_windows_paths: List[str]
        self.wsl_windows_directories: List[str]

        # Argument to pass to a file manager on the command line
        self.arg: str = ""

        # whether to print command to be executed before launching the file manager
        self.verbose: bool
        self.debug: bool

        self.file_manager_specified: bool
        self.open_not_select_directory: bool
        self.allow_conversion: bool

    def _launch_file_manager(self, uris_or_paths: List[str]) -> None:
        """
        Launch the file manager

        :param uris_or_paths: list of URIs, or a list of a single empty string
        :param arg: arg to pass the file manager
        :param file_manager: file manager executable name
        :param verbose: if True print command to be executed before launching
         it
        """

        for u in uris_or_paths:
            cmd = f"{self.file_manager} {self.arg}{u}"
            if self.verbose:
                print("Executing", cmd)
            # Do not check current_platform here, it makes no sense
            args = shlex.split(cmd) if platform.system() != "Windows" else cmd
            proc = subprocess.Popen(args)
            if is_wsl2 and self.file_manager == "explorer.exe":
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
        path_or_uri: Optional[PathOrUri] = None,
        open_not_select_directory: bool = True,
        file_manager: Optional[str] = None,
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
                # Convert URI to a regular path
                uri = None
                path = Path(tools.file_uri_to_path(pu))
            else:
                uri = pu
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

        haserror = not (path.exists() if path else Path(tools.file_uri_to_path(pu)).exists())
        if haserror and self.debug:
            print(f"Path '{path}' does not exist", file=sys.stderr)

        return ProcessPathOrUri(fully_processed=haserror, path=path, uri=uri)

    def _process_path_or_uri_no_select(
        self, path: Optional[Path], uri: Optional[str]
    ) -> None:
        """
        Process the path or URI when using a file manager that cannot select files
        or directories.
        """

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
        else:
            parse_result = None

        assert path is not None

        if not (path.is_dir() and self.open_not_select_directory):
            path = path.parent
        if uri:
            assert parse_result is not None
            uri = str(urllib.parse.urlunparse(parse_result._replace(path=str(path))))
        else:
            path = tools.quote_path(path=path)
        self.locations.append(uri or str(path))

    def _process_path_or_uri_can_select(
        self, path: Optional[Path], uri: Optional[str]
    ) -> None:
        """
        Process the path or URI when using a file manager that can select files
        and potentially directories.
        """

        # Whether to open a directory or select it depends on file manager capabilities
        # and the option open_not_select_directory
        is_directory = False

        if (
            self.open_not_select_directory
            and self.file_manager_type != FileManagerType.dual_panel
            or self.file_manager_type == FileManagerType.regular
        ):
            if uri:
                path = Path(tools.file_uri_to_path(uri=uri))
                is_directory = path.is_dir()
            else:
                assert path is not None
                is_directory = path.is_dir()
            if is_directory:
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
                if uri is None:
                    path = tools.quote_path(path=path)
                self.directories.append(uri or str(path))
        if not is_directory:
            if uri is None and self.file_manager != "explorer.exe":
                assert path is not None
                path = tools.quote_path(path=path)
            self.locations.append(uri or str(path))

    def _process_path_or_uri(self, path_or_uri: PathOrUri) -> None:
        """
        Examines the path or URI and processes it according to the needs of the
        file manager.

        :param path_or_uri: path or URI to process
        """

        if isinstance(path_or_uri, str):
            # turn the single path / URI into a Sequence
            path_or_uri = (path_or_uri,)

        filtered_path_or_uri = (p_or_u for p_or_u in path_or_uri if p_or_u)
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
