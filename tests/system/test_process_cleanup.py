#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

"""
Tests that a started file manager is neither waited for nor left unread.

The case these are built around is a file manager that outlives the call, which is
the normal case and the one that a first attempt at this got wrong: stand-ins that
finish promptly pass against code that warns in use. The outliving cases therefore run
in a child interpreter and assert on what that interpreter printed, because the report
belongs to the interpreter that shuts down.

The child's output goes to a file rather than a pipe: the manager inherits the
handle, so a pipe would stay open until it exits and the parent would wait for
nothing. The stand-ins are chosen to work with their output redirected, and every
case kills its own child again.

macOS takes the same path as Linux here and is not exercised on this machine.
"""

import os
import signal
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from showinfm import filemanager

if sys.platform == "win32":
    # One item per launch: the package builds one command line from the manager,
    # its argument and the item, so a list of separate arguments would become
    # separate launches.
    DONE = ("cmd", ["/c exit"])
    BUSY = ("ping", ["-n 30 127.0.0.1"])
else:
    DONE = ("true", [""])
    BUSY = ("sleep", ["30"])

REPO_SRC = str(Path(filemanager.__file__).parent.parent)

CHILD = """
import sys, time
sys.path.insert(0, {src!r})
from showinfm import filemanager

m = filemanager.FileManager()
m.file_manager, m.arg, m.verbose, m.debug = {manager!r}, {arg!r}, False, False
filemanager.is_wsl2 = False
m._launch_file_manager({items!r})
print("PID", filemanager._PROCESSES[-1].pid, flush=True)
print("exiting with", len(filemanager._PROCESSES), "listed", flush=True)
time.sleep({grace})
"""


def run_child(tmp_path: Path, spec: tuple[str, list[str]], grace: float) -> str:
    """Launch the library in another interpreter and return everything it wrote."""
    manager, items = spec
    script = tmp_path / "child.py"
    script.write_text(
        CHILD.format(
            src=REPO_SRC,
            manager=manager,
            arg="",
            items=items,
            grace=grace,
        ),
        encoding="utf-8",
    )
    out = tmp_path / "child.out"
    with out.open("w", encoding="utf-8") as handle:
        subprocess.run(
            [sys.executable, "-X", "dev", str(script)],
            stdout=handle,
            stderr=handle,
            timeout=180,
            check=False,
        )
    text = out.read_text(encoding="utf-8")
    kill_after = [
        int(line.split()[1]) for line in text.splitlines() if line.startswith("PID ")
    ]
    for pid in kill_after:
        _kill(pid)
    return text


def _kill(pid: int) -> None:
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"], capture_output=True, check=False
            )
        else:
            os.kill(pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass  # already gone, which is the hope


@pytest.fixture(autouse=True)
def empty_registry() -> Iterator[None]:
    """Leave no references, and no unreaped child, from one test to the next.

    The wait after the kill matters: nothing reaps these for us any more, so a
    dropped reference here would leave a zombie for the rest of the session and
    the next test would count it as its own.
    """

    def drain() -> None:
        for process in filemanager._PROCESSES:
            process.kill()
        for process in filemanager._PROCESSES:
            process.wait()
        filemanager._PROCESSES.clear()

    drain()
    yield
    drain()


def launch(spec: tuple[str, list[str]]) -> None:
    manager, items = spec
    filemanager.is_wsl2 = False
    m = filemanager.FileManager()
    m.file_manager, m.arg, m.verbose, m.debug = manager, "", False, False
    m._launch_file_manager(list(items))


def test_a_launch_keeps_no_finalizer_to_report_it() -> None:
    """
    The mechanism the rest depends on: an object started here carries no finalizer, so
    nothing can call it out as still running when this interpreter ends.
    """

    launch(BUSY)
    process = filemanager._PROCESSES[-1]

    assert "__del__" in vars(type(process))
    assert type(process).__del__ is not subprocess.Popen.__del__
    assert isinstance(process, subprocess.Popen)


def test_a_started_file_manager_is_not_waited_for() -> None:
    """
    Reaping must not quietly become waiting: the launch returns while the child runs.
    """

    started = time.monotonic()
    launch(BUSY)

    assert time.monotonic() - started < 2.0
    assert filemanager._PROCESSES[-1].poll() is None


def test_the_registry_keeps_only_the_file_managers_still_running() -> None:
    """
    A long series of launches accumulates nothing: each one notes the status of the
    ones before it. Asserted as never more than one, since a child that finishes in
    microseconds can be read by its own launch.
    """

    for _ in range(8):
        launch(DONE)
        time.sleep(0.2)

    assert len(filemanager._PROCESSES) <= 1
    assert all(p.returncode is None for p in filemanager._PROCESSES)


@pytest.mark.skipif(sys.platform == "win32", reason="no zombie processes on Windows")
def test_finished_children_are_reaped_rather_than_left_as_zombies() -> None:
    """
    With no finalizer, this package is the only thing that reads a status, so the
    registry has to do it. Unreaped children would show as zombies parented here:
    counted rather than assumed, and bounded by one because each launch reads the
    ones before it.
    """

    for _ in range(8):
        launch(DONE)
        time.sleep(0.15)

    assert _zombie_children() <= 1
    filemanager._reap_processes()
    assert _zombie_children() == 0


def _zombie_children() -> int:
    listing = subprocess.run(
        ["ps", "-eo", "pid,ppid,stat,comm"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    mine = str(os.getpid())
    return sum(
        1
        for line in listing.splitlines()
        if len(line.split()) >= 3
        and line.split()[1] == mine
        and line.split()[2].startswith("Z")
    )


def test_no_report_when_the_file_manager_outlives_the_caller(
    tmp_path: Path,
) -> None:
    """
    The case that a first attempt missed: the manager is still running when the
    interpreter exits, so there is no status to note and no later launch to note it.
    Measured in a child interpreter, since the report is raised as that interpreter
    shuts down.

    Both complaints are asserted absent, not just the warning. A first attempt traded
    the ResourceWarning for a TypeError from a None finalizer, which a search for the
    warning alone would have called a pass.
    """

    text = run_child(tmp_path, BUSY, grace=0.0)

    assert "exiting with 1 listed" in text, text
    assert "ResourceWarning" not in text, text
    assert "Exception ignored" not in text, text


def test_no_report_when_the_file_manager_finished_first(tmp_path: Path) -> None:
    """
    The mirror case: the child is gone before the caller, and its status was read by
    the exit hook rather than left to be guessed at.
    """

    text = run_child(tmp_path, DONE, grace=1.0)

    assert "exiting with" in text, text
    assert "ResourceWarning" not in text, text
    assert "Exception ignored" not in text, text
