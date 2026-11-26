#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Never

import pytest

from showinfm import filemanager
from showinfm.system import linux


class FakeWslpath:
    """
    Stand in for subprocess.run so wslpath need not be installed.

    Only wslpath calls are answered. Translations come from a table of paired
    paths; a path that is not in the table raises CalledProcessError, which is how
    a failing wslpath reaches this code, and so lets the untranslatable case be
    tested. Any other program raises AssertionError, because a test that quietly
    depended on a real subprocess would pass or fail by machine rather than by
    design.
    """

    def __init__(self) -> None:
        self._to_wsl: dict[str, str] = {}
        self._to_windows: dict[str, str] = {}
        self.calls: list[list[str]] = []

    def pair(self, windows_path: str, wsl_path: str) -> None:
        """
        Teach the stand-in one Windows path and the WSL path it maps to.

        :param windows_path: path as it appears to Windows
        :param wsl_path: path as it appears to Linux under WSL
        """

        self._to_wsl[windows_path] = wsl_path
        self._to_windows[wsl_path] = windows_path

    def __call__(
        self, cmd: list[str], *_args: object, **_kwargs: object
    ) -> subprocess.CompletedProcess:
        program, *arguments = [str(part) for part in cmd]
        if program != "wslpath":
            msg = f"unexpected subprocess call for {program}"
            raise AssertionError(msg)
        self.calls.append([program, *arguments])
        direction, path = arguments
        table = self._to_wsl if direction == "-u" else self._to_windows
        if path not in table:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0, table[path].encode(), b"")


def _unanswerable() -> OSError:
    """The answer a vanished network location gives, built in one place."""

    return OSError(
        22, "The specified network name is no longer available", None, 64, None
    )


class UnanswerablePath(type(Path())):  # type: ignore[valid-type]
    """
    A location the system cannot answer for, in every way it could be asked.

    The redirector answers a network location that went away mid-call with a code
    pathlib does not swallow -- WinError 64 was measured here, and the swallow list is
    both narrow and moving between releases. Nothing on a quiet machine produces that
    answer on demand, so it is injected rather than hoped for.

    Each question is overridden on its own rather than by overriding stat(), because
    that is not portable: on Python 3.11 is_dir(), exists() and is_file() all route
    through the method, while on 3.14 they do not, and a stat() override there left the
    double answering from the real filesystem -- it reported a folder that was never
    injected. glob() is overridden too, because pathlib's selector asks its own class
    whether the directory it is about to scan is one, which is how a glob carries the
    same error even when the two questions above are guarded.

    Subclassing Path itself is not possible on Python 3.11: the flavour is set by the
    Path() factory, not by inheritance.
    """

    def is_dir(self) -> bool:
        raise _unanswerable()

    def is_file(self) -> bool:
        raise _unanswerable()

    def exists(self) -> bool:
        raise _unanswerable()

    def glob(self, *_args: object, **_kwargs: object) -> Never:
        raise _unanswerable()


@pytest.fixture
def unanswerable_path() -> type:
    """The class, so a scenario can put it on the module attribute the code reads."""

    return UnanswerablePath


@pytest.fixture
def fake_wslpath(monkeypatch: pytest.MonkeyPatch) -> FakeWslpath:
    """
    Answer every wslpath call from FakeWslpath for the duration of a test.

    Patched on the subprocess module the code under test uses, so
    translate_wsl_path() runs for real, including its choice of -u or -w.
    """

    fake = FakeWslpath()
    monkeypatch.setattr(linux.subprocess, "run", fake)
    return fake


@pytest.fixture(autouse=True)
def clear_cached_desktop() -> Iterator[None]:
    """
    Drop the desktop state that would otherwise carry from test to test.

    linux_desktop() is decorated with functools.cache, and stock_linux_file_manager()
    memoises into the _linux_desktop global, so without this the first test to reach
    either one fixes the answer for all the rest and the verdict depends on the order
    the tests happen to run in.
    """

    linux.linux_desktop.cache_clear()
    linux._linux_desktop = None
    yield
    linux.linux_desktop.cache_clear()
    linux._linux_desktop = None


@pytest.fixture(autouse=True)
def isolated_launch_registry() -> Iterator[None]:
    """
    Keep one test's launch records from being read by the next.

    The registry is module level on purpose -- a file manager started here must outlive
    the call -- and _reap_processes() reads every entry in it on each launch. A stand-in
    that cannot answer poll() therefore stays in the list, because the exception happens
    before the entries can be filtered out, and then every later launch in the same
    process fails on it: two incomplete fakes in test_windows.py turned into forty-three
    failures across the suite, in whichever tests happened to run after them. Restoring
    what the list held beforehand keeps an incomplete fake inside the test that made it,
    and keeps the exit hook from reporting one on the way out.
    """

    registry = filemanager._PROCESSES  # one list, held on purpose
    recorded = list(registry)
    yield
    registry[:] = recorded
