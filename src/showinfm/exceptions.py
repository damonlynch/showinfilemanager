# SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: MIT

"""
Exceptions raised by this package.

Defined in a module of their own so that callers can import them without
importing platform specific code.
"""


class WindowsShellUnavailableError(RuntimeError):
    """
    Raised when files cannot be selected in Windows File Explorer because the
    win32com.shell module of pywin32 is not usable on this system.

    Selecting files in Windows Explorer is done through the Win32 shell API,
    which this package reaches via win32com.shell. That module can be
    unavailable even when pywin32 is installed: pywin32 registers its
    components in a post-install step which does not run in some environments,
    such as embedded Python distributions and installations that skip build
    scripts. Opening folders without selecting their contents does not use the
    Win32 shell API, so it continues to work.
    """


class LinuxFileManagerError(RuntimeError):
    """
    Base of the errors raised while working out which Linux file manager to use.

    Every failure of the discovery code in showinfm.system.linux is one of these,
    so a caller that only needs to know that no file manager could be settled on
    catches this class. Existing callers that catch Exception continue to work,
    because the discovery code raised a bare Exception until these classes existed.
    """


class DesktopEnvironmentUnknownError(LinuxFileManagerError):
    """
    Raised when the desktop environment cannot be mapped to a stock file manager.

    Either XDG_CURRENT_DESKTOP is not set, or its value is one of the desktops
    this package does not have a file manager for.
    """


class XdgUnavailableError(LinuxFileManagerError):
    """
    Raised when the xdg utilities or the Python bindings for them are not installed.

    The user's choice of file manager is read through xdg-mime and the desktop
    entry files it names, which needs both.
    """


class XdgQueryError(LinuxFileManagerError):
    """
    Raised when xdg-mime runs but does not answer which file manager is registered
    for directories.

    A successful query that reports no registered handler is not this error: that is
    no user choice, and the caller falls back to the stock file manager.
    """


class DesktopEntryError(LinuxFileManagerError):
    """
    Raised when a .desktop entry cannot be read, parsed, or is malformed.

    An entry that reads fine but has no Exec key is not this error: it names no
    program, so the next registered handler is tried instead.
    """
