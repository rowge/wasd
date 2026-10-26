#!/usr/bin/env python3
"""Set the signed-in user's password and turn off automatic sign-in.

The password arrives on standard input. It is not printed, not stored, and
not accepted on the command line. Completing the install runs this through
pkexec after the account is already signed in.
"""

import os
import pwd
import re
import subprocess
import sys
from pathlib import Path

USER_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
AUTOLOGIN = (
    Path("/etc/plasmalogin.conf.d/zz-wasd-autologin.conf"),
    Path("/etc/sddm.conf.d/zz-wasd-autologin.conf"),
)


def validate_password(blob):
    if not isinstance(blob, (bytes, bytearray)) or not blob:
        return "Type a password in both boxes."
    if b"\n" in blob or b"\x00" in blob:
        return "That password cannot be used."
    if len(blob) > 256:
        return "That password is too long."
    try:
        blob.decode("utf-8")
    except UnicodeError:
        return "That password cannot be used."
    return None


def apply_password(user, blob):
    line = user.encode("utf-8") + b":" + bytes(blob) + b"\n"
    proc = subprocess.run(["chpasswd"], input=line, capture_output=True)
    line = b""
    if proc.returncode != 0:
        print("The password was not set.", file=sys.stderr)
        return 1
    for path in AUTOLOGIN:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            print("The password is set. Automatic sign-in is still on.", file=sys.stderr)
            return 1
    marker_dir = Path("/etc/wasd")
    marker_dir.mkdir(parents=True, exist_ok=True)
    marker = marker_dir / "password-set"
    marker.write_text(user + "\n")
    os.chmod(marker, 0o644)
    return 0


def self_check():
    if validate_password(b"") is None:
        raise SystemExit("empty password was accepted")
    if validate_password(b"one\ntwo") is None:
        raise SystemExit("a newline password was accepted")
    if validate_password(b"a" * 257) is None:
        raise SystemExit("a long password was accepted")
    if validate_password("fine password".encode()) is not None:
        raise SystemExit("a normal password was refused")
    print("password self-check ok")


def main():
    if "--self-check" in sys.argv:
        self_check()
        return 0
    uid = os.environ.get("PKEXEC_UID", "")
    if not uid.isdigit():
        print("This is only used by Completing the install.", file=sys.stderr)
        return 1
    try:
        user = pwd.getpwuid(int(uid)).pw_name
    except KeyError:
        print("This user cannot be changed here.", file=sys.stderr)
        return 1
    if not USER_NAME.fullmatch(user) or user == "root":
        print("This user cannot be changed here.", file=sys.stderr)
        return 1
    blob = sys.stdin.buffer.read(257)
    problem = validate_password(blob)
    if problem:
        print(problem, file=sys.stderr)
        return 1
    return apply_password(user, blob)


if __name__ == "__main__":
    raise SystemExit(main())
