#!/usr/bin/env python3
"""Install the Flatpaks chosen during setup, on the installed system.

Completing the install runs this through pkexec. The live USB refuses it.
A passphrase never belongs in this file's arguments or in the choice file.
The self-check does not call Flatpak or NetworkManager.
"""

import errno
import json
import os
import pty
import re
import select
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/usr/libexec")

from disks import is_live  # noqa: E402
from network import (  # noqa: E402
    Refuse,
    apply_ethernet,
    connect_saved,
    parse_devices,
    parse_wifi_list,
    validate_tcp,
    validate_wifi,
)

BAKED = frozenset({"com.brave.Browser"})
OBS_ID = "com.obsproject.Studio"
OBS_PLUGINS = (
    "com.obsproject.Studio.Plugin.OBSVkCapture",
    "com.obsproject.Studio.Plugin.Gstreamer",
    "com.obsproject.Studio.Plugin.GStreamerVaapi",
)
FLATPAK_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*(\.[A-Za-z][A-Za-z0-9_-]*)+$")
MARKER = Path("/etc/wasd/apps-set")
ANSI = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
LOG_LINES = 200
NAMES = {
    "com.brave.Browser": "Brave",
    "com.discordapp.Discord": "Discord",
    "im.riot.Riot": "Element",
    "com.heroicgameslauncher.hgl": "Heroic",
    "com.usebottles.bottles": "Bottles",
    "com.obsproject.Studio": "OBS Studio",
    "io.github.benjamimgois.goverlay": "GOverlay",
    "com.github.wwmm.easyeffects": "Easy Effects",
    "org.freedesktop.Piper": "Piper",
    "org.openrgb.OpenRGB": "OpenRGB",
    "io.github.ilya_zlobintsev.LACT": "LACT",
    "org.kde.gwenview": "Gwenview",
    "org.kde.okular": "Okular",
    "org.kde.kcalc": "Calculator",
    "org.kde.haruna": "Haruna",
    "io.github.DenysMb.Kontainer": "Kontainer",
    "com.github.tchx84.Flatseal": "Flatseal",
    "com.github.Matoking.protontricks": "Protontricks",
    "io.github.flattool.Warehouse": "Warehouse",
    "com.vysp3r.ProtonPlus": "ProtonPlus",
    "org.gnome.Firmware": "Firmware",
    "org.videolan.VLC": "VLC",
    "org.gimp.GIMP": "GIMP",
    "com.bitwarden.desktop": "Bitwarden",
    "com.obsproject.Studio.Plugin.OBSVkCapture": "OBS VkCapture",
    "com.obsproject.Studio.Plugin.Gstreamer": "OBS GStreamer",
    "com.obsproject.Studio.Plugin.GStreamerVaapi": "OBS VA-API",
}


class InstallError(Exception):
    pass


def valid_id(app_id):
    return isinstance(app_id, str) and len(app_id) <= 200 and FLATPAK_ID.fullmatch(app_id) is not None


def app_label(app_id, apps=None):
    if app_id in NAMES:
        return NAMES[app_id]
    if apps:
        for item in apps:
            if item.get("id") == app_id and item.get("name"):
                return item["name"]
    if valid_id(app_id):
        return app_id
    return "That app"


def read_app_entries(data):
    if "apps" not in data:
        return []
    apps = data["apps"]
    if not isinstance(apps, list):
        return None
    cleaned = []
    for item in apps:
        if not isinstance(item, dict) or set(item.keys()) != {"name", "id"}:
            return None
        name = item["name"]
        app_id = item["id"]
        if not isinstance(name, str) or not isinstance(app_id, str):
            return None
        if any(char in name or char in app_id for char in ("\n", "\r", "\x00")):
            return None
        if len(name) > 80 or len(app_id) > 200:
            return None
        cleaned.append({"name": name, "id": app_id})
    return cleaned


def download_plan(apps):
    """Return the ids to download, and how many entries were refused.

    Brave stays in the image, so a checked Brave is not downloaded and is
    not uninstalled. OBS Studio brings its three plugins with it.
    """
    if not isinstance(apps, list):
        return None
    queue = []
    seen = set()
    refused = 0
    for item in apps:
        if not isinstance(item, dict):
            refused += 1
            continue
        app_id = item.get("id")
        if not valid_id(app_id):
            refused += 1
            continue
        if app_id in BAKED or app_id in seen:
            continue
        seen.add(app_id)
        queue.append(app_id)
        if app_id == OBS_ID:
            for plugin in OBS_PLUGINS:
                if plugin not in seen:
                    seen.add(plugin)
                    queue.append(plugin)
    return queue, refused


def needs_download(apps):
    plan = download_plan(apps)
    if plan is None:
        return False
    queue, refused = plan
    return bool(queue or refused)


def connectivity_online(text):
    return (text or "").strip().lower() in {"full", "limited"}


def list_snapshot(wifi_text, device_text):
    return {
        "networks": parse_wifi_list(wifi_text),
        "devices": parse_devices(device_text),
    }


def parse_pick(data):
    if not isinstance(data, dict):
        raise ValueError("That network cannot be used.")
    if "passphrase" in data:
        raise ValueError("That passphrase cannot be used.")
    allowed = {"ssid", "security", "hidden", "tcp"}
    if any(key not in allowed for key in data):
        raise ValueError("That network cannot be used.")
    ssid = data.get("ssid") or ""
    security = data.get("security") or ""
    hidden = data.get("hidden", False)
    if not isinstance(ssid, str) or not isinstance(security, str) or not isinstance(hidden, bool):
        raise ValueError("That network cannot be used.")
    if "\n" in security or "\r" in security or "\x00" in security or len(security) > 80:
        raise ValueError("That network cannot be used.")
    tcp = data.get("tcp", None)
    if tcp is not None:
        if not isinstance(tcp, dict) or "passphrase" in json.dumps(tcp):
            raise ValueError("That network cannot be used.")
        problem = validate_tcp(tcp)
        if problem:
            raise ValueError(problem)
    if ssid:
        problem = validate_wifi(ssid, "")
        if problem:
            raise ValueError(problem)
    elif tcp is None or tcp.get("kind") != "ethernet":
        raise ValueError("Choose a Wi-Fi network or set an address.")
    wifi_tcp = tcp if tcp and tcp.get("kind") == "wifi" else None
    ether_tcp = tcp if tcp and tcp.get("kind") == "ethernet" else None
    if ssid and tcp and tcp.get("kind") == "wifi" and wifi_tcp is None:
        raise ValueError("Choose an adapter.")
    return {
        "ssid": ssid.strip(),
        "security": security,
        "hidden": hidden,
        "tcp": wifi_tcp or ether_tcp,
    }


def session_problem():
    uid = os.environ.get("PKEXEC_UID", "")
    if not uid.isdigit():
        return "This is only used by Completing the install."
    if is_live():
        return "This computer was not changed."
    return ""


def install_ids(ids, runner):
    """One Flatpak transaction. A separate install per app repeats the download setup."""
    if not isinstance(ids, list) or not ids or len(ids) > 40:
        raise InstallError("That app was refused.")
    for app_id in ids:
        if not valid_id(app_id) or app_id in BAKED:
            raise InstallError("That app was refused.")
    result = runner(["install", "-y", "--noninteractive", "--system", "flathub", *ids])
    if getattr(result, "returncode", 1) != 0:
        raise InstallError(app_label(ids[0]))


def install_one(app_id, runner):
    install_ids([app_id], runner)


def connect_picked(pick, passphrase, runner, key_dir):
    ssid = pick.get("ssid") or ""
    tcp = pick.get("tcp")
    if ssid:
        wifi_tcp = tcp if tcp and tcp.get("kind") == "wifi" else None
        connect_saved(
            ssid,
            passphrase,
            pick.get("security") or "",
            bool(pick.get("hidden")),
            runner,
            key_dir,
            wifi_tcp,
        )
    passphrase = ""
    if tcp and tcp.get("kind") == "ethernet":
        return apply_ethernet(tcp, runner, key_dir)
    return ""


def app_log_path():
    return Path(os.environ.get("WASD_APP_LOG", "/tmp/wasd-app-install.log"))


def read_app_log():
    """Last lines of the install output. A symlink is refused."""
    path = app_log_path()
    if path.is_symlink() or not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return "\n".join(text.splitlines()[-80:])


class TerminalLog:
    """Keep the text a terminal would show. A redraw replaces the open line."""

    def __init__(self, path):
        self.path = Path(path)
        self.lines = []
        self.current = ""
        self._read()

    def _read(self):
        path = self.path
        if path.is_symlink() or not path.is_file():
            return
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        self.lines = text.splitlines()[-LOG_LINES:]

    def feed(self, data):
        text = ANSI.sub("", str(data).replace("\x00", "")).replace("\r\n", "\n")
        pieces = text.split("\n")
        for index, piece in enumerate(pieces):
            if "\r" in piece:
                self.current = piece.split("\r")[-1]
            else:
                self.current += piece
            if index < len(pieces) - 1:
                self.lines.append(self.current)
                self.current = ""
        if len(self.lines) > LOG_LINES:
            self.lines = self.lines[-LOG_LINES:]
        self._flush()

    def _flush(self):
        shown = list(self.lines)
        if self.current:
            shown.append(self.current)
        body = "\n".join(shown[-LOG_LINES:])
        if body:
            body += "\n"
        path = self.path
        parent = path.parent
        if path.is_symlink() or parent.is_symlink() or not parent.is_dir():
            return
        temporary = parent / (path.name + ".part")
        if temporary.is_symlink():
            return
        temporary.write_text(body, encoding="utf-8")
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)


def _read_ready(fd, log):
    try:
        chunk = os.read(fd, 4096)
    except OSError as exc:
        if exc.errno == errno.EIO:
            return False
        raise
    if not chunk:
        return False
    log.feed(chunk.decode("utf-8", "replace"))
    return True


def _flatpak(args):
    if os.environ.get("WASD_SELF_CHECK") == "1":
        raise SystemExit("self-check tried to run flatpak")
    if not shutil.which("flatpak"):
        raise InstallError("Flatpak is not available.")
    log = TerminalLog(app_log_path())
    names = [item for item in args if FLATPAK_ID.fullmatch(item or "")]
    if names:
        log.feed("\n" + "\n".join(names) + "\n")
    # A pipe hides the download bar and holds the text until the app finishes.
    try:
        master, slave = pty.openpty()
    except OSError:
        master, slave = None, None
    if slave is not None:
        try:
            import fcntl
            import struct
            import termios

            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 120, 0, 0))
        except (OSError, ImportError):
            pass
    try:
        proc = subprocess.Popen(
            ["flatpak", *args],
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
        raise InstallError("Flatpak is not available.") from exc
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
                    if not _read_ready(master, log):
                        break
                    continue
                if proc.poll() is None:
                    continue
                while True:
                    try:
                        leftover, _, _ = select.select([master], [], [], 0)
                    except (OSError, ValueError):
                        leftover = []
                    if not leftover or not _read_ready(master, log):
                        break
                break
        else:
            assert proc.stdout is not None
            while True:
                chunk = proc.stdout.read(4096)
                if not chunk:
                    break
                log.feed(chunk.decode("utf-8", "replace"))
        code = proc.wait()
    finally:
        if master is not None:
            os.close(master)
    if code == 0:
        log.feed("installed\n")
    return subprocess.CompletedProcess(["flatpak", *args], code)


def _nmcli(args):
    if "--rescan" in args:
        index = args.index("--rescan")
        value = args[index + 1] if index + 1 < len(args) else ""
        if value != "no":
            raise SystemExit("refusing a network rescan")
    if os.environ.get("WASD_SELF_CHECK") == "1":
        raise SystemExit("self-check tried to run nmcli")
    if not shutil.which("nmcli"):
        raise Refuse("NetworkManager is not available.")
    return subprocess.run(["nmcli", *args], capture_output=True, text=True)


def _require():
    problem = session_problem()
    if problem:
        print(problem, file=sys.stderr)
        return False
    return True


def online_main():
    if not _require():
        return 1
    try:
        result = _nmcli(["-t", "-f", "CONNECTIVITY", "general"])
    except Refuse:
        print("offline")
        return 0
    text = result.stdout if result.returncode == 0 else ""
    print("online" if connectivity_online(text) else "offline")
    return 0


def list_main():
    if not _require():
        return 1
    try:
        wifi = _nmcli(["-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "no"])
        devices = _nmcli(["-t", "-f", "DEVICE,TYPE", "device", "status"])
    except Refuse as exc:
        print(exc, file=sys.stderr)
        return 1
    wifi_text = wifi.stdout if wifi.returncode == 0 else ""
    device_text = devices.stdout if devices.returncode == 0 else ""
    print(json.dumps(list_snapshot(wifi_text, device_text)))
    return 0


def install_main():
    if not _require():
        return 1
    blob = sys.stdin.buffer.read(8193)
    if len(blob) > 8192:
        print("That app was refused.", file=sys.stderr)
        return 1
    try:
        text = blob.decode("utf-8")
    except UnicodeError:
        print("That app was refused.", file=sys.stderr)
        return 1
    blob = b""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or len(lines) > 40:
        print("That app was refused.", file=sys.stderr)
        return 1
    try:
        install_ids(lines, _flatpak)
    except InstallError as exc:
        print(exc, file=sys.stderr)
        return 1
    print("ok")
    return 0


def _write_marker(text):
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(text)
    os.chmod(MARKER, 0o644)


def skip_main():
    if not _require():
        return 1
    _write_marker("skipped\n")
    return 0


def mark_main():
    if not _require():
        return 1
    _write_marker("installed\n")
    return 0


def _read_pick_file():
    uid = os.environ.get("PKEXEC_UID", "")
    path = Path(f"/run/user/{uid}/wasd-apps-pick.json")
    if path.is_symlink() or not path.is_file():
        raise ValueError("That network cannot be used.")
    stat = path.stat()
    if stat.st_uid != int(uid) or (stat.st_mode & 0o777) != 0o600:
        raise ValueError("That network cannot be used.")
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        raise ValueError("That network cannot be used.") from None
    pick = parse_pick(data)
    try:
        path.unlink()
    except OSError:
        pass
    return pick


def _read_passphrase():
    blob = sys.stdin.buffer.read(64)
    if len(blob) > 63:
        print("That passphrase cannot be used.", file=sys.stderr)
        return None
    try:
        passphrase = blob.decode("utf-8")
    except UnicodeError:
        print("That passphrase cannot be used.", file=sys.stderr)
        return None
    return passphrase


def connect_main():
    if not _require():
        return 1
    try:
        pick = _read_pick_file()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    if not pick.get("ssid"):
        print("Choose a Wi-Fi network.", file=sys.stderr)
        return 1
    passphrase = _read_passphrase()
    if passphrase is None:
        return 1
    key_dir = Path("/run/wasd-apps")
    try:
        note = connect_picked(pick, passphrase, _nmcli, key_dir)
    except Refuse as exc:
        passphrase = ""
        print(exc, file=sys.stderr)
        return 1
    passphrase = ""
    if note:
        print(note)
    return 0


def address_main():
    if not _require():
        return 1
    try:
        pick = _read_pick_file()
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    tcp = pick.get("tcp")
    if not tcp or tcp.get("kind") != "ethernet":
        print("No address was saved.", file=sys.stderr)
        return 1
    key_dir = Path("/run/wasd-apps")
    try:
        note = apply_ethernet(tcp, _nmcli, key_dir)
    except Refuse as exc:
        print(exc, file=sys.stderr)
        return 1
    if note:
        print(note)
    return 0


def self_check():
    os.environ["WASD_SELF_CHECK"] = "1"
    os.environ.pop("PKEXEC_UID", None)
    if session_problem() != "This is only used by Completing the install.":
        raise SystemExit("a helper without pkexec was allowed")
    if not valid_id("com.discordapp.Discord"):
        raise SystemExit("a flatpak id was refused")
    for bad in ("../evil", "com.brave.Browser/stable", "-hidden", "not an id", "", "app/com.discordapp.Discord"):
        if valid_id(bad):
            raise SystemExit(f"a bad id was accepted: {bad}")
    apps = [
        {"name": "Brave", "id": "com.brave.Browser"},
        {"name": "Discord", "id": "com.discordapp.Discord"},
        {"name": "Nope", "id": "../evil"},
        {"name": "OBS Studio", "id": "com.obsproject.Studio"},
        {"name": "Discord", "id": "com.discordapp.Discord"},
    ]
    plan = download_plan(apps)
    if plan is None:
        raise SystemExit("a usable app list was refused")
    queue, refused = plan
    if refused != 1:
        raise SystemExit(f"refused count was {refused}")
    if "com.brave.Browser" in queue:
        raise SystemExit("Brave was queued for download")
    if queue.count("com.discordapp.Discord") != 1:
        raise SystemExit(f"Discord was queued wrong: {queue}")
    obs_at = queue.index(OBS_ID)
    if list(queue[obs_at + 1:obs_at + 4]) != list(OBS_PLUGINS):
        raise SystemExit(f"OBS plugins were not queued: {queue}")
    if download_plan([{"name": "Brave", "id": "com.brave.Browser"}]) != ([], 0):
        raise SystemExit("Brave alone still wants a download")
    if download_plan("nope") is not None:
        raise SystemExit("a broken app list was planned")
    if not connectivity_online("full") or not connectivity_online("limited\n"):
        raise SystemExit("an online link was treated as offline")
    for offline in ("none", "portal", "unknown", "", "fullish"):
        if connectivity_online(offline):
            raise SystemExit(f"{offline} was treated as online")
    snapshot = list_snapshot("*:Home:80:WPA2\n", "wlp3s0:wifi:disconnected:\n")
    if snapshot["networks"][0]["ssid"] != "Home" or snapshot["devices"][0]["device"] != "wlp3s0":
        raise SystemExit(f"network list parsed wrong: {snapshot}")
    try:
        parse_pick({"ssid": "Home", "passphrase": "not-stored-secret"})
    except ValueError as exc:
        if str(exc) != "That passphrase cannot be used.":
            raise SystemExit(f"a passphrase in the pick was {exc}") from exc
    else:
        raise SystemExit("a passphrase in the pick was accepted")
    try:
        parse_pick({"ssid": ""})
    except ValueError as exc:
        if str(exc) != "Choose a Wi-Fi network or set an address.":
            raise SystemExit(f"an empty network was {exc}") from exc
    else:
        raise SystemExit("an empty network was accepted")
    manual = {
        "mode": "manual",
        "interface": "wlp3s0",
        "kind": "wifi",
        "address": "192.168.1.20",
        "netmask": "255.255.255.0",
        "gateway": "192.168.1.1",
        "dns": "1.1.1.1",
    }
    picked = parse_pick({"ssid": "Home", "security": "WPA2", "hidden": False, "tcp": manual})
    if picked.get("passphrase") or picked["tcp"]["kind"] != "wifi":
        raise SystemExit(f"the pick was stored wrong: {picked}")
    seen = []

    class Result:
        def __init__(self, code=0, stdout="", stderr=""):
            self.returncode = code
            self.stdout = stdout
            self.stderr = stderr

    def runner(args):
        seen.append(list(args))
        if args[:2] == ["connection", "load"]:
            text = Path(args[2]).read_text()
            if "psk=" not in text or "192.168.1.20/24" not in text:
                raise SystemExit("the wifi key file missed the address or the passphrase")
            if "not-stored-secret" not in text:
                raise SystemExit("the key file missed the passphrase")
        return Result()

    secret = "not-stored-secret"
    key_dir = Path("/tmp/wasd-apps-self")
    if key_dir.exists():
        shutil.rmtree(key_dir)
    connect_picked(picked, secret, runner, key_dir)
    secret = ""
    if any("not-stored-secret" in " ".join(args) for args in seen):
        raise SystemExit("the passphrase was placed on a command")
    if any(arg == "--rescan" for args in seen for arg in args):
        raise SystemExit("connecting rescanned")
    for path in key_dir.rglob("*"):
        if path.is_file() and b"not-stored-secret" in path.read_bytes():
            raise SystemExit(f"the passphrase was left in {path}")
    shutil.rmtree(key_dir, ignore_errors=True)
    installed = []

    def install_runner(args):
        installed.append(list(args))
        return Result()

    install_one("com.discordapp.Discord", install_runner)
    if installed != [["install", "-y", "--noninteractive", "--system", "flathub", "com.discordapp.Discord"]]:
        raise SystemExit(f"flatpak was invoked wrong: {installed}")
    install_ids(["com.discordapp.Discord", "org.freedesktop.Piper"], install_runner)
    if installed[-1] != [
        "install", "-y", "--noninteractive", "--system", "flathub",
        "com.discordapp.Discord", "org.freedesktop.Piper",
    ]:
        raise SystemExit(f"a shared download was {installed[-1]}")
    try:
        install_ids(["com.discordapp.Discord"] * 41, install_runner)
    except InstallError:
        pass
    else:
        raise SystemExit("a huge download was accepted")
    try:
        install_one("com.brave.Browser", install_runner)
    except InstallError as exc:
        if str(exc) != "That app was refused.":
            raise SystemExit(f"Brave install was {exc}") from exc
    else:
        raise SystemExit("Brave was installed again")
    try:
        install_one("../evil", install_runner)
    except InstallError:
        pass
    else:
        raise SystemExit("a bad id was installed")
    if len(installed) != 2:
        raise SystemExit("a refused app reached flatpak")
    import inspect
    if "pty.openpty" not in inspect.getsource(_flatpak):
        raise SystemExit("flatpak output would stay buffered")
    try:
        _nmcli(["device", "wifi", "list", "--rescan", "yes"])
    except SystemExit as exc:
        if str(exc) != "refusing a network rescan":
            raise SystemExit(f"rescan refusal was {exc}") from exc
    else:
        raise SystemExit("a rescan was allowed")
    try:
        _nmcli(["-t", "-f", "CONNECTIVITY", "general"])
    except SystemExit as exc:
        if str(exc) != "self-check tried to run nmcli":
            raise SystemExit(f"nmcli guard was {exc}") from exc
    else:
        raise SystemExit("self-check reached NetworkManager")
    try:
        _flatpak(["install", "flathub", "com.discordapp.Discord"])
    except SystemExit as exc:
        if str(exc) != "self-check tried to run flatpak":
            raise SystemExit(f"flatpak guard was {exc}") from exc
    else:
        raise SystemExit("self-check reached Flatpak")
    log_path = Path("/tmp/wasd-apps-log-self")
    if log_path.is_symlink() or log_path.exists():
        log_path.unlink()
    os.environ["WASD_APP_LOG"] = str(log_path)
    log = TerminalLog(log_path)
    log.feed("Fetching 1/3\r\x1b[32mFetching 2/3\x1b[0m\rFetching 3/3\nInstalled\n")
    text = log_path.read_text(encoding="utf-8")
    if "Fetching 1/3" in text or "Fetching 2/3" in text or "\x1b" in text:
        raise SystemExit(f"the log kept a redraw: {text!r}")
    if text.splitlines() != ["Fetching 3/3", "Installed"]:
        raise SystemExit(f"the log was {text!r}")
    if (log_path.stat().st_mode & 0o777) != 0o644:
        raise SystemExit(f"the log mode was {oct(log_path.stat().st_mode & 0o777)}")
    again = TerminalLog(log_path)
    again.feed("Next app\n")
    if log_path.read_text(encoding="utf-8").splitlines() != ["Fetching 3/3", "Installed", "Next app"]:
        raise SystemExit("a later install replaced the log")
    shown = read_app_log()
    if shown.splitlines() != ["Fetching 3/3", "Installed", "Next app"]:
        raise SystemExit(f"the visible log was {shown!r}")
    link = Path("/tmp/wasd-apps-log-link")
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(log_path)
    os.environ["WASD_APP_LOG"] = str(link)
    if read_app_log():
        raise SystemExit("a linked log was shown")
    os.environ.pop("WASD_APP_LOG", None)
    log_path.unlink()
    link.unlink()
    print("apps self-check ok")


def main():
    if "--self-check" in sys.argv:
        self_check()
        return 0
    if "--online" in sys.argv:
        return online_main()
    if "--list" in sys.argv:
        return list_main()
    if "--install" in sys.argv:
        return install_main()
    if "--skip" in sys.argv:
        return skip_main()
    if "--mark" in sys.argv:
        return mark_main()
    if "--connect" in sys.argv:
        return connect_main()
    if "--address" in sys.argv:
        return address_main()
    print("Nothing was changed.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
