# Copyright (c) 2021 Damon Lynch
# SPDX - License - Identifier: MIT

import re
import shlex
from pathlib import Path

from . import urivalidate
from . import current_platform
from ..constants import Platform


def is_uri(path_uri: str) -> bool:
    """
    Checks if string is probably a uri of some kind.
    :param path_uri: the
    :return: True if probably a URI, else False
    """

    return re.match("^%s$" % urivalidate.URI, path_uri, re.VERBOSE) is not None


def quote_path(path: Path) -> Path:
    """
    Quote path in a way that works with file managers on Windows and Unix-like.

    If path is already quoted, returns it as is.

    Replaces single quoted string with double quotes on Windows.

    Uses shlex.quote on non-Windows platforms, but again only if the path is
    not already quoted.

    :param path: path to quote, if necessary
    :return: double quoted path
    """

    p = str(Path)
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
