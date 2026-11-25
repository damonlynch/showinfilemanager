#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

"""
Tests for what only Windows does: the win32com.shell dependency of issue #39, and the
UNC locations of issue #38.

Each scenario runs in its own interpreter through tests/system/windows_probe.py,
because current_platform and the decision to import win32com.shell are both made
while the package is being imported, and the modules that consume current_platform
bind it with a from-import. Patching either of them part way through a run inspects a
module that has already committed to its answer. One subprocess per scenario is the
price of that, and reports are cached per scenario so the suite stays quick.

These hold on a real Windows install too: the blocked case forbids the import rather
than relying on pywin32 being absent.

The UNC tests come in two layers. The string one needs no share and pins the separator
a URI with a host converts to. The live one is skipped unless SHOWINFM_UNC_ROOT names a
readable share, because only a real folder shows what the library hands over is what
Windows accepts -- quote and doubled separators both fail there, and both fail quietly
on a machine without a share.
"""

import functools
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import showinfm
from showinfm import filemanager
from showinfm.exceptions import WindowsShellUnavailableError
from showinfm.system import windows
from showinfm.system.tools import file_uri_to_path

REPO_ROOT = Path(__file__).resolve().parents[2]

# A share to test against, as only its owner can know it. Nothing here writes to it.
UNC_ROOT = os.environ.get("SHOWINFM_UNC_ROOT", "")
REAL_UNC = bool(UNC_ROOT) and platform.system() == "Windows" and Path(UNC_ROOT).is_dir()

requires_unc_share = pytest.mark.skipif(
    not REAL_UNC,
    reason="needs SHOWINFM_UNC_ROOT set to a readable network share",
)


@pytest.fixture(scope="module")
def unc_folder() -> str:
    """
    A real directory on the share, preferring one whose name contains a space, since
    that is what quoting was added for and what it breaks on.

    :return: the directory as Windows names it
    """

    try:
        subfolders = [p for p in Path(UNC_ROOT).iterdir() if p.is_dir()]
    except OSError as e:
        pytest.skip(f"{UNC_ROOT} could not be listed: {e}")
    spaced = [p for p in subfolders if " " in p.name]
    return str((spaced or subfolders or [Path(UNC_ROOT)])[0])


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
    # Equality, not containment: os.startfile is a direct Win32 call, so the folder has
    # to arrive as it stands. Wrapping it in quotes was issue #38, and rebuilding the
    # quoted value as a Path also collapsed the leading separators of a UNC location.
    assert report["startfile"] == [folder]


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


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="ntpath and the Windows url2pathname decide this shape",
)
def test_a_uri_with_a_host_keeps_one_separator_before_the_share() -> None:
    """
    file://host/share is how a network location is written as a URI, and url2pathname()
    returns a path that still begins with a separator. Two separators in front of the
    share name is a path the shell API refuses, so the host alone supplies them.
    """

    assert (
        file_uri_to_path("file://storage/Backup/media render/holiday.jpg")
        == r"\\storage\Backup\media render\holiday.jpg"
    )


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="ntpath and the Windows url2pathname decide this shape",
)
def test_a_uri_without_a_host_still_converts_to_a_drive_path() -> None:
    """The ordinary case, which must not move while the network one is corrected."""

    assert file_uri_to_path("file:///C:/x y/holiday.jpg") == r"C:\x y\holiday.jpg"


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="ntpath and the Windows url2pathname decide this shape",
)
def test_a_localhost_authority_still_names_a_local_drive_path() -> None:
    """
    RFC 8089 counts an authority of localhost as a local file URI, "exactly as if no
    authority were present", so the drive letter begins the path, not becoming a share
    called C: on a host named localhost.
    """

    assert (
        file_uri_to_path("file://localhost/C:/x y/holiday.jpg") == r"C:\x y\holiday.jpg"
    )


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="the same rule, read on the interpreter that used to drop the host",
)
def test_a_localhost_authority_still_names_a_local_path_off_windows() -> None:
    """
    The POSIX half of the pair above, and of the same sentence in the RFC. A host of
    localhost is this machine, not a share, so no leading component is added.
    """

    assert (
        file_uri_to_path("file://localhost/home/damon/holiday.jpg")
        == "/home/damon/holiday.jpg"
    )


@requires_unc_share
def test_a_live_network_folder_reaches_startfile_exactly(
    monkeypatch: pytest.MonkeyPatch, unc_folder: str
) -> None:
    """
    The whole route, with only the API call stood in for: the folder is real, so Windows
    decides its directoryness rather than this test asserting it. Quote would arrive as
    literal characters, and rebuilding a quoted value as a Path drops one of the two
    leading separators.
    """

    opened: list[str] = []
    monkeypatch.setattr(filemanager, "os", SimpleNamespace(startfile=opened.append))

    filemanager.FileManager().show_in_file_manager(
        unc_folder, file_manager="explorer.exe"
    )

    assert opened == [unc_folder]


@requires_unc_share
def test_a_live_network_folder_survives_the_uri_round_trip(unc_folder: str) -> None:
    """
    as_uri() and back has to name the same folder: that round trip is the only way a
    caller hands a network location over as a URI.
    """

    converted = file_uri_to_path(Path(unc_folder).as_uri())

    assert converted == unc_folder
    assert Path(converted).is_dir()


@requires_unc_share
def test_a_live_network_folder_given_as_a_uri_is_opened_not_selected(
    monkeypatch: pytest.MonkeyPatch, unc_folder: str
) -> None:
    """
    The route issue #38 recommends as a workaround. Converting the URI back to a path is
    what decides whether the folder is opened or selected, so a doubled separator there
    sends it to the shell API instead, which refuses it. Neither API is really called.
    """

    opened: list[str] = []
    selected: list = []
    monkeypatch.setattr(filemanager, "os", SimpleNamespace(startfile=opened.append))
    monkeypatch.setattr(
        filemanager.windows,
        "launch_file_explorer",
        lambda paths, verbose=False: selected.append(paths),
    )

    filemanager.FileManager().show_in_file_manager(
        Path(unc_folder).as_uri(), file_manager="explorer.exe"
    )

    assert selected == []
    assert opened == [unc_folder]


@requires_unc_share
def test_the_shell_api_accepts_the_network_folder_it_is_given(unc_folder: str) -> None:
    """
    The Windows answer, not this machine's opinion of the string. SHILCreateFromPath is
    the first call launch_file_explorer() makes and the one that refused the doubled
    separator. Parsing a path opens no window.
    """

    converted = file_uri_to_path(Path(unc_folder).as_uri())
    report = scenario("unc_parse", converted)

    assert report["available"] is True, (
        "pywin32 is not usable here, so the shell API cannot answer"
    )
    assert report["error"] is None, report
    assert report["parsed"] is True
