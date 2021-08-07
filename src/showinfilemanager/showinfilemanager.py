import os
import platform
import shlex
import subprocess
import sys
from typing import Optional, Tuple, Union, Sequence
import urllib.parse
import shutil
import argparse
import pathlib


import showinfilemanager.linux as linux
import showinfilemanager.__about__ as __about__
import showinfilemanager.__init__ as __init__
from showinfilemanager.constants import FileManagerType

_valid_file_manager_probed = False
_valid_file_manager = None
_valid_file_manager_type = None


def get_stock_file_manager() -> str:
    """
    Get stock file manager for this operating system / desktop.

    Exceptions are not caught.

    :return: executable name
    """

    system = platform.system()
    if system == 'Windows':
        file_manager = 'explorer.exe'
    elif system == 'Linux':
        file_manager = linux.get_stock_linux_file_manager()
    elif system == 'Darwin':
        raise NotImplementedError
    else:
        raise NotImplementedError

    assert shutil.which(file_manager) is not None
    return file_manager


def get_user_file_manager() -> str:
    """
    Get the file manager as set by the user.

    Exceptions are not caught.

    :return: executable name
    """

    system = platform.system()
    if system == 'Windows':
        file_manager = 'explorer.exe'
    elif system == 'Linux':
        file_manager = linux.get_user_linux_file_manager()
    elif system == 'Darwin':
        raise NotImplementedError
    else:
        raise NotImplementedError

    assert shutil.which(file_manager) is not None
    return file_manager


def get_valid_file_manager() -> str:
    """
    Get user's file manager, falling back to using sensible defaults for the desktop / OS.

    All exceptions are caught, except those if this platform is not supported by this module.

    :return: If the user's default file manager is set and it is known by this module, then
    return it. Otherwise return the stock file manager, if it exists.
    """

    system = platform.system()
    if system == 'Windows':
        file_manager = 'explorer.exe'
    elif system == 'Linux':
        file_manager = linux.get_valid_linux_file_manager()
    elif system == 'Darwin':
        raise NotImplementedError
    else:
        raise NotImplementedError
    return file_manager


def show_in_file_manager(path_or_uri: Optional[Union[str, Sequence[str]]] = None,
                         file_manager: Optional[str] = None) -> None:
    """
    Open the system file manager and display an optional directory, or items in the  directory.

    If there is no valid file manager found on the system, do nothing. A valid file manager
    is a file manager this module knows about.

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
        print(cmd)
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
            system = platform.system()
            if system == 'Windows':
                _valid_file_manager_type = FileManagerType.win_select
            elif system == 'Linux':
                _valid_file_manager_type = linux.get_linux_file_manager_type(fm)
            else:
                raise NotImplementedError
        _valid_file_manager_probed = True


class Diagnostic:

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

        if platform.system() == "Linux":
            try:
                self.desktop = linux.get_linux_desktop()
            except:
                self.desktop = linux.LinuxDesktop.unknown
        else:
            self.desktop = ''

    def __str__(self) -> str:
        return "Stock file manager: {}\nUser's choice of file manager: {}\nValid file manager: {}".format(
            self.stock_file_manager, self.user_file_manager, self.valid_file_manager
        ) + "\nLinux Desktop: {}".format(self.desktop.name) if self.desktop else ""


def parser_options(formatter_class=argparse.HelpFormatter):
    parser = argparse.ArgumentParser(
        prog=__about__.__title__, description=__about__.__summary__, formatter_class=formatter_class
    )

    parser.add_argument(
        '--version', action='version', version='%(prog)s {}'.format(__init__.__version__)
    )

    parser.add_argument('path', nargs='*')

    return parser


def main() -> None:
    parser = parser_options()

    args = parser.parse_args()

    print(Diagnostic())

    show_in_file_manager(path_or_uri=args.path)


if __name__ == '__main__':
    main()

