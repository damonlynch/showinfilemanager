#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

"""
Tests for the Windows-only win32com.shell dependency, which is issue #39.

Each scenario runs in its own interpreter through tests/system/windows_probe.py,
because current_platform and the decision to import win32com.shell are both made
while the package is being imported, and the modules that consume current_platform
bind it with a from-import. Patching either of them part way through a run inspects a
module that has already committed to its answer. One subprocess per scenario is the
price of that, and reports are cached per scenario so the suite stays quick.

These hold on a real Windows install too: the blocked case forbids the import rather
than relying on pywin32 being absent.
"""

import functools
import json
import platform
import subprocess
import sys
from pathlib import Path

import pytest

import showinfm
from showinfm.exceptions import WindowsShellUnavailableError
from showinfm.system import windows

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def explorer_tree(tmp_path_factory: pytest.TempPathFactory) -> tuple[str, str]:
    """A directory and a file in it, as the shell API and os.startfile see them."""

    folder = tmp_path_factory.mktemp("explorer")
    target = folder / "holiday.jpg"
    target.write_text("", encoding="utf-8")
    return str(folder), str(target)


@functools.cache
def scenario(mode: str, target: str) -> dict:
    """
    Run one probe scenario in a fresh interpreter and return its report.

    A scenario that dies is never read as a pass: the child's stderr comes with the
    assertion, since a broken probe otherwise looks exactly like broken code.
    """

    result = subprocess.run(
        [sys.executable, "-m", "tests.system.windows_probe", mode, target],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{mode} exited {result.returncode}\n{result.stderr}"
    return json.loads(result.stdout)


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="on Windows the import is expected to happen",
)
def test_importing_here_never_reaches_for_pywin32() -> None:
    report = scenario("as_is", "")

    assert report["attempted_pywin32_imports"] == []
    assert report["available"] is False
    assert report["status"] == "not required (not running on Windows)"
    assert "Windows shell" not in report["diagnostics"]


def test_importing_as_macos_never_reaches_for_pywin32() -> None:
    report = scenario("darwin", "")

    assert report["attempted_pywin32_imports"] == []
    assert report["status"] == "not required (not running on Windows)"


def test_the_probe_records_an_import_when_one_is_actually_made() -> None:
    """
    The empty lists above are only evidence because this shows a non-empty list is
    reachable: a tracer that never fired would pass them just as well.
    """

    report = scenario("windows_attempt", "")

    assert report["attempted_pywin32_imports"], report["attempted_pywin32_imports"]


def test_selecting_files_aborts_and_says_how_to_fix_it(
    explorer_tree: tuple[str, str],
) -> None:
    _, target = explorer_tree
    report = scenario("windows_missing", target)

    assert report["raised"] == "WindowsShellUnavailableError"
    assert "win32com.shell" in report["message"]
    assert "pywin32_postinstall" in report["message"]


def test_the_availability_probe_tracks_whether_the_module_loaded(
    explorer_tree: tuple[str, str],
) -> None:
    _, target = explorer_tree
    blocked = scenario("windows_missing", target)
    loaded = scenario("windows_present", target)

    assert blocked["available"] is False
    assert blocked["status"].startswith("not available (")
    assert loaded["available"] is True
    assert loaded["status"] == "available"


def test_files_are_selected_by_walking_the_shell_api(
    explorer_tree: tuple[str, str],
) -> None:
    folder, target = explorer_tree
    calls = scenario("windows_present", target)["shell_calls"]

    assert [call[0] for call in calls] == [
        "SHILCreateFromPath",
        "SHParseDisplayName",
        "SHOpenFolderAndSelectItems",
    ]
    assert calls[0][1] == folder
    assert str(calls[1][1]).endswith("holiday.jpg")


def test_opening_a_folder_needs_no_pywin32(explorer_tree: tuple[str, str]) -> None:
    folder, _ = explorer_tree
    report = scenario("windows_folder_only", folder)

    assert report["errors"] == []
    assert len(report["startfile"]) == 1
    # Asserted as containment rather than equality: the folder reaches startfile
    # quoted, which is the separate unfixed defect about quoted paths
    assert folder in report["startfile"][0]


def test_diagnostics_report_the_shell_state_on_windows(
    explorer_tree: tuple[str, str],
) -> None:
    _, target = explorer_tree
    report = scenario("windows_missing", target)

    assert "Windows shell: not available" in report["diagnostics"]


def test_the_command_line_tool_aborts_with_a_status_of_one(
    explorer_tree: tuple[str, str],
) -> None:
    _, target = explorer_tree
    report = scenario("cli_missing", target)

    assert report["exit_code"] == 1
    assert "pywin32" in report["stderr"]
    assert report["stderr"].endswith("\n")


def test_the_command_line_tool_launches_normally_when_the_shell_loads(
    explorer_tree: tuple[str, str],
) -> None:
    _, target = explorer_tree
    report = scenario("cli_present", target)

    assert report["exit_code"] == "returned"
    assert report["stderr"] == ""


def test_the_error_is_a_runtime_error_reachable_from_the_package() -> None:
    assert issubclass(WindowsShellUnavailableError, RuntimeError)
    assert showinfm.WindowsShellUnavailableError is WindowsShellUnavailableError
    assert showinfm.windows_shell_available is windows.windows_shell_available
