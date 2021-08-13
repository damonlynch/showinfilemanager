# Show in File Manager

**Show in File Manager** is a Python package to open the system file manager and optionally select
files in it. The point is not to _open_ the files, but to _select_ them in the file manager, thereby highlighting the
files and allowing the user to quickly do something with them.

Plenty of programs expose this functionality in their user interface. On Windows terms like "Show in Windows Explorer",
"Show in Explorer", and "Reveal in Explorer" are common. Cross-platform programs use terms like "Open Containing
Folder" or "Open in File Browser":

![Show in Windows Explorer](https://github.com/damonlynch/showinfilemanager/raw/main/.github/photomechanic-win.png)
![Open containing folder](https://github.com/damonlynch/showinfilemanager/raw/main/.github/documentviewer-gnome.png)

The command results in the file manager opening, ideally with the files selected:

![Peony file manager](https://github.com/damonlynch/showinfilemanager/raw/main/.github/peony-kylin.png)

With Show in File Manager, your Python program or command line script can do the same, with minimum effort from you.
Although this package provides several functions to assist in identifying the the system's file managers, in most 
circumstances you need to call only one function, the function `show_in_file_manager`, and it should just work.

This package aspires to be a platform independent, but it currently supports Windows 10/11, Linux, WSL, and macOS.


## How to Install

```bash
python3 -m pip install show-in-file-manager
```

## Rationale

This package solves the following problems:
 - What is the operating system's stock file manager?
 - What is the user's choice of file manager?
 - Is it best to use the stock or user's choice of file manager? 
 - How do I supply command line arguments to select files in the file manager?
 - What about file managers with limited features?  

There is no standard command line argument with which to open an operating system's file manager and select files at a
specified path. Moreover, not all file managers support specifying files to select &mdash;
if you try to pass a file to some file managers, they will open the file instead of selecting it, or worse yet display 
an error message. Some file managers will only allow selecting one file at a time from the command line. 

On desktop Linux the problem is especially acute, as Linux provides a plethora of file managers, with widely varying
command line arguments. Moreover, the user's default file manager can sometimes be incorrectly set to nonsensical 
values, such as an AppImage or Flatpak of a random application.

Windows is not without its share of limitations. Explorer.exe will select only one file at a time when called from the
command line, and the argument must be quoted in a way that it understands. 


## Supported File Managers

|File Manager|Used by|Command line       |Can Select Files|Handles Multiple Files / Directories|Notes|
|------------|-------|-------------------|:---:|:---:|----|
| Windows File Explorer|Windows 10 / 11, Windows Subsystem for Linux (WSL)| `explorer.exe /select,URI`|&#9989;|&#10060;|No space between comma and URI. Can specify only one URI.|
|Finder|macOS|`open --reveal URI`|&#9989;|&#10060;| |
| Nautilus (Files)|Gnome, Pop OS, Zorin|`nautilus --select URI1 URI2`|&#9989;|&#9888;|Multiple URIs open multiple Nautilus windows.|
|Dolphin|KDE|`dolphin --select URI1 URI2 `|&#9989;|&#9989;|A regression in recent KDE releases means `--select` is ignored, but it is fixed in KDE Neon testing.|
|Nemo|Linux Mint|`nemo URI1 URI2`|&#9989;|&#9888;|Multiple URIs open multiple Nemo windows.|
|Pantheon|Elementary OS|`io.elementary.files URI1 URI2`|&#9989;|&#9888;| Multiple URIs open multiple Pantheon tabs.|
|Deepin File Manager|Deepin|`dde-file-manager --show-item URI1 URI2`|&#9989;|&#9888;| Multiple URIs open multiple Deepin File Manager tabs.|
|Peony|Ubuntu Kylin|`peony --show-items URI1 URI2`|&#9989;|&#9989;| |
|Caja|Mate|`caja  URI1 URI2`|&#10060;|&#9888;|Specifying a file causes an error. Multiple URIs open multiple Caja windows.|
|Thunar|XFCE|`thunar URI1 URI2`|&#10060;|&#9888;|Specifying a file opens it. Multiple URIs open multiple Thunar windows.|
|PCManFM|LXDE|`pcmanfm  URI`|&#10060;|&#10060;|Specifying a file opens it. Multiple URIs open only the first URI.|
|PCManFM-Qt|LXQt|`pcmanfm-qt  URI1 URI2`|&#10060;|&#9888;|Specifying a file opens it. Multiple URIs open multiple PCManFM-Qt windows.|

All file managers tested thus far accept URIs like `file:///home/user/file.txt`, as well as regular paths like
`/home/user/file.txt`.

## Usage

### Open the file manager with the files to select

```python
def show_in_file_manager(path_or_uri: Optional[Union[str, Sequence[str]]] = None,
                         open_not_select_directory: Optional[bool] = True,
                         file_manager: Optional[str] = None,
                         verbose: bool = False) -> None:
    """
    Open the file manager and show zero or more directories or files in it.

    The path_or_uri is a sequence of items, or a single item. An item can
    be regular path, or a URI.

    On non-Windows platforms, regular paths will be converted to URIs
    when passed as command line arguments to the file manager, because
    some file mangers do not handle regular paths correctly.

    On Windows or WSL, regular paths are not converted to URIs, but they
    are quoted.

    The most common use of this function is to call it without specifying
    the file manager to use, which defaults to the value returned by
    get_valid_file_manager()

    For file managers unable to select files to display, the file manager
    will instead display the contents of the path.

    For file managers that can handle file selections, but only one at time,
    multiple file manager windows will be opened.

    If you specify a file manager executable and this package does not
    recognize it, it will be called with the files as the only command line
    arguments.

    :param path_or_uri: zero or more files or directories to open, specified
     as a single URI or valid path, or a sequence of URIs/paths.
    :param open_not_select_directory: if the URI or path is a directory and
     not a file, open the directory itself in the file manager, rather than
     selecting it and displaying it in its parent directory.
    :param file_manager: executable name to use. If not specified, then
     get_valid_file_manager() will determine which file manager to use.
    :param verbose: if True print command to be executed before launching
     it
    """
```

Other functions mentioned below are not necessary to call, but are provided for convenience and control.

### Determine the most sensible choice of file manager

```python
def get_valid_file_manager() -> str:
    """
    Get user's file manager, falling back to using sensible defaults for the desktop / OS.

    The user's choice of file manager is the default choice. However, this is not always
    set correctly, most likely because the user's distro has not correctly set the default
    file manager. If the user's choice is unrecognized by this package, then reject it and
    choose the standard file manager for the detected desktop environment.

    All exceptions are caught, except those if this platform is not supported by this package.

    :return: If the user's default file manager is set and it is known by this package, then
    return it. Otherwise return the stock file manager, if it exists. If it does not exist,
    an empty string will be returned.
    """
```

This package makes opinionated choices about the most sensible choice of file manager:
1. A file manager is "valid" if and only if this package recognizes it, e.g. `nautilus`, `explorer.exe`.
2. If the user's choice of file manager is valid, that file manager is used.
3. If the user's choice of file manager is invalid or could not be determined, the desktop or OS's stock file manager 
   is used.


### Get the operating system's stock file manager

```python
def get_stock_file_manager() -> str:
    """
    Get stock file manager for this operating system / desktop.

    On Windows the default is `explorer.exe`. On Linux the first step
    is to determine which desktop is running, and from that lookup its
    default file manager. On macOS, the default is finder, accessed
    via the command 'open'.

    Exceptions are not caught.

    :return: executable name
    """
```

### Get the user's choice of file manager

```python
def get_user_file_manager() -> str:
    """
    Get the file manager as set by the user.

    Exceptions are not caught.

    :return: executable name
    """
```

On Windows and macOS, for now only the stock file manager is returned. That could change in future releases.

On Linux, the file manager is probed using `xdg-mime query default inode/directory`, and the resulting `.desktop` file
is parsed to extract the file manager command. 



## Examples

Show file or directory in file manager, using the most sensible choice of file manager:
```python
show_in_file_manager('C:\Documents\myfile.txt')                                # Windows path
show_in_file_manager('file://C:/Documents/myfile.txt')                         # Windows URI
show_in_file_manager('/home/user/myfile.txt')                                  # Linux path
show_in_file_manager(('/home/user/myfile.txt', '/home/user/other file.txt'))   # Linux multiple paths
show_in_file_manager('file:///home/user/other%20file.txt')                     # Linux URI
show_in_file_manager()                                                         # Simply open the file manager
show_in_file_manager('/home/user')                                             # Open the file manager at a directory
```

## Limitations

 - The code is in a preliminary state. Critiques are welcome.
 - Its behavior in a confined Linux environment like a Flatpak, Snap, or AppImage is untested.

## Contributing

Please file issues or pull requests to improve the code. Discuss improvements in the GitHub discussion section for 
this project.

The initial source of this code is from [Rapid Photo Downloader](https://github.com/damonlynch/rapid-photo-downloader).


## License

[MIT](https://choosealicense.com/licenses/mit/)

  
## Authors

- [@damonlynch](https://github.com/damonlynch)



