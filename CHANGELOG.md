Changelog for Show in File Manager
==================================

0.9.0 (2021-09-08)
------------------
 - Add option to specify file manager to use from command line
 - Support [Double Commander](https://doublecmd.sourceforge.io/)
 - Support [Krusader](https://krusader.org/)
 - Support [SpaceFM](https://ignorantguru.github.io/spacefm/)
 - Support [fman](https://fman.io/)

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