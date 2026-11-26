# Release Notes for Show in File Manager 1.1.7

- Show in File Manager 1.1.6 switched its build system from `setuptools` to [Hatch](https://github.com/pypa/hatch).

  - `hatch build -t sdist` produces an archive of the project's source code.
  - `hatch build -t wheel` produces a wheel (zip archive) of the program's Python code; it also generates the manpage.
  - `hatch check` runs code linting, formatting, and type checks.
  - `hatch test -a` runs the full test suite (as of 1.1.7).

- To generate the manpage, the Hatch plugin [Hatch-argparse-manpage](https://github.com/damonlynch/hatch-argparse-manpage) is used, which is a new build-time dependency. This plugin can be used with any Hatch project, not just Show in File Manager.
