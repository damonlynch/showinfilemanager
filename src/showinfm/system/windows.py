# Copyright (c) 2021 Damon Lynch
# SPDX - License - Identifier: MIT

from pathlib import Path
from typing import List, Optional

try:
    from win32com.shell import shell
except ImportError:
    pass

from .tools import is_uri, path_to_file_url, file_url_to_path, directories_and_their_files
from ..constants import FileManagerType


WindowsFileManagerBehavior = {}
WindowsFileManagerBehavior['doublecmd.exe'] = FileManagerType.dual_panel
WindowsFileManagerBehavior['fman.exe'] = FileManagerType.dual_panel


def windows_file_manager_type(file_manager: str) -> FileManagerType:
    """
    Determine the type of command line arguments the Windows file manager expects
    :param file_manager: executable name
    :return: FileManagerType matching with the executable name, else FileManagerType.regular as a fallback
    """

    if file_manager == 'explorer.exe':
        return FileManagerType.win_select
    return WindowsFileManagerBehavior.get(file_manager, FileManagerType.regular)


def parse_command_line_arguments(path_or_uri: List[str]) -> List[str]:
    """
    Convert any glob component in the filename component of Windows paths, which the Windows shell does not
    do itself

    :param path_or_uri: list of paths or URIs
    :return: list of paths or URIs with resolved paths and no glob components
    """

    paths = []
    for pu in path_or_uri:
        if is_uri(pu):
            uri = pu
            path = Path(file_url_to_path(uri))
        else:
            uri = None
            path = Path(pu)
        if not path.is_dir():
            for globbed_pu in path.parent.resolve().glob(path.name):
                if uri:
                    paths.append(path_to_file_url(str(globbed_pu)))
                else:
                    paths.append(str(globbed_pu))
        else:
            if uri:
                paths.append(path_to_file_url(str(path)))
            else:
                paths.append(str(path.resolve()))

    return paths


def launch_file_explorer(paths: List[str], verbose: Optional[bool] = False) -> None:
    """
    Open Windows File Explorer, selecting files in their folders

    Inspired by https://mail.python.org/pipermail/python-win32/2012-September/012531.html
    and http://mail.python.org/pipermail/python-win32/2012-September/012533.html
    """

    folder_contents = directories_and_their_files(paths)

    if folder_contents:
        desktop = shell.SHGetDesktopFolder()
        for folder in folder_contents.keys():
            folder_pidl = shell.SHILCreateFromPath(folder, 0)[0]
            shell_folder = desktop.BindToObject(folder_pidl, None, shell.IID_IShellFolder)
            win_items = {desktop.GetDisplayNameOf(item, 0): item for item in shell_folder}
            to_select = [win_items[file] for file in folder_contents[folder] if file in win_items]
            if verbose:
                files = '", "'.join(folder_contents[folder])
                if files:
                    files = '"{}"'.format(files)
                print(
                    'Executing Windows shell to open file explorer at "{}", selecting {}'.format(folder, files)
                )
            shell.SHOpenFolderAndSelectItems(folder_pidl, to_select, 0)
