#!/usr/bin/python3
# SPDX-FileCopyrightText: Copyright 2021-2024 Damon Lynch
# SPDX-License-Identifier: MIT

__author__ = "Damon Lynch"
__copyright__ = "Copyright 2021-2024, Damon Lynch"

import doctest

from showinfm.system.linux import wsl_transform_path_uri

if __name__ == "__main__":
    doctest.run_docstring_examples(wsl_transform_path_uri, globals())
