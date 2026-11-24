#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

import subprocess

import pytest

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

    def to_windows(self, wsl_path: str, windows_path: str) -> None:
        """
        Answer wslpath -w alone, without teaching the reverse direction.

        Real translations are not symmetric: a path that arrives as
        'c:/Program Files/x' comes back from wslpath -w as 'C:\\Program Files\\x'.
        Tests that depend on that normalisation need to state it rather than get
        the input echoed back at them.

        :param wsl_path: path as it appears to Linux under WSL
        :param windows_path: path as wslpath reports it to Windows
        """

        self._to_windows[wsl_path] = windows_path

    def __call__(
        self, cmd: list[str], *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess:
        program, *arguments = [str(part) for part in cmd]
        if program != "wslpath":
            raise AssertionError(f"unexpected subprocess call for {program}")
        self.calls.append([program, *arguments])
        direction, path = arguments
        table = self._to_wsl if direction == "-u" else self._to_windows
        if path not in table:
            raise subprocess.CalledProcessError(1, cmd)
        return subprocess.CompletedProcess(cmd, 0, table[path].encode(), b"")


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
