from enum import Enum


class FileManagerType(Enum):
    regular = 1         # file_manager "File1" "File2"
    select = 2          # file_manager --select
    dir_only_uri = 3    # cannot select files
    show_item = 4       # file_manager --show-item
    show_items = 5      # file_manager --show-items
    win_select = 6      # explorer.exe /select