from pathlib import Path
from typing import List
import urllib.parse

from .tools import is_uri, path_to_url, url_to_path


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
            path = Path(url_to_path(uri))
        else:
            uri = None
            path = Path(pu)
        if not path.is_dir():
            for globbed_pu in path.parent.resolve().glob(path.name):
                if uri:
                    paths.append(path_to_url(str(globbed_pu)))
                else:
                    paths.append(str(globbed_pu))
        else:
            if uri:
                paths.append(path_to_url(str(path)))
            else:
                paths.append(str(path.resolve()))

    return paths