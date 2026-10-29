#!/usr/bin/env python3
"""Open Completing the install on the first desktop session.

The password, and a saved Wi-Fi passphrase, are posted to a local page and
handed to their setters on standard input. Neither is placed on a command
line. Checked Flatpaks are downloaded on this same window. This does nothing
on the live USB, and nothing when the install choices are not there.
"""

import datetime
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/usr/libexec")

from agents import (  # noqa: E402
    AgentError,
    install_agent,
    names_from,
    needs_fetch,
    prepare,
    real_runner,
)
from apps import (  # noqa: E402
    InstallError,
    app_label,
    download_plan,
    needs_download,
    parse_pick,
    read_app_entries,
    read_app_log,
)
from disks import is_live  # noqa: E402
from lookapply import LookError, look_from, look_sentence  # noqa: E402
from network import passphrase_problem, read_saved_tcp, read_saved_wifi  # noqa: E402
from set_password import validate_password  # noqa: E402

CHOICES = Path(os.environ.get("WASD_CHOICES", "/etc/wasd/choices.json"))
MARKER = Path(os.environ.get("WASD_PASSWORD_MARK", "/etc/wasd/password-set"))
WIFI_MARKER = Path(os.environ.get("WASD_WIFI_MARK", "/etc/wasd/wifi-set"))
APPS_MARKER = Path(os.environ.get("WASD_APPS_MARK", "/etc/wasd/apps-set"))
LOOK_MARKER = Path(os.environ.get("WASD_LOOK_MARK", "/etc/wasd/look-set"))
AGENTS_MARKER = Path(os.environ.get("WASD_AGENTS_MARK", "/etc/wasd/agents-set"))
USER_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
QML = Path(os.environ.get("WASD_COMPLETE_QML", "/usr/share/wasd/install/Complete.qml"))
WIFI_MESSAGES = {
    "Type the passphrase.",
    "That passphrase cannot be used.",
    "A passphrase is 8 to 63 characters, or empty for an open network.",
    "The passphrase was not accepted.",
    "That network was not found.",
    "Could not connect.",
    "No network was saved.",
    "This computer was not changed.",
    "NetworkManager is not available.",
    "This is only used by Completing the install.",
}
TCP_MESSAGES = {
    "Those settings were not used.",
    "Saved for this adapter. It is not connected yet.",
    "No address was saved.",
    "Choose an adapter.",
    "Use an IP address like 192.168.1.20.",
    "Use a netmask like 255.255.255.0.",
    "Use a gateway like 192.168.1.1.",
    "Use a DNS address like 1.1.1.1.",
    "This computer was not changed.",
    "NetworkManager is not available.",
    "This is only used by Completing the install.",
}


def autostart_path():
    override = os.environ.get("WASD_AUTOSTART")
    if override:
        return Path(override)
    return Path.home() / ".config/autostart/wasd-complete.desktop"


def desktop_icon_path():
    override = os.environ.get("WASD_DESKTOP_ICON")
    if override:
        return Path(override)
    return Path.home() / "Desktop" / "wasd-complete.desktop"


def trash_root():
    override = os.environ.get("WASD_TRASH")
    if override:
        return Path(override)
    data = os.environ.get("XDG_DATA_HOME")
    root = Path(data) if data else Path.home() / ".local" / "share"
    return root / "Trash"


def move_to_trash(path):
    path = Path(path)
    if path.name != "wasd-complete.desktop":
        return False
    if not path.exists() and not path.is_symlink():
        return True
    root = trash_root()
    files = root / "files"
    info = root / "info"
    try:
        files.mkdir(parents=True, exist_ok=True)
        info.mkdir(parents=True, exist_ok=True)
        os.chmod(root, 0o700)
    except OSError:
        return False
    name = path.name
    number = 2
    while (files / name).exists() or (info / f"{name}.trashinfo").exists():
        name = f"wasd-complete-{number}.desktop"
        number += 1
        if number > 100:
            return False
    info_path = info / f"{name}.trashinfo"
    absolute = str(path if path.is_absolute() else path.resolve())
    when = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    try:
        info_path.write_text(
            "[Trash Info]\n"
            f"Path={urllib.parse.quote(absolute, safe='/')}\n"
            f"DeletionDate={when}\n"
        )
        os.chmod(info_path, 0o600)
        shutil.move(str(path), files / name)
    except OSError:
        try:
            info_path.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    return True


class WifiError(Exception):
    pass


class TcpError(Exception):
    pass


class AppError(InstallError):
    pass


def read_choices():
    try:
        data = json.loads(CHOICES.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    user = data.get("user") or ""
    if not isinstance(user, str) or not USER_NAME.fullmatch(user) or user == "root":
        return None
    flag = data.get("password")
    if flag is True:
        password = True
    elif flag is False:
        password = False
    else:
        return None
    wifi = None
    if "wifi" in data:
        wifi = read_saved_wifi(CHOICES)
        if wifi is None:
            return None
    tcp = None
    if "tcp" in data:
        tcp = read_saved_tcp(CHOICES)
        if tcp is None:
            return None
    apps = read_app_entries(data)
    if apps is None:
        return None
    try:
        look = look_from(data)
        agents = names_from(data)
    except (LookError, AgentError):
        return None
    return {
        "password": password,
        "user": user,
        "wifi": wifi,
        "tcp": tcp,
        "apps": apps,
        "look": look,
        "agents": agents,
    }


def pkexec_setter(blob):
    proc = subprocess.run(
        ["pkexec", "/usr/libexec/wasd-set-password"],
        input=blob,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError("not set")


def pkexec_wifi(blob):
    proc = subprocess.run(
        ["pkexec", "/usr/libexec/wasd-connect-wifi"],
        input=blob,
        capture_output=True,
    )
    if proc.returncode != 0:
        text = (proc.stderr or b"").decode("utf-8", "replace").strip()
        line = text.splitlines()[-1] if text else ""
        raise WifiError(line if line in WIFI_MESSAGES else "Could not connect.")


def pkexec_wifi_skip():
    proc = subprocess.run(
        ["pkexec", "/usr/libexec/wasd-connect-wifi", "--skip"],
        capture_output=True,
    )
    if proc.returncode != 0:
        text = (proc.stderr or b"").decode("utf-8", "replace").strip()
        line = text.splitlines()[-1] if text else ""
        raise WifiError(line if line in WIFI_MESSAGES else "Could not continue.")


def pkexec_ethernet():
    proc = subprocess.run(
        ["pkexec", "/usr/libexec/wasd-connect-wifi", "--ethernet"],
        capture_output=True,
    )
    err = (proc.stderr or b"").decode("utf-8", "replace").strip()
    out = (proc.stdout or b"").decode("utf-8", "replace").strip()
    if proc.returncode != 0:
        line = err.splitlines()[-1] if err else ""
        raise TcpError(line if line in TCP_MESSAGES else "Those settings were not used.")
    note = out.splitlines()[-1] if out else ""
    if note and note not in TCP_MESSAGES:
        note = ""
    return note


def _pkexec_apps(args, blob=b""):
    if os.environ.get("WASD_SELF_CHECK") == "1":
        raise SystemExit("self-check tried to run the app helper")
    proc = subprocess.run(
        ["pkexec", "/usr/libexec/wasd-install-apps", *args],
        input=blob if blob else None,
        capture_output=True,
    )
    return proc


def _apps_error(proc, fallback):
    text = (proc.stderr or b"").decode("utf-8", "replace").strip()
    line = text.splitlines()[-1] if text else ""
    return line if line in APP_MESSAGES else fallback


def pkexec_install(app_ids):
    """One Flatpak transaction. A string is one app. A list is the rest of the queue."""
    if isinstance(app_ids, str):
        ids = [app_ids]
    elif isinstance(app_ids, list):
        ids = app_ids
    else:
        raise AppError("That app was refused.")
    if not ids or len(ids) > 40 or any(not isinstance(item, str) for item in ids):
        raise AppError("That app was refused.")
    blob = "".join(item + "\n" for item in ids).encode()
    if len(blob) > 8192:
        raise AppError("That app was refused.")
    proc = _pkexec_apps(["--install"], blob)
    if proc.returncode != 0:
        raise AppError(_apps_error(proc, app_label(ids[0])))


def pkexec_apps_skip():
    proc = _pkexec_apps(["--skip"])
    if proc.returncode != 0:
        raise AppError(_apps_error(proc, "Could not continue."))


def pkexec_apps_mark():
    proc = _pkexec_apps(["--mark"])
    if proc.returncode != 0:
        raise AppError(_apps_error(proc, "Could not continue."))


def pkexec_online():
    proc = _pkexec_apps(["--online"])
    if proc.returncode != 0:
        return "offline"
    text = (proc.stdout or b"").decode("utf-8", "replace").strip()
    return text if text in {"online", "offline"} else "offline"


def pkexec_list():
    proc = _pkexec_apps(["--list"])
    if proc.returncode != 0:
        raise AppError("The network list is not available.")
    try:
        data = json.loads((proc.stdout or b"").decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise AppError("The network list is not available.") from None
    if not isinstance(data, dict):
        raise AppError("The network list is not available.")
    return data


def _write_pick(pick):
    uid = os.getuid()
    directory = Path(f"/run/user/{uid}")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "wasd-apps-pick.json"
    path.write_text(json.dumps(pick))
    os.chmod(path, 0o600)
    return path


def pkexec_connect(blob, pick):
    path = _write_pick(pick)
    try:
        proc = _pkexec_apps(["--connect"], blob)
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    if proc.returncode != 0:
        raise WifiError(_apps_error(proc, "Could not connect."))


def agent_home():
    override = os.environ.get("WASD_AGENT_HOME")
    if override:
        return Path(override)
    return Path.home()


def pkexec_look():
    if os.environ.get("WASD_SELF_CHECK") == "1":
        raise SystemExit("self-check tried to apply the look")
    choices = read_choices()
    if choices is None:
        raise LookError("The desktop was not set.")
    proc = subprocess.run(
        [
            "pkexec",
            "/usr/libexec/wasd-apply-choices",
            "--choices",
            str(CHOICES),
            "--user",
            choices["user"],
            "--session",
            "--rebuild",
        ],
        capture_output=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", "replace")
        raise LookError(look_sentence(err))


def pkexec_agents_mark():
    if os.environ.get("WASD_SELF_CHECK") == "1":
        raise SystemExit("self-check tried to mark the agents")
    proc = subprocess.run(
        ["pkexec", "/usr/libexec/wasd-install-agents", "--mark"],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise AgentError("Could not continue.")


def pkexec_address(pick):
    path = _write_pick(pick)
    try:
        proc = _pkexec_apps(["--address"])
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    if proc.returncode != 0:
        raise TcpError(_apps_error(proc, "Those settings were not used."))
    out = (proc.stdout or b"").decode("utf-8", "replace").strip()
    note = out.splitlines()[-1] if out else ""
    if note and note not in TCP_MESSAGES:
        note = ""
    return note


SETTER = pkexec_setter
WIFI_SETTER = pkexec_wifi
WIFI_SKIP = pkexec_wifi_skip
TCP_SETTER = pkexec_ethernet
INSTALLER = pkexec_install
APPS_SKIP = pkexec_apps_skip
APPS_MARK = pkexec_apps_mark
ONLINE = pkexec_online
LISTER = pkexec_list
CONNECT = pkexec_connect
ADDRESS = pkexec_address
LOOK_APPLY = pkexec_look
AGENT_RUNNER = real_runner
AGENT_MARK = pkexec_agents_mark
APPS_LOCK = threading.Lock()
APPS_QUEUE = []
APPS_AT = 0
APPS_FAILED = ""
APPS_REFUSED = 0
APPS_READY = False
APPS_ONE = False
PICK = None
AGENTS_QUEUE = []
AGENTS_AT = 0
AGENTS_FAILED = ""
AGENTS_READY = False

APP_MESSAGES = WIFI_MESSAGES | TCP_MESSAGES | {
    "That app was refused.",
    "Could not install that app.",
    "Could not continue.",
    "The network list is not available.",
    "Choose a Wi-Fi network.",
    "Choose a Wi-Fi network or set an address.",
    "That network cannot be used.",
    "That network name cannot be used.",
    "Type the network name.",
    "Nothing is waiting to download.",
    "The download has not started.",
    "Choose retry or continue.",
    "Flatpak is not available.",
}
PICK_MESSAGES = {
    "That passphrase cannot be used.",
    "That network cannot be used.",
    "Type the network name.",
    "That network name cannot be used.",
    "Choose a Wi-Fi network or set an address.",
    "Choose an adapter.",
    "Choose automatic or manual.",
    "Use an IP address like 192.168.1.20.",
    "Use a netmask like 255.255.255.0.",
    "Use a gateway like 192.168.1.1.",
    "Use a DNS address like 1.1.1.1.",
}


def _reset_apps():
    global APPS_QUEUE, APPS_AT, APPS_FAILED, APPS_REFUSED, APPS_READY, APPS_ONE, PICK
    APPS_QUEUE = []
    APPS_AT = 0
    APPS_FAILED = ""
    APPS_REFUSED = 0
    APPS_READY = False
    APPS_ONE = False
    PICK = None


def _apps_choices():
    choices = read_choices()
    if choices is None:
        return None
    return choices


def finish_allowed():
    choices = read_choices()
    if choices is None:
        return False
    if choices["password"] and not MARKER.is_file():
        return False
    if choices["wifi"] is not None and not WIFI_MARKER.is_file():
        return False
    if needs_download(choices["apps"]) and not APPS_MARKER.is_file():
        return False
    if choices["look"] is not None and not LOOK_MARKER.is_file():
        return False
    if choices["agents"] and not AGENTS_MARKER.is_file():
        return False
    return True


def _queue_done():
    APPS_MARK()
    return 200, "done"


def _install_current(choices):
    """Install every remaining app in one download.

    A failure names the first app and continues one at a time, so Retry
    and Continue still refer to one app.
    """
    global APPS_AT, APPS_FAILED, APPS_ONE
    if ONLINE() != "online":
        return 200, "offline"
    if APPS_AT >= len(APPS_QUEUE):
        return _queue_done()
    remaining = APPS_QUEUE[APPS_AT:]
    batch = len(remaining) > 1 and not APPS_ONE
    try:
        INSTALLER(remaining if batch else remaining[0])
    except AppError:
        if batch:
            APPS_ONE = True
        APPS_FAILED = remaining[0]
        return 200, "fail\n" + app_label(remaining[0], choices["apps"])
    if batch:
        APPS_AT = len(APPS_QUEUE)
    else:
        APPS_AT += 1
    if APPS_AT >= len(APPS_QUEUE):
        return _queue_done()
    return 200, "next"


def apps_check():
    global APPS_QUEUE, APPS_AT, APPS_FAILED, APPS_REFUSED, APPS_READY, APPS_ONE
    choices = _apps_choices()
    if choices is None:
        return 409, "The choice file is not usable."
    plan = download_plan(choices["apps"])
    if plan is None:
        return 409, "The choice file is not usable."
    queue, refused = plan
    if not queue and not refused:
        _reset_apps()
        return 200, "none"
    if ONLINE() != "online":
        _reset_apps()
        return 200, "offline"
    APPS_QUEUE = queue
    APPS_AT = 0
    APPS_REFUSED = refused
    APPS_FAILED = "refused" if refused else ""
    APPS_READY = True
    APPS_ONE = False
    if refused:
        return 200, "bad\nThat app was refused."
    return 200, "online"


def apps_install():
    if not APPS_READY:
        return 409, "The download has not started."
    if APPS_FAILED:
        return 409, "Choose retry or continue."
    choices = _apps_choices()
    if choices is None:
        return 409, "The choice file is not usable."
    return _install_current(choices)


def apps_retry():
    global APPS_AT, APPS_FAILED
    if not APPS_READY or not APPS_FAILED:
        return 409, "Choose retry or continue."
    if APPS_FAILED == "refused":
        return 200, "bad\nThat app was refused."
    choices = _apps_choices()
    if choices is None:
        return 409, "The choice file is not usable."
    if ONLINE() != "online":
        return 200, "offline"
    app_id = APPS_FAILED
    try:
        INSTALLER(app_id)
    except AppError:
        return 200, "fail\n" + app_label(app_id, choices["apps"])
    APPS_FAILED = ""
    APPS_AT += 1
    if APPS_AT >= len(APPS_QUEUE):
        return _queue_done()
    return 200, "next"


def apps_continue():
    global APPS_AT, APPS_FAILED, APPS_REFUSED
    if not APPS_READY or not APPS_FAILED:
        return 409, "Choose retry or continue."
    if APPS_FAILED == "refused":
        APPS_REFUSED = max(0, APPS_REFUSED - 1)
        APPS_FAILED = ""
        if APPS_REFUSED:
            APPS_FAILED = "refused"
            return 200, "bad\nThat app was refused."
        if APPS_AT >= len(APPS_QUEUE):
            return _queue_done()
        return 200, "next"
    skipped = APPS_QUEUE[APPS_AT] if APPS_AT < len(APPS_QUEUE) else ""
    APPS_FAILED = ""
    APPS_AT += 1
    if skipped == "com.obsproject.Studio":
        plugins = {
            "com.obsproject.Studio.Plugin.OBSVkCapture",
            "com.obsproject.Studio.Plugin.Gstreamer",
            "com.obsproject.Studio.Plugin.GStreamerVaapi",
        }
        while APPS_AT < len(APPS_QUEUE) and APPS_QUEUE[APPS_AT] in plugins:
            APPS_AT += 1
    if APPS_AT >= len(APPS_QUEUE):
        return _queue_done()
    return 200, "next"


def apps_skip():
    choices = _apps_choices()
    if choices is None:
        return 409, "The choice file is not usable."
    if not needs_download(choices["apps"]):
        return 409, "Nothing is waiting to download."
    try:
        APPS_SKIP()
    except AppError as exc:
        return 400, str(exc) if str(exc) in APP_MESSAGES else "Could not continue."
    _reset_apps()
    return 200, "ok"


def apps_pick(blob):
    global PICK
    try:
        data = json.loads(blob.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        PICK = None
        return 400, "That network cannot be used."
    try:
        PICK = parse_pick(data)
    except ValueError as exc:
        PICK = None
        message = str(exc)
        return 400, message if message in PICK_MESSAGES else "That network cannot be used."
    return 200, "ok"


def apps_connect(blob):
    if not isinstance(PICK, dict) or not PICK.get("ssid"):
        return 409, "Choose a Wi-Fi network."
    try:
        text = blob.decode("utf-8")
    except UnicodeError:
        return 400, "That passphrase cannot be used."
    problem = passphrase_problem(PICK.get("security") or "", text)
    text = ""
    if problem:
        return 400, problem
    try:
        CONNECT(blob, PICK)
    except WifiError as exc:
        return 400, str(exc) if str(exc) in APP_MESSAGES else "Could not connect."
    return 200, "ok"


def apps_address():
    if not isinstance(PICK, dict) or not PICK.get("tcp") or PICK["tcp"].get("kind") != "ethernet":
        return 409, "No address was saved."
    try:
        note = ADDRESS(PICK)
    except TcpError as exc:
        return 400, str(exc) if str(exc) in APP_MESSAGES else "Those settings were not used."
    return 200, note or "ok"


def apps_list():
    try:
        data = LISTER()
    except AppError as exc:
        return 400, str(exc) if str(exc) in APP_MESSAGES else "The network list is not available."
    networks = data.get("networks") if isinstance(data.get("networks"), list) else []
    devices = data.get("devices") if isinstance(data.get("devices"), list) else []
    return 200, json.dumps({"networks": networks, "devices": devices})


def _reset_agents():
    global AGENTS_QUEUE, AGENTS_AT, AGENTS_FAILED, AGENTS_READY
    AGENTS_QUEUE = []
    AGENTS_AT = 0
    AGENTS_FAILED = ""
    AGENTS_READY = False


def look_apply():
    choices = read_choices()
    if choices is None:
        return 409, "The choice file is not usable."
    if choices["look"] is None:
        return 200, "none"
    if LOOK_MARKER.is_file():
        return 200, "ok"
    try:
        LOOK_APPLY()
    except LookError as exc:
        return 500, look_sentence(str(exc))
    except Exception:
        return 500, "The desktop was not set."
    return 200, "ok"


def _agents_done():
    AGENT_MARK()
    _reset_agents()
    return 200, "done"


def _agent_current():
    global AGENTS_AT, AGENTS_FAILED
    if AGENTS_AT >= len(AGENTS_QUEUE):
        return _agents_done()
    name = AGENTS_QUEUE[AGENTS_AT]
    if needs_fetch(name) and ONLINE() != "online":
        return 200, "offline"
    try:
        install_agent(agent_home(), name, AGENT_RUNNER)
    except AgentError:
        AGENTS_FAILED = name
        return 200, "fail\n" + name
    AGENTS_AT += 1
    if AGENTS_AT >= len(AGENTS_QUEUE):
        return _agents_done()
    return 200, "next"


def agents_check():
    global AGENTS_QUEUE, AGENTS_AT, AGENTS_FAILED, AGENTS_READY
    choices = read_choices()
    if choices is None:
        return 409, "The choice file is not usable."
    names = choices["agents"] or []
    if not names:
        return 200, "none"
    prepare(agent_home(), names)
    AGENTS_QUEUE = list(names)
    AGENTS_AT = 0
    AGENTS_FAILED = ""
    AGENTS_READY = True
    if any(needs_fetch(name) for name in names) and ONLINE() != "online":
        return 200, "offline"
    return 200, "online"


def agents_install():
    if not AGENTS_READY:
        return 409, "The download has not started."
    if AGENTS_FAILED:
        return 409, "Choose retry or continue."
    return _agent_current()


def agents_retry():
    global AGENTS_AT, AGENTS_FAILED
    if not AGENTS_READY or not AGENTS_FAILED:
        return 409, "Choose retry or continue."
    name = AGENTS_FAILED
    if needs_fetch(name) and ONLINE() != "online":
        return 200, "offline"
    try:
        install_agent(agent_home(), name, AGENT_RUNNER)
    except AgentError:
        return 200, "fail\n" + name
    AGENTS_FAILED = ""
    AGENTS_AT += 1
    if AGENTS_AT >= len(AGENTS_QUEUE):
        return _agents_done()
    return 200, "next"


def agents_continue():
    global AGENTS_AT, AGENTS_FAILED
    if not AGENTS_READY or not AGENTS_FAILED:
        return 409, "Choose retry or continue."
    AGENTS_FAILED = ""
    AGENTS_AT += 1
    if AGENTS_AT >= len(AGENTS_QUEUE):
        return _agents_done()
    return 200, "next"


def agents_skip():
    choices = read_choices()
    if choices is None or not choices["agents"]:
        return 409, "Nothing is waiting to download."
    try:
        AGENT_MARK()
    except AgentError:
        return 400, "Could not continue."
    _reset_agents()
    return 200, "ok"


AWAKE_PID = Path("/tmp/wasd-awake.pid")
AWAKE_STOP = Path("/tmp/wasd-awake.stop")
AWAKE_PROC = None


def hold_awake():
    """Keep the screen on while the checked apps download. A failure changes nothing."""
    global AWAKE_PROC
    if os.environ.get("WASD_SELF_CHECK") == "1":
        return
    if AWAKE_PROC is not None and AWAKE_PROC.poll() is None:
        return
    binary = Path(os.environ.get("WASD_AWAKE", "/usr/libexec/wasd-awake"))
    if binary.is_symlink() or not binary.is_file():
        return
    try:
        AWAKE_STOP.unlink(missing_ok=True)
    except OSError:
        return
    try:
        AWAKE_PROC = subprocess.Popen(
            [str(binary)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        AWAKE_PROC = None


def release_awake():
    """Drop the screen hold. The timeout setting stays as it was."""
    global AWAKE_PROC
    if os.environ.get("WASD_SELF_CHECK") == "1":
        return
    try:
        AWAKE_STOP.write_text("stop\n")
    except OSError:
        pass
    try:
        pid_text = AWAKE_PID.read_text(encoding="utf-8")
    except OSError:
        pid_text = ""
    pid = pid_text.strip()
    if pid.isdigit():
        try:
            os.kill(int(pid), signal.SIGTERM)
        except OSError:
            pass
    if AWAKE_PROC is not None and AWAKE_PROC.poll() is None:
        try:
            AWAKE_PROC.terminate()
        except OSError:
            pass
    AWAKE_PROC = None


def remove_autostart():
    if not finish_allowed():
        return False
    if not move_to_trash(desktop_icon_path()):
        return False
    path = autostart_path()
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return False
    return True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _reply(self, code, text):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # The install holds the apps lock until Flatpak returns. This read stays
        # outside that lock so the window can follow the output while it runs.
        if self.client_address[0] != "127.0.0.1":
            self._reply(403, "This request was refused.")
            return
        if self.path.split("?", 1)[0] != "/output":
            self._reply(404, "This request was refused.")
            return
        self._reply(200, read_app_log())

    def do_POST(self):
        if self.client_address[0] != "127.0.0.1":
            self._reply(403, "This request was refused.")
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length < 0 or length > 2048:
            self._reply(400, "That request was not usable.")
            return
        blob = self.rfile.read(length) if length else b""
        try:
            if self.path == "/awake":
                hold_awake()
                self._reply(200, "ok")
                return
            if self.path == "/awake/release":
                release_awake()
                self._reply(200, "ok")
                return
            if self.path == "/password":
                problem = validate_password(blob)
                if problem:
                    self._reply(400, problem)
                    return
                try:
                    SETTER(blob)
                except Exception:
                    self._reply(500, "The password was not set.")
                    return
                self._reply(200, "ok")
                return
            if self.path == "/wifi":
                saved = read_saved_wifi(CHOICES)
                if saved is None:
                    self._reply(409, "No network was saved.")
                    return
                try:
                    text = blob.decode("utf-8")
                except UnicodeError:
                    self._reply(400, "That passphrase cannot be used.")
                    return
                problem = passphrase_problem(saved[1], text)
                text = ""
                if problem:
                    self._reply(400, problem)
                    return
                try:
                    WIFI_SETTER(blob)
                except WifiError as exc:
                    self._reply(400, str(exc))
                    return
                except Exception:
                    self._reply(500, "Could not connect.")
                    return
                self._reply(200, "ok")
                return
            if self.path == "/wifi/skip":
                saved = read_saved_wifi(CHOICES)
                if saved is None:
                    self._reply(409, "No network was saved.")
                    return
                try:
                    WIFI_SKIP()
                except WifiError as exc:
                    self._reply(400, str(exc))
                    return
                except Exception:
                    self._reply(500, "Could not continue.")
                    return
                self._reply(200, "ok")
                return
            if self.path == "/tcp":
                saved_tcp = read_saved_tcp(CHOICES)
                if saved_tcp is None or saved_tcp.get("kind") != "ethernet":
                    self._reply(409, "No address was saved.")
                    return
                try:
                    note = TCP_SETTER()
                except TcpError as exc:
                    self._reply(400, str(exc))
                    return
                except Exception:
                    self._reply(500, "Those settings were not used.")
                    return
                self._reply(200, note or "ok")
                return
            if self.path == "/look/apply":
                with APPS_LOCK:
                    code, text = look_apply()
                self._reply(code, text)
                return
            if self.path.startswith("/agents"):
                with APPS_LOCK:
                    if self.path == "/agents/check":
                        code, text = agents_check()
                    elif self.path == "/agents/install":
                        code, text = agents_install()
                    elif self.path == "/agents/retry":
                        code, text = agents_retry()
                    elif self.path == "/agents/continue":
                        code, text = agents_continue()
                    elif self.path == "/agents/skip":
                        code, text = agents_skip()
                    else:
                        code, text = 404, "This request was refused."
                self._reply(code, text)
                return
            if self.path.startswith("/apps"):
                with APPS_LOCK:
                    if self.path == "/apps/check":
                        code, text = apps_check()
                    elif self.path == "/apps/install":
                        code, text = apps_install()
                    elif self.path == "/apps/retry":
                        code, text = apps_retry()
                    elif self.path == "/apps/continue":
                        code, text = apps_continue()
                    elif self.path == "/apps/skip":
                        code, text = apps_skip()
                    elif self.path == "/apps/pick":
                        code, text = apps_pick(blob)
                    elif self.path == "/apps/connect":
                        code, text = apps_connect(blob)
                    elif self.path == "/apps/address":
                        code, text = apps_address()
                    elif self.path == "/apps/list":
                        code, text = apps_list()
                    else:
                        code, text = 404, "This request was refused."
                self._reply(code, text)
                return
            if self.path == "/done":
                if remove_autostart():
                    self._reply(200, "ok")
                else:
                    self._reply(409, "The window will open again next time.")
                return
            self._reply(404, "This request was refused.")
        finally:
            blob = b""


def serve():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def self_check():
    global SETTER, WIFI_SETTER, WIFI_SKIP, TCP_SETTER, CHOICES, MARKER, WIFI_MARKER, APPS_MARKER
    global INSTALLER, APPS_SKIP, APPS_MARK, ONLINE, LISTER, CONNECT, ADDRESS
    global LOOK_MARKER, AGENTS_MARKER, LOOK_APPLY, AGENT_RUNNER, AGENT_MARK
    os.environ["WASD_SELF_CHECK"] = "1"
    tmp = Path("/tmp/wasd-complete-self")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(mode=0o700)
    choices = tmp / "choices.json"
    marker = tmp / "password-set"
    wifi_marker = tmp / "wifi-set"
    apps_marker = tmp / "apps-set"
    look_marker = tmp / "look-set"
    agents_marker = tmp / "agents-set"
    auto = tmp / "wasd-complete.desktop"
    icon = tmp / "Desktop" / "wasd-complete.desktop"
    icon.parent.mkdir(mode=0o700)
    choices.write_text(json.dumps({"password": True, "user": "alex"}))
    os.environ["WASD_CHOICES"] = str(choices)
    os.environ["WASD_PASSWORD_MARK"] = str(marker)
    os.environ["WASD_WIFI_MARK"] = str(wifi_marker)
    os.environ["WASD_APPS_MARK"] = str(apps_marker)
    os.environ["WASD_LOOK_MARK"] = str(look_marker)
    os.environ["WASD_AGENTS_MARK"] = str(agents_marker)
    os.environ["WASD_AGENT_HOME"] = str(tmp / "agent-home")
    os.environ["WASD_AUTOSTART"] = str(auto)
    os.environ["WASD_DESKTOP_ICON"] = str(icon)
    os.environ["WASD_TRASH"] = str(tmp / "Trash")
    CHOICES = choices
    MARKER = marker
    WIFI_MARKER = wifi_marker
    APPS_MARKER = apps_marker
    LOOK_MARKER = look_marker
    AGENTS_MARKER = agents_marker
    auto.write_text("[Desktop Entry]\n")
    icon.write_text("[Desktop Entry]\nName=Completing the install\n")
    seen = {}

    def fake_setter(blob):
        seen["length"] = len(blob)
        if b"not-stored-secret" != blob:
            raise RuntimeError("unexpected")

    def fake_wifi(blob):
        seen["wifi"] = len(blob)
        if blob != b"not-stored-secret":
            raise WifiError("The passphrase was not accepted.")

    def fake_skip():
        seen["skip"] = True
        wifi_marker.write_text("skipped\n")

    def fake_ethernet():
        seen["ethernet"] = seen.get("ethernet", 0) + 1
        return "Saved for this adapter. It is not connected yet."

    installed = []
    calls = []
    fail_once = {"com.discordapp.Discord"}
    online_calls = {"n": 0}

    def fake_install(app_id):
        calls.append(app_id if isinstance(app_id, str) else list(app_id))
        ids = [app_id] if isinstance(app_id, str) else list(app_id)
        for item in ids:
            if item == "com.brave.Browser" or not isinstance(item, str) or not item or "/" in item or " " in item:
                raise AppError("That app was refused.")
            if item in fail_once:
                fail_once.remove(item)
                raise AppError("Discord")
        installed.extend(ids)

    def fake_apps_skip():
        seen["apps_skip"] = True
        apps_marker.write_text("skipped\n")

    def fake_apps_mark():
        apps_marker.write_text("installed\n")

    def fake_online():
        online_calls["n"] += 1
        if online_calls.get("force") == "offline":
            return "offline"
        if online_calls["n"] == 1:
            return "offline"
        return "online"

    def fake_list():
        seen["list"] = True
        return {
            "networks": [{"ssid": "Home", "signal": 80, "security": "WPA2", "inUse": False}],
            "devices": [{"device": "wlp3s0", "kind": "wifi", "label": "Wi-Fi"}],
        }

    def fake_connect(blob, pick):
        seen["connect"] = len(blob)
        seen["pick"] = dict(pick)
        if blob != b"not-stored-secret":
            raise WifiError("The passphrase was not accepted.")
        if "passphrase" in pick:
            raise WifiError("That passphrase cannot be used.")

    def fake_address(pick):
        seen["address"] = pick.get("tcp", {}).get("interface")
        return "Saved for this adapter. It is not connected yet."

    SETTER = fake_setter
    WIFI_SETTER = fake_wifi
    WIFI_SKIP = fake_skip
    TCP_SETTER = fake_ethernet
    INSTALLER = fake_install
    APPS_SKIP = fake_apps_skip
    APPS_MARK = fake_apps_mark
    ONLINE = fake_online
    LISTER = fake_list
    CONNECT = fake_connect
    ADDRESS = fake_address

    def fake_look():
        seen["look"] = seen.get("look", 0) + 1
        look_marker.write_text("ok\n")

    def fake_agent_mark():
        agents_marker.write_text("ok\n")

    agent_calls = []

    def fake_agent_runner(argv):
        agent_calls.append(list(argv))
        if argv[0] == "curl":
            Path(argv[argv.index("--output") + 1]).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            if agent_calls and not seen.get("agent_failed"):
                seen["agent_failed"] = True
                return 1, b"", b"no"
            return 0, b"", b""
        if argv[0] == "bash":
            return 0, b"", b""
        return 1, b"", b"no"

    LOOK_APPLY = fake_look
    AGENT_RUNNER = fake_agent_runner
    AGENT_MARK = fake_agent_mark
    if finish_allowed():
        raise SystemExit("finish ran before the password was set")
    server = serve()
    port = server.server_address[1]
    import urllib.error
    import urllib.request

    missing_tcp = urllib.request.Request(f"http://127.0.0.1:{port}/tcp", data=b"192.168.9.9", method="POST")
    try:
        urllib.request.urlopen(missing_tcp, timeout=2)
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise SystemExit(f"tcp without a saved address returned {exc.code}") from exc
    else:
        raise SystemExit("an address was applied without being saved")
    if seen.get("ethernet"):
        raise SystemExit("a missing address reached the setter")
    early_done = urllib.request.Request(f"http://127.0.0.1:{port}/done", data=b"", method="POST")
    try:
        urllib.request.urlopen(early_done, timeout=2)
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise SystemExit(f"done before the password returned {exc.code}") from exc
    else:
        raise SystemExit("done ran before the password was set")
    if not icon.is_file() or not auto.is_file():
        raise SystemExit("the desktop icon was removed before setup finished")
    if (tmp / "Trash").exists():
        raise SystemExit("the icon was trashed before setup finished")
    early = urllib.request.Request(f"http://127.0.0.1:{port}/wifi", data=b"not-stored-secret", method="POST")
    try:
        urllib.request.urlopen(early, timeout=2)
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise SystemExit(f"wifi without a saved network returned {exc.code}") from exc
    else:
        raise SystemExit("wifi connected without a saved network")
    secret = b"not-stored-secret"
    request = urllib.request.Request(f"http://127.0.0.1:{port}/password", data=secret, method="POST")
    with urllib.request.urlopen(request, timeout=2) as response:
        if response.status != 200:
            raise SystemExit("password post failed")
    if seen.get("length") != len(secret):
        raise SystemExit("the setter was not called")
    marker.write_text("alex\n")
    if not finish_allowed():
        raise SystemExit("finish stayed blocked after the password was set")
    choices.write_text(json.dumps({
        "password": True,
        "user": "alex",
        "wifi": {"ssid": "Home", "security": "WPA2", "hidden": False},
    }))
    if finish_allowed():
        raise SystemExit("finish ran before the wifi passphrase was set")
    short = urllib.request.Request(f"http://127.0.0.1:{port}/wifi", data=b"short", method="POST")
    try:
        urllib.request.urlopen(short, timeout=2)
    except urllib.error.HTTPError as exc:
        if exc.code != 400:
            raise SystemExit(f"a short passphrase returned {exc.code}") from exc
    else:
        raise SystemExit("a short passphrase was accepted")
    if "wifi" in seen:
        raise SystemExit("a short passphrase reached the setter")
    joined = urllib.request.Request(f"http://127.0.0.1:{port}/wifi", data=secret, method="POST")
    with urllib.request.urlopen(joined, timeout=2) as response:
        if response.status != 200:
            raise SystemExit("wifi post failed")
    if seen.get("wifi") != len(secret):
        raise SystemExit("the wifi setter was not called")
    if finish_allowed():
        raise SystemExit("finish ran before the wifi marker was written")
    wifi_marker.write_text("Home\n")
    if not finish_allowed():
        raise SystemExit("finish stayed blocked after the wifi passphrase was set")
    wifi_marker.unlink()
    if finish_allowed():
        raise SystemExit("finish ran after the wifi marker was removed")
    skipped = urllib.request.Request(f"http://127.0.0.1:{port}/wifi/skip", data=b"", method="POST")
    with urllib.request.urlopen(skipped, timeout=2) as response:
        if response.status != 200:
            raise SystemExit("wifi skip failed")
    if not seen.get("skip"):
        raise SystemExit("wifi skip did not record the choice")
    if wifi_marker.read_text() != "skipped\n":
        raise SystemExit("the skip marker was wrong")
    if not finish_allowed():
        raise SystemExit("finish stayed blocked after wifi was skipped")
    done = urllib.request.Request(f"http://127.0.0.1:{port}/done", data=b"", method="POST")
    with urllib.request.urlopen(done, timeout=2) as response:
        if response.status != 200:
            raise SystemExit("done post failed")
    if auto.exists():
        raise SystemExit("the startup entry was not removed")
    if icon.exists():
        raise SystemExit("the desktop icon stayed after setup finished")
    trashed = tmp / "Trash" / "files" / "wasd-complete.desktop"
    info = tmp / "Trash" / "info" / "wasd-complete.desktop.trashinfo"
    if not trashed.is_file() or trashed.read_text() != "[Desktop Entry]\nName=Completing the install\n":
        raise SystemExit("the desktop icon was not moved to the trash")
    info_text = info.read_text()
    if "[Trash Info]" not in info_text or "DeletionDate=" not in info_text or str(icon) not in urllib.parse.unquote(info_text):
        raise SystemExit(f"the trash note was wrong: {info_text}")
    choices.write_text(json.dumps({
        "password": True,
        "user": "alex",
        "wifi": {"ssid": "Home", "security": "WPA2", "hidden": False},
        "tcp": {
            "mode": "manual",
            "interface": "enp4s0",
            "kind": "ethernet",
            "address": "192.168.1.20",
            "netmask": "255.255.255.0",
            "gateway": "192.168.1.1",
            "dns": "1.1.1.1",
        },
    }))
    posted = urllib.request.Request(f"http://127.0.0.1:{port}/tcp", data=b"192.168.9.9", method="POST")
    with urllib.request.urlopen(posted, timeout=2) as response:
        body = response.read().decode()
        if response.status != 200 or body != "Saved for this adapter. It is not connected yet.":
            raise SystemExit(f"ethernet apply returned {body}")
    if seen.get("ethernet") != 1:
        raise SystemExit("the ethernet setter was not called")
    if not finish_allowed():
        raise SystemExit("finish stayed blocked after the address was saved")
    wifi_only = json.loads(choices.read_text())
    wifi_only["tcp"]["kind"] = "wifi"
    wifi_only["tcp"]["interface"] = "wlp3s0"
    choices.write_text(json.dumps(wifi_only))
    try:
        urllib.request.urlopen(posted, timeout=2)
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise SystemExit(f"a wifi address used the ethernet helper: {exc.code}") from exc
    else:
        raise SystemExit("a wifi address used the ethernet helper")
    if seen.get("ethernet") != 1:
        raise SystemExit("a wifi address reached the ethernet setter")
    bad_address = json.loads(choices.read_text())
    bad_address["tcp"]["address"] = "192.168.1.999"
    bad_address["tcp"]["kind"] = "ethernet"
    bad_address["tcp"]["interface"] = "enp4s0"
    choices.write_text(json.dumps(bad_address))
    try:
        urllib.request.urlopen(posted, timeout=2)
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise SystemExit(f"a bad address returned {exc.code}") from exc
    else:
        raise SystemExit("a bad address was applied")
    auto.write_text("[Desktop Entry]\n")
    icon.write_text("[Desktop Entry]\nName=Completing the install\n")
    brave_only = {
        "password": True,
        "user": "alex",
        "wifi": {"ssid": "Home", "security": "WPA2", "hidden": False},
        "apps": [{"name": "Brave", "id": "com.brave.Browser"}],
    }
    choices.write_text(json.dumps(brave_only))
    if not finish_allowed():
        raise SystemExit("Brave alone blocked finishing")
    brave_check = urllib.request.Request(f"http://127.0.0.1:{port}/apps/check", data=b"", method="POST")
    with urllib.request.urlopen(brave_check, timeout=2) as response:
        body = response.read().decode()
        if response.status != 200 or body != "none":
            raise SystemExit(f"Brave alone wanted a download: {body}")
    if installed:
        raise SystemExit(f"Brave reached the installer: {installed}")
    if online_calls["n"] != 0:
        raise SystemExit("Brave alone asked whether the network was up")
    download_apps = {
        "password": True,
        "user": "alex",
        "wifi": {"ssid": "Home", "security": "WPA2", "hidden": False},
        "apps": [
            {"name": "Brave", "id": "com.brave.Browser"},
            {"name": "Discord", "id": "com.discordapp.Discord"},
            {"name": "Nope", "id": "../evil"},
            {"name": "OBS Studio", "id": "com.obsproject.Studio"},
        ],
    }
    choices.write_text(json.dumps(download_apps))
    if finish_allowed():
        raise SystemExit("finish ran before the apps were downloaded")
    held = urllib.request.Request(f"http://127.0.0.1:{port}/done", data=b"", method="POST")
    try:
        urllib.request.urlopen(held, timeout=2)
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise SystemExit(f"done during a download returned {exc.code}") from exc
    else:
        raise SystemExit("done ran while a download was still waiting")
    if not icon.is_file():
        raise SystemExit("the desktop icon was removed while a download was waiting")
    offline = urllib.request.Request(f"http://127.0.0.1:{port}/apps/check", data=b"", method="POST")
    with urllib.request.urlopen(offline, timeout=2) as response:
        body = response.read().decode()
        if body != "offline":
            raise SystemExit(f"an offline computer continued: {body}")
    if online_calls["n"] != 1:
        raise SystemExit("the offline check did not read connectivity once")
    early_install = urllib.request.Request(f"http://127.0.0.1:{port}/apps/install", data=b"", method="POST")
    try:
        urllib.request.urlopen(early_install, timeout=2)
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise SystemExit(f"an offline install returned {exc.code}") from exc
    else:
        raise SystemExit("an offline install started")
    if installed:
        raise SystemExit("an offline install reached Flatpak")
    skipped_apps = urllib.request.Request(f"http://127.0.0.1:{port}/apps/skip", data=b"", method="POST")
    with urllib.request.urlopen(skipped_apps, timeout=2) as response:
        if response.status != 200 or not seen.get("apps_skip"):
            raise SystemExit("the download skip was not recorded")
    if apps_marker.read_text() != "skipped\n":
        raise SystemExit("the skip marker was wrong")
    if not finish_allowed():
        raise SystemExit("finish stayed blocked after the download was skipped")
    apps_marker.unlink()
    if finish_allowed():
        raise SystemExit("finish ran after the download skip was removed")
    online = urllib.request.Request(f"http://127.0.0.1:{port}/apps/check", data=b"", method="POST")
    with urllib.request.urlopen(online, timeout=2) as response:
        body = response.read().decode()
        if body != "bad\nThat app was refused.":
            raise SystemExit(f"a bad app id was not refused: {body}")
    if installed:
        raise SystemExit("a bad app id reached the installer")
    continued = urllib.request.Request(f"http://127.0.0.1:{port}/apps/continue", data=b"", method="POST")
    with urllib.request.urlopen(continued, timeout=2) as response:
        if response.read().decode() != "next":
            raise SystemExit("continue after a refused id did not move on")
    failed = urllib.request.Request(f"http://127.0.0.1:{port}/apps/install", data=b"", method="POST")
    with urllib.request.urlopen(failed, timeout=2) as response:
        body = response.read().decode()
        if body != "fail\nDiscord":
            raise SystemExit(f"a failed app was not named: {body}")
    if installed:
        raise SystemExit("a failed install was counted as installed")
    retried = urllib.request.Request(f"http://127.0.0.1:{port}/apps/retry", data=b"", method="POST")
    with urllib.request.urlopen(retried, timeout=2) as response:
        if response.read().decode() != "next":
            raise SystemExit("retry did not move on")
    if installed != ["com.discordapp.Discord"]:
        raise SystemExit(f"retry installed the wrong app: {installed}")
    expected = [
        "com.obsproject.Studio",
        "com.obsproject.Studio.Plugin.OBSVkCapture",
        "com.obsproject.Studio.Plugin.Gstreamer",
        "com.obsproject.Studio.Plugin.GStreamerVaapi",
    ]
    while installed[-1:] != expected[-1:]:
        step = urllib.request.Request(f"http://127.0.0.1:{port}/apps/install", data=b"", method="POST")
        with urllib.request.urlopen(step, timeout=2) as response:
            body = response.read().decode()
        if body == "done":
            break
        if body != "next":
            raise SystemExit(f"the rest of the download returned {body}")
        if len(installed) > 8:
            raise SystemExit(f"the download did not finish: {installed}")
    if installed != ["com.discordapp.Discord", *expected]:
        raise SystemExit(f"the download queue was {installed}")
    batch = ["com.discordapp.Discord", *expected]
    if calls[0] != batch:
        raise SystemExit(f"the first download was not one transaction: {calls[0]!r}")
    if calls[1:] != batch:
        raise SystemExit(f"a failed download did not continue one app at a time: {calls[1:]!r}")
    clean_apps = {
        "password": True,
        "user": "alex",
        "wifi": {"ssid": "Home", "security": "WPA2", "hidden": False},
        "apps": [
            {"name": "Discord", "id": "com.discordapp.Discord"},
            {"name": "OBS Studio", "id": "com.obsproject.Studio"},
        ],
    }
    choices.write_text(json.dumps(clean_apps))
    clean_check = urllib.request.Request(f"http://127.0.0.1:{port}/apps/check", data=b"", method="POST")
    with urllib.request.urlopen(clean_check, timeout=2) as response:
        if response.read().decode() != "online":
            raise SystemExit("a clean download did not start")
    before = len(calls)
    clean_install = urllib.request.Request(f"http://127.0.0.1:{port}/apps/install", data=b"", method="POST")
    with urllib.request.urlopen(clean_install, timeout=2) as response:
        if response.read().decode() != "done":
            raise SystemExit("a clean download did not finish in one step")
    if calls[before:] != [batch]:
        raise SystemExit(f"a clean download was not one transaction: {calls[before:]!r}")
    if installed != [*batch, *batch]:
        raise SystemExit(f"the clean download installed {installed}")
    if "com.brave.Browser" in installed or any("/" in item for item in installed):
        raise SystemExit(f"a baked or refused app was installed: {installed}")
    if apps_marker.read_text() != "installed\n":
        raise SystemExit("the install marker was wrong")
    if not finish_allowed():
        raise SystemExit("finish stayed blocked after the download")
    leaked = urllib.request.Request(
        f"http://127.0.0.1:{port}/apps/pick",
        data=b'{"ssid":"Cafe","passphrase":"not-stored-secret"}',
        method="POST",
    )
    try:
        urllib.request.urlopen(leaked, timeout=2)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        if exc.code != 400 or "not-stored-secret" in detail:
            raise SystemExit(f"a stored passphrase returned {exc.code} {detail}") from exc
    else:
        raise SystemExit("a passphrase was accepted in the network choice")
    if b"not-stored-secret" in choices.read_bytes():
        raise SystemExit("the passphrase was written into the choice file")
    pick = urllib.request.Request(
        f"http://127.0.0.1:{port}/apps/pick",
        data=b'{"ssid":"Cafe","security":"WPA2","hidden":true}',
        method="POST",
    )
    with urllib.request.urlopen(pick, timeout=2) as response:
        if response.read().decode() != "ok":
            raise SystemExit("a network choice was refused")
    joined_now = urllib.request.Request(
        f"http://127.0.0.1:{port}/apps/connect",
        data=b"not-stored-secret",
        method="POST",
    )
    with urllib.request.urlopen(joined_now, timeout=2) as response:
        if response.status != 200:
            raise SystemExit("the first-boot network did not connect")
    if seen.get("connect") != len(b"not-stored-secret") or seen.get("pick", {}).get("ssid") != "Cafe":
        raise SystemExit("the first-boot network was not the one chosen")
    if "passphrase" in seen.get("pick", {}):
        raise SystemExit("the passphrase was stored with the network")
    listed = urllib.request.Request(f"http://127.0.0.1:{port}/apps/list", data=b"", method="POST")
    with urllib.request.urlopen(listed, timeout=2) as response:
        listing = response.read().decode()
    if not seen.get("list") or "Home" not in listing or "rescan" in listing:
        raise SystemExit(f"the network list was wrong: {listing}")
    done_apps = urllib.request.Request(f"http://127.0.0.1:{port}/done", data=b"", method="POST")
    with urllib.request.urlopen(done_apps, timeout=2) as response:
        if response.status != 200:
            raise SystemExit("done after the download failed")
    if icon.exists():
        raise SystemExit("the desktop icon stayed after the download finished")
    server.shutdown()
    _reset_apps()
    _reset_agents()
    choices.write_text(
        json.dumps(
            {
                "password": False,
                "user": "alex",
                "loading": "stained-glass.jpg",
                "login": "throne.jpg",
                "theme": "We10XOS-dark",
                "wallpaper": "camp.png",
                "agents": ["Grok Build", "Grok Bot", "Grok", "Codex"],
            }
        )
    )
    if look_marker.exists():
        look_marker.unlink()
    if agents_marker.exists():
        agents_marker.unlink()

    def fail_look():
        raise LookError("The wallpaper did not change.")

    def unknown_look():
        raise LookError("boom")

    LOOK_APPLY = fail_look
    code, text = look_apply()
    if code != 500 or text != "The wallpaper did not change.":
        raise SystemExit(f"the wallpaper failure was {code} {text}")
    if look_marker.exists():
        raise SystemExit("a failed look wrote the marker")
    LOOK_APPLY = unknown_look
    code, text = look_apply()
    if code != 500 or text != "The desktop was not set.":
        raise SystemExit(f"an unknown look failure was {code} {text}")
    LOOK_APPLY = fake_look
    if finish_allowed():
        raise SystemExit("finish ran before the look was applied")
    server = serve()
    port = server.server_address[1]
    early_look = urllib.request.Request(f"http://127.0.0.1:{port}/done", data=b"", method="POST")
    try:
        urllib.request.urlopen(early_look, timeout=2)
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise SystemExit(f"done before the look returned {exc.code}") from exc
    else:
        raise SystemExit("done ran before the look was applied")
    applied = urllib.request.Request(f"http://127.0.0.1:{port}/look/apply", data=b"", method="POST")
    with urllib.request.urlopen(applied, timeout=2) as response:
        if response.read().decode() != "ok":
            raise SystemExit("the look was not applied")
    if seen.get("look") != 1 or not look_marker.is_file():
        raise SystemExit("the look marker was not written")
    with urllib.request.urlopen(applied, timeout=2) as response:
        if response.read().decode() != "ok" or seen.get("look") != 1:
            raise SystemExit("the look was applied twice")
    checked = urllib.request.Request(f"http://127.0.0.1:{port}/agents/check", data=b"", method="POST")
    with urllib.request.urlopen(checked, timeout=2) as response:
        if response.read().decode() != "online":
            raise SystemExit("the agents did not start")
    home = Path(os.environ["WASD_AGENT_HOME"])
    web = (home / ".local/share/applications/wasd-agent-grok.desktop").read_text(encoding="utf-8")
    if "https://grok.com/" not in web or "/usr/libexec/wasd-webapp" not in web:
        raise SystemExit("the Grok window was not written before the download")
    first = urllib.request.Request(f"http://127.0.0.1:{port}/agents/install", data=b"", method="POST")
    with urllib.request.urlopen(first, timeout=2) as response:
        if response.read().decode() != "fail\nGrok Build":
            raise SystemExit("a failed agent was installed")
    if agents_marker.exists():
        raise SystemExit("a failed agent finished the list")
    again = urllib.request.Request(f"http://127.0.0.1:{port}/agents/retry", data=b"", method="POST")
    with urllib.request.urlopen(again, timeout=2) as response:
        if response.read().decode() != "next":
            raise SystemExit("the agent retry did not continue")
    while True:
        step = urllib.request.Request(f"http://127.0.0.1:{port}/agents/install", data=b"", method="POST")
        with urllib.request.urlopen(step, timeout=2) as response:
            text = response.read().decode()
        if text == "done":
            break
        if text != "next":
            raise SystemExit(f"an agent step returned {text}")
    curls = [item for item in agent_calls if item and item[0] == "curl"]
    if len(curls) != 2 or any(item[-1] != "https://x.ai/cli/install.sh" for item in curls):
        raise SystemExit(f"the grok installer was wrong: {curls}")
    codex = (home / ".local/bin/wasd-agent-codex").read_text(encoding="utf-8")
    if "curl" in codex or "does not download" not in codex:
        raise SystemExit("an unverified agent was given an installer")
    if not agents_marker.is_file():
        raise SystemExit("the agents marker was not written")
    agents_marker.unlink()
    online_calls["force"] = "offline"
    _reset_agents()
    offline = urllib.request.Request(f"http://127.0.0.1:{port}/agents/check", data=b"", method="POST")
    with urllib.request.urlopen(offline, timeout=2) as response:
        if response.read().decode() != "offline":
            raise SystemExit("an offline agent download started")
    skipped = urllib.request.Request(f"http://127.0.0.1:{port}/agents/skip", data=b"", method="POST")
    with urllib.request.urlopen(skipped, timeout=2) as response:
        if response.read().decode() != "ok" or not agents_marker.is_file():
            raise SystemExit("skipping agents did not finish")
    online_calls["force"] = ""
    done_look = urllib.request.Request(f"http://127.0.0.1:{port}/done", data=b"", method="POST")
    with urllib.request.urlopen(done_look, timeout=2) as response:
        if response.status != 200:
            raise SystemExit("done after the look and the agents failed")
    choices.write_text(json.dumps({"password": False, "user": "alex", "agents": ["Nope"]}))
    bad = urllib.request.Request(f"http://127.0.0.1:{port}/look/apply", data=b"", method="POST")
    try:
        urllib.request.urlopen(bad, timeout=2)
    except urllib.error.HTTPError as exc:
        if exc.code != 409:
            raise SystemExit(f"an unknown agent returned {exc.code}") from exc
    else:
        raise SystemExit("an unknown agent was accepted")
    log_path = tmp / "app-install.log"
    log_path.write_text("\n".join(f"line {index}" for index in range(100)) + "\n", encoding="utf-8")
    os.chmod(log_path, 0o644)
    os.environ["WASD_APP_LOG"] = str(log_path)
    held = threading.Event()
    release = threading.Event()

    def hold_apps():
        with APPS_LOCK:
            held.set()
            release.wait(3)

    worker = threading.Thread(target=hold_apps, daemon=True)
    worker.start()
    if not held.wait(2):
        raise SystemExit("the install lock was not taken")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/output", timeout=2) as response:
            body = response.read().decode()
    finally:
        release.set()
        worker.join(2)
    if body.splitlines() != [f"line {index}" for index in range(20, 100)]:
        raise SystemExit("the install output was truncated wrong")
    link = tmp / "app-install-link"
    link.symlink_to("/etc/passwd")
    os.environ["WASD_APP_LOG"] = str(link)
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/output", timeout=2) as response:
        if response.read():
            raise SystemExit("a linked install log was shown")
    os.environ.pop("WASD_APP_LOG", None)
    import inspect
    awake_source = inspect.getsource(hold_awake) + inspect.getsource(release_awake)
    if "WASD_SELF_CHECK" not in awake_source:
        raise SystemExit("the screen hold would run during self-check")
    for banned in ("gsettings", "kwriteconfig", "powerprofilesctl", "xset", "setterm"):
        if banned in awake_source:
            raise SystemExit(f"the screen hold uses {banned}")
    window = Path(__file__).with_name("Complete.qml").read_text(encoding="utf-8")
    if 'postApps("/awake"' not in window or "showAppTerm" not in window or "preview" not in window:
        raise SystemExit("the app install does not hold the screen")
    sentinel = tmp / "awake-ran"
    if sentinel.exists():
        sentinel.unlink()
    fake_awake = tmp / "wasd-awake"
    fake_awake.write_text(f"#!/bin/sh\ntouch {sentinel}\n", encoding="utf-8")
    os.chmod(fake_awake, 0o755)
    os.environ["WASD_AWAKE"] = str(fake_awake)
    for path in ("/awake", "/awake/release"):
        posted = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=b"", method="POST")
        with urllib.request.urlopen(posted, timeout=2) as response:
            if response.status != 200:
                raise SystemExit(f"{path} returned {response.status}")
    if sentinel.exists():
        raise SystemExit("self-check held the screen")
    os.environ.pop("WASD_AWAKE", None)
    server.shutdown()
    for child in tmp.rglob("*"):
        if not child.is_file():
            continue
        data = child.read_bytes()
        if b"not-stored-secret" in data:
            raise SystemExit(f"the secret was written to {child}")
        if b"192.168.9.9" in data:
            raise SystemExit(f"the posted address was written to {child}")
    shutil.rmtree(tmp)
    print("complete self-check ok")


def main():
    if "--self-check" in sys.argv:
        self_check()
        return 0
    if is_live():
        return 0
    if not CHOICES.is_file():
        return 0
    choices = read_choices()
    if choices is None:
        print("The choice file is not usable.", file=sys.stderr)
        return 1
    ask = choices["password"] and not MARKER.is_file()
    saved = choices["wifi"]
    ask_wifi = saved is not None and not WIFI_MARKER.is_file()
    tcp = choices.get("tcp")
    ask_ethernet = tcp is not None and tcp.get("kind") == "ethernet"
    ask_apps = needs_download(choices["apps"]) and not APPS_MARKER.is_file()
    ask_agents = bool(choices["agents"]) and not AGENTS_MARKER.is_file()
    server = serve()
    port = server.server_address[1]
    qml = next(
        (
            found
            for found in (
                "/usr/bin/wasd-qml",
                shutil.which("qml6"),
                shutil.which("qml"),
                shutil.which("qml-qt6"),
                "/usr/lib64/qt6/bin/qml",
            )
            if found and os.access(found, os.X_OK)
        ),
        "/usr/bin/wasd-qml",
    )
    command = [
        qml,
        str(QML),
        "--want-password",
        "1" if ask else "0",
        "--want-wifi",
        "1" if ask_wifi else "0",
        "--want-ethernet",
        "1" if ask_ethernet else "0",
        "--want-apps",
        "1" if ask_apps else "0",
        "--want-agents",
        "1" if ask_agents else "0",
        "--wifi-ssid",
        saved[0] if saved else "",
        "--wifi-security",
        saved[1] if saved else "",
        "--port",
        str(port),
    ]
    try:
        proc = subprocess.run(command)
    finally:
        release_awake()
        server.shutdown()
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
