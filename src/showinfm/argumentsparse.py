# Copyright (c) 2016-2024 Damon Lynch
# SPDX - License - Identifier: MIT

"""
Parse command line arguments
"""

import importlib.metadata
from argparse import ArgumentParser, HelpFormatter


def package_metadata():
    """
    Get Python package metadata

    :return: version number and package summary
    """

    try:
        version = importlib.metadata.version("show-in-file-manager")
    except Exception:
        version = "Unknown version"
        summary = (
            "Platform independent Python module to open the system file manager "
            "and optionally select files in it "
        )

    else:
        metadata = importlib.metadata.metadata("show-in-file-manager")
        summary = metadata["summary"]

    return version, summary


def get_parser(formatter_class=HelpFormatter) -> ArgumentParser:
    """
    Parse command line options for this script

    :param formatter_class: one of 4 argparse formatting classes
    :return: argparse.ArgumentParser
    """

    version, summary = package_metadata()

    parser = ArgumentParser(
        prog="showinfilemanager", description=summary, formatter_class=formatter_class
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {version}")

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
