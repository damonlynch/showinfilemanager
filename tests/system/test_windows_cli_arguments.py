#  SPDX-FileCopyrightText: 2026 Damon Lynch <damonlynch@gmail.com>
#  SPDX-License-Identifier: MIT

"""
Tests for the argument layer only Windows runs before a file manager is started.

showinfm.showinfm.main() calls windows.parse_command_line_arguments() on every Windows
command line run, because cmd.exe and PowerShell leave a glob unexpanded and explorer.exe
takes no smb: URI. That function is the only caller of tools.path_to_file_uri(), so the
two are tested together here: one decides what a Windows argument means, the other turns
a path back into the URI form that decision preserves.

Nothing here starts a file manager. parse_command_line_arguments() and path_to_file_uri()
touch only the filesystem and strings, so they are called directly. The scenarios that
would hand a location to a manager are in test_filemanager_dispatch.py, and the ones that
would call the shell API are in test_windows.py.

The whole module is Windows only: the shapes asserted below come from ntpath, from the
Windows url2pathname() and from what pathlib calls a root, none of which a POSIX
interpreter reproduces. They are skipped elsewhere rather than rewritten, because an
expectation softened to pass on both hosts pins neither.
"""

import os
import platform
import string
from pathlib import Path

import pytest

from showinfm.system import tools, windows

# A host no resolver can answer for: .invalid is reserved for exactly this (RFC 6761),
# so no search suffix turns it into a real share. A bare "srv" resolves on some
# networks, and its answer came and went across runs here -- the wrong ground for a
# test when the question is what the code does with a share that cannot be reached.
DEAD_SERVER = "srv.invalid"
DEAD_SHARE_ROOT = f"\\\\{DEAD_SERVER}\\share"

UNC_ROOT = os.environ.get("SHOWINFM_UNC_ROOT", "")
REAL_UNC = bool(UNC_ROOT) and platform.system() == "Windows" and Path(UNC_ROOT).is_dir()

requires_unc_share = pytest.mark.skipif(
    not REAL_UNC,
    reason="needs SHOWINFM_UNC_ROOT set to a readable network share",
)

pytestmark = pytest.mark.skipif(
    platform.system() != "Windows",
    reason="ntpath, the Windows url2pathname and what pathlib calls a root decide these",
)


def parse_dead_share(argument: str) -> list[str]:
    r"""
    Run the parser on an argument naming a share nobody can reach, or say why this
    machine cannot answer the question.

    Two answers stand in the way, and neither is the code's. If the server resolves,
    the share can be a folder and the empty result here cannot happen. Worse, the
    redirector answers a share that went away with codes pathlib's is_dir() does not
    swallow -- WinError 64, "The specified network name is no longer available", is one
    -- and those leave parse_command_line_arguments() as an OSError. Asked repeatedly on
    the developer's own Windows machine that happened in one run of six. It is a defect
    in the code's exposure to the network, reported as a finding, and not what the
    expectations below are about, so they are skipped naming the error rather than
    failed or, worse, passed quietly.
    """

    def hiccup(e: OSError) -> None:
        pytest.skip(
            f"the network layer answered {argument!r} with WinError "
            f"{getattr(e, 'winerror', None)} ({e.strerror}), not 'not found'"
        )

    try:
        reachable = Path(DEAD_SHARE_ROOT).is_dir()
    except OSError as e:
        hiccup(e)
        return []
    if reachable:
        pytest.skip(f"{DEAD_SHARE_ROOT} is a folder here, so no dead share to test")
    try:
        return windows.parse_command_line_arguments([argument])
    except OSError as e:
        hiccup(e)
        return []


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """Two files a pattern matches, one it does not, and two folders."""

    for name in ("a1.jpg", "a2.jpg", "b.jpg"):
        (tmp_path / name).write_text("", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "my dir").mkdir()
    return tmp_path.resolve()


@pytest.fixture
def unc_folder() -> str:
    """A real directory on the share, preferring a name with a space in it."""

    try:
        subfolders = [p for p in Path(UNC_ROOT).iterdir() if p.is_dir()]
    except OSError as e:
        pytest.skip(f"{UNC_ROOT} could not be listed: {e}")
    spaced = [p for p in subfolders if " " in p.name]
    return str((spaced or subfolders or [Path(UNC_ROOT)])[0])


@pytest.fixture
def unmapped_drive_root() -> str:
    r"""
    A drive letter this machine answers as absent, so no network and no mounted volume
    is involved. is_dir() has to answer False rather than raise: an empty optical drive,
    a card reader or the redirector can answer a letter with a code pathlib lets
    through, and that would be the machine talking rather than the parser.
    """

    for letter in string.ascii_uppercase:
        root = Path(f"{letter}:\\")
        try:
            if not root.is_dir():
                return f"{letter}:\\"
        except OSError:
            continue
    pytest.skip("no drive letter on this machine answered as an absent one")


# --- glob expansion, the reason this function exists ---


def test_a_glob_is_expanded_because_the_windows_shell_leaves_it(folder: Path) -> None:
    result = windows.parse_command_line_arguments([str(folder / "a*.jpg")])

    assert sorted(result) == [str(folder / "a1.jpg"), str(folder / "a2.jpg")]


def test_a_pattern_that_matches_nothing_contributes_no_path(folder: Path) -> None:
    """
    An unexpanded pattern must not be handed on as if it named a file: explorer.exe
    would be asked to select a file called a star, and the item the caller did mean to
    say would be lost with it.
    """

    assert windows.parse_command_line_arguments([str(folder / "zz*.jpg")]) == []


def test_a_plain_path_comes_back_resolved(folder: Path) -> None:
    assert windows.parse_command_line_arguments([str(folder / "b.jpg")]) == [
        str(folder / "b.jpg")
    ]


def test_a_directory_is_not_globbed(folder: Path) -> None:
    """
    A folder's own name is not a pattern, and globbing it would answer with the entries
    inside rather than the folder, opening the wrong thing.
    """

    assert windows.parse_command_line_arguments([str(folder / "sub")]) == [
        str(folder / "sub")
    ]


def test_a_directory_named_to_look_like_a_pattern_stays_that_directory(
    folder: Path,
) -> None:
    r"""
    pathlib reads the bracket in trip[1] as a single character class, so globbing the
    name of a folder that exists answers with whatever other entry of the parent the
    pattern happens to match -- here the sibling trip1, created to be picked up instead.
    Checking whether it is a directory before globbing is what keeps a folder a folder
    whatever its name looks like, and brackets are ordinary characters in a Windows
    folder name.
    """

    bracket = folder / "trip[1]"
    bracket.mkdir()
    (folder / "trip1").mkdir()

    assert windows.parse_command_line_arguments([str(bracket)]) == [str(bracket)]


def test_a_relative_directory_comes_back_absolute(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    r"""
    The plain-path branch ends in resolve(), so a folder named relative to the working
    directory is answered with the folder Windows will actually open: without it the
    answer is a bare name, and a file manager started from a different working directory
    opens nothing or the wrong thing.
    """

    monkeypatch.chdir(folder)

    assert windows.parse_command_line_arguments(["sub"]) == [str(folder / "sub")]


def test_an_existing_root_directory_is_answered_with_the_root_itself(
    folder: Path,
) -> None:
    r"""
    A root carries no filename component, so there is nothing to glob and the folder the
    caller named is the answer. This is the drive holding the working directory, which
    always exists; the counterpart above is what happens when a root cannot be reached.
    """

    root = f"{folder.drive}\\"

    assert windows.parse_command_line_arguments([root]) == [root]


def test_a_relative_glob_expands_against_the_working_directory(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    The caller typed a bare pattern, so the only anchor is the working directory. The
    parent is resolved before globbing, which is what makes the answer absolute.
    """

    monkeypatch.chdir(folder)

    assert sorted(windows.parse_command_line_arguments(["a*.jpg"])) == [
        str(folder / "a1.jpg"),
        str(folder / "a2.jpg"),
    ]


def test_a_glob_expands_in_place_and_leaves_the_other_arguments_alone(
    folder: Path,
) -> None:
    """
    Several arguments arrive as one list and a pattern can match several files, so what
    has to hold is the caller's order, with the pattern replaced where it stood.
    """

    result = windows.parse_command_line_arguments(
        [str(folder / "a*.jpg"), "trash://", str(folder / "b.jpg")]
    )

    assert sorted(result[:2]) == [str(folder / "a1.jpg"), str(folder / "a2.jpg")]
    assert result[2:] == ["trash://", str(folder / "b.jpg")]


# --- file: URIs, which stay URIs and can carry a pattern too ---


def test_a_file_uri_naming_a_directory_stays_a_file_uri(folder: Path) -> None:
    """
    The URI form is what the caller used, so it is what comes back, with the space still
    encoded because a raw one would split the argument it goes into.
    """

    for name in ("sub", "my dir"):
        uri = (folder / name).as_uri()
        assert windows.parse_command_line_arguments([uri]) == [uri]


def test_a_glob_inside_a_file_uri_is_expanded_and_stays_a_uri(folder: Path) -> None:
    """
    A pattern is a pattern whatever the spelling, so it expands, and the files it matched
    are turned back into URIs rather than handed on as paths. That conversion is the only
    reason parse_command_line_arguments() calls path_to_file_uri() at all.
    """

    result = windows.parse_command_line_arguments([(folder / "a*.jpg").as_uri()])

    assert sorted(result) == sorted(
        (folder / name).as_uri() for name in ("a1.jpg", "a2.jpg")
    )
    assert all(uri.startswith("file:///") for uri in result)


def test_a_file_uri_naming_one_file_stays_a_uri(folder: Path) -> None:
    uri = (folder / "b.jpg").as_uri()

    assert windows.parse_command_line_arguments([uri]) == [uri]


def test_a_file_uri_glob_that_matches_nothing_contributes_no_path(
    folder: Path,
) -> None:
    assert windows.parse_command_line_arguments([(folder / "zz*.jpg").as_uri()]) == []


# --- an smb: URI is a share path by the time anything looks at it ---


def test_an_smb_uri_is_not_carried_past_the_conversion() -> None:
    r"""
    explorer.exe takes no smb: URI, so the argument becomes \\srv\share\h.jpg and is
    globbed as a path. Nothing was matched against a server that cannot be reached, and
    nothing was invented for it either: the URI did not survive, which is what the
    branch for schemes with no filesystem item would have answered, and no path under
    the working directory appeared, which is what the plain path branch would have made.
    """

    dead = f"smb://{DEAD_SERVER}/share/h*.jpg"

    assert parse_dead_share(dead) == []


def test_an_unreachable_share_root_raises_from_the_glob() -> None:
    r"""
    A root has no filename component, so pathlib reports its name as empty and glob()
    rejects that pattern instead of matching nothing. Recorded as it behaves: the
    ValueError escapes parse_command_line_arguments(), and main() calls the parser
    outside its try, so showinfilemanager smb://srv/share ends in a traceback rather
    than a message.
    """

    with pytest.raises(ValueError, match="Unacceptable pattern"):
        parse_dead_share(f"smb://{DEAD_SERVER}/share")


def test_an_unmapped_drive_root_raises_from_the_glob(
    unmapped_drive_root: str,
) -> None:
    """The same defect with no network in it, so it is asked of every Windows machine."""

    with pytest.raises(ValueError, match="Unacceptable pattern"):
        windows.parse_command_line_arguments([unmapped_drive_root])


@requires_unc_share
def test_an_smb_uri_glob_expands_to_share_paths(unc_folder: str) -> None:
    r"""
    The half that needs a real share: a pattern in an smb: URI has to match, and what
    comes back has to be UNC paths, since those are what Windows opens. No machine
    without the share can show this, and a made-up server proves only the negative above.
    """

    server, share = UNC_ROOT.strip("\\").split("\\", 1)
    tail = unc_folder[len(UNC_ROOT) :].replace("\\", "/").replace(" ", "%20")
    uri = f"smb://{server}/{share}{tail}/*"

    result = windows.parse_command_line_arguments([uri])

    assert sorted(result) == sorted(str(p) for p in Path(unc_folder).iterdir())
    assert all(not part.startswith("smb:") for part in result)


# --- a scheme that names no filesystem item ---


@pytest.mark.parametrize(
    "uri",
    [
        "trash://",
        f"ftp://{DEAD_SERVER}/pub/holiday.jpg",
        f"nfs://{DEAD_SERVER}/export/holiday.jpg",
        "camera:/1234567890",
    ],
)
def test_a_uri_that_names_no_filesystem_item_is_passed_along_exactly(
    uri: str,
) -> None:
    """
    Globbing or resolving one would answer with something the caller never said: the host
    becomes a share on a server that may not exist, or the drive holding the working
    directory does. An argument that is not a filesystem location is returned untouched.
    """

    assert windows.parse_command_line_arguments([uri]) == [uri]


def test_several_schemes_in_one_call_are_each_answered_for(folder: Path) -> None:
    """Refusing to convert one argument does not stop the list or disturb the others."""

    uri = (folder / "a*.jpg").as_uri()

    result = windows.parse_command_line_arguments(["trash://", uri])

    assert result[0] == "trash://"
    assert sorted(result[1:]) == sorted(
        (folder / name).as_uri() for name in ("a1.jpg", "a2.jpg")
    )


# --- tools.path_to_file_uri(), reached from the two URI branches above ---


def test_a_windows_path_with_a_space_becomes_one_uri_token() -> None:
    """
    A raw space would end the argument, so it has to be encoded. The drive letter keeps
    its colon and the separator becomes a slash: this is the form RFC 8089 gives a local
    file, and the one file_uri_to_path() reads back.
    """

    drive = r"C:\x y\holiday.jpg"

    assert tools.path_to_file_uri(drive) == "file:///C:/x%20y/holiday.jpg"


def test_a_share_path_keeps_its_server_as_the_authority() -> None:
    r"""
    Two separators then a server is not a local file, so the server moves into the
    authority and those separators go: file://srv/... is the spelling that round trips,
    and the one the WSL route hands to explorer.exe.
    """

    share = r"\\srv\Backup\media render\h.jpg"

    assert tools.path_to_file_uri(share) == "file://srv/Backup/media%20render/h.jpg"


def test_a_relative_path_is_made_absolute(
    folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    A URI carries no working directory, so a relative path would mean one file to the
    caller and another to whatever read the URI back. abspath() is what closes the round
    trip, and it is the only part of this function not covered by its caller.
    """

    monkeypatch.chdir(folder)

    uri = tools.path_to_file_uri("b.jpg")

    assert uri.startswith("file:///")
    assert tools.file_uri_to_path(uri) == str(folder / "b.jpg")


@pytest.mark.parametrize(
    "raw",
    [
        r"C:\x y\holiday.jpg",
        r"C:\holiday.jpg",
        r"\\srv\Backup\media render\holiday.jpg",
        r"\\srv\share",
    ],
)
def test_the_uri_names_the_same_place_the_path_did(raw: str) -> None:
    """
    The promise the URI branches of parse_command_line_arguments() depend on: a path that
    goes out as a URI comes back as the same path, spaces and all.
    """

    uri = tools.path_to_file_uri(raw)

    assert " " not in uri
    assert tools.file_uri_to_path(uri) == os.path.normpath(raw)


def test_a_separator_at_the_end_of_a_directory_does_not_grow_another_uri(
    folder: Path,
) -> None:
    r"""
    str() of a root ends with a separator, and normpath() drops a trailing one from a
    drive or share path. Two spellings of the same folder must not become two different
    URIs, since the file manager would then be shown whichever the caller happened to
    type.
    """

    with_sep = tools.path_to_file_uri(str(folder / "sub") + os.sep)
    without = tools.path_to_file_uri(str(folder / "sub"))

    assert with_sep == without == (folder / "sub").as_uri()
