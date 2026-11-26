#  SPDX-FileCopyrightText: 2016-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

"""
Tests for main(), the command line entry point.

The library never exits and never prints on its own, so main() is the only place a failure
becomes something the user sees: the diagnostics under --debug, the reason written to
stderr, and the traceback that --debug asks to be left alone. The launch itself is recorded
rather than performed, so no file manager is started here.
"""

import platform
import sys

import pytest

from showinfm import showinfm


@pytest.fixture
def launched(monkeypatch: pytest.MonkeyPatch) -> list:
    """Collect the arguments each call passes on, and start nothing."""

    calls: list = []
    monkeypatch.setattr(
        showinfm, "show_in_file_manager", lambda **kwargs: calls.append(kwargs)
    )
    return calls


def argv(monkeypatch: pytest.MonkeyPatch, *options: str) -> None:
    monkeypatch.setattr(sys, "argv", ["showinfilemanager", *options])


@pytest.fixture
def failing(monkeypatch: pytest.MonkeyPatch) -> str:
    """Make the launch raise, and hand back the message it raises with."""

    failure = "nothing to open"

    def fail(**_kwargs: object) -> None:
        raise ValueError(failure)

    monkeypatch.setattr(showinfm, "show_in_file_manager", fail)
    return failure


def test_debug_prints_the_diagnostics_and_forces_verbose(
    launched: list, monkeypatch: pytest.MonkeyPatch, capsys, tmp_path
) -> None:
    """
    --debug is the reporting switch, so it prints what the package knows and turns on the
    command echo with it. The paths arrive as the list argparse collected, unchanged, because
    on this platform nothing has to be retokenised first.
    """

    argv(monkeypatch, "--debug", str(tmp_path))

    showinfm.main()

    out, err = capsys.readouterr()
    assert "Stock: " in out
    assert err == ""
    assert launched[0]["verbose"] is True
    assert launched[0]["debug"] is True
    assert launched[0]["path_or_uri"] == [str(tmp_path)]


def test_selecting_a_folder_is_the_inverse_of_the_option(
    launched: list, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """
    The option is about folders and the flag the package carries is about not selecting them,
    so the two are opposite by one negation.
    """

    argv(monkeypatch, "--select-folder", str(tmp_path))

    showinfm.main()

    assert launched[0]["open_not_select_directory"] is False


def test_a_failure_is_written_to_stderr_and_the_command_returns(
    failing: str, monkeypatch: pytest.MonkeyPatch, capsys, tmp_path
) -> None:
    """
    Anything the launch raises that is not the missing shell is reported as its message and
    swallowed, so a script calling the command is not handed a traceback.
    """

    argv(monkeypatch, str(tmp_path))

    showinfm.main()

    assert capsys.readouterr().err == failing


def test_debug_lets_the_same_failure_propagate(
    failing: str, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """
    Under --debug the message alone is not enough, so the exception is left to reach the
    interpreter and print its traceback after the report has been written.
    """

    argv(monkeypatch, "--debug", str(tmp_path))

    with pytest.raises(ValueError, match=failing):
        showinfm.main()


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="only the Windows run takes the arguments through the parser at all",
)
def test_a_parser_failure_is_reported_as_a_message_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """
    Globbing and URI normalisation happen on the raw arguments before anything launches,
    and that call used to sit outside this function's try. So the one failure a user
    could meet without a file manager running was the only one that reached them as a
    traceback -- and after the parser stopped raising on an unreachable root, this is
    what keeps a future raise from escaping unannounced.
    """

    def unparseable(_arguments, **_kwargs):
        message = "Unacceptable pattern: ''"
        raise ValueError(message)

    monkeypatch.setattr(showinfm.windows, "parse_command_line_arguments", unparseable)
    argv(monkeypatch, "Q:\\")

    showinfm.main()

    assert capsys.readouterr().err == "Unacceptable pattern: ''"


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="only the Windows run takes the arguments through the parser at all",
)
def test_debug_lets_a_parser_failure_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same promise --debug already makes of every other failure here."""

    def unparseable(_arguments, **_kwargs):
        message = "Unacceptable pattern: ''"
        raise ValueError(message)

    monkeypatch.setattr(showinfm.windows, "parse_command_line_arguments", unparseable)
    argv(monkeypatch, "--debug", "Q:\\")

    with pytest.raises(ValueError, match="Unacceptable pattern"):
        showinfm.main()


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="only the Windows run reads the arguments through the parser at all",
)
def test_the_debug_flag_reaches_the_argument_parser(
    launched: list, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """
    Dropping an argument is silent unless --debug asked for the reason, so the flag has
    to survive the trip from the parsed options to the parser. Recorded as the function
    receives it rather than inferred from a docstring, and the list passes through
    untouched so what the launch was given is visible too.
    """

    seen: list = []

    def record(arguments, *, debug=False):
        seen.append(debug)
        return list(arguments)

    monkeypatch.setattr(showinfm.windows, "parse_command_line_arguments", record)

    argv(monkeypatch, str(tmp_path))
    showinfm.main()
    argv(monkeypatch, "--debug", str(tmp_path))
    showinfm.main()

    assert seen == [False, True]
    assert [recorded["path_or_uri"] for recorded in launched] == [
        [str(tmp_path)],
        [str(tmp_path)],
    ]
