#  SPDX-FileCopyrightText: 2016-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

"""
Tests for the version argumentsparse.py falls back to when the package cannot be imported.

The packaging build imports this module by path to reach get_parser(), while the package
itself is not yet importable, so the module reads the version from its sibling
__about__.py instead. It parses that file rather than running it, and the first scenario
below pins the difference. The second pins what actually breaks in practice: the sibling
moving, which would otherwise let the command line and the built distribution disagree.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

import showinfm
from showinfm import argumentsparse


def load_at_build_time(path: Path, name: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    """
    Run the module the way the build does: by file, with the package unimportable.

    None in sys.modules is the interpreter's own signal that an import of that name is
    forbidden, which turns the try at the top of the module into its except branch. The
    submodule has to be blocked alongside the package: a cached showinfm.__about__ is
    handed back without importing its parent, so blocking only the parent would leave the
    module on the import branch and every scenario below would test nothing.

    :return: the loaded module, loose-typed because its members exist only after this call
    """

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "showinfm", None)
    monkeypatch.setitem(sys.modules, "showinfm.__about__", None)
    spec.loader.exec_module(module)
    return module


def test_the_build_time_fallback_reads_the_version_without_running_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """
    A sibling that raises on being executed still yields its version, because only the
    literal is taken from it. An implementation that ran the file instead would die on
    that line, and the man page build would never reach get_parser().
    """

    source = Path(argumentsparse.__file__)
    (tmp_path / "__about__.py").write_text(
        '__version__ = "9.9.9.build-time"\nraise RuntimeError("executed")\n',
        encoding="utf-8",
    )
    copied = tmp_path / "argumentsparse.py"
    copied.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    module = load_at_build_time(copied, "argumentsparse_build_time", monkeypatch)

    assert module.__version__ == "9.9.9.build-time"
    with pytest.raises(SystemExit):
        module.get_parser().parse_args(["--version"])
    assert capsys.readouterr().out == "showinfilemanager 9.9.9.build-time\n"


def test_the_build_time_version_agrees_with_the_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The fallback and the import have to answer the same thing, or the built documentation
    carries a different version from the installed package. Reading the sibling by name
    below the module rather than beside it is what would make this fail.
    """

    module = load_at_build_time(
        Path(argumentsparse.__file__), "argumentsparse_fresh", monkeypatch
    )

    assert module.__version__ == showinfm.__version__
