#!/usr/bin/python3
# SPDX-FileCopyrightText: 2021-2024 Damon Lynch <damonlynch@gmail.com>
# SPDX-License-Identifier: MIT

import doctest

from showinfm.system.linux import wsl_transform_path_uri

if __name__ == "__main__":
    doctest.run_docstring_examples(wsl_transform_path_uri, globals())
