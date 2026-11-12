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
import shlex
import shutil
import socket
import struct
import subprocess
import sys
import tarfile
import threading
import urllib.parse
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GAMES_DIRS = (
    "launchers",
    "battlenet",
    "ubisoft",
    "rockstar",
    "minecraft",
    "minecraft-bedrock",
    "minecraft-modded",
    "multimc",
    "curseforge",
    "ftb",
    "starcitizen",
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
        mount_games=False,
        channel_dirs=(),
        native=False,
        native_args=(),
        native_env=(),
        archive_root="",
        native_program=(),
        host_link=(),
        bundle_libs=False,
    ):
        self.launcher_id = launcher_id
        self.setup_url = setup_url
        self.setup_name = setup_name
        self.program = tuple(program)
        self.games_link = tuple(games_link)
        self.user_link = tuple(user_link)
        self.games_dir = games_dir
        self.mount_games = bool(mount_games)
        self.channel_dirs = tuple(channel_dirs)
        # A native launcher is a Linux program. It is pointed at its games
        # folder. A user namespace makes Bubblewrap, PulseAudio, and
        # CurseForge's login handler see the wrong account.
        self.native = bool(native)
        self.native_args = tuple(native_args)
        self.native_env = tuple(native_env)
        # A packed Linux build is extracted beside the download. The program
        # that runs is native_program inside that tree, never the archive.
        self.archive_root = archive_root
        self.native_program = tuple(native_program)
        # A host path the program always uses. With mount_games, the games
        # folder is mounted on an empty directory there. Otherwise that path
        # is a link to the games folder. Java Minecraft still uses a mount,
        # because that launcher will not create files through a link.
        self.host_link = tuple(host_link)
        self.bundle_libs = bool(bundle_libs)


# Display names match WASD Install and WASD Launchers. The setup addresses
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
    "Java Minecraft": Launcher(
        "minecraft",
        "https://launcher.mojang.com/download/Minecraft.exe",
        "Minecraft.exe",
        ("drive_c", "Program Files (x86)", "Minecraft Launcher", "MinecraftLauncher.exe"),
        # Mounted over the games folder at launch. A symlink makes this
        # launcher refuse to create its files, and typing in it stalls.
        user_link=("AppData", "Roaming", ".minecraft"),
    ),
    "Minecraft Bedrock": Launcher(
        "minecraft-bedrock",
        "https://github.com/Wyze3306/BedrockOnLinux/releases/download/v2.3.0/BedrockOnLinux-2.3.0-x86_64.AppImage",
        "BedrockOnLinux-2.3.0-x86_64.AppImage",
        (),
        # BOL_HOME is the games folder. BedrockOnLinux starts umu, and umu's
        # bubblewrap refuses a user namespace that still has root capabilities.
        native=True,
        native_env=(("BOL_HOME", "{games}"),),
    ),
    "Modded Minecraft": Launcher(
        "minecraft-modded",
        "https://github.com/PolyMC/PolyMC/releases/download/8.1/PolyMC-Linux-amd64-8.1.AppImage",
        "PolyMC-Linux-amd64-8.1.AppImage",
        (),
        # --dir is the games folder. Instances and mods are written there.
        # The AppImage stays in the cache.
        native=True,
        native_args=("--dir", "{games}"),
    ),
    "MultiMC": Launcher(
        "multimc",
        "https://files.multimc.org/downloads/mmc-develop-lin64.tar.gz",
        "mmc-develop-lin64.tar.gz",
        (),
        # --dir is the games folder. WASD starts bin/MultiMC itself. The
        # upstream wrapper only adds the library path, which is set below.
        native=True,
        native_args=("--dir", "{games}"),
        archive_root="MultiMC",
        native_program=("bin", "MultiMC"),
        bundle_libs=True,
    ),
    "CurseForge": Launcher(
        "curseforge",
        "https://curseforge.overwolf.com/electron/linux/CurseForge-1.325.0-41594.AppImage",
        "CurseForge-1.325.0-41594.AppImage",
        (),
        # The Linux build's mod folder is Documents/curseforge. That path
        # is a link to the games folder. --no-sandbox lets the login handler
        # start when the browser returns.
        host_link=("Documents", "curseforge"),
        native=True,
        native_args=("--no-sandbox",),
    ),
    "FTB App": Launcher(
        "ftb",
        "https://piston.feed-the-beast.com/app/ftb-app-linux-1.30.1-x86_64.AppImage",
        "ftb-app-linux-1.30.1-x86_64.AppImage",
        (),
        # getAppHome in the 1.30.1 source puts instances, the runtime, and
        # settings in ~/.ftba. That path is a link to the games folder.
        # PulseAudio refuses the account namespace, so the app stays outside it.
        host_link=(".ftba",),
        native=True,
        native_args=("--no-sandbox",),
    ),
    "Star Citizen": Launcher(
        "starcitizen",
        "https://install.robertsspaceindustries.com/rel/2/RSI%20Launcher-Setup-2.19.1.exe",
        "RSI-Launcher-Setup.exe",
        ("drive_c", "Program Files", "Roberts Space Industries", "RSI Launcher", "RSI Launcher.exe"),
        # The launcher installs the game under this folder. An old setup file
        # is refused at sign-in, so the download follows their latest.yml.
        # LIVE is created here. The folder is mounted as a real directory,
        # because the launcher cannot create it through a link and then
        # shows error 8004.
        ("drive_c", "Program Files", "Roberts Space Industries", "StarCitizen"),
        mount_games=True,
        channel_dirs=("LIVE",),
    ),
}

# Roberts Space Industries publishes the current setup here. The catalog URL
# is the 2026-11-02 file, used when the check does not download.
RSI_LATEST = "https://install.robertsspaceindustries.com/rel/2/latest.yml"
_RSI_SETUP = re.compile(r"^RSI Launcher-Setup-[0-9]+\.[0-9]+\.[0-9]+\.exe$")
# A choice saved before Java Minecraft had that name.
ALIASES = {"Minecraft": "Java Minecraft"}
# Current Minecraft uses 21. Packs from 1.17 and 1.16 still need 17 and 8.
# Adoptium publishes one archive for each. The games drive holds them.
JAVA_RUNTIMES = (
    ("21", "https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jre/hotspot/normal/eclipse?project=jdk"),
    ("17", "https://api.adoptium.net/v3/binary/latest/17/ga/linux/x64/jre/hotspot/normal/eclipse?project=jdk"),
    ("8", "https://api.adoptium.net/v3/binary/latest/8/ga/linux/x64/jre/hotspot/normal/eclipse?project=jdk"),
)
JAVA_CONFIG = {
    "minecraft-modded": "polymc.cfg",
    "multimc": "multimc.cfg",
}
# The launcher is inside the mount namespace, where a new Brave cannot
# reach the session bus. This program asks the helper outside to open it.
_BROWSER_SHIM = """#!/usr/bin/env python3
import os
import socket
import sys

def chosen(argv):
    url = ""
    for arg in argv:
        if not arg.startswith("-"):
            url = arg
    return url

def allowed(url):
    if not url or len(url) > 4096:
        return False
    for ch in url:
        if ord(ch) < 33 or ord(ch) == 127:
            return False
    lower = url.lower()
    return lower.startswith("https://") or lower.startswith("http://") or lower.startswith("cfauth://")

def main():
    url = chosen(sys.argv[1:])
    if not allowed(url):
        return 1
    address = os.environ.get("WASD_OPEN_SOCKET", "")
    if not address:
        return 1
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(address)
        sock.sendall(url.encode("utf-8") + bytes([10]))
    except OSError:
        return 1
    finally:
        sock.close()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
"""


def canonical_name(name):
    if isinstance(name, str) and name in ALIASES:
        return ALIASES[name]
    return name


def names_from(data):
    """Return the launcher list, or None when the installer did not save one."""
    if not isinstance(data, dict) or "launchers" not in data:
        return None
    raw = data["launchers"]
    if not isinstance(raw, list):
        raise LauncherError("Choose the launchers again.")
    names = []
    for item in raw:
        item = canonical_name(item)
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
    taken = {item.casefold() for item in CATALOG}
    taken.update(item.casefold() for item in ALIASES)
    if name.casefold() in taken:
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
    if isinstance(name, str):
        name = canonical_name(name)
        if name in CATALOG:
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


def _account_names(user_name):
    names = []
    for name in (user_name, "steamuser"):
        if name and name not in names:
            names.append(name)
    return names


def _link_games(folder, parts, target):
    """Point a host path at the games folder. An empty directory becomes the link."""
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


def _prepare_game_mount(folder, parts, target):
    """Leave an empty real directory where the games folder is mounted.

    Minecraft will not create a folder through a symlink, and it retries
    that path while the window is waiting for a key. The mount exists only
    for the launch command. A remake deletes this empty directory and
    leaves the games folder alone.
    """
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
    slot = current / leaf
    target = _safe_dir(target)
    if slot.is_symlink():
        slot.unlink()
    elif slot.is_dir():
        for child in list(slot.iterdir()):
            dest = target / child.name
            if dest.exists() or dest.is_symlink():
                continue
            shutil.move(str(child), str(dest))
        if any(slot.iterdir()):
            raise LauncherError("The games drive could not be prepared.")
    elif slot.exists():
        raise LauncherError("The games drive could not be prepared.")
    slot.mkdir(parents=True, exist_ok=True)
    if slot.is_symlink() or not slot.is_dir() or any(slot.iterdir()):
        raise LauncherError("The games drive could not be prepared.")


def _noroot_library(home):
    """The id library. The image copy wins. A local copy is the fallback."""
    system = Path("/usr/libexec/wasd-noroot.so")
    if system.is_file() and not system.is_symlink():
        return system
    return Path(home) / ".local/lib/wasd-noroot.so"


def _write_preload_list(home):
    """The library list Java still reads after a launcher clears LD_PRELOAD."""
    path = Path(home) / ".cache/wasd/launchers/ld.so.preload"
    if path.is_symlink():
        raise LauncherError("Could not open that launcher.")
    path.parent.mkdir(parents=True, exist_ok=True)
    library = str(_noroot_library(home))
    text = library + "\n"
    host = Path("/etc/ld.so.preload")
    if host.is_file() and not host.is_symlink():
        try:
            existing = host.read_text(encoding="utf-8")
        except OSError:
            existing = ""
        if library not in existing.splitlines():
            if existing and not existing.endswith("\n"):
                existing += "\n"
            text = existing + text
    path.write_text(text, encoding="utf-8")
    os.chmod(path, 0o644)
    return path


def _browser_url(text):
    """A sign-in page or CurseForge's return link. Not a file path."""
    if not isinstance(text, str) or not text or len(text) > 4096:
        return False
    if any(ord(ch) < 33 or ord(ch) == 127 for ch in text):
        return False
    lowered = text.lower()
    return lowered.startswith(("https://", "http://", "cfauth://"))


def _browser_shim(home):
    path = Path(home) / ".cache/wasd/launchers/bin/xdg-open"
    if path.is_symlink():
        raise LauncherError("Could not open that launcher.")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.read_text(encoding="utf-8") != _BROWSER_SHIM:
        path.write_text(_BROWSER_SHIM, encoding="utf-8")
    os.chmod(path, 0o755)
    return path


def _browser_env(env, home):
    """Open Brave outside the namespace, and show Java this account's id."""
    shim = _browser_shim(home)
    bindir = str(shim.parent)
    parts = [item for item in env.get("PATH", "").split(":") if item and item != bindir]
    env["PATH"] = ":".join([bindir, *parts])
    env["BROWSER"] = str(shim)
    env["WASD_SPOOF_UID"] = "1"


def _game_preload(env, home):
    """Hand the id library to a game whose launcher removes LD_PRELOAD."""
    library = str(_noroot_library(home))
    current = env.get("GAME_PRELOAD", "")
    parts = [item for item in current.split(":") if item and item != library]
    env["GAME_PRELOAD"] = ":".join([library, *parts])


def _host_open(url):
    if os.environ.get("WASD_SELF_CHECK") == "1":
        raise SystemExit("self-check tried to open a browser")
    if not _browser_url(url):
        return
    opener = "/usr/bin/xdg-open"
    if not os.access(opener, os.X_OK):
        return
    subprocess.Popen(
        [opener, url],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        close_fds=True,
    )


class _BrowserBridge:
    """Accept a sign-in link from inside the namespace and open it outside."""

    def __init__(self, env, opener=None):
        self._sock = None
        self._thread = None
        self._stop = False
        self.path = None
        self._opener = opener or _host_open
        if env.get("WASD_SPOOF_UID") != "1":
            return
        if os.environ.get("WASD_SELF_CHECK") == "1" and opener is None:
            return
        runtime = os.environ.get("XDG_RUNTIME_DIR", "")
        if not runtime or not Path(runtime).is_dir() or Path(runtime).is_symlink():
            return
        directory = Path(runtime) / "wasd"
        try:
            directory.mkdir(mode=0o700, exist_ok=True)
            path = directory / f"open-{os.getpid()}.sock"
            if path.exists() or path.is_symlink():
                path.unlink()
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.bind(str(path))
            os.chmod(path, 0o600)
            sock.listen(8)
            sock.settimeout(0.2)
        except OSError:
            return
        self.path = path
        self._sock = sock
        env["WASD_OPEN_SOCKET"] = str(path)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        sock = self._sock
        while not self._stop:
            try:
                conn, _addr = sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                data = b""
                conn.settimeout(1)
                while b"\n" not in data and len(data) < 4200:
                    chunk = conn.recv(2048)
                    if not chunk:
                        break
                    data += chunk
                text = data.split(b"\n", 1)[0].decode("utf-8", "replace")
                if _browser_url(text):
                    self._opener(text)
            except OSError:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def close(self):
        self._stop = True
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2)
        if self.path is not None:
            try:
                Path(self.path).unlink(missing_ok=True)
            except OSError:
                pass


def _register_cfauth(home, launcher, program=None):
    """Let the browser hand CurseForge's login back to the app."""
    if launcher.launcher_id != "curseforge":
        return None
    app = Path(program) if program is not None else _cache(home, launcher)
    if app.is_symlink() or not app.is_file():
        return None
    desktop = Path(home) / ".local/share/applications/wasd-cfauth.desktop"
    if desktop.is_symlink():
        raise LauncherError("The menu entry is a link.")
    desktop.parent.mkdir(parents=True, exist_ok=True)
    command = _cfauth_exec(app)
    desktop.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=CurseForge\n"
        "NoDisplay=true\n"
        f"Exec={command}\n"
        "MimeType=x-scheme-handler/cfauth;\n"
        "Terminal=false\n",
        encoding="utf-8",
    )
    os.chmod(desktop, 0o644)
    if os.environ.get("WASD_SELF_CHECK") == "1":
        return desktop
    subprocess.run(
        ["xdg-mime", "default", desktop.name, "x-scheme-handler/cfauth"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return desktop


def _cfauth_exec(app):
    """Launch the same CurseForge binary the running app was started from."""
    app = Path(app)
    command = "env APPIMAGE_EXTRACT_AND_RUN=1 "
    if app.name in ("AppRun", _CURSE_WRAPPER):
        # AppRun only finds its own directory when APPDIR is already set.
        # --no-sandbox is not a file, so its search walks off the tree.
        command += "APPDIR=" + shlex.quote(str(app.parent)) + " "
    return command + shlex.quote(str(app)) + " --no-sandbox %u"


def _valid_squashfs(superblock, offset, size):
    if len(superblock) < 48 or superblock[:4] != b"hsqs":
        return False
    (
        _magic,
        inodes,
        _mkfs,
        block_size,
        _fragments,
        compression,
        block_log,
        _flags,
        _ids,
        major,
        minor,
        _root,
        used,
    ) = struct.unpack_from("<IIIIIHHHHHHQQ", superblock)
    if major != 4 or minor != 0 or not 1 <= compression <= 6:
        return False
    if not 1 <= inodes <= 1_000_000 or not 4096 <= block_size <= 1_048_576:
        return False
    if block_log >= 32 or (1 << block_log) != block_size:
        return False
    if used < 96 or offset < 0 or offset + used > size:
        return False
    return True


def _squashfs_offset(path):
    """The real squashfs superblock. An AppImage can contain an earlier false hit."""
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    size = len(data)
    if size < 96:
        return None
    start = 0
    while True:
        hit = data.find(b"hsqs", start)
        if hit < 0 or hit + 48 > size:
            return None
        if _valid_squashfs(data[hit:hit + 48], hit, size):
            return hit
        start = hit + 1


def _remove_tree(path):
    path = Path(path)
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.exists():
        _unlink_tree(path)


def _unsquash_appimage(image, dest, offset):
    dest = Path(dest)
    if dest.exists() or dest.is_symlink():
        raise LauncherError("Could not open that launcher.")
    tool = shutil.which("unsquashfs")
    if tool:
        result = subprocess.run(
            [tool, "-o", str(offset), "-d", str(dest), str(image)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0 or dest.is_symlink() or not dest.is_dir():
            _remove_tree(dest)
            raise LauncherError("Could not open that launcher.")
        return
    work = dest.parent / ".wasd-curse-work"
    if work.is_symlink():
        raise LauncherError("Could not open that launcher.")
    _remove_tree(work)
    work.mkdir()
    try:
        result = subprocess.run(
            [str(image), "--appimage-extract"],
            cwd=work,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        got = work / "squashfs-root"
        if result.returncode != 0 or got.is_symlink() or not got.is_dir():
            raise LauncherError("Could not open that launcher.")
        got.rename(dest)
    finally:
        _remove_tree(work)


# ostree cannot mount an AppImage, so the runtime unpacks CurseForge into one
# shared temporary directory and removes that directory when the process exits.
# A second start rewrites the agent while the first one still has it open, and
# modpack unzip then fails inside that file. Unpack once beside the download.
_CURSE_EXTRACT_STAMP = "wasd-curse-2"
_CURSE_WRAPPER = "wasd-run"


def _curse_stamp(image):
    stat = image.stat()
    return f"{_CURSE_EXTRACT_STAMP} {stat.st_size} {stat.st_mtime_ns}\n"


def _curse_agent(tree):
    return (
        Path(tree)
        / "resources/app.asar.unpacked/plugins/curse/linux/Curse.Agent.Host"
    )


def _curse_wrapper_script():
    """Start the private copy. A later launch follows APPIMAGE."""
    return (
        "#!/bin/bash\n"
        "here=$(CDPATH= cd -- \"$(dirname -- \"$0\")\" && pwd)\n"
        "export APPDIR=\"$here\"\n"
        "export APPIMAGE=\"$here/" + _CURSE_WRAPPER + "\"\n"
        "unset APPIMAGE_EXTRACT_AND_RUN\n"
        "exec \"$here/AppRun\" \"$@\"\n"
    )


def _curse_ready(dest, stamp):
    dest = Path(dest)
    if dest.is_symlink() or not dest.is_dir():
        return False
    for name in ("AppRun", "curseforge", _CURSE_WRAPPER, ".wasd-extract"):
        path = dest / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            return False
        if name != ".wasd-extract" and not os.access(path, os.X_OK):
            return False
    agent = _curse_agent(dest)
    if agent.is_symlink() or not agent.is_file() or agent.stat().st_size < 1024:
        return False
    try:
        text = (dest / ".wasd-extract").read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False
    return text == stamp


def _mark_extracted(staging, stamp):
    staging = Path(staging)
    apprun = staging / "AppRun"
    binary = staging / "curseforge"
    if apprun.is_symlink() or binary.is_symlink():
        raise LauncherError("Could not open that launcher.")
    _executable(apprun)
    _executable(binary)
    wrapper = staging / _CURSE_WRAPPER
    if wrapper.is_symlink():
        raise LauncherError("Could not open that launcher.")
    temporary = staging / (_CURSE_WRAPPER + ".wasd")
    if temporary.is_symlink():
        raise LauncherError("Could not open that launcher.")
    temporary.write_text(_curse_wrapper_script(), encoding="utf-8")
    os.chmod(temporary, 0o755)
    os.replace(temporary, wrapper)
    stamp_path = staging / ".wasd-extract"
    if stamp_path.is_symlink():
        raise LauncherError("Could not open that launcher.")
    stamp_path.write_text(stamp, encoding="utf-8")


def _extract_curseforge(image):
    """Unpack CurseForge once beside its download and return that starter.

    A file that is not an AppImage is left unchanged, so the self-check's
    stand-in still launches as itself.
    """
    image = Path(image)
    if image.is_symlink() or not image.is_file() or image.stat().st_size < 96:
        return None
    parent = image.parent
    if parent.is_symlink() or not parent.is_dir():
        raise LauncherError("Could not open that launcher.")
    dest = parent / "extracted"
    if dest.is_symlink():
        raise LauncherError("Could not open that launcher.")
    stamp = _curse_stamp(image)
    if _curse_ready(dest, stamp):
        return _executable(dest / _CURSE_WRAPPER)
    offset = _squashfs_offset(image)
    if offset is None:
        return None
    feed_log("Preparing CurseForge.\n")
    staging = parent / "extracted.partial"
    if staging.is_symlink():
        raise LauncherError("Could not open that launcher.")
    _remove_tree(staging)
    try:
        _unsquash_appimage(image, staging, offset)
        host = _curse_agent(staging)
        if host.is_symlink() or not host.is_file() or host.stat().st_size < 1024:
            raise LauncherError("Could not open that launcher.")
        _mark_extracted(staging, stamp)
        if dest.exists() or dest.is_symlink():
            _remove_tree(dest)
        staging.rename(dest)
    except LauncherError:
        _remove_tree(staging)
        raise
    except OSError as exc:
        _remove_tree(staging)
        raise LauncherError("Could not open that launcher.") from exc
    return _executable(dest / _CURSE_WRAPPER)


def _curseforge_program(env, launcher, cached):
    if launcher.launcher_id != "curseforge":
        return cached
    prepared = _extract_curseforge(cached)
    if prepared is None:
        return cached
    env["APPDIR"] = str(prepared.parent)
    # Login and a second window start $APPIMAGE. Keep that on this copy.
    env["APPIMAGE"] = str(prepared)
    env.pop("APPIMAGE_EXTRACT_AND_RUN", None)
    return prepared


def _java_binary(games, version):
    return Path(games) / "java" / version / "bin" / "java"


def _usable_java(path):
    path = Path(path)
    return (
        path.is_file()
        and not path.is_symlink()
        and os.access(path, os.X_OK)
        and path.stat().st_size > 0
    )


def _set_cfg_key(path, key, value):
    path = Path(path)
    if path.is_symlink():
        raise LauncherError("Could not open that launcher.")
    line = f"{key}={value}"
    rows = []
    if path.exists():
        if not path.is_file():
            raise LauncherError("Could not open that launcher.")
        rows = path.read_text(encoding="utf-8").splitlines()
    found = False
    out = []
    prefix = key + "="
    for row in rows:
        if row.startswith(prefix):
            if not found:
                out.append(line)
                found = True
            continue
        out.append(row)
    if not found:
        out.append(line)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def _extract_java(archive, dest):
    dest = Path(dest)
    if dest.is_symlink():
        raise LauncherError("Could not open that launcher.")
    parent = _safe_dir(dest.parent)
    staging = parent / (".wasd-java-" + dest.name)
    if staging.exists() or staging.is_symlink():
        _unlink_tree(staging)
    staging.mkdir()

    def _java_member(member, _dest):
        name = member.name
        if not name or name.startswith("/") or ".." in Path(name).parts:
            raise LauncherError("Could not open that launcher.")
        if member.issym():
            link = member.linkname or ""
            # Adoptium's legal notices link to a sibling with ../. That
            # stays inside the archive. A link that leaves it does not.
            if link.startswith("/"):
                raise LauncherError("Could not open that launcher.")
            resolved = Path(os.path.normpath(str(Path(name).parent / link)))
            if resolved.is_absolute() or ".." in resolved.parts:
                raise LauncherError("Could not open that launcher.")
        elif not (member.isfile() or member.isdir()):
            raise LauncherError("Could not open that launcher.")
        return member

    try:
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(staging, filter=_java_member)
        found = None
        for candidate in staging.rglob("java"):
            if candidate.parent.name != "bin" or candidate.is_symlink() or not candidate.is_file():
                continue
            found = candidate.parent.parent
            break
        if found is None:
            raise LauncherError("Could not open that launcher.")
        if dest.exists() or dest.is_symlink():
            _unlink_tree(dest)
        found.rename(dest)
    except LauncherError:
        raise
    except (tarfile.TarError, OSError) as exc:
        raise LauncherError("Could not open that launcher.") from exc
    finally:
        if staging.exists() or staging.is_symlink():
            _unlink_tree(staging)
    binary = dest / "bin" / "java"
    if binary.is_symlink() or not binary.is_file():
        raise LauncherError("Could not open that launcher.")
    if not os.access(binary, os.X_OK):
        binary.chmod(0o755)
    return binary


def _ensure_java(games, fetch):
    """Download Java 21, 17, and 8 onto the games drive. Java 21 is the default."""
    games = Path(games)
    if games.is_symlink() or not games.is_dir():
        raise LauncherError("The games drive could not be prepared.")
    for version, url in JAVA_RUNTIMES:
        binary = _java_binary(games, version)
        if _usable_java(binary):
            continue
        archive = games / "java" / f"{version}.tar.gz"
        if archive.is_symlink():
            raise LauncherError("Could not open that launcher.")
        archive.parent.mkdir(parents=True, exist_ok=True)
        try:
            fetch(url, archive)
            _extract_java(archive, games / "java" / version)
        except LauncherError:
            raise
        except Exception as exc:
            raise LauncherError("Could not open that launcher.") from exc
        finally:
            if archive.is_file() and not archive.is_symlink():
                archive.unlink()
        if not _usable_java(binary):
            raise LauncherError("Could not open that launcher.")


def _write_java_path(games, launcher):
    name = JAVA_CONFIG.get(launcher.launcher_id)
    if not name:
        return
    _set_cfg_key(Path(games) / name, "JavaPath", str(_java_binary(games, "21")))


def _java_env(env, launcher, games):
    if launcher.launcher_id != "minecraft-modded":
        return
    env["POLYMC_JAVA_PATHS"] = ":".join(
        str(_java_binary(games, version)) for version, _url in JAVA_RUNTIMES
    )


def _cfg_value(path, key):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        return ""
    prefix = key + "="
    try:
        rows = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for row in rows:
        if row.startswith(prefix):
            return row[len(prefix):]
    return ""


def _version_tuple(text):
    """The first three numeric parts of a Minecraft version. 1.12.2 is (1, 12, 2)."""
    if not isinstance(text, str) or not text:
        return None
    parts = []
    for piece in text.split("."):
        if not piece.isdigit():
            return None
        parts.append(int(piece))
        if len(parts) == 3:
            break
    if len(parts) < 2 or parts[0] < 1:
        return None
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _java_for_minecraft(version):
    """Java 8, 17, or 21 for a release. A version this table does not know is left alone."""
    key = _version_tuple(version)
    if key is None:
        return ""
    if key < (1, 17, 0):
        return "8"
    if key < (1, 20, 5):
        return "17"
    if key[0] == 1:
        return "21"
    return ""


def _minecraft_version(pack):
    pack = Path(pack)
    if pack.is_symlink() or not pack.is_file():
        return ""
    try:
        data = json.loads(pack.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return ""
    components = data.get("components") if isinstance(data, dict) else None
    if not isinstance(components, list):
        return ""
    for item in components:
        if isinstance(item, dict) and item.get("uid") == "net.minecraft":
            version = item.get("version")
            if isinstance(version, str):
                return version
    return ""


def _assign_instance_java(games):
    """Give each pack the Java it needs, unless that pack already has one chosen."""
    games = Path(games)
    root = games / "instances"
    if root.is_symlink() or not root.is_dir():
        return
    for child in root.iterdir():
        if child.is_symlink() or not child.is_dir() or child.name.startswith("."):
            continue
        pack = child / "mmc-pack.json"
        cfg = child / "instance.cfg"
        if cfg.is_symlink() or pack.is_symlink():
            continue
        java = _java_for_minecraft(_minecraft_version(pack))
        if not java:
            continue
        if _cfg_value(cfg, "OverrideJavaLocation") == "true":
            continue
        binary = _java_binary(games, java)
        if not _usable_java(binary):
            continue
        _set_cfg_key(cfg, "OverrideJavaLocation", "true")
        _set_cfg_key(cfg, "JavaPath", str(binary))


def _raise_memory(games, launcher):
    """MultiMC's own default is 1024 MB. A current pack runs out of that."""
    if launcher.launcher_id != "multimc":
        return
    path = Path(games) / JAVA_CONFIG[launcher.launcher_id]
    if path.is_symlink():
        return
    current = _cfg_value(path, "MaxMemAlloc")
    if current.isdigit() and int(current) > 1024:
        return
    _set_cfg_key(path, "MaxMemAlloc", "8192")


def _prepare_native(env, home, launcher, games, fetch, program=None):
    _browser_env(env, home)
    _game_preload(env, home)
    _register_cfauth(home, launcher, program)
    if launcher.launcher_id in JAVA_CONFIG:
        _ensure_java(games, fetch)
        _write_java_path(games, launcher)
        _assign_instance_java(games)
        _raise_memory(games, launcher)
        _java_env(env, launcher, games)


def _mounted_argv(argv, mounts, home=None, workdir=None):
    """Run argv with the games folder mounted on each empty directory."""
    if not mounts:
        return list(argv)
    # The namespace root is this account. umu still sees euid 0 unless
    # wasd-noroot.so reports the id captured here, before the namespace.
    euid = os.getuid()
    if euid <= 0:
        raise LauncherError("The games drive could not be prepared.")
    preload = _write_preload_list(home) if home is not None else None
    lines = ["set -eu"]
    for source, target in mounts:
        source = Path(source)
        target = Path(target)
        if (
            not source.is_absolute()
            or source.is_symlink()
            or not source.is_dir()
            or not target.is_absolute()
            or target.is_symlink()
            or not target.is_dir()
            or any(target.iterdir())
        ):
            raise LauncherError("The games drive could not be prepared.")
        lines.append(
            "mount --bind " + shlex.quote(str(source)) + " " + shlex.quote(str(target))
        )
    lines.append("so=/usr/libexec/wasd-noroot.so")
    lines.append('if [ ! -f "$so" ]; then so="${HOME}/.local/lib/wasd-noroot.so"; fi')
    lines.append('if [ ! -f "$so" ]; then exit 1; fi')
    if preload is not None:
        lines.append(
            "if [ -e /etc/ld.so.preload ]; then mount --bind "
            + shlex.quote(str(preload))
            + " /etc/ld.so.preload; fi"
        )
    lines.append(f"export WASD_EUID={euid}")
    lines.append('export LD_PRELOAD="$so${LD_PRELOAD:+:$LD_PRELOAD}"')
    if workdir is not None:
        lines.append("cd " + shlex.quote(str(workdir)))
    lines.append('exec "$@"')
    return [
        "unshare",
        "--user",
        "--mount",
        "--map-root-user",
        "--propagation",
        "private",
        "--",
        "bash",
        "-c",
        "\n".join(lines) + "\n",
        "bash",
        *argv,
    ]


def _prefer_minecraft_vulkan(games):
    # OpenGL creates the window and plays the music, and the window stays black.
    # Vulkan draws that same window. An explicit graphics choice stays as it is.
    games = Path(games)
    if games.is_symlink() or not games.is_dir():
        return
    path = games / "options.txt"
    if path.is_symlink():
        return
    chosen = 'preferredGraphicsBackend:"vulkan"'
    try:
        if not path.exists():
            path.write_text(chosen + "\n", encoding="utf-8")
            return
        if not path.is_file():
            return
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    default = 'preferredGraphicsBackend:"default"'
    if default not in text:
        return
    try:
        path.write_text(text.replace(default, chosen, 1), encoding="utf-8")
    except OSError:
        return


def _channel_dir(games, name):
    """Create one game channel folder, such as Star Citizen's LIVE folder."""
    if not isinstance(name, str) or name in ("", ".", "..") or any(ch in name for ch in "/\\"):
        raise LauncherError("The games drive could not be prepared.")
    folder = Path(games) / name
    if folder.is_symlink():
        raise LauncherError("The launcher folder is a link.")
    _safe_dir(folder)


def _host_slot(home, launcher):
    if not launcher.host_link:
        return None
    return Path(home).joinpath(*launcher.host_link)


def _mounts(user_name, launcher, prefix, games, home=None):
    mounts = []
    if launcher.user_link:
        for name in _account_names(user_name):
            slot = prefix / "drive_c" / "users" / name
            for part in launcher.user_link:
                slot = slot / part
            mounts.append((games, slot))
    if launcher.mount_games and launcher.host_link:
        slot = _host_slot(home, launcher)
        if slot is None:
            raise LauncherError("The games drive could not be prepared.")
        mounts.append((games, slot))
    elif launcher.mount_games and launcher.games_link:
        mounts.append((games, prefix.joinpath(*launcher.games_link)))
    return mounts


def _mount_slot(launcher, prefix, home=None):
    if launcher.mount_games and launcher.host_link:
        slot = _host_slot(home, launcher)
        return "" if slot is None else str(slot)
    if launcher.mount_games and launcher.games_link:
        return str(prefix.joinpath(*launcher.games_link))
    return ""


def _mount_text(text, slot, games=""):
    return str(text).replace("{mount}", slot).replace("{games}", str(games))


def _workdir_argv(argv, workdir):
    """Start in the games folder without entering a user namespace."""
    script = "set -eu\ncd " + shlex.quote(str(workdir)) + '\nexec "$@"\n'
    return ["bash", "-c", script, "bash", *argv]


def _launch_argv(user_name, launcher, prefix, games, args, home=None):
    mounts = _mounts(user_name, launcher, prefix, games, home)
    slot = _mount_slot(launcher, prefix, home)
    if launcher.native:
        command = [_mount_text(item, slot, games) for item in args]
        command.extend(_mount_text(item, slot, games) for item in launcher.native_args)
    else:
        command = umu_argv(list(args))
    workdir = games if launcher.launcher_id in JAVA_CONFIG else None
    if mounts:
        command = _mounted_argv(command, mounts, home, workdir)
    elif workdir is not None:
        command = _workdir_argv(command, workdir)
    _check_argv(command)
    return command


# CurseForge's account lives here, not in the empty prefix Nuke/Fix deletes.
_LAUNCHER_STATE = {
    "curseforge": (".config", "CurseForge"),
}


def _share_with_container(env, games):
    """Let pressure-vessel see a games folder that is outside the home directory.

    BedrockOnLinux runs umu inside that container. The container shares $HOME
    and does not share /games, so wineboot cannot execute umu-shim and stops
    before GameInput. The path is appended to any list already set.
    """
    games = str(games)
    if not games or not Path(games).is_absolute():
        return
    key = "PRESSURE_VESSEL_FILESYSTEMS_RW"
    parts = [part for part in env.get(key, "").split(":") if part and part != games]
    env[key] = ":".join([games, *parts])


def launch_env(prefix, launcher, slot="", games=""):
    """The environment for one launch. A native program is not a Wine prefix."""
    if not launcher.native:
        return umu_env(prefix, launcher)
    env = os.environ.copy()
    for key in (
        "WINEPREFIX",
        "GAMEID",
        "PROTONPATH",
        "STORE",
        "WINE_SIMULATE_WRITECOPY",
        "WINEDLLOVERRIDES",
    ):
        env.pop(key, None)
    # The performance profile watches this on the running program.
    env["WASD_GAME"] = "1"
    # ostree has no FUSE for an AppImage to mount itself.
    env["APPIMAGE_EXTRACT_AND_RUN"] = "1"
    for key, value in launcher.native_env:
        env[str(key)] = _mount_text(value, slot, games)
    if launcher.launcher_id == "minecraft-bedrock":
        _share_with_container(env, games)
    if launcher.launcher_id == "curseforge":
        # Electron refuses to register cfauth unless it can name its desktop file.
        # The browser then opens, and the return link never reaches the app.
        env["CHROME_DESKTOP"] = "wasd-cfauth.desktop"
    return env


def _executable(path):
    """Make a cached native program executable. A link is refused."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise LauncherError("Could not open that launcher.")
    if not os.access(path, os.X_OK):
        try:
            path.chmod(0o755)
        except OSError as exc:
            raise LauncherError("Could not open that launcher.") from exc
    if not os.access(path, os.X_OK):
        raise LauncherError("Could not open that launcher.")
    return path


def ensure_links(prefix, games, saves, user_name, launcher, home=None):
    prefix = _safe_dir(prefix)
    dos = _safe_dir(prefix / "dosdevices")
    _replace_link(dos / "d:", games)
    for name in _account_names(user_name):
        folder = _safe_dir(prefix / "drive_c" / "users" / name)
        _replace_link(folder / "Documents", saves)
        my_docs = folder / "My Documents"
        if my_docs.is_symlink() or not my_docs.exists():
            _replace_link(my_docs, saves)
        if launcher.user_link:
            _prepare_game_mount(folder, launcher.user_link, games)
    if launcher.host_link:
        if home is None:
            raise LauncherError("The games drive could not be prepared.")
        if launcher.mount_games:
            _prepare_game_mount(Path(home), launcher.host_link, games)
        else:
            _link_games(Path(home), launcher.host_link, games)
    if launcher.games_link:
        moved = prefix.joinpath(*launcher.games_link)
        parent = _safe_dir(moved.parent)
        if parent != moved.parent and moved.parent.is_symlink():
            raise LauncherError("The launcher folder is a link.")
        if launcher.mount_games:
            _prepare_game_mount(parent, (moved.name,), games)
            for name in launcher.channel_dirs:
                _channel_dir(games, name)
        else:
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
    ensure_links(prefix, games, saves, home.name, launcher, home)
    return prefix


def _clear_launcher_state(home, launcher, games):
    """Remove a native launcher's account files. The games folder stays."""
    parts = _LAUNCHER_STATE.get(launcher.launcher_id)
    if not parts:
        return
    path = Path(home).joinpath(*parts)
    if path.is_symlink():
        path.unlink()
        return
    if not path.exists():
        return
    if not path.is_dir():
        raise LauncherError("The launcher folder is a link.")
    resolved = path.resolve()
    kept = Path(games).resolve()
    if resolved == kept or _inside(resolved, kept) or _inside(kept, resolved):
        raise LauncherError("The launcher folder is a link.")
    _unlink_tree(path)


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
    _clear_launcher_state(home, launcher, games)
    layout(home, name, root)
    return prefix


def _png_rgba(width, height, rgba):
    if width < 1 or height < 1 or len(rgba) != width * height * 4:
        return b""

    def chunk(tag, payload):
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    rows = []
    stride = width * 4
    for y in range(height):
        rows.append(b"\x00" + rgba[y * stride:(y + 1) * stride])
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
        + chunk(b"IEND", b"")
    )


def _dib_to_rgba(dib):
    """Turn one 32-bit icon image into top-down RGBA. Other depths are skipped."""
    if len(dib) < 40:
        return None
    size, width, height, planes, bitcount, comp = struct.unpack_from("<IiiHHI", dib, 0)
    if size < 40 or width < 1 or width > 1024 or planes != 1 or bitcount != 32 or comp not in (0, 3):
        return None
    xor_h = height // 2 if height >= width * 2 else height
    if xor_h < 1 or xor_h > 1024:
        return None
    pixels = size + xor_h * width * 4
    if len(dib) < pixels:
        return None
    raw = dib[size:pixels]
    if all(raw[i] == 0 for i in range(3, len(raw), 4)):
        fixed = bytearray(raw)
        for i in range(3, len(fixed), 4):
            fixed[i] = 255
        raw = bytes(fixed)
    rgba = bytearray(xor_h * width * 4)
    row = width * 4
    for y in range(xor_h):
        src = (xor_h - 1 - y) * row
        for x in range(width):
            b, g, r, a = raw[src:src + 4]
            rgba[(y * width + x) * 4:(y * width + x) * 4 + 4] = bytes((r, g, b, a))
            src += 4
    return width, xor_h, bytes(rgba)


def _rva_offset(rva, sections):
    for virtual, virtual_size, raw, raw_size in sections:
        span = max(virtual_size, raw_size)
        if virtual <= rva < virtual + span:
            return raw + (rva - virtual)
    return None


def pe_icon_png(path):
    """Return a PNG of the largest 32-bit icon stored in a program, or None."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if len(data) < 0x40 or data[:2] != b"MZ":
        return None
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if pe <= 0 or pe + 24 > len(data) or data[pe:pe + 4] != b"PE\0\0":
        return None
    coff = pe + 4
    sections_n, optional_size = struct.unpack_from("<H", data, coff + 2)[0], struct.unpack_from("<H", data, coff + 16)[0]
    optional = coff + 20
    if optional + optional_size > len(data) or sections_n > 96:
        return None
    magic = struct.unpack_from("<H", data, optional)[0]
    if magic == 0x20B:
        count_at, dirs_at = optional + 108, optional + 112
    elif magic == 0x10B:
        count_at, dirs_at = optional + 92, optional + 96
    else:
        return None
    if count_at + 4 > len(data):
        return None
    dir_count = struct.unpack_from("<I", data, count_at)[0]
    if dir_count < 3 or dirs_at + dir_count * 8 > len(data):
        return None
    resource_rva, resource_size = struct.unpack_from("<II", data, dirs_at + 16)
    if resource_rva == 0 or resource_size == 0:
        return None
    sections = []
    table = optional + optional_size
    for index in range(sections_n):
        at = table + index * 40
        if at + 40 > len(data):
            return None
        virtual_size, virtual, raw_size, raw = struct.unpack_from("<IIII", data, at + 8)
        sections.append((virtual, virtual_size, raw, raw_size))
    base = _rva_offset(resource_rva, sections)
    if base is None:
        return None

    def directory(relative):
        at = base + relative
        if at + 16 > len(data):
            return []
        named, ids = struct.unpack_from("<HH", data, at + 12)
        found = []
        cursor = at + 16
        for entry in range(named + ids):
            if cursor + 8 > len(data):
                break
            ident, offset = struct.unpack_from("<II", data, cursor)
            cursor += 8
            if entry >= named:
                found.append((ident, offset))
        return found

    best = None
    for ident, offset in directory(0):
        if ident != 3 or not offset & 0x80000000:
            continue
        for _name, name_offset in directory(offset & 0x7FFFFFFF):
            if not name_offset & 0x80000000:
                continue
            for _lang, leaf in directory(name_offset & 0x7FFFFFFF):
                if leaf & 0x80000000:
                    continue
                info = base + leaf
                if info + 16 > len(data):
                    continue
                leaf_rva, leaf_size = struct.unpack_from("<II", data, info)
                file_at = _rva_offset(leaf_rva, sections)
                if file_at is None or leaf_size < 40 or file_at + leaf_size > len(data):
                    continue
                parsed = _dib_to_rgba(data[file_at:file_at + leaf_size])
                if parsed and (best is None or parsed[0] > best[0]):
                    best = parsed
    if best is None:
        return None
    return _png_rgba(best[0], best[1], best[2])


def _pe_containing_dib(dib):
    """A program file whose only icon is dib. The self-check reads it back."""
    def directory(named, ids):
        return struct.pack("<IIHHHH", 0, 0, 0, 0, named, ids)

    def entry(ident, offset, subdir):
        if subdir:
            offset |= 0x80000000
        return struct.pack("<II", ident, offset)

    blob = b"".join((
        directory(0, 1),
        entry(3, 24, True),
        directory(0, 1),
        entry(1, 48, True),
        directory(0, 1),
        entry(0, 72, False),
        struct.pack("<IIII", 0x1000 + 88, len(dib), 0, 0),
        dib,
    ))
    optional = bytearray(240)
    struct.pack_into("<H", optional, 0, 0x20B)
    struct.pack_into("<I", optional, 16, 0)  # AddressOfEntryPoint
    struct.pack_into("<Q", optional, 24, 0x140000000)
    struct.pack_into("<I", optional, 32, 0x1000)
    struct.pack_into("<I", optional, 36, 0x200)
    struct.pack_into("<I", optional, 56, 0x2000)
    struct.pack_into("<I", optional, 60, 0x200)
    struct.pack_into("<H", optional, 68, 3)
    struct.pack_into("<H", optional, 108, 16)
    struct.pack_into("<II", optional, 112 + 16, 0x1000, len(blob))
    coff = struct.pack("<HHIIIHH", 0x8664, 1, 0, 0, 0, len(optional), 0x22)
    section = struct.pack("<8sIIIIIIHHI", b".rsrc\0\0\0", len(blob), 0x1000, 0x200, 0x200, 0, 0, 0, 0, 0x40000040)
    dos = bytearray(64)
    dos[:2] = b"MZ"
    struct.pack_into("<I", dos, 0x3C, 64)
    file_bytes = bytes(dos) + b"PE\0\0" + coff + bytes(optional) + section
    file_bytes += b"\0" * (0x200 - len(file_bytes))
    file_bytes += blob
    file_bytes += b"\0" * ((0x200 - (len(blob) % 0x200)) % 0x200)
    return file_bytes


def _menu_icon(home, name, root):
    """Use the launcher's own icon after one has been extracted.

    A new menu entry keeps the WASD icon until that file exists.
    Proton's shortcut icon wins. Otherwise the icon is taken from the program.
    """
    launcher = require_launcher(home, name)
    home = Path(home)
    icons = _prefix(root, launcher) / "drive_c" / "proton_shortcuts" / "icons"
    best = None
    best_rank = -1
    hint = Path(launcher.program[-1]).stem.lower() if launcher.program else ""
    if icons.is_dir() and not icons.is_symlink():
        for png in icons.glob("*x*/apps/*.png"):
            if not png.is_file() or png.is_symlink():
                continue
            try:
                size = int(png.parent.parent.name.split("x", 1)[0])
            except ValueError:
                continue
            rank = size + (100000 if hint and hint in png.name.lower() else 0)
            if rank >= best_rank:
                best = png
                best_rank = rank
    if best is None:
        program = program_path(home, name, root)
        data = b""
        if program.is_file() and not program.is_symlink():
            data = pe_icon_png(program) or b""
    else:
        try:
            data = best.read_bytes()
        except OSError:
            data = b""
    if not data:
        return "wasd-logo"
    dest_dir = home / ".local/share/icons/wasd"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{launcher.launcher_id}.png"
    if dest.is_symlink():
        return "wasd-logo"
    dest.write_bytes(data)
    os.chmod(dest, 0o644)
    return str(dest)


def _desktop_text(home, name, root):
    script = Path(__file__).resolve()
    python = sys.executable
    command = f'"{python}" "{script}" --open "{name}"'
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name}\n"
        f"Exec={command}\n"
        f"Icon={_menu_icon(home, name, root)}\n"
        "Terminal=false\n"
        "Categories=Game;\n"
        "StartupNotify=true\n"
    )


def write_menu(home, name, root=None):
    name = canonical_name(name)
    launcher = require_launcher(home, name)
    home = Path(home)
    root = Path(root) if root is not None else games_root(home)
    desktop = home / ".local/share/applications" / f"wasd-launcher-{launcher.launcher_id}.desktop"
    if desktop.is_symlink():
        raise LauncherError("The menu entry is a link.")
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text(_desktop_text(home, name, root), encoding="utf-8")
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
        if launcher.archive_root:
            return _archived_program(home, launcher)
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


def _archive_root(home, launcher):
    return _cache(home, launcher).parent / "app" / launcher.archive_root


def _archived_program(home, launcher):
    return _archive_root(home, launcher).joinpath(*launcher.native_program)


def _safe_extract(archive, dest):
    """Extract a launcher archive without following a link out of dest."""
    dest = _safe_dir(dest)
    try:
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar.getmembers():
                name = member.name
                if not name or name.startswith("/") or ".." in Path(name).parts:
                    raise LauncherError("Could not open that launcher.")
                if member.issym() or member.islnk():
                    raise LauncherError("Could not open that launcher.")
            tar.extractall(dest, filter="data")
    except LauncherError:
        raise
    except (tarfile.TarError, OSError) as exc:
        raise LauncherError("Could not open that launcher.") from exc
    return dest


def _unpack_archive(home, launcher):
    """Leave the unpacked program beside the download, outside the mount."""
    program = _archived_program(home, launcher)
    if program.is_symlink():
        raise LauncherError("Could not open that launcher.")
    if program.is_file():
        return _executable(program)
    archive = _cache(home, launcher)
    if archive.is_symlink() or not archive.is_file() or archive.stat().st_size == 0:
        raise LauncherError("Could not open that launcher.")
    root_parent = _archive_root(home, launcher).parent
    if root_parent.exists():
        if root_parent.is_symlink():
            raise LauncherError("Could not open that launcher.")
        _unlink_tree(root_parent)
    _safe_extract(archive, root_parent)
    if program.is_symlink() or not program.is_file():
        raise LauncherError("Could not open that launcher.")
    return _executable(program)


def _bundle_env(env, root):
    """Point the launcher at its own libraries, and keep those off the game.

    MultiMC's start script does this. WASD starts bin/MultiMC with the same
    variables.
    """
    previous = env.get("LD_LIBRARY_PATH", "")
    if "GAME_LIBRARY_PATH" not in env:
        env["GAME_LIBRARY_PATH"] = previous
    if "GAME_PRELOAD" not in env:
        env["GAME_PRELOAD"] = env.get("LD_PRELOAD", "")
    env["LD_LIBRARY_PATH"] = str(Path(root) / "bin")
    return env


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


# Proton turns on write-copy for these stores. Battle.net crashes after
# sign-in without it. The menu launch has to name the store.
_WRITECOPY = {
    "battlenet": "battlenet",
    "ubisoft": "ubisoft",
}


def umu_env(prefix, launcher):
    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix)
    env["GAMEID"] = "umu-default"
    env["WASD_GAME"] = "1"
    # A native launcher is shown this account's id. Wine has to keep the
    # namespace id, because that id owns the prefix.
    env.pop("WASD_SPOOF_UID", None)
    env.pop("WASD_OPEN_SOCKET", None)
    env.pop("STORE", None)
    env.pop("WINE_SIMULATE_WRITECOPY", None)
    env.pop("PROTONPATH", None)
    store = _WRITECOPY.get(launcher.launcher_id)
    if store:
        env["STORE"] = store
        env["WINE_SIMULATE_WRITECOPY"] = "1"
    if launcher.launcher_id == "starcitizen":
        # umu's Star Citizen fixes, and the Proton build that currently
        # passes its anti-cheat check. The other launchers stay on the
        # default Proton.
        env["GAMEID"] = "umu-starcitizen"
        env["PROTONPATH"] = "GE-Proton"
        env["WINEDLLOVERRIDES"] = "dxwebsetup.exe,dotNetFx45_Full_setup.exe=d"
    return env


def rsi_setup_url(text):
    """The setup file named by Roberts Space Industries' latest.yml."""
    if not isinstance(text, str):
        raise LauncherError("Could not open that launcher.")
    name = ""
    for line in text.splitlines():
        if line.startswith("path: "):
            name = line[len("path: "):].strip()
            break
    if not _RSI_SETUP.fullmatch(name):
        raise LauncherError("Could not open that launcher.")
    return "https://install.robertsspaceindustries.com/rel/2/" + urllib.parse.quote(name)


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
    bridge = _BrowserBridge(env)
    try:
        return _stream(argv, env)
    finally:
        bridge.close()


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
    name = canonical_name(name)
    launcher = require_launcher(home, name)
    home = Path(home)
    feed_log(name + "\n")
    prefix = layout(home, name, root)
    root = Path(root) if root is not None else games_root(home)
    games = _games(root, launcher)
    saves = _saves(root, launcher)
    write_menu(home, name, root)
    if not launcher.setup_url and not launcher.setup_name:
        return prefix
    env = launch_env(prefix, launcher, _mount_slot(launcher, prefix, home), games)
    if not launcher.native and not (prefix / "system.reg").is_file():
        boot = _launch_argv(home.name, launcher, prefix, games, ["wineboot", "-u"], home)
        if runner(boot, env) != 0:
            raise LauncherError("Could not open that launcher.")
        ensure_links(prefix, games, saves, home.name, launcher, home)
    program = program_path(home, name, root)
    if launcher.archive_root:
        setup = _cache(home, launcher)
        ready = program.is_file() and not program.is_symlink()
        if (force_setup or not ready) and (
            setup.is_symlink() or not setup.is_file() or setup.stat().st_size == 0
        ):
            if not launcher.setup_url:
                raise LauncherError("Choose the program you downloaded.")
            try:
                fetch(launcher.setup_url, setup)
            except LauncherError:
                raise
            except Exception as exc:
                raise LauncherError("Could not open that launcher.") from exc
        target = _unpack_archive(home, launcher)
    elif not force_setup and program.is_file() and not program.is_symlink():
        target = program
    elif not launcher.setup_url:
        target = _cache(home, launcher)
        if target.is_symlink() or not target.is_file() or target.stat().st_size == 0:
            raise LauncherError("Choose the program you downloaded.")
    else:
        setup = _cache(home, launcher)
        setup_url = launcher.setup_url
        if launcher.launcher_id == "starcitizen" and os.environ.get("WASD_SELF_CHECK") != "1":
            listing = setup.with_name("latest.yml")
            try:
                fetch(RSI_LATEST, listing)
                setup_url = rsi_setup_url(listing.read_text(encoding="utf-8"))
            except LauncherError:
                listing.unlink(missing_ok=True)
                raise
            except OSError as exc:
                listing.unlink(missing_ok=True)
                raise LauncherError("Could not open that launcher.") from exc
            listing.unlink(missing_ok=True)
        if setup.is_symlink() or not setup.is_file() or setup.stat().st_size == 0:
            try:
                fetch(setup_url, setup)
            except LauncherError:
                raise
            except Exception as exc:
                raise LauncherError("Could not open that launcher.") from exc
        if setup.is_symlink() or not setup.is_file():
            raise LauncherError("Could not open that launcher.")
        target = setup
    # A later open can turn the slot back into a link. Mounting needs a real directory.
    if launcher.user_link or launcher.mount_games or launcher.host_link:
        ensure_links(prefix, games, saves, home.name, launcher, home)
    if launcher.launcher_id == "minecraft":
        _prefer_minecraft_vulkan(games)
    if launcher.native and not launcher.archive_root:
        target = _executable(target)
    target = _curseforge_program(env, launcher, target)
    if launcher.bundle_libs:
        _bundle_env(env, _archive_root(home, launcher))
    if launcher.native:
        _prepare_native(env, home, launcher, games, fetch, target)
    command = _launch_argv(home.name, launcher, prefix, games, [str(target)], home)
    code = runner(command, env)
    ensure_links(prefix, games, saves, home.name, launcher, home)
    write_menu(home, name, root)
    if code != 0:
        raise LauncherError("Could not open that launcher.")
    return prefix


def launch_installed(home, name, runner, root=None, fetch=None):
    """Open the installed program. Do not download or run its setup."""
    name = canonical_name(name)
    launcher = require_launcher(home, name)
    home = Path(home)
    root = Path(root) if root is not None else games_root(home)
    program = program_path(home, name, root)
    if not program.is_file() or program.is_symlink():
        raise LauncherError("That launcher is not installed.")
    prefix = _prefix(root, launcher)
    if prefix.is_symlink() or not prefix.is_dir():
        raise LauncherError("Could not open that launcher.")
    games = _games(root, launcher)
    saves = _saves(root, launcher)
    if launcher.user_link or launcher.mount_games or launcher.host_link:
        ensure_links(prefix, games, saves, home.name, launcher, home)
    if launcher.launcher_id == "minecraft":
        _prefer_minecraft_vulkan(games)
    if launcher.archive_root:
        program = _unpack_archive(home, launcher)
    elif launcher.native:
        program = _executable(program)
    feed_log(name + "\n")
    if fetch is None:
        fetch = FETCH
    env = launch_env(prefix, launcher, _mount_slot(launcher, prefix, home), games)
    program = _curseforge_program(env, launcher, program)
    if launcher.bundle_libs:
        _bundle_env(env, _archive_root(home, launcher))
    if launcher.native:
        _prepare_native(env, home, launcher, games, fetch, program)
    command = _launch_argv(home.name, launcher, prefix, games, [str(program)], home)
    code = runner(command, env)
    write_menu(home, name, root)
    if code != 0:
        raise LauncherError("Could not open that launcher.")
    return prefix


def browse_launcher(home, name, root=None):
    """Open this launcher's games folder. The mount slot stays empty."""
    name = canonical_name(name)
    launcher = require_launcher(home, name)
    home = Path(home)
    root = Path(root) if root is not None else games_root(home)
    games = _games(root, launcher)
    if games.is_symlink():
        raise LauncherError("Could not open that folder.")
    games = _safe_dir(games)
    if OPENER(str(games)) != 0:
        raise LauncherError("Could not open that folder.")
    return games


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
    write_menu(home, name, root)
    return prefix


def offers_reinstall(launcher):
    """The vendor setup is a different program from the one Launch opens.

    A native launcher's download is the program. Reinstall would open that
    same file, which Launch already does.
    """
    return bool(launcher.program) and not launcher.native


def _status_row(home, name, launcher, root, custom):
    prefix = _prefix(root, launcher)
    program = program_path(home, name, root)
    return {
        "name": name,
        "id": launcher.launcher_id,
        "ready": program.is_file() and not program.is_symlink(),
        "prepared": prefix.is_dir() and not prefix.is_symlink(),
        "reinstall": offers_reinstall(launcher),
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


def real_open(path):
    """Open a games folder in the file manager. The self-check never does."""
    if os.environ.get("WASD_SELF_CHECK") == "1":
        raise SystemExit("self-check tried to open a folder")
    return subprocess.run(["xdg-open", str(path)]).returncode


OPENER = real_open


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
            elif self.path == "/browse":
                browse_launcher(_home(), text)
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
        if "api.adoptium.net" in url:
            payload = b"#!/bin/sh\nexit 0\n"
            info = tarfile.TarInfo("jdk/bin/java")
            info.size = len(payload)
            info.mode = 0o755
            buf = __import__("io").BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                tar.addfile(info, __import__("io").BytesIO(payload))
            dest.write_bytes(buf.getvalue())
        elif dest.name.endswith(".tar.gz"):
            payload = b"#!/bin/sh\nexit 0\n"
            info = tarfile.TarInfo("MultiMC/bin/MultiMC")
            info.size = len(payload)
            info.mode = 0o755
            buf = __import__("io").BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                tar.addfile(info, __import__("io").BytesIO(payload))
            dest.write_bytes(buf.getvalue())
        else:
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
    try:
        real_open("/tmp")
    except SystemExit as exc:
        if "self-check tried to open a folder" not in str(exc):
            raise
    else:
        raise SystemExit("self-check opened a folder")

    if names_from({"password": False}) is not None:
        raise SystemExit("a missing launcher list was treated as a choice")
    if names_from({"launchers": []}) != []:
        raise SystemExit("an empty launcher list was refused")
    if names_from({"launchers": ["Minecraft"]}) != ["Java Minecraft"]:
        raise SystemExit("a saved Minecraft choice was refused")
    try:
        names_from({"launchers": ["Minecraft", "Java Minecraft"]})
    except LauncherError:
        pass
    else:
        raise SystemExit("Minecraft was listed twice")
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
        if calls[0][1].get("WASD_GAME") != "1":
            raise SystemExit("a launcher was not marked as a game")
        if calls[0][1].get("STORE") != "battlenet" or calls[0][1].get("WINE_SIMULATE_WRITECOPY") != "1":
            raise SystemExit("Battle.net did not turn on write-copy")
        if calls[0][1].get("WASD_SPOOF_UID") or calls[0][1].get("WASD_OPEN_SOCKET"):
            raise SystemExit("Battle.net would hide its prefix owner")
        rock_env = umu_env(prefix, CATALOG["Rockstar Launcher"])
        if "STORE" in rock_env or "WINE_SIMULATE_WRITECOPY" in rock_env:
            raise SystemExit("Rockstar turned on the Battle.net workaround")
        ubi_env = umu_env(prefix, CATALOG["Ubisoft Connect"])
        if ubi_env.get("STORE") != "ubisoft" or ubi_env.get("WINE_SIMULATE_WRITECOPY") != "1":
            raise SystemExit("Ubisoft did not turn on write-copy")
        if "PROTONPATH" in ubi_env or ubi_env.get("GAMEID") != "umu-default":
            raise SystemExit("Ubisoft used the Star Citizen Proton")
        star_env = umu_env(prefix, CATALOG["Star Citizen"])
        if star_env.get("GAMEID") != "umu-starcitizen" or star_env.get("PROTONPATH") != "GE-Proton":
            raise SystemExit("Star Citizen did not use its Proton")
        if star_env.get("WINEDLLOVERRIDES") != "dxwebsetup.exe,dotNetFx45_Full_setup.exe=d":
            raise SystemExit("Star Citizen would run the launcher's own installers")
        if "STORE" in star_env:
            raise SystemExit("Star Citizen turned on the Battle.net workaround")
        opened = calls[-1][0]
        if opened[-1].endswith("Battle.net-Setup.exe") is False or len(opened) != 2:
            raise SystemExit(f"the vendor window was not the only argument: {opened}")
        desktop = home / ".local/share/applications/wasd-launcher-battlenet.desktop"
        entry = desktop.read_text(encoding="utf-8")
        if "Name=Battle.net" not in entry or '--open "Battle.net"' not in entry:
            raise SystemExit("Battle.net was not added to the menu")
        if "Icon=wasd-logo" not in entry:
            raise SystemExit("a new launcher did not start with the WASD icon")
        icon_dir = prefix / "drive_c/proton_shortcuts/icons/256x256/apps"
        icon_dir.mkdir(parents=True, exist_ok=True)
        (icon_dir / "1AC2_Battle.net Launcher.0.png").write_bytes(b"blizzard-icon")
        write_menu(home, "Battle.net", root)
        entry = desktop.read_text(encoding="utf-8")
        icon = ""
        for line in entry.splitlines():
            if line.startswith("Icon="):
                icon = line.split("=", 1)[1]
        if not icon.endswith("/.local/share/icons/wasd/battlenet.png"):
            raise SystemExit(f"Battle.net kept the WASD icon: {icon}")
        if Path(icon).read_bytes() != b"blizzard-icon":
            raise SystemExit("the Battle.net icon was not copied")
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
        if not rows["Battle.net"]["reinstall"] or rows["Minecraft Bedrock"]["reinstall"]:
            raise SystemExit(f"Reinstall was offered on the wrong row: {rows['Battle.net']} {rows['Minecraft Bedrock']}")
        write_marker()
        if marker_path().read_text(encoding="utf-8") != "ok\n":
            raise SystemExit("the launcher marker was not written")
        log = Path(os.environ["WASD_APP_LOG"]).read_text(encoding="utf-8")
        if "Battle.net\n" not in log or "Ubisoft Connect\n" not in log:
            raise SystemExit("the install log did not name the launcher")
        mine = layout(home, "Minecraft", root)
        world_slot = mine / "drive_c" / "users" / "steamuser" / "AppData" / "Roaming" / ".minecraft"
        home_slot = mine / "drive_c" / "users" / home.name / "AppData" / "Roaming" / ".minecraft"
        minecraft_games = root / "minecraft"
        if world_slot.is_symlink() or home_slot.is_symlink() or any(world_slot.iterdir()) or any(home_slot.iterdir()):
            raise SystemExit("Minecraft worlds are behind a link")
        (minecraft_games / "saves").mkdir()
        (minecraft_games / "saves" / "world.txt").write_text("keep\n", encoding="utf-8")
        (world_slot / "extra.txt").write_text("moved\n", encoding="utf-8")
        ensure_links(mine, minecraft_games, root / "saves" / "minecraft", home.name, CATALOG["Java Minecraft"])
        if (minecraft_games / "extra.txt").read_text(encoding="utf-8") != "moved\n":
            raise SystemExit("a Minecraft file stayed in the launcher")
        if any(world_slot.iterdir()):
            raise SystemExit("the Minecraft mount folder was not emptied")
        nuke(home, "Minecraft", root)
        if (minecraft_games / "saves" / "world.txt").read_text(encoding="utf-8") != "keep\n":
            raise SystemExit("nuking Minecraft deleted the worlds")
        if (minecraft_games / "extra.txt").read_text(encoding="utf-8") != "moved\n":
            raise SystemExit("nuking Minecraft deleted a moved file")
        if not (mine / "dosdevices" / "d:").is_symlink():
            raise SystemExit("Minecraft lost drive D:")
        calls.clear()
        before_fetches = len(fetches)
        install_launcher(home, "Minecraft", runner, fetch, root)
        if fetches[before_fetches:] != [CATALOG["Java Minecraft"].setup_url]:
            raise SystemExit(f"Minecraft did not use the official launcher: {fetches[before_fetches:]}")
        if not calls or calls[0][0][0] != "unshare" or "wineboot" not in calls[0][0]:
            raise SystemExit(f"Minecraft was not opened on its games folder: {calls}")
        mounted = "\n".join(str(part) for part in calls[-1][0])
        if "mount --bind" not in mounted or str(minecraft_games) not in mounted or str(world_slot) not in mounted:
            raise SystemExit(f"Minecraft was not mounted on the games folder: {calls[-1][0]}")
        if "wasd-noroot.so" not in mounted or "WASD_EUID=" not in mounted or "ld.so.preload" not in mounted:
            raise SystemExit("Minecraft would launch as root")
        if calls[-1][1].get("WASD_SPOOF_UID") or calls[-1][1].get("WASD_OPEN_SOCKET"):
            raise SystemExit("Minecraft would hide its prefix owner")
        if "\ncd " in mounted:
            raise SystemExit("Minecraft was started in its games folder")
        if not calls[-1][0][-1].endswith("Minecraft.exe"):
            raise SystemExit(f"Minecraft was not opened: {calls}")
        options = minecraft_games / "options.txt"
        if options.read_text(encoding="utf-8") != 'preferredGraphicsBackend:"vulkan"\n':
            raise SystemExit("Minecraft did not choose Vulkan")
        options.write_text(
            'version:1\npreferredGraphicsBackend:"default"\nfullscreen:false\n',
            encoding="utf-8",
        )
        if world_slot.is_symlink() or world_slot.is_file():
            world_slot.unlink()
        elif world_slot.exists():
            shutil.rmtree(world_slot)
        world_slot.symlink_to(minecraft_games)
        (mine / "system.reg").write_text("WINE REGISTRY Version 2\n", encoding="utf-8")
        calls.clear()
        install_launcher(home, "Minecraft", runner, fetch, root)
        if world_slot.is_symlink() or not world_slot.is_dir() or any(world_slot.iterdir()):
            raise SystemExit("Minecraft left the games folder as a link")
        mounted = "\n".join(str(part) for part in calls[-1][0])
        if "mount --bind" not in mounted or "wineboot" in calls[-1][0]:
            raise SystemExit(f"Minecraft did not mount after the link came back: {calls[-1][0]}")
        kept = options.read_text(encoding="utf-8")
        if 'preferredGraphicsBackend:"vulkan"' not in kept or "fullscreen:false" not in kept:
            raise SystemExit(f"Minecraft did not switch the default graphics choice: {kept!r}")
        options.write_text('preferredGraphicsBackend:"opengl"\n', encoding="utf-8")
        pixel = struct.pack("<IiiHHIIiiII", 40, 1, 2, 1, 32, 0, 4, 0, 0, 0, 0)
        pixel += bytes((0x10, 0x20, 0x30, 0xFF)) + b"\x00\x00\x00\x00"
        _cache(home, CATALOG["Java Minecraft"]).write_bytes(_pe_containing_dib(pixel))
        write_menu(home, "Minecraft", root)
        mine_icon = ""
        mine_entry = (home / ".local/share/applications/wasd-launcher-minecraft.desktop").read_text(encoding="utf-8")
        for line in mine_entry.splitlines():
            if line.startswith("Icon="):
                mine_icon = line.split("=", 1)[1]
        if not mine_icon.endswith("/.local/share/icons/wasd/minecraft.png"):
            raise SystemExit(f"Minecraft kept the WASD icon: {mine_icon}")
        if not Path(mine_icon).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise SystemExit("Minecraft's icon was not its own")
        mine_rows = {row["name"]: row for row in status_rows(home, root)}
        if not mine_rows["Java Minecraft"]["ready"]:
            raise SystemExit("Minecraft's launcher was not counted as installed")
        calls.clear()
        launch_installed(home, "Minecraft", runner, root)
        if not str(calls[-1][0][-1]).endswith("/minecraft/Minecraft.exe"):
            raise SystemExit(f"Launch did not open the Minecraft launcher: {calls}")
        if options.read_text(encoding="utf-8") != 'preferredGraphicsBackend:"opengl"\n':
            raise SystemExit("Minecraft overwrote an explicit graphics choice")
        installed_mine = (
            _prefix(root, CATALOG["Java Minecraft"])
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
        if "Name=Java Minecraft" not in mine_entry or '--open "Java Minecraft"' not in mine_entry:
            raise SystemExit("Minecraft's menu entry kept the old name")

        def check_native(name, folder, marker):
            launcher = CATALOG[name]
            calls.clear()
            before = len(fetches)
            install_launcher(home, name, runner, fetch, root)
            expected = [launcher.setup_url]
            if launcher.launcher_id in JAVA_CONFIG:
                expected.extend(url for _version, url in JAVA_RUNTIMES)
            if fetches[before:] != expected:
                raise SystemExit(f"{name} did not use its published program: {fetches[before:]}")
            if any(
                "umu-run" in str(part) or str(part) == "wineboot" or str(part).endswith("/wineboot")
                for argv, _env in calls
                for part in argv
            ):
                raise SystemExit(f"{name} was opened with Wine: {calls}")
            games = root / folder
            app = _archived_program(home, launcher) if launcher.archive_root else _cache(home, launcher)
            if games.is_symlink() or not games.is_dir():
                raise SystemExit(f"{name} games folder is a link")
            argv, env = calls[-1]
            mounted = "\n".join(str(part) for part in argv)
            if argv[0] == "unshare" or "mount --bind" in mounted or "ld.so.preload" in mounted:
                raise SystemExit(f"{name} was put in a user namespace: {argv}")
            if str(app) not in argv:
                raise SystemExit(f"{name} was not pointed at its games folder: {argv}")
            try:
                app.resolve().relative_to(games.resolve())
            except ValueError:
                pass
            else:
                raise SystemExit(f"{name} was launched from its games folder")
            if env.get("APPIMAGE_EXTRACT_AND_RUN") != "1" or env.get("WASD_GAME") != "1":
                raise SystemExit(f"{name} would not run its own program")
            if any(key in env for key in ("GAMEID", "WINEPREFIX", "PROTONPATH")):
                raise SystemExit(f"{name} was given a Wine prefix")
            if marker == "BOL_HOME":
                if env.get("BOL_HOME") != str(games) or launcher.mount_games or launcher.games_link:
                    raise SystemExit(f"{name} would write outside its games folder: {env.get('BOL_HOME')}")
                shared = env.get("PRESSURE_VESSEL_FILESYSTEMS_RW", "").split(":")
                if str(games) not in shared:
                    raise SystemExit(f"{name} would hide its Wine prefix from the container")
            elif marker == "--dir":
                if "--dir" not in argv or argv[argv.index("--dir") + 1] != str(games):
                    raise SystemExit(f"{name} would write outside its games folder: {argv}")
            elif marker == "--no-sandbox":
                link = home.joinpath(*launcher.host_link)
                if "--no-sandbox" not in argv or not link.is_symlink() or link.resolve() != games.resolve():
                    raise SystemExit(f"{name} would write outside its games folder: {argv}")
            else:
                raise SystemExit(f"{name} has no games-folder check")
            if marker != "--no-sandbox" and "--no-sandbox" in argv:
                raise SystemExit(f"{name} was given a sandbox flag it does not need")
            library = str(_noroot_library(home))
            if env.get("WASD_SPOOF_UID") != "1":
                raise SystemExit(f"{name} would run as root")
            shim = home / ".cache/wasd/launchers/bin/xdg-open"
            if env.get("BROWSER") != str(shim) or env.get("PATH", "").split(":")[0] != str(shim.parent):
                raise SystemExit(f"{name} would not open a browser")
            if not shim.is_file() or shim.is_symlink() or not os.access(shim, os.X_OK):
                raise SystemExit(f"{name} has no browser opener")
            opener = shim.read_text(encoding="utf-8")
            if "cfauth://" not in opener or "https://" not in opener or "file://" in opener:
                raise SystemExit("the browser opener would open a file")
            if env.get("GAME_PRELOAD", "").split(":")[0] != library:
                raise SystemExit(f"{name} would drop the id library")
            if launcher.launcher_id in JAVA_CONFIG:
                if f"\ncd {shlex.quote(str(games))}" not in mounted:
                    raise SystemExit(f"{name} would not find Java")
                for version, _url in JAVA_RUNTIMES:
                    binary = _java_binary(games, version)
                    if not _usable_java(binary):
                        raise SystemExit(f"{name} is missing Java {version}")
                cfg_path = games / JAVA_CONFIG[launcher.launcher_id]
                cfg = cfg_path.read_text(encoding="utf-8")
                if f"JavaPath={_java_binary(games, '21')}" not in cfg:
                    raise SystemExit(f"{name} did not choose Java")
                if launcher.launcher_id == "minecraft-modded":
                    paths = env.get("POLYMC_JAVA_PATHS", "").split(":")
                    for version, _url in JAVA_RUNTIMES:
                        if str(_java_binary(games, version)) not in paths:
                            raise SystemExit(f"{name} would hide a Java")
                elif env.get("POLYMC_JAVA_PATHS"):
                    raise SystemExit(f"{name} was given PolyMC's Java list")
            else:
                if "\ncd " in mounted:
                    raise SystemExit(f"{name} was started in its games folder")
                if (games / "java").exists():
                    raise SystemExit(f"{name} downloaded Java it does not need")
                if env.get("POLYMC_JAVA_PATHS"):
                    raise SystemExit(f"{name} was given a Java list")
            if launcher.launcher_id == "curseforge":
                desk = home / ".local/share/applications/wasd-cfauth.desktop"
                text = desk.read_text(encoding="utf-8")
                if "x-scheme-handler/cfauth" not in text or "%u" not in text or str(app) not in text:
                    raise SystemExit("CurseForge login cannot return")
                if "APPIMAGE_EXTRACT_AND_RUN=1" not in text or "--no-sandbox" not in text:
                    raise SystemExit("CurseForge login would not start")
                if env.get("CHROME_DESKTOP") != desk.name:
                    raise SystemExit("CurseForge would not register its login")
                if (home / ".config/mimeapps.list").exists():
                    raise SystemExit("self-check changed the browser")
            if launcher.bundle_libs:
                if not str(app).endswith("/bin/MultiMC"):
                    raise SystemExit(f"{name} was not its own program: {app}")
                if env.get("LD_LIBRARY_PATH") != str(Path(app).parent):
                    raise SystemExit(f"{name} did not use its libraries: {env.get('LD_LIBRARY_PATH')}")
                if "GAME_LIBRARY_PATH" not in env or "GAME_PRELOAD" not in env:
                    raise SystemExit(f"{name} would hand its libraries to the game")
            if not app.is_file() or app.is_symlink() or not os.access(app, os.X_OK):
                raise SystemExit(f"{name} was not executable")
            if launcher.launcher_id in JAVA_CONFIG:
                cfg_path = games / JAVA_CONFIG[launcher.launcher_id]

                def pack(folder_name, version, cfg):
                    folder_path = games / "instances" / folder_name
                    folder_path.mkdir(parents=True)
                    (folder_path / "mmc-pack.json").write_text(
                        '{"components":[{"uid":"net.minecraft","version":"' + version + '"}]}',
                        encoding="utf-8",
                    )
                    if cfg:
                        (folder_path / "instance.cfg").write_text(cfg, encoding="utf-8")
                    return folder_path

                old = pack("Old Pack", "1.12.2", "OverrideJavaLocation=false\n")
                middle = pack("Middle Pack", "1.20.1", "")
                chosen = pack("Chosen Pack", "1.7.10", "OverrideJavaLocation=true\nJavaPath=/opt/custom/java\n")
                current = pack("Current Pack", "1.21.1", "")
                later = pack("Later Pack", "26.1", "name=Later\n")
                _set_cfg_key(cfg_path, "MaxMemAlloc", "1024")
                launch_installed(home, name, runner, root, fetch)

                def instance_text(path):
                    return (path / "instance.cfg").read_text(encoding="utf-8")

                old_text = instance_text(old)
                if "OverrideJavaLocation=true" not in old_text or f"JavaPath={_java_binary(games, '8')}" not in old_text:
                    raise SystemExit(f"{name} left an old pack on the wrong Java: {old_text!r}")
                middle_text = instance_text(middle)
                if f"JavaPath={_java_binary(games, '17')}" not in middle_text:
                    raise SystemExit(f"{name} left a 1.20 pack on the wrong Java: {middle_text!r}")
                chosen_text = instance_text(chosen)
                if "JavaPath=/opt/custom/java" not in chosen_text or chosen_text.count("JavaPath=") != 1:
                    raise SystemExit(f"{name} replaced a chosen Java: {chosen_text!r}")
                current_text = instance_text(current)
                if f"JavaPath={_java_binary(games, '21')}" not in current_text:
                    raise SystemExit(f"{name} left a current pack without Java: {current_text!r}")
                later_text = instance_text(later)
                if "JavaPath=" in later_text or "OverrideJavaLocation=" in later_text:
                    raise SystemExit(f"{name} guessed Java for a newer pack: {later_text!r}")
                mem = cfg_path.read_text(encoding="utf-8")
                if launcher.launcher_id == "multimc":
                    if "MaxMemAlloc=8192" not in mem:
                        raise SystemExit(f"{name} kept a 1024 MB heap: {mem!r}")
                    _set_cfg_key(cfg_path, "MaxMemAlloc", "16384")
                    launch_installed(home, name, runner, root, fetch)
                    if "MaxMemAlloc=16384" not in cfg_path.read_text(encoding="utf-8"):
                        raise SystemExit(f"{name} replaced a larger heap")
                elif "MaxMemAlloc=1024" not in mem:
                    raise SystemExit(f"{name} changed a heap it does not own: {mem!r}")
            (games / "keep.txt").write_text("world\n", encoding="utf-8")
            state = None
            if launcher.launcher_id == "curseforge":
                state = home.joinpath(*_LAUNCHER_STATE["curseforge"])
                state.mkdir(parents=True)
                (state / "storage.json").write_text("{}\n", encoding="utf-8")
            nuke(home, name, root)
            if (games / "keep.txt").read_text(encoding="utf-8") != "world\n":
                raise SystemExit(f"nuking {name} deleted its games")
            if state is not None and state.exists():
                raise SystemExit("nuking CurseForge left the signed-out account")
            if launcher.host_link:
                link = home.joinpath(*launcher.host_link)
                if link.is_symlink():
                    link.unlink()
                elif link.is_dir():
                    link.rmdir()
                link.mkdir()
            calls.clear()
            before = len(fetches)
            install_launcher(home, name, runner, fetch, root)
            if len(fetches) != before:
                raise SystemExit(f"{name} downloaded again after it was installed")
            mounted = "\n".join(str(part) for part in calls[-1][0])
            if "unshare" in calls[-1][0] or "mount --bind" in mounted or "umu-run" in mounted:
                raise SystemExit(f"{name} was put in a user namespace: {calls[-1][0]}")
            if launcher.host_link:
                link = home.joinpath(*launcher.host_link)
                if not link.is_symlink() or link.resolve() != games.resolve():
                    raise SystemExit(f"{name} left its games folder as a real directory")

        check_native("Minecraft Bedrock", "minecraft-bedrock", "BOL_HOME")
        check_native("Modded Minecraft", "minecraft-modded", "--dir")
        check_native("MultiMC", "multimc", "--dir")
        check_native("CurseForge", "curseforge", "--no-sandbox")
        check_native("FTB App", "ftb", "--no-sandbox")

        def java_tar(members):
            import io

            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                for member, payload in members:
                    if payload is None:
                        tar.addfile(member)
                    else:
                        member.size = len(payload)
                        tar.addfile(member, io.BytesIO(payload))
            return buf.getvalue()

        java_root = Path(tmp) / "java-unpack"
        java_root.mkdir()
        script = tarfile.TarInfo("jdk/bin/java")
        script.mode = 0o755
        notice = tarfile.TarInfo("jdk/legal/java.base/LICENSE")
        link = tarfile.TarInfo("jdk/legal/java.naming/LICENSE")
        link.type = tarfile.SYMTYPE
        link.linkname = "../java.base/LICENSE"
        good_archive = Path(tmp) / "good-java.tar.gz"
        good_archive.write_bytes(java_tar([
            (script, b"#!/bin/sh\nexit 0\n"),
            (notice, b"keep"),
            (link, None),
        ]))
        unpacked = _extract_java(good_archive, java_root / "21")
        if not _usable_java(unpacked) or not (java_root / "21/legal/java.naming/LICENSE").is_symlink():
            raise SystemExit("Java did not unpack")
        escape = tarfile.TarInfo("jdk/bin/java")
        escape.mode = 0o755
        outside = tarfile.TarInfo("jdk/legal/java.naming/LICENSE")
        outside.type = tarfile.SYMTYPE
        outside.linkname = "../../../../../../tmp/wasd-java-escape"
        bad_archive = Path(tmp) / "bad-java.tar.gz"
        bad_archive.write_bytes(java_tar([
            (escape, b"#!/bin/sh\nexit 0\n"),
            (outside, None),
        ]))
        try:
            _extract_java(bad_archive, java_root / "bad")
        except LauncherError:
            pass
        else:
            raise SystemExit("Java followed a link out of the archive")
        opened_urls = []
        runtime = Path(tmp) / "runtime"
        runtime.mkdir()
        previous_runtime = os.environ.get("XDG_RUNTIME_DIR")
        os.environ["XDG_RUNTIME_DIR"] = str(runtime)
        bridge = _BrowserBridge({"WASD_SPOOF_UID": "1"}, opener=opened_urls.append)
        try:
            if not bridge.path or not Path(bridge.path).is_socket():
                raise SystemExit("the browser bridge did not listen")
            shim = _browser_shim(home)

            def send(args):
                return subprocess.run(
                    [str(shim), *args],
                    env={"WASD_OPEN_SOCKET": str(bridge.path), "PATH": os.environ.get("PATH", "")},
                    check=False,
                ).returncode

            def wait_for(count):
                import time

                deadline = time.time() + 2
                while len(opened_urls) < count and time.time() < deadline:
                    time.sleep(0.05)

            if send(["https://www.microsoft.com/link"]) != 0:
                raise SystemExit("a sign-in link was refused")
            wait_for(1)
            if send(["cfauth://wasd"]) != 0:
                raise SystemExit("CurseForge login was refused")
            wait_for(2)
            if send(["file:///etc/passwd"]) == 0:
                raise SystemExit("the browser opener accepted a file")
            if send(["https://example.com/a b"]) == 0:
                raise SystemExit("the browser opener accepted a bad link")
            raw = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            raw.settimeout(2)
            raw.connect(str(bridge.path))
            raw.sendall(b"file:///tmp/secret\n")
            raw.close()
            wait_for(3)
        finally:
            bridge.close()
            if previous_runtime is None:
                os.environ.pop("XDG_RUNTIME_DIR", None)
            else:
                os.environ["XDG_RUNTIME_DIR"] = previous_runtime
        if opened_urls != ["https://www.microsoft.com/link", "cfauth://wasd"]:
            raise SystemExit(f"the browser bridge opened {opened_urls}")
        star_prefix = layout(home, "Star Citizen", root)
        star = CATALOG["Star Citizen"]
        star_slot = star_prefix.joinpath(*star.games_link)
        star_games = root / "starcitizen"
        live = star_games / "LIVE"
        if star_slot.is_symlink() or not star_slot.is_dir() or any(star_slot.iterdir()):
            raise SystemExit("Star Citizen games are behind a link")
        if live.is_symlink() or not live.is_dir():
            raise SystemExit("Star Citizen did not create the LIVE folder")
        (live / "keep.txt").write_text("game\n", encoding="utf-8")
        star_slot.rmdir()
        star_slot.symlink_to(star_games)
        (star_prefix / "system.reg").write_text("WINE REGISTRY Version 2\n", encoding="utf-8")
        calls.clear()
        before_fetches = len(fetches)
        install_launcher(home, "Star Citizen", runner, fetch, root)
        if fetches[before_fetches:] != [star.setup_url]:
            raise SystemExit(f"Star Citizen did not use the published setup: {fetches[before_fetches:]}")
        if star_slot.is_symlink() or not star_slot.is_dir() or any(star_slot.iterdir()):
            raise SystemExit("Star Citizen left the games folder as a link")
        if (live / "keep.txt").read_text(encoding="utf-8") != "game\n":
            raise SystemExit("Star Citizen setup disturbed the LIVE folder")
        mounted = "\n".join(str(part) for part in calls[-1][0])
        if "mount --bind" not in mounted or str(star_games) not in mounted or str(star_slot) not in mounted:
            raise SystemExit(f"Star Citizen was not mounted on its games folder: {calls[-1][0]}")
        if "wineboot" in calls[-1][0] or not calls[-1][0][-1].endswith("RSI-Launcher-Setup.exe"):
            raise SystemExit(f"Star Citizen did not open its setup: {calls[-1][0]}")
        nuke(home, "Star Citizen", root)
        if (live / "keep.txt").read_text(encoding="utf-8") != "game\n":
            raise SystemExit("nuking Star Citizen deleted the LIVE folder")
        if star_slot.is_symlink() or any(star_slot.iterdir()):
            raise SystemExit("Star Citizen remake put the games link back")
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
            ("Minecraft", str(chosen)),
            ("MultiMC", str(chosen)),
            ("CurseForge", str(chosen)),
            ("FTB App", str(chosen)),
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

        opened_folders = []

        def record_open(path):
            opened_folders.append(str(path))
            return 0

        global RUNNER, FETCH, OPENER
        RUNNER = runner
        FETCH = fetch
        OPENER = record_open
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
            minecraft_row = body["rows"][list(CATALOG).index("Java Minecraft")]
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
                or custom_only["reinstall"]
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
            linked_games = root / "ftb"
            if linked_games.is_symlink():
                linked_games.unlink()
            elif linked_games.exists():
                shutil.rmtree(linked_games)
            linked_games.symlink_to(root / "minecraft")
            refused_folder = urllib.request.Request(
                f"http://127.0.0.1:{port}/browse", data=b"FTB App", method="POST"
            )
            try:
                urllib.request.urlopen(refused_folder, timeout=2)
            except urllib.error.HTTPError as exc:
                if exc.code != 500:
                    raise SystemExit(f"a linked games folder returned {exc.code}") from exc
            else:
                raise SystemExit("a linked games folder was opened")
            linked_games.unlink()
            opened_folders.clear()
            for label, folder in (("Java Minecraft", "minecraft"), ("FTB App", "ftb")):
                opened_folders.clear()
                browsed = urllib.request.Request(
                    f"http://127.0.0.1:{port}/browse", data=label.encode(), method="POST"
                )
                with urllib.request.urlopen(browsed, timeout=2) as response:
                    if response.read().decode() != "ok" or opened_folders != [str(root / folder)]:
                        raise SystemExit(f"Browse did not open {label}: {opened_folders}")
                if (root / folder).is_symlink() or not (root / folder).is_dir():
                    raise SystemExit(f"Browse left {label} as a link")
        finally:
            server.shutdown()
            RUNNER = real_runner
            FETCH = real_fetch
            OPENER = real_open

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
    rockstar_warn = "Click OK on the final error in the Rockstar installation. It still works."
    if rockstar_warn not in main or "dismissRockstarWarn" not in main:
        raise SystemExit("Rockstar has no installer warning")
    if rockstar_warn not in launch or "rockstarInstallWarn" not in launch:
        raise SystemExit("WASD Launchers has no Rockstar warning")
    star_warn = "Click No on the two errors that ask if you want to see more information. The launcher still works."
    if star_warn not in main or "dismissStarCitizenWarn" not in main:
        raise SystemExit("Star Citizen has no installer warning")
    if star_warn not in launch or "starCitizenInstallWarn" not in launch:
        raise SystemExit("WASD Launchers has no Star Citizen warning")
    for name in CATALOG:
        if name not in launch:
            raise SystemExit(f"{name} is missing from WASD Launchers")
        if name not in main:
            raise SystemExit(f"{name} is missing from WASD Install")
    if "EA App" in launch or "EA App" in main:
        raise SystemExit("EA App is still in the installer")
    if "preview" not in launch or "/remake" not in launch or "/launch" not in launch:
        raise SystemExit("WASD Launchers cannot preview, launch, or remake")
    if "Nuke/Fix" not in launch or "Reinstall" not in launch or "Saved games stay." not in launch:
        raise SystemExit("WASD Launchers is missing Nuke/Fix, Reinstall, or the saved-games note")
    keeps = launch.index("function keepsReinstall")
    shows = launch.index("function showInstall")
    kept_ids = launch[keeps:shows]
    for name, launcher in CATALOG.items():
        listed = f'"{launcher.launcher_id}"' in kept_ids
        if listed != offers_reinstall(launcher):
            raise SystemExit(f"{name} still shows Reinstall after it is installed")
    if "showInstall(name, reinstall)" not in launch:
        raise SystemExit("WASD Launchers always shows Reinstall")
    if "Browse" not in launch or '"/browse"' not in launch:
        raise SystemExit("WASD Launchers cannot open a games folder")
    if "customNameField" not in launch or "addCustomGame" not in launch or '"/custom"' not in launch:
        raise SystemExit("WASD Launchers cannot add a downloaded game")
    if "Name a game" not in launch:
        raise SystemExit("WASD Launchers has no name box")
    if "launcherScroll" not in launch:
        raise SystemExit("WASD Launchers has no scrollbar")
    if CATALOG["Java Minecraft"].setup_url != "https://launcher.mojang.com/download/Minecraft.exe":
        raise SystemExit("Minecraft is not the official launcher")
    if CATALOG["Java Minecraft"].user_link != ("AppData", "Roaming", ".minecraft"):
        raise SystemExit("Minecraft games would stay in the launcher")
    if CATALOG["Java Minecraft"].native:
        raise SystemExit("Java Minecraft would skip the official launcher")
    bedrock = CATALOG["Minecraft Bedrock"]
    modded = CATALOG["Modded Minecraft"]
    if _java_for_minecraft("1.7.10") != "8" or _java_for_minecraft("1.16.5") != "8":
        raise SystemExit("an old pack would stay on Java 21")
    if _java_for_minecraft("1.17") != "17" or _java_for_minecraft("1.20.4") != "17":
        raise SystemExit("a 1.17 pack would get the wrong Java")
    if _java_for_minecraft("1.20.5") != "21" or _java_for_minecraft("1.21.1") != "21":
        raise SystemExit("a current pack would get the wrong Java")
    if _java_for_minecraft("26.1") or _java_for_minecraft("nope"):
        raise SystemExit("an unknown pack would be given a Java")
    if (
        not bedrock.native
        or bedrock.native_env != (("BOL_HOME", "{games}"),)
        or bedrock.games_link
        or bedrock.mount_games
        or bedrock.host_link
        or bedrock.user_link
        or "BedrockOnLinux-2.3.0-x86_64.AppImage" not in bedrock.setup_url
    ):
        raise SystemExit("Bedrock would enter a user namespace")
    if (
        not modded.native
        or modded.native_args != ("--dir", "{games}")
        or modded.games_link
        or modded.mount_games
        or "PolyMC-Linux-amd64-8.1.AppImage" not in modded.setup_url
    ):
        raise SystemExit("Modded Minecraft would enter a user namespace")
    multimc = CATALOG["MultiMC"]
    curse = CATALOG["CurseForge"]
    ftb = CATALOG["FTB App"]
    if (
        not multimc.native
        or multimc.native_args != ("--dir", "{games}")
        or multimc.games_link
        or multimc.mount_games
        or multimc.host_link
        or multimc.archive_root != "MultiMC"
        or multimc.native_program != ("bin", "MultiMC")
        or not multimc.bundle_libs
        or "mmc-develop-lin64.tar.gz" not in multimc.setup_url
    ):
        raise SystemExit("MultiMC would enter a user namespace")
    if (
        not curse.native
        or curse.native_args != ("--no-sandbox",)
        or curse.host_link != ("Documents", "curseforge")
        or curse.mount_games
        or curse.games_link
        or "CurseForge-1.325.0-41594.AppImage" not in curse.setup_url
    ):
        raise SystemExit("CurseForge would enter a user namespace")
    if (
        not ftb.native
        or ftb.native_args != ("--no-sandbox",)
        or ftb.host_link != (".ftba",)
        or ftb.mount_games
        or "ftb-app-linux-1.30.1-x86_64.AppImage" not in ftb.setup_url
    ):
        raise SystemExit("the FTB App would enter a user namespace")
    for folder in ("minecraft-bedrock", "minecraft-modded", "multimc", "curseforge", "ftb"):
        if folder not in GAMES_DIRS:
            raise SystemExit("a new install would not make the Minecraft folders")
        if folder in _READY_DIRS:
            raise SystemExit("an older games drive would be refused")
    if "minecraft" in _READY_DIRS:
        raise SystemExit("an older games drive would be refused")
    star = CATALOG["Star Citizen"]
    if star.games_link != ("drive_c", "Program Files", "Roberts Space Industries", "StarCitizen"):
        raise SystemExit("Star Citizen would install onto the launcher drive")
    if not star.mount_games or star.channel_dirs != ("LIVE",):
        raise SystemExit("Star Citizen would not create the LIVE folder")
    if star.program[-1] != "RSI Launcher.exe":
        raise SystemExit("Star Citizen would not open the RSI Launcher")
    sample = "version: 2.19.1\npath: RSI Launcher-Setup-2.19.1.exe\n"
    if rsi_setup_url(sample) != "https://install.robertsspaceindustries.com/rel/2/RSI%20Launcher-Setup-2.19.1.exe":
        raise SystemExit("Star Citizen did not use the published setup")
    for bad in ("path: setup.exe\n", "version: 1\n", ""):
        try:
            rsi_setup_url(bad)
        except LauncherError:
            pass
        else:
            raise SystemExit("Star Citizen accepted a setup that was not theirs")
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
    if "qt5-qtbase" not in build or "qt5-qtbase-gui" not in build or "qt5-qtsvg" not in build:
        raise SystemExit("MultiMC would start without Qt 5")
    if "/etc/ld.so.preload" not in build:
        raise SystemExit("Java would lose its home directory")

    def superblock(major=4, minor=0, block_size=131072, block_log=17, compression=1, inodes=10, used=400):
        return struct.pack(
            "<IIIIIHHHHHHQQ",
            0x73717368,
            inodes,
            0,
            block_size,
            0,
            compression,
            block_log,
            0,
            1,
            major,
            minor,
            1,
            used,
        )

    with tempfile.TemporaryDirectory(prefix="wasd-curse-") as curse_tmp:
        curse_root = Path(curse_tmp)
        false_hit = bytearray(superblock(major=3, minor=1, block_size=99, block_log=0, used=10))
        false_hit[:4] = b"hsqs"
        good = superblock()
        image = curse_root / "fake.AppImage"
        image.write_bytes(b"hsqs-early" + bytes(false_hit) + b"pad" + good + bytes(400))
        found = _squashfs_offset(image)
        if found != image.read_bytes().rfind(b"hsqs"):
            raise SystemExit("CurseForge would unpack the wrong part of the AppImage")
        plain = curse_root / "plain"
        plain.write_bytes(b"MZ")
        if _squashfs_offset(plain) is not None or _extract_curseforge(plain) is not None:
            raise SystemExit("CurseForge extracted a file that is not an AppImage")
        kept = curse_root / "kept.AppImage"
        kept.write_bytes(b"x" * 96)
        tree = curse_root / "extracted"
        tree.mkdir()
        (tree / "AppRun").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (tree / "AppRun").chmod(0o755)
        (tree / "curseforge").write_bytes(b"elf-curseforge")
        (tree / "curseforge").chmod(0o755)
        agent = _curse_agent(tree)
        agent.parent.mkdir(parents=True)
        agent.write_bytes(b"agent-host" + (b"\x00" * 1024))
        wrapper = tree / _CURSE_WRAPPER
        wrapper.write_text("#!/bin/bash\nexit 7\n", encoding="utf-8")
        wrapper.chmod(0o755)
        (tree / ".wasd-extract").write_text(_curse_stamp(kept), encoding="utf-8")
        before = agent.stat().st_mtime_ns
        got = _extract_curseforge(kept)
        if got != wrapper or wrapper.read_text(encoding="utf-8") != "#!/bin/bash\nexit 7\n":
            raise SystemExit("CurseForge unpacked again over its own agent")
        if agent.stat().st_mtime_ns != before or (curse_root / "extracted.partial").exists():
            raise SystemExit("CurseForge unpacked again over its own agent")
        stage = curse_root / "stage"
        stage.mkdir()
        (stage / "AppRun").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (stage / "curseforge").write_bytes(b"elf-curseforge")
        _mark_extracted(stage, "stamp\n")
        script = (stage / _CURSE_WRAPPER).read_text(encoding="utf-8")
        if script != _curse_wrapper_script() or "unset APPIMAGE_EXTRACT_AND_RUN" not in script:
            raise SystemExit("CurseForge would unpack into the shared temporary directory")
        if 'exec "$here/AppRun"' not in script or not os.access(stage / _CURSE_WRAPPER, os.X_OK):
            raise SystemExit("CurseForge would unpack into the shared temporary directory")
        env = {}
        prepared = _curseforge_program(env, CATALOG["CurseForge"], kept)
        if prepared != wrapper or env.get("APPDIR") != str(tree) or env.get("APPIMAGE") != str(wrapper):
            raise SystemExit("CurseForge would start the AppImage again")
        if "APPIMAGE_EXTRACT_AND_RUN" in env:
            raise SystemExit("CurseForge would unpack into the shared temporary directory")
        command = _cfauth_exec(wrapper)
        if "APPDIR=" not in command or str(wrapper) not in command or "--no-sandbox" not in command:
            raise SystemExit("CurseForge login would unpack the AppImage again")
        if str(kept) in command:
            raise SystemExit("CurseForge login would unpack the AppImage again")
        (tree / ".wasd-extract").write_text("wasd-curse-1 stale\n", encoding="utf-8")
        if _extract_curseforge(kept) is not None:
            raise SystemExit("CurseForge trusted a stale extract")
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
