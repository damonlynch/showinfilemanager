# Copyright (c) 2021 Damon Lynch
# SPDX - License - Identifier: MIT

from ..constants import Platform
import platform
from . import linux

system = platform.system()
is_wsl = False
if system == "Windows":
    current_platform = Platform.windows
elif system == "Linux":
    if linux.detect_wsl():
        current_platform = Platform.windows
        is_wsl = True
    else:
        current_platform = Platform.linux
elif system == "Darwin":
    current_platform = Platform.macos
else:
    current_platform = None
    raise NotImplementedError