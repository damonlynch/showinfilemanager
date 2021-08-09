# Copyright (c) 2021 Damon Lynch
# SPDX - License - Identifier: MIT

__author__ = 'Damon Lynch'
__copyright__ = "Copyright 2021, Damon Lynch"

from ..constants import Platform
import platform
from . import linux

system = platform.system()
if system == "Windows":
    current_platform = Platform.windows
elif system == "Linux":
    if linux.detect_wsl():
        current_platform = Platform.windows
    else:
        current_platform = Platform.linux
elif system == "Darwin":
    current_platform = Platform.macos
else:
    current_platform = None
    raise NotImplementedError