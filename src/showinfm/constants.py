# Copyright (c) 2016-2021 Damon Lynch
# SPDX - License - Identifier: MIT

from enum import Enum


class FileManagerType(Enum):
    regular = 1         # file_manager "File1" "File2"
    select = 2          # file_manager --select
    dir_only_uri = 3    # cannot select files
    show_item = 4       # file_manager --show-item
    show_items = 5      # file_manager --show-items
    win_select = 6      # explorer.exe /select
    reveal = 7          # open --reveal   (macOS)
    dual_panel = 8      # file_manager "File1" "File2"


class Platform(Enum):
    windows = 1
    linux = 2
    macos = 3


single_file_only = ('explorer.exe', 'pcmanfm', 'open', 'cutefish-filemanager')
cannot_open_uris = ('fman', 'fman.exe')