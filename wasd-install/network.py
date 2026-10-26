#!/usr/bin/env python3
"""Network helper for Install WASD.

--serve listens on 127.0.0.1:8765. Status is a read. Connecting and TCP/IP
changes run only on a live USB, through NetworkManager, and the passphrase
is not printed or written to the installer file.
"""

import json
import re
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/usr/libexec")
try:
    from disks import is_live
except ImportError:
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from disks import is_live

PORT = 8765
IPV4 = re.compile(r"^(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}$")


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
    if not isinstance(passphrase, str) or "\n" in passphrase or "\x00" in passphrase:
        return "That passphrase cannot be used."
    if passphrase and not 8 <= len(passphrase) <= 63:
        return "A passphrase is 8 to 63 characters, or empty for an open network."
    return None


def validate_tcp(data):
    mode = data.get("mode") or ""
    if mode == "auto":
        return None
    if mode != "manual":
        return "Choose automatic or manual."
    address = data.get("address") or ""
    netmask = data.get("netmask") or ""
    gateway = data.get("gateway") or ""
    dns = data.get("dns") or ""
    if not IPV4.fullmatch(address):
        return "Use an IP address like 192.168.1.20."
    try:
        netmask_prefix(netmask)
    except Refuse as exc:
        return str(exc)
    if not IPV4.fullmatch(gateway):
        return "Use a gateway like 192.168.1.1."
    servers = [part for part in re.split(r"[\s,]+", dns) if part]
    if not servers or any(not IPV4.fullmatch(part) for part in servers):
        return "Use a DNS address like 1.1.1.1."
    return None


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


def _detail():
    active = _nmcli(["-t", "-f", "NAME,TYPE", "connection", "show", "--active"])
    for line in active.stdout.splitlines():
        parts = _split_terse(line)
        if len(parts) < 2:
            continue
        if parts[1] == "802-11-wireless":
            return parts[0] or "Wi-Fi"
        if parts[1] == "802-3-ethernet":
            return "Wired"
    return ""


def status(rescan=False):
    if not shutil.which("nmcli"):
        return {"connected": False, "detail": "", "networks": []}
    general = _nmcli(["-t", "-f", "STATE", "general"])
    connected = general.stdout.strip() == "connected"
    networks = []
    if rescan:
        _nmcli(["radio", "wifi", "on"])
        listed = _nmcli(["-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes"])
        networks = parse_wifi_list(listed.stdout)
    return {"connected": connected, "detail": _detail() if connected else "", "networks": networks}


def _active_connection():
    active = _nmcli(["-t", "-f", "NAME,TYPE", "connection", "show", "--active"])
    for line in active.stdout.splitlines():
        parts = _split_terse(line)
        if len(parts) >= 2 and parts[1] in ("802-11-wireless", "802-3-ethernet") and parts[0]:
            return parts[0]
    return ""


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
        text = (result.stderr or result.stdout or "").lower()
        if "secret" in text or "password" in text or "psk" in text:
            raise Refuse("The passphrase was not accepted.")
        if "not found" in text or "no network" in text:
            raise Refuse("That network was not found.")
        raise Refuse("Could not connect.")


def apply_tcp(data):
    problem = validate_tcp(data)
    if problem:
        raise Refuse(problem)
    if not is_live():
        raise Refuse("This computer was not changed.")
    name = _active_connection()
    if not name:
        raise Refuse("Connect first.")
    if data.get("mode") == "auto":
        result = _nmcli(["connection", "modify", name, "ipv4.method", "auto", "ipv4.addresses", "", "ipv4.gateway", "", "ipv4.dns", ""])
    else:
        prefix = netmask_prefix(data["netmask"])
        servers = [part for part in re.split(r"[\s,]+", data["dns"]) if part]
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
        if self.path.split("?", 1)[0] != "/status":
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
                apply_tcp(data)
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
    print("network self-check ok")


def main():
    if "--self-check" in sys.argv:
        self_check()
        return 0
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
