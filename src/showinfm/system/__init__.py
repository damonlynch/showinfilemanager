# SPDX-FileCopyrightText: Copyright 2021-2024 Damon Lynch
# SPDX-License-Identifier: MIT

import platform
from typing import Union

from ..constants import Platform
from . import linux

current_platform: Union[Platform, None]
system = platform.system()
is_wsl: bool = False
is_wsl1: bool = False
is_wsl2: bool = False
if system == "Windows":
    current_platform = Platform.windows
elif system == "Linux":
    current_platform = Platform.linux
    if linux.detect_wsl():
        is_wsl = True
        if linux.wsl_version() == linux.LinuxDesktop.wsl2:
            is_wsl2 = True
        else:
            is_wsl1 = True
elif system == "Darwin":
    current_platform = Platform.macos
else:
    current_platform = None
    raise NotImplementedError
