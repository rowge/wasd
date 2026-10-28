#!/usr/bin/env python3
"""Network helper for Install WASD.

--serve listens on 127.0.0.1:8765. Status is a read. Connecting and TCP/IP
changes run only on a live USB, through NetworkManager, and the passphrase
is not printed or written to the installer file.

The same file is also installed as wasd-connect-wifi. That entry connects
the network saved at install time. Completing the install runs it through
pkexec and passes the passphrase on standard input, not on the command line.
A manual address is read from the choice file. On Wi-Fi it is part of that
connection. On Ethernet, --ethernet writes it. The request does not carry
the address.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, "/usr/libexec")
try:
    from disks import is_live
except ImportError:
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from disks import is_live

PORT = 8765
WIFI_ID = "WASD Wi-Fi"
ETHERNET_ID = "WASD Ethernet"
WIFI_KEYS = {"ssid", "security", "hidden"}
TCP_KEYS = {"mode", "interface", "kind", "address", "netmask", "gateway", "dns"}
IFACE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,15}$")
DEVICE_KIND = {"wifi": "wifi", "ethernet": "ethernet"}
DEVICE_LABEL = {"wifi": "Wi-Fi", "ethernet": "Ethernet"}
SKIP_NAME_PREFIXES = ("docker", "virbr", "veth", "br-")


class Refuse(Exception):
    pass


def netmask_prefix(mask):
    parts = mask.split(".")
    if len(parts) != 4 or any(not part.isdigit() for part in parts):
        raise Refuse("Use a netmask like 255.255.255.0.")
    numbers = [int(part) for part in parts]
    if any(number < 0 or number > 255 for number in numbers):
        raise Refuse("Use a netmask like 255.255.255.0.")
    bits = "".join(f"{number:08b}" for number in numbers)
    if "01" in bits:
        raise Refuse("Use a netmask like 255.255.255.0.")
    return str(bits.count("1"))


def validate_wifi(ssid, passphrase):
    if not isinstance(ssid, str) or not ssid.strip() or ssid.startswith("-"):
        return "Type the network name."
    if "\n" in ssid or "\x00" in ssid or len(ssid) > 32:
        return "That network name cannot be used."
    if not isinstance(passphrase, str) or "\n" in passphrase or "\r" in passphrase or "\x00" in passphrase:
        return "That passphrase cannot be used."
    if passphrase and not 8 <= len(passphrase) <= 63:
        return "A passphrase is 8 to 63 characters, or empty for an open network."
    return None


def wifi_is_open(security):
    text = (security or "").strip().lower()
    return text in ("", "--", "open", "none")


def passphrase_problem(security, passphrase):
    if not isinstance(passphrase, str) or "\n" in passphrase or "\r" in passphrase or "\x00" in passphrase:
        return "That passphrase cannot be used."
    if not wifi_is_open(security) and not passphrase:
        return "Type the passphrase."
    if passphrase and not 8 <= len(passphrase) <= 63:
        return "A passphrase is 8 to 63 characters, or empty for an open network."
    return None


def read_saved_wifi(path):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or "wifi" not in data:
        return None
    wifi = data["wifi"]
    if not isinstance(wifi, dict) or any(key not in WIFI_KEYS for key in wifi):
        return None
    ssid = wifi.get("ssid") or ""
    security = wifi.get("security") or ""
    if not isinstance(ssid, str) or not isinstance(security, str):
        return None
    if not isinstance(wifi.get("hidden", False), bool):
        return None
    if validate_wifi(ssid, "") is not None:
        return None
    return ssid.strip(), security, wifi.get("hidden", False) is True


def _key_value(value):
    return value.replace("\\", "\\\\")


def ipv4_ok(value):
    if not isinstance(value, str):
        return False
    parts = value.split(".")
    if len(parts) != 4:
        return False
    for part in parts:
        if not part.isdigit() or (len(part) > 1 and part.startswith("0")):
            return False
        number = int(part)
        if number > 255:
            return False
    return True


def dns_servers(value):
    if not isinstance(value, str):
        return []
    return [part for part in re.split(r"[\s,]+", value) if part]


def _manual_ipv4(tcp):
    prefix = netmask_prefix(tcp["netmask"])
    servers = dns_servers(tcp["dns"])
    return [
        "[ipv4]",
        "method=manual",
        f"address1={tcp['address']}/{prefix},{tcp['gateway']}",
        f"dns={';'.join(servers)};",
        "",
    ]


def render_keyfile(ssid, passphrase, hidden, secured, tcp=None):
    manual = tcp if tcp and tcp.get("kind") == "wifi" else None
    lines = [
        "[connection]",
        f"id={WIFI_ID}",
        "type=wifi",
    ]
    if manual:
        lines.append(f"interface-name={manual['interface']}")
    lines.extend([
        "autoconnect=true",
        "",
        "[wifi]",
        f"ssid={_key_value(ssid)}",
        "mode=infrastructure",
        f"hidden={'true' if hidden else 'false'}",
        "",
    ])
    if secured:
        lines.extend([
            "[wifi-security]",
            "key-mgmt=wpa-psk",
            f"psk={_key_value(passphrase)}",
            "",
        ])
    if manual:
        lines.extend(_manual_ipv4(manual))
    else:
        lines.extend([
            "[ipv4]",
            "method=auto",
            "",
        ])
    lines.extend([
        "[ipv6]",
        "method=auto",
        "",
    ])
    return "\n".join(lines)


def wifi_error(result):
    text = ((getattr(result, "stderr", "") or "") + (getattr(result, "stdout", "") or "")).lower()
    if "secret" in text or "password" in text or "psk" in text:
        return "The passphrase was not accepted."
    if "not found" in text or "no network" in text:
        return "That network was not found."
    return "Could not connect."


def connect_saved(ssid, passphrase, security, hidden, runner, key_dir, tcp=None):
    problem = passphrase_problem(security, passphrase)
    if problem:
        raise Refuse(problem)
    secured = bool(passphrase)
    key_dir = Path(key_dir)
    key_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(key_dir, 0o700)
    path = key_dir / "wasd.nmconnection"
    try:
        path.write_text(render_keyfile(ssid, passphrase if secured else "", hidden, secured, tcp))
        os.chmod(path, 0o600)
        passphrase = ""
        radio = runner(["radio", "wifi", "on"])
        if radio.returncode != 0:
            raise Refuse("Could not connect.")
        runner(["connection", "delete", "id", WIFI_ID])
        loaded = runner(["connection", "load", str(path)])
        if loaded.returncode != 0:
            runner(["connection", "delete", "id", WIFI_ID])
            raise Refuse("Could not connect.")
        up = runner(["-w", "25", "connection", "up", "id", WIFI_ID])
        if up.returncode != 0:
            runner(["connection", "delete", "id", WIFI_ID])
            raise Refuse(wifi_error(up))
    finally:
        passphrase = ""
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def validate_tcp(data):
    if not isinstance(data, dict) or any(key not in TCP_KEYS for key in data):
        return "Choose an adapter."
    mode = data.get("mode") or ""
    if mode == "auto":
        return None
    if mode != "manual":
        return "Choose automatic or manual."
    interface = data.get("interface") or ""
    kind = data.get("kind") or ""
    if (
        not isinstance(interface, str)
        or not IFACE_NAME.fullmatch(interface)
        or interface.startswith("-")
        or "\n" in interface
        or "\x00" in interface
        or kind not in DEVICE_KIND
    ):
        return "Choose an adapter."
    address = data.get("address") or ""
    netmask = data.get("netmask") or ""
    gateway = data.get("gateway") or ""
    dns = data.get("dns") or ""
    if not ipv4_ok(address):
        return "Use an IP address like 192.168.1.20."
    if not isinstance(netmask, str):
        return "Use a netmask like 255.255.255.0."
    try:
        netmask_prefix(netmask)
    except Refuse as exc:
        return str(exc)
    if not ipv4_ok(gateway):
        return "Use a gateway like 192.168.1.1."
    servers = dns_servers(dns)
    if not servers or any(not ipv4_ok(part) for part in servers):
        return "Use a DNS address like 1.1.1.1."
    return None


def read_saved_tcp(path):
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or "tcp" not in data:
        return None
    tcp = data["tcp"]
    if validate_tcp(tcp) is not None or tcp.get("mode") != "manual":
        return None
    return {
        "mode": "manual",
        "interface": tcp["interface"],
        "kind": tcp["kind"],
        "address": tcp["address"],
        "netmask": tcp["netmask"],
        "gateway": tcp["gateway"],
        "dns": tcp["dns"],
    }


def _device_allowed(name, nm_type):
    if not isinstance(name, str) or not IFACE_NAME.fullmatch(name):
        return None
    lowered = name.lower()
    if lowered == "lo" or lowered.startswith(SKIP_NAME_PREFIXES):
        return None
    return DEVICE_KIND.get(nm_type)


def parse_devices(text):
    rows = []
    seen = set()
    for line in text.splitlines():
        parts = _split_terse(line)
        if len(parts) < 2:
            continue
        name, nm_type = parts[0], parts[1]
        kind = _device_allowed(name, nm_type)
        if kind is None or name in seen:
            continue
        seen.add(name)
        rows.append({
            "device": name,
            "kind": kind,
            "label": DEVICE_LABEL[kind],
        })
    rows.sort(key=lambda row: (0 if row["kind"] == "wifi" else 1, row["device"]))
    return rows


def list_devices():
    if not is_live():
        raise Refuse("This computer was not changed.")
    if not shutil.which("nmcli"):
        return []
    listed = _nmcli(["-t", "-f", "DEVICE,TYPE", "device", "status"])
    if listed.returncode != 0:
        return []
    return parse_devices(listed.stdout)


def _nmcli(args):
    if not shutil.which("nmcli"):
        raise Refuse("NetworkManager is not available.")
    return subprocess.run(["nmcli", *args], capture_output=True, text=True)


def _split_terse(line):
    parts = []
    current = []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def parse_wifi_list(text):
    rows = []
    seen = set()
    for line in text.splitlines():
        parts = _split_terse(line)
        if len(parts) < 4:
            continue
        in_use, ssid, signal, security = parts[0], parts[1], parts[2], parts[3]
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        try:
            strength = int(signal)
        except ValueError:
            strength = 0
        rows.append({
            "ssid": ssid,
            "signal": strength,
            "security": security,
            "inUse": in_use == "*",
        })
    rows.sort(key=lambda row: (-row["signal"], row["ssid"].lower()))
    return rows[:12]


def _link_up(state):
    text = (state or "").strip().lower()
    return text == "connected" or text.startswith("connected (")


def _detail_from(active_text):
    for line in (active_text or "").splitlines():
        parts = _split_terse(line)
        if len(parts) < 2:
            continue
        if parts[1] == "802-11-wireless":
            return parts[0] or "Wi-Fi"
        if parts[1] == "802-3-ethernet":
            return "Wired"
    return ""


def connection_view(general_text, device_text, active_text):
    """Whether a real adapter is up.

    NetworkManager's overall state stays at "connected (site only)" or
    "connected (local only)" while it checks past the local network. A wired
    adapter in "connected" is already up. Loopback and virtual adapters are
    not a connection.
    """
    wired = False
    wireless = False
    for line in (device_text or "").splitlines():
        parts = _split_terse(line)
        if len(parts) < 3:
            continue
        kind = _device_allowed(parts[0], parts[1])
        if not _link_up(parts[2]):
            continue
        if kind == "ethernet":
            wired = True
        elif kind == "wifi":
            wireless = True
    general = ""
    for line in (general_text or "").splitlines():
        if line.strip():
            general = line.strip()
            break
    connected = _link_up(general) or wired or wireless
    if not connected:
        return False, ""
    detail = _detail_from(active_text)
    if not detail and wired:
        detail = "Wired"
    if not detail and wireless:
        detail = "Wi-Fi"
    return True, detail


def status(rescan=False):
    if not shutil.which("nmcli"):
        return {"connected": False, "detail": "", "networks": []}
    networks = []
    if rescan:
        _nmcli(["radio", "wifi", "on"])
        listed = _nmcli(["-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes"])
        if listed.returncode == 0:
            networks = parse_wifi_list(listed.stdout)
    general = _nmcli(["-t", "-f", "STATE", "general"])
    devices = _nmcli(["-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"])
    active = _nmcli(["-t", "-f", "NAME,TYPE", "connection", "show", "--active"])
    connected, detail = connection_view(
        general.stdout if general.returncode == 0 else "",
        devices.stdout if devices.returncode == 0 else "",
        active.stdout if active.returncode == 0 else "",
    )
    return {"connected": connected, "detail": detail, "networks": networks}


def connect_wifi(data):
    ssid = data.get("ssid") or ""
    passphrase = data.get("passphrase") or ""
    problem = validate_wifi(ssid, passphrase)
    if problem:
        raise Refuse(problem)
    if not is_live():
        raise Refuse("This computer was not changed.")
    command = ["-w", "25", "device", "wifi", "connect", ssid.strip()]
    if passphrase:
        command += ["password", passphrase]
    if data.get("hidden"):
        command += ["hidden", "yes"]
    result = _nmcli(command)
    passphrase = ""
    if result.returncode != 0:
        raise Refuse(wifi_error(result))


def connect_saved_main():
    uid = os.environ.get("PKEXEC_UID", "")
    if not uid.isdigit():
        print("This is only used by Completing the install.", file=sys.stderr)
        return 1
    if is_live():
        print("This computer was not changed.", file=sys.stderr)
        return 1
    blob = sys.stdin.buffer.read(64)
    if len(blob) > 63:
        print("That passphrase cannot be used.", file=sys.stderr)
        return 1
    try:
        passphrase = blob.decode("utf-8")
    except UnicodeError:
        print("That passphrase cannot be used.", file=sys.stderr)
        return 1
    blob = b""
    saved = read_saved_wifi(os.environ.get("WASD_CHOICES", "/etc/wasd/choices.json"))
    if saved is None:
        passphrase = ""
        print("No network was saved.", file=sys.stderr)
        return 1
    ssid, security, hidden = saved
    tcp = read_saved_tcp(os.environ.get("WASD_CHOICES", "/etc/wasd/choices.json"))
    key_dir = Path(os.environ.get("WASD_WIFI_KEYDIR", "/run/wasd-wifi"))
    try:
        connect_saved(ssid, passphrase, security, hidden, _nmcli, key_dir, tcp)
    except Refuse as exc:
        passphrase = ""
        print(exc, file=sys.stderr)
        return 1
    passphrase = ""
    marker = Path(os.environ.get("WASD_WIFI_MARK", "/etc/wasd/wifi-set"))
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(ssid + "\n")
    os.chmod(marker, 0o644)
    return 0


def skip_saved_main():
    uid = os.environ.get("PKEXEC_UID", "")
    if not uid.isdigit():
        print("This is only used by Completing the install.", file=sys.stderr)
        return 1
    if is_live():
        print("This computer was not changed.", file=sys.stderr)
        return 1
    saved = read_saved_wifi(os.environ.get("WASD_CHOICES", "/etc/wasd/choices.json"))
    if saved is None:
        print("No network was saved.", file=sys.stderr)
        return 1
    marker = Path(os.environ.get("WASD_WIFI_MARK", "/etc/wasd/wifi-set"))
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("skipped\n")
    os.chmod(marker, 0o644)
    return 0


def render_ethernet_keyfile(tcp):
    lines = [
        "[connection]",
        f"id={ETHERNET_ID}",
        "type=ethernet",
        f"interface-name={tcp['interface']}",
        "autoconnect=true",
        "",
    ]
    lines.extend(_manual_ipv4(tcp))
    lines.extend([
        "[ipv6]",
        "method=auto",
        "",
    ])
    return "\n".join(lines)


def apply_ethernet(tcp, runner, key_dir):
    if not tcp or tcp.get("kind") != "ethernet":
        raise Refuse("No address was saved.")
    problem = validate_tcp(tcp)
    if problem:
        raise Refuse("Choose an adapter." if problem == "Choose an adapter." else problem)
    key_dir = Path(key_dir)
    key_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(key_dir, 0o700)
    path = key_dir / "wasd-ethernet.nmconnection"
    try:
        path.write_text(render_ethernet_keyfile(tcp))
        os.chmod(path, 0o600)
        runner(["connection", "delete", "id", ETHERNET_ID])
        loaded = runner(["connection", "load", str(path)])
        if loaded.returncode != 0:
            runner(["connection", "delete", "id", ETHERNET_ID])
            raise Refuse("Those settings were not used.")
        up = runner(["-w", "15", "connection", "up", "id", ETHERNET_ID])
        if up.returncode != 0:
            return "Saved for this adapter. It is not connected yet."
        return ""
    finally:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def apply_ethernet_main():
    uid = os.environ.get("PKEXEC_UID", "")
    if not uid.isdigit():
        print("This is only used by Completing the install.", file=sys.stderr)
        return 1
    if is_live():
        print("This computer was not changed.", file=sys.stderr)
        return 1
    tcp = read_saved_tcp(os.environ.get("WASD_CHOICES", "/etc/wasd/choices.json"))
    if tcp is None or tcp.get("kind") != "ethernet":
        print("No address was saved.", file=sys.stderr)
        return 1
    key_dir = Path(os.environ.get("WASD_WIFI_KEYDIR", "/run/wasd-wifi"))
    try:
        note = apply_ethernet(tcp, _nmcli, key_dir)
    except Refuse as exc:
        print(exc, file=sys.stderr)
        return 1
    if note:
        print(note)
    return 0


def _device_connection(device, kind):
    listed = _nmcli(["-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"])
    if listed.returncode != 0:
        return ""
    for line in listed.stdout.splitlines():
        parts = _split_terse(line)
        if len(parts) < 4 or parts[0] != device:
            continue
        if DEVICE_KIND.get(parts[1]) != kind or parts[2] != "connected":
            return ""
        name = parts[3]
        if not name or name == "--":
            return ""
        return name
    return ""


def apply_tcp(data):
    if not is_live():
        raise Refuse("This computer was not changed.")
    if not isinstance(data, dict):
        raise Refuse("Choose an adapter.")
    if (data.get("mode") or "") == "auto":
        return {"applied": False, "message": "Automatic uses the address the network offers."}
    problem = validate_tcp(data)
    if problem:
        raise Refuse(problem)
    name = _device_connection(data["interface"], data["kind"])
    if not name:
        return {
            "applied": False,
            "message": "Saved for the installed system. This adapter is not connected yet.",
        }
    prefix = netmask_prefix(data["netmask"])
    servers = dns_servers(data["dns"])
    result = _nmcli([
        "connection", "modify", name,
        "ipv4.method", "manual",
        "ipv4.addresses", f"{data['address']}/{prefix}",
        "ipv4.gateway", data["gateway"],
        "ipv4.dns", ",".join(servers),
    ])
    if result.returncode != 0:
        raise Refuse("Those settings were not used.")
    up = _nmcli(["connection", "up", name])
    if up.returncode != 0:
        raise Refuse("Those settings were saved, and the connection did not come back.")
    return {
        "applied": True,
        "message": "Saved for the installed system. These settings are in use on this adapter now.",
    }


def _reply(handler, code, text):
    body = text.encode()
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _local(self):
        if self.client_address[0] == "127.0.0.1":
            return True
        _reply(self, 403, "This request was refused.")
        return False

    def do_GET(self):
        if not self._local():
            return
        path = self.path.split("?", 1)[0]
        if path == "/devices":
            try:
                devices = list_devices()
            except Refuse as exc:
                _reply(self, 400, str(exc))
                return
            _reply(self, 200, json.dumps({"devices": devices}))
            return
        if path != "/status":
            _reply(self, 404, "This request was refused.")
            return
        rescan = "rescan=1" in self.path
        _reply(self, 200, json.dumps(status(rescan)))

    def do_POST(self):
        if not self._local():
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length < 0 or length > 2048:
            _reply(self, 400, "That request was not usable.")
            return
        blob = self.rfile.read(length) if length else b""
        try:
            data = json.loads(blob.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            _reply(self, 400, "That request was not usable.")
            return
        if not isinstance(data, dict):
            _reply(self, 400, "That request was not usable.")
            return
        try:
            if self.path == "/wifi":
                connect_wifi(data)
            elif self.path == "/tcp":
                _reply(self, 200, json.dumps(apply_tcp(data)))
                return
            else:
                _reply(self, 404, "This request was refused.")
                return
        except Refuse as exc:
            _reply(self, 400, str(exc))
            return
        _reply(self, 200, json.dumps(status(False)))


def self_check():
    if netmask_prefix("255.255.255.0") != "24":
        raise SystemExit("a normal netmask was wrong")
    try:
        netmask_prefix("255.255.255.1")
    except Refuse:
        pass
    else:
        raise SystemExit("a broken netmask was accepted")
    if validate_wifi("", "") != "Type the network name.":
        raise SystemExit("an empty network name was accepted")
    if validate_wifi("Home", "short") is None:
        raise SystemExit("a short passphrase was accepted")
    if validate_wifi("Home", "") is not None:
        raise SystemExit("an open network was refused")
    try:
        connect_wifi({"ssid": "Home", "passphrase": "correct horse"})
    except Refuse as exc:
        if str(exc) != "This computer was not changed.":
            raise SystemExit(f"preview connect was not refused: {exc}") from exc
    else:
        raise SystemExit("a network change ran outside the live USB")
    try:
        apply_tcp({"mode": "manual", "address": "192.168.1.20", "netmask": "255.255.255.0", "gateway": "192.168.1.1", "dns": "1.1.1.1"})
    except Refuse as exc:
        if str(exc) != "This computer was not changed.":
            raise SystemExit(f"preview tcp was not refused: {exc}") from exc
    else:
        raise SystemExit("a TCP change ran outside the live USB")
    rows = parse_wifi_list("*:Home:80:WPA2\n :Shop:40:WPA1 WPA2\n :Home:10:WPA2\n")
    if len(rows) != 2 or rows[0]["ssid"] != "Home" or rows[0]["inUse"] is not True:
        raise SystemExit(f"wifi list parsed wrong: {rows}")
    if connect_saved_main() != 1:
        raise SystemExit("a saved network connect ran without Completing the install")
    if skip_saved_main() != 1:
        raise SystemExit("a skipped network was recorded without Completing the install")
    if apply_ethernet_main() != 1:
        raise SystemExit("an ethernet address was applied without Completing the install")
    sample_devices = "\n".join([
        "enp4s0:ethernet:connected:Wired connection 1",
        "wlp3s0:wifi:disconnected:",
        "lo:loopback:unmanaged:",
        "docker0:bridge:connected:docker0",
        "virbr0:bridge:connected:virbr0",
        "tun0:tun:unmanaged:",
        "wlp0s20f3:wifi:unavailable:",
        "eth0:ethernet:unavailable:",
        "veth123:ethernet:unmanaged:",
        "docker1:ethernet:connected:docker1",
        "p2p-dev-wlp3s0:wifi-p2p:disconnected:",
        "-bad:ethernet:disconnected:",
    ])
    devices = parse_devices(sample_devices)
    names = [row["device"] for row in devices]
    if names != ["wlp0s20f3", "wlp3s0", "enp4s0", "eth0"]:
        raise SystemExit(f"adapters parsed wrong: {devices}")
    if devices[0]["label"] != "Wi-Fi" or devices[0]["kind"] != "wifi" or devices[2]["kind"] != "ethernet":
        raise SystemExit(f"adapter labels were wrong: {devices}")
    wired_devices = "\n".join([
        "enp1s0:ethernet:connected:Wired connection 1",
        "lo:loopback:connected (externally):lo",
        "docker0:bridge:connected:docker0",
    ])
    site_only, site_detail = connection_view("connected (site only)\n", wired_devices, "")
    if not site_only or site_detail != "Wired":
        raise SystemExit(f"a wired link still being checked was {site_only} {site_detail}")
    local_only, local_detail = connection_view(
        "connected (local only)",
        "enp1s0:ethernet:connected:Wired connection 1",
        "Wired connection 1:802-3-ethernet",
    )
    if not local_only or local_detail != "Wired":
        raise SystemExit(f"a local wired link was {local_only} {local_detail}")
    coming_up, coming_detail = connection_view(
        "connecting",
        "enp1s0:ethernet:connecting (getting IP configuration):",
        "",
    )
    if coming_up or coming_detail:
        raise SystemExit(f"a cable still connecting looked up: {coming_up} {coming_detail}")
    virtual, virtual_detail = connection_view(
        "disconnected",
        "lo:loopback:connected (externally):lo\ndocker0:bridge:connected:docker0\ndocker1:ethernet:connected:docker1",
        "",
    )
    if virtual or virtual_detail:
        raise SystemExit(f"a virtual adapter looked connected: {virtual} {virtual_detail}")
    offline, offline_detail = connection_view("disconnected\n", "enp1s0:ethernet:unavailable:\nwlp3s0:wifi:disconnected:", "")
    if offline or offline_detail:
        raise SystemExit(f"no cable looked connected: {offline} {offline_detail}")
    try:
        list_devices()
    except Refuse as exc:
        if str(exc) != "This computer was not changed.":
            raise SystemExit(f"device list was not refused: {exc}") from exc
    else:
        raise SystemExit("a device list ran outside the live USB")
    manual_tcp = {
        "mode": "manual",
        "interface": "wlp3s0",
        "kind": "wifi",
        "address": "192.168.1.20",
        "netmask": "255.255.255.0",
        "gateway": "192.168.1.1",
        "dns": "1.1.1.1",
    }
    if validate_tcp(manual_tcp) is not None:
        raise SystemExit("a manual address was refused")
    if validate_tcp(dict(manual_tcp, address="192.168.1.999")) is None:
        raise SystemExit("a bad address was accepted")
    if validate_tcp(dict(manual_tcp, interface="-wlp3s0")) is None:
        raise SystemExit("a bad adapter name was accepted")
    tmp = Path("/tmp/wasd-wifi-self")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(mode=0o700)
    choices = tmp / "choices.json"
    key_dir = tmp / "key"
    secret = "correct horse"
    choices.write_text(json.dumps({"wifi": {"ssid": "Home", "security": "WPA2", "hidden": False}}))
    saved = read_saved_wifi(choices)
    if saved != ("Home", "WPA2", False):
        raise SystemExit(f"saved wifi was read wrong: {saved}")
    os.environ["PKEXEC_UID"] = "1000"
    os.environ["WASD_CHOICES"] = str(choices)
    os.environ["WASD_WIFI_MARK"] = str(tmp / "wifi-set")
    try:
        if skip_saved_main() != 0:
            raise SystemExit("skip did not record the choice")
    finally:
        os.environ.pop("PKEXEC_UID", None)
    skipped = (tmp / "wifi-set").read_text()
    if skipped != "skipped\n":
        raise SystemExit("the skip marker was wrong")
    (tmp / "wifi-set").unlink()
    if read_saved_wifi(tmp / "missing.json") is not None:
        raise SystemExit("a missing choice file looked like a saved network")
    if read_saved_tcp(tmp / "missing.json") is not None:
        raise SystemExit("a missing choice file looked like a saved address")
    leaked = tmp / "leaked.json"
    leaked.write_text(json.dumps({"wifi": {"ssid": "Home", "passphrase": "stored-secret"}}))
    if read_saved_wifi(leaked) is not None:
        raise SystemExit("a stored passphrase was accepted")
    leaked.unlink()
    if passphrase_problem("WPA2", "") != "Type the passphrase.":
        raise SystemExit("a secured network skipped the passphrase")
    if passphrase_problem("WPA2", "short") is None:
        raise SystemExit("a short passphrase was accepted for a saved network")
    if passphrase_problem("", "") is not None:
        raise SystemExit("an open saved network was refused")

    class Result:
        def __init__(self, code, stdout="", stderr=""):
            self.returncode = code
            self.stdout = stdout
            self.stderr = stderr

    seen = []
    flags = {}

    def runner(args):
        seen.append(list(args))
        if len(args) >= 2 and args[0] == "connection" and args[1] == "load":
            text = Path(args[2]).read_text()
            mode = Path(args[2]).stat().st_mode & 0o777
            flags["mode"] = mode
            flags["hidden"] = "hidden=true" in text
            flags["ssid"] = "ssid=Home" in text
            flags["psk"] = "\npsk=" in text
            if secret not in text:
                flags["missed"] = True
            return Result(0)
        if "up" in args:
            flags["up"] = True
            return Result(0)
        return Result(0)

    connect_saved("Home", secret, "WPA2", False, runner, key_dir)
    if any("correct horse" in " ".join(args) for args in seen):
        raise SystemExit("the passphrase was placed on a command")
    manual_flags = {}

    def manual_runner(args):
        if len(args) >= 2 and args[0] == "connection" and args[1] == "load":
            text = Path(args[2]).read_text()
            manual_flags["text"] = text
            manual_flags["mode"] = Path(args[2]).stat().st_mode & 0o777
            if secret not in text:
                manual_flags["missed"] = True
        if any(secret in arg for arg in args):
            manual_flags["argv"] = True
        return Result(0)

    connect_saved("Home", secret, "WPA2", False, manual_runner, key_dir, manual_tcp)
    manual_text = manual_flags.get("text") or ""
    manual_ipv4 = manual_text.split("[ipv4]", 1)[-1].split("[ipv6]", 1)[0]
    if (
        manual_flags.get("argv")
        or manual_flags.get("missed")
        or manual_flags.get("mode") != 0o600
        or "interface-name=wlp3s0" not in manual_text
        or "method=manual" not in manual_ipv4
        or "address1=192.168.1.20/24,192.168.1.1" not in manual_ipv4
        or "dns=1.1.1.1;" not in manual_ipv4
        or "method=auto" in manual_ipv4
    ):
        raise SystemExit(f"the wifi address was not saved: {manual_text}")
    secret = ""
    if flags.get("missed") or flags.get("mode") != 0o600 or not flags.get("ssid") or not flags.get("psk"):
        raise SystemExit("the connection file was wrong")
    if flags.get("hidden"):
        raise SystemExit("a listed network was marked hidden")
    if not flags.get("up"):
        raise SystemExit("the saved network was not started")
    if ["radio", "wifi", "on"] not in seen or ["-w", "25", "connection", "up", "id", WIFI_ID] not in seen:
        raise SystemExit(f"network commands were wrong: {seen}")
    if any(path.is_file() for path in key_dir.glob("*")):
        raise SystemExit("the connection file was left behind")
    failed = []

    def fail_up(args):
        failed.append(list(args))
        if "up" in args:
            return Result(1, stderr="Secrets were required, but not provided.")
        return Result(0)

    try:
        connect_saved("Home", "another secret", "WPA2", True, fail_up, key_dir)
    except Refuse as exc:
        if str(exc) != "The passphrase was not accepted.":
            raise SystemExit(f"a rejected passphrase was {exc}") from exc
    else:
        raise SystemExit("a rejected passphrase connected")
    if ["connection", "delete", "id", WIFI_ID] not in failed:
        raise SystemExit("a failed connection was kept")
    if any(path.is_file() for path in tmp.rglob("*") if path.suffix == ".nmconnection"):
        raise SystemExit("a failed connection file was left behind")
    opened = {"psk": False}

    def open_runner(args):
        if len(args) >= 2 and args[1] == "load":
            opened["psk"] = "psk=" in Path(args[2]).read_text()
        return Result(0)

    connect_saved("Cafe", "", "", True, open_runner, key_dir)
    if opened["psk"]:
        raise SystemExit("an open network stored a passphrase")
    ether = {
        "mode": "manual",
        "interface": "enp4s0",
        "kind": "ethernet",
        "address": "192.168.1.50",
        "netmask": "255.255.255.0",
        "gateway": "192.168.1.1",
        "dns": "1.1.1.1 1.0.0.1",
    }
    ether_flags = {}
    ether_seen = []

    def ether_runner(args):
        ether_seen.append(list(args))
        if len(args) >= 2 and args[1] == "load":
            text = Path(args[2]).read_text()
            ether_flags["text"] = text
            ether_flags["mode"] = Path(args[2]).stat().st_mode & 0o777
        return Result(0)

    if apply_ethernet(ether, ether_runner, key_dir):
        raise SystemExit("a connected ethernet adapter was reported down")
    ether_text = ether_flags.get("text") or ""
    ether_ipv4 = ether_text.split("[ipv4]", 1)[-1].split("[ipv6]", 1)[0]
    if (
        ether_flags.get("mode") != 0o600
        or "type=ethernet" not in ether_text
        or "interface-name=enp4s0" not in ether_text
        or "method=manual" not in ether_ipv4
        or "method=auto" in ether_ipv4
        or "address1=192.168.1.50/24,192.168.1.1" not in ether_ipv4
        or "dns=1.1.1.1;1.0.0.1;" not in ether_ipv4
    ):
        raise SystemExit(f"the ethernet file was wrong: {ether_text}")
    if any(path.is_file() for path in key_dir.glob("*")):
        raise SystemExit("the ethernet file was left behind")
    down_seen = []

    def ether_down(args):
        down_seen.append(list(args))
        if "up" in args:
            return Result(1, stderr="device not found")
        return Result(0)

    if apply_ethernet(ether, ether_down, key_dir) != "Saved for this adapter. It is not connected yet.":
        raise SystemExit("a down adapter did not keep the address")
    if len([args for args in down_seen if args[:3] == ["connection", "delete", "id"]]) != 1:
        raise SystemExit(f"a down adapter removed the saved address: {down_seen}")
    failed_load = []

    def ether_fail(args):
        failed_load.append(list(args))
        if len(args) >= 2 and args[1] == "load":
            return Result(1, stderr="error")
        return Result(0)

    try:
        apply_ethernet(ether, ether_fail, key_dir)
    except Refuse as exc:
        if str(exc) != "Those settings were not used.":
            raise SystemExit(f"a failed ethernet load was {exc}") from exc
    else:
        raise SystemExit("a failed ethernet load was kept")
    if len([args for args in failed_load if args[:3] == ["connection", "delete", "id"]]) < 2:
        raise SystemExit("a failed ethernet load left the connection")
    try:
        apply_ethernet(dict(ether, interface="enp4s0;rm"), ether_runner, key_dir)
    except Refuse:
        pass
    else:
        raise SystemExit("a bad interface was applied")
    choices.write_text(json.dumps({"tcp": ether, "wifi": {"ssid": "Home", "security": "WPA2", "hidden": False}}))
    if read_saved_tcp(choices) != ether:
        raise SystemExit(f"saved tcp was read wrong: {read_saved_tcp(choices)}")
    for path in tmp.rglob("*"):
        if path.is_file() and b"correct horse" in path.read_bytes():
            raise SystemExit(f"the passphrase was written to {path}")
        if path.is_file() and b"another secret" in path.read_bytes():
            raise SystemExit(f"the rejected passphrase was written to {path}")
    shutil.rmtree(tmp)
    print("network self-check ok")


def main():
    if "--self-check" in sys.argv:
        self_check()
        return 0
    if os.path.basename(sys.argv[0]) == "wasd-connect-wifi":
        if "--skip" in sys.argv:
            return skip_saved_main()
        if "--ethernet" in sys.argv:
            return apply_ethernet_main()
        return connect_saved_main()
    if "--serve" not in sys.argv:
        print("Nothing was changed.", file=sys.stderr)
        return 2
    try:
        server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    except OSError:
        print("The network helper is not available.", file=sys.stderr)
        return 1
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
