#!/usr/bin/env python3
"""While a game is open, hold performance and keep the screen and sleep off.

The hold ends when the game does. The profile returns to whatever it was.
Steam marks its games. WASD launchers mark theirs. Nothing else counts.
"""

import fcntl
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def game_marked(blob):
    for item in blob.split(b"\0"):
        if item == b"WASD_GAME=1":
            return True
        if item.startswith(b"SteamGameId="):
            value = item.split(b"=", 1)[1]
            if value and value != b"0":
                return True
    return False


def process_alive(pid):
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    end = stat.rfind(")")
    if end < 0 or end + 2 >= len(stat):
        return False
    return stat[end + 2] not in "ZX"


def game_running():
    proc = Path("/proc")
    try:
        names = list(proc.iterdir())
    except OSError:
        return False
    for name in names:
        if not name.name.isdigit() or not process_alive(name.name):
            continue
        try:
            blob = (name / "environ").read_bytes()
        except OSError:
            continue
        if game_marked(blob):
            return True
    return False


def profile_argv():
    return [
        "powerprofilesctl",
        "launch",
        "--profile",
        "performance",
        "--reason",
        "A game is running",
        "--appid",
        "wasd-game",
        "--",
        "sleep",
        "infinity",
    ]


def inhibit_argv():
    return [
        "systemd-inhibit",
        "--what=idle:sleep",
        "--who=WASD",
        "--why=A game is running",
        "--mode=block",
        "--",
        "sleep",
        "infinity",
    ]


def spawn(argv):
    try:
        return subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None


def stop(proc):
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()


def self_check():
    if not game_marked(b"WASD_GAME=1\0HOME=/home/rowge"):
        raise SystemExit("a WASD game was not noticed")
    if not game_marked(b"HOME=/\0SteamGameId=526870"):
        raise SystemExit("a Steam game was not noticed")
    if game_marked(b"SteamGameId=0\0WASD_GAME=0"):
        raise SystemExit("an idle Steam client counted as a game")
    if game_marked(b""):
        raise SystemExit("an empty process counted as a game")
    profile = profile_argv()
    inhibit = inhibit_argv()
    if "set" in profile or profile[1] != "launch" or "performance" not in profile:
        raise SystemExit("the performance hold would stick")
    if inhibit[:4] != ["systemd-inhibit", "--what=idle:sleep", "--who=WASD", "--why=A game is running"]:
        raise SystemExit("the screen hold is not limited to the game")
    if profile[-2:] != ["sleep", "infinity"] or inhibit[-2:] != ["sleep", "infinity"]:
        raise SystemExit("the holds do not end with the game")
    joined = " ".join(profile + inhibit)
    for banned in ("gsettings", "kwriteconfig", "xset", "setterm"):
        if banned in joined:
            raise SystemExit(f"the game power helper uses {banned}")
    print("game power self-check ok")


def lock_session():
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/wasd-game-power-{os.getuid()}"
    path = Path(runtime)
    path.mkdir(parents=True, exist_ok=True)
    handle = (path / "wasd-game-power.lock").open("w")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    return handle


def main():
    held_lock = lock_session()
    if held_lock is None:
        return
    profile = None
    inhibit = None
    stopping = {"now": False}

    def release(signum=None, frame=None):
        if stopping["now"]:
            return
        stopping["now"] = True
        stop(profile)
        stop(inhibit)
        raise SystemExit

    signal.signal(signal.SIGTERM, release)
    signal.signal(signal.SIGINT, release)
    while not stopping["now"]:
        running = game_running()
        if running and profile is None and inhibit is None:
            profile = spawn(profile_argv())
            if profile is not None:
                time.sleep(0.2)
                if profile.poll() is not None:
                    profile = None
            inhibit = spawn(inhibit_argv())
        elif not running and (profile is not None or inhibit is not None):
            stop(profile)
            stop(inhibit)
            profile = None
            inhibit = None
        time.sleep(2)


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        self_check()
    else:
        main()
