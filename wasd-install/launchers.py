#!/usr/bin/env python3
"""Prepare the game launchers and a program the user downloaded.

WASD makes the Wine prefix and opens that program's own window. Language,
install, and sign-in stay in that window. The self-check injects the command
runner and the download. It does not call Lutris, Wine, umu, or the network.
"""

import json
import os
import re
import select
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GAMES_DIRS = (
    "launchers",
    "battlenet",
    "ubisoft",
    "rockstar",
    "minecraft",
    "custom",
    "saves",
)
# A games drive prepared before Minecraft and custom still counts.
# ea is not required, so an older drive still counts.
_READY_DIRS = ("launchers", "battlenet", "ubisoft", "rockstar", "saves")
BANNED_ARGS = {"/S", "-S", "/silent", "--silent", "/SILENT", "--silent"}
_CUSTOM_ID = re.compile(r"custom([1-9]\d*)")


class LauncherError(Exception):
    pass


class Launcher:
    def __init__(
        self,
        launcher_id,
        setup_url,
        setup_name,
        program,
        games_link=(),
        user_link=(),
        games_dir="",
    ):
        self.launcher_id = launcher_id
        self.setup_url = setup_url
        self.setup_name = setup_name
        self.program = tuple(program)
        self.games_link = tuple(games_link)
        self.user_link = tuple(user_link)
        self.games_dir = games_dir


# Display names match Install WASD and WASD Launchers. The setup addresses
# are the ones published for these launchers. No silent switch is passed.
CATALOG = {
    "Battle.net": Launcher(
        "battlenet",
        "https://www.battle.net/download/getInstallerForGame?os=win&installer=Battle.net-Setup.exe",
        "Battle.net-Setup.exe",
        ("drive_c", "Program Files (x86)", "Battle.net", "Battle.net Launcher.exe"),
    ),
    "Ubisoft Connect": Launcher(
        "ubisoft",
        "https://ubistatic3-a.akamaihd.net/orbit/launcher_installer/UbisoftConnectInstaller.exe",
        "UbisoftConnectInstaller.exe",
        ("drive_c", "Program Files (x86)", "Ubisoft", "Ubisoft Game Launcher", "UbisoftConnect.exe"),
        ("drive_c", "Program Files (x86)", "Ubisoft", "Ubisoft Game Launcher", "games"),
    ),
    "Rockstar Launcher": Launcher(
        "rockstar",
        "https://gamedownloads.rockstargames.com/public/installer/Rockstar-Games-Launcher.exe",
        "Rockstar-Games-Launcher.exe",
        ("drive_c", "Program Files", "Rockstar Games", "Launcher", "Launcher.exe"),
    ),
    "Minecraft": Launcher(
        "minecraft",
        "https://launcher.mojang.com/download/Minecraft.exe",
        "Minecraft.exe",
        ("drive_c", "Program Files (x86)", "Minecraft Launcher", "MinecraftLauncher.exe"),
        user_link=("AppData", "Roaming", ".minecraft"),
    ),
}


def names_from(data):
    """Return the launcher list, or None when the installer did not save one."""
    if not isinstance(data, dict) or "launchers" not in data:
        return None
    raw = data["launchers"]
    if not isinstance(raw, list):
        raise LauncherError("Choose the launchers again.")
    names = []
    for item in raw:
        if not isinstance(item, str) or item not in CATALOG or item in names:
            raise LauncherError("Choose the launchers again.")
        names.append(item)
    return names


def launchers_problem(data):
    try:
        names_from(data)
    except LauncherError:
        return "Choose the launchers again. Nothing was erased."
    return ""


def _reserved_ids():
    taken = set(GAMES_DIRS)
    taken.update(item.launcher_id for item in CATALOG.values())
    return taken


def _custom_name(name):
    if not isinstance(name, str):
        raise LauncherError("Name that game in a few words.")
    name = " ".join(name.split())
    if not name or len(name) > 40 or any(ord(ch) < 32 for ch in name):
        raise LauncherError("Name that game in a few words.")
    if '"' in name or "\\" in name:
        raise LauncherError("Name that game in a few words.")
    if name.casefold() in {item.casefold() for item in CATALOG}:
        raise LauncherError("That launcher is already on the list.")
    return name


def _custom_id(value):
    if not isinstance(value, str) or len(value) > 40 or not _CUSTOM_ID.fullmatch(value):
        return ""
    if value in _reserved_ids():
        return ""
    return value


def _next_custom_id(rows):
    """custom1, then custom2. A removed number is not reused."""
    highest = 0
    for row in rows:
        match = _CUSTOM_ID.fullmatch(row["id"])
        if match:
            highest = max(highest, int(match.group(1)))
    slug = f"custom{highest + 1}"
    if len(slug) > 40 or slug in _reserved_ids():
        raise LauncherError("Could not add that game.")
    return slug


def _plain_filename(name):
    if not isinstance(name, str) or not name or name in (".", ".."):
        return ""
    if "/" in name or "\\" in name or len(name) > 180:
        return ""
    return name


def _custom_file(home):
    return Path(home) / ".local/share/wasd/custom-launchers.json"


def load_custom(home):
    path = _custom_file(home)
    if path.is_symlink() or not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    rows = []
    seen = set()
    reserved = _reserved_ids()
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        slug = _custom_id(item.get("id"))
        raw_file = item.get("file", "")
        if raw_file == "":
            filename = ""
        else:
            filename = _plain_filename(raw_file)
            if not filename:
                continue
        if not isinstance(name, str) or not slug or slug in reserved or slug in seen:
            continue
        if not name.strip() or len(name) > 40 or any(ord(ch) < 32 for ch in name):
            continue
        if '"' in name or "\\" in name:
            continue
        seen.add(slug)
        rows.append({"name": name, "id": slug, "file": filename})
    return rows


def save_custom(home, rows):
    path = _custom_file(home)
    if path.is_symlink():
        raise LauncherError("Could not add that game.")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise LauncherError("Could not add that game.")
    path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    os.chmod(path, 0o644)


def custom_launcher(row):
    return Launcher(row["id"], "", row["file"], (), games_dir=row["id"])


def find_launcher(home, name):
    if isinstance(name, str) and name in CATALOG:
        return CATALOG[name]
    if not isinstance(name, str) or not name:
        return None
    for row in load_custom(home):
        if row["name"] == name:
            return custom_launcher(row)
    return None


def require_launcher(home, name):
    found = find_launcher(home, name)
    if found is None:
        raise LauncherError("Choose the launchers again.")
    return found


def _own_program(path):
    if not isinstance(path, str) or not path or "\n" in path or "\x00" in path:
        raise LauncherError("Choose the program you downloaded.")
    file_path = Path(path)
    if not file_path.is_absolute() or file_path.is_symlink() or not file_path.is_file():
        raise LauncherError("Choose the program you downloaded.")
    try:
        size = file_path.stat().st_size
    except OSError as exc:
        raise LauncherError("Choose the program you downloaded.") from exc
    if size <= 0 or not _plain_filename(file_path.name):
        raise LauncherError("Choose the program you downloaded.")
    return file_path


def choose_root(home, mount):
    """Use the games drive when it is mounted and this account can write it."""
    mount = Path(mount)
    try:
        mounted = os.path.ismount(mount)
    except OSError:
        mounted = False
    if mounted and _root_writable(mount):
        return mount
    return Path(home) / "Games"


def games_root(home):
    override = os.environ.get("WASD_GAMES_ROOT")
    if override:
        return Path(override)
    return choose_root(home, "/games")


def _root_writable(mount):
    if os.access(mount, os.W_OK):
        return True
    for name in _READY_DIRS:
        folder = mount / name
        if folder.is_symlink() or not folder.is_dir() or not os.access(folder, os.W_OK):
            return False
    return True


def _prefix(root, launcher):
    return Path(root) / "launchers" / launcher.launcher_id


def _games(root, launcher):
    folder = launcher.games_dir or launcher.launcher_id
    path = Path(root)
    for part in Path(folder).parts:
        if part in ("", ".", ".."):
            raise LauncherError("The launcher folder is a link.")
        path = path / part
    return path


def _saves(root, launcher):
    return Path(root) / "saves" / launcher.launcher_id


def _inside(child, parent):
    try:
        Path(child).resolve().relative_to(Path(parent).resolve())
    except (OSError, ValueError):
        return False
    return True


def _safe_dir(path):
    path = Path(path)
    if path.is_symlink():
        raise LauncherError("The launcher folder is a link.")
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise LauncherError("The games drive could not be prepared.") from exc
    if path.is_symlink() or not path.is_dir():
        raise LauncherError("The launcher folder is a link.")
    return path


def _unlink_tree(path):
    """Remove a directory without following a link out of it."""
    path = Path(path)
    if path.is_symlink() or not path.exists():
        if path.is_symlink():
            path.unlink()
        return
    for child in list(path.iterdir()):
        if child.is_symlink() or not child.is_dir():
            child.unlink()
        else:
            _unlink_tree(child)
    path.rmdir()


def _link_under(folder, parts, target):
    """Point folder/parts at target. Parent folders are created, never followed."""
    if not parts:
        return
    current = _safe_dir(folder)
    for part in parts[:-1]:
        if part in ("", ".", ".."):
            raise LauncherError("The launcher folder is a link.")
        current = _safe_dir(current / part)
    leaf = parts[-1]
    if leaf in ("", ".", ".."):
        raise LauncherError("The launcher folder is a link.")
    _replace_link(current / leaf, target)


def _replace_link(link, target):
    """Point link at target. A real directory is moved aside, never followed."""
    link = Path(link)
    target = _safe_dir(target)
    if link.is_symlink():
        if link.resolve() == target.resolve():
            return
        link.unlink()
    elif link.is_dir():
        for child in list(link.iterdir()):
            dest = target / child.name
            if dest.exists() or dest.is_symlink():
                continue
            shutil.move(str(child), str(dest))
        if any(link.iterdir()):
            return
        link.rmdir()
    elif link.exists():
        return
    link.symlink_to(target)


def ensure_links(prefix, games, saves, user_name, launcher):
    prefix = _safe_dir(prefix)
    dos = _safe_dir(prefix / "dosdevices")
    _replace_link(dos / "d:", games)
    users = []
    for name in (user_name, "steamuser"):
        if name and name not in users:
            users.append(name)
    for name in users:
        folder = _safe_dir(prefix / "drive_c" / "users" / name)
        _replace_link(folder / "Documents", saves)
        my_docs = folder / "My Documents"
        if my_docs.is_symlink() or not my_docs.exists():
            _replace_link(my_docs, saves)
        if launcher.user_link:
            _link_under(folder, launcher.user_link, games)
    if launcher.games_link:
        moved = prefix.joinpath(*launcher.games_link)
        parent = _safe_dir(moved.parent)
        if parent != moved.parent and moved.parent.is_symlink():
            raise LauncherError("The launcher folder is a link.")
        _replace_link(moved, games)


def _guard(prefix, games, saves):
    prefix = Path(prefix)
    if prefix.is_symlink():
        raise LauncherError("The launcher folder is a link.")
    if not prefix.exists():
        return
    resolved = prefix.resolve()
    for kept in (Path(games).resolve(), Path(saves).resolve()):
        if resolved == kept or _inside(resolved, kept) or _inside(kept, resolved):
            raise LauncherError("The launcher folder is a link.")


def layout(home, name, root=None):
    """Create the prefix, the games folder, and the D: link. Nothing is run."""
    launcher = require_launcher(home, name)
    home = Path(home)
    root = Path(root) if root is not None else games_root(home)
    games = _games(root, launcher)
    saves = _saves(root, launcher)
    prefix = _prefix(root, launcher)
    _guard(prefix, games, saves)
    _safe_dir(games)
    _safe_dir(saves)
    if not prefix.exists():
        _safe_dir(prefix.parent)
        prefix.mkdir()
    if prefix.is_symlink():
        raise LauncherError("The launcher folder is a link.")
    ensure_links(prefix, games, saves, home.name, launcher)
    return prefix


def nuke(home, name, root=None):
    """Delete the prefix only. Games and saves stay where they are."""
    launcher = require_launcher(home, name)
    home = Path(home)
    root = Path(root) if root is not None else games_root(home)
    games = _games(root, launcher)
    saves = _saves(root, launcher)
    prefix = _prefix(root, launcher)
    _guard(prefix, games, saves)
    if prefix.is_symlink():
        raise LauncherError("The launcher folder is a link.")
    if prefix.exists():
        _unlink_tree(prefix)
    layout(home, name, root)
    return prefix


def _desktop_text(home, name):
    script = Path(__file__).resolve()
    python = sys.executable
    command = f'"{python}" "{script}" --open "{name}"'
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name}\n"
        f"Exec={command}\n"
        "Icon=wasd-logo\n"
        "Terminal=false\n"
        "Categories=Game;\n"
        "StartupNotify=true\n"
    )


def write_menu(home, name):
    launcher = require_launcher(home, name)
    home = Path(home)
    desktop = home / ".local/share/applications" / f"wasd-launcher-{launcher.launcher_id}.desktop"
    if desktop.is_symlink():
        raise LauncherError("The menu entry is a link.")
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(_desktop_text(home, name), encoding="utf-8")
    os.chmod(desktop, 0o644)
    return desktop


def program_path(home, name, root=None):
    """The program to launch.

    Minecraft's download is the launcher itself. It does not add
    MinecraftLauncher.exe under Program Files. That file still wins when a
    future installer creates it.
    """
    launcher = require_launcher(home, name)
    home = Path(home)
    if not launcher.program:
        return _cache(home, launcher)
    root = Path(root) if root is not None else games_root(home)
    installed = _prefix(root, launcher).joinpath(*launcher.program)
    if installed.is_file() and not installed.is_symlink():
        return installed
    if launcher.launcher_id == "minecraft":
        cached = _cache(home, launcher)
        if cached.is_file() and not cached.is_symlink():
            return cached
    return installed


def needs_setup(home, name, root=None):
    path = program_path(home, name, root)
    return not path.is_file() or path.is_symlink()


def _cache(home, launcher):
    return Path(home) / ".cache/wasd/launchers" / launcher.launcher_id / launcher.setup_name


def _check_argv(argv):
    for item in argv:
        text = str(item)
        if text in BANNED_ARGS or text.startswith("--locale") or text.startswith("--lang"):
            raise LauncherError("Could not open that launcher.")
        name = Path(text).name
        if name == "lutris" or text.startswith("lutris:"):
            raise LauncherError("Could not open that launcher.")


def umu_bin():
    override = os.environ.get("WASD_UMU")
    if override:
        return override
    return "/usr/bin/umu-run"


def umu_argv(args):
    return [umu_bin(), *args]


def umu_env(prefix):
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    env["GAMEID"] = "umu-default"
    return env


def log_path():
    return Path(os.environ.get("WASD_APP_LOG", "/tmp/wasd-app-install.log"))


def feed_log(text):
    path = log_path()
    if path.is_symlink():
        return
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        return
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text)
    except OSError:
        return


def reset_log():
    path = log_path()
    if path.is_symlink():
        return
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        return
    try:
        path.write_text("", encoding="utf-8")
    except OSError:
        return


def _stream(argv, env):
    if os.environ.get("WASD_SELF_CHECK") == "1":
        raise SystemExit("self-check tried to run a launcher")
    _check_argv(argv)
    import pty

    try:
        master, slave = pty.openpty()
    except OSError:
        master, slave = None, None
    try:
        proc = subprocess.Popen(
            argv,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=slave if slave is not None else subprocess.PIPE,
            stderr=subprocess.STDOUT,
            close_fds=True,
        )
    except OSError as exc:
        if slave is not None:
            os.close(slave)
        if master is not None:
            os.close(master)
        raise LauncherError("Could not open that launcher.") from exc
    if slave is not None:
        os.close(slave)
    try:
        if master is not None:
            while True:
                try:
                    ready, _, _ = select.select([master], [], [], 0.2)
                except (OSError, ValueError):
                    break
                if ready:
                    try:
                        chunk = os.read(master, 4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    feed_log(chunk.decode("utf-8", "replace"))
                    continue
                if proc.poll() is not None:
                    break
        else:
            assert proc.stdout is not None
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                feed_log(chunk.decode("utf-8", "replace"))
        return proc.wait()
    finally:
        if master is not None:
            os.close(master)


def real_runner(argv, env):
    return _stream(argv, env)


def real_fetch(url, dest):
    if os.environ.get("WASD_SELF_CHECK") == "1":
        raise SystemExit("self-check tried to download a launcher")
    dest = Path(dest)
    if dest.is_symlink():
        raise LauncherError("Could not open that launcher.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    code = _stream(["curl", "-fL", "--output", str(dest), url], os.environ.copy())
    if code != 0 or not dest.is_file() or dest.stat().st_size == 0:
        dest.unlink(missing_ok=True)
        raise LauncherError("Could not open that launcher.")


def install_launcher(home, name, runner, fetch, root=None, force_setup=False):
    """Prepare the prefix and open the vendor window. Do not click through it.

    force_setup opens the vendor setup even when the program is already there.
    """
    launcher = require_launcher(home, name)
    home = Path(home)
    feed_log(name + "\n")
    prefix = layout(home, name, root)
    root = Path(root) if root is not None else games_root(home)
    games = _games(root, launcher)
    saves = _saves(root, launcher)
    write_menu(home, name)
    if not launcher.setup_url and not launcher.setup_name:
        return prefix
    env = umu_env(prefix)
    if not (prefix / "system.reg").is_file():
        boot = umu_argv(["wineboot", "-u"])
        _check_argv(boot)
        if runner(boot, env) != 0:
            raise LauncherError("Could not open that launcher.")
        ensure_links(prefix, games, saves, home.name, launcher)
    program = program_path(home, name, root)
    if not force_setup and program.is_file() and not program.is_symlink():
        target = program
    elif not launcher.setup_url:
        target = _cache(home, launcher)
        if target.is_symlink() or not target.is_file() or target.stat().st_size == 0:
            raise LauncherError("Choose the program you downloaded.")
    else:
        setup = _cache(home, launcher)
        if setup.is_symlink() or not setup.is_file() or setup.stat().st_size == 0:
            try:
                fetch(launcher.setup_url, setup)
            except LauncherError:
                raise
            except Exception as exc:
                raise LauncherError("Could not open that launcher.") from exc
        if setup.is_symlink() or not setup.is_file():
            raise LauncherError("Could not open that launcher.")
        target = setup
    command = umu_argv([str(target)])
    _check_argv(command)
    code = runner(command, env)
    ensure_links(prefix, games, saves, home.name, launcher)
    if code != 0:
        raise LauncherError("Could not open that launcher.")
    return prefix


def launch_installed(home, name, runner, root=None):
    """Open the installed program. Do not download or run its setup."""
    launcher = require_launcher(home, name)
    home = Path(home)
    root = Path(root) if root is not None else games_root(home)
    program = program_path(home, name, root)
    if not program.is_file() or program.is_symlink():
        raise LauncherError("That launcher is not installed.")
    prefix = _prefix(root, launcher)
    if prefix.is_symlink() or not prefix.is_dir():
        raise LauncherError("Could not open that launcher.")
    feed_log(name + "\n")
    command = umu_argv([str(program)])
    _check_argv(command)
    code = runner(command, umu_env(prefix))
    if code != 0:
        raise LauncherError("Could not open that launcher.")
    return prefix


def remake(home, name, runner, fetch, root=None):
    nuke(home, name, root)
    return install_launcher(home, name, runner, fetch, root)


def _store_program(home, row, source):
    """Copy the downloaded program into the setup cache. The original stays."""
    launcher = Launcher(row["id"], "", source.name, (), games_dir=row["id"])
    dest = _cache(home, launcher)
    if dest.is_symlink():
        raise LauncherError("Could not add that game.")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not dest.exists() or source.resolve() != dest.resolve():
            shutil.copyfile(source, dest)
        os.chmod(dest, 0o644)
    except OSError as exc:
        raise LauncherError("Could not add that game.") from exc
    if dest.is_symlink() or not dest.is_file() or dest.stat().st_size == 0:
        raise LauncherError("Could not add that game.")
    return dest


def add_custom(home, name, program, runner, fetch, root=None):
    """Make /games/custom1, then custom2. A program is opened only when one was given."""
    name = _custom_name(name)
    if program is None:
        program = ""
    if not isinstance(program, str):
        raise LauncherError("Choose the program you downloaded.")
    home = Path(home)
    rows = load_custom(home)
    existing = next((row for row in rows if row["name"].casefold() == name.casefold()), None)
    if existing is not None:
        if not program or existing["file"]:
            raise LauncherError("That name is already used.")
        source = _own_program(program)
        _store_program(home, existing, source)
        existing["file"] = source.name
        save_custom(home, rows)
        return install_launcher(home, existing["name"], runner, fetch, root, force_setup=True)
    slug = _next_custom_id(rows)
    row = {"name": name, "id": slug, "file": ""}
    if program:
        source = _own_program(program)
        _store_program(home, row, source)
        row["file"] = source.name
    rows.append(row)
    save_custom(home, rows)
    if row["file"]:
        return install_launcher(home, name, runner, fetch, root, force_setup=True)
    prefix = layout(home, name, root)
    write_menu(home, name)
    return prefix


def _status_row(home, name, launcher, root, custom):
    prefix = _prefix(root, launcher)
    program = program_path(home, name, root)
    return {
        "name": name,
        "id": launcher.launcher_id,
        "ready": program.is_file() and not program.is_symlink(),
        "prepared": prefix.is_dir() and not prefix.is_symlink(),
        "custom": custom,
        "folder": str(_games(root, launcher)),
    }


def status_rows(home, root=None):
    home = Path(home)
    root = Path(root) if root is not None else games_root(home)
    rows = []
    for name, launcher in CATALOG.items():
        rows.append(_status_row(home, name, launcher, root, False))
    for row in load_custom(home):
        rows.append(_status_row(home, row["name"], custom_launcher(row), root, True))
    return rows


def marker_path():
    override = os.environ.get("WASD_LAUNCHERS_MARK")
    if override:
        return Path(override)
    return Path.home() / ".local/share/wasd/launchers-set"


def write_marker():
    path = marker_path()
    if path.is_symlink():
        raise LauncherError("Could not open that launcher.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ok\n", encoding="utf-8")
    os.chmod(path, 0o644)


def window_args(preview, port):
    if preview:
        return ["--preview"]
    return ["--port", str(port)]


def _qml():
    return Path(os.environ.get("WASD_LAUNCHERS_QML", "/usr/share/wasd/launchers/Launchers.qml"))


def _qml_bin():
    found = next(
        (
            item
            for item in (
                "/usr/bin/wasd-qml",
                shutil.which("qml6"),
                shutil.which("qml"),
                shutil.which("qml-qt6"),
                "/usr/lib64/qt6/bin/qml",
            )
            if item and os.access(item, os.X_OK)
        ),
        "/usr/bin/wasd-qml",
    )
    return found


RUNNER = real_runner
FETCH = real_fetch


def _home():
    override = os.environ.get("WASD_LAUNCHER_HOME")
    if override:
        return Path(override)
    return Path.home()


class WindowHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _reply(self, code, text):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.client_address[0] != "127.0.0.1":
            self._reply(403, "This request was refused.")
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            self._reply(400, "That request was not usable.")
            return
        limit = 4096 if self.path == "/custom" else 64
        if length < 0 or length > limit:
            self._reply(400, "That request was not usable.")
            return
        blob = self.rfile.read(length) if length else b""
        try:
            text = blob.decode("utf-8").strip()
        except UnicodeError:
            self._reply(400, "Choose a launcher.")
            return
        if self.path == "/status":
            self._reply(200, json.dumps({"rows": status_rows(_home())}))
            return
        if self.path == "/custom":
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                self._reply(400, "Name that game in a few words.")
                return
            if not isinstance(payload, dict):
                self._reply(400, "Name that game in a few words.")
                return
            program = payload.get("program", "")
            if program is None:
                program = ""
            if not isinstance(program, str):
                self._reply(400, "Choose the program you downloaded.")
                return
            try:
                add_custom(_home(), payload.get("name"), program, RUNNER, FETCH)
            except LauncherError as exc:
                self._reply(500, str(exc))
                return
            self._reply(200, "ok")
            return
        if find_launcher(_home(), text) is None:
            self._reply(400, "Choose a launcher.")
            return
        try:
            if self.path == "/install":
                install_launcher(_home(), text, RUNNER, FETCH, force_setup=True)
            elif self.path == "/launch":
                launch_installed(_home(), text, RUNNER)
            elif self.path == "/open":
                install_launcher(_home(), text, RUNNER, FETCH)
            elif self.path == "/remake":
                remake(_home(), text, RUNNER, FETCH)
            else:
                self._reply(404, "This request was refused.")
                return
        except LauncherError as exc:
            self._reply(500, str(exc))
            return
        self._reply(200, "ok")


def serve_window(preview):
    qml = _qml()
    binary = _qml_bin()
    if preview:
        command = [binary, str(qml), *window_args(True, 0)]
        return subprocess.run(command).returncode
    server = ThreadingHTTPServer(("127.0.0.1", 0), WindowHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    command = [binary, str(qml), *window_args(False, server.server_address[1])]
    try:
        return subprocess.run(command).returncode
    finally:
        server.shutdown()


def _open_name(argv):
    if "--open" not in argv and "--remake" not in argv:
        return "", ""
    flag = "--remake" if "--remake" in argv else "--open"
    index = argv.index(flag)
    if index + 1 >= len(argv):
        return flag, ""
    return flag, argv[index + 1]


def self_check():
    import json
    import tempfile
    import urllib.error
    import urllib.request

    os.environ["WASD_SELF_CHECK"] = "1"
    calls = []
    fetches = []

    def runner(argv, env):
        calls.append((list(argv), dict(env)))
        joined = " ".join(argv)
        if "lutris" in joined or "/S" in argv or any(str(item).startswith("--locale") for item in argv):
            raise SystemExit(f"a launcher was silenced: {argv}")
        if argv[0].endswith("curl"):
            raise SystemExit("self-check downloaded a launcher")
        return 0

    def fetch(url, dest):
        fetches.append(url)
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"MZ")

    try:
        real_runner(["/usr/bin/umu-run", "wineboot", "-u"], {})
    except SystemExit as exc:
        if "self-check tried to run a launcher" not in str(exc):
            raise
    else:
        raise SystemExit("self-check ran umu")
    try:
        real_fetch("https://example.invalid/setup.exe", Path("/tmp/wasd-launcher-nope"))
    except SystemExit as exc:
        if "self-check tried to download a launcher" not in str(exc):
            raise
    else:
        raise SystemExit("self-check downloaded a launcher")

    if names_from({"password": False}) is not None:
        raise SystemExit("a missing launcher list was treated as a choice")
    if names_from({"launchers": []}) != []:
        raise SystemExit("an empty launcher list was refused")
    for bad in ({"launchers": "Battle.net"}, {"launchers": ["Nope"]}, {"launchers": ["Battle.net", "Battle.net"]}):
        try:
            names_from(bad)
        except LauncherError:
            pass
        else:
            raise SystemExit(f"a bad launcher list was accepted: {bad}")
    if launchers_problem({"launchers": ["Nope"]}) != "Choose the launchers again. Nothing was erased.":
        raise SystemExit("an unknown launcher had the wrong refusal")
    if "EA App" in CATALOG or "ea" in GAMES_DIRS or "ea" in _READY_DIRS:
        raise SystemExit("EA App is still offered")
    try:
        names_from({"launchers": ["EA App"]})
    except LauncherError:
        pass
    else:
        raise SystemExit("EA App was still accepted")
    if launchers_problem({"user": "alex"}) != "":
        raise SystemExit("a missing launcher list was refused")

    with tempfile.TemporaryDirectory(prefix="wasd-launchers-") as tmp:
        home = Path(tmp) / "home"
        home.mkdir()
        root = Path(tmp) / "games"
        root.mkdir()
        os.environ["WASD_GAMES_ROOT"] = str(root)
        os.environ["WASD_LAUNCHER_HOME"] = str(home)
        os.environ["WASD_LAUNCHERS_MARK"] = str(Path(tmp) / "launchers-set")
        os.environ["WASD_APP_LOG"] = str(Path(tmp) / "install.log")
        if choose_root(home, root) != home / "Games":
            raise SystemExit("a plain folder was treated as the games drive")
        prefix = layout(home, "Battle.net", root)
        games = root / "battlenet"
        saves = root / "saves" / "battlenet"
        kept = games / "keep.txt"
        kept.write_text("game\n", encoding="utf-8")
        (saves / "save.txt").write_text("save\n", encoding="utf-8")
        link = prefix / "dosdevices" / "d:"
        if not link.is_symlink() or link.resolve() != games.resolve():
            raise SystemExit("D: does not point at the games folder")
        docs = prefix / "drive_c" / "users" / "steamuser" / "Documents"
        if not docs.is_symlink() or docs.resolve() != saves.resolve():
            raise SystemExit("Documents stayed inside the prefix")
        ubi = layout(home, "Ubisoft Connect", root)
        ubi_games = ubi / "drive_c" / "Program Files (x86)" / "Ubisoft" / "Ubisoft Game Launcher" / "games"
        if not ubi_games.is_symlink() or ubi_games.resolve() != (root / "ubisoft").resolve():
            raise SystemExit("Ubisoft games stayed inside the prefix")
        notes = prefix / "drive_c" / "users" / "home" / "Documents"
        if notes.exists() or notes.is_symlink():
            notes.unlink()
        notes.parent.mkdir(parents=True, exist_ok=True)
        notes.mkdir()
        (notes / "note.txt").write_text("moved\n", encoding="utf-8")
        ensure_links(prefix, games, saves, "home", CATALOG["Battle.net"])
        if (saves / "note.txt").read_text(encoding="utf-8") != "moved\n":
            raise SystemExit("a save was left in the prefix")
        if not notes.is_symlink():
            raise SystemExit("Documents was not moved out of the prefix")
        (saves / "note.txt").write_text("kept\n", encoding="utf-8")
        other = notes if notes.is_symlink() else notes
        if other.is_symlink():
            other.unlink()
        other.mkdir()
        (other / "note.txt").write_text("newer\n", encoding="utf-8")
        ensure_links(prefix, games, saves, "home", CATALOG["Battle.net"])
        if (saves / "note.txt").read_text(encoding="utf-8") != "kept\n":
            raise SystemExit("a save was overwritten")
        nuke(home, "Battle.net", root)
        if not kept.is_file() or kept.read_text(encoding="utf-8") != "game\n":
            raise SystemExit("nuking the prefix deleted the games")
        if (saves / "save.txt").read_text(encoding="utf-8") != "save\n":
            raise SystemExit("nuking the prefix deleted the saves")
        if (root / "launchers" / "battlenet").resolve() == games.resolve():
            raise SystemExit("the new prefix is the games folder")
        if not (prefix / "dosdevices" / "d:").is_symlink():
            raise SystemExit("remake did not put D: back")
        trap = root / "launchers" / "battlenet"
        _unlink_tree(trap)
        trap.symlink_to(games)
        try:
            nuke(home, "Battle.net", root)
        except LauncherError:
            pass
        else:
            raise SystemExit("a linked prefix was removed")
        if kept.read_text(encoding="utf-8") != "game\n":
            raise SystemExit("a linked prefix deleted the games")
        trap.unlink()
        install_launcher(home, "Battle.net", runner, fetch, root)
        if fetches != [CATALOG["Battle.net"].setup_url]:
            raise SystemExit(f"the setup was not fetched once: {fetches}")
        if not calls or "wineboot" not in calls[0][0] or calls[0][0][0] != "/usr/bin/umu-run":
            raise SystemExit(f"the prefix was not prepared with umu: {calls}")
        if calls[0][1].get("GAMEID") != "umu-default" or calls[0][1].get("WINEPREFIX") != str(prefix):
            raise SystemExit("the prefix environment was wrong")
        opened = calls[-1][0]
        if opened[-1].endswith("Battle.net-Setup.exe") is False or len(opened) != 2:
            raise SystemExit(f"the vendor window was not the only argument: {opened}")
        desktop = home / ".local/share/applications/wasd-launcher-battlenet.desktop"
        entry = desktop.read_text(encoding="utf-8")
        if "Name=Battle.net" not in entry or '--open "Battle.net"' not in entry:
            raise SystemExit("Battle.net was not added to the menu")
        if (home / "Desktop").exists():
            raise SystemExit("a launcher was put on the desktop")
        program = program_path(home, "Battle.net", root)
        program.parent.mkdir(parents=True, exist_ok=True)
        program.write_bytes(b"MZ")
        before = len(fetches)
        install_launcher(home, "Battle.net", runner, fetch, root)
        if len(fetches) != before:
            raise SystemExit("an installed launcher downloaded its setup again")
        if not calls[-1][0][-1].endswith("Battle.net Launcher.exe"):
            raise SystemExit("Open did not start the installed launcher")
        calls.clear()
        before = len(fetches)
        launch_installed(home, "Battle.net", runner, root)
        if len(fetches) != before or not calls[-1][0][-1].endswith("Battle.net Launcher.exe"):
            raise SystemExit("Launch did not start the installed launcher")
        try:
            launch_installed(home, "Ubisoft Connect", runner, root)
        except LauncherError:
            pass
        else:
            raise SystemExit("Launch started a launcher that is not installed")
        calls.clear()
        install_launcher(home, "Battle.net", runner, fetch, root, force_setup=True)
        if len(fetches) != before or not calls[-1][0][-1].endswith("Battle.net-Setup.exe"):
            raise SystemExit("Reinstall did not open the setup")
        ubisoft = layout(home, "Ubisoft Connect", root)
        (ubisoft / "system.reg").write_text("ok\n", encoding="utf-8")
        calls.clear()
        install_launcher(home, "Ubisoft Connect", runner, fetch, root)
        if any("wineboot" in item[0] for item in calls):
            raise SystemExit("a prepared prefix was created again")
        if fetches[-1] != CATALOG["Ubisoft Connect"].setup_url:
            raise SystemExit("the Ubisoft setup was not the published one")
        rows = {row["name"]: row for row in status_rows(home, root)}
        if "EA App" in rows or not rows["Battle.net"]["ready"] or rows["Ubisoft Connect"]["ready"]:
            raise SystemExit(f"the menu status was wrong: {rows}")
        write_marker()
        if marker_path().read_text(encoding="utf-8") != "ok\n":
            raise SystemExit("the launcher marker was not written")
        log = Path(os.environ["WASD_APP_LOG"]).read_text(encoding="utf-8")
        if "Battle.net\n" not in log or "Ubisoft Connect\n" not in log:
            raise SystemExit("the install log did not name the launcher")
        mine = layout(home, "Minecraft", root)
        world_link = mine / "drive_c" / "users" / "steamuser" / "AppData" / "Roaming" / ".minecraft"
        home_link = mine / "drive_c" / "users" / home.name / "AppData" / "Roaming" / ".minecraft"
        minecraft_games = root / "minecraft"
        if not world_link.is_symlink() or world_link.resolve() != minecraft_games.resolve():
            raise SystemExit("Minecraft worlds stayed in the launcher")
        if not home_link.is_symlink() or home_link.resolve() != minecraft_games.resolve():
            raise SystemExit("Minecraft worlds were not linked for the account")
        (world_link / "saves").mkdir()
        (world_link / "saves" / "world.txt").write_text("keep\n", encoding="utf-8")
        nuke(home, "Minecraft", root)
        if (minecraft_games / "saves" / "world.txt").read_text(encoding="utf-8") != "keep\n":
            raise SystemExit("nuking Minecraft deleted the worlds")
        if not (mine / "dosdevices" / "d:").is_symlink():
            raise SystemExit("Minecraft lost drive D:")
        calls.clear()
        before_fetches = len(fetches)
        install_launcher(home, "Minecraft", runner, fetch, root)
        if fetches[before_fetches:] != [CATALOG["Minecraft"].setup_url]:
            raise SystemExit(f"Minecraft did not use the official launcher: {fetches[before_fetches:]}")
        if not calls or "wineboot" not in calls[0][0] or not calls[-1][0][-1].endswith("Minecraft.exe"):
            raise SystemExit(f"Minecraft was not opened: {calls}")
        mine_rows = {row["name"]: row for row in status_rows(home, root)}
        if not mine_rows["Minecraft"]["ready"]:
            raise SystemExit("Minecraft's launcher was not counted as installed")
        calls.clear()
        launch_installed(home, "Minecraft", runner, root)
        if not str(calls[-1][0][-1]).endswith("/minecraft/Minecraft.exe"):
            raise SystemExit(f"Launch did not open the Minecraft launcher: {calls}")
        installed_mine = (
            _prefix(root, CATALOG["Minecraft"])
            / "drive_c"
            / "Program Files (x86)"
            / "Minecraft Launcher"
            / "MinecraftLauncher.exe"
        )
        installed_mine.parent.mkdir(parents=True)
        installed_mine.write_bytes(b"MZ")
        calls.clear()
        launch_installed(home, "Minecraft", runner, root)
        if not str(calls[-1][0][-1]).endswith("MinecraftLauncher.exe"):
            raise SystemExit(f"Launch ignored the installed Minecraft launcher: {calls}")
        download = home / "Downloads"
        download.mkdir()
        chosen = download / "MyGame.exe"
        chosen.write_bytes(b"MZ")
        calls.clear()
        before_fetches = len(fetches)
        add_custom(home, "My Game", str(chosen), runner, fetch, root)
        if len(fetches) != before_fetches:
            raise SystemExit("a downloaded game was fetched from the network")
        if not calls or "wineboot" not in calls[0][0] or not calls[-1][0][-1].endswith("MyGame.exe"):
            raise SystemExit(f"the downloaded game was not opened: {calls}")
        custom_games = root / "custom1"
        custom_prefix = root / "launchers" / "custom1"
        drive = custom_prefix / "dosdevices" / "d:"
        if not custom_games.is_dir() or not drive.is_symlink() or drive.resolve() != custom_games.resolve():
            raise SystemExit("the game folder was not created")
        menu = (home / ".local/share/applications/wasd-launcher-custom1.desktop").read_text(encoding="utf-8")
        if "Name=My Game" not in menu or '--open "My Game"' not in menu:
            raise SystemExit("the game was not added to the menu")
        if (home / "Desktop").exists():
            raise SystemExit("a game was put on the desktop")
        (custom_games / "keep.txt").write_text("stay\n", encoding="utf-8")
        nuke(home, "My Game", root)
        if (custom_games / "keep.txt").read_text(encoding="utf-8") != "stay\n":
            raise SystemExit("nuking a game deleted its folder")
        linked = download / "linked.exe"
        linked.symlink_to(chosen)
        for bad_name, bad_program in (
            ("Battle.net", str(chosen)),
            ("My Game", str(chosen)),
            ("", str(chosen)),
            ('Say "hi"', str(chosen)),
            ("OK", "relative.exe"),
            ("OK", str(home / "missing.exe")),
            ("Linked", str(linked)),
        ):
            try:
                add_custom(home, bad_name, bad_program, runner, fetch, root)
            except LauncherError:
                pass
            else:
                raise SystemExit(f"a bad game was accepted: {bad_name}")

        global RUNNER, FETCH
        RUNNER = runner
        FETCH = fetch
        server = ThreadingHTTPServer(("127.0.0.1", 0), WindowHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.server_address[1]
        try:
            status = urllib.request.Request(
                f"http://127.0.0.1:{port}/status", data=b"", method="POST"
            )
            with urllib.request.urlopen(status, timeout=2) as response:
                body = json.loads(response.read().decode())
            if [row["name"] for row in body["rows"]] != [*CATALOG.keys(), "My Game"]:
                raise SystemExit(f"the window listed {body}")
            minecraft_row = body["rows"][list(CATALOG).index("Minecraft")]
            if minecraft_row["folder"] != str(root / "minecraft") or minecraft_row["custom"]:
                raise SystemExit(f"Minecraft was not on the list: {minecraft_row}")
            custom_row = body["rows"][-1]
            if (
                custom_row["id"] != "custom1"
                or custom_row["folder"] != str(root / "custom1")
                or not custom_row["custom"]
            ):
                raise SystemExit(f"the added game was not on the list: {custom_row}")
            refused = urllib.request.Request(
                f"http://127.0.0.1:{port}/install", data=b"Nope", method="POST"
            )
            try:
                urllib.request.urlopen(refused, timeout=2)
            except urllib.error.HTTPError as exc:
                if exc.code != 400:
                    raise SystemExit(f"an unknown launcher returned {exc.code}") from exc
            else:
                raise SystemExit("an unknown launcher was accepted")
            calls.clear()
            launched = urllib.request.Request(
                f"http://127.0.0.1:{port}/launch", data=b"Battle.net", method="POST"
            )
            with urllib.request.urlopen(launched, timeout=2) as response:
                if response.read().decode() != "ok" or not calls[-1][0][-1].endswith("Battle.net Launcher.exe"):
                    raise SystemExit("the window did not launch Battle.net")
            calls.clear()
            reinstall = urllib.request.Request(
                f"http://127.0.0.1:{port}/install", data=b"Battle.net", method="POST"
            )
            with urllib.request.urlopen(reinstall, timeout=2) as response:
                if response.read().decode() != "ok" or not calls[-1][0][-1].endswith("Battle.net-Setup.exe"):
                    raise SystemExit("the window reinstall did not open the setup")
            missing = urllib.request.Request(
                f"http://127.0.0.1:{port}/launch", data=b"Ubisoft Connect", method="POST"
            )
            try:
                urllib.request.urlopen(missing, timeout=2)
            except urllib.error.HTTPError as exc:
                if exc.code != 500:
                    raise SystemExit(f"launching a missing launcher returned {exc.code}") from exc
            else:
                raise SystemExit("a missing launcher was launched")
            calls.clear()
            acted = urllib.request.Request(
                f"http://127.0.0.1:{port}/remake", data=b"Rockstar Launcher", method="POST"
            )
            with urllib.request.urlopen(acted, timeout=2) as response:
                if response.read().decode() != "ok":
                    raise SystemExit("remake did not finish")
            rockstar_games = root / "rockstar" / "keep.txt"
            rockstar_games.write_text("stay\n", encoding="utf-8")
            nuke(home, "Rockstar Launcher", root)
            if rockstar_games.read_text(encoding="utf-8") != "stay\n":
                raise SystemExit("remake deleted Rockstar games")
            nested = download
            for _ in range(4):
                nested = nested / "folder-name"
            nested.mkdir(parents=True)
            extra = nested / "Extra.exe"
            extra.write_bytes(b"MZ")
            payload = json.dumps({"name": "Extra Game", "program": str(extra)}).encode()
            if len(payload) <= 64:
                raise SystemExit("the custom request was too short to prove the limit")
            calls.clear()
            added = urllib.request.Request(
                f"http://127.0.0.1:{port}/custom", data=payload, method="POST"
            )
            with urllib.request.urlopen(added, timeout=2) as response:
                if response.read().decode() != "ok" or not calls[-1][0][-1].endswith("Extra.exe"):
                    raise SystemExit("the window did not add the downloaded game")
            crowded = urllib.request.Request(
                f"http://127.0.0.1:{port}/install", data=b"A" * 80, method="POST"
            )
            try:
                urllib.request.urlopen(crowded, timeout=2)
            except urllib.error.HTTPError as exc:
                if exc.code != 400:
                    raise SystemExit(f"a long launcher name returned {exc.code}") from exc
            else:
                raise SystemExit("a long launcher name was accepted")
            taken = urllib.request.Request(
                f"http://127.0.0.1:{port}/custom",
                data=json.dumps({"name": "Battle.net", "program": str(extra)}).encode(),
                method="POST",
            )
            try:
                urllib.request.urlopen(taken, timeout=2)
            except urllib.error.HTTPError as exc:
                if exc.code != 500:
                    raise SystemExit(f"a reserved game name returned {exc.code}") from exc
            else:
                raise SystemExit("a reserved game name was accepted")
            with urllib.request.urlopen(status, timeout=2) as response:
                listed_rows = json.loads(response.read().decode())["rows"]
            listed = [row["name"] for row in listed_rows]
            if listed != [*CATALOG.keys(), "My Game", "Extra Game"]:
                raise SystemExit(f"the added games were {listed}")
            extra_row = listed_rows[-1]
            if extra_row["id"] != "custom2" or extra_row["folder"] != str(root / "custom2"):
                raise SystemExit(f"the second folder was not custom2: {extra_row}")
            calls.clear()
            named = urllib.request.Request(
                f"http://127.0.0.1:{port}/custom",
                data=json.dumps({"name": "Custom"}).encode(),
                method="POST",
            )
            with urllib.request.urlopen(named, timeout=2) as response:
                if response.read().decode() != "ok" or calls:
                    raise SystemExit("a name alone ran a program")
            quiet = urllib.request.Request(
                f"http://127.0.0.1:{port}/install", data=b"Custom", method="POST"
            )
            with urllib.request.urlopen(quiet, timeout=2) as response:
                if response.read().decode() != "ok" or calls:
                    raise SystemExit("install without a program ran one")
            with urllib.request.urlopen(status, timeout=2) as response:
                named_rows = json.loads(response.read().decode())["rows"]
            custom_only = named_rows[-1]
            if (
                custom_only["name"] != "Custom"
                or custom_only["id"] != "custom3"
                or custom_only["ready"]
                or custom_only["folder"] != str(root / "custom3")
            ):
                raise SystemExit(f"the named folder was wrong: {custom_only}")
            calls.clear()
            attached = urllib.request.Request(
                f"http://127.0.0.1:{port}/custom",
                data=json.dumps({"name": "Custom", "program": str(chosen)}).encode(),
                method="POST",
            )
            with urllib.request.urlopen(attached, timeout=2) as response:
                if response.read().decode() != "ok" or not calls[-1][0][-1].endswith("MyGame.exe"):
                    raise SystemExit("the program was not opened for that folder")
            menu = (home / ".local/share/applications/wasd-launcher-custom3.desktop").read_text(encoding="utf-8")
            if "Name=Custom" not in menu or '--open "Custom"' not in menu:
                raise SystemExit("the named folder was not in the menu")
            if (home / ".local/share/applications/wasd-launcher-custom.desktop").exists():
                raise SystemExit("the folder used the reserved name")
        finally:
            server.shutdown()
            RUNNER = real_runner
            FETCH = real_fetch

    here = Path(__file__).resolve().parent
    page = (here / "AppsPage.qml").read_text(encoding="utf-8")
    main = (here / "Main.qml").read_text(encoding="utf-8")
    window = (here / "Complete.qml").read_text(encoding="utf-8")
    launch = (here / "Launchers.qml").read_text(encoding="utf-8")
    order = [page.index('text: "General"'), page.index('text: "Launchers"'), page.index('text: "Agents"')]
    if order != sorted(order) or 'text: "Apps"' not in page:
        raise SystemExit("the groups are not General, Launchers, Agents under Apps")
    if "selectAllLaunchers" not in page or "selectNoneLaunchers" not in page:
        raise SystemExit("Launchers has no select all")
    if "Installing the launchers." not in window or 'status === "Installing what you checked."' not in window:
        raise SystemExit("first boot lost the launcher line or the app output")
    if "launcherNames" not in main or 'launchers[launcherNames[k]] = false' not in main:
        raise SystemExit("launchers do not start unchecked")
    if "Do not log in at the end of the Battle.net installation. Just close the window." not in main:
        raise SystemExit("Battle.net has no login warning")
    if "dismissBattleNetWarn" not in main:
        raise SystemExit("the Battle.net warning cannot be closed")
    for name in CATALOG:
        if name not in launch:
            raise SystemExit(f"{name} is missing from WASD Launchers")
    if "EA App" in launch or "EA App" in main:
        raise SystemExit("EA App is still in the installer")
    if "preview" not in launch or "/remake" not in launch or "/launch" not in launch:
        raise SystemExit("WASD Launchers cannot preview, launch, or remake")
    if "Nuke/Fix" not in launch or "Reinstall" not in launch or "Saved games stay." not in launch:
        raise SystemExit("WASD Launchers is missing Nuke/Fix, Reinstall, or the saved-games note")
    if "customNameField" not in launch or "addCustomGame" not in launch or '"/custom"' not in launch:
        raise SystemExit("WASD Launchers cannot add a downloaded game")
    if "Name a game" not in launch:
        raise SystemExit("WASD Launchers has no name box")
    if CATALOG["Minecraft"].setup_url != "https://launcher.mojang.com/download/Minecraft.exe":
        raise SystemExit("Minecraft is not the official launcher")
    if CATALOG["Minecraft"].user_link != ("AppData", "Roaming", ".minecraft"):
        raise SystemExit("Minecraft games would stay in the launcher")
    if window_args(True, 9) != ["--preview"]:
        raise SystemExit("preview would install a launcher")
    script = here.parent / "system_files/usr/bin/wasd-launchers"
    desktop = here.parent / "system_files/usr/share/applications/wasd-launchers.desktop"
    if "launchers.py" not in script.read_text(encoding="utf-8"):
        raise SystemExit("the menu command does not open the helper")
    entry = desktop.read_text(encoding="utf-8")
    if "Name=WASD Launchers" not in entry or "Exec=wasd-launchers" not in entry:
        raise SystemExit("the menu app is not named WASD Launchers")
    build = (here.parent / "build_files/build.sh").read_text(encoding="utf-8")
    if "test -s /usr/share/applications/wasd-launchers.desktop" not in build:
        raise SystemExit("the image build does not check for WASD Launchers")
    if "install -m 0755 /ctx/wasd-install/launchers.py /usr/libexec/launchers.py" not in build:
        raise SystemExit("the image build does not install the helper")
    print("launchers self-check ok")


def main(argv):
    global RUNNER, FETCH
    if "--self-check" in argv:
        self_check()
        return 0
    if os.environ.get("WASD_SELF_CHECK") == "1":
        print("self-check tried to open a launcher", file=sys.stderr)
        return 2
    if "--window" in argv:
        return serve_window("--preview" in argv)
    flag, name = _open_name(argv)
    if flag:
        if find_launcher(_home(), name) is None:
            print("Choose a launcher.", file=sys.stderr)
            return 2
        try:
            if flag == "--remake":
                remake(_home(), name, RUNNER, FETCH)
            else:
                install_launcher(_home(), name, RUNNER, FETCH)
        except LauncherError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0
    print("This is only used by WASD Launchers.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
