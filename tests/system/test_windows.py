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

import ctypes
import functools
import json
import os
import platform
import shlex
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace

import pytest

import showinfm
from showinfm import filemanager
from showinfm.constants import Platform
from showinfm.exceptions import WindowsShellUnavailableError
from showinfm.system import tools, windows
from showinfm.system.tools import file_uri_to_path, smb_uri_to_unc

REPO_ROOT = Path(__file__).resolve().parents[2]

# A share to test against, as only its owner can know it. Nothing here writes to it.
UNC_ROOT = os.environ.get("SHOWINFM_UNC_ROOT", "")
REAL_UNC = bool(UNC_ROOT) and platform.system() == "Windows" and Path(UNC_ROOT).is_dir()

requires_unc_share = pytest.mark.skipif(
    not REAL_UNC,
    reason="needs SHOWINFM_UNC_ROOT set to a readable network share",
)


def win_argv(command: str) -> list[str]:
    """
    Ask Windows how a command string tokenises, rather than reading it here.

    CreateProcess tokenises by the MSVC rule: a backslash escapes the quote after it,
    so `"C:\"` arrives as `C:"`. CommandLineToArgvW implements that rule, which makes it
    the answer for a manager launched from a command string.
    Windows only: ctypes.windll does not exist elsewhere.
    """

    shell32 = ctypes.windll.shell32
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    shell32.CommandLineToArgvW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_int),
    ]
    count = ctypes.c_int(0)
    argv = shell32.CommandLineToArgvW(command, ctypes.byref(count))
    try:
        return [argv[i] for i in range(count.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(argv)


class RecordedLaunch:
    """
    Stand in for a launched file manager, answering what the package asks of one.

    Nothing is started here, so the stand-in reports itself finished. It has to answer
    poll() as well as wait(): _reap_processes() reads every recorded launch that way to
    keep the module's list of them from growing, and a stand-in that cannot answer
    leaves its object in that list for the rest of the process. Every later launch then
    fails on it -- in whichever test happens to run next, which is how one incomplete
    fake turned into forty-three failures.
    """

    def __init__(self) -> None:
        self.returncode: int | None = None

    def poll(self) -> int:
        self.returncode = 0
        return 0

    def wait(self) -> None:
        self.returncode = 0


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
        check=False,
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
    reason="the translation exists because Windows writes a share as a UNC path",
)
def test_an_smb_uri_becomes_the_unc_path_for_the_same_share() -> None:
    r"""
    Windows has no smb: handler, so the URI has to be said the Windows way before
    anything can open it. The share alone, and the server alone, are roots: their
    str() carries a trailing separator, which is what the quoting has to survive.
    """

    assert smb_uri_to_unc("smb://srv/share/holiday.jpg") == r"\\srv\share\holiday.jpg"
    assert (
        smb_uri_to_unc("smb://srv/my share/holiday.jpg")
        == r"\\srv\my share\holiday.jpg"
    )
    assert smb_uri_to_unc("smb://srv/share/h%20name.jpg") == r"\\srv\share\h name.jpg"
    assert smb_uri_to_unc("SMB://SRV/Share") == r"\\SRV\Share"
    assert smb_uri_to_unc("smb://srv/share") == r"\\srv\share"
    assert Path(smb_uri_to_unc("smb://srv/share")).is_absolute()

    with pytest.raises(ValueError, match="Not an smb URI"):
        smb_uri_to_unc("smb:///share/holiday.jpg")


@requires_unc_share
def test_a_live_smb_uri_reaches_the_share_it_names(
    monkeypatch: pytest.MonkeyPatch, unc_folder: str
) -> None:
    """
    The translation proved against the share itself rather than a made-up server: the
    UNC path it produces is the folder Windows can see, and the shell API accepts it.
    """

    server, share = UNC_ROOT.strip("\\").split("\\", 1)
    tail = unc_folder[len(UNC_ROOT) :].replace("\\", "/").replace(" ", "%20")
    uri = f"smb://{server}/{share}{tail}"

    opened: list[str] = []
    monkeypatch.setattr(filemanager, "os", SimpleNamespace(startfile=opened.append))
    monkeypatch.setattr(
        filemanager.windows,
        "launch_file_explorer",
        lambda paths, verbose=False: opened.extend(paths),
    )

    filemanager.FileManager().show_in_file_manager(uri, file_manager="explorer.exe")

    assert opened == [unc_folder]
    assert scenario("unc_parse", unc_folder)["error"] is None


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


@pytest.mark.parametrize(
    "uri",
    [
        "smb://srv/share/h.jpg",
        "ftp://srv/pub/h.jpg",
        "nfs://srv/export/h.jpg",
        "trash://",
        "camera:/1234567890",
        "mailto:someone@example.com",
    ],
)
def test_a_uri_of_another_scheme_is_not_turned_into_a_path(uri: str) -> None:
    """
    file_uri_to_path() takes file: URIs only; smb:// has its own translation and
    the rest name no filesystem location at all. Converting those invented a place
    the URI never claimed: a server taken from the authority, or the filesystem
    root for trash://.
    """

    with pytest.raises(ValueError, match="Not a file URI"):
        file_uri_to_path(uri)


def test_only_file_uris_are_accepted_by_the_converter() -> None:
    """The guard is on the scheme, not on the grammar, so the ordinary case converts."""

    assert file_uri_to_path("file:///x y/h.jpg").endswith(os.path.join("x y", "h.jpg"))


def test_a_file_uri_with_a_raw_space_is_still_recognised() -> None:
    """
    RFC 3986 forbids a space, so the grammar alone rejected the URIs people actually
    write, and an unrecognized one was taken for a relative path and resolved against
    the working directory.
    """

    assert tools.is_uri("file:///home/damon/My Docs/h.jpg")
    assert tools.is_file_uri("file:///home/damon/My Docs/h.jpg")
    assert not tools.is_file_uri("smb://srv/share/h.jpg")
    assert not tools.is_file_uri("/home/damon/My Docs/h.jpg")


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
def test_a_live_network_folder_reaches_another_manager_quoted_and_intact(
    monkeypatch: pytest.MonkeyPatch, unc_folder: str
) -> None:
    """
    The route the explorer.exe guard leaves to quote_path(): a manager that is not
    explorer.exe receives one command string, so the folder must arrive quoted as one
    token and still name the share. Rebuilding that token as a Path left it as
    "\\server\\share\folder" with one leading separator, a local path, and no change to
    the quoting itself could fix that. Hence a real share.
    """

    launched: list = []

    def popen(args, *rest, **kwargs):
        launched.append(args)
        return RecordedLaunch()

    monkeypatch.setattr(filemanager, "subprocess", SimpleNamespace(Popen=popen))

    filemanager.FileManager().show_in_file_manager(unc_folder, file_manager="nemo")

    assert launched == [f'nemo "{unc_folder}"']


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


@pytest.fixture
def as_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Select the Windows branch of quote_path() on any interpreter.

    The branch is chosen by current_platform, which is patched here the same way the
    dispatch scenarios set it. What a patch cannot move is the Path class, which
    follows the interpreter, so the UNC case below separates right from wrong only on
    Windows. That is where it matters, and it is skipped elsewhere rather than diluted.
    """

    monkeypatch.setattr(tools, "current_platform", Platform.windows)


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="only a Windows Path collapses the UNC prefix it is handed",
)
def test_quoting_a_windows_unc_path_keeps_both_leading_separators(
    as_windows: None,
) -> None:
    r"""
    Wrapping a path in quotes must leave the path alone. Rebuilding the quoted value
    as a Path hides the UNC root behind the quote character, so "\\server\share" comes
    back as "\server\share" -- a folder called server on the current drive. That is the
    failure issue #38 reports, for any manager other than explorer.exe.
    """

    quoted = tools.quote_path(path=Path(r"\\server\share\media render"))

    assert quoted == '"\\\\server\\share\\media render"'
    assert Path(quoted.strip('"')).is_absolute()


def test_quoting_a_windows_drive_path_makes_one_token(as_windows: None) -> None:
    """The point of the quoting: an unquoted space would split the argument."""

    quoted = tools.quote_path(path=Path(r"C:\x y\holiday.jpg"))

    assert quoted == '"C:\\x y\\holiday.jpg"'


def test_quoting_an_already_quoted_windows_path_leaves_it_alone(
    as_windows: None,
) -> None:
    """
    A path that arrives quoted is returned as it stands. Quoting it again would nest the
    quotes, so the caller would get an argument whose closing quote is escaped.
    """

    quoted = tools.quote_path(path=Path('"C:\\x y\\holiday.jpg"'))

    assert quoted == '"C:\\x y\\holiday.jpg"'


def test_a_single_quoted_windows_path_becomes_double_quoted(as_windows: None) -> None:
    """Windows takes double quotes, so a path arriving single quoted is rewritten."""

    quoted = tools.quote_path(path=Path("'C:\\x y'"))

    assert quoted == '"C:\\x y"'


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="only a Windows path renders its root with a trailing separator",
)
def test_quoting_a_windows_root_escapes_its_trailing_separator(
    as_windows: None,
) -> None:
    r"""
    str() of a root ends with a separator, and for a share root pathlib adds that
    separator itself: `\\server\share` becomes `\\server\share\`. Quoting it as it
    stands leaves the closing quote escaped, so the token needs a doubled separator.
    """

    assert tools.quote_path(path=Path("C:\\")) == '"C:\\\\"'
    assert tools.quote_path(path=Path(r"\\server\share")) == '"\\\\server\\share\\\\"'


def test_quoting_leaves_a_path_without_a_trailing_separator_alone(
    as_windows: None,
) -> None:
    """The escape is for roots only; an ordinary path must not grow characters."""

    assert (
        tools.quote_path(path=Path(r"C:\x y\holiday.jpg")) == '"C:\\x y\\holiday.jpg"'
    )


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="CreateProcess tokenising is what is being asked",
)
def test_a_quoted_root_parses_back_to_one_argument(as_windows: None) -> None:
    """
    The parser's verdict rather than this file's reading of the string: what a file
    manager launched from one command string is handed. Before the escape was added,
    `nemo "C:\"` came back as the single argument `C:"`.
    """

    for raw in ("C:\\", "\\\\server\\share"):
        wanted = str(Path(raw))
        parsed = win_argv(f"nemo {tools.quote_path(path=Path(raw))}")
        assert parsed == ["nemo", wanted]


@requires_unc_share
def test_a_live_share_root_reaches_another_manager_as_one_token(
    monkeypatch: pytest.MonkeyPatch, unc_folder: str
) -> None:
    """
    The share root alongside a folder below it: the root is the case whose str() ends
    with a separator, and a swallowed quote corrupts the argument after it too. The
    assertion is what the parser returns, not what this file built.
    """

    launched: list = []

    def popen(args, *rest, **kwargs):
        launched.append(args)
        return RecordedLaunch()

    monkeypatch.setattr(filemanager, "subprocess", SimpleNamespace(Popen=popen))

    root = str(Path(UNC_ROOT))
    filemanager.FileManager().show_in_file_manager(
        [UNC_ROOT, unc_folder], file_manager="nemo"
    )

    assert launched == [f'nemo "{root}\\" "{unc_folder}"']
    assert win_argv(launched[0]) == ["nemo", root, unc_folder]


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="a Windows interpreter turns the POSIX path into separators of its own",
)
def test_quoting_off_windows_uses_shell_quoting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    The other branch, kept as the contrast that stops a Windows fix leaking into it: the
    managers here are handed a command line that shlex will split, so they need shell
    quoting rather than double quotes.

    Only expressible on a POSIX interpreter: patching current_platform selects the
    branch, not the Path class, and a WindowsPath renders this input with backslashes.
    """

    monkeypatch.setattr(tools, "current_platform", Platform.linux)

    quoted = tools.quote_path(path=Path("/home/damon/holiday film.jpg"))

    assert quoted == "'/home/damon/holiday film.jpg'"
    assert shlex.split(f"nemo {quoted}")[1] == "/home/damon/holiday film.jpg"


@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="a Windows interpreter turns the POSIX path into separators of its own",
)
def test_a_posix_path_that_arrives_quoted_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Quoting is applied once, so a path already wrapped in matching quotes goes through
    untouched. Wrapping it again would have the shell look for a file whose name begins and
    ends with a quote character.
    """

    monkeypatch.setattr(tools, "current_platform", Platform.linux)

    single = "'/home/damon/holiday film.jpg'"
    double = '"/home/damon/holiday film.jpg"'

    assert tools.quote_path(path=Path(single)) == single
    assert tools.quote_path(path=Path(double)) == double


@pytest.fixture
def fake_shell(monkeypatch: pytest.MonkeyPatch) -> list:
    """
    Stand in for the three shell functions the launcher calls, and return what it was asked.

    Put on the module attribute the launcher reads, so the guard for a missing pywin32 stays
    behind the scenario and only the announcement is under test.
    """

    calls: list = []
    shell = SimpleNamespace(
        SHILCreateFromPath=lambda path, _flags: (
            calls.append(["pidl", path]) or (f"pidl-{path}", 0)
        ),
        SHParseDisplayName=lambda display, _unused, _reference: (
            calls.append(["item", display]) or (f"item-{display}", 0)
        ),
        SHOpenFolderAndSelectItems=lambda folder, items, _flags: calls.append(
            ["open", folder, list(items), _flags]
        ),
    )
    monkeypatch.setattr(windows, "_shell", shell)
    return calls


def test_the_selection_is_announced_with_the_files_it_selects(
    fake_shell: list, capsys, tmp_path
) -> None:
    """
    What the shell API is asked to do is invisible unless it is printed, so verbose names the
    folder and the files selected in it.
    """

    target = tmp_path / "holiday.jpg"

    windows.launch_file_explorer([str(target)], True)

    out = capsys.readouterr().out
    assert f'at "{tmp_path}", selecting "{target.name}"' in out
    assert fake_shell[0] == ["pidl", str(tmp_path)]


def test_nothing_is_announced_when_there_is_nothing_to_select(
    fake_shell: list, capsys
) -> None:
    """
    With no location there is no folder to ask the shell about, so the loop is skipped
    entirely rather than announcing an empty selection.
    """

    windows.launch_file_explorer([], True)

    assert capsys.readouterr().out == ""
    assert fake_shell == []


@pytest.mark.skipif(
    platform.system() != "Windows",
    reason="only a Windows path reports a share root as a folder with no name",
)
def test_a_root_is_announced_with_nothing_quoted_after_it(
    fake_shell: list, capsys
) -> None:
    r"""
    A share root is the folder and has no name of its own, so the list of files to
    select is a list of one empty string, and joining it answers with nothing. Quoting
    that would announce `selecting ""`, a file called two quote characters, which is
    how the announcement stops matching what the shell API is asked to do. Reached from
    the command line by selecting -- rather than opening -- a share: explorer.exe is
    handed the root itself.
    """

    windows.launch_file_explorer([r"\\srv\share"], True)

    out = capsys.readouterr().out
    assert out.startswith("Executing Windows shell to open file explorer at ")
    assert out.endswith(", selecting \n")
    assert fake_shell[0] == ["pidl", "\\\\srv\\share\\"]
