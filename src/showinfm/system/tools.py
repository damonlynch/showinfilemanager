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

    camera: is an opaque identifier from Rapid Photo Downloader rather than a
    location, so it is accepted whatever the grammar says.

    file: is accepted by prefix because the grammar forbids a raw space, and a
    space is how people write a file URI whose path contains one:
    file:///home/user/My Docs/x.jpg. Rejected by the grammar, that string is
    taken for a relative path and resolved against the working directory.

    :param path_uri: the
    :return: True if probably a URI, else False
    """

    if path_uri and path_uri.startswith(("camera:/", "file:/")):
        return True
    return re.match("^%s$" % urivalidate.URI, path_uri, re.VERBOSE) is not None


def is_file_uri(path_uri: str) -> bool:
    """
    Does the URI name a location on a filesystem, i.e. carry the file: scheme?

    Only such a URI can become a path. Others say what they are by their scheme,
    smb://, trash://, camera:/ among them, and rewriting one of those as a path
    invents a place the scheme never named: trash:// is not the root of the
    filesystem, and no path says where a share named by a URI actually is.

    :param path_uri: the path or URI to examine
    :return: True if the value is a URI with the file: scheme
    """

    return path_uri[:6].lower() == "file:/"


def _double_quoted(value: str) -> str:
    r"""
    Wrap a Windows path in double quotes, leaving it a single command line token.

    A trailing backslash has to be doubled first: CreateProcess tokenises with the
    MSVC rule where `\"` is an escaped quote rather than the end of the argument, so
    `"C:\"` arrives as `C:"` and, with another path following it, swallows that too.
    pathlib produces such a trailing separator on its own for a share root, since
    `"\\server\share"` is a root and `str()` of a root ends with a separator.
    """

    # Hoisted out of the f-string: a backslash in an f-string expression is a
    # syntax error before Python 3.12, and 3.11 is the supported floor.
    escaped = re.sub(r"(\\+)$", r"\1\1", value)
    return f'"{escaped}"'


def quote_path(path: Path) -> str:
    r"""
    Quote path in a way that works with file managers on Windows and Unix-like.

    If path is already quoted, returns it as is.

    Replaces single quoted string with double quotes on Windows, and escapes a
    trailing separator so the closing quote closes.

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
            return _double_quoted(p[1:-1])
        if re.match(r"""\"(.*)\"""", p) is None:
            # Add double quotes where there was no quoting at all
            return _double_quoted(p)
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
    r"""
    Convert a file: URL to a path.

    On Windows this is more reliable than urllib.parse.urlparse, because that fails when
    run with a URI like file:///D:/some/directory

    Only a file: URI names a location on a filesystem, so anything else raises. A
    share URI has a defensible reading as a UNC path, but trash:// has no path to
    stand for it, and rewriting it as the filesystem root opens a folder the caller
    never asked for and reports no error while doing it.

    Taken from https://stackoverflow.com/a/61922504/592623
    and modified by Damon Lynch 2021, 2024, 2026

    :raises ValueError: if the URI does not carry the file: scheme
    """

    if not is_file_uri(uri):
        raise ValueError(f"Not a file URI: {uri!r}")

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
