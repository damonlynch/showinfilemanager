#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

"""
Run one Windows-shell scenario in a fresh interpreter and report it as JSON.

This is not a test module. tests/system/test_windows.py starts it with
python -m tests.system.windows_probe <mode> [path], one subprocess per scenario.

A new interpreter is the only way to reach these paths honestly.
showinfm.system decides current_platform the first time it is imported, and
showinfm.system.windows decides whether to import win32com.shell at that same
moment, so patching either one part way through a run inspects a module that has
already committed to its answer. The same applies to current_platform's consumers,
which bind it with a from-import and so hold a copy.

Every mode prints one JSON object on stdout and exits zero even when the scenario
contains a failure, so the parent reads what happened instead of inferring it from a
crash. Anything printed by the code under test is captured into the report.
"""

import io
import json
import os
import platform
import sys
import types
from contextlib import redirect_stderr, redirect_stdout

MODE = sys.argv[1]
TARGET = sys.argv[2] if len(sys.argv) > 2 else ""
REPORT: dict[str, object] = {"mode": MODE}


class ImportTracer:
    """Record every attempt to import pywin32, while answering none of them."""

    def __init__(self) -> None:
        self.attempts: list[str] = []

    def find_spec(self, name, path=None, target=None):
        if name == "win32com" or name.startswith("win32com."):
            self.attempts.append(name)
        return None


def pretend_windows() -> None:
    """Make the import-time platform decision take the Windows branch."""

    platform.system = lambda: "Windows"


def pretend_macos() -> None:
    platform.system = lambda: "Darwin"


def block_win32com() -> None:
    """
    Make any pywin32 import fail, whether or not the package is installed.

    None in sys.modules is the interpreter's own signal that an import of that name
    is forbidden, which raises ImportError. Without this the scenario would only
    represent a missing pywin32 on machines that lack it, and would pass on the
    developer's own Windows install.
    """

    for name in ("win32com", "win32com.shell", "win32com.shell.shell"):
        sys.modules[name] = None


def install_fake_shell() -> list:
    """
    Stand in for win32com.shell with the three functions the code calls.

    Returns the log the stand-in appends to, so a test can tell that the shell API
    really was driven, rather than a branch that skipped it.
    """

    calls: list = []
    shell = types.ModuleType("win32com.shell.shell")
    shell.SHILCreateFromPath = lambda path, flags: (
        calls.append(["SHILCreateFromPath", path]) or (f"pidl-{path}", 0)
    )
    shell.SHParseDisplayName = lambda display, unused, reference: (
        calls.append(["SHParseDisplayName", display]) or (f"item-{display}", 0)
    )
    shell.SHOpenFolderAndSelectItems = lambda folder, items, flags: calls.append(
        ["SHOpenFolderAndSelectItems", folder, list(items), flags]
    )
    package = types.ModuleType("win32com.shell")
    package.shell = shell
    root = types.ModuleType("win32com")
    root.shell = package
    sys.modules["win32com"] = root
    sys.modules["win32com.shell"] = package
    sys.modules["win32com.shell.shell"] = shell
    return calls


def report_availability() -> None:
    from showinfm.system import windows

    REPORT["attempted_pywin32_imports"] = list(tracer.attempts)
    REPORT["available"] = windows.windows_shell_available()
    REPORT["status"] = windows.windows_shell_status()


def report_diagnostics() -> None:
    from showinfm.showinfm import Diagnostics

    stdout = io.StringIO()
    with redirect_stdout(stdout):
        text = str(Diagnostics())
    REPORT["diagnostics"] = text


def report_unc_parse() -> None:
    """
    Ask the real shell API to parse a path, without opening anything.

    SHILCreateFromPath is the first call launch_file_explorer() makes and the one that
    refuses a malformed UNC location, so this settles whether a path is acceptable while
    no Explorer window appears. Only the real module answers, since the fake shell the
    other scenarios install records calls rather than parsing them.
    """

    from showinfm.system import windows

    REPORT["available"] = windows.windows_shell_available()
    if windows._shell is None:
        REPORT["error"] = "win32com.shell was not imported"
        return
    try:
        pidl = windows._shell.SHILCreateFromPath(TARGET, 0)[0]
    except Exception as e:
        REPORT["error"] = f"{type(e).__name__}: {e}"
    else:
        REPORT["error"] = None
        REPORT["parsed"] = bool(pidl)


def report_abort() -> None:
    from showinfm.system import windows

    try:
        windows.launch_file_explorer([TARGET])
    except Exception as e:
        REPORT["raised"] = type(e).__name__
        REPORT["message"] = str(e)
    else:
        REPORT["raised"] = None


def report_launch() -> None:
    from showinfm.system import windows

    windows.launch_file_explorer([TARGET])
    REPORT["shell_calls"] = SHELL_CALLS


def report_folder_only() -> None:
    """Opening a folder on Windows needs no pywin32, so it must not abort."""

    import showinfm

    opened: list = []
    os.startfile = lambda path: opened.append(path)
    errors: list = []
    try:
        showinfm.show_in_file_manager(TARGET)
    except Exception as e:
        errors.append(f"{type(e).__name__}: {e}")
    REPORT["startfile"] = opened
    REPORT["errors"] = errors


def report_cli() -> None:
    from showinfm.showinfm import main

    sys.argv = ["showinfilemanager", TARGET]
    stderr = io.StringIO()
    code = "returned"
    try:
        with redirect_stderr(stderr):
            main()
    except SystemExit as e:
        code = e.code
    REPORT["exit_code"] = code
    REPORT["stderr"] = stderr.getvalue()


tracer = ImportTracer()
sys.meta_path.insert(0, tracer)
SHELL_CALLS: list = []

if MODE in ("as_is", "darwin"):
    if MODE == "darwin":
        pretend_macos()
    import showinfm.system.windows  # noqa: F401  the import is the subject

    report_availability()
    report_diagnostics()
elif MODE == "windows_attempt":
    # Nothing blocked or faked: this is the positive control for the tracer. The
    # other scenarios prove no import happens off Windows only because this one
    # shows an import is recorded when it does happen.
    pretend_windows()
    report_availability()
elif MODE == "windows_missing":
    pretend_windows()
    block_win32com()
    report_availability()
    report_abort()
    report_diagnostics()
elif MODE == "windows_present":
    pretend_windows()
    # Bound before the import, because that is the moment the module binds _shell
    SHELL_CALLS = install_fake_shell()
    report_availability()
    report_launch()
elif MODE == "windows_folder_only":
    pretend_windows()
    block_win32com()
    report_folder_only()
elif MODE == "unc_parse":
    # No pretend_windows() here: this scenario answers for the machine it runs on, which
    # is the only way the shell API's own verdict on a UNC path is worth anything.
    report_unc_parse()
elif MODE in ("cli_missing", "cli_present"):
    pretend_windows()
    if MODE == "cli_missing":
        block_win32com()
    else:
        install_fake_shell()
    report_cli()
else:
    raise AssertionError(f"unknown scenario: {MODE}")

print(json.dumps(REPORT))
