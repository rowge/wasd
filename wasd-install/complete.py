#!/usr/bin/env python3
"""Open Completing the install on the first desktop session.

The password is posted to a local page and handed to the setter on its
standard input. It is not placed on a command line. This does nothing on
the live USB, and nothing when the install choices are not there.
"""

import json
import os
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/usr/libexec")

from disks import is_live  # noqa: E402
from set_password import validate_password  # noqa: E402

CHOICES = Path(os.environ.get("WASD_CHOICES", "/etc/wasd/choices.json"))
MARKER = Path(os.environ.get("WASD_PASSWORD_MARK", "/etc/wasd/password-set"))
QML = Path(os.environ.get("WASD_COMPLETE_QML", "/usr/share/wasd/install/Complete.qml"))


def autostart_path():
    override = os.environ.get("WASD_AUTOSTART")
    if override:
        return Path(override)
    return Path.home() / ".config/autostart/wasd-complete.desktop"


def password_wanted():
    try:
        data = json.loads(CHOICES.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    flag = data.get("password")
    if flag is True:
        return True
    if flag is False:
        return False
    return None


def pkexec_setter(blob):
    proc = subprocess.run(
        ["pkexec", "/usr/libexec/wasd-set-password"],
        input=blob,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError("not set")


SETTER = pkexec_setter


def finish_allowed():
    wanted = password_wanted()
    if wanted is None:
        return False
    if wanted and not MARKER.is_file():
        return False
    return True


def remove_autostart():
    if not finish_allowed():
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

    def do_POST(self):
        if self.client_address[0] != "127.0.0.1":
            self._reply(403, "This request was refused.")
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length < 0 or length > 256:
            self._reply(400, "That password cannot be used.")
            return
        blob = self.rfile.read(length) if length else b""
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
            finally:
                blob = b""
            self._reply(200, "ok")
            return
        if self.path == "/done":
            if remove_autostart():
                self._reply(200, "ok")
            else:
                self._reply(409, "The window will open again next time.")
            return
        self._reply(404, "This request was refused.")


def serve():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def self_check():
    global SETTER, CHOICES, MARKER
    tmp = Path("/tmp/wasd-complete-self")
    if tmp.exists():
        for child in tmp.iterdir():
            child.unlink()
    else:
        tmp.mkdir(mode=0o700)
    choices = tmp / "choices.json"
    marker = tmp / "password-set"
    auto = tmp / "wasd-complete.desktop"
    choices.write_text(json.dumps({"password": True, "user": "alex"}))
    os.environ["WASD_CHOICES"] = str(choices)
    os.environ["WASD_PASSWORD_MARK"] = str(marker)
    os.environ["WASD_AUTOSTART"] = str(auto)
    CHOICES = choices
    MARKER = marker
    auto.write_text("[Desktop Entry]\n")
    seen = {}

    def fake_setter(blob):
        seen["length"] = len(blob)
        if b"not-stored-secret" != blob:
            raise RuntimeError("unexpected")

    SETTER = fake_setter
    if finish_allowed():
        raise SystemExit("finish ran before the password was set")
    server = serve()
    port = server.server_address[1]
    import urllib.request

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
    done = urllib.request.Request(f"http://127.0.0.1:{port}/done", data=b"", method="POST")
    with urllib.request.urlopen(done, timeout=2) as response:
        if response.status != 200:
            raise SystemExit("done post failed")
    if auto.exists():
        raise SystemExit("the startup entry was not removed")
    server.shutdown()
    for child in tmp.iterdir():
        data = child.read_bytes()
        if b"not-stored-secret" in data:
            raise SystemExit(f"the secret was written to {child}")
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
    wanted = password_wanted()
    if wanted is None:
        print("The choice file is not usable.", file=sys.stderr)
        return 1
    ask = wanted and not MARKER.is_file()
    server = serve()
    port = server.server_address[1]
    qml = "qml6" if shutil.which("qml6") else "qml"
    command = [
        qml,
        str(QML),
        "--want-password",
        "1" if ask else "0",
        "--port",
        str(port),
    ]
    try:
        proc = subprocess.run(command)
    finally:
        server.shutdown()
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
