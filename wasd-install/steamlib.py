#!/usr/bin/env python3
"""Tell Steam that /games is a storage drive.

Steam reads this list when it starts and writes it back when it quits.
The menu runs this before Steam opens. Completing the install runs it
once, and skips it when Steam is already open.
"""

import os
import re
import secrets
import sys
from pathlib import Path


PATH_RE = re.compile(r'"path"\s+"([^"]*)"')
KEY_RE = re.compile(r'^\t"(\d+)"\s*$', re.M)


def steam_is_running():
    flag = os.environ.get("WASD_STEAM_RUNNING")
    if flag == "1":
        return True
    if flag == "0":
        return False
    try:
        names = list(Path("/proc").iterdir())
    except OSError:
        return False
    for name in names:
        if not name.name.isdigit():
            continue
        try:
            command = (name / "cmdline").read_bytes()
        except OSError:
            continue
        if (
            b"steam.sh" in command
            or b"steamwebhelper" in command
            or b"ubuntu12_32/steam" in command
        ):
            return True
    return False


def games_is_mounted(games):
    flag = os.environ.get("WASD_STEAM_MOUNTED")
    if flag == "1":
        return True
    if flag == "0":
        return False
    try:
        return games.is_dir() and not games.is_symlink() and games.is_mount()
    except OSError:
        return False


def real_library(folder):
    apps = folder / "steamapps"
    if apps.is_symlink() or folder.is_symlink() or not apps.is_dir():
        return None
    return folder


def choose_library(games):
    if not games_is_mounted(games) or games.is_symlink() or not games.is_dir():
        return None
    library = real_library(games / "SteamLibrary")
    if library is not None:
        return library
    plain = real_library(games)
    if plain is not None:
        return plain
    apps = games / "SteamLibrary" / "steamapps"
    try:
        apps.mkdir(parents=True, mode=0o755)
    except OSError:
        return None
    return real_library(games / "SteamLibrary")


def same_path(left, right):
    a = os.path.normpath(left)
    b = os.path.normpath(right)
    if a == b:
        return True
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False


def content_id():
    return str(secrets.randbits(63))


def folder_block(index, library, ident):
    return (
        f'\t"{index}"\n'
        "\t{\n"
        f'\t\t"path"\t\t"{library}"\n'
        '\t\t"label"\t\t""\n'
        f'\t\t"contentid"\t\t"{ident}"\n'
        '\t\t"totalsize"\t\t"0"\n'
        '\t\t"update_clean_bytes_tally"\t\t"0"\n'
        '\t\t"time_last_update_verified"\t\t"0"\n'
        '\t\t"apps"\n'
        "\t\t{\n"
        "\t\t}\n"
        "\t}\n"
    )


def fresh_list(steam_root, library, home_id, games_id):
    return (
        '"libraryfolders"\n'
        "{\n"
        + folder_block("0", steam_root, home_id)
        + folder_block("1", library, games_id)
        + "}\n"
    )


def add_folder(text, library, ident):
    if '"' in library or "\n" in library:
        return text, False
    body = text.rstrip("\n")
    if not body.endswith("}"):
        return text, False
    if any(same_path(found, library) for found in PATH_RE.findall(body)):
        return text, False
    keys = [int(number) for number in KEY_RE.findall(body)]
    if not keys:
        return text, False
    split = body.rfind("\n}")
    if split < 0:
        return text, False
    block = folder_block(str(max(keys) + 1), library, ident)
    return body[:split] + "\n" + block + "}\n", True


def write_text(path, text):
    path.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
    temporary = path.with_name(path.name + ".wasd-tmp")
    temporary.write_text(text, encoding="utf-8")
    os.chmod(temporary, 0o644)
    os.replace(temporary, path)


def write_marker(library, ident):
    marker = library / "libraryfolder.vdf"
    if marker.exists():
        return
    write_text(
        marker,
        '"libraryfolder"\n'
        "{\n"
        f'\t"contentid"\t\t"{ident}"\n'
        '\t"label"\t\t""\n'
        "}\n",
    )


def lists_for(steam_root):
    names = [steam_root / "steamapps" / "libraryfolders.vdf"]
    config = steam_root / "config" / "libraryfolders.vdf"
    if config.is_file() and not config.is_symlink():
        try:
            same = names[0].is_file() and os.path.samefile(names[0], config)
        except OSError:
            same = False
        if not same:
            names.append(config)
    return names


def ensure(home, games, *, mounted, running):
    if running:
        return "busy"
    previous = os.environ.get("WASD_STEAM_MOUNTED")
    os.environ["WASD_STEAM_MOUNTED"] = "1" if mounted else "0"
    try:
        library = choose_library(games)
    finally:
        if previous is None:
            os.environ.pop("WASD_STEAM_MOUNTED", None)
        else:
            os.environ["WASD_STEAM_MOUNTED"] = previous
    if library is None:
        return "skipped"
    steam_root = home / ".local" / "share" / "Steam"
    ident = content_id()
    changed = False
    for path in lists_for(steam_root):
        if not path.is_file():
            if path.name != "libraryfolders.vdf" or path.parent.name != "steamapps":
                continue
            write_text(path, fresh_list(str(steam_root), str(library), content_id(), ident))
            changed = True
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        updated, did = add_folder(text, str(library), ident)
        if did:
            write_text(path, updated)
            changed = True
    if changed:
        write_marker(library, ident)
        return "added"
    return "present"


def main():
    if "--self-check" in sys.argv:
        self_check()
        return 0
    games = Path(os.environ.get("WASD_GAMES", "/games"))
    home = Path(os.environ.get("WASD_STEAM_HOME", str(Path.home())))
    mounted = games_is_mounted(games)
    ensure(home, games, mounted=mounted, running=steam_is_running())
    return 0


def self_check():
    import tempfile

    with tempfile.TemporaryDirectory(prefix="wasd-steam-library-") as raw:
        root = Path(raw)
        home = root / "home"
        games = root / "games"
        library = games / "SteamLibrary"
        (library / "steamapps").mkdir(parents=True)
        steam_root = home / ".local" / "share" / "Steam"
        vdf = steam_root / "steamapps" / "libraryfolders.vdf"

        if ensure(home, games, mounted=False, running=False) != "skipped" or vdf.exists():
            raise SystemExit("an unmounted /games was added to Steam")

        if ensure(home, games, mounted=True, running=True) != "busy" or vdf.exists():
            raise SystemExit("Steam was edited while it was open")

        if ensure(home, games, mounted=True, running=False) != "added":
            raise SystemExit("the games drive was not added")
        text = vdf.read_text(encoding="utf-8")
        if str(steam_root) not in text or str(library) not in text:
            raise SystemExit(f"the new library list is wrong: {text}")
        marker = library / "libraryfolder.vdf"
        if not marker.is_file() or "contentid" not in marker.read_text(encoding="utf-8"):
            raise SystemExit("the games library marker was not written")
        before = vdf.read_bytes()
        if ensure(home, games, mounted=True, running=False) != "present" or vdf.read_bytes() != before:
            raise SystemExit("a second add changed the library list")

        one = (
            '"libraryfolders"\n'
            "{\n"
            + folder_block("0", str(steam_root), "11").replace(
                '\t\t"apps"\n\t\t{\n\t\t}\n',
                '\t\t"apps"\n\t\t{\n\t\t\t"440"\t\t"9"\n\t\t}\n',
            )
            + "}\n"
        )
        write_text(vdf, one)
        config = steam_root / "config" / "libraryfolders.vdf"
        write_text(config, one)
        if ensure(home, games, mounted=True, running=False) != "added":
            raise SystemExit("an existing library list was left unchanged")
        updated = vdf.read_text(encoding="utf-8")
        if '"440"' not in updated or str(library) not in updated:
            raise SystemExit(f"the existing game was dropped: {updated}")
        if config.read_text(encoding="utf-8") != updated:
            raise SystemExit("Steam's two library lists do not match")

        plain = root / "plain"
        (plain / "steamapps").mkdir(parents=True)
        other = root / "other-home"
        if ensure(other, plain, mounted=True, running=False) != "added":
            raise SystemExit("a library at the root of /games was skipped")
        other_text = (other / ".local" / "share" / "Steam" / "steamapps" / "libraryfolders.vdf").read_text(
            encoding="utf-8"
        )
        if str(plain) not in other_text or "SteamLibrary" in other_text:
            raise SystemExit(f"the plain library path is wrong: {other_text}")

        broken = root / "broken-home"
        broken_vdf = broken / ".local" / "share" / "Steam" / "steamapps" / "libraryfolders.vdf"
        write_text(broken_vdf, "not a library list\n")
        if ensure(broken, games, mounted=True, running=False) != "present":
            raise SystemExit("a broken library list was rewritten")
        if broken_vdf.read_text(encoding="utf-8") != "not a library list\n":
            raise SystemExit("a broken library list was changed")
    print("steam library self-check ok")


if __name__ == "__main__":
    raise SystemExit(main())
