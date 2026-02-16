#  SPDX-FileCopyrightText: 2021-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

# ruff: noqa: F401


from showinfm.__about__ import __version__
from showinfm.constants import cannot_open_uris, single_file_only
from showinfm.showinfm import (
    show_in_file_manager,
    stock_file_manager,
    user_file_manager,
    valid_file_manager,
)
from showinfm.system.linux import LinuxDesktop, linux_desktop, linux_desktop_humanize
