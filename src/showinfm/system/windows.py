#  SPDX-FileCopyrightText: 2021-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

import os
import sys
from pathlib import Path
from typing import Any

from showinfm.constants import FileManagerType, Platform
from showinfm.exceptions import WindowsShellUnavailableError
from showinfm.system import current_platform
from showinfm.system.tools import (
    directories_and_their_files,
    file_uri_to_path,
    is_directory,
    is_file_uri,
    is_present,
    is_smb_uri,
    is_uri,
    path_to_file_uri,
    smb_uri_to_unc,
)

WindowsFileManagerBehavior = {
    "doublecmd.exe": FileManagerType.dual_panel,
    "fman.exe": FileManagerType.dual_panel,
}

# win32com.shell is used for one thing only: selecting files in Windows
# Explorer. Importing it is therefore restricted to Windows, where it's needed,
# and any failure to import it is recorded instead of raised, so that this
# package remains importable and folders can still be opened. The failure is
# reported when the API is actually needed, in launch_file_explorer().
_shell: Any = None
_shell_import_error: BaseException | None = None

if current_platform == Platform.windows:
    try:
        # Anything that stops this import from working means the API cannot be
        # used, so the exact exception type doesn't matter: pywin32 can fail
        # with a plain ImportError when it isn't installed, and with errors
        # from its own registration when the post-install step never ran.
        from win32com.shell import shell as _shell
    except Exception as e:
        _shell_import_error = e


def _shell_unusable_reason() -> str:
    """
    Describe why the Win32 shell API cannot be used.

    :return: reason for the API being unavailable
    """

    if _shell_import_error is not None:
        return f"{type(_shell_import_error).__name__}: {_shell_import_error}"
    return "win32com.shell was not imported"


def windows_shell_available() -> bool:
    """
    Whether the Win32 shell API that selects files in Windows Explorer can be
    used on this system.

    Only meaningful on Windows. On Linux and macOS the module is deliberately
    never imported, because those platforms select files by passing command
    line arguments to their file managers, so requiring pywin32 there would add
    a dependency that is never used. The result is therefore False on those
    platforms even though nothing is wrong with them.

    :return: True if win32com.shell was imported, else False
    """

    return _shell is not None


def windows_shell_status() -> str:
    """
    Describe whether the Win32 shell API can be used, for diagnostic output.

    :return: single line description of the state on this system
    """

    if current_platform != Platform.windows:
        return "not required (not running on Windows)"
    if _shell is not None:
        return "available"
    return f"not available ({_shell_unusable_reason()})"


def windows_file_manager_type(file_manager: str) -> FileManagerType:
    """
    Determine the type of command line arguments the Windows file manager expects
    :param file_manager: executable name
    :return: FileManagerType matching with the executable name, else
     FileManagerType.regular as a fallback
    """

    if file_manager == "explorer.exe":
        return FileManagerType.win_select
    return WindowsFileManagerBehavior.get(file_manager, FileManagerType.regular)


def parse_command_line_arguments(
    path_or_uri: list[str], *, debug: bool = False
) -> list[str]:
    """
    Convert any glob component in the filename component of Windows paths, which the
    Windows shell does not do itself

    An argument naming something that is there is used as it stands; only what nothing
    answers for is read as a pattern. Globbing every name was the rule, and it cannot
    stay: brackets are legal in a Windows filename and common in the ones screenshot and
    download tools write, so a name carrying them was re-read as a character class,
    matched nothing, and vanished without a word -- while a one character class, as in
    holiday[1].jpg, matched a different file and opened that instead. The two characters
    a caller must type to mean a wildcard, * and ?, are illegal in a filename, so a name
    that exists is never a pattern the caller meant.

    :param path_or_uri: list of paths or URIs
    :param debug: say on stderr which arguments were dropped, and why
    :return: list of paths or URIs with resolved paths and no glob components. An
     argument that names nothing this machine can reach contributes nothing.
    """

    paths = []
    for pu in path_or_uri:
        if is_file_uri(pu):
            uri = pu
            path = Path(file_uri_to_path(uri=uri))
        elif is_smb_uri(pu):
            # Windows names the same share as a UNC path, and it is the path that
            # can be globbed and resolved here. The URI form means nothing to
            # explorer.exe, so it is not carried past this point.
            uri = None
            path = Path(smb_uri_to_unc(uri=pu))
        elif is_uri(pu):
            # A URI of another scheme names no filesystem item, so there is
            # nothing to glob or resolve: pass it along as it arrived rather
            # than turning its host into a UNC server.
            paths.append(pu)
            continue
        else:
            uri = None
            path = Path(pu)
        if is_directory(path):
            if uri:
                paths.append(path_to_file_uri(str(path)))
            else:
                paths.append(str(path.resolve()))
            continue

        if not path.name:
            # A root has no filename component to glob, and glob() refuses the empty
            # pattern with ValueError rather than matching nothing. There is nothing
            # here to show, so the argument contributes nothing.
            if debug:
                print(f"Path does not exist: '{pu}'", file=sys.stderr)
            continue

        parent = path.parent.resolve()
        if is_present(path):
            # The name is an item on disk. Built the way a match is built -- the
            # resolved parent and this component, never the target of a link at the
            # end of it -- so a literal and a pattern cannot spell one file apart.
            matched = [parent / path.name]
        else:
            try:
                matched = list(parent.glob(path.name))
            except OSError:
                # The selector asks its own class whether the directory it is about to
                # scan is one, so glob() carries the same narrow swallow list as the two
                # questions above even though neither of them raised. A location that
                # cannot be answered has no matches, which is what this line already
                # answers for a folder that is not there.
                matched = []
            if not matched and debug:
                print(f"No file matched: '{pu}'", file=sys.stderr)

        for globbed_pu in matched:
            if uri:
                paths.append(path_to_file_uri(str(globbed_pu)))
            else:
                paths.append(str(globbed_pu))

    return paths


def launch_file_explorer(paths: list[str], verbose: bool | None = False) -> None:
    """
    Open Windows File Explorer, selecting files in their folders

    Inspired by https://mail.python.org/pipermail/python-win32/2012-September/012531.html
    and https://mail.python.org/pipermail/python-win32/2012-September/012533.html

    See also:
    https://learn.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shopenfolderandselectitems

    :param paths: list of paths to select
    :param verbose: if True print what will be executed
    :raises WindowsShellUnavailableError: if win32com.shell is not available
    """

    if _shell is None:
        msg = (
            "Cannot select files in Windows File Explorer: the win32com.shell "
            f"module of pywin32 could not be loaded ({_shell_unusable_reason()}). "
            "Install pywin32. If it is already installed, its components may not "
            "be registered, in which case run 'python -m pywin32_postinstall "
            "-install'. Folders can still be opened without pywin32."
        )
        raise WindowsShellUnavailableError(msg)

    folder_contents = directories_and_their_files(paths)
    if folder_contents:
        for folder in folder_contents:
            folder_pidl = _shell.SHILCreateFromPath(folder, 0)[0]
            if verbose:
                files = '", "'.join(folder_contents[folder])
                if files:
                    files = f'"{files}"'
                print(
                    "Executing Windows shell to open file "
                    f'explorer at "{folder}", selecting {files}'
                )
            to_select = [
                _shell.SHParseDisplayName(os.path.join(folder, filename), 0, None)[0]
                for filename in folder_contents[folder]
            ]
            _shell.SHOpenFolderAndSelectItems(folder_pidl, to_select, 0)  # type: ignore
