#  SPDX-FileCopyrightText: 2016-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

"""
Keeps the README's transcribed docstrings in step with the code they quote.

The Usage section reproduces four docstrings verbatim inside python fences, because that is
the clearest way to show what the package promises. Nothing else reads the README, so a
docstring edited without its mirror leaves a correct test suite describing an out of date
API. Three of the four had drifted by 2026-11-27, all of them missing a :raises: line that
the CHANGELOG did document, and only a diff against the imported module found it.
"""

import inspect
import re
from itertools import zip_longest
from pathlib import Path

import pytest

from showinfm import (
    show_in_file_manager,
    stock_file_manager,
    user_file_manager,
    valid_file_manager,
)

README = Path(__file__).resolve().parents[1] / "README.md"

TRANSCRIBED = {
    "show_in_file_manager": show_in_file_manager,
    "valid_file_manager": valid_file_manager,
    "stock_file_manager": stock_file_manager,
    "user_file_manager": user_file_manager,
}


def readme_block(name: str) -> str:
    """Return the fenced python block that transcribes this function."""

    assert README.is_file()
    blocks = re.findall(
        r"```python\n(.*?)```", README.read_text(encoding="utf-8"), re.DOTALL
    )
    wanted = [b for b in blocks if b.startswith(f"def {name}(")]
    assert len(wanted) == 1, (
        f"expected one README block for {name}, found {len(wanted)}"
    )
    return wanted[0]


@pytest.mark.parametrize("name", sorted(TRANSCRIBED))
def test_the_readme_docstring_matches_the_code(name: str) -> None:
    """
    The body between the README's triple quotes is the function's docstring, line for line.
    Both sides are dedented and stripped of trailing whitespace, so the comparison is the text
    a reader sees rather than the indentation the source file happened to use.
    """

    block = readme_block(name)
    found = re.search(r'    """\n(.*?)\n    """', block, re.DOTALL)
    assert found is not None

    # getdoc() dedents, so the comparison holds whether or not the interpreter left the
    # source indentation inside __doc__, which changed in 3.13.
    doc = inspect.getdoc(TRANSCRIBED[name])
    assert doc is not None
    wanted = [line.rstrip() for line in doc.splitlines()]
    actual = [
        line[4:].rstrip() if line.startswith("    ") else line.rstrip()
        for line in found.group(1).splitlines()
    ]

    if actual == wanted:
        return

    lengths = f"README has {len(actual)} lines, the source docstring {len(wanted)}"
    for index, pair in enumerate(zip_longest(actual, wanted, fillvalue=None)):
        before, after = pair
        if before != after:
            pytest.fail(
                f"{name} docstring differs at line {index + 1} ({lengths}):\n"
                f"  README: {before!r}\n  source: {after!r}"
            )


@pytest.mark.parametrize("name", sorted(TRANSCRIBED))
def test_the_readme_signature_lists_the_same_parameters(name: str) -> None:
    """
    Names in order, and each default spelled as repr() spells it. The annotations are not
    compared: the README writes the PathOrUri alias where the live annotation is the union
    that alias names, and the two render differently by design.
    """

    signature = readme_block(name).split('    """')[0]
    declared = re.findall(r"^\s*(\w+):", signature, re.MULTILINE)
    parameters = inspect.signature(TRANSCRIBED[name]).parameters

    assert declared == list(parameters)

    for param in parameters.values():
        line = next(
            item
            for item in signature.splitlines()
            if re.match(rf"\s*{param.name}:", item)
        )
        if param.default is inspect.Parameter.empty:
            assert "=" not in line
        else:
            assert repr(param.default) in line
