#!/usr/bin/env python3
"""Erase one disk on a live USB and install WASD.

--render prints a kickstart and does not touch a disk.
--install refuses unless this is a live USB, then hands that kickstart to
the existing installer. The password is not written into the kickstart.
Anaconda keeps a copy of the kickstart on the installed disk.
"""

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/usr/libexec")

from disks import DEVICE_NAME, display_name, is_live, live_disk_names  # noqa: E402

HOST_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
USER_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
FILE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
LANG_NAME = re.compile(r"^[A-Za-z0-9_.@-]+$")
KEYMAP_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
ZONE_NAME = re.compile(r"^[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)+$|^UTC$")
CHOICES_END = "WASD_CHOICES_END"


class Refuse(Exception):
    pass


def load_choices(payload):
    text = payload
    if payload and not payload.lstrip().startswith("{"):
        try:
            text = base64.b64decode(payload, validate=True).decode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise Refuse("The choices could not be read. Nothing was erased.") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise Refuse("The choices could not be read. Nothing was erased.") from exc
    if not isinstance(data, dict):
        raise Refuse("The choices could not be read. Nothing was erased.")
    if not isinstance(data.get("password"), bool):
        raise Refuse("The choice file must not contain a password. Nothing was erased.")
    user = data.get("user") or ""
    hostname = data.get("hostname") or ""
    device = data.get("device") or ""
    avatar = data.get("avatar") or ""
    disk_name = data.get("disk") or ""
    if not USER_NAME.fullmatch(user) or user == "root":
        raise Refuse("Choose a username first. Nothing was erased.")
    if not HOST_NAME.fullmatch(hostname):
        raise Refuse("Give the computer a usable name. Nothing was erased.")
    if not DEVICE_NAME.fullmatch(device):
        raise Refuse("Choose a disk again. Nothing was erased.")
    if avatar and not FILE_NAME.fullmatch(avatar):
        raise Refuse("Choose a picture again. Nothing was erased.")
    if not disk_name or "\n" in disk_name:
        raise Refuse("Choose a disk again. Nothing was erased.")
    encoded = json.dumps(data, indent=2)
    if CHOICES_END in encoded:
        raise Refuse("The choices could not be saved. Nothing was erased.")
    return data, encoded


def filtered_defaults(text):
    kept = []
    for line in text.splitlines():
        if re.match(r"^\s*user\b", line):
            continue
        if re.search(r"--password\b", line):
            continue
        kept.append(line)
    body = "\n".join(kept).strip()
    if "ostreecontainer" not in body:
        raise Refuse("The live installer defaults have no image. Nothing was erased.")
    if re.search(r"^\s*user\b", body, re.M) or "--password" in body:
        raise Refuse("The installer defaults still contain an account password. Nothing was erased.")
    return body + "\n"


def locale_bits():
    lang = "en_US.UTF-8"
    locale = Path("/etc/locale.conf")
    if locale.is_file():
        for line in locale.read_text(errors="replace").splitlines():
            if line.startswith("LANG="):
                value = line.split("=", 1)[1].strip().strip('"')
                if LANG_NAME.fullmatch(value):
                    lang = value
    keymap = "us"
    vconsole = Path("/etc/vconsole.conf")
    if vconsole.is_file():
        for line in vconsole.read_text(errors="replace").splitlines():
            if line.startswith("KEYMAP="):
                value = line.split("=", 1)[1].strip().strip('"')
                if KEYMAP_NAME.fullmatch(value):
                    keymap = value
    zone = "UTC"
    localtime = Path("/etc/localtime")
    try:
        target = os.readlink(localtime) if localtime.is_symlink() else ""
    except OSError:
        target = ""
    if "zoneinfo/" in target:
        value = target.split("zoneinfo/", 1)[1]
        if ZONE_NAME.fullmatch(value):
            zone = value
    return lang, keymap, zone


def render_kickstart(data, choices_text, defaults_text):
    user = data["user"]
    hostname = data["hostname"]
    device = data["device"]
    avatar = data["avatar"]
    lang, keymap, zone = locale_bits()
    defaults = filtered_defaults(defaults_text)
    # The account is locked here. The post script clears that lock so the
    # first boot signs in with no password. The chosen password is typed
    # after install and is not part of this file.
    return f"""# WASD install for this boot. The account password is not in this file.
lang {lang}
keyboard {keymap}
timezone {zone} --utc
network --bootproto=dhcp --device=link --activate --onboot=yes --hostname={hostname}
rootpw --lock
ignoredisk --only-use={device}
clearpart --all --initlabel --disklabel=gpt --drives={device}
autopart --type=btrfs
bootloader --location=mbr --boot-drive={device}
user --name={user} --groups=wheel --lock

{defaults}
%post --erroronfail --log=/tmp/anacoda_custom_logs/wasd-account.log
set -euo pipefail
target_user={user}
if ! id "$target_user" >/dev/null 2>&1; then
    useradd -m -G wheel "$target_user"
fi
passwd -d "$target_user"
install -d -m 0755 /etc/wasd /etc/plasmalogin.conf.d /etc/sddm.conf.d
cat > /etc/plasmalogin.conf.d/zz-wasd-autologin.conf << 'EOF'
[Autologin]
User={user}
Session=plasma
Relogin=false
EOF
cp /etc/plasmalogin.conf.d/zz-wasd-autologin.conf /etc/sddm.conf.d/zz-wasd-autologin.conf
cat > /etc/wasd/choices.json << '{CHOICES_END}'
{choices_text}
{CHOICES_END}
chmod 0644 /etc/wasd/choices.json
home=$(getent passwd "$target_user" | cut -d: -f6)
if [ -z "$home" ]; then
    echo "The account has no home directory." >&2
    exit 1
fi
install -d -m 0755 -o "$target_user" -g "$target_user" "$home/.config/autostart"
cat > "$home/.config/autostart/wasd-complete.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=Completing the install
Exec=/usr/bin/wasd-complete
X-GNOME-Autostart-enabled=true
OnlyShowIn=KDE;
EOF
chown "$target_user:$target_user" "$home/.config/autostart/wasd-complete.desktop"
icon=/usr/share/wasd/icons/{avatar}
if [ -n "{avatar}" ] && [ -f "$icon" ]; then
    install -d -m 0755 /var/lib/AccountsService/icons /var/lib/AccountsService/users
    install -m 0644 "$icon" "/var/lib/AccountsService/icons/$target_user"
    printf '%s\\n' '[User]' "Icon=/var/lib/AccountsService/icons/$target_user" 'SystemAccount=false' > "/var/lib/AccountsService/users/$target_user"
    install -m 0644 "$icon" "$home/.face"
    chown "$target_user:$target_user" "$home/.face"
fi
%end

%post --nochroot --log=/tmp/anacoda_custom_logs/wasd-network.log
set -u
src=/etc/NetworkManager/system-connections
if [ -d "$src" ] && [ -n "$(ls -A "$src" 2>/dev/null || true)" ]; then
    deployment=$(ostree rev-parse --repo=/mnt/sysimage/ostree/repo ostree/0/1/0 || true)
    if [ -n "$deployment" ]; then
        dest="/mnt/sysimage/ostree/deploy/default/deploy/${{deployment}}.0/etc/NetworkManager/system-connections"
        mkdir -p "$dest"
        cp -a "$src"/. "$dest"/ || true
        chmod 0700 "$dest" || true
        find "$dest" -type f -exec chmod 0600 {{}} + || true
    fi
fi
%end

reboot
"""


def assert_disk_matches(data, lsblk_payload):
    device = data["device"]
    banned = live_disk_names(lsblk_payload)
    if device in banned:
        raise Refuse("That disk is the live USB. Nothing was erased.")
    found = None
    blob = json.loads(lsblk_payload) if isinstance(lsblk_payload, str) else lsblk_payload
    for dev in blob.get("blockdevices") or []:
        if dev.get("type") == "disk" and dev.get("name") == device:
            found = dev
            break
    if found is None:
        raise Refuse("That disk is not on this computer. Nothing was erased.")
    shown = display_name(found.get("model"), device)
    if shown != data["disk"] and data["disk"] != device:
        raise Refuse("The selected disk does not match. Nothing was erased.")


def read_defaults(path):
    file = Path(path)
    if not file.is_file():
        raise Refuse("The live installer defaults are missing. Nothing was erased.")
    return file.read_text(errors="replace")


def current_lsblk():
    import subprocess

    result = subprocess.run(
        ["lsblk", "-J", "-o", "NAME,TYPE,MODEL,LABEL,MOUNTPOINTS,PKNAME"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def self_check():
    defaults = """ostreecontainer --url=example:latest --transport=containers-storage --no-signature-verification
user --name=bazzite --password=bazzite --plaintext --groups=wheel
%include /usr/share/anaconda/post-scripts/install-configure-upgrade.ks
"""
    choices = {
        "disk": "Samsung SSD 990 PRO",
        "device": "nvme0n1",
        "hostname": "wasd",
        "user": "alex",
        "avatar": "knight.jpg",
        "password": True,
        "apps": [],
        "agents": [],
    }
    payload = base64.b64encode(json.dumps(choices).encode()).decode()
    data, text = load_choices(payload)
    kick = render_kickstart(data, text, defaults)
    for needle in (
        "ignoredisk --only-use=nvme0n1",
        "clearpart --all --initlabel --disklabel=gpt --drives=nvme0n1",
        "user --name=alex --groups=wheel --lock",
        "passwd -d",
        "ostreecontainer --url=example:latest",
        '"password": true',
        "[Autologin]",
        "Session=plasma",
    ):
        if needle not in kick:
            raise SystemExit(f"kickstart missing {needle}")
    if "icons/knight.jpg" not in kick:
        raise SystemExit("kickstart missed the account picture")
    if "system-connections" not in kick or "${deployment}" not in kick or "chmod 0600 {}" not in kick:
        raise SystemExit("the network copy was wrong")
    if "wpakey" in kick or "passphrase" in kick:
        raise SystemExit("the network copy was wrong")
    if "name=bazzite" in kick or "--password" in kick or "password=bazzite" in kick:
        raise SystemExit("kickstart kept a password or the default account")
    empty = dict(choices)
    empty["avatar"] = ""
    empty_data, empty_text = load_choices(json.dumps(empty))
    empty_kick = render_kickstart(empty_data, empty_text, defaults)
    if "icons/knight.jpg" in empty_kick or '[ -n "" ]' not in empty_kick:
        raise SystemExit("an empty account picture was still installed")
    if "not-stored" in kick:
        raise SystemExit("kickstart kept a secret")
    try:
        load_choices(json.dumps({"password": "secret", "user": "alex", "device": "nvme0n1", "hostname": "wasd", "avatar": "knight.jpg", "disk": "Disk"}))
    except Refuse:
        pass
    else:
        raise SystemExit("a password string was accepted")
    lsblk = {
        "blockdevices": [
            {
                "name": "sda",
                "type": "disk",
                "model": "Live USB",
                "children": [{"name": "sda1", "type": "part", "label": "WASD", "mountpoints": ["/run/initramfs/live"]}],
            },
            {"name": "nvme0n1", "type": "disk", "model": "Samsung SSD 990 PRO", "children": []},
        ]
    }
    assert_disk_matches(data, lsblk)
    bad = dict(choices)
    bad["device"] = "sda"
    bad["disk"] = "Live USB"
    try:
        assert_disk_matches(bad, lsblk)
    except Refuse:
        pass
    else:
        raise SystemExit("the live USB was accepted")
    from disks import self_check as disks_check

    disks_check()
    print("erase self-check ok")


def main():
    parser = argparse.ArgumentParser(description="Install WASD onto the selected disk")
    parser.add_argument("--render", action="store_true", help="Print the kickstart and do not install")
    parser.add_argument("--install", action="store_true", help="Start the install on a live USB")
    parser.add_argument("--self-check", action="store_true", help="Check the kickstart rules without a disk")
    parser.add_argument("--defaults", default="/usr/share/anaconda/interactive-defaults.ks")
    parser.add_argument("payload", nargs="?", help="Choice JSON, or its base64")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return 0
    if args.render:
        try:
            data, text = load_choices(args.payload or "")
            kick = render_kickstart(data, text, read_defaults(args.defaults))
        except Refuse as exc:
            print(str(exc), file=sys.stderr)
            return 1
        sys.stdout.write(kick)
        return 0
    if not args.install:
        print("Nothing was erased.", file=sys.stderr)
        return 2
    if not is_live():
        print("This is not a live USB. Nothing was erased.", file=sys.stderr)
        return 1
    try:
        data, text = load_choices(args.payload or "")
        assert_disk_matches(data, current_lsblk())
        kick = render_kickstart(data, text, read_defaults(args.defaults))
    except Refuse as exc:
        print(str(exc), file=sys.stderr)
        return 1
    path = Path("/run/wasd-install.ks")
    path.write_text(kick)
    os.chmod(path, 0o600)
    os.execvp("liveinst", ["liveinst", "--kickstart", str(path)])


if __name__ == "__main__":
    raise SystemExit(main())
