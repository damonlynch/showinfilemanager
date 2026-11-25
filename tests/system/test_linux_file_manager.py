#  SPDX-FileCopyrightText: 2016-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

"""
Tests for desktop detection and file manager selection in showinfm.system.linux.

Nothing here reads the machine it runs on: the desktop comes from a set
XDG_CURRENT_DESKTOP, and xdg-mime, the .desktop entries, shutil.which and caja
--version are all answered from below.

Beyond the desktop and file manager tables, the xdg-mime cases cover a registered
handler that cannot be used: no .desktop file, no executable named in it, several
handlers listed in order of preference, an answer with no trailing newline, and no
handler registered at all.
"""

import re
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from showinfm.constants import FileManagerType
from showinfm.system import linux
from showinfm.system.linux import LinuxDesktop


class FakeSubprocess:
    """
    A subprocess namespace holding only what showinfm.system.linux reaches for.

    Assigned to the module rather than to the real subprocess module, so a test
    cannot disturb anything else in the process, including pytest's own workers.
    """

    CalledProcessError = subprocess.CalledProcessError
    PIPE = subprocess.PIPE

    def __init__(self) -> None:
        self.run_output: bytes | None = None
        self.run_error: BaseException | None = None
        self.check_output_result: str | None = None
        self.check_output_error: BaseException | None = None
        self.calls: list[list[str]] = []

    def run(self, cmd: list[str], *args: object, **kwargs: object):
        self.calls.append([str(part) for part in cmd])
        if self.run_error is not None:
            raise self.run_error
        if self.run_output is None:
            raise AssertionError("subprocess.run called with no canned output")
        return subprocess.CompletedProcess(cmd, 0, self.run_output, b"")

    def check_output(self, cmd: list[str], *args: object, **kwargs: object) -> str:
        self.calls.append([str(part) for part in cmd])
        if self.check_output_error is not None:
            raise self.check_output_error
        if self.check_output_result is None:
            raise AssertionError("check_output called with no canned output")
        return self.check_output_result


@pytest.fixture
def fake_subprocess(monkeypatch: pytest.MonkeyPatch) -> FakeSubprocess:
    """Replace the subprocess module the code under test uses with FakeSubprocess."""

    fake = FakeSubprocess()
    monkeypatch.setattr(linux, "subprocess", fake)
    return fake


@pytest.fixture
def xdg_entries(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_subprocess: FakeSubprocess
):
    """
    An XDG setup with two data directories whose .desktop files a test can write.

    The directories are reported in the order a real system lists them, the user's
    before the system's, so a test can tell whether the preference list or the
    directory order drives the search. DesktopEntry stands in for pyxdg's and, like
    it, refuses a path that is not a file, so a candidate that resolves to a
    directory cannot be quietly accepted as a desktop entry.
    """
    user_dir = tmp_path / "user"
    system_dir = tmp_path / "system"
    for data_dir in (user_dir, system_dir):
        (data_dir / "applications").mkdir(parents=True)

    class ParsingError(Exception):
        """Stands in for xdg.Exceptions.ParsingError."""

    class Entry:
        construct_error: BaseException | None = None
        parse_error: BaseException | None = None

        def __init__(self, path: str) -> None:
            if Entry.construct_error is not None:
                raise Entry.construct_error
            if not Path(path).is_file():
                raise OSError(f"{path} is not a file")
            self.text = Path(path).read_text(encoding="utf-8")

        def parse(self, path: str | None = None) -> None:
            if Entry.parse_error is not None:
                raise Entry.parse_error

        def getExec(self) -> str:
            for line in self.text.splitlines():
                if line.startswith("Exec="):
                    return line[len("Exec=") :]
            return ""

    monkeypatch.setattr(linux, "have_xdg", True)
    monkeypatch.setattr(
        linux,
        "BaseDirectory",
        SimpleNamespace(xdg_data_dirs=[str(user_dir), str(system_dir)]),
        raising=False,
    )
    monkeypatch.setattr(linux, "DesktopEntry", Entry, raising=False)
    monkeypatch.setattr(
        linux,
        "xdg",
        SimpleNamespace(Exceptions=SimpleNamespace(ParsingError=ParsingError)),
        raising=False,
    )

    def write(name: str, exec_line: str = "nautilus %U", system: bool = False) -> Path:
        root = system_dir if system else user_dir
        path = root / "applications" / name
        path.write_text(
            f"[Desktop Entry]\nType=Application\nExec={exec_line}\n", encoding="utf-8"
        )
        return path

    def answer(xdg_mime_output: str) -> None:
        fake_subprocess.check_output_result = xdg_mime_output

    return SimpleNamespace(
        answer=answer,
        write=write,
        entry_class=Entry,
        ParsingError=ParsingError,
        subprocess=fake_subprocess,
    )


@pytest.mark.parametrize(
    ("environment", "expected"),
    [
        ("gnome", LinuxDesktop.gnome),
        ("kde", LinuxDesktop.kde),
        ("KDE", LinuxDesktop.kde),
        ("xfce", LinuxDesktop.xfce),
        ("mate", LinuxDesktop.mate),
        ("cosmic", LinuxDesktop.cosmic),
        ("ubuntu:gnome", LinuxDesktop.ubuntugnome),
        ("kde:plasma", LinuxDesktop.kde),
        ("gnome-classic:gnome", LinuxDesktop.gnome),
        ("budgie:gnome", LinuxDesktop.gnome),
        ("pop:gnome", LinuxDesktop.popgnome),
        ("zorin:gnome", LinuxDesktop.zorin),
        ("unity:unity7", LinuxDesktop.unity),
        ("unity:unity7:ubuntu", LinuxDesktop.unity),
        ("x-cinnamon", LinuxDesktop.cinnamon),
    ],
)
def test_desktop_environment_names_a_known_desktop(
    monkeypatch: pytest.MonkeyPatch, environment: str, expected: LinuxDesktop
) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", environment)
    assert linux.linux_desktop() is expected


def test_unrecognised_desktop_environment_names_no_desktop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "wayland")
    with pytest.raises(Exception, match="wayland"):
        linux.linux_desktop()


def test_unset_desktop_environment_falls_back_to_wsl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("XDG_CURRENT_DESKTOP", raising=False)
    monkeypatch.setattr(linux, "wsl_version", lambda: LinuxDesktop.wsl2)
    assert linux.linux_desktop() is LinuxDesktop.wsl2


def test_unset_desktop_environment_off_wsl_has_no_desktop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("XDG_CURRENT_DESKTOP", raising=False)
    monkeypatch.setattr(linux, "wsl_version", lambda: None)
    with pytest.raises(Exception, match="XDG_CURRENT_DESKTOP is not set"):
        linux.linux_desktop()


def test_every_desktop_can_be_spelled_out() -> None:
    """
    Rapid Photo Downloader calls linux_desktop_humanize() on the result of
    linux_desktop(), and it indexes the table by enum name, so a desktop added to the
    enum without a matching name raises at startup.
    """

    for desktop in LinuxDesktop:
        assert linux.linux_desktop_humanize(desktop)


@pytest.mark.parametrize(
    ("desktop", "expected"),
    [
        (LinuxDesktop.gnome, "nautilus"),
        (LinuxDesktop.kde, "dolphin"),
        (LinuxDesktop.mate, "caja"),
        (LinuxDesktop.xfce, "thunar"),
        (LinuxDesktop.lxqt, "pcmanfm-qt"),
        (LinuxDesktop.cosmic, "cosmic-files"),
        (LinuxDesktop.wsl2, "explorer.exe"),
        # these four resolve through LinuxDesktopFamily rather than directly
        (LinuxDesktop.ubuntugnome, "nautilus"),
        (LinuxDesktop.popgnome, "nautilus"),
        (LinuxDesktop.zorin, "nautilus"),
        (LinuxDesktop.unity, "nautilus"),
    ],
)
def test_stock_file_manager_for_a_desktop(
    monkeypatch: pytest.MonkeyPatch, desktop: LinuxDesktop, expected: str
) -> None:
    monkeypatch.setattr(linux, "_linux_desktop", desktop)
    assert linux.stock_linux_file_manager() == expected


def test_unknown_desktop_has_no_stock_file_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(linux, "_linux_desktop", LinuxDesktop.unknown)
    with pytest.raises(Exception, match="unknown"):
        linux.stock_linux_file_manager()


@pytest.mark.parametrize(
    ("manager", "expected"),
    [
        ("nautilus", FileManagerType.select),
        ("dolphin", FileManagerType.select),
        ("nemo", FileManagerType.regular),
        ("io.elementary.files", FileManagerType.regular),
        ("cosmic-files", FileManagerType.regular),
        ("thunar", FileManagerType.dir_only_uri),
        ("pcmanfm", FileManagerType.dir_only_uri),
        ("krusader", FileManagerType.dir_only_uri),
        ("peony", FileManagerType.show_items),
        ("dde-file-manager", FileManagerType.show_item),
        ("doublecmd", FileManagerType.dual_panel),
        ("fman", FileManagerType.dual_panel),
        ("lumina-fm", FileManagerType.dir_only_uri),
    ],
)
def test_argument_style_for_a_known_file_manager(
    manager: str, expected: FileManagerType
) -> None:
    assert linux.linux_file_manager_type(manager) is expected


def test_file_manager_not_in_the_table_gets_plain_arguments() -> None:
    assert linux.linux_file_manager_type("not-a-file-manager") is (
        FileManagerType.regular
    )


def test_caja_from_126_can_select_files(fake_subprocess: FakeSubprocess) -> None:
    fake_subprocess.run_output = b"caja 1.26.0\n"
    assert linux.linux_file_manager_type("caja") is FileManagerType.select


def test_caja_before_126_cannot_select_files(fake_subprocess: FakeSubprocess) -> None:
    fake_subprocess.run_output = b"caja 1.24.1\n"
    assert linux.linux_file_manager_type("caja") is FileManagerType.dir_only_uri


def test_caja_not_installed_cannot_select_files(
    fake_subprocess: FakeSubprocess,
) -> None:
    # caja --version is probed on every call for this manager, so the common case is
    # the binary being absent, which surfaces as FileNotFoundError rather than
    # CalledProcessError
    fake_subprocess.run_error = FileNotFoundError("caja")
    assert linux.linux_file_manager_type("caja") is FileManagerType.dir_only_uri


def test_caja_probe_failure_is_not_fatal(fake_subprocess: FakeSubprocess) -> None:
    fake_subprocess.run_error = subprocess.CalledProcessError(1, ["caja"])
    assert linux.caja_supports_select() is False


def test_caja_version_with_a_banner_is_not_a_version(
    fake_subprocess: FakeSubprocess,
) -> None:
    """
    caja_version() takes everything from the first digit to the end of the output, so
    a version string carrying a product name is not parseable, and the exception
    escapes caja_version() to be absorbed by caja_supports_select(). Whether real
    caja prints such a banner is unverified; this pins the consequence if it does.
    """

    fake_subprocess.run_output = b"caja 1.26.0 (MATE Desktop)\n"
    with pytest.raises(Exception):
        linux.caja_version()
    assert linux.linux_file_manager_type("caja") is FileManagerType.dir_only_uri


def test_caja_output_without_a_digit_cannot_be_compared(
    fake_subprocess: FakeSubprocess,
) -> None:
    fake_subprocess.run_output = b"caja version unknown\n"
    assert linux.caja_version() is None
    assert linux.caja_supports_select() is False


def test_user_file_manager_is_queried_for_directories(xdg_entries) -> None:
    xdg_entries.write("org.gnome.Nautilus.desktop")
    xdg_entries.answer("org.gnome.Nautilus.desktop\n")

    assert linux.user_linux_file_manager() == "nautilus"
    assert xdg_entries.subprocess.calls == [
        ["xdg-mime", "query", "default", "inode/directory"]
    ]


def test_exec_arguments_and_paths_are_stripped_from_the_choice(xdg_entries) -> None:
    xdg_entries.write("nemo.desktop", "/usr/bin/nemo --no-desktop %F")
    xdg_entries.answer("nemo.desktop\n")
    assert linux.user_linux_file_manager() == "nemo"


def test_quoted_exec_programs_are_stripped_of_their_quotes(xdg_entries) -> None:
    xdg_entries.write("thunar.desktop", '"/usr/bin/thunar" %U')
    xdg_entries.answer("thunar.desktop\n")
    assert linux.user_linux_file_manager() == "thunar"


def test_missing_desktop_file_leaves_no_choice(xdg_entries) -> None:
    xdg_entries.answer("absent-file-manager.desktop\n")
    assert linux.user_linux_file_manager() == ""


def test_trailing_semicolon_is_ignored(xdg_entries) -> None:
    xdg_entries.write("peony.desktop", "peony %U")
    xdg_entries.answer("peony.desktop;\n")
    assert linux.user_linux_file_manager() == "peony"


def test_the_first_handler_of_a_list_is_the_users_choice(xdg_entries) -> None:
    """
    xdg-mime lists every accepted handler separated by semicolons, in order of
    preference, so the first is the default. Looking the whole list up as one filename
    matched nothing and dropped the user's configured file manager without a word.
    """

    xdg_entries.write("org.gnome.Nautilus.desktop")
    xdg_entries.write("nemo.desktop", "nemo %U")
    xdg_entries.answer("org.gnome.Nautilus.desktop;nemo.desktop\n")
    assert linux.user_linux_file_manager() == "nautilus"


def test_a_missing_first_handler_falls_through_to_the_next(xdg_entries) -> None:
    """
    Registering a handler is not the same as having it installed: the .desktop file of
    the preferred one can be gone while a later entry in the list is still there, and
    the user's choice is then the next one down rather than the desktop default.
    """

    xdg_entries.write("nemo.desktop", "nemo %U")
    xdg_entries.answer("org.gnome.Nautilus.desktop;nemo.desktop\n")
    assert linux.user_linux_file_manager() == "nemo"


def test_a_stale_override_without_an_executable_falls_through(xdg_entries) -> None:
    """
    The override .desktop file left behind in the user's data directory by an
    uninstalled file manager keeps its place at the head of xdg-mime's list, but names
    no executable, so the handler registered next is the user's real choice rather
    than no choice at all.
    """

    xdg_entries.write("org.kde.dolphin.desktop", "")
    xdg_entries.write("thunar.desktop", "thunar %F")
    xdg_entries.answer("org.kde.dolphin.desktop;thunar.desktop\n")
    assert linux.user_linux_file_manager() == "thunar"


def test_preference_order_outranks_directory_order(xdg_entries) -> None:
    """
    The user's data directory is searched before the system's, but for each handler
    rather than for each list entry, so a preferred handler installed system-wide
    beats a less preferred one the user installed. Swapping that nesting would let the
    user's nemo answer here.
    """

    xdg_entries.write("nemo.desktop", "nemo %U")
    xdg_entries.write("org.gnome.Nautilus.desktop", system=True)
    xdg_entries.answer("org.gnome.Nautilus.desktop;nemo.desktop\n")
    assert linux.user_linux_file_manager() == "nautilus"


def test_no_handler_in_the_list_has_a_desktop_file(xdg_entries) -> None:
    xdg_entries.answer("gone.desktop;also-gone.desktop\n")
    assert linux.user_linux_file_manager() == ""


def test_an_answer_without_a_newline_keeps_its_whole_name(xdg_entries) -> None:
    """
    Whether the answer ends in a newline depends on how check_output decoded it, so the
    name is stripped rather than sliced, and no character is lost when there is no
    newline to remove.
    """

    xdg_entries.write("nemo.desktop", "nemo %U")
    xdg_entries.answer("nemo.desktop")
    assert linux.user_linux_file_manager() == "nemo"


def test_no_handler_configured_yields_no_user_choice(xdg_entries) -> None:
    """
    Nothing is registered for inode/directory wherever there is no desktop, which is
    the usual answer under WSL. An empty answer used to be looked up as a filename,
    which resolves to the applications directory itself, and that exists, so it came
    back as the unreadable desktop entry message in the --debug output instead of as
    no choice.
    """

    xdg_entries.answer("")
    assert linux.user_linux_file_manager() == ""


def test_unreadable_desktop_entry_names_its_own_path(xdg_entries) -> None:
    path = xdg_entries.write("broken.desktop")
    xdg_entries.answer("broken.desktop\n")
    xdg_entries.entry_class.construct_error = OSError("unreadable")

    # match is a regex, and a Windows temp path starts C:\Users, where \U is an
    # invalid escape; on Linux the path needs no escaping, which is why this only
    # fails here
    with pytest.raises(Exception, match=re.escape(str(path))):
        linux.user_linux_file_manager()


def test_unparsable_desktop_entry_is_reported_separately(xdg_entries) -> None:
    xdg_entries.write("malformed.desktop")
    xdg_entries.answer("malformed.desktop\n")
    xdg_entries.entry_class.parse_error = xdg_entries.ParsingError("bad")

    with pytest.raises(Exception, match="Could not parse desktop entry"):
        linux.user_linux_file_manager()


def test_without_pyxdg_there_is_no_user_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(linux, "have_xdg", False)
    with pytest.raises(Exception, match="xdg utilities"):
        linux.user_linux_file_manager()


def test_failing_xdg_mime_leaves_no_user_choice(xdg_entries) -> None:
    xdg_entries.subprocess.check_output_error = OSError("no xdg-mime")
    with pytest.raises(Exception, match="Could not determine file manager"):
        linux.user_linux_file_manager()


def _ladder(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stock: str = "",
    user: str | None = "",
    missing: tuple[str, ...] = (),
) -> str:
    """
    Drive valid_linux_file_manager() with a chosen stock and user answer.

    shutil.which() resolves nothing for an empty name, so the stand-in matches that:
    a stub returning a path for "" would make the empty-name guard in the code under
    test look load-bearing when it is not.

    :param missing: names shutil.which() cannot resolve, so that the user's choice can
     be installed while the stock manager is not, and the other way round
    """

    monkeypatch.setattr(linux, "stock_linux_file_manager", lambda: stock)
    if user is None:

        def user_query_fails() -> str:
            raise Exception("no xdg")

        monkeypatch.setattr(linux, "user_linux_file_manager", user_query_fails)
    else:
        monkeypatch.setattr(linux, "user_linux_file_manager", lambda: user)
    monkeypatch.setattr(
        linux,
        "shutil",
        SimpleNamespace(
            which=lambda name: (
                None if not name or name in missing else f"/usr/bin/{name}"
            )
        ),
    )
    return linux.valid_linux_file_manager()


def test_users_choice_wins_when_the_package_knows_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _ladder(monkeypatch, stock="nautilus", user="dolphin") == "dolphin"


def test_a_choice_the_package_does_not_know_falls_back_to_stock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _ladder(monkeypatch, stock="nautilus", user="konqueror") == "nautilus"


def test_a_failing_user_query_falls_back_to_stock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _ladder(monkeypatch, stock="thunar", user=None) == "thunar"


def test_nothing_installed_yields_no_file_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _ladder(monkeypatch, stock="", user="") == ""


def test_an_uninstalled_choice_yields_no_file_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _ladder(monkeypatch, stock="nautilus", missing=("nautilus",)) == ""


def test_a_stale_user_choice_falls_back_to_the_stock_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A user choice that is not installed does not settle the answer on its own: the
    stock manager is tried as well, and here it is the one that exists.
    """

    assert (
        _ladder(monkeypatch, stock="nautilus", user="dolphin", missing=("dolphin",))
        == "nautilus"
    )


def test_a_stale_override_falls_back_to_the_stock_manager(
    xdg_entries, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The dolphin example end to end, with no stubbed reader: the registered handler's
    .desktop file is intact and names dolphin, which is no longer installed, and the
    desktop's stock manager is. The first assertion is what makes the second mean
    anything, since a fallback would also pass if the override read as nothing.
    """

    xdg_entries.write("org.kde.dolphin.desktop", "dolphin %u")
    xdg_entries.answer("org.kde.dolphin.desktop\n")
    monkeypatch.setattr(linux, "stock_linux_file_manager", lambda: "nautilus")
    monkeypatch.setattr(
        linux,
        "shutil",
        SimpleNamespace(
            which=lambda name: (
                None if not name or name == "dolphin" else f"/usr/bin/{name}"
            )
        ),
    )

    assert linux.user_linux_file_manager() == "dolphin"
    assert linux.valid_linux_file_manager() == "nautilus"
