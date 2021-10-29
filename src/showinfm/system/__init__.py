# Copyright (c) 2021 Damon Lynch
# SPDX - License - Identifier: MIT

from ..constants import Platform
import platform
from . import linux

system = platform.system()
is_wsl = False
is_wsl1 = False
is_wsl2 = False
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