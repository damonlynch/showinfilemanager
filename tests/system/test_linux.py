#  SPDX-FileCopyrightText: 2016-2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

"""
Tests for the WSL path and URI translation in showinfm.system.linux, converted
from the doctest in wsl_transform_path_uri().

Two layers. The hermetic one answers wslpath from a table and takes any path that
has to exist from tmp_path, so every expectation is an exact string rather than a
pattern, and it runs on any interpreter on a POSIX machine. The live layer needs a
WSL installation and is skipped without one, because it is the only place that
checks the real wslpath against those expectations.

The retired doctest masked both of these with ellipsis matching and with
expressions such as "r.is_dir if r.exists else True", which pass when the path is
absent. Existence is a stated premise here, never a condition an assertion
accommodates.
"""

import platform
import re
import shutil
from pathlib import Path

import pytest

from showinfm.system.linux import (
    _quote_path_for_uri,
    wsl_path_to_uri_for_windows_explorer,
    wsl_transform_path_uri,
)
from tests.conftest import FakeWslpath

# This code is the WSL route, which native Windows never takes. On a Windows
# interpreter a temporary directory also reads as file:///C:/..., which the code
# classifies as a Windows URI rather than a POSIX one, so the expectations below
# would describe a different branch. Replaces the guard the retired doctest carried:
# assert platform.system() == "Linux".
pytestmark = pytest.mark.skipif(
    platform.system() == "Windows",
    reason="WSL path translation is only reachable from Linux",
)

# Stands in for a path on a mounted Windows drive that does not exist. /mnt holds
# only drives Windows actually has, so no machine can produce this one.
ABSENT = "/mnt/c/show-in-file-manager-tests-absent"

REAL_WSL = shutil.which("wslpath") is not None and Path("/mnt/c/Program Files").is_dir()

requires_wsl = pytest.mark.skipif(
    not REAL_WSL,
    reason="needs a live WSL installation with /mnt/c/Program Files",
)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/mnt/c/Program Files", "file:///c:/Program%20Files"),
        ("/mnt/c/Program Files/", "file:///c:/Program%20Files/"),
        ("/mnt/c", "file:///c:/"),
        ("/mnt/c/", "file:///c:/"),
        (
            "/mnt/c/Program Files/Common Files",
            "file:///c:/Program%20Files/Common%20Files",
        ),
        (
            "/mnt/d/Users/Damon Lynch/My Photos",
            "file:///d:/Users/Damon%20Lynch/My%20Photos",
        ),
        ("/mnt/C/Foobar", "file:///C:/Foobar"),
        ("/mnt/e/Unicode Ω dir", "file:///e:/Unicode%20%CE%A9%20dir"),
        ("/mnt/c/we?rd#case", "file:///c:/we%3Frd%23case"),
        ("/mnt/c/100%25sure", "file:///c:/100%2525sure"),
    ],
)
def test_explorer_uri_for_a_mounted_drive_path(path: str, expected: str) -> None:
    assert wsl_path_to_uri_for_windows_explorer(path) == expected


@pytest.mark.parametrize(
    "path",
    [
        "/mnt/c/Program Files",
        "/mnt/c",
        "/mnt/c/Program Files/Common Files",
        "/mnt/d/Users/Damon Lynch/My Photos",
        "/mnt/c/we?rd#case",
    ],
)
def test_explorer_uri_drive_component_is_one_character(path: str) -> None:
    """
    What the Python 3.14 defect broke. pathname2url() gained two leading slashes,
    so the slice that extracted the drive letter returned 'nt' and the URI came out
    as file://nt:/c:/Program%20Files. Whatever else changes, exactly one character
    must sit between file:/// and the colon.
    """

    uri = wsl_path_to_uri_for_windows_explorer(path)
    assert re.match(r"^file:///[^:/]{1}:/", uri), uri


def test_explorer_uri_rejects_unc_paths() -> None:
    with pytest.raises(AssertionError):
        wsl_path_to_uri_for_windows_explorer(r"\\wsl.localhost\Ubuntu\home")


def test_explorer_uri_rejects_paths_outside_mnt() -> None:
    with pytest.raises(AssertionError):
        wsl_path_to_uri_for_windows_explorer("/home/damon/file.txt")


def test_uri_encoding_leaves_slashes_alone() -> None:
    """
    Pins the replacement for pathname2url(). It was literally quote(pathname) on
    every Python up to and including 3.13, and the extra slashes 3.14 adds are what
    shifted the drive letter.
    """

    assert _quote_path_for_uri("/mnt/c/x y") == "/mnt/c/x%20y"
    assert _quote_path_for_uri("//wsl.localhost/Ubuntu/home") == (
        "//wsl.localhost/Ubuntu/home"
    )


def test_windows_path_input_is_located_on_the_windows_filesystem(
    fake_wslpath: FakeWslpath,
) -> None:
    windows_path = r"C:\Program Files"
    fake_wslpath.pair(windows_path, ABSENT)

    result = wsl_transform_path_uri(windows_path, True)

    assert result.linux_path == ABSENT
    assert result.is_win_location is True
    assert result.exists is False
    assert result.is_dir is None
    assert result.win_path == windows_path
    assert result.win_uri == "file:///c:/show-in-file-manager-tests-absent"


def test_only_the_requested_direction_of_translation_is_called(
    fake_wslpath: FakeWslpath,
) -> None:
    windows_path = r"C:\Program Files"
    fake_wslpath.pair(windows_path, ABSENT)

    wsl_transform_path_uri(windows_path, True)

    assert fake_wslpath.calls == [["wslpath", "-u", windows_path]]


def test_unc_input_keeps_two_slashes_and_encodes_spaces(
    fake_wslpath: FakeWslpath, tmp_path: Path
) -> None:
    unc = r"\\wsl.localhost\Ubuntu\home\damon\My Photos"
    folder = tmp_path / "My Photos"
    folder.mkdir()
    fake_wslpath.pair(unc, str(folder))

    result = wsl_transform_path_uri(unc, True)

    assert result.win_uri == "file://wsl.localhost/Ubuntu/home/damon/My%20Photos/"
    assert result.win_path == unc
    assert result.linux_path == str(folder)
    assert result.is_dir is True
    assert result.exists is True
    # The 3.14 defect turned this into file:////wsl.localhost/...
    assert result.win_uri.count("//") == 1


def test_unc_input_of_an_absent_target_has_no_trailing_slash(
    fake_wslpath: FakeWslpath,
) -> None:
    unc = r"\\wsl.localhost\Ubuntu\home\damon\nope.txt"
    fake_wslpath.pair(unc, ABSENT)

    result = wsl_transform_path_uri(unc, True)

    assert result.win_uri == "file://wsl.localhost/Ubuntu/home/damon/nope.txt"
    assert result.is_win_location is True
    assert result.exists is False
    assert result.is_dir is None


def test_path_wslpath_cannot_translate_reports_no_location(
    fake_wslpath: FakeWslpath,
) -> None:
    windows_path = r"C:\Program Files"

    result = wsl_transform_path_uri(windows_path, True)

    assert result.linux_path is None
    assert result.is_win_location is None
    assert result.exists is False
    assert result.win_uri is None
    assert result.win_path == windows_path


def test_posix_uri_directory_skips_wslpath_when_not_asked_to_convert(
    fake_wslpath: FakeWslpath, tmp_path: Path
) -> None:
    folder = tmp_path / "etc"
    folder.mkdir()

    result = wsl_transform_path_uri(folder.as_uri(), False)

    assert result.win_path is None
    assert result.win_uri is None
    assert result.linux_path == str(folder)
    assert result.is_dir is True
    assert result.is_win_location is False
    assert fake_wslpath.calls == []


def test_posix_uri_file_is_converted_for_windows(
    fake_wslpath: FakeWslpath, tmp_path: Path
) -> None:
    folder = tmp_path / "etc"
    folder.mkdir()
    target = folder / "fstab"
    target.write_text("", encoding="utf-8")
    unc = "\\\\wsl.localhost\\Ubuntu" + str(target).replace("/", "\\")
    fake_wslpath.pair(unc, str(target))

    result = wsl_transform_path_uri(target.as_uri(), True)

    assert result.exists is True
    assert result.is_dir is False
    assert result.is_win_location is False
    assert result.win_path == unc
    assert result.win_uri is not None
    assert result.win_uri.startswith("file://wsl.localhost/Ubuntu/")
    assert result.win_uri.endswith("/etc/fstab")
    assert result.win_uri.count("//") == 1


def test_generated_windows_uri_encodes_spaces(
    fake_wslpath: FakeWslpath, tmp_path: Path
) -> None:
    folder = tmp_path / "dir with spaces"
    folder.mkdir()
    unc = r"\\wsl.localhost\Ubuntu\tmp\dir with spaces"
    fake_wslpath.pair(unc, str(folder))

    result = wsl_transform_path_uri(folder.as_uri(), True)

    assert result.win_uri == "file://wsl.localhost/Ubuntu/tmp/dir%20with%20spaces/"


def test_spaces_in_a_windows_uri_input_are_encoded(
    fake_wslpath: FakeWslpath,
) -> None:
    fake_wslpath.pair("c:/Program Files/Common Files", ABSENT)

    result = wsl_transform_path_uri("file:///c:/Program Files/Common Files", True)

    assert result.win_uri == "file:///c:/Program%20Files/Common%20Files"
    assert result.linux_path == ABSENT


def test_win_path_is_normalised_when_the_target_exists(
    fake_wslpath: FakeWslpath, tmp_path: Path
) -> None:
    target = tmp_path / "barrier.conf"
    target.write_text("", encoding="utf-8")
    windows_path = r"C:\Program Files\Barrier\barrier.conf"
    fake_wslpath.pair("c:/Program Files/Barrier/barrier.conf", str(target))
    # wslpath -w is what normalises the drive letter and the separators, so it is
    # stated separately from the -u direction the URI path is translated with
    fake_wslpath.to_windows(str(target), windows_path)

    result = wsl_transform_path_uri(
        "file:///c:/Program%20Files/Barrier/barrier.conf", True
    )

    assert result.exists is True
    assert result.is_dir is False
    # tmp_path stands in for a mounted drive, so is_win_location is False here
    # rather than the True a real /mnt/c path gives; the live layer covers both.
    assert result.win_path == windows_path


def test_win_path_stays_in_the_input_dialect_when_the_target_is_absent(
    fake_wslpath: FakeWslpath,
) -> None:
    """
    The retired doctest expected a normalised path here. It only ever held when
    the file existed, because wslpath is what normalises it, and it was run on a
    machine where the Barrier directory had long since lost its contents.
    """

    fake_wslpath.pair("c:/Program Files/Barrier/barrier.conf", ABSENT)

    result = wsl_transform_path_uri(
        "file:///c:/Program%20Files/Barrier/barrier.conf", True
    )

    assert result.exists is False
    assert result.is_dir is None
    assert result.is_win_location is True
    assert result.win_path == "c:/Program Files/Barrier/barrier.conf"
    assert result.win_uri == "file:///c:/Program%20Files/Barrier/barrier.conf"


def test_relative_path_resolves_against_the_working_directory(
    fake_wslpath: FakeWslpath, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "data.txt"
    target.write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = wsl_transform_path_uri("data.txt", False)

    assert result.linux_path == str(target.resolve())
    assert result.exists is True
    assert result.is_dir is False
    assert result.is_win_location is False
    assert result.win_path is None
    assert result.win_uri is None
    assert fake_wslpath.calls == []


@requires_wsl
@pytest.mark.parametrize(
    "path_or_uri",
    [
        r"C:\Program Files",
        "/mnt/c/Program Files",
        "/mnt/c/Program Files/",
        "file:///c:/Program%20Files",
        "file:///c:/Program Files",
    ],
)
def test_live_wsl_locates_program_files(path_or_uri: str) -> None:
    """
    Exact values rather than ellipsis, because these are the strings handed to
    explorer.exe. This is the case the 3.14 defect broke.
    """

    result = wsl_transform_path_uri(path_or_uri, True)

    assert result.exists is True
    assert result.is_dir is True
    assert result.is_win_location is True
    assert result.linux_path == "/mnt/c/Program Files"
    assert result.win_path == r"C:\Program Files"
    assert result.win_uri == "file:///c:/Program%20Files/"


@requires_wsl
def test_live_wsl_home_directory_is_a_windows_unc_location() -> None:
    result = wsl_transform_path_uri(str(Path.home()), True)

    assert result.exists is True
    assert result.is_dir is True
    assert result.is_win_location is False
    assert result.win_path is not None and result.win_path.startswith("\\\\")
    assert result.win_uri is not None
    assert re.match(r"^file://[^/]+(/[^/]+)+/$", result.win_uri), result.win_uri
