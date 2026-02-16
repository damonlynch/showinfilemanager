#  SPDX-FileCopyrightText: 2016-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

"""
Parse command line arguments
"""

import importlib.metadata
from argparse import ArgumentParser, HelpFormatter
from pathlib import Path

try:
    from showinfm import __about__ as __about__
except ImportError:
    # The script is being run at build time
    # Module imports are unavailable

    here = Path(__file__).parent
    with open(here / "__about__.py") as f:
        about = {}
        exec(f.read(), about)

    # Convert about dictionary to class
    class About:
        pass

    __about__ = About()
    __about__.__dict__.update(about)


def package_metadata():
    """
    Get Python package metadata

    :return: package summary
    """

    try:
        metadata = importlib.metadata.metadata("show-in-file-manager")
        summary = metadata["summary"]
    except Exception:
        summary = (
            "Platform independent Python module to open the system file manager "
            "and optionally select files in it "
        )
    return summary


def get_parser(formatter_class=HelpFormatter) -> ArgumentParser:
    """
    Parse command line options for this script

    :param formatter_class: one of 4 argparse formatting classes
    :return: argparse.ArgumentParser
    """

    summary = package_metadata()

    parser = ArgumentParser(
        prog="showinfilemanager", description=summary, formatter_class=formatter_class
    )

    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__about__.__version__}"
    )

    parser.add_argument("-f", "--file-manager", help="file manager to run")

    parser.add_argument(
        "-s",
        "--select-folder",
        action="store_true",
        help="select folder instead of displaying its contents",
    )

    parser.add_argument(
        "--verbose", action="store_true", help="display command being run to stdout"
    )

    parser.add_argument(
        "--debug", action="store_true", help="output debugging information to stdout"
    )

    parser.add_argument(
        "path", nargs="*", help="zero or more URIs or paths of files or directories"
    )

    return parser
