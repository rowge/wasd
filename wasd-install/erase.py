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

from agents import agents_problem  # noqa: E402
from disks import DEVICE_NAME, display_name, is_live, live_disk_names, parse_disks  # noqa: E402
from lookapply import look_problem  # noqa: E402
from network import validate_tcp  # noqa: E402
from windowsboot import windows_post  # noqa: E402

HOST_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
USER_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
FILE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
LANG_NAME = re.compile(r"^[A-Za-z0-9_.@-]+$")
KEYMAP_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
ZONE_NAME = re.compile(r"^[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)+$|^UTC$")
PART_NAME = re.compile(r"^(nvme[0-9]+n[0-9]+p[0-9]+|sd[a-z]+[0-9]+|vd[a-z]+[0-9]+|mmcblk[0-9]+p[0-9]+|hd[a-z]+[0-9]+)$")
UUID_NAME = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
KEEP_FS = {"btrfs", "ext4", "xfs", "ntfs", "exfat"}
CHOICES_END = "WASD_CHOICES_END"
SECRET_KEYS = {"passphrase", "wpakey", "psk"}
WIFI_SECURITY = re.compile(r"[A-Za-z0-9 ._+-]*")
MIN_OS_GB = 64
MIN_GAMES_GB = 32
OVERHEAD_GB = 4


class Refuse(Exception):
    pass


def reject_secrets(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in SECRET_KEYS:
                raise Refuse("The choice file must not contain a passphrase. Nothing was erased.")
            if str(key).lower() == "password" and not isinstance(item, bool):
                raise Refuse("The choice file must not contain a password. Nothing was erased.")
            reject_secrets(item)
    elif isinstance(value, list):
        for item in value:
            reject_secrets(item)


def checked_wifi(data):
    if "wifi" not in data:
        return
    wifi = data["wifi"]
    if not isinstance(wifi, dict) or any(key not in {"ssid", "security", "hidden"} for key in wifi):
        raise Refuse("The choice file must not contain a passphrase. Nothing was erased.")
    ssid = wifi.get("ssid") or ""
    security = wifi.get("security") or ""
    hidden = wifi.get("hidden", False)
    if (
        not isinstance(ssid, str)
        or not ssid.strip()
        or ssid.startswith("-")
        or "\n" in ssid
        or "\x00" in ssid
        or len(ssid) > 32
    ):
        raise Refuse("Choose the network again. Nothing was erased.")
    if not isinstance(security, str) or not WIFI_SECURITY.fullmatch(security) or len(security) > 64:
        raise Refuse("Choose the network again. Nothing was erased.")
    if not isinstance(hidden, bool):
        raise Refuse("Choose the network again. Nothing was erased.")


def checked_tcp(data):
    if "tcp" not in data:
        return
    tcp = data["tcp"]
    allowed = {"mode", "interface", "kind", "address", "netmask", "gateway", "dns"}
    if not isinstance(tcp, dict) or set(tcp) != allowed or tcp.get("mode") != "manual":
        raise Refuse("Choose the adapter again. Nothing was erased.")
    if tcp.get("kind") not in {"wifi", "ethernet"} or validate_tcp(tcp):
        raise Refuse("Choose the adapter again. Nothing was erased.")


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
    reject_secrets(data)
    checked_wifi(data)
    checked_tcp(data)
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
    problem = look_problem(data)
    if problem:
        raise Refuse(problem)
    problem = agents_problem(data)
    if problem:
        raise Refuse(problem)
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


def plain_int(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def first_partition(device):
    if device.startswith(("nvme", "mmcblk")):
        return device + "p1"
    return device + "1"


def games_plan(data, os_device):
    raw = data.get("games")
    if not raw:
        return {"mode": "off"}
    if not isinstance(raw, dict):
        raise Refuse("The games choice could not be read. Nothing was erased.")
    mode = raw.get("mode") or "off"
    if mode == "off":
        return {"mode": "off"}
    if mode == "split":
        os_gb = plain_int(raw.get("osGb"))
        games_gb = plain_int(raw.get("gamesGb"))
        total = plain_int(raw.get("bytes"))
        if os_gb is None or games_gb is None:
            raise Refuse("Set the size for WASD and for games. Nothing was erased.")
        if os_gb < MIN_OS_GB or games_gb < MIN_GAMES_GB:
            raise Refuse("Leave at least 64 GB for WASD and 32 GB for games. Nothing was erased.")
        if total is not None and os_gb + games_gb > (total // (1024 ** 3)) - OVERHEAD_GB:
            raise Refuse("Those sizes do not fit on the selected drive. Nothing was erased.")
        return {"mode": "split", "osGb": os_gb, "gamesGb": games_gb}
    device = raw.get("device") or ""
    disk_name = raw.get("disk") or ""
    if mode not in {"keep", "format"} or not DEVICE_NAME.fullmatch(device) or device == os_device:
        raise Refuse("Choose the games drive again. Nothing was erased.")
    if not disk_name or "\n" in disk_name or len(disk_name) > 80:
        raise Refuse("Choose the games drive again. Nothing was erased.")
    confirmed = raw.get("confirmed") is True
    if mode == "format":
        return {
            "mode": "format",
            "device": device,
            "disk": disk_name,
            "part": first_partition(device),
            "confirmed": confirmed,
        }
    part = raw.get("part") or ""
    fstype = str(raw.get("fstype") or "").lower()
    uuid = raw.get("uuid") or ""
    if not PART_NAME.fullmatch(part) or not part.startswith(device) or fstype not in KEEP_FS or not UUID_NAME.fullmatch(uuid):
        raise Refuse("Choose the games drive again. Nothing was erased.")
    mount_fs = "ntfs3" if fstype == "ntfs" else fstype
    return {
        "mode": "keep",
        "device": device,
        "disk": disk_name,
        "part": part,
        "fstype": mount_fs,
        "uuid": uuid,
        "confirmed": confirmed,
    }


def wipe_plan(data, os_device, games_device):
    raw = data.get("wipe")
    if not raw:
        return []
    if not isinstance(raw, list):
        raise Refuse("The wipe choice could not be read. Nothing was erased.")
    plans = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict) or item.get("confirmed") is not True:
            raise Refuse("Confirm that wipe again. Nothing was erased.")
        device = item.get("device") or ""
        disk_name = item.get("disk") or ""
        if (
            not DEVICE_NAME.fullmatch(device)
            or device in {os_device, games_device}
            or device in seen
        ):
            raise Refuse("Choose that drive again. Nothing was erased.")
        if not disk_name or "\n" in disk_name or len(disk_name) > 80:
            raise Refuse("Choose that drive again. Nothing was erased.")
        seen.add(device)
        plans.append({"device": device, "disk": disk_name})
    return plans


def wipe_post(plans):
    if not plans:
        return ""
    commands = []
    for item in plans:
        device = item["device"]
        commands.append(
            f'wipefs -a "/dev/{device}"\n'
            f"printf '%s\\n' 'label: gpt' | sfdisk --wipe always \"/dev/{device}\"\n"
            f'partprobe "/dev/{device}" || true'
        )
    body = "\n".join(commands)
    return f"""
%post --nochroot --erroronfail --log=/tmp/anacoda_custom_logs/wasd-wipe.log
set -eu
{body}
%end
"""


def storage_lines(device, plan):
    if plan["mode"] != "split":
        return (
            f"ignoredisk --only-use={device}\n"
            f"clearpart --all --initlabel --disklabel=gpt --drives={device}\n"
            "autopart --type=btrfs\n"
            f"bootloader --location=mbr --boot-drive={device}"
        )
    os_mib = plan["osGb"] * 1024
    return (
        f"ignoredisk --only-use={device}\n"
        f"clearpart --all --initlabel --disklabel=gpt --drives={device}\n"
        "reqpart --add-boot\n"
        f"part / --fstype=btrfs --size={os_mib} --ondisk={device} --label=wasd\n"
        f"part /games --fstype=btrfs --size=1024 --grow --ondisk={device} --label=games\n"
        f"bootloader --location=mbr --boot-drive={device}"
    )


def games_post(plan):
    if plan["mode"] == "off":
        return ""
    if plan["mode"] == "split":
        return """
%post --nochroot --log=/tmp/anacoda_custom_logs/wasd-games.log
set -u
if [ -d /mnt/sysimage/games ]; then
    mkdir -p /mnt/sysimage/games/SteamLibrary/steamapps || true
fi
%end
"""
    mount_fs = "btrfs" if plan["mode"] == "format" else plan["fstype"]
    uuid = plan.get("uuid") or ""
    prepare = ""
    if plan["mode"] == "format":
        prepare = f"""
dev={plan["device"]}
part={plan["part"]}
wipefs -a "/dev/$dev"
printf '%s\\n' 'label: gpt' ', type=linux, name=games' | sfdisk --wipe always "/dev/$dev"
partprobe "/dev/$dev" || true
udevadm settle || sleep 2
mkfs.btrfs -f -L games "/dev/$part"
uuid=$(blkid -s UUID -o value "/dev/$part")
"""
    else:
        prepare = f"""
part={plan["part"]}
uuid=$(blkid -s UUID -o value "/dev/$part")
if [ "$uuid" != "{uuid}" ]; then
    echo "The games drive changed." >&2
    exit 1
fi
"""
    return f"""
%post --nochroot --erroronfail --log=/tmp/anacoda_custom_logs/wasd-games.log
set -eu
{prepare}
if [ -z "$uuid" ]; then
    echo "The games drive has no id." >&2
    exit 1
fi
deployment=$(ostree rev-parse --repo=/mnt/sysimage/ostree/repo ostree/0/1/0 || true)
fstab=/mnt/sysimage/etc/fstab
if [ -n "$deployment" ]; then
    alt="/mnt/sysimage/ostree/deploy/default/deploy/${{deployment}}.0/etc/fstab"
    if [ -f "$alt" ]; then
        fstab=$alt
    fi
fi
if ! grep -q ' /games ' "$fstab"; then
    printf '%s\\n' "UUID=$uuid /games {mount_fs} defaults,nofail 0 0" >> "$fstab"
fi
mkdir -p /run/wasd-games
mount -t {mount_fs} "UUID=$uuid" /run/wasd-games
mkdir -p /run/wasd-games/SteamLibrary/steamapps
umount /run/wasd-games
%end
"""


def render_kickstart(data, choices_text, defaults_text):
    user = data["user"]
    hostname = data["hostname"]
    device = data["device"]
    avatar = data["avatar"]
    lang, keymap, zone = locale_bits()
    defaults = filtered_defaults(defaults_text)
    plan = games_plan(data, device)
    games_device = plan.get("device") or ""
    wiped = wipe_plan(data, device, games_device)
    storage = storage_lines(device, plan)
    games = games_post(plan)
    emptied = wipe_post(wiped)
    windows = windows_post(device, plan, wiped)
    # The account is locked here. The post script clears that lock so the
    # first boot signs in with no password. The chosen password is typed
    # after install and is not part of this file.
    return f"""# WASD install for this boot. The account password is not in this file.
lang {lang}
keyboard {keymap}
timezone {zone} --utc
network --bootproto=dhcp --device=link --activate --onboot=yes --hostname={hostname}
rootpw --lock
{storage}
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
install -d -m 0755 -o "$target_user" -g "$target_user" "$home/Desktop"
cat > "$home/Desktop/wasd-complete.desktop" << 'EOF'
[Desktop Entry]
Type=Application
Name=Completing the install
Comment=Finish setting up this computer
Exec=/usr/bin/wasd-complete
Icon=wasd-logo
Terminal=false
EOF
chown "$target_user:$target_user" "$home/Desktop/wasd-complete.desktop"
chmod 0755 "$home/Desktop/wasd-complete.desktop"
icon=/usr/share/wasd/icons/{avatar}
if [ -n "{avatar}" ] && [ -f "$icon" ]; then
    install -d -m 0755 /var/lib/AccountsService/icons /var/lib/AccountsService/users
    install -m 0644 "$icon" "/var/lib/AccountsService/icons/$target_user"
    printf '%s\\n' '[User]' "Icon=/var/lib/AccountsService/icons/$target_user" 'SystemAccount=false' > "/var/lib/AccountsService/users/$target_user"
    install -m 0644 "$icon" "$home/.face"
    chown "$target_user:$target_user" "$home/.face"
fi
if [ -x /usr/libexec/wasd-apply-choices ]; then
    if ! /usr/libexec/wasd-apply-choices --choices /etc/wasd/choices.json --user "$target_user" --rebuild --no-mark; then
        echo "The look choices were saved. The first boot will apply them." >&2
    fi
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
{games}
{emptied}
{windows}
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


def assert_games_matches(data, lsblk_payload):
    plan = games_plan(data, data["device"])
    if plan["mode"] == "off":
        return
    blob = json.loads(lsblk_payload) if isinstance(lsblk_payload, str) else lsblk_payload
    rows = parse_disks(blob)
    if plan["mode"] == "split":
        found = next((row for row in rows if row["device"] == data["device"]), None)
        if found is None:
            raise Refuse("That disk is not on this computer. Nothing was erased.")
        real = found.get("bytes") or 0
        if real and plan["osGb"] + plan["gamesGb"] > (real // (1024 ** 3)) - OVERHEAD_GB:
            raise Refuse("Those sizes do not fit on the selected drive. Nothing was erased.")
        return
    if plan["device"] in live_disk_names(blob):
        raise Refuse("That disk is the live USB. Nothing was erased.")
    found = next((row for row in rows if row["device"] == plan["device"]), None)
    if found is None:
        raise Refuse("That games drive is not on this computer. Nothing was erased.")
    if found["name"] != plan["disk"] and plan["disk"] != plan["device"]:
        raise Refuse("The games drive does not match. Nothing was erased.")
    if found["windows"] and not plan.get("confirmed"):
        raise Refuse("The Windows drive stays. Nothing was erased.")
    if plan["mode"] == "format":
        if (found["occupied"] or found["games"]) and not plan.get("confirmed"):
            raise Refuse("That drive is not empty. Nothing was erased.")
        return
    if found["part"] != plan["part"] or not found.get("uuid") or found["uuid"].lower() != plan["uuid"].lower():
        raise Refuse("Choose the games drive again. Nothing was erased.")


def assert_wipe_matches(data, lsblk_payload):
    blob = json.loads(lsblk_payload) if isinstance(lsblk_payload, str) else lsblk_payload
    plan = games_plan(data, data["device"])
    wiped = wipe_plan(data, data["device"], plan.get("device") or "")
    if not wiped:
        return
    rows = parse_disks(blob)
    banned = live_disk_names(blob)
    for item in wiped:
        if item["device"] in banned:
            raise Refuse("That disk is the live USB. Nothing was erased.")
        found = next((row for row in rows if row["device"] == item["device"]), None)
        if found is None:
            raise Refuse("That disk is not on this computer. Nothing was erased.")
        if found["name"] != item["disk"] and item["disk"] != item["device"]:
            raise Refuse("The selected disk does not match. Nothing was erased.")


def current_lsblk():
    import subprocess

    result = subprocess.run(
        ["lsblk", "-J", "-b", "-o", "NAME,SIZE,MODEL,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,PKNAME"],
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
        "Desktop/wasd-complete.desktop",
        "Name=Completing the install",
        "Icon=wasd-logo",
        "/usr/libexec/wasd-apply-choices",
        "--no-mark",
        "The look choices were saved. The first boot will apply them.",
        "/usr/libexec/wasd-windows-boot --root /mnt/sysimage --skip nvme0n1",
    ):
        if needle not in kick:
            raise SystemExit(f"kickstart missing {needle}")
    if "icons/knight.jpg" not in kick:
        raise SystemExit("kickstart missed the account picture")
    if "autopart --type=btrfs" not in kick or "part /games" in kick:
        raise SystemExit("the default install changed the disk layout")
    if "system-connections" not in kick or "${deployment}" not in kick or "chmod 0600 {}" not in kick:
        raise SystemExit("the network copy was wrong")
    if "wpakey" in kick or "passphrase" in kick:
        raise SystemExit("the network copy was wrong")
    if "name=bazzite" in kick or "--password" in kick or "password=bazzite" in kick:
        raise SystemExit("kickstart kept a password or the default account")
    if "grub2-mkconfig" in kick or "os-prober" in kick:
        raise SystemExit("the windows menu rewrites the bootloader")
    formatted = dict(choices)
    formatted["games"] = {"mode": "format", "device": "nvme1n1", "disk": "WD Black", "confirmed": True}
    format_data, format_text = load_choices(json.dumps(formatted))
    format_kick = render_kickstart(format_data, format_text, defaults)
    if "--skip nvme0n1 --skip nvme1n1" not in format_kick:
        raise SystemExit("a formatted games drive stayed eligible for the windows menu")
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
    saved_net = dict(choices)
    saved_net["wifi"] = {"ssid": "Home", "security": "WPA2", "hidden": False}
    net_data, net_text = load_choices(json.dumps(saved_net))
    net_kick = render_kickstart(net_data, net_text, defaults)
    if '"ssid": "Home"' not in net_kick or '"security": "WPA2"' not in net_kick:
        raise SystemExit("the saved network was not kept")
    if "passphrase" in net_text or "wpakey" in net_text or '"psk"' in net_text:
        raise SystemExit("the saved network kept a passphrase")
    try:
        leaked = dict(choices)
        leaked["wifi"] = {"ssid": "Home", "security": "WPA2", "hidden": False, "passphrase": "secret"}
        load_choices(json.dumps(leaked))
    except Refuse:
        pass
    else:
        raise SystemExit("a wifi passphrase was accepted")
    try:
        dashed = dict(choices)
        dashed["wifi"] = {"ssid": "-Home", "security": "", "hidden": True}
        load_choices(json.dumps(dashed))
    except Refuse:
        pass
    else:
        raise SystemExit("a network name starting with a dash was accepted")
    saved_tcp = dict(choices)
    saved_tcp["tcp"] = {
        "mode": "manual",
        "interface": "enp4s0",
        "kind": "ethernet",
        "address": "192.168.1.20",
        "netmask": "255.255.255.0",
        "gateway": "192.168.1.1",
        "dns": "1.1.1.1",
    }
    tcp_data, tcp_text = load_choices(json.dumps(saved_tcp))
    tcp_kick = render_kickstart(tcp_data, tcp_text, defaults)
    if '"interface": "enp4s0"' not in tcp_kick or '"address": "192.168.1.20"' not in tcp_kick:
        raise SystemExit("the saved address was not kept")
    if "passphrase" in tcp_text or "wpakey" in tcp_text or '"psk"' in tcp_text:
        raise SystemExit("the saved address kept a passphrase")
    for bad_tcp in (
        dict(saved_tcp["tcp"], address="192.168.1.999"),
        dict(saved_tcp["tcp"], interface="-enp4s0"),
        dict(saved_tcp["tcp"], interface="enp4s0;rm"),
        dict(saved_tcp["tcp"], kind="bridge"),
        dict(saved_tcp["tcp"], mode="auto"),
        dict(saved_tcp["tcp"], passphrase="secret"),
    ):
        try:
            refused = dict(choices)
            refused["tcp"] = bad_tcp
            load_choices(json.dumps(refused))
        except Refuse:
            pass
        else:
            raise SystemExit(f"a bad address was accepted {bad_tcp}")
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
    fit = games_plan(
        {"games": {"mode": "split", "osGb": 128, "gamesGb": 1730, "bytes": 2_000_000_000_000}},
        "nvme0n1",
    )
    if fit["osGb"] != 128 or fit["gamesGb"] != 1730:
        raise SystemExit(f"split sizes were changed {fit}")
    for bad_games in (
        {"mode": "split", "osGb": True, "gamesGb": 32, "bytes": 2_000_000_000_000},
        {"mode": "split", "osGb": 128, "gamesGb": 1731, "bytes": 2_000_000_000_000},
        {"mode": "split", "osGb": 32, "gamesGb": 32, "bytes": 2_000_000_000_000},
        {"mode": "keep", "device": "nvme0n1", "disk": "Same", "part": "nvme0n1p1", "fstype": "btrfs", "uuid": "12345678-1234-1234-1234-123456789abc"},
    ):
        try:
            games_plan({"games": bad_games}, "nvme0n1")
        except Refuse:
            pass
        else:
            raise SystemExit(f"games choice was accepted {bad_games}")
    split = dict(choices)
    split["games"] = {"mode": "split", "osGb": 128, "gamesGb": 1730, "bytes": 2_000_000_000_000}
    split_data, split_text = load_choices(json.dumps(split))
    split_kick = render_kickstart(split_data, split_text, defaults)
    if "autopart" in split_kick or "part /games" not in split_kick or "--label=games" not in split_kick:
        raise SystemExit("the split install did not keep the games space")
    if "--size=131072" not in split_kick or "reqpart --add-boot" not in split_kick:
        raise SystemExit("the split install missed the WASD size")
    keep = dict(choices)
    keep["games"] = {
        "mode": "keep",
        "device": "nvme1n1",
        "disk": "WD BLACK SN850X",
        "part": "nvme1n1p1",
        "fstype": "ntfs",
        "uuid": "12345678-1234-1234-1234-123456789abc",
    }
    keep_data, keep_text = load_choices(json.dumps(keep))
    keep_kick = render_kickstart(keep_data, keep_text, defaults)
    if "mkfs" in keep_kick or "12345678-1234-1234-1234-123456789abc" not in keep_kick or "ntfs3" not in keep_kick:
        raise SystemExit("keeping a games drive formatted it")
    if "autopart --type=btrfs" not in keep_kick or "ignoredisk --only-use=nvme0n1" not in keep_kick:
        raise SystemExit("keeping a games drive changed the WASD disk")
    if "part /games" in keep_kick or "clearpart" not in keep_kick.split("ignoredisk --only-use=nvme0n1", 1)[-1]:
        raise SystemExit("keeping a games drive partitioned the wrong disk")
    formatted = dict(choices)
    formatted["games"] = {"mode": "format", "device": "nvme3n1", "disk": "Empty Shelf"}
    format_data, format_text = load_choices(json.dumps(formatted))
    format_kick = render_kickstart(format_data, format_text, defaults)
    if "mkfs.btrfs -f -L games" not in format_kick or "/dev/$part" not in format_kick:
        raise SystemExit("an empty games drive was not formatted")
    if "autopart --type=btrfs" not in format_kick or "part /games" in format_kick:
        raise SystemExit("formatting a games drive changed the WASD disk")
    for kick_text in (kick, split_kick, keep_kick, format_kick):
        if "wpakey" in kick_text or "passphrase" in kick_text or "${deployment}" not in kick_text:
            raise SystemExit("a games kickstart was wrong")
    games_lsblk = {
        "blockdevices": [
            {
                "name": "sda",
                "type": "disk",
                "size": 16_000_000_000,
                "model": "Live USB",
                "children": [{"name": "sda1", "type": "part", "label": "WASD", "mountpoints": ["/run/initramfs/live"]}],
            },
            {"name": "nvme0n1", "type": "disk", "size": 2_000_000_000_000, "model": "Samsung SSD 990 PRO", "children": []},
            {
                "name": "nvme1n1",
                "type": "disk",
                "size": 1_000_000_000_000,
                "model": "WD_BLACK SN850X",
                "children": [{
                    "name": "nvme1n1p1",
                    "type": "part",
                    "fstype": "ntfs",
                    "label": "games",
                    "size": 999_000_000_000,
                    "uuid": "12345678-1234-1234-1234-123456789abc",
                }],
            },
            {
                "name": "nvme2n1",
                "type": "disk",
                "size": 1_000_000_000_000,
                "model": "Windows Disk",
                "children": [{"name": "nvme2n1p1", "type": "part", "fstype": "BitLocker"}],
            },
            {"name": "nvme3n1", "type": "disk", "size": 4_000_000_000_000, "model": "Empty Shelf", "children": []},
        ]
    }
    assert_games_matches(split_data, games_lsblk)
    assert_games_matches(keep_data, games_lsblk)
    assert_games_matches(format_data, games_lsblk)
    windows_games = dict(keep)
    windows_games["games"] = {
        "mode": "keep",
        "device": "nvme2n1",
        "disk": "Windows Disk",
        "part": "nvme2n1p1",
        "fstype": "ntfs",
        "uuid": "12345678-1234-1234-1234-123456789abc",
    }
    occupied = dict(formatted)
    occupied["games"] = {"mode": "format", "device": "nvme1n1", "disk": "WD BLACK SN850X"}
    usb_games = dict(formatted)
    usb_games["games"] = {"mode": "format", "device": "sda", "disk": "Live USB"}
    for refused, label in (
        (windows_games, "windows"),
        (occupied, "occupied"),
        (usb_games, "live usb"),
    ):
        try:
            assert_games_matches(refused, games_lsblk)
        except Refuse:
            pass
        else:
            raise SystemExit(f"the {label} games drive was accepted")
    forced = dict(formatted)
    forced["games"] = {
        "mode": "format",
        "device": "nvme2n1",
        "disk": "Windows Disk",
        "confirmed": True,
    }
    assert_games_matches(forced, games_lsblk)
    forced_kick = render_kickstart(forced, json.dumps(forced), defaults)
    if "dev=nvme2n1" not in forced_kick or "mkfs.btrfs -f -L games" not in forced_kick:
        raise SystemExit("a confirmed Windows games wipe was not formatted")
    if "ignoredisk --only-use=nvme0n1" not in forced_kick:
        raise SystemExit("a games wipe moved the WASD disk")
    windows_keep_blob = json.loads(json.dumps(games_lsblk))
    windows_keep_blob["blockdevices"][3]["children"] = [{
        "name": "nvme2n1p3",
        "type": "part",
        "fstype": "ntfs",
        "label": "Windows",
        "size": 900_000_000_000,
        "uuid": "abcdefab-1234-1234-1234-123456789abc",
    }]
    kept = dict(keep)
    kept["games"] = {
        "mode": "keep",
        "device": "nvme2n1",
        "disk": "Windows Disk",
        "part": "nvme2n1p3",
        "fstype": "ntfs",
        "uuid": "abcdefab-1234-1234-1234-123456789abc",
        "confirmed": True,
    }
    assert_games_matches(kept, windows_keep_blob)
    kept_kick = render_kickstart(kept, json.dumps(kept), defaults)
    if "ntfs3" not in kept_kick or "mkfs.btrfs -f -L games" in kept_kick:
        raise SystemExit("a confirmed Windows games drive was formatted")
    emptied = dict(choices)
    emptied["wipe"] = [{"device": "nvme3n1", "disk": "Empty Shelf", "confirmed": True}]
    assert_wipe_matches(emptied, games_lsblk)
    empty_kick = render_kickstart(emptied, json.dumps(emptied), defaults)
    if 'wipefs -a "/dev/nvme3n1"' not in empty_kick or "wasd-wipe.log" not in empty_kick:
        raise SystemExit("a leave-empty wipe did not erase the drive")
    wipe_tail = empty_kick.split("wasd-wipe.log", 1)[-1]
    if "mkfs.btrfs" in wipe_tail or "/games" in wipe_tail:
        raise SystemExit("a leave-empty wipe was used for games")
    if "ignoredisk --only-use=nvme0n1" not in empty_kick:
        raise SystemExit("leaving a drive empty changed the WASD disk")
    try:
        wipe_plan(dict(emptied, wipe=[{"device": "nvme0n1", "disk": "Samsung SSD 990 PRO", "confirmed": True}]), "nvme0n1", "")
    except Refuse:
        pass
    else:
        raise SystemExit("the install drive was wiped and left")
    try:
        wipe_plan(dict(emptied, wipe=[{"device": "nvme3n1", "disk": "Empty Shelf"}]), "nvme0n1", "")
    except Refuse:
        pass
    else:
        raise SystemExit("an unconfirmed wipe was accepted")
    from disks import self_check as disks_check
    from windowsboot import self_check as windows_check

    disks_check()
    windows_check()
    try:
        refused = dict(choices)
        refused["theme"] = "Not a theme"
        refused["loading"] = "stained-glass.jpg"
        refused["login"] = "throne.jpg"
        refused["wallpaper"] = "stained-glass.jpg"
        load_choices(json.dumps(refused))
    except Refuse:
        pass
    else:
        raise SystemExit("an unknown theme was accepted")
    try:
        refused = dict(choices)
        refused["agents"] = ["Not an agent"]
        load_choices(json.dumps(refused))
    except Refuse:
        pass
    else:
        raise SystemExit("an unknown agent was accepted")
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
        listing = current_lsblk()
        assert_disk_matches(data, listing)
        assert_games_matches(data, listing)
        assert_wipe_matches(data, listing)
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
