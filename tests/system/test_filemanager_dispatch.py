#  SPDX-FileCopyrightText: 2016-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

"""
Tests for the dispatch and launch decisions in showinfm.filemanager.

This is the layer between a call to show_in_file_manager() and the process that gets
started: which file manager, which argument, which bucket a path or URI lands in, and
whether anything is launched at all. Nothing here opens a file manager. Three names are
where that layer can reach the outside world, and all three are replaced with recorders:
subprocess.Popen, windows.launch_file_explorer() and os.startfile().

The platform flags are copied into each module by a from-import, so a scenario sets them
in every module that reads one. configure() refuses combinations that no real machine
produces, because a half-patched state makes a test pass while exercising something that
cannot happen.

The flags are as far as the simulation reaches: a Windows interpreter keeps its own path
layer, so the scenarios that expect a POSIX path back are skipped rather than rewritten.
See requires_posix_paths.
"""

import platform
from pathlib import Path
from types import SimpleNamespace

import pytest

from showinfm import filemanager
from showinfm.constants import FileManagerType, Platform
from showinfm.system import linux as real_linux
from showinfm.system import tools, windows

LINUX = Platform.linux
WINDOWS = Platform.windows
MACOS = Platform.macos

# Three scenarios depend on the path layer as well as the platform flags, and this
# interpreter can fake the flags but not the layer: pathlib and urllib follow the host.
# So "/mnt/c/notes.txt" reads as relative to the current drive, which resolve()
# prefixes; the "/C:/users/x" that urlparse() returns for a Windows URI reads as
# "\C:\users\x", so re-quoting it escapes every separator; and file:/// becomes a
# malformed UNC root that Path.is_dir() reported true only before 3.12. None of those
# branches is reachable here: current_platform and is_wsl are both set from
# platform.system() at import time, and dir_only_uri comes only from the Linux table.
# So each expectation stays the exact string a real machine gets, and the scenario is
# skipped rather than softened -- the guard test_linux.py puts on the same route.
requires_posix_paths = pytest.mark.skipif(
    platform.system() == "Windows",
    reason="depends on POSIX path semantics a Windows interpreter cannot reproduce",
)

# The mirror of the marker above: these scenarios name a drive path, and url2pathname()
# and ntpath follow the interpreter rather than the patched flags, so on a POSIX
# interpreter file:///C:/x becomes a path called C:x rather than a drive path. The
# expectation is the string Windows produces, so it is asked of Windows only.
requires_windows_paths = pytest.mark.skipif(
    platform.system() != "Windows",
    reason="depends on Windows path semantics a POSIX interpreter cannot reproduce",
)


class RecordedPopen:
    """Stand in for a Popen result, remembering that it was waited on."""

    def __init__(self, harness: "Dispatch", command: object) -> None:
        self.harness = harness
        self.command = command

    def wait(self) -> None:
        self.harness.waited.append(self.command)


class Dispatch:
    """The module-level seams a scenario needs, with everything recorded."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self.launches: list = []
        self.waited: list = []
        self.shell_calls: list = []
        self.startfile_calls: list = []
        self.valid_manager_calls = 0
        self.wsl_reports: dict[str, object] = {}
        self.default_report = None
        self._monkeypatch = monkeypatch
        self._tmp_path = tmp_path
        self.interpreter = "Linux"

        monkeypatch.setattr(
            filemanager,
            "subprocess",
            SimpleNamespace(Popen=self._popen),
        )
        monkeypatch.setattr(
            filemanager,
            "os",
            SimpleNamespace(startfile=self._startfile),
        )
        monkeypatch.setattr(
            filemanager,
            "windows",
            SimpleNamespace(
                launch_file_explorer=self._shell,
                windows_file_manager_type=windows.windows_file_manager_type,
            ),
        )
        monkeypatch.setattr(
            filemanager,
            "linux",
            SimpleNamespace(
                valid_linux_file_manager=self._valid_linux_file_manager,
                linux_file_manager_type=real_linux.linux_file_manager_type,
                wsl_transform_path_uri=self._wsl_transform,
            ),
        )

    def _popen(self, args: object, *more: object, **kwargs: object) -> RecordedPopen:
        self.launches.append(args)
        return RecordedPopen(self, args)

    def _startfile(self, path: str) -> None:
        self.startfile_calls.append(path)

    def _shell(self, locations: list[str], verbose: bool = False) -> None:
        self.shell_calls.append(list(locations))

    def _valid_linux_file_manager(self) -> str:
        self.valid_manager_calls += 1
        return "nautilus"

    def _wsl_transform(self, pu: str, require_win_path: bool):
        report = self.wsl_reports.get(pu, self.default_report)
        assert report is not None, f"no WSL report staged for {pu}"
        return report

    def report(self, **overrides):
        """Build a WSLTransformPathURI for a path under tmp_path."""
        fields = dict(
            is_win_location=False,
            win_uri=None,
            win_path=None,
            linux_path=str(self._tmp_path),
            is_dir=True,
            exists=True,
        )
        fields.update(overrides)
        return real_linux.WSLTransformPathURI(**fields)

    def configure(
        self,
        platform: Platform = LINUX,
        wsl: bool = False,
        wsl1: bool = False,
        wsl2: bool = False,
    ) -> None:
        """
        Present one coherent machine to every module that holds a copy of the flags.

        :param platform: the value of current_platform everywhere
        :param wsl: whether the code believes it is running under WSL at all
        :param wsl1: the WSL1 variant, which changes file manager choice
        :param wsl2: the WSL2 variant, which makes explorer.exe be waited on
        :raises AssertionError: for a combination no real system produces
        """

        if wsl1 or wsl2:
            if not wsl:
                raise AssertionError("wsl1 and wsl2 both imply wsl")
            if platform is not LINUX:
                raise AssertionError("WSL is reported as Linux")
        if wsl1 and wsl2:
            raise AssertionError("a machine is either WSL1 or WSL2")
        if platform is LINUX and wsl:
            interpreter = "Linux"
        elif platform is WINDOWS:
            interpreter = "Windows"
        else:
            interpreter = "Darwin"
        self.interpreter = interpreter

        for module in (filemanager, tools, windows, real_linux):
            if hasattr(module, "current_platform"):
                self._monkeypatch.setattr(module, "current_platform", platform)
        self._monkeypatch.setattr(filemanager, "is_wsl", wsl)
        self._monkeypatch.setattr(filemanager, "is_wsl1", wsl1)
        self._monkeypatch.setattr(filemanager, "is_wsl2", wsl2)
        self._monkeypatch.setattr(
            filemanager, "platform", SimpleNamespace(system=lambda: interpreter)
        )

    def run(self, path_or_uri=None, **kwargs) -> None:
        """One fresh FileManager per call, so no state carries between scenarios."""

        filemanager.FileManager().show_in_file_manager(path_or_uri, **kwargs)

    @property
    def commands(self) -> list:
        """Every launch as a comparable list of words."""

        return [c if isinstance(c, list) else [c] for c in self.launches]


@pytest.fixture
def dispatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Dispatch:
    """A Linux machine, nothing launched for real, and no WSL."""

    harness = Dispatch(monkeypatch, tmp_path)
    harness.configure()
    return harness


@pytest.mark.parametrize(
    ("manager_type", "expected"),
    [
        (FileManagerType.win_select, "/select,"),
        (FileManagerType.select, "--select "),
        (FileManagerType.show_item, "--show-item "),
        (FileManagerType.show_items, "--show-items "),
        (FileManagerType.reveal, "--reveal "),
        (FileManagerType.regular, ""),
        (FileManagerType.dual_panel, ""),
    ],
)
def test_argument_for_each_file_manager_type(
    dispatch: Dispatch, manager_type: FileManagerType, expected: str
) -> None:
    """
    win_select is the only one without a trailing space, because explorer.exe takes
    /select,PATH as a single argument.
    """

    fm = filemanager.FileManager()
    fm.file_manager_type = manager_type
    fm._set_file_manager_argument()
    assert fm.arg == expected


def test_a_directory_is_opened_rather_than_selected(
    dispatch: Dispatch, tmp_path
) -> None:
    dispatch.run(str(tmp_path), file_manager="dolphin")
    assert dispatch.commands == [["dolphin", tmp_path.as_uri()]]


def test_a_path_object_is_accepted(dispatch: Dispatch, tmp_path) -> None:
    """
    Callers reach for pathlib, and a Path is not iterable, so a single one has to be
    treated as the item it is rather than as a sequence.
    """

    dispatch.run(tmp_path, file_manager="dolphin")
    assert dispatch.commands == [["dolphin", tmp_path.as_uri()]]


def test_paths_and_strings_can_be_mixed_in_one_call(
    dispatch: Dispatch, tmp_path
) -> None:
    """
    The sequence case: each item is resolved to its string form on the way in, so the
    rest of this layer never has to know which kind of item it was given.
    """

    first = tmp_path / "one.jpg"
    second = tmp_path / "two.jpg"
    first.write_text("", encoding="utf-8")
    second.write_text("", encoding="utf-8")
    dispatch.run([first, str(second)], file_manager="dolphin")
    assert dispatch.commands == [
        ["dolphin", "--select", first.as_uri(), second.as_uri()]
    ]


def test_a_file_is_selected(dispatch: Dispatch, tmp_path) -> None:
    target = tmp_path / "holiday.jpg"
    target.write_text("", encoding="utf-8")
    dispatch.run(str(target), file_manager="dolphin")
    assert dispatch.commands == [["dolphin", "--select", target.as_uri()]]


@requires_posix_paths
def test_a_file_manager_that_cannot_select_files_gets_the_parent(
    dispatch: Dispatch, tmp_path
) -> None:
    """Thunar is typed dir_only_uri: the URI handed over is the containing folder."""

    target = tmp_path / "holiday.jpg"
    target.write_text("", encoding="utf-8")
    dispatch.run(str(target), file_manager="thunar")
    assert dispatch.commands == [["thunar", tmp_path.as_uri()]]


def test_a_regular_file_manager_never_receives_a_select_switch(
    dispatch: Dispatch, tmp_path
) -> None:
    target = tmp_path / "holiday.jpg"
    target.write_text("", encoding="utf-8")
    dispatch.run(str(target), file_manager="nemo")
    assert dispatch.commands == [["nemo", target.as_uri()]]


def test_a_dual_panel_manager_gets_the_directory_as_a_location(
    dispatch: Dispatch, tmp_path
) -> None:
    """Dual panel managers are never routed through the directory branch."""

    dispatch.run(str(tmp_path), file_manager="doublecmd")
    assert dispatch.commands == [["doublecmd", tmp_path.as_uri()]]


def test_several_files_are_passed_in_one_command(dispatch: Dispatch, tmp_path) -> None:
    for name in ("a.jpg", "b.jpg"):
        (tmp_path / name).write_text("", encoding="utf-8")
    dispatch.run(
        [str(tmp_path / "a.jpg"), str(tmp_path / "b.jpg")], file_manager="nautilus"
    )
    assert dispatch.commands == [
        [
            "nautilus",
            "--select",
            (tmp_path / "a.jpg").as_uri(),
            (tmp_path / "b.jpg").as_uri(),
        ]
    ]


def test_a_single_file_manager_is_launched_once_per_file(
    dispatch: Dispatch, tmp_path
) -> None:
    """pcmanfm is in single_file_only, so its paths are never joined together."""

    for name in ("a.jpg", "b.jpg"):
        (tmp_path / name).write_text("", encoding="utf-8")
    dispatch.run(
        [str(tmp_path / "a.jpg"), str(tmp_path / "b.jpg")], file_manager="pcmanfm"
    )
    assert len(dispatch.commands) == 2
    assert all(command[0] == "pcmanfm" for command in dispatch.commands)


def test_a_path_with_spaces_survives_the_round_trip(
    dispatch: Dispatch, tmp_path
) -> None:
    """
    Quoting happens before shlex.split, so what the file manager receives is the path as
    one argument. This is the shape issues about spaces in names keep returning to.
    """

    folder = tmp_path / "summer trip"
    folder.mkdir()
    target = folder / "holiday film.jpg"
    target.write_text("", encoding="utf-8")
    dispatch.run(str(target), file_manager="nautilus", allow_conversion=False)
    assert dispatch.commands == [["nautilus", "--select", str(target)]]


def test_a_foreign_scheme_reaches_a_uri_capable_manager_unchanged(
    dispatch: Dispatch,
) -> None:
    """
    Nautilus opens smb:// itself, which is why nothing was converted here before.
    The scheme is how it knows to browse a share rather than a folder.
    """

    uri = "smb://srv/share/holiday.jpg"
    dispatch.run(uri, file_manager="nautilus")
    assert dispatch.commands == [["nautilus", "--select", uri]]


def test_a_foreign_scheme_is_not_rewritten_for_a_path_only_manager(
    dispatch: Dispatch,
) -> None:
    """
    lumina-fm is handed a path, so the URI used to be rewritten as one: smb:// became
    //srv/share (or /share before the host was kept), a location that may well exist and
    open as if it were the share.
    """

    dispatch.run("smb://srv/share/holiday.jpg", file_manager="lumina-fm")
    assert dispatch.commands == [["lumina-fm", "smb://srv/share/holiday.jpg"]]


def test_a_scheme_without_a_path_is_not_collapsed_to_the_root(
    dispatch: Dispatch,
) -> None:
    """trash:// became /, the filesystem root, which opens as if intended."""

    dispatch.run("trash://", file_manager="fman")
    assert dispatch.commands == [["fman", "trash://"]]


def test_a_file_uri_with_a_raw_space_is_still_converted(
    dispatch: Dispatch,
) -> None:
    """
    The grammar rejects a space, so file:///home/damon/My Docs was taken for a
    relative path and resolved against the working directory: nautilus was asked to
    select a file under the project folder. The file: prefix bypass makes it a URI
    again, and the space is encoded because a raw one would split the command line.
    """

    dispatch.run("file:///home/damon/My Docs/holiday.jpg", file_manager="nautilus")
    assert dispatch.commands == [
        [
            "nautilus",
            "--select",
            "file:///home/damon/My%20Docs/holiday.jpg",
        ]
    ]


@requires_windows_paths
def test_an_smb_uri_becomes_a_share_path_for_explorer(dispatch: Dispatch) -> None:
    r"""
    Windows cannot open an smb: URI, so it is said as the UNC path for the same share.
    The server here need not exist: nothing is contacted, only the handover observed.
    """

    dispatch.configure(platform=WINDOWS)
    dispatch.run("smb://srv/share/holiday.jpg", file_manager="explorer.exe")
    assert dispatch.shell_calls == [[r"\\srv\share\holiday.jpg"]]


@requires_windows_paths
def test_explorer_is_handed_nothing_for_a_scheme_with_no_path(
    dispatch: Dispatch,
) -> None:
    """
    A scheme Windows cannot name either, and which no file manager was asked to browse,
    is dropped rather than turned into a server: the shell API answers a URI with a COM
    error, so the launch falls back to the bare start a dropped item already causes.
    """

    dispatch.configure(platform=WINDOWS)
    dispatch.run("ftp://srv/pub/holiday.jpg", file_manager="explorer.exe")
    assert dispatch.shell_calls == []
    assert dispatch.startfile_calls == []
    assert dispatch.commands == [["explorer.exe "]]


@requires_windows_paths
def test_a_file_uri_with_a_space_becomes_a_drive_path_for_explorer(
    dispatch: Dispatch,
) -> None:
    """What the bypass buys on Windows: a drive path, not one starting file:."""

    dispatch.configure(platform=WINDOWS)
    dispatch.run("file:///C:/x y/holiday.jpg", file_manager="explorer.exe")
    assert dispatch.shell_calls == [[r"C:\x y\holiday.jpg"]]


def test_no_path_still_opens_the_file_manager(dispatch: Dispatch) -> None:
    """With nothing to select the manager is launched bare, argument cleared."""

    dispatch.run(file_manager="nautilus")
    assert dispatch.commands == [["nautilus"]]


def test_empty_entries_are_not_launched(dispatch: Dispatch, tmp_path) -> None:
    target = tmp_path / "holiday.jpg"
    target.write_text("", encoding="utf-8")
    dispatch.run(["", str(target), ""], file_manager="dolphin")
    assert dispatch.commands == [["dolphin", "--select", target.as_uri()]]


@requires_posix_paths
def test_on_macos_no_path_opens_the_volume(dispatch: Dispatch) -> None:
    """
    file:/// has to become a path before the code can tell that it is a directory. On
    a Windows interpreter that path is a malformed UNC root, which Path.is_dir()
    reported true until 3.12 -- so this scenario passes on 3.11 and fails on 3.12
    here, and neither result says anything about the code.
    """

    dispatch.configure(platform=MACOS)
    dispatch.run(file_manager="open")
    assert dispatch.commands == [["open", "file:///"]]


def test_the_command_is_split_on_every_platform_but_windows(
    dispatch: Dispatch, tmp_path
) -> None:
    """
    On Windows the command stays one string rather than a list of words, and the path
    arrives double quoted because that is how quote_path serves the Windows shell. A
    dual panel manager is given no switch.
    """

    target = tmp_path / "holiday.jpg"
    target.write_text("", encoding="utf-8")
    dispatch.configure(platform=WINDOWS)
    dispatch.run(str(target), file_manager="doublecmd.exe")
    assert dispatch.launches == [f'doublecmd.exe "{target}"'], (
        "on Windows the command line is passed to CreateProcess as one string"
    )


def test_explorer_uses_the_shell_rather_than_a_process(
    dispatch: Dispatch, tmp_path
) -> None:
    """The win32 shell API is what allows several files to be selected at once."""

    target = tmp_path / "holiday.jpg"
    target.write_text("", encoding="utf-8")
    dispatch.configure(platform=WINDOWS)
    dispatch.run(str(target), file_manager="explorer.exe")
    assert dispatch.shell_calls == [[str(target)]]
    assert dispatch.launches == []


def test_directories_on_windows_use_startfile(dispatch: Dispatch, tmp_path) -> None:
    """
    A directory on native Windows goes to os.startfile, a direct Win32 call that takes
    the path as it stands. Quote reaches it as literal characters, and rebuilding a
    quoted value as a Path also drops one of the two leading separators of a UNC
    location -- issue #38.
    """

    dispatch.configure(platform=WINDOWS)
    dispatch.run(str(tmp_path), file_manager="explorer.exe")
    assert dispatch.startfile_calls == [str(tmp_path)]
    assert dispatch.launches == []
    assert dispatch.shell_calls == []


def test_other_windows_file_managers_still_receive_a_quoted_directory(
    dispatch: Dispatch, tmp_path
) -> None:
    """
    The exemption is for explorer.exe alone. Any other manager is launched as a single
    command string, which CreateProcess splits at the first space, and a temp path on
    this machine always holds one. nemo is used because only a manager that opens a
    directory reaches this branch.
    """

    dispatch.configure(platform=WINDOWS)
    dispatch.run(str(tmp_path), file_manager="nemo")
    assert dispatch.startfile_calls == []
    assert dispatch.launches == [f'nemo "{tmp_path}"']


def test_windows_locations_and_directories_are_both_handled(
    dispatch: Dispatch, tmp_path
) -> None:
    other = tmp_path / "elsewhere"
    other.mkdir()
    target = other / "holiday.jpg"
    target.write_text("", encoding="utf-8")
    dispatch.configure(platform=WINDOWS)
    dispatch.run([str(tmp_path), str(target)], file_manager="explorer.exe")
    assert dispatch.startfile_calls == [str(tmp_path)]
    assert dispatch.shell_calls == [[str(target)]]


@pytest.fixture
def wsl(dispatch: Dispatch, tmp_path: Path) -> Dispatch:
    """A WSL2 machine, with the path translation answered from below."""

    dispatch.configure(platform=LINUX, wsl=True, wsl2=True)
    windows_file = "file:///c:/Users/damon/Pictures/holiday.jpg"
    windows_folder = "file:///c:/Users/damon/Pictures/"
    dispatch.wsl_reports = {
        "/mnt/c/Users/damon/Pictures/holiday.jpg": dispatch.report(
            is_win_location=True, win_uri=windows_file, is_dir=False
        ),
        "/mnt/c/Users/damon/Pictures": dispatch.report(
            is_win_location=True, win_uri=windows_folder, is_dir=True
        ),
        str(tmp_path / "holiday.jpg"): dispatch.report(
            is_win_location=False,
            win_uri=f"\\\\wsl.localhost\\Ubuntu{tmp_path / 'holiday.jpg'}",
            linux_path=str(tmp_path / "holiday.jpg"),
            is_dir=False,
        ),
    }
    dispatch.default_report = dispatch.report(
        is_win_location=False, linux_path=str(tmp_path), is_dir=True
    )
    return dispatch


def test_wsl_routes_windows_paths_to_explorer_without_a_process(
    wsl: Dispatch,
) -> None:
    """The 1.0.0 workaround: the /select, argument carries the URI in one word."""

    wsl.run("/mnt/c/Users/damon/Pictures/holiday.jpg")
    assert wsl.commands == [
        ["explorer.exe", "/select,file:///c:/Users/damon/Pictures/holiday.jpg"]
    ]
    assert wsl.shell_calls == [], (
        "called from WSL, the win32 shell API is not available"
    )


def test_wsl_opens_a_windows_directory_without_selecting_it(wsl: Dispatch) -> None:
    wsl.run("/mnt/c/Users/damon/Pictures")
    assert wsl.commands == [["explorer.exe", "file:///c:/Users/damon/Pictures/"]]


def test_wsl_waits_for_explorer_so_the_terminal_is_not_mangled(wsl: Dispatch) -> None:
    """The fix for the terminal being taken over by explorer.exe on WSL2."""

    wsl.run("/mnt/c/Users/damon/Pictures/holiday.jpg")
    assert wsl.waited == wsl.launches


def test_wsl1_does_not_wait_for_explorer(wsl: Dispatch) -> None:
    wsl.configure(platform=LINUX, wsl=True, wsl1=True)
    wsl.run("/mnt/c/Users/damon/Pictures/holiday.jpg")
    assert wsl.waited == []
    assert len(wsl.launches) == 1


def test_an_explicit_linux_file_manager_overrides_the_explorer_route(
    wsl: Dispatch, tmp_path
) -> None:
    target = tmp_path / "holiday.jpg"
    target.write_text("", encoding="utf-8")
    wsl.run(str(target), file_manager="dolphin")
    assert wsl.commands == [["dolphin", "--select", target.as_uri()]]
    assert wsl.shell_calls == []


def test_a_share_uri_with_a_space_reaches_the_manager_in_one_token(
    dispatch: Dispatch,
) -> None:
    """
    The grammar forbids a raw space, so without the smb: prefix bypass this URI was
    taken for a path, found not to exist, and dropped: the manager was never called.
    One token here is the point, since a space left in the command line would make it
    two arguments out of one URI.
    """

    dispatch.run("smb://srv/Backup/media render/holiday.jpg", file_manager="nautilus")
    assert dispatch.commands == [
        ["nautilus", "--select", "smb://srv/Backup/media%20render/holiday.jpg"]
    ]


def test_an_smb_uri_is_handed_to_a_linux_manager_under_wsl_as_it_arrived(
    wsl: Dispatch,
) -> None:
    """
    The caller's half of the decision in linux.wsl_transform_path_uri: nothing can be
    translated for this scheme and nothing should be, because nautilus opens smb://
    itself under WSL exactly as it does on any other Linux install. The record staged
    here is the one that function now returns, so the two halves are pinned together.
    """

    uri = "smb://srv/Backup/media render/holiday.jpg"
    wsl.wsl_reports[uri] = wsl.report(
        linux_path=None, win_path=None, win_uri=None, is_dir=None, is_win_location=False
    )

    wsl.run(uri, file_manager="nautilus")

    assert wsl.commands == [
        ["nautilus", "--select", "smb://srv/Backup/media%20render/holiday.jpg"]
    ]
    assert wsl.shell_calls == []
    assert wsl.startfile_calls == []


def test_an_smb_uri_for_explorer_under_wsl_becomes_a_share_uri(
    wsl: Dispatch,
) -> None:
    """
    The other answer the same function gives: explorer.exe is handed the file://
    spelling of a share, which is the form that survives /select, from WSL. Which
    string Windows accepts is pinned in test_linux.py; which one is launched is here.

    The item is selected rather than opened, because nothing on the Linux side can
    say a share is a directory, and guessing would decide by the name of the share.
    """

    uri = "smb://srv/Backup/media render"
    wsl.wsl_reports[uri] = wsl.report(
        linux_path=None,
        win_path="\\\\srv\\Backup\\media render",
        win_uri="file://srv/Backup/media%20render",
        is_dir=None,
        is_win_location=True,
    )

    wsl.run(uri, file_manager="explorer.exe")

    assert wsl.commands == [
        ["explorer.exe", "/select,file://srv/Backup/media%20render"]
    ]
    assert wsl.startfile_calls == []


@requires_posix_paths
def test_an_explicit_manager_still_receives_a_windows_path(
    wsl: Dispatch,
) -> None:
    """
    A path on the Windows file system goes to explorer.exe by default, but naming a file
    manager suppresses that and the /mnt path is passed on as an ordinary Linux path.
    Drop the not file_manager_specified test from _process_path_or_uri_wsl and
    explorer.exe answers here instead.
    """

    wsl.wsl_reports["/mnt/c/Users/damon/Notes.txt"] = wsl.report(
        is_win_location=True,
        win_uri="file:///c:/Users/damon/Notes.txt",
        linux_path="/mnt/c/Users/damon/Notes.txt",
        is_dir=False,
    )
    wsl.run("/mnt/c/Users/damon/Notes.txt", file_manager="dolphin")
    assert wsl.commands == [
        ["dolphin", "--select", "file:///mnt/c/Users/damon/Notes.txt"]
    ]


def test_a_regular_manager_selecting_a_directory_gets_the_parent(
    dispatch: Dispatch, tmp_path
) -> None:
    """
    A regular file manager has no way to distinguish opening a folder from selecting
    one, so when asked to select it is handed the containing folder instead. Turning
    open_not_select_directory off is what selects a directory, and without this branch
    the directory itself would be opened and nothing selected.
    """

    folder = tmp_path / "trip"
    folder.mkdir()
    dispatch.run(str(folder), file_manager="nemo", open_not_select_directory=False)
    assert dispatch.commands == [["nemo", tmp_path.as_uri()]]


def test_a_missing_path_under_wsl_ends_with_a_bare_launch(wsl: Dispatch) -> None:
    """
    A path that does not exist is dropped before it reaches any bucket, and the empty
    buckets fall through to a launch of the file manager with no argument.
    """

    wsl.wsl_reports["/mnt/c/gone.jpg"] = wsl.report(exists=False, is_win_location=True)
    wsl.run("/mnt/c/gone.jpg")
    assert wsl.commands == [["nautilus"]]
    assert wsl.shell_calls == []


def test_a_windows_path_that_cannot_be_converted_ends_with_a_bare_launch(
    wsl: Dispatch,
) -> None:
    """
    An unconvertible Windows URI is dropped, which empties every bucket, and the last
    block of _launch() then opens the file manager with no path and no switch. So a call
    whose only argument cannot be translated brings up a window rather than doing
    nothing. Recorded as it behaves.
    """

    wsl.wsl_reports["/mnt/c/odd.jpg"] = wsl.report(
        is_win_location=True, win_uri=None, exists=True, is_dir=False
    )
    wsl.run("/mnt/c/odd.jpg")
    assert wsl.commands == [["nautilus"]]


def test_a_linux_path_that_cannot_be_resolved_ends_with_a_bare_launch(
    wsl: Dispatch,
) -> None:
    wsl.wsl_reports["/mnt/c/odd.jpg"] = wsl.report(
        is_win_location=False, win_uri=None, linux_path=None, exists=True, is_dir=False
    )
    wsl.run("/mnt/c/odd.jpg")
    assert wsl.commands == [["nautilus"]]


def test_the_valid_file_manager_is_probed_once_per_instance(
    dispatch: Dispatch, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """
    The latch in _set_valid_file_manager is what stops xdg-mime and the desktop
    detection running again for every path in a batch.
    """

    calls = []
    monkeypatch.setattr(
        filemanager, "valid_file_manager", lambda: calls.append(1) or "dolphin"
    )
    monkeypatch.setattr(
        filemanager, "_file_manager_type", lambda fm: FileManagerType.select
    )
    target = tmp_path / "holiday.jpg"
    target.write_text("", encoding="utf-8")

    fm = filemanager.FileManager()
    for _ in range(3):
        fm.show_in_file_manager(str(target))

    assert len(calls) == 1


def test_no_valid_file_manager_launches_nothing(
    dispatch: Dispatch, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(filemanager, "valid_file_manager", lambda: "")
    target = tmp_path / "holiday.jpg"
    target.write_text("", encoding="utf-8")
    dispatch.run(str(target))
    assert dispatch.launches == []
    assert dispatch.shell_calls == []
    assert dispatch.startfile_calls == []


def test_configuring_an_impossible_machine_is_refused(dispatch: Dispatch) -> None:
    """
    A scenario that contradicts itself would exercise a state no consumer can be in, so
    it has to fail here rather than pass quietly.
    """

    with pytest.raises(AssertionError, match="WSL is reported as Linux"):
        dispatch.configure(platform=WINDOWS, wsl=True, wsl2=True)
    with pytest.raises(AssertionError, match="imply wsl"):
        dispatch.configure(platform=LINUX, wsl2=True)
    with pytest.raises(AssertionError, match="either WSL1 or WSL2"):
        dispatch.configure(platform=LINUX, wsl=True, wsl1=True, wsl2=True)
