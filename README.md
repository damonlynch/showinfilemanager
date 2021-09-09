# Show in File Manager

**Show in File Manager** is a Python package to open the system file manager and optionally select
files in it. The point is not to _open_ the files, but to _select_ them in the file manager, thereby highlighting the
files and allowing the user to quickly do something with them.

Plenty of programs expose this functionality in their user interface. On Windows terms like "Show in Windows Explorer",
"Show in Explorer", and "Reveal in Explorer" are common. Cross-platform programs use terms like "Open Containing
Folder" or "Open in File Browser":

![Show in Windows Explorer](https://github.com/damonlynch/showinfilemanager/raw/main/.github/photomechanic-win.png)
![Open containing folder](https://github.com/damonlynch/showinfilemanager/raw/main/.github/documentviewer-gnome.png)

A command like "Open in File Browser" results in the file manager opening, ideally with the files selected:

![Peony file manager](https://github.com/damonlynch/showinfilemanager/raw/main/.github/peony-kylin.png)

With **Show in File Manager**, your Python program or command line script can do the same, with minimum effort from you.
Although this package provides several functions to assist in identifying the the system's file managers, in most 
circumstances you need to call only one function, the function `show_in_file_manager`, and it should just work.

This package aspires to be platform independent, but it currently supports only Windows 10/11, Linux, WSL, and macOS. It
works with 18 [supported file managers](#supported-file-managers).


## How to install and run

```bash
python3 -m pip install show-in-file-manager
```

Generate the man page:
```bash
python3 setup.py build_pandoc
```

You can import it as a Python module:
```python
from showinfm import show_in_file_manager
show_in_file_manager('/home/user/file.txt')
```

Or run it from the command line:
```bash
showinfilemanager file1.txt file2.txt
```

```commandline
showinfilemanager.exe D:\Documents\*.docx
```

More [examples](#examples) are below.

## Rationale

This package solves the following problems:
 - What is the operating system's stock file manager?
 - What is the user's choice of file manager?
 - Is the user's choice of file manager set correctly? 
 - How do I supply command line arguments to select files in the file manager?
 - What about file managers with limited features?  

There is no standard command line argument with which to open an operating system's file manager and select files at a
specified path. Moreover, not all file managers support specifying files to select &mdash;
if you try to pass a file to some file managers, they will open the file instead of selecting it, or worse yet display 
an error message. Some file managers will only allow selecting one file at a time from the command line. 

On desktop Linux the problem is especially acute, as Linux provides a plethora of file managers, with widely varying
command line arguments. Moreover, the user's default file manager can sometimes be incorrectly set to nonsensical 
values, such as an AppImage or Flatpak of a random application.

Windows is not without its share of limitations. `explorer.exe` will select only one file at a time when called from the
command line, and the argument must be quoted in a way that it understands. Rather than using the command line, this
package instead uses the [Win32 API](https://docs.microsoft.com/en-us/windows/win32/api/shlobj_core/nf-shlobj_core-shopenfolderandselectitems)
to programmatically select multiple files. Using the Win32 API is not possible when calling `explorer.exe` from within
WSL &mdash; this package will launch `explorer.exe` using the command line under WSL. 


## Supported file managers

This package takes care of calling the file managers with the correct arguments for you. The command line arguments
shown here are for reference. 

Almost all file managers accept [URIs](https://en.wikipedia.org/wiki/Uniform_Resource_Identifier)
like `file:///home/user/file.txt` in addition to regular paths like `/home/user/file.txt`.

|File Manager|Used by|Command line       |Can Select Files|Handles Multiple Files / Directories|Notes|
|------------|-------|-------------------|:---:|:---:|----|
| Windows File Explorer|Windows 10 / 11, Windows Subsystem for Linux (WSL)| `explorer.exe /select,URI`|&#9989;|&#9888;|No space between comma and URI. Can specify only one URI via the command line, but multiple files can be specified via the Win32 API.|
|Finder|macOS|`open --reveal URI`|&#9989;|&#10060;| |
|[Nautilus (Files)](https://gitlab.gnome.org/GNOME/nautilus)|Gnome, Pop!_OS, Zorin|`nautilus --select URI1 URI2`|&#9989;|&#9888;|Multiple URIs open multiple Nautilus windows. See [issue #1955](https://gitlab.gnome.org/GNOME/nautilus/-/issues/1955).|
|[Dolphin](https://github.com/KDE/dolphin)|KDE|`dolphin --select URI1 URI2 `|&#9989;|&#9989;|A regression in recent KDE releases means `--select` is ignored, but it is fixed in KDE Neon testing.|
|[Nemo](https://github.com/linuxmint/nemo)|Linux Mint|`nemo URI1 URI2`|&#9989;|&#9888;|Multiple URIs open multiple Nemo windows. Cannot select folders.|
|[Elementary OS Files](https://github.com/elementary/files)|Elementary OS|`io.elementary.files URI1 URI2`|&#9989;|&#9888;| Multiple URIs open multiple Files tabs. Cannot select folders.|
|[Deepin File Manager](https://github.com/linuxdeepin/dde-file-manager)|Deepin|`dde-file-manager --show-item URI1 URI2`|&#9989;|&#9888;| Multiple URIs open multiple Deepin File Manager tabs.|
|[Peony](https://github.com/ukui/peony)|Ubuntu Kylin|`peony --show-items URI1 URI2`|&#9989;|&#9989;| |
|[Caja](https://github.com/mate-desktop/caja)|Mate|`caja --select URI1 URI2`|&#9888;|&#9888;|Starting with 1.26, can select a file or folder using `--select`. In all versions, specifying a file without this switch causes an error. Multiple URIs open multiple Caja windows. See [issue #1547](https://github.com/mate-desktop/caja/issues/1547).|
|[Thunar](https://gitlab.xfce.org/xfce/thunar)|XFCE|`thunar URI1 URI2`|&#10060;|&#9888;|Specifying a file opens it. Multiple URIs open multiple Thunar windows.|
|PCManFM|LXDE|`pcmanfm  URI`|&#10060;|&#10060;|Specifying a file opens it. Multiple URIs open only the first URI.|
|[PCManFM-Qt](https://github.com/lxqt/pcmanfm-qt)|LXQt|`pcmanfm-qt URI1 URI2`|&#10060;|&#9888;|Specifying a file opens it. Multiple URIs open multiple PCManFM-Qt windows.|
|[CutefishOS File Manager](https://github.com/cutefishos/filemanager)|CutefishOS|`cutefish-filemanager`|&#10060;|&#10060;|Specifying a file causes File Manager to attempt to open it as if it is a folder. Multiple URIs open only the first URI.|
|[Index](https://invent.kde.org/maui/index-fm)|Linux|`index URI1 URI2` |&#10060;|&#10060;|Specifying a file has no effect. Multiple URIs open multiple tabs, in addition to the user's home directory, which is always opened.|
|[Double Commander](https://doublecmd.sourceforge.io/)|Windows, Linux|`doublecmd URI1 URI2`|&#9989;|&#9888;|A double panel file manager accepting up to two URIs. Cannot select folders.|
|[Krusader](https://krusader.org/)|KDE|`krusader URI`|&#10060;|&#9888;|A double panel file manager accepting one URI. Two URIs can be specified using `--left` and `--right`, but that is unsupported by this package. Specifying a file causes an error.|
|[SpaceFM](https://ignorantguru.github.io/spacefm/)|Linux|`spacefm URI1 URI2`|&#10060;|&#9989;|Specifying a file opens it.|
|[fman](https://fman.io/)|Windows, Linux, macOS|`fman path1 path2`|&#9989;|&#9888;|A double panel file manager accepting up to two paths. Cannot select folders. Does not accept URIs.|


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
    valid_file_manager()

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
     valid_file_manager() will determine which file manager to use.
    :param verbose: if True print command to be executed before launching
     it
    """
```

Other functions mentioned below are not necessary to call, but are provided for convenience and control.

### Determine the most sensible choice of file manager

```python
def valid_file_manager() -> str:
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
1. A file manager is valid if and only if this package recognizes it, e.g. `nautilus`, `explorer.exe`.
2. If the user's choice of file manager is valid (i.e. an actual file manager, not some random application), that file
   manager is used.
3. If the user's choice of file manager is invalid or could not be determined, the desktop or OS's stock file manager 
   is used.


### Get the operating system's stock file manager

```python
def stock_file_manager() -> str:
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
def user_file_manager() -> str:
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

From Python, show file or directory in file manager, using the most sensible choice of file manager:
```python
show_in_file_manager('C:\Documents\myfile.txt')                               # Windows path
show_in_file_manager('file://C:/Documents/myfile.txt')                        # Windows URI
show_in_file_manager('/home/user/myfile.txt')                                 # Linux path
show_in_file_manager(('/home/user/myfile.txt', '/home/user/other file.txt'))  # Linux multiple paths
show_in_file_manager('file:///home/user/other%20file.txt')                    # Linux URI
show_in_file_manager()                                                        # Simply open the file manager
show_in_file_manager('/home/user')                                            # Open the file manager at a directory
show_in_file_manager('/home/user', open_not_select_directory=False)           # Select the user directory in the home folder
```

Open the system home directory (`/home` on Linux, `/Users` on macOS) and select the user's home folder in it:
```bash
showinfilemanager -s ~
```
Open the user's home directory directly, without selecting it:
```bash
showinfilemanager ~
```
Select files in two different directories, and open a third directory:
```bash
showinfilemanager myfile.txt ../anotherfile.txt ../../
```
The previous command will open three different instances of the file manager, because of three different directories
(macOS users may need to adjust finder preferences in order to display multiple finder windows).

## Limitations

 - Its behavior in a confined Linux environment like a Flatpak, Snap, or AppImage is untested.
 - On WSL, it currently only opens explorer.exe &mdash; running a Linux file manager under WSL2 is currently not
   supported.

## Contributing

Please file issues or pull requests to improve the code. Discuss improvements in the GitHub discussion section for 
this project.

The initial source of this code is from [Rapid Photo Downloader](https://github.com/damonlynch/rapid-photo-downloader).


## License

[MIT](https://choosealicense.com/licenses/mit/)

  
## Authors

- [@damonlynch](https://github.com/damonlynch)



