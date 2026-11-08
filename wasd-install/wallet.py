#!/usr/bin/env python3
"""Create an encryption key when Set a password was left unchecked.

Completing the install runs this only in that case. The key has no
passphrase, and the wallet opens with the desktop. Anyone at the computer
can open it. A password install does not run this.
"""

import inspect
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

FINGERPRINT = re.compile(r"^[0-9A-Fa-f]{40}$|^[0-9A-Fa-f]{64}$")
WALLET_NOT_SET = "The wallet was not set up."
BATCH = b"""%no-protection
Key-Type: eddsa
Key-Curve: ed25519
Key-Usage: sign
Subkey-Type: ecdh
Subkey-Curve: cv25519
Subkey-Usage: encrypt
Name-Real: WASD
Name-Comment: wasd-wallet
Expire-Date: 0
%commit
"""


def decide(kind):
    if kind == "missing":
        return "create-gpg"
    return "skip"


def command_for(action, fingerprint=None):
    helper = os.environ.get("WASD_WALLET_FILE", "/usr/libexec/wasd-wallet-file")
    if action == "kind":
        return [helper, "kind"]
    if action == "create-gpg":
        return [helper, "create-gpg", fingerprint]
    if action == "open-gpg":
        return [helper, "open-gpg"]
    raise ValueError(action)


def wallet_dir():
    # The wallet daemon reads this directory. XDG_DATA_HOME must not move it.
    return Path.home() / ".local" / "share" / "kwalletd"


def fpr_path():
    return wallet_dir() / "wasd-gpg-fpr"


def read_fpr_file():
    path = fpr_path()
    try:
        text = path.read_text(encoding="utf-8").strip()
        mode = path.stat().st_mode
    except OSError:
        return None
    if not FINGERPRINT.fullmatch(text):
        return None
    if stat.S_IMODE(mode) & 0o077:
        return None
    return text


def write_fpr_file(fingerprint):
    path = fpr_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    path.write_text(fingerprint + "\n", encoding="utf-8")
    os.chmod(path, 0o600)


def file_matches(kind, fingerprint):
    if kind != "gpg" or not fingerprint:
        return False
    stored = read_fpr_file()
    return bool(stored) and stored.lower() == fingerprint.lower()


def gpg_env():
    env = os.environ.copy()
    env["LANG"] = "C.UTF-8"
    env["LC_ALL"] = "C"
    return env


def agent_ready():
    gnupg = Path.home() / ".gnupg"
    gnupg.mkdir(mode=0o700, exist_ok=True)
    os.chmod(gnupg, 0o700)
    conf = gnupg / "gpg-agent.conf"
    try:
        lines = conf.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    if "no-allow-external-cache" not in lines:
        lines.append("no-allow-external-cache")
        conf.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(conf, 0o600)
    subprocess.run(["gpgconf", "--reload", "gpg-agent"], capture_output=True, env=gpg_env())


def list_wasd_keys():
    proc = subprocess.run(
        ["gpg", "--batch", "--pinentry-mode", "cancel", "--with-colons", "--list-secret-keys"],
        capture_output=True,
        text=True,
        env=gpg_env(),
    )
    found = []
    current = None
    saw_uid = False
    for line in (proc.stdout or "").splitlines():
        parts = line.split(":")
        tag = parts[0] if parts else ""
        if tag == "sec":
            current = {"fpr": None, "ours": False}
            saw_uid = False
            found.append(current)
        elif tag == "fpr" and current is not None and current["fpr"] is None and not saw_uid:
            candidate = parts[9] if len(parts) > 9 else ""
            if FINGERPRINT.fullmatch(candidate):
                current["fpr"] = candidate
        elif tag == "uid" and current is not None:
            saw_uid = True
            uid = parts[9] if len(parts) > 9 else ""
            if "(wasd-wallet)" in uid:
                current["ours"] = True
        elif tag == "ssb":
            saw_uid = True
    return [item for item in found if item["ours"] and item["fpr"]]


def trust_key(fingerprint):
    subprocess.run(
        ["gpg", "--batch", "--import-ownertrust"],
        input=f"{fingerprint}:6:\n",
        capture_output=True,
        text=True,
        env=gpg_env(),
    )


def ensure_key():
    found = list_wasd_keys()
    if len(found) > 1:
        return None
    if len(found) == 1:
        trust_key(found[0]["fpr"])
        return found[0]["fpr"]
    handle = -1
    path = None
    try:
        handle, path = tempfile.mkstemp(prefix="wasd-wallet-", dir=str(Path.home()))
        os.chmod(path, 0o600)
        os.write(handle, BATCH)
        os.close(handle)
        handle = -1
        proc = subprocess.run(
            ["gpg", "--batch", "--pinentry-mode", "loopback", "--generate-key", path],
            capture_output=True,
            env=gpg_env(),
        )
        if proc.returncode != 0:
            return None
    finally:
        if handle >= 0:
            os.close(handle)
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass
    found = list_wasd_keys()
    if len(found) != 1:
        return None
    trust_key(found[0]["fpr"])
    return found[0]["fpr"]


def wallet_is_ours(kind, fingerprint):
    if file_matches(kind, fingerprint):
        return True
    if kind != "gpg" or not fingerprint:
        return False
    found = list_wasd_keys()
    if len(found) == 1 and found[0]["fpr"].lower() == fingerprint.lower():
        write_fpr_file(found[0]["fpr"])
        return True
    return False


def parse_kind(text):
    line = ""
    for item in (text or "").splitlines():
        if item.strip():
            line = item.strip()
    if line == "missing":
        return "missing", None
    if line == "blowfish":
        return "blowfish", None
    if line == "gpg":
        return "gpg", None
    if line.startswith("gpg "):
        fingerprint = line.split(" ", 1)[1].strip()
        if FINGERPRINT.fullmatch(fingerprint):
            return "gpg", fingerprint
        return "gpg", None
    if line == "other":
        return "other", None
    return None, None


def run_file(action, fingerprint):
    proc = subprocess.run(command_for(action, fingerprint), capture_output=True)
    return proc.returncode


def apply():
    agent_ready()
    for _attempt in (1, 2):
        kind_proc = subprocess.run(command_for("kind"), capture_output=True, text=True)
        if kind_proc.returncode != 0:
            return 1
        kind, fingerprint = parse_kind(kind_proc.stdout)
        if kind is None:
            return 1
        ours = wallet_is_ours(kind, fingerprint)
        action = decide(kind)
        if action == "skip":
            if ours:
                run_file("open-gpg", None)
            return 0
        if action == "create-gpg":
            made = ensure_key()
            if not made:
                return 1
            code = run_file("create-gpg", made)
            if code == 4 and _attempt == 1:
                continue
            if code != 0:
                return 1
            write_fpr_file(made)
            return 0
        return 1
    return 1


def self_check():
    cases = (
        ("missing", "create-gpg"),
        ("gpg", "skip"),
        ("blowfish", "skip"),
        ("other", "skip"),
    )
    for kind, expected in cases:
        got = decide(kind)
        if got != expected:
            raise SystemExit(f"decide {kind} returned {got}")
    commands = (
        command_for("kind"),
        command_for("create-gpg", "a" * 40),
        command_for("open-gpg"),
    )
    for argv in commands:
        if "wasd-wallet-file" not in argv[0]:
            raise SystemExit("the wallet file helper was left out")
    create = command_for("create-gpg", "c" * 40)
    if create[1:] != ["create-gpg", "c" * 40]:
        raise SystemExit("creating a wallet takes more than the fingerprint")
    main_source = inspect.getsource(main)
    if "WASD_SELF_CHECK" not in main_source or "apply(" not in main_source:
        raise SystemExit("self-check could set up a wallet")
    if '"--lock"' in main_source:
        raise SystemExit("a password would create a wallet")
    banned = ("subprocess", "apply", "run_file", "ensure_key", "agent_ready")
    if any(name in self_check.__code__.co_names for name in banned):
        raise SystemExit("self-check calls a program")
    previous = os.environ.get("HOME")
    temp = tempfile.mkdtemp(prefix="wasd-wallet-self-")
    try:
        os.environ["HOME"] = temp
        loose = fpr_path()
        loose.parent.mkdir(parents=True, exist_ok=True)
        loose.write_text("ab" * 20 + "\n", encoding="utf-8")
        os.chmod(loose, 0o644)
        if read_fpr_file() is not None:
            raise SystemExit("a shared fingerprint file was accepted")
        os.chmod(loose, 0o600)
        if not file_matches("gpg", "AB" * 20):
            raise SystemExit("the fingerprint comparison was case-sensitive")
        if file_matches("blowfish", "ab" * 20):
            raise SystemExit("another wallet was treated as ours")
        if file_matches("gpg", "cd" * 20):
            raise SystemExit("a different fingerprint matched")
    finally:
        if previous is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = previous
        import shutil

        shutil.rmtree(temp)
    print("wallet self-check ok")


def main():
    if "--self-check" in sys.argv:
        self_check()
        return 0
    if os.environ.get("WASD_SELF_CHECK") == "1":
        print("self-check tried to set up the wallet", file=sys.stderr)
        return 1
    if "--gpg" in sys.argv:
        if apply() != 0:
            print(WALLET_NOT_SET, file=sys.stderr)
            return 1
        return 0
    print("This is only used by Completing the install.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
