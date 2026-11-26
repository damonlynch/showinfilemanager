#  SPDX-FileCopyrightText: 2016-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

"""
Tests for the diagnostics the command line prints under --debug.

Diagnostics is what gets pasted into a bug report when no file manager turns up, so a
failure to detect one is part of the answer rather than a crash: each detection error is
kept as its message, and a desktop that cannot be read is reported as unknown. The three
detections are reached through this package's own names, which is where the scenarios
below intervene. Nothing is launched.
"""

import pytest

from showinfm import showinfm
from showinfm.constants import Platform
from showinfm.showinfm import Diagnostics
from showinfm.system import linux


@pytest.fixture(autouse=True)
def answered(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Present a Linux desktop whose three detections all succeed.

    Without it the report depends on the machine running the suite, and a scenario about
    what is said when detection fails would be answering a different question.
    """

    monkeypatch.setattr(showinfm, "current_platform", Platform.linux)
    monkeypatch.setattr(showinfm, "stock_file_manager", lambda: "nautilus")
    monkeypatch.setattr(showinfm, "user_file_manager", lambda: "dolphin")
    monkeypatch.setattr(showinfm, "valid_file_manager", lambda: "nautilus")
    monkeypatch.setattr(linux, "linux_desktop", lambda: linux.LinuxDesktop.gnome)


def test_a_failure_to_detect_is_reported_as_its_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A detection that raises leaves its text in the report, so the reader learns which
    question the package could not answer instead of seeing a traceback about one.
    """

    stock_failure = "The desktop wayland is unknown"
    valid_failure = "xdg utilities are not installed"

    def no_stock() -> str:
        raise RuntimeError(stock_failure)

    def no_valid() -> str:
        raise RuntimeError(valid_failure)

    monkeypatch.setattr(showinfm, "stock_file_manager", no_stock)
    monkeypatch.setattr(showinfm, "valid_file_manager", no_valid)

    diagnostics = Diagnostics()

    assert diagnostics.stock_file_manager == stock_failure
    assert diagnostics.valid_file_manager == valid_failure
    report = str(diagnostics)
    assert f"Stock: {stock_failure}" in report
    assert f"Valid: {valid_failure}" in report
    assert "User's choice: dolphin" in report


def test_no_user_choice_registered_reads_as_a_state_not_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A machine with nothing registered for directories is a normal machine, not a broken
    one, so the report says the choice is not set. Naming an empty string as a file manager
    that is not installed sends whoever reads the report looking for a program called ''.
    """

    monkeypatch.setattr(showinfm, "user_file_manager", lambda: "")

    diagnostics = Diagnostics()

    assert diagnostics.user_file_manager == ""
    report = str(diagnostics)
    assert "User's choice: not set" in report
    assert "not installed" not in report


def test_nothing_usable_to_run_is_reported_as_no_file_manager_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    An empty answer from valid_file_manager() is the one finding a bug report needs: no
    file manager on this system can be run, so nothing was launched. Left blank, the line
    reads as though the check never happened.
    """

    monkeypatch.setattr(showinfm, "valid_file_manager", lambda: "")

    diagnostics = Diagnostics()

    assert diagnostics.valid_file_manager == ""
    assert "Valid: no file manager found" in str(diagnostics)


def test_a_desktop_that_cannot_be_read_is_reported_as_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The desktop line is worth having even when reading it failed, so the enum's own unknown
    member is substituted rather than leaving the field unset.
    """

    failure = "The value for XDG_CURRENT_DESKTOP is not set"

    def unreadable() -> linux.LinuxDesktop:
        raise RuntimeError(failure)

    monkeypatch.setattr(linux, "linux_desktop", unreadable)

    diagnostics = Diagnostics()

    assert diagnostics.desktop is linux.LinuxDesktop.unknown
    assert "Linux Desktop: unknown" in str(diagnostics)


def test_wsl1_is_reported_by_its_version(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    WSL1 and WSL2 select files differently, so the report names which one the package
    believes it is on. Only the absence of the WSL2 flag distinguishes them here.
    """

    monkeypatch.setattr(showinfm, "is_wsl", True)
    monkeypatch.setattr(showinfm, "is_wsl2", False)

    diagnostics = Diagnostics()

    assert diagnostics.wsl_version == "1"
    assert "WSL version 1" in str(diagnostics)
