#  SPDX-FileCopyrightText: 2008-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-FileCopyrightText: 2008-2021 The pip developers
#  SPDX-License-Identifier: MIT

import os
import re
import shlex
from collections import defaultdict
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import pathname2url, url2pathname

from showinfm.constants import Platform, cannot_open_uris
from showinfm.system import current_platform, urivalidate


def filemanager_requires_path(file_manager: str) -> bool:
    return current_platform == Platform.windows or file_manager in cannot_open_uris


def is_uri(path_uri: str) -> bool:
    """
    Checks if string is probably a uri of some kind.
    :param path_uri: the
    :return: True if probably a URI, else False
    """

    if path_uri and path_uri.startswith("camera:/"):
        return True
    return re.match("^%s$" % urivalidate.URI, path_uri, re.VERBOSE) is not None


def quote_path(path: Path) -> str:
    r"""
    Quote path in a way that works with file managers on Windows and Unix-like.

    If path is already quoted, returns it as is.

    Replaces single quoted string with double quotes on Windows.

    Uses shlex.quote on non-Windows platforms, but again only if the path is
    not already quoted.

    The quoted value is a command line token rather than a path, so it is
    returned as a string: rebuilding it as a Path reinterprets it, and on
    Windows a leading quote hides the UNC prefix, turning "\\server\share"
    into the drive-relative "\server\share".

    :param path: path to quote, if necessary
    :return: the path as one command line token, double quoted on Windows and
     shell quoted elsewhere
    """

    p = str(path)
    if current_platform == Platform.windows:
        # Double quotes are not allowed in paths names - they are used for quoting

        if re.match("""'(.*)'""", p) is not None:
            # Replace single quotes with double quotes
            return f'"{p[1:-1]}"'
        if re.match(r"""\"(.*)\"""", p) is None:
            # Add double quotes where there was no quoting at all
            return f'"{p}"'
    else:
        if not (p[0] in ('"', "'") and p[-1] == p[0]):
            return shlex.quote(p)
    return p


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
    and modified by Damon Lynch 2021, 2024
    """

    parsed = urlparse(uri)
    path = url2pathname(parsed.path)
    # RFC 8089: an authority of "localhost" names this machine, "exactly as if no
    # authority were present", so it must not become the host of a network path.
    # Loopback addresses and FQDNs that resolve locally are deliberately not
    # recognised here: that would mean resolving a name while converting a path.
    authority = "" if parsed.netloc.lower() == "localhost" else parsed.netloc
    root = f"{os.path.sep}{os.path.sep}{authority}{os.path.sep}"
    if authority:
        # A URI with a host names a network location, and the host supplies the leading
        # separators. url2pathname() keeps the one the URI's path starts with, and
        # os.path.join() on Python 3.11 adds a separator of its own in front of what is
        # left, so the UNC root is built by hand: two separators, the host, one more,
        # then the remainder. normpath() leaves a doubling inside a UNC path alone, and
        # the shell API refuses such a path.
        path = root + path.lstrip(f"{os.path.sep}{os.path.altsep or ''}")
    else:
        path = os.path.join(root, path)
    return os.path.normpath(path)


def directories_and_their_files(paths: list[str]) -> defaultdict[str, list[str]]:
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
