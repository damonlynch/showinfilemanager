Changelog for Show in File Manager
==================================

1.1.4 (2022-03-04)
------------------
 - Move debian directory into doc

1.1.3 (2022-02-18)
------------------
 - Fix bug [#3](https://github.com/damonlynch/showinfilemanager/issues/3):
   Missing dependency on packaging.

1.1.2 (2021-12-27)
------------------
 - Add check for "unity:unity7:ubuntu" in environment variable
   XDG_CURRENT_DESKTOP. 
   See https://github.com/damonlynch/rapid-photo-downloader/issues/46.

1.1.1 (2021-10-31)
------------------
 - Add `allow_conversion` switch to `show_in_file_manager()`. Set to False 
   if passing non-standard URIs.
 - Recognize non-standard URI prefix 'camera:/', used by KDE.
 - Added function `linux_desktop_humanize()`, to make Linux desktop environment 
   variable name values human friendly.

1.1.0 (2021-10-29)
------------------
 - On WSL2, use a Linux file manager (if set) for WSL paths, and Windows 
   Explorer for Windows paths. If no Linux file manager is installed, use 
   Windows Explorer. To override the default choice of using Explorer for 
   Windows paths, simply specify a file manager of your choice.
 - On both WSL1 and WSL2, use Windows style URIs to work around a
   [bug](https://github.com/microsoft/WSL/issues/7603) in WSL where using 
   the /select switch while passing a path with spaces in it fails.
 - Don't mess up the terminal when launching Windows Explorer from WSL 
   on Windows Terminal.
 
1.0.1 (2021-10-23)
-----------------
 - Reformat code with black.

1.0.0 (2021-10-04)
------------------
 - Support [Lumina](https://lumina-desktop.org/).

0.9.0 (2021-09-08)
------------------
 - Add option to specify file manager to use from command line.
 - Support [Double Commander](https://doublecmd.sourceforge.io/).
 - Support [Krusader](https://krusader.org/).
 - Support [SpaceFM](https://ignorantguru.github.io/spacefm/).
 - Support [fman](https://fman.io/).

0.0.8 (2021-08-31)
------------------
 - Support [CutefishOS](https://en.cutefishos.com/).
 - Support [Index File Manager](https://invent.kde.org/maui/index-fm).

0.0.7 (2021-08-20)
------------------
 - Use `--select` command line switch in caja 1.26 or newer.

0.0.6 (2021-08-19)
------------------
 - Remove get_ prefix from package level function names.

0.0.5 (2021-08-19)
------------------
 - Add setup.py for man page generation.
 - Improve README to clarify installation and usage.
 - Parse filename globs passed via the command line on Windows.
 - Use win32 API to execute explorer.exe on Windows, allowing for
   multiple file selection.

0.0.4 (2021-08-14)
------------------
 - Update README to include installation instructions.
 - Include CHANGELOG.md in package.
 - Generate man page for use in Linux.
 - Improve command line argument documentation.

0.0.3 (2021-08-12)
------------------
 - Update README.

0.0.2 (2021-08-12)
------------------
 - Move config data from `__about__.py` to static config in 
   `pyproject.toml` [(PEP 621)](https://www.python.org/dev/peps/pep-0621/).
 - Added command line arguments `--debug` and `--verbose`.

0.0.1 (2021-08-12)
------------------
 - Initial release.
