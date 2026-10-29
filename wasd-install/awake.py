#!/usr/bin/env python3
"""Hold the screen and sleep off until this process is stopped.

The timeout setting is not changed. Both holds end when the process exits.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PID_PATH = Path("/tmp/wasd-awake.pid")
STOP_PATH = Path("/tmp/wasd-awake.stop")


def inhibit_argv():
    return [
        "systemd-inhibit",
        "--what=idle:sleep",
        "--who=Install WASD",
        "--why=Copying WASD",
        "--mode=block",
        "--",
        "sleep",
        "infinity",
    ]


def screen_call(method, signature, *args):
    return [
        "busctl",
        "--user",
        "call",
        "org.freedesktop.ScreenSaver",
        "/org/freedesktop/ScreenSaver",
        "org.freedesktop.ScreenSaver",
        method,
        signature,
        *args,
    ]


def self_check():
    sleep = inhibit_argv()
    if sleep[:6] != [
        "systemd-inhibit",
        "--what=idle:sleep",
        "--who=Install WASD",
        "--why=Copying WASD",
        "--mode=block",
        "--",
    ] or sleep[-2:] != ["sleep", "infinity"]:
        raise SystemExit("the sleep hold is not limited to the copy")
    screen = screen_call("Inhibit", "ss", "Install WASD", "Copying WASD")
    release = screen_call("UnInhibit", "u", "1")
    if screen[-4:] != ["Inhibit", "ss", "Install WASD", "Copying WASD"]:
        raise SystemExit("the screen hold is not a temporary inhibit")
    if release[-3:] != ["UnInhibit", "u", "1"]:
        raise SystemExit("the screen hold is not released")
    joined = " ".join(sleep + screen + release)
    for banned in ("gsettings", "kwriteconfig", "powerprofilesctl", "xset", "setterm"):
        if banned in joined:
            raise SystemExit(f"the awake helper uses {banned}")
    print("awake self-check ok")


def parent_death():
    try:
        import ctypes

        ctypes.CDLL(None).prctl(1, signal.SIGTERM)
    except Exception:
        return
    if os.getppid() == 1:
        raise SystemExit


def read_cookie(text):
    parts = (text or "").split()
    if len(parts) >= 2 and parts[0] == "u" and parts[1].isdigit():
        return parts[1]
    return ""


def main():
    if STOP_PATH.exists():
        return
    parent_death()
    PID_PATH.write_text(f"{os.getpid()}\n")
    cookie = ""
    inhibit = None
    try:
        inhibit = subprocess.Popen(
            inhibit_argv(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        inhibit = None
    try:
        result = subprocess.run(
            screen_call("Inhibit", "ss", "Install WASD", "Copying WASD"),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        cookie = read_cookie(result.stdout)
    except (OSError, subprocess.TimeoutExpired):
        cookie = ""

    stopping = {"now": False}

    def stop(signum=None, frame=None):
        if stopping["now"]:
            return
        stopping["now"] = True
        if cookie:
            try:
                subprocess.run(
                    screen_call("UnInhibit", "u", cookie),
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
        if inhibit is not None and inhibit.poll() is None:
            try:
                os.killpg(inhibit.pid, signal.SIGTERM)
            except OSError:
                inhibit.terminate()
        try:
            PID_PATH.unlink()
        except OSError:
            pass
        raise SystemExit

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    while not stopping["now"]:
        if STOP_PATH.exists() or os.getppid() == 1:
            stop()
        time.sleep(0.4)


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
    else:
        main()
