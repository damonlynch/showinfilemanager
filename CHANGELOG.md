# Changelog for Show in File Manager

## 1.1.8 (2026-11-28)

- The source archive built by `hatch build -t sdist` now contains the `tests` directory, so a Linux distribution that rebuilds this package from source can run the test suite against the code it is about to install. 
- The archive no longer contains `AGENTS.md`. 
- Nothing about the installed program differs from 1.1.7.

## 1.1.7 (2026-11-27)

- Minimum supported Python version is now 3.11.
- Added pytest coverage for Python versions 3.11–3.15.
- Fix [#39](https://github.com/damonlynch/showinfilemanager/issues/39): Show in File Manager on Windows wrongly assumes successful import of `win32com.shell`.
- Fix the Windows Explorer URIs generated under WSL on recent Python releases:
  `urllib.request.pathname2url()` changed in Python 3.12 for paths beginning with
  two slashes and again in 3.14 for absolute paths, so UNC shares came out with
  four leading slashes and drive paths as `file://nt:/c:/...`.
- A file manager registered in `xdg-mime` but since uninstalled no longer leaves Show in File Manager with no file manager at all; the desktop's stock manager is used instead.
- Fix [#38](https://github.com/damonlynch/showinfilemanager/issues/38): UNC folders become local paths: quoting drops one of the two leading separators.
- Fix `file_uri_to_path()` for network locations: the share name ended up behind two
  separators, which the Windows shell API refuses, and on other platforms the host was
  dropped, so `file://host/share` became the local path `/share`. A network URI built with
  `Path.as_uri()` therefore never opened, so the workaround suggested in issue #38 did not
  work either. `Path.is_dir()` also answered differently for the doubled path on Python
  3.11 and 3.14, so which route the failure took depended on the interpreter.
- Fix `quote_path()` for network paths on Windows: rebuilding the quoted value as a `Path` dropped one of the two leading separators, so any file manager other than Explorer was handed a local path.
- Fix quoted paths ending in a separator on Windows: `C:\` arrived at the file manager as `C:"`, and a second path was swallowed with it.
- Accept `pathlib.Path` and other `os.PathLike` objects as items in `show_in_file_manager()`, which the documentation already implied.
- Fix URIs whose scheme is not `file:` being rewritten as a path, which could open somewhere the URI never named: the host in the URI became a server, and a URI with no path became the root of the filesystem. Such a URI is now passed to the file manager unchanged, which is what the file managers supporting it expect.
- Fix a `file:` URI containing a space being mistaken for a relative path and resolved against the working directory.
- `file_uri_to_path()` now raises `ValueError` for a URI that is not a `file:` URI.
- Accept `smb://` URIs by translating them to the UNC path for the same share, since Windows has no handler for that scheme. A file manager that opens `smb://` itself is given the URI unchanged.
- Fix a share URI under WSL being resolved against the current drive, so `file://server/share` could name a local folder that has nothing to do with the share. Explorer now receives the share, and a URI with a space in it reaches the file manager as one argument rather than two.
- Fix [#4](https://github.com/damonlynch/showinfilemanager/issues/4): a started file manager was reported as still running when this process exited, regardless of whether the child had long finished. Its exit status is now read on each launch and at exit, and the report is turned off for these children, since a file manager is meant to outlive the call. Nothing is waited for.
- The file: URI passed to a file manager on Windows is spelled file:///C:/… again on Python 3.14 and 3.15, where a change in urllib.parse.urljoin() had shortened it to file:/C:/…. Ordinary paths and share locations are unaffected.
- On Windows, a filename containing brackets, which is how screenshot and download tools name their files, was re-read as a glob pattern: `showinfilemanager "C:\Users\me\Desktop\Screenshot [2026-11-26] 091500.png"` opened nothing at all, while a name with a single character class, `holiday[1].jpg`, opened a different file instead. A name that exists is now used as the name it is, and only what nothing answers for is read as a pattern, so `*` and `?` behave exactly as before.
- On Windows, an argument the program could not place ended in a Python traceback rather than a report. An unmapped drive letter, or a network share root that cannot be reached, had its filename globbed anyway, and pathlib refuses a pattern containing nothing; and an `smb` URI naming no server — three separators before the share, as in `smb:///share/file.jpg` — was rejected as malformed. The first now contributes no location, the answer a pattern that matches no file already gave. The second is still refused, but as the message `Not an smb URI naming a share: 'smb:///share/file.jpg'`, which the command writes instead of a traceback.
- A location the system cannot answer for is now treated as no folder and nothing matched, rather than as a failure. Asking whether a network share is a directory can answer with an error instead of yes or no — measured on Windows as `OSError: [WinError 64] The specified network name is no longer available` when a share went away mid-call — and that error used to propagate out of `show_in_file_manager()` as an `OSError` neither its documentation nor the README declares. An argument the program cannot place is left out, whether nothing matched it, it is not there, or the system would not answer for it, and `--debug` names the argument it leaves out.
- `stock_file_manager()` and `user_file_manager()` now raise `FileManagerUnavailableError` for a file manager that is not installed, naming it in the message, instead of a bare `assert`
- `directories_and_their_files()` now raises `InvalidPathsArgumentError`, a new `TypeError` in `showinfm.exceptions`, when a single path arrives as a string instead of in a list: a string is iterable, so grouping it would have answered with one entry per character rather than failing, and the Windows shell API below it selects one file per entry.
- `user_file_manager()` answers with an empty string when the user has no file manager set. A choice that is set but cannot be run raises `FileManagerUnavailableError`, by name.
- Running `showinfilemanager --debug` prints a short report of the file managers found on this system. When the user has no file manager set, the report now states `User's choice: not set`, instead of showing error output as it did previously. The report's last line, `Valid:`, names the file manager the program settles on and then actually runs, unless another is given on the command line. On Linux a valid file manager sometimes cannot be found: neither the file manager registered by the user nor the desktop's stock one is installed, or the desktop cannot be identified — because `XDG_CURRENT_DESKTOP` is unset, or holds a value this package does not recognize — leaving no stock manager to try either. In previous versions the line read `Valid: ` with nothing after it, which looked exactly like a check that never ran. It now reads `Valid: no file manager found`, so the report says in words that no file manager could be found to open the folder.

## 1.1.6 (2026-02-17)

- Support [Cosmic Files](https://github.com/pop-os/cosmic-files).
- Add check for "kde:plasma" in environment variable `XDG_CURRENT_DESKTOP`.
- Fix [#27](https://github.com/damonlynch/showinfilemanager/issues/27): Incorrect behavior when Windows explorer hides file extensions. Thanks to tpl2go for the fix.
- Fix [#29](https://github.com/damonlynch/showinfilemanager/issues/29): Directory names with Unicode do not open correctly in file managers that cannot select files. Thanks to nipatriknilsson for identifying the underlying problem.
- Drop Python 3.8 and 3.9 support. Use Python 3.10+ typing syntax.
- Add `__version__` to package.
- `hatch build -t sdist` now produces an archive of the project's source code.
- `hatch build -t wheel` now produces a wheel (zip archive) of the program's Python code; it also generates the manpage.

## 1.1.6a1 (2024-04-18)

- Update SPDX headers to be compliant with spec.
- Switch to [hatch](https://hatch.pypa.io/latest/) from setuptools.
- New build dependency: [hatch-argparse-manpage](https://github.com/damonlynch/hatch-argparse-manpage).
- Add [Release Notes](RELEASE_NOTES.md).
- Refactor: use absolute imports, not relative.
- Refactor: flatten code by using a new class. The API is unchanged.

## 1.1.5 (2024-03-06)

- Drop setup.py and setup.cfg in favor of pyproject.toml.
- Purge doc directory.
- New build dependency: [argparse-manpage](https://github.com/praiskup/argparse-manpage)
- Generate man page with argparse-manpage instead of pandoc.
- Format and lint using ruff. Drop black.
- Drop Python 3.6 and 3.7 support.

## 1.1.4 (2022-03-04)

- Move debian directory into doc

## 1.1.3 (2022-02-18)

- Fix [#3](https://github.com/damonlynch/showinfilemanager/issues/3): Missing dependency on packaging.

## 1.1.2 (2021-12-27)

- Add check for "unity:unity7:ubuntu" in environment variable XDG_CURRENT_DESKTOP. See https://github.com/damonlynch/rapid-photo-downloader/issues/46.

## 1.1.1 (2021-10-31)

- Add `allow_conversion` switch to `show_in_file_manager()`. Set to False if passing non-standard URIs.
- Recognize non-standard URI prefix 'camera:/', used by KDE.
- Added function `linux_desktop_humanize()`, to make Linux desktop environment variable name values human friendly.

## 1.1.0 (2021-10-29)

- On WSL2, use a Linux file manager (if set) for WSL paths, and Windows Explorer for Windows paths. If no Linux file manager is installed, use Windows Explorer. To override the default choice of using Explorer for Windows paths, simply specify a file manager of your choice.
- On both WSL1 and WSL2, use Windows style URIs to work around a [bug](https://github.com/microsoft/WSL/issues/7603) in WSL where using the /select switch while passing a path with spaces in it fails.
- Don't mess up the terminal when launching Windows Explorer from WSL on Windows Terminal.

## 1.0.1 (2021-10-23)

- Reformat code with black.

## 1.0.0 (2021-10-04)

- Support [Lumina](https://lumina-desktop.org/).

## 0.9.0 (2021-09-08)

- Add option to specify file manager to use from command line.
- Support [Double Commander](https://doublecmd.sourceforge.io/).
- Support [Krusader](https://krusader.org/).
- Support [SpaceFM](https://ignorantguru.github.io/spacefm/).
- Support [fman](https://fman.io/).

## 0.0.8 (2021-08-31)

- Support [CutefishOS](https://en.cutefishos.com/).
- Support [Index File Manager](https://invent.kde.org/maui/index-fm).

## 0.0.7 (2021-08-20)

- Use `--select` command line switch in caja 1.26 or newer.

## 0.0.6 (2021-08-19)

- Remove get\_ prefix from package level function names.

## 0.0.5 (2021-08-19)

- Add setup.py for man page generation.
- Improve README to clarify installation and usage.
- Parse filename globs passed via the command line on Windows.
- Use win32 API to execute explorer.exe on Windows, allowing for multiple file selection.

## 0.0.4 (2021-08-14)

- Update README to include installation instructions.
- Include CHANGELOG.md in package.
- Generate man page for use in Linux.
- Improve command line argument documentation.

## 0.0.3 (2021-08-12)

- Update README.

## 0.0.2 (2021-08-12)

- Move config data from `__about__.py` to static config in `pyproject.toml` [(PEP 621)](https://www.python.org/dev/peps/pep-0621/).
- Added command line arguments `--debug` and `--verbose`.

## 0.0.1 (2021-08-12)

- Initial release.
