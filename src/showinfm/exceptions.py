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
