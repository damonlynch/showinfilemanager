#!/usr/bin/python3
#  SPDX-FileCopyrightText: 2021-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

import doctest
import platform

from showinfm.system.linux import wsl_transform_path_uri

if __name__ == "__main__":
    if platform.system() == "Linux":
        doctest.run_docstring_examples(wsl_transform_path_uri, globals())
