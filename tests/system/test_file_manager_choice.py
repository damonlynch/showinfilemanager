#  SPDX-FileCopyrightText: 2016-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

"""
Tests for the installed check in stock_file_manager() and user_file_manager().

Both functions name a file manager without knowing whether the machine can still run it:
the desktop's configuration can point at a program that was uninstalled, and the user's
choice can be empty. What they report has to say which name failed, because --debug prints
these strings to a human reading a bug report. Nothing here launches anything.
"""

import pytest

from showinfm import showinfm
from showinfm.constants import Platform
from showinfm.exceptions import FileManagerUnavailableError
from showinfm.showinfm import Diagnostics
from showinfm.system import linux


@pytest.fixture(autouse=True)
def nothing_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer every PATH lookup as a miss, on a Linux desktop."""

    monkeypatch.setattr(showinfm, "current_platform", Platform.linux)
    monkeypatch.setattr(showinfm.shutil, "which", lambda _name: None)


def test_a_missing_stock_manager_is_named_in_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The desktop's stock manager is a name from a table, so the failure has to carry it: a
    caller that only sees that something is missing cannot tell the user what to install.
    """

    monkeypatch.setattr(
        showinfm.linux, "stock_linux_file_manager", lambda: "no-such-fm"
    )

    with pytest.raises(FileManagerUnavailableError) as caught:
        showinfm.stock_file_manager()

    assert "no-such-fm" in str(caught.value)


def test_no_user_choice_at_all_is_reported_as_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    r"""
    An empty answer from the user's configuration reaches the same check as a program that
    is gone, because there is nothing to run either way. The name shows as '' rather than
    the message reading as though a real program were missing.
    """

    monkeypatch.setattr(showinfm.linux, "user_linux_file_manager", lambda: "")

    with pytest.raises(FileManagerUnavailableError) as caught:
        showinfm.user_file_manager()

    assert "''" in str(caught.value)


def test_the_diagnostics_report_carries_the_missing_manager_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    This line used to read "Stock: " with nothing after it, because the check was an assert
    and an assert carries no message of its own. The report is the only thing a user pastes,
    so the name has to survive into it.
    """

    monkeypatch.setattr(
        showinfm.linux, "stock_linux_file_manager", lambda: "no-such-fm"
    )
    monkeypatch.setattr(showinfm, "user_file_manager", lambda: "dolphin")
    monkeypatch.setattr(showinfm, "valid_file_manager", lambda: "dolphin")
    monkeypatch.setattr(
        showinfm.linux, "linux_desktop", lambda: linux.LinuxDesktop.gnome
    )

    report = [ln for ln in str(Diagnostics()).splitlines() if ln.startswith("Stock:")]

    assert report == ["Stock: The stock file manager 'no-such-fm' is not installed"]
