# Copyright (c) 2021 Damon Lynch
# Some portions Copyright (c) 2008-2021 The pip developers
# SPDX - License - Identifier: MIT

from collections import defaultdict
import os
from pathlib import Path
import re
import shlex
import sys
from typing import List, DefaultDict, Optional

from urllib.parse import urlparse, unquote, urljoin
from urllib.request import url2pathname, pathname2url

from . import urivalidate
from . import current_platform, is_wsl2
from ..constants import Platform, cannot_open_uris


def filemanager_requires_path(file_manager: str) -> bool:
    return current_platform == Platform.windows or file_manager in cannot_open_uris


def is_uri(path_uri: str) -> bool:
    """
    Checks if string is probably a uri of some kind.
    :param path_uri: the
    :return: True if probably a URI, else False
    """

    if path_uri and path_uri.startswith('camera:/'):
        return True
    return re.match("^%s$" % urivalidate.URI, path_uri, re.VERBOSE) is not None


def quote_path(path: Path) -> Path:
    """
    Quote path in a way that works with file managers on Windows and Unix-like.

    If path is already quoted, returns it as is.

    Replaces single quoted string with double quotes on Windows.

    Uses shlex.quote on non-Windows platforms, but again only if the path is
    not already quoted.

    :param path: path to quote, if necessary
    :param target_platform: platform the file manager command will be executed on
    :return: double quoted path
    """

    p = str(path)
    if current_platform == Platform.windows:
        # Double quotes are not allowed in paths names - they are used for quoting

        if re.match("""'(.*)'""", p) is not None:
            # Replace single quotes with double quotes
            return Path('"{}"'.format(p[1:-1]))
        if re.match(r"""\"(.*)\"""", p) is None:
            # Add double quotes where there was no quoting at all
            return Path('"{}"'.format(path))
    else:
        if not (p[0] in ('"', "'") and p[-1] == p[0]):
            return Path(shlex.quote(p))
    return path


def path_to_file_uri(path: str) -> str:
    """
    Convert a path to a file: URL.  The path will be made absolute and have
    quoted path parts.

    Taken from pip: https://github.com/pypa/pip/blob/main/src/pip/_internal/utils/urls.py
    Copyright (c) 2008-2021 The pip developers
    """

    path = os.path.normpath(os.path.abspath(path))
    url = urljoin("file:", pathname2url(path))
    return url


def file_uri_to_path(uri: str) -> str:
    """
    Convert a file: URL to a path.

    On Windows this is more reliable than urllib.parse.urlparse, because that fails when
    run with a URI like file:///D:/some/directory

    Taken from https://stackoverflow.com/a/61922504/592623
    and modified by Damon Lynch 2021
    """

    parsed = urlparse(uri)
    host = "{0}{0}{mnt}{0}".format(os.path.sep, mnt=parsed.netloc)
    p = os.path.normpath(os.path.join(host, url2pathname(parsed.path)))
    return p


def directories_and_their_files(paths: List[str]) -> DefaultDict[str, List[str]]:
    """
    Group paths into directories and their files.

    If path is a directory, the parent will be the directory, and the subfolder will
    be the child of that directory.

    :param paths: list of paths
    :return: default dict of folders with list of their files
    """

    if isinstance(paths, str):
        paths = [paths]
    folder_contents = defaultdict(list)
    for path in paths:
        p = Path(path)
        folder_contents[str(p.parent)].append(p.name)
    return folder_contents
