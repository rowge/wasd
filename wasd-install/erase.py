#!/usr/bin/env python3
"""Erase one disk on a live USB and install WASD.

--render prints a kickstart and does not touch a disk.
--install refuses unless this is a live USB, then runs bootc on the
selected disk. It does not open another window. After the copy it sets
up the account, the computer name, sign-in, and the look. It then copies
the apps already on the USB, points later updates at the WASD image,
restores the security labels on the new system, and enrolls the Secure
Boot key when the firmware is UEFI. When games were
requested, it adds that filesystem after those steps and before the USB
can come out. The account password, the Wi-Fi passphrase, and the
enrollment password are not stored in the choice file or the kickstart.
The kickstart renderer still omits them.
"""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/usr/libexec")

from agents import agents_problem  # noqa: E402
from disks import DEVICE_NAME, display_name, is_live, live_disk_names, parse_disks  # noqa: E402
from lookapply import LookError, apply_look, look_from, look_problem  # noqa: E402
from network import validate_tcp  # noqa: E402
from windowsboot import windows_post  # noqa: E402

HOST_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
USER_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
FILE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
LANG_NAME = re.compile(r"^[A-Za-z0-9_.@-]+$")
KEYMAP_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
ZONE_NAME = re.compile(r"^[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)+$|^UTC$")
# Pacific Time, including daylight saving. The hardware clock stays UTC.
DEFAULT_ZONE = "America/Los_Angeles"
PART_NAME = re.compile(r"^(nvme[0-9]+n[0-9]+p[0-9]+|sd[a-z]+[0-9]+|vd[a-z]+[0-9]+|mmcblk[0-9]+p[0-9]+|hd[a-z]+[0-9]+)$")
UUID_NAME = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
KEEP_FS = {"btrfs", "ext4", "xfs", "ntfs", "exfat"}
CHOICES_END = "WASD_CHOICES_END"
SECRET_KEYS = {"passphrase", "wpakey", "psk"}
WIFI_SECURITY = re.compile(r"[A-Za-z0-9 ._+-]*")
MIN_OS_GB = 64
MIN_GAMES_GB = 32
OVERHEAD_GB = 4
STATUS_PATH = Path("/tmp/wasd-install.status")
BOOTC_LOG = Path("/tmp/wasd-install-bootc.log")
STATUS_ID = re.compile(r"^[A-Za-z0-9]{8,40}$")
IMAGE_URL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,240}$")
STAGE_LINES = {
    "prepare": "Preparing the disk.",
    "copy": "Copying WASD.",
    "account": "Setting up your account.",
    "boot": "Installing the bootloader.",
    "done": "You can remove the USB stick. Press Enter to restart.",
}
WIPED_LINE = "The disk was erased. The install did not finish."
NOT_STARTED = "The installer could not be started. Nothing was erased."
GAMES_FAILED = "WASD was copied. The games partition was not created."
ACCOUNT_FAILED = "WASD was copied. The account was not set up."
APPS_FAILED = "WASD was copied. The installed apps were not copied."
UPDATES_FAILED = "WASD was copied. Later updates were not pointed at WASD."
LABELS_FAILED = "WASD was copied. The security labels were not restored."
GAMES_LOG = Path("/tmp/wasd-install-games.log")
ACCOUNT_LOG = Path("/tmp/wasd-install-account.log")
POST_LOG = Path("/tmp/wasd-install-post.log")
FLATPAK_SOURCE = Path("/var/lib/flatpak")
# security.selinux cannot be removed on the new disk, so the copy skips it.
# The label step writes those labels. File capabilities still copy. Once an
# xattr filter is set, rsync no longer skips system.* on its own.
RSYNC_APPS = [
    "rsync",
    "-aAXUHKP",
    "--open-noatime",
    "--filter=-x system.*",
    "--filter=-x security.selinux",
]
SECUREBOOT_KEY = Path("/usr/share/ublue-os/sb_pubkey.der")
# Public MOK password from the disk page. It is not an account password.
ENROLLMENT_PASSWORD = "universalblue"
MOK_SKIP = {"Jupiter", "Galileo"}
ACCOUNT_COMMANDS = {"useradd", "passwd", "usermod"}
WIFI_SOURCE = Path("/etc/NetworkManager/system-connections")
ACCOUNT_PART = re.compile(r"[A-Za-z0-9._+-]+")
WIFI_SECRETS = {
    "psk",
    "password",
    "passwd",
    "pin",
    "leap-password",
    "private-key-password",
    "wpa-psk",
    "secret",
}
SYSROOT = Path("/run/wasd-sysroot")
GAMES_MOUNT = Path("/run/wasd-games")
MOUNT_POINTS = {str(SYSROOT), str(GAMES_MOUNT)}
MOUNT_FS = {"btrfs", "ext4", "xfs", "ntfs3", "exfat"}
REV_NAME = re.compile(r"^[0-9a-f]{64}$")
# The deployment directory on the disk names the checksum. A fixed ostree
# index does not match what bootc writes.
DEPLOYMENT_SHELL = """
deployment=
found=0
for dir in /mnt/sysimage/ostree/deploy/default/deploy/*.0; do
    [ -d "$dir" ] || continue
    base=${dir##*/}
    rev=${base%.0}
    case $rev in
        *[!0-9a-f]*) continue ;;
    esac
    if [ ${#rev} -eq 64 ]; then
        deployment=$rev
        found=$((found + 1))
    fi
done
if [ "$found" -ne 1 ]; then
    deployment=
fi
""".strip()
DISK_COMMANDS = {
    "blkid",
    "mkfs.btrfs",
    "mount",
    "ostree",
    "partprobe",
    "sfdisk",
    "udevadm",
    "umount",
    "wipefs",
}


class Refuse(Exception):
    pass


class GamesProblem(Exception):
    """The disk copy finished and the games step then failed."""


class AccountProblem(Exception):
    """The disk copy finished and the account step then failed."""


class PostProblem(Exception):
    """The disk copy finished and a later setup step then failed."""


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
    zone = DEFAULT_ZONE
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
{DEPLOYMENT_SHELL}
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
    {DEPLOYMENT_SHELL}
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


def image_ref(defaults_text):
    """The live image stored on this USB, as a containers-storage reference."""
    match = re.search(
        r"(?m)^\s*ostreecontainer\b[^\n]*--url=(\S+)[^\n]*--transport=containers-storage\b",
        defaults_text,
    )
    if not match:
        raise Refuse("The live installer defaults have no image. Nothing was erased.")
    url = match.group(1)
    if not IMAGE_URL.fullmatch(url) or ".." in url or url.startswith("-"):
        raise Refuse("The live installer defaults have no image. Nothing was erased.")
    return "containers-storage:" + url


def bootc_argv(device, plan, source):
    """The bootc command for this disk. It does not create the games filesystem."""
    if not DEVICE_NAME.fullmatch(device):
        raise Refuse("Choose a disk again. Nothing was erased.")
    if (
        not source.startswith("containers-storage:")
        or ".." in source
        or any(token in source for token in (" ", ";", "|", "&", "$", "`", "'", '"', "\\"))
    ):
        raise Refuse("The live installer defaults have no image. Nothing was erased.")
    argv = [
        "bootc",
        "install",
        "to-disk",
        "--wipe",
        "--filesystem",
        "btrfs",
        "--skip-fetch-check",
        "--source-imgref",
        source,
        # Without these, the installed boot prints the text log over the loading screen.
        "--karg",
        "quiet",
        "--karg",
        "rhgb",
    ]
    if plan.get("mode") == "split":
        os_gb = plan.get("osGb")
        if isinstance(os_gb, bool) or not isinstance(os_gb, int) or os_gb < MIN_OS_GB or os_gb > 100000:
            raise Refuse("Set the size for WASD and for games. Nothing was erased.")
        argv.extend(["--root-size", f"{os_gb}G"])
    argv.append(f"/dev/{device}")
    if any(part == "liveinst" or str(part).endswith("/liveinst") for part in argv):
        raise Refuse(NOT_STARTED)
    return argv


def install_gate(live, euid):
    """Whether --install may continue, must become root, or must stop."""
    if not live:
        return "refuse"
    if euid != 0:
        return "pkexec"
    return "root"


def write_status(status_id, line):
    if os.environ.get("WASD_SELF_CHECK") == "1" or not STATUS_ID.fullmatch(status_id):
        return
    blob = f"{status_id}\n{line}\n"
    temporary = STATUS_PATH.with_name(f".wasd-install.status.{status_id}")
    try:
        temporary.write_text(blob)
        os.chmod(temporary, 0o644)
        os.replace(temporary, STATUS_PATH)
    except OSError:
        return


def announce_stage(status_id, stage, spoken):
    line = STAGE_LINES[stage]
    if os.environ.get("WASD_SELF_CHECK") != "1":
        print(line, flush=True)
        write_status(status_id, line)
    spoken.append(stage)


def started_line(exc):
    """The sentence for a failure after the wipe has started."""
    text = str(exc).strip()
    return text or WIPED_LINE


def pre_wipe_message(output):
    line = ""
    for item in (output or "").splitlines():
        if item.strip():
            line = item.strip()
    if not line or "Traceback" in line or 'File "' in line or len(line) > 120:
        return NOT_STARTED
    if "Nothing was erased." in line:
        return line
    return line.rstrip(".") + ". Nothing was erased."


def run_bootc(argv, status_id, runner, spoken, finish=None, account=None, post=None):
    """Run bootc. A failure before it wipes the disk leaves the disk alone.

    account runs after the copy and before the bootloader sentence.
    post runs after that sentence and before games. It copies the apps
    already on the USB, points later updates at the registry image, and
    enrolls the Secure Boot key. finish runs after post, including when
    post reports a failure, and before the USB sentence. A failure in any
    of those steps skips the USB sentence. The sentence is the first failure.
    """
    if not argv or argv[0] != "bootc" or "to-disk" not in argv or "liveinst" in argv:
        raise Refuse(NOT_STARTED)
    device = argv[-1]
    if not device.startswith("/dev/") or not DEVICE_NAME.fullmatch(device.removeprefix("/dev/")):
        raise Refuse("Choose a disk again. Nothing was erased.")
    state = {"wiped": False}
    # The copy is the long part. bootc prints the bootloader line while
    # the copy is still running. The window ranks the account before that
    # line, so the bootloader sentence waits until the account step has run.
    announce_stage(status_id, "copy", spoken)

    def on_line(line):
        if "Wiping " in line:
            state["wiped"] = True
        if "copy" not in spoken and (
            "Deploying container image" in line or "layers needed" in line or "layers already present" in line
        ):
            announce_stage(status_id, "copy", spoken)

    try:
        result = runner(argv, on_line)
    except OSError as exc:
        raise Refuse(NOT_STARTED) from exc
    if result is None:
        raise Refuse(NOT_STARTED)
    if not isinstance(result, tuple) or len(result) != 2 or not isinstance(result[0], int) or isinstance(result[0], bool):
        raise Started(WIPED_LINE)
    code, output = result
    if not isinstance(output, str):
        raise Started(WIPED_LINE)
    if "Wiping " in output:
        state["wiped"] = True
    if code != 0:
        if state["wiped"]:
            raise Started(WIPED_LINE)
        raise Refuse(pre_wipe_message(output))
    if "copy" not in spoken:
        announce_stage(status_id, "copy", spoken)
    if account is not None:
        try:
            account()
        except Started:
            raise
        except Exception as exc:
            raise Started(ACCOUNT_FAILED) from exc
    if "boot" not in spoken:
        announce_stage(status_id, "boot", spoken)
    post_problem = None
    if post is not None:
        try:
            post()
        except Started:
            raise
        except PostProblem as exc:
            text = str(exc).strip()
            if text not in {APPS_FAILED, UPDATES_FAILED, LABELS_FAILED} or "Nothing was erased." in text:
                text = UPDATES_FAILED
            post_problem = text
        except Exception:
            # The disk is already copied. This must not say it was left alone.
            post_problem = UPDATES_FAILED
    if finish is not None:
        try:
            finish()
        except Started:
            raise
        except Exception as exc:
            # The disk is already copied. The games failure is the sentence
            # when the earlier steps returned. An earlier failure stays.
            if post_problem is None:
                raise Started(GAMES_FAILED) from exc
    if post_problem:
        raise Started(post_problem)
    announce_stage(status_id, "done", spoken)
    return 0


def bootc_runner(argv, on_line):
    """The real bootc process. The self-check never calls this."""
    if os.environ.get("WASD_SELF_CHECK") == "1":
        raise SystemExit("self-check tried to run bootc")
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except OSError:
        return None
    chunks = []
    try:
        with BOOTC_LOG.open("w") as handle:
            os.chmod(BOOTC_LOG, 0o600)
            assert proc.stdout is not None
            for line in proc.stdout:
                handle.write(line)
                handle.flush()
                chunks.append(line)
                on_line(line)
        code = proc.wait()
    except OSError:
        proc.kill()
        proc.wait()
        return 1, "".join(chunks)
    return code, "".join(chunks)


def stop_if_checking(action):
    if os.environ.get("WASD_SELF_CHECK") == "1":
        raise SystemExit(f"self-check tried to {action}")


def games_log(text):
    if os.environ.get("WASD_SELF_CHECK") == "1" or not text:
        return
    blob = text if str(text).endswith("\n") else str(text) + "\n"
    try:
        fd = os.open(GAMES_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    except OSError:
        return
    try:
        os.chmod(GAMES_LOG, 0o600)
        os.write(fd, blob.encode())
    except OSError:
        return
    finally:
        os.close(fd)


def games_needed(plan):
    return isinstance(plan, dict) and plan.get("mode") not in (None, "off", "")


def partition_of(device, name):
    if not DEVICE_NAME.fullmatch(device or "") or not PART_NAME.fullmatch(name or ""):
        return False
    if not name.startswith(device):
        return False
    rest = name[len(device):]
    if device.startswith(("nvme", "mmcblk")):
        return rest.startswith("p") and rest[1:].isdigit()
    return rest.isdigit()


def plain_sector(value):
    if isinstance(value, bool) or not isinstance(value, int):
        raise GamesProblem("a partition size could not be read")
    return value


def table_body(blob):
    if isinstance(blob, str):
        try:
            blob = json.loads(blob)
        except json.JSONDecodeError as exc:
            raise GamesProblem("the partition table could not be read") from exc
    if not isinstance(blob, dict):
        raise GamesProblem("the partition table could not be read")
    table = blob.get("partitiontable") or blob
    if not isinstance(table, dict):
        raise GamesProblem("the partition table could not be read")
    return table


def table_partitions(blob):
    parts = table_body(blob).get("partitions") or []
    if not isinstance(parts, list):
        raise GamesProblem("the partition table could not be read")
    return parts


def part_node(part):
    if not isinstance(part, dict):
        raise GamesProblem("a partition could not be read")
    name = str(part.get("node") or "").removeprefix("/dev/")
    if not PART_NAME.fullmatch(name):
        raise GamesProblem("a partition could not be read")
    return name


def node_names(blob):
    return [part_node(part) for part in table_partitions(blob)]


def part_bytes(part, blob):
    sectorsize = plain_sector(table_body(blob).get("sectorsize"))
    size = plain_sector(part.get("size"))
    if sectorsize <= 0 or size <= 0:
        raise GamesProblem("a partition size could not be read")
    return size * sectorsize


def free_tail(blob):
    """The free space after the last partition, aligned to 1 MiB.

    sfdisk --append without a start uses the first gap. A hole between
    the boot partitions must not become the games partition.
    """
    table = table_body(blob)
    sectorsize = plain_sector(table.get("sectorsize"))
    lastlba = plain_sector(table.get("lastlba"))
    if sectorsize <= 0 or lastlba <= 0:
        raise GamesProblem("the partition table could not be read")
    mebibyte = 1024 * 1024
    if mebibyte % sectorsize != 0:
        raise GamesProblem("the sector size is not usable")
    align = mebibyte // sectorsize
    parts = table_partitions(blob)
    if not parts:
        raise GamesProblem("the disk has no partitions")
    spans = []
    for part in parts:
        start = plain_sector(part.get("start"))
        size = plain_sector(part.get("size"))
        if start < 0 or size <= 0:
            raise GamesProblem("a partition size could not be read")
        end = start + size
        if end - 1 > lastlba:
            raise GamesProblem("a partition runs past the disk")
        spans.append((start, end))
    spans.sort()
    for index in range(1, len(spans)):
        if spans[index][0] < spans[index - 1][1]:
            raise GamesProblem("the partitions overlap")
    last_end = spans[-1][1]
    start = ((last_end + align - 1) // align) * align
    if start > lastlba:
        raise GamesProblem("there is no room for games")
    size = lastlba - start + 1
    if size <= 0 or size * sectorsize < MIN_GAMES_GB * (1024 ** 3):
        raise GamesProblem("there is no room for games")
    return start, size


def split_request(device, start, size):
    if not DEVICE_NAME.fullmatch(device or ""):
        raise GamesProblem("the disk name is not a whole disk")
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        raise GamesProblem("the free space could not be read")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise GamesProblem("the free space could not be read")
    argv = ["sfdisk", "--append", "--lock", f"/dev/{device}"]
    if "--wipe" in argv:
        raise GamesProblem("the split would wipe the disk")
    script = f"start={start}, size={size}, type=linux, name=games\n"
    return argv, script


def only_root(rows):
    """The one btrfs partition bootc created."""
    found = []
    for row in rows:
        if not isinstance(row, dict):
            raise GamesProblem("the WASD filesystem could not be read")
        if (row.get("fstype") or "").lower() != "btrfs":
            continue
        name = row.get("name") or ""
        if not PART_NAME.fullmatch(name):
            raise GamesProblem("the WASD filesystem is not a partition")
        found.append(name)
    if len(found) != 1:
        raise GamesProblem("WASD does not have one filesystem")
    return found[0]


def new_partition(before, after, device, root):
    """The one partition that appeared. Its name comes from the new table."""
    if not DEVICE_NAME.fullmatch(device or "") or not PART_NAME.fullmatch(root or ""):
        raise GamesProblem("the new partition could not be named")
    before_names = set(before)
    after_names = []
    added = []
    for row in after:
        if not isinstance(row, dict):
            raise GamesProblem("the new partition could not be named")
        name = row.get("name") or ""
        after_names.append(name)
        if name not in before_names:
            added.append(row)
    if set(before_names) - set(after_names):
        raise GamesProblem("a partition disappeared")
    if len(added) != 1:
        raise GamesProblem("the games partition was not the only new partition")
    row = added[0]
    name = row.get("name") or ""
    if not partition_of(device, name) or name == root:
        raise GamesProblem("the games partition is on the wrong disk")
    if (row.get("fstype") or "").lower():
        raise GamesProblem("the games partition is not empty")
    size = row.get("bytes")
    if size is not None and (isinstance(size, bool) or not isinstance(size, int) or size < MIN_GAMES_GB * (1024 ** 3)):
        raise GamesProblem("the games partition is too small")
    return name


def find_part(blob, name):
    for part in table_partitions(blob):
        if part_node(part) == name:
            return part
    raise GamesProblem("the games partition is missing")


def lone_partition(blob, device):
    names = node_names(blob)
    if len(names) != 1 or names[0] != first_partition(device) or not partition_of(device, names[0]):
        raise GamesProblem("the games drive does not have one partition")
    return names[0]


def mentions(argv, device):
    disk = f"/dev/{device}"
    for part in argv:
        if part == disk:
            return True
        if not part.startswith(disk):
            continue
        rest = part[len(disk):]
        if device.startswith(("nvme", "mmcblk")) and rest.startswith("p") and rest[1:].isdigit():
            return True
        if not device.startswith(("nvme", "mmcblk")) and rest.isdigit():
            return True
    return False


def format_commands(os_device, games_device):
    """Wipe only the games drive, then format its first partition."""
    if (
        not DEVICE_NAME.fullmatch(os_device or "")
        or not DEVICE_NAME.fullmatch(games_device or "")
        or games_device == os_device
    ):
        raise GamesProblem("the games drive is the WASD disk")
    part = first_partition(games_device)
    if not partition_of(games_device, part):
        raise GamesProblem("the games partition is the WASD disk")
    wipe = ["wipefs", "-a", f"/dev/{games_device}"]
    argv = ["sfdisk", "--wipe", "always", "--lock", f"/dev/{games_device}"]
    script = "label: gpt\ntype=linux, name=games\n"
    mkfs = ["mkfs.btrfs", "-f", "-L", "games", f"/dev/{part}"]
    if mkfs[-1] in {f"/dev/{os_device}", f"/dev/{games_device}"}:
        raise GamesProblem("the format command targets the whole disk")
    if mentions(wipe + argv + mkfs, os_device):
        raise GamesProblem("the format command names the WASD disk")
    return wipe, argv, script, mkfs


def fstab_line(uuid, fstype):
    if not UUID_NAME.fullmatch(uuid or "") or fstype not in MOUNT_FS:
        raise GamesProblem("the games filesystem cannot be mounted")
    return f"UUID={uuid.lower()} /games {fstype} defaults,nofail 0 0\n"


def path_inside(root, parts):
    """Walk parts. A symlink may be followed only when it stays under root."""
    current = Path(root).resolve()
    root_path = current
    for part in parts:
        if part in {".", ".."} or not re.fullmatch(r"[A-Za-z0-9._+-]+", part or ""):
            raise GamesProblem("a path left the new system")
        nxt = current / part
        if nxt.is_symlink():
            current = nxt.resolve()
        else:
            current = nxt
        if not current.resolve().is_relative_to(root_path):
            raise GamesProblem("a path left the new system")
    return current


def deployment_fstab(mount, rev):
    if not REV_NAME.fullmatch(rev or ""):
        raise GamesProblem("the installed system has no deployment")
    deploy = path_inside(mount, ("ostree", "deploy", "default", "deploy", f"{rev}.0"))
    etc = deploy / "etc"
    root_path = Path(mount).resolve()
    if etc.is_symlink():
        etc = etc.resolve()
        if not etc.is_relative_to(root_path):
            raise GamesProblem("the filesystem table left the new system")
    fstab = etc / "fstab"
    if fstab.is_symlink():
        fstab = fstab.resolve()
    if not fstab.is_relative_to(root_path):
        raise GamesProblem("the filesystem table left the new system")
    return fstab


def append_fstab(path, line, root):
    root_path = Path(root).resolve()
    file = Path(path).resolve()
    if not file.is_file() or not file.is_relative_to(root_path):
        raise GamesProblem("the filesystem table left the new system")
    if line.count("\n") != 1 or not line.endswith("\n") or not line.startswith("UUID=") or " /games " not in line:
        raise GamesProblem("the filesystem table line is wrong")
    text = file.read_text(errors="replace")
    if " /games " in text:
        return False
    if text and not text.endswith("\n"):
        text += "\n"
    temporary = file.with_name(file.name + ".wasd-games")
    try:
        temporary.write_text(text + line)
        os.chmod(temporary, 0o644)
        os.replace(temporary, file)
    finally:
        if temporary.exists():
            temporary.unlink()
    return True


def checked_argv(argv, script):
    if not argv or any(not isinstance(item, str) or not item for item in argv):
        raise GamesProblem("a disk command was empty")
    if argv[0] not in DISK_COMMANDS:
        raise GamesProblem("a disk command is not allowed")
    if script is not None and argv[0] != "sfdisk":
        raise GamesProblem("a disk command was given a script")
    if script is not None and (len(script) > 400 or "\x00" in script):
        raise GamesProblem("the partition script is not usable")
    if argv[0] == "sfdisk":
        target = argv[-1].removeprefix("/dev/")
        if not DEVICE_NAME.fullmatch(target):
            raise GamesProblem("sfdisk was aimed at a partition")
        if "--append" in argv and "--wipe" in argv:
            raise GamesProblem("the split would wipe the disk")
    if argv[0] == "wipefs":
        if not DEVICE_NAME.fullmatch(argv[-1].removeprefix("/dev/")):
            raise GamesProblem("wipefs was aimed at a partition")
    if argv[0] == "mkfs.btrfs":
        if not PART_NAME.fullmatch(argv[-1].removeprefix("/dev/")):
            raise GamesProblem("the format command targets the whole disk")
    if argv[0] == "partprobe" and (len(argv) != 2 or not DEVICE_NAME.fullmatch(argv[-1].removeprefix("/dev/"))):
        raise GamesProblem("partprobe was not limited to one disk")
    if argv[0] in {"mount", "umount"} and argv[-1] not in MOUNT_POINTS:
        raise GamesProblem("the mount is not a games mount")
    return argv


def run_disk_result(argv, script=None):
    stop_if_checking("run " + (argv[0] if argv else "a disk command"))
    checked_argv(argv, script)
    games_log(" ".join(argv))
    if script:
        games_log(script)
    try:
        # A script is the whole stdin. Without one, do not leave the command
        # attached to a terminal, or sfdisk would start an interactive session.
        if script is None:
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True)
        else:
            result = subprocess.run(argv, input=script, capture_output=True, text=True)
    except OSError as exc:
        games_log(str(exc))
        raise GamesProblem("a disk command could not be started") from exc
    if result.stdout:
        games_log(result.stdout)
    if result.stderr:
        games_log(result.stderr)
    return result


def run_disk(argv, script=None):
    result = run_disk_result(argv, script)
    if result.returncode != 0:
        raise GamesProblem("a disk command failed")
    return result


def assert_not_live(device):
    stop_if_checking("read disks")
    if not DEVICE_NAME.fullmatch(device or ""):
        raise GamesProblem("the disk name is not a whole disk")
    if device in live_disk_names(current_lsblk()):
        raise GamesProblem("that disk is the live USB")


def read_table(device):
    stop_if_checking("read a partition table")
    if not DEVICE_NAME.fullmatch(device or ""):
        raise GamesProblem("the disk name is not a whole disk")
    result = run_disk(["sfdisk", "--json", f"/dev/{device}"])
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GamesProblem("the partition table could not be read") from exc


def blkid_value(name, tag):
    stop_if_checking("read a filesystem")
    if not PART_NAME.fullmatch(name or ""):
        raise GamesProblem("the games partition is not a partition")
    node = f"/dev/{name}"
    if not os.path.exists(node):
        raise GamesProblem("the games partition is missing")
    result = run_disk_result(["blkid", "-p", "-s", tag, "-o", "value", node])
    if result.returncode not in (0, 2):
        raise GamesProblem("the games filesystem could not be read")
    return result.stdout.strip()


def fs_type(name):
    stop_if_checking("read a filesystem type")
    return blkid_value(name, "TYPE").lower()


def fs_uuid(name):
    stop_if_checking("read a filesystem id")
    uuid = blkid_value(name, "UUID")
    if not UUID_NAME.fullmatch(uuid):
        raise GamesProblem("the games drive has no id")
    return uuid


def typed_rows(device, blob):
    stop_if_checking("read a filesystem type")
    rows = []
    for part in table_partitions(blob):
        name = part_node(part)
        if not partition_of(device, name):
            raise GamesProblem("a partition is on the wrong disk")
        rows.append({"name": name, "fstype": fs_type(name), "bytes": part_bytes(part, blob)})
    return rows


def deployment_rev(sysroot):
    """The checksum of the one deployment directory on the mounted system."""
    root = Path(sysroot)
    if root.is_symlink():
        raise GamesProblem("the new system is not mounted")
    deploy_root = root / "ostree" / "deploy" / "default" / "deploy"
    if deploy_root.is_symlink() or not deploy_root.is_dir():
        raise GamesProblem("the installed system has no deployment")
    found = []
    for child in deploy_root.iterdir():
        if child.is_symlink() or not child.is_dir():
            continue
        if not child.name.endswith(".0"):
            continue
        rev = child.name[:-2]
        if not REV_NAME.fullmatch(rev):
            continue
        if not child.resolve().is_relative_to(root.resolve()):
            raise GamesProblem("the installed system has no deployment")
        found.append(rev)
    if len(found) != 1:
        raise GamesProblem("the installed system has no deployment")
    return found[0]


def read_rev(sysroot):
    stop_if_checking("read the deployment")
    root = Path(sysroot).resolve()
    if root != SYSROOT.resolve():
        raise GamesProblem("the new system is not mounted")
    return deployment_rev(root)


def reread(device):
    stop_if_checking("reread a partition table")
    if not DEVICE_NAME.fullmatch(device or ""):
        raise GamesProblem("the disk name is not a whole disk")
    run_disk_result(["partprobe", f"/dev/{device}"])
    run_disk(["udevadm", "settle", "--timeout=20"])


def make_btrfs(name):
    stop_if_checking("format a partition")
    if not PART_NAME.fullmatch(name or ""):
        raise GamesProblem("the games partition is not a partition")
    if fs_type(name):
        raise GamesProblem("the games partition is not empty")
    run_disk(["mkfs.btrfs", "-f", "-L", "games", f"/dev/{name}"])


def fresh_mount(path):
    if path.is_symlink():
        raise GamesProblem("the mount folder is a link")
    path.mkdir(parents=True, exist_ok=True)
    if os.path.ismount(path):
        raise GamesProblem("a mount is already in use")
    if any(path.iterdir()):
        raise GamesProblem("the mount folder is not empty")


def quiet_umount(path):
    stop_if_checking("unmount")
    if str(path) not in MOUNT_POINTS:
        raise GamesProblem("the mount is not a games mount")
    try:
        result = subprocess.run(["umount", str(path)], capture_output=True, text=True)
    except OSError as exc:
        games_log(str(exc))
        return False
    if result.returncode != 0:
        games_log(result.stderr)
        return False
    return True


def mount_library(mount):
    stop_if_checking("make a games folder")
    root = Path(mount).resolve()
    if root != GAMES_MOUNT.resolve() or not os.path.ismount(root):
        raise GamesProblem("the games folder is not mounted")
    steam = root / "SteamLibrary"
    apps = steam / "steamapps"
    if steam.is_symlink() or apps.is_symlink():
        raise GamesProblem("the games folder is a link")
    steam.mkdir(mode=0o755, exist_ok=True)
    apps.mkdir(mode=0o755, exist_ok=True)


def attach_games(root_name, uuid, fstype):
    """Mount the remembered WASD filesystem and add /games to it.

    root_name is the btrfs partition from before the games volume exists.
    Afterwards both filesystems are btrfs, so the root is not looked up again.
    """
    stop_if_checking("attach games")
    if not PART_NAME.fullmatch(root_name or ""):
        raise GamesProblem("the WASD filesystem is not a partition")
    line = fstab_line(uuid, fstype)
    fresh_mount(SYSROOT)
    fresh_mount(GAMES_MOUNT)
    mounted_sys = False
    mounted_games = False
    finished = False
    try:
        run_disk(["mount", "-t", "btrfs", f"/dev/{root_name}", str(SYSROOT)])
        mounted_sys = True
        rev = read_rev(SYSROOT)
        fstab = deployment_fstab(SYSROOT, rev)
        if not fstab.is_file():
            raise GamesProblem("the new system has no filesystem table")
        deploy = path_inside(SYSROOT, ("ostree", "deploy", "default", "deploy", f"{rev}.0"))
        games_dir = deploy / "games"
        # Do not follow a symlink. /games is already a directory in the
        # image; this is the mountpoint on the mounted filesystem.
        if games_dir.is_symlink() or not games_dir.is_relative_to(SYSROOT.resolve()):
            raise GamesProblem("the games path is a link")
        games_dir.mkdir(mode=0o755, exist_ok=True)
        append_fstab(fstab, line, SYSROOT)
        run_disk(["mount", "-t", fstype, f"UUID={uuid}", str(GAMES_MOUNT)])
        mounted_games = True
        mount_library(GAMES_MOUNT)
        finished = True
    finally:
        games_ok = quiet_umount(GAMES_MOUNT) if mounted_games else True
        sys_ok = quiet_umount(SYSROOT) if mounted_sys else True
        if finished and not (games_ok and sys_ok):
            raise GamesProblem("a games folder stayed mounted")


def add_split_games(device, plan):
    stop_if_checking("add a split games partition")
    if not DEVICE_NAME.fullmatch(device or "") or plan.get("mode") != "split":
        raise GamesProblem("this disk is not split")
    assert_not_live(device)
    before = read_table(device)
    root = only_root(typed_rows(device, before))
    start, size = free_tail(before)
    argv, script = split_request(device, start, size)
    run_disk(argv, script)
    reread(device)
    after = read_table(device)
    name = new_partition(node_names(before), typed_rows(device, after), device, root)
    part = find_part(after, name)
    if plain_sector(part.get("start")) != start or plain_sector(part.get("size")) != size:
        raise GamesProblem("the games partition is not the free space")
    make_btrfs(name)
    reread(device)
    if fs_type(name) != "btrfs":
        raise GamesProblem("the games filesystem is not btrfs")
    attach_games(root, fs_uuid(name), "btrfs")


def add_formatted_games(os_device, plan):
    stop_if_checking("format a games drive")
    device = plan.get("device") or ""
    if plan.get("mode") != "format":
        raise GamesProblem("this disk is not a new games drive")
    assert_not_live(os_device)
    assert_not_live(device)
    if device == os_device:
        raise GamesProblem("the games drive is the WASD disk")
    root = only_root(typed_rows(os_device, read_table(os_device)))
    wipe, argv, script, mkfs = format_commands(os_device, device)
    run_disk(wipe)
    run_disk(argv, script)
    reread(device)
    name = lone_partition(read_table(device), device)
    if fs_type(name):
        raise GamesProblem("the games partition is not empty")
    if mkfs != ["mkfs.btrfs", "-f", "-L", "games", f"/dev/{name}"]:
        raise GamesProblem("the format command changed")
    make_btrfs(name)
    reread(device)
    if fs_type(name) != "btrfs":
        raise GamesProblem("the games filesystem is not btrfs")
    attach_games(root, fs_uuid(name), "btrfs")


def add_kept_games(os_device, plan):
    stop_if_checking("keep a games drive")
    if plan.get("mode") != "keep":
        raise GamesProblem("this disk is not a kept games drive")
    device = plan.get("device") or ""
    part = plan.get("part") or ""
    assert_not_live(os_device)
    assert_not_live(device)
    if device == os_device or not partition_of(device, part):
        raise GamesProblem("the games drive is the WASD disk")
    uuid = fs_uuid(part)
    if uuid.lower() != str(plan.get("uuid") or "").lower():
        raise GamesProblem("the games drive changed")
    actual = fs_type(part)
    mount_fs = "ntfs3" if actual == "ntfs" else actual
    if mount_fs != plan.get("fstype") or mount_fs not in MOUNT_FS:
        raise GamesProblem("the games filesystem changed")
    root = only_root(typed_rows(os_device, read_table(os_device)))
    attach_games(root, uuid, mount_fs)


def prepare_games(os_device, plan):
    stop_if_checking("prepare games")
    try:
        mode = plan.get("mode")
        if mode == "split":
            add_split_games(os_device, plan)
        elif mode == "format":
            add_formatted_games(os_device, plan)
        elif mode == "keep":
            add_kept_games(os_device, plan)
        elif mode != "off":
            raise GamesProblem("the games choice is not one of the three")
    except GamesProblem as exc:
        games_log(str(exc))
        raise
    except OSError as exc:
        games_log(str(exc))
        raise GamesProblem("the games partition was not created") from exc


def finish_games(os_device, plan):
    if not games_needed(plan):
        return
    prepare_games(os_device, plan)


def account_log(text):
    if os.environ.get("WASD_SELF_CHECK") == "1" or not text:
        return
    blob = text if str(text).endswith("\n") else str(text) + "\n"
    try:
        fd = os.open(ACCOUNT_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    except OSError:
        return
    try:
        os.chmod(ACCOUNT_LOG, 0o600)
        os.write(fd, blob.encode())
    except OSError:
        return
    finally:
        os.close(fd)


def host_root(path):
    return Path(path).resolve() == Path("/").resolve()


def secret_line(line):
    body = line.split("#", 1)[0].strip()
    if "=" not in body:
        return False
    key = body.split("=", 1)[0].strip().lower()
    if key in WIFI_SECRETS:
        return True
    tail = key[len("wep-key"):] if key.startswith("wep-key") else ""
    return bool(tail) and tail.isdigit()


def strip_secrets(text):
    """Drop secret assignments. The network name and the other fields stay."""
    kept = []
    for line in str(text).splitlines():
        if secret_line(line):
            continue
        kept.append(line)
    if not kept:
        return ""
    return "\n".join(kept) + "\n"


def passwd_record(text, user):
    if not USER_NAME.fullmatch(user or "") or user == "root":
        raise AccountProblem("the username is not usable")
    found = None
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split(":")
        if not fields or fields[0] != user:
            continue
        if len(fields) < 7 or found is not None:
            raise AccountProblem("the account id could not be read")
        found = fields
    if found is None:
        return None
    if not found[2].isdigit() or not found[3].isdigit():
        raise AccountProblem("the account id could not be read")
    uid = int(found[2])
    gid = int(found[3])
    if uid < 1000 or gid < 0:
        raise AccountProblem("the account id could not be read")
    home = found[5]
    parts = Path(home).parts
    if (
        not home.startswith("/")
        or home == "/"
        or "\x00" in home
        or not parts
        or parts[-1] != user
        or any(part in {".", ".."} for part in parts)
    ):
        raise AccountProblem("the home directory is not usable")
    return {"uid": uid, "gid": gid, "home": home}


def walk_inside(start, jail, parts):
    """Follow parts from start. A symlink is allowed only inside jail."""
    if host_root(jail):
        raise AccountProblem("a path left the new system")
    jail_path = Path(jail).resolve()
    current = Path(start).resolve()
    if host_root(current) or not current.is_relative_to(jail_path):
        raise AccountProblem("a path left the new system")
    for part in parts:
        if part in {".", ".."} or not ACCOUNT_PART.fullmatch(part or ""):
            raise AccountProblem("a path left the new system")
        nxt = current / part
        current = nxt.resolve() if nxt.is_symlink() else nxt
        if host_root(current) or not current.resolve().is_relative_to(jail_path):
            raise AccountProblem("a path left the new system")
    return current


def ensure_dir(start, jail, parts, mode=0o755):
    current = walk_inside(start, jail, ())
    if not current.is_dir():
        raise AccountProblem("a path left the new system")
    jail_path = Path(jail).resolve()
    for part in parts:
        if part in {".", ".."} or not ACCOUNT_PART.fullmatch(part or ""):
            raise AccountProblem("a path left the new system")
        nxt = current / part
        if nxt.is_symlink():
            current = nxt.resolve()
            if not current.is_dir() or not current.is_relative_to(jail_path):
                raise AccountProblem("a path left the new system")
            continue
        if nxt.exists() and not nxt.is_dir():
            raise AccountProblem("a path left the new system")
        made = False
        if not nxt.exists():
            nxt.mkdir(mode=mode)
            made = True
        current = nxt.resolve()
        if not current.is_dir() or not current.is_relative_to(jail_path):
            raise AccountProblem("a path left the new system")
        if made:
            os.chmod(current, mode)
    return current


def write_exact(path, data, mode, jail):
    path = Path(path)
    if host_root(jail) or path.is_symlink():
        raise AccountProblem("a path left the new system")
    jail_path = Path(jail).resolve()
    parent = path.parent.resolve()
    if not parent.is_dir() or not parent.is_relative_to(jail_path):
        raise AccountProblem("a path left the new system")
    blob = data if isinstance(data, bytes) else str(data).encode()
    temporary = parent / (path.name + ".wasd-account")
    if temporary.is_symlink() or not temporary.parent.resolve().is_relative_to(jail_path):
        raise AccountProblem("a path left the new system")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        try:
            os.write(fd, blob)
        finally:
            os.close(fd)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    if path.is_symlink() or not path.resolve().is_relative_to(jail_path):
        raise AccountProblem("a path left the new system")
    os.chmod(path, mode)


def link_shared_var(deploy, jail):
    """Use the var the booted system mounts, not the copy inside the deployment.

    bootc leaves a real var directory in the deployment. After boot, that
    directory is hidden by ostree/deploy/<name>/var. The home and the account
    picture have to be written through a symlink to that shared var.
    """
    deploy = Path(deploy)
    jail_path = Path(jail).resolve()
    if host_root(deploy) or host_root(jail) or deploy.is_symlink() or not deploy.is_dir():
        raise AccountProblem("the new system is not mounted")
    if not deploy.resolve().is_relative_to(jail_path):
        raise AccountProblem("the new system is not mounted")
    shared = deploy.parent.parent / "var"
    if shared.is_symlink() or not shared.is_dir() or host_root(shared):
        raise AccountProblem("the new system is not mounted")
    if not shared.resolve().is_relative_to(jail_path):
        raise AccountProblem("the new system is not mounted")
    local = deploy / "var"
    if local.is_symlink():
        if local.resolve() != shared.resolve():
            raise AccountProblem("the new system is not mounted")
        return
    if local.exists():
        same = False
        try:
            same = local.stat().st_ino == shared.stat().st_ino and local.stat().st_dev == shared.stat().st_dev
        except OSError as exc:
            raise AccountProblem("the new system is not mounted") from exc
        if same:
            return
        if not local.is_dir() or not local.resolve().is_relative_to(deploy.resolve()):
            raise AccountProblem("the new system is not mounted")
        shutil.rmtree(local)
    local.symlink_to("../../var")
    if not local.is_symlink() or local.resolve() != shared.resolve():
        raise AccountProblem("the new system is not mounted")


def ensure_tree_links(deploy, jail):
    """The deployment's home and var must stay on the mounted system.

    useradd --prefix follows them. --root would chroot and hide the shared
    var the booted system actually uses.
    """
    if host_root(deploy) or host_root(jail):
        raise AccountProblem("a path left the new system")
    jail_path = Path(jail).resolve()
    if not Path(deploy).resolve().is_relative_to(jail_path):
        raise AccountProblem("a path left the new system")
    for name in ("var", "home"):
        path = Path(deploy) / name
        if not path.exists() and not path.is_symlink():
            continue
        if path.is_symlink():
            resolved = path.resolve()
            if not resolved.is_relative_to(jail_path):
                raise AccountProblem("a path left the new system")
            continue
        if not path.is_dir() or not path.resolve().is_relative_to(jail_path):
            raise AccountProblem("a path left the new system")


def checked_account(argv, jail):
    if not argv or any(not isinstance(item, str) or item == "" for item in argv):
        raise AccountProblem("an account command was empty")
    if argv[0] not in ACCOUNT_COMMANDS:
        raise AccountProblem("an account command is not allowed")
    banned = {"-p", "--password", "--stdin", "-s", "--root", "-R", "--password-fd"}
    if any(item in banned for item in argv):
        raise AccountProblem("an account command would store a password")
    if argv[0] == "passwd" and "--delete" not in argv and "-d" not in argv:
        raise AccountProblem("an account command would store a password")
    if "--prefix" not in argv or argv.index("--prefix") != 1 or len(argv) < 3:
        raise AccountProblem("an account command has no deployment")
    raw = argv[2]
    if not raw.startswith("/") or "\x00" in raw or "\n" in raw:
        raise AccountProblem("an account command left the new system")
    prefix = Path(raw).resolve()
    jail_path = Path(jail).resolve()
    if host_root(prefix) or host_root(jail_path) or not prefix.is_relative_to(jail_path):
        raise AccountProblem("an account command left the new system")
    user = argv[-1]
    if not USER_NAME.fullmatch(user) or user == "root":
        raise AccountProblem("the username is not usable")
    expected = {
        "useradd": ["useradd", "--prefix", raw, "--create-home", "--groups", "wheel", user],
        "usermod": ["usermod", "--prefix", raw, "--append", "--groups", "wheel", user],
        "passwd": ["passwd", "--prefix", raw, "--delete", user],
    }
    if argv != expected[argv[0]]:
        raise AccountProblem("an account command would store a password")
    return argv


def account_commands(deploy, user, exists):
    if not USER_NAME.fullmatch(user or "") or user == "root":
        raise AccountProblem("the username is not usable")
    prefix = str(Path(deploy).resolve())
    if exists:
        commands = [
            ["usermod", "--prefix", prefix, "--append", "--groups", "wheel", user],
            ["passwd", "--prefix", prefix, "--delete", user],
        ]
    else:
        commands = [
            ["useradd", "--prefix", prefix, "--create-home", "--groups", "wheel", user],
            ["passwd", "--prefix", prefix, "--delete", user],
        ]
    return commands


def run_account(argv, jail):
    stop_if_checking("run " + (argv[0] if argv else "an account command"))
    checked_account(argv, jail)
    account_log(" ".join(argv))
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    except OSError as exc:
        account_log(str(exc))
        raise AccountProblem("an account command could not be started") from exc
    if result.returncode != 0:
        account_log(result.stderr)
        raise AccountProblem("an account command failed")
    return result


def deployment_dir(mount, rev):
    if not REV_NAME.fullmatch(rev or ""):
        raise AccountProblem("the installed system has no deployment")
    try:
        deploy = path_inside(mount, ("ostree", "deploy", "default", "deploy", f"{rev}.0"))
    except GamesProblem as exc:
        raise AccountProblem("the installed system has no deployment") from exc
    if host_root(deploy) or deploy.is_symlink() or not deploy.is_dir():
        raise AccountProblem("the installed system has no deployment")
    if not deploy.resolve().is_relative_to(Path(mount).resolve()):
        raise AccountProblem("the installed system has no deployment")
    return deploy


def read_target_passwd(deploy, jail, user):
    path = walk_inside(deploy, jail, ("etc", "passwd"))
    if path.is_symlink() or not path.is_file():
        raise AccountProblem("the account list is missing")
    if not path.resolve().is_relative_to(Path(jail).resolve()):
        raise AccountProblem("a path left the new system")
    return passwd_record(path.read_text(errors="replace"), user)


def home_inside(deploy, jail, home, user):
    parts = Path(home).parts
    if not parts or parts[0] != "/" or parts[-1] != user:
        raise AccountProblem("the home directory is not usable")
    parent = walk_inside(deploy, jail, parts[1:-1])
    path = parent / user
    if path.is_symlink():
        raise AccountProblem("the home directory is a link")
    if host_root(path) or not path.resolve().is_relative_to(Path(jail).resolve()):
        raise AccountProblem("a path left the new system")
    return path


def make_home(path, jail):
    path = Path(path)
    if path.is_symlink() or host_root(path):
        raise AccountProblem("the home directory is a link")
    if path.exists() and not path.is_dir():
        raise AccountProblem("the home directory is not usable")
    if not path.exists():
        path.mkdir(mode=0o700)
        os.chmod(path, 0o700)
    if not path.is_dir() or not path.resolve().is_relative_to(Path(jail).resolve()):
        raise AccountProblem("a path left the new system")
    return path


def write_hostname(deploy, jail, hostname):
    if not HOST_NAME.fullmatch(hostname or ""):
        raise AccountProblem("the computer name is not usable")
    etc = ensure_dir(deploy, jail, ("etc",))
    write_exact(etc / "hostname", hostname + "\n", 0o644, jail)


def write_choices(deploy, jail, text):
    if not isinstance(text, str) or "\x00" in text or CHOICES_END in text:
        raise AccountProblem("the choice file must not contain a secret")
    try:
        parsed = json.loads(text)
        reject_secrets(parsed)
    except (json.JSONDecodeError, Refuse) as exc:
        raise AccountProblem("the choice file must not contain a secret") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("password"), bool):
        raise AccountProblem("the choice file must not contain a password")
    etc = ensure_dir(deploy, jail, ("etc", "wasd"))
    body = text if text.endswith("\n") else text + "\n"
    write_exact(etc / "choices.json", body, 0o644, jail)


def autologin_text(user):
    if not USER_NAME.fullmatch(user or "") or user == "root":
        raise AccountProblem("the username is not usable")
    return f"[Autologin]\nUser={user}\nSession=plasma\nRelogin=false\n"


def write_autologin(deploy, jail, user):
    body = autologin_text(user)
    for folder in ("plasmalogin.conf.d", "sddm.conf.d"):
        dest = ensure_dir(deploy, jail, ("etc", folder))
        write_exact(dest / "zz-wasd-autologin.conf", body, 0o644, jail)


def desktop_files(user):
    if not USER_NAME.fullmatch(user or "") or user == "root":
        raise AccountProblem("the username is not usable")
    autostart = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Completing the install\n"
        "Exec=/usr/bin/wasd-complete\n"
        "X-GNOME-Autostart-enabled=true\n"
        "OnlyShowIn=KDE;\n"
    )
    icon = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Completing the install\n"
        "Comment=Finish setting up this computer\n"
        "Exec=/usr/bin/wasd-complete\n"
        "Icon=wasd-logo\n"
        "Terminal=false\n"
    )
    return autostart, icon


def write_desktops(home, jail, user):
    autostart, icon = desktop_files(user)
    start_dir = ensure_dir(home, jail, (".config", "autostart"))
    desk_dir = ensure_dir(home, jail, ("Desktop",))
    write_exact(start_dir / "wasd-complete.desktop", autostart, 0o644, jail)
    write_exact(desk_dir / "wasd-complete.desktop", icon, 0o755, jail)


def read_nofollow(path, limit):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        return None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        blob = os.read(fd, limit + 1)
    finally:
        os.close(fd)
    if len(blob) > limit:
        return None
    return blob


def avatar_file(deploy, jail, avatar):
    if not avatar:
        return None
    if not FILE_NAME.fullmatch(avatar):
        raise AccountProblem("the account picture is not usable")
    folder = walk_inside(deploy, jail, ("usr", "share", "wasd", "icons"))
    if not folder.is_dir() or folder.is_symlink():
        return None
    source = folder / avatar
    if source.is_symlink() or not source.is_file():
        return None
    if not source.resolve().is_relative_to(folder.resolve()):
        return None
    return source


def copy_avatar(deploy, jail, user, avatar, home):
    source = avatar_file(deploy, jail, avatar)
    if source is None:
        return
    data = read_nofollow(source, 20 * 1024 * 1024)
    if data is None:
        return
    icons = ensure_dir(deploy, jail, ("var", "lib", "AccountsService", "icons"))
    users = ensure_dir(deploy, jail, ("var", "lib", "AccountsService", "users"))
    write_exact(icons / user, data, 0o644, jail)
    users_file = f"[User]\nIcon=/var/lib/AccountsService/icons/{user}\nSystemAccount=false\n"
    write_exact(users / user, users_file, 0o644, jail)
    write_exact(home / ".face", data, 0o644, jail)


def wifi_file_name(name):
    if not name or name in {".", ".."} or len(name) > 255:
        return False
    return "/" not in name and "\x00" not in name and "\n" not in name and "\r" not in name


def copy_wifi(source_dir, deploy, jail):
    """Copy saved connections. Secret lines are not written onto the disk."""
    source_dir = Path(source_dir)
    if host_root(jail) or not source_dir.is_dir() or source_dir.is_symlink():
        return
    files = []
    for item in source_dir.iterdir():
        if not wifi_file_name(item.name) or item.is_symlink() or not item.is_file():
            continue
        files.append(item)
    if not files:
        return
    dest = ensure_dir(deploy, jail, ("etc", "NetworkManager", "system-connections"))
    os.chmod(dest, 0o700)
    for item in files:
        blob = read_nofollow(item, 256 * 1024)
        if blob is None:
            continue
        cleaned = strip_secrets(blob.decode("utf-8", errors="replace"))
        if not cleaned.strip() or any(secret_line(line) for line in cleaned.splitlines()):
            continue
        write_exact(dest / item.name, cleaned, 0o600, jail)
    os.chmod(dest, 0o700)


def own_one(path, uid, gid, jail_path):
    path = Path(path)
    if path.is_symlink():
        if not path.parent.resolve().is_relative_to(jail_path):
            raise AccountProblem("a path left the new system")
    elif not path.resolve().is_relative_to(jail_path):
        raise AccountProblem("a path left the new system")
    if os.geteuid() != 0:
        return
    try:
        os.lchown(path, uid, gid)
    except OSError as exc:
        raise AccountProblem("the account files could not be given to the user") from exc


def own_tree(root, uid, gid, jail):
    if isinstance(uid, bool) or isinstance(gid, bool) or uid < 1000 or gid < 0:
        raise AccountProblem("the account id could not be read")
    root = Path(root)
    if root.is_symlink() or host_root(jail) or host_root(root):
        raise AccountProblem("the home directory is a link")
    jail_path = Path(jail).resolve()
    if not root.resolve().is_relative_to(jail_path):
        raise AccountProblem("a path left the new system")
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        if current.is_symlink() or not current.resolve().is_relative_to(jail_path):
            raise AccountProblem("a path left the new system")
        kept = []
        for name in dirnames:
            item = current / name
            if item.is_symlink():
                own_one(item, uid, gid, jail_path)
                continue
            if not item.resolve().is_relative_to(jail_path):
                raise AccountProblem("a path left the new system")
            kept.append(name)
        dirnames[:] = kept
        own_one(current, uid, gid, jail_path)
        for name in filenames:
            own_one(current / name, uid, gid, jail_path)


def apply_saved_look(deploy, home, user, data):
    # The startup picture is rebuilt on the first boot. Doing it here would
    # change the live system, or this computer.
    try:
        look = look_from(data)
    except LookError as exc:
        account_log("The look choices were saved. The first boot will apply them.")
        account_log(str(exc))
        return
    if look is None:
        return
    try:
        note = apply_look(Path(deploy), Path(home), user, look, session=False, rebuild=False)
    except (LookError, OSError) as exc:
        account_log("The look choices were saved. The first boot will apply them.")
        account_log(str(exc))
        return
    if note:
        account_log(note)


def place_account(deploy, jail, data, choices_text, wifi_source):
    """Write the account files. The user is already listed in the deployment."""
    if host_root(deploy) or host_root(jail):
        raise AccountProblem("the new system is not mounted")
    user = data.get("user") or ""
    record = read_target_passwd(deploy, jail, user)
    if record is None:
        raise AccountProblem("the account was not created")
    ensure_tree_links(deploy, jail)
    home = make_home(home_inside(deploy, jail, record["home"], user), jail)
    write_hostname(deploy, jail, data.get("hostname") or "")
    write_choices(deploy, jail, choices_text)
    write_autologin(deploy, jail, user)
    write_desktops(home, jail, user)
    copy_avatar(deploy, jail, user, data.get("avatar") or "", home)
    apply_saved_look(deploy, home, user, data)
    own_tree(home, record["uid"], record["gid"], jail)
    if wifi_source is not None:
        copy_wifi(wifi_source, deploy, jail)


def ensure_user(deploy, jail, user):
    existing = read_target_passwd(deploy, jail, user)
    for argv in account_commands(deploy, user, existing is not None):
        run_account(argv, jail)
    record = read_target_passwd(deploy, jail, user)
    if record is None:
        raise AccountProblem("the account was not created")
    return record


def write_account(os_device, data, choices_text, wifi_source=None):
    stop_if_checking("write the account")
    if not DEVICE_NAME.fullmatch(os_device or ""):
        raise AccountProblem("the disk name is not a whole disk")
    user = data.get("user") or ""
    if not USER_NAME.fullmatch(user) or user == "root":
        raise AccountProblem("the username is not usable")
    if host_root(SYSROOT):
        raise AccountProblem("the new system is not mounted")
    assert_not_live(os_device)
    root_name = only_root(typed_rows(os_device, read_table(os_device)))
    if wifi_source is None:
        wifi_source = WIFI_SOURCE
    fresh_mount(SYSROOT)
    mounted = False
    finished = False
    try:
        run_disk(["mount", "-t", "btrfs", f"/dev/{root_name}", str(SYSROOT)])
        mounted = True
        deploy = deployment_dir(SYSROOT, read_rev(SYSROOT))
        if host_root(deploy) or not deploy.resolve().is_relative_to(SYSROOT.resolve()):
            raise AccountProblem("the new system is not mounted")
        ensure_tree_links(deploy, SYSROOT)
        link_shared_var(deploy, SYSROOT)
        ensure_user(deploy, SYSROOT, user)
        place_account(deploy, SYSROOT, data, choices_text, wifi_source)
        finished = True
    finally:
        ok = quiet_umount(SYSROOT) if mounted else True
        if finished and not ok:
            raise AccountProblem("the new system stayed mounted")


def prepare_account(os_device, data, choices_text):
    stop_if_checking("prepare the account")
    try:
        write_account(os_device, data, choices_text)
    except AccountProblem as exc:
        account_log(str(exc))
        raise
    except (GamesProblem, OSError) as exc:
        account_log(str(exc))
        raise AccountProblem("the account was not set up") from exc


def redact(text):
    blob = str(text or "")
    if ENROLLMENT_PASSWORD in blob:
        return "output omitted"
    if len(blob) > 65536:
        return blob[:65536]
    return blob


def post_log(text):
    if os.environ.get("WASD_SELF_CHECK") == "1" or not text:
        return
    blob = redact(text)
    blob = blob if blob.endswith("\n") else blob + "\n"
    try:
        fd = os.open(POST_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    except OSError:
        return
    try:
        os.chmod(POST_LOG, 0o600)
        os.write(fd, blob.encode())
    except OSError:
        return
    finally:
        os.close(fd)


def require_live():
    if not is_live():
        raise PostProblem(UPDATES_FAILED)


def require_sysroot(jail):
    if host_root(jail) or Path(jail).resolve() != SYSROOT.resolve():
        raise PostProblem(UPDATES_FAILED)


def registry_image(source):
    """The registry name stored in the live image reference."""
    prefix = "containers-storage:"
    if not isinstance(source, str) or not source.startswith(prefix):
        raise PostProblem(UPDATES_FAILED)
    image = source[len(prefix):]
    switch_argv(image)
    return image


def switch_argv(image):
    """bootc switch for the installed system. It does not fetch or reboot."""
    if not isinstance(image, str) or not IMAGE_URL.fullmatch(image):
        raise PostProblem(UPDATES_FAILED)
    leaf = image.rsplit("/", 1)[-1]
    if (
        ".." in image
        or image.startswith("-")
        or "containers-storage" in image
        or (":" not in leaf and "@" not in image)
        or any(token in image for token in (" ", ";", "|", "&", "$", "`", "'", '"', "\\", "\n", "\x00"))
        or ENROLLMENT_PASSWORD in image
    ):
        raise PostProblem(UPDATES_FAILED)
    return [
        "bootc",
        "switch",
        "--mutate-in-place",
        "--transport",
        "registry",
        image,
    ]


def deployment_name_ok(path):
    path = Path(path)
    name = path.name
    if not name.endswith(".0") or not REV_NAME.fullmatch(name[:-2]):
        return False
    parts = path.parts
    return len(parts) >= 5 and parts[-5:-1] == ("ostree", "deploy", "default", "deploy")


def inside_sysroot(path, jail):
    target = Path(path).resolve()
    jail_path = Path(jail).resolve()
    if host_root(target) or host_root(jail_path) or target == jail_path:
        return False
    return target.is_relative_to(jail_path)


def checked_post(argv, jail):
    """Reject a post command that would change this computer or store the MOK password."""
    if not argv or any(not isinstance(item, str) or item == "" for item in argv):
        raise PostProblem(UPDATES_FAILED)
    if any(ENROLLMENT_PASSWORD in item for item in argv):
        raise PostProblem(UPDATES_FAILED)
    if any(item == "--apply" or item == "liveinst" or item.endswith("/liveinst") for item in argv):
        raise PostProblem(UPDATES_FAILED)
    if argv[0] == "bootc":
        raise PostProblem(UPDATES_FAILED)
    jail_path = Path(jail).resolve()
    if host_root(jail_path):
        raise PostProblem(UPDATES_FAILED)
    if argv[0] == "rsync":
        if len(argv) != len(RSYNC_APPS) + 2 or argv[: len(RSYNC_APPS)] != RSYNC_APPS:
            raise PostProblem(APPS_FAILED)
        if argv[-2] != str(FLATPAK_SOURCE):
            raise PostProblem(APPS_FAILED)
        dest = Path(argv[-1])
        if not dest.is_absolute() or dest.is_symlink() or not inside_sysroot(dest, jail_path):
            raise PostProblem(APPS_FAILED)
        resolved = dest.resolve()
        if str(resolved) == "/var/lib" or str(resolved).startswith("/var/lib/"):
            raise PostProblem(APPS_FAILED)
        if resolved == Path(FLATPAK_SOURCE).resolve() or str(resolved).startswith(str(FLATPAK_SOURCE) + "/"):
            raise PostProblem(APPS_FAILED)
        return argv
    if argv[0] == "sync":
        if len(argv) != 2 or not inside_sysroot(argv[1], jail_path):
            raise PostProblem(APPS_FAILED)
        return argv
    if argv[0] == "mount":
        if len(argv) != 4 or argv[1] != "--bind" or Path(argv[3]).is_symlink():
            raise PostProblem(UPDATES_FAILED)
        source = Path(argv[2]).resolve()
        target = Path(argv[3]).resolve()
        if source != jail_path or target.name != "sysroot" or not inside_sysroot(target, jail_path):
            raise PostProblem(UPDATES_FAILED)
        return argv
    if argv[0] == "umount":
        if len(argv) != 2 or Path(argv[1]).is_symlink() or not inside_sysroot(argv[1], jail_path):
            raise PostProblem(UPDATES_FAILED)
        if Path(argv[1]).resolve().name != "sysroot":
            raise PostProblem(UPDATES_FAILED)
        return argv
    if argv[0] == "chroot":
        if len(argv) < 3 or Path(argv[1]).is_symlink() or argv[2] != "bootc":
            raise PostProblem(UPDATES_FAILED)
        root = Path(argv[1]).resolve()
        if not deployment_name_ok(root) or not inside_sysroot(root, jail_path):
            raise PostProblem(UPDATES_FAILED)
        if argv[2:] != switch_argv(argv[-1]):
            raise PostProblem(UPDATES_FAILED)
        return argv
    if argv[0] == "setenforce":
        if argv != ["setenforce", "0"]:
            raise PostProblem(LABELS_FAILED)
        return argv
    if argv[0] == "setfiles":
        if len(argv) != 5 or argv[1] != "-r" or any(Path(item).is_symlink() for item in argv[2:]):
            raise PostProblem(LABELS_FAILED)
        root = Path(argv[2]).resolve()
        spec = Path(argv[3]).resolve()
        path = Path(argv[4]).resolve()
        if host_root(root) or not inside_sysroot(root, jail_path):
            raise PostProblem(LABELS_FAILED)
        if not inside_sysroot(spec, jail_path) or not inside_sysroot(path, jail_path):
            raise PostProblem(LABELS_FAILED)
        try:
            relative = path.relative_to(root)
        except ValueError as exc:
            raise PostProblem(LABELS_FAILED) from exc
        if relative.as_posix() not in {"etc/selinux", "var/lib/flatpak", "var/home", "var/lib/AccountsService"}:
            raise PostProblem(LABELS_FAILED)
        if spec.name != "file_contexts" or not spec.as_posix().endswith(
            "etc/selinux/targeted/contexts/files/file_contexts"
        ):
            raise PostProblem(LABELS_FAILED)
        return argv
    if argv[0] == "mokutil":
        allowed = (
            ["mokutil", "--timeout", "-1"],
            ["mokutil", "--import", str(SECUREBOOT_KEY)],
        )
        if argv not in allowed:
            raise PostProblem(UPDATES_FAILED)
        return argv
    raise PostProblem(UPDATES_FAILED)


def import_stdin():
    return ENROLLMENT_PASSWORD + "\n" + ENROLLMENT_PASSWORD + "\n"


def stdin_ok(argv, stdin_text):
    if argv[:2] == ["mokutil", "--import"]:
        return stdin_text == import_stdin()
    return stdin_text is None


def run_post(argv, jail, stdin_text=None, check=True):
    stop_if_checking("run " + (argv[0] if argv else "a post command"))
    require_live()
    require_sysroot(jail)
    checked_post(argv, SYSROOT)
    if not stdin_ok(argv, stdin_text):
        raise PostProblem(UPDATES_FAILED)
    if stdin_text is None:
        post_log(" ".join(argv))
    else:
        post_log("mokutil import input was not logged")
    try:
        if stdin_text is None:
            result = subprocess.run(
                argv,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
            )
        else:
            result = subprocess.run(argv, input=stdin_text, capture_output=True, text=True)
    except OSError as exc:
        post_log(redact(str(exc)))
        raise PostProblem("a post command failed") from exc
    if argv[0] != "mokutil":
        if result.stdout:
            post_log(redact(result.stdout))
        if result.stderr:
            post_log(redact(result.stderr))
    if check and result.returncode != 0:
        raise PostProblem("a post command failed")
    return result


def flatpak_dir(deploy, jail):
    """The shared var/lib on the new system. A link out of that system is refused."""
    try:
        dest = walk_inside(deploy, jail, ("var", "lib"))
    except AccountProblem as exc:
        raise PostProblem(APPS_FAILED) from exc
    if dest.is_symlink() or not dest.is_dir() or not inside_sysroot(dest, jail):
        raise PostProblem(APPS_FAILED)
    resolved = dest.resolve()
    if str(resolved) == "/var/lib" or str(resolved).startswith("/var/lib/"):
        raise PostProblem(APPS_FAILED)
    return resolved


def flatpak_argv(dest, jail):
    """Copy /var/lib/flatpak into the new system's var/lib.

    The source has to be named. One path makes rsync list that directory
    and exit 0, which copies nothing.
    """
    if Path(dest).is_symlink():
        raise PostProblem(APPS_FAILED)
    argv = [*RSYNC_APPS, str(FLATPAK_SOURCE), str(Path(dest).resolve())]
    checked_post(argv, jail)
    return argv


def copy_flatpak(deploy, jail):
    stop_if_checking("copy the installed apps")
    require_live()
    require_sysroot(jail)
    if FLATPAK_SOURCE.is_symlink() or not FLATPAK_SOURCE.is_dir():
        raise PostProblem(APPS_FAILED)
    try:
        ensure_dir(deploy, jail, ("var", "lib"))
        dest = flatpak_dir(deploy, jail)
        post_log("Copying installed apps.")
        run_post(flatpak_argv(dest, jail), jail)
        run_post(["sync", str(dest)], jail)
    except PostProblem as exc:
        if str(exc) == APPS_FAILED:
            raise
        post_log(redact(str(exc)))
        raise PostProblem(APPS_FAILED) from exc
    except (AccountProblem, OSError) as exc:
        post_log(redact(str(exc)))
        raise PostProblem(APPS_FAILED) from exc


def ensure_sysroot_dir(deploy, jail):
    """The directory bootc reads as /sysroot after the deployment is chrooted."""
    root = Path(deploy)
    if root.is_symlink() or host_root(root) or not root.resolve().is_relative_to(Path(jail).resolve()):
        raise PostProblem(UPDATES_FAILED)
    path = root / "sysroot"
    if path.is_symlink() or (path.exists() and not path.is_dir()) or os.path.ismount(path):
        raise PostProblem(UPDATES_FAILED)
    if not path.exists():
        path.mkdir(mode=0o755)
    if not path.is_dir() or path.is_symlink() or not inside_sysroot(path, jail):
        raise PostProblem(UPDATES_FAILED)
    return path.resolve()


def bind_argv(jail, target):
    if Path(target).is_symlink():
        raise PostProblem(UPDATES_FAILED)
    argv = ["mount", "--bind", str(Path(jail).resolve()), str(Path(target).resolve())]
    checked_post(argv, jail)
    return argv


def bootc_present(deploy, jail):
    try:
        folder = walk_inside(deploy, jail, ("usr", "bin"))
    except AccountProblem as exc:
        raise PostProblem(UPDATES_FAILED) from exc
    path = folder / "bootc"
    if path.is_symlink() or not path.is_file() or not inside_sysroot(path, jail):
        raise PostProblem(UPDATES_FAILED)
    return path


def chroot_argv(deploy, jail, source):
    """chroot into the deployment, then switch. The host's own bootc is not started."""
    original = Path(deploy)
    if original.is_symlink():
        raise PostProblem(UPDATES_FAILED)
    root = original.resolve()
    jail_path = Path(jail).resolve()
    if not deployment_name_ok(root) or not inside_sysroot(root, jail_path):
        raise PostProblem(UPDATES_FAILED)
    argv = ["chroot", str(root), *switch_argv(registry_image(source))]
    checked_post(argv, jail_path)
    return argv


def umount_bound(path):
    stop_if_checking("unmount the new system root")
    require_live()
    target = Path(path).resolve()
    argv = ["umount", str(target)]
    try:
        checked_post(argv, SYSROOT)
    except PostProblem:
        return False
    if not os.path.ismount(target):
        return True
    result = run_post(argv, SYSROOT, check=False)
    return result.returncode == 0


def point_updates(deploy, jail, source):
    """Point the new deployment at the registry image. This does not fetch it."""
    stop_if_checking("point later updates")
    require_live()
    require_sysroot(jail)
    bound = False
    switched = False
    target = None
    try:
        bootc_present(deploy, jail)
        target = ensure_sysroot_dir(deploy, jail)
        post_log("Pointing later updates at the registry image.")
        run_post(bind_argv(jail, target), jail)
        bound = True
        run_post(chroot_argv(deploy, jail, source), jail)
        switched = True
    except PostProblem as exc:
        if str(exc) == UPDATES_FAILED:
            raise
        post_log(redact(str(exc)))
        raise PostProblem(UPDATES_FAILED) from exc
    except (AccountProblem, OSError) as exc:
        post_log(redact(str(exc)))
        raise PostProblem(UPDATES_FAILED) from exc
    finally:
        unmounted = True
        if bound and target is not None:
            try:
                unmounted = umount_bound(target)
            except (PostProblem, OSError):
                unmounted = False
        if switched and not unmounted:
            raise PostProblem(UPDATES_FAILED)
    if not switched:
        raise PostProblem(UPDATES_FAILED)


def policy_spec(deploy, jail):
    """The installed policy's file contexts. A link out of the new system is refused."""
    current = Path(deploy).resolve()
    jail_path = Path(jail).resolve()
    if host_root(current) or not current.is_relative_to(jail_path):
        raise PostProblem(LABELS_FAILED)
    for part in ("etc", "selinux", "targeted", "contexts", "files", "file_contexts"):
        nxt = current / part
        if nxt.is_symlink():
            raise PostProblem(LABELS_FAILED)
        current = nxt
        if host_root(current) or not current.resolve().is_relative_to(jail_path):
            raise PostProblem(LABELS_FAILED)
    if not current.is_file():
        raise PostProblem(LABELS_FAILED)
    return current.resolve()


def label_paths(deploy, jail):
    """setfiles commands that label the new system as it will look after boot.

    The files are still mounted under the install tree. setfiles -r matches
    them against /etc/selinux, /var/lib/flatpak, /var/home, and the account
    picture directory. That is the same labeling restorecon does once that
    system is running. The home and the account picture are labeled when
    they are real directories. A missing avatar directory is left alone.
    """
    policy = policy_spec(deploy, jail)
    deploy_root = Path(deploy).resolve()
    etc = deploy_root / "etc" / "selinux"
    if etc.is_symlink() or not etc.is_dir() or not inside_sysroot(etc, jail):
        raise PostProblem(LABELS_FAILED)
    flatpak_parent = flatpak_dir(deploy, jail)
    flatpak = flatpak_parent / "flatpak"
    if flatpak.is_symlink() or not flatpak.is_dir() or not inside_sysroot(flatpak, jail):
        raise PostProblem(LABELS_FAILED)
    stateroot = flatpak_parent.parent.parent
    if (
        stateroot.is_symlink()
        or host_root(stateroot)
        or not inside_sysroot(stateroot, jail)
        or (stateroot / "var" / "lib" / "flatpak").resolve() != flatpak.resolve()
    ):
        raise PostProblem(LABELS_FAILED)
    commands = [
        setfiles_argv(deploy_root, policy, etc, jail),
        setfiles_argv(stateroot.resolve(), policy, flatpak, jail),
    ]
    for relative in ("var/home", "var/lib/AccountsService"):
        path = stateroot / relative
        if path.is_symlink() or not path.is_dir():
            continue
        if host_root(path) or not inside_sysroot(path, jail):
            raise PostProblem(LABELS_FAILED)
        commands.append(setfiles_argv(stateroot.resolve(), policy, path, jail))
    return commands


def setfiles_argv(root, spec, path, jail):
    if any(Path(item).is_symlink() for item in (root, spec, path)):
        raise PostProblem(LABELS_FAILED)
    argv = ["setfiles", "-r", str(Path(root).resolve()), str(Path(spec).resolve()), str(Path(path).resolve())]
    checked_post(argv, jail)
    return argv


def restore_labels(deploy, jail):
    """Relabel the policy store and the copied Flatpak tree.

    The caller still enrolls the key and creates the games partition when
    this fails. The window hears this failure when nothing earlier failed.
    """
    stop_if_checking("restore security labels")
    require_live()
    require_sysroot(jail)
    try:
        commands = label_paths(deploy, jail)
        # Labeling needs the live session permissive. The installed policy is unchanged.
        run_post(["setenforce", "0"], jail, check=False)
        for argv in commands:
            run_post(argv, jail)
    except PostProblem as exc:
        if str(exc) == LABELS_FAILED:
            raise
        post_log(redact(str(exc)))
        raise PostProblem(LABELS_FAILED) from exc
    except OSError as exc:
        post_log(redact(str(exc)))
        raise PostProblem(LABELS_FAILED) from exc


def efi_firmware():
    path = Path("/sys/firmware/efi")
    return path.is_dir() and not path.is_symlink()


def key_file_present():
    path = SECUREBOOT_KEY
    return path.is_file() and not path.is_symlink()


def product_name():
    path = Path("/sys/devices/virtual/dmi/id/product_name")
    if path.is_symlink() or not path.is_file():
        return ""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return ""
    try:
        return os.read(fd, 128).decode("utf-8", errors="replace").strip()
    finally:
        os.close(fd)


def enrollment_skipped(efi, key_present, product):
    if not efi or not key_present:
        return True
    return str(product or "").strip() in MOK_SKIP


def mokutil_commands(efi, key_present, product):
    if enrollment_skipped(efi, key_present, product):
        return []
    return [
        ["mokutil", "--timeout", "-1"],
        ["mokutil", "--import", str(SECUREBOOT_KEY)],
    ]


def enroll_secure_boot():
    """Ask the firmware to enroll the key. A failure here does not stop the install."""
    stop_if_checking("enroll a key")
    require_live()
    try:
        if enrollment_skipped(efi_firmware(), key_file_present(), product_name()):
            post_log("Secure Boot enrollment was skipped.")
            return
        run_post(["mokutil", "--timeout", "-1"], SYSROOT, check=False)
        imported = run_post(
            ["mokutil", "--import", str(SECUREBOOT_KEY)],
            SYSROOT,
            stdin_text=import_stdin(),
            check=False,
        )
        if imported.returncode != 0:
            post_log("Secure Boot enrollment did not finish.")
            return
        post_log("Secure Boot enrollment finished.")
    except (PostProblem, OSError) as exc:
        post_log("Secure Boot enrollment was skipped.")
        post_log(redact(str(exc)))


def write_post(os_device, source):
    """Copy apps, point updates, restore labels, then enroll the key.

    The app copy has to succeed before the update step and the labels.
    An update failure still restores labels and still enrolls the key.
    The caller creates the games partition after this, then shows the
    first failure. The USB sentence is not printed.
    """
    stop_if_checking("write the installed system")
    require_live()
    registry_image(source)
    if not DEVICE_NAME.fullmatch(os_device or "") or host_root(SYSROOT):
        raise PostProblem(APPS_FAILED)
    assert_not_live(os_device)
    fresh_mount(SYSROOT)
    mounted = False
    copied = False
    failure = None
    try:
        root_name = only_root(typed_rows(os_device, read_table(os_device)))
        run_disk(["mount", "-t", "btrfs", f"/dev/{root_name}", str(SYSROOT)])
        mounted = True
        deploy = deployment_dir(SYSROOT, read_rev(SYSROOT))
        if host_root(deploy) or not deploy.resolve().is_relative_to(SYSROOT.resolve()):
            raise PostProblem(APPS_FAILED)
        try:
            copy_flatpak(deploy, SYSROOT)
            copied = True
        except PostProblem:
            failure = APPS_FAILED
        if copied:
            try:
                point_updates(deploy, SYSROOT, source)
            except PostProblem:
                if failure is None:
                    failure = UPDATES_FAILED
            try:
                restore_labels(deploy, SYSROOT)
            except PostProblem:
                if failure is None:
                    failure = LABELS_FAILED
    except PostProblem:
        raise
    except (GamesProblem, AccountProblem, OSError) as exc:
        post_log(redact(str(exc)))
        if failure is None:
            failure = APPS_FAILED
    finally:
        root_ok = quiet_umount(SYSROOT) if mounted else True
        if failure is None and mounted and not root_ok:
            failure = UPDATES_FAILED
    if mounted:
        try:
            enroll_secure_boot()
        except PostProblem as exc:
            post_log(redact(str(exc)))
            if failure is None:
                failure = UPDATES_FAILED
    if failure:
        raise PostProblem(failure)


def finish_post(os_device, source):
    stop_if_checking("finish the installed system")
    try:
        write_post(os_device, source)
    except PostProblem:
        raise
    except (GamesProblem, AccountProblem, OSError) as exc:
        post_log(redact(str(exc)))
        raise PostProblem(APPS_FAILED) from exc


def sample_table(lastlba, parts, sectorsize=512):
    return {
        "partitiontable": {
            "label": "gpt",
            "device": "/dev/nvme0n1",
            "unit": "sectors",
            "firstlba": 34,
            "lastlba": lastlba,
            "sectorsize": sectorsize,
            "partitions": parts,
        }
    }


def check_games():
    """Check the games plan. This does not run sfdisk, mkfs, mount, or bootc."""
    if set(STAGE_LINES) != {"prepare", "copy", "account", "boot", "done"}:
        raise SystemExit(f"status lines changed: {sorted(STAGE_LINES)}")
    if "Nothing was erased." in GAMES_FAILED or "Setting up your account." in GAMES_FAILED:
        raise SystemExit("the games failure used the wrong sentence")
    if games_needed({"mode": "off"}) or games_needed({}) or not games_needed({"mode": "split"}):
        raise SystemExit("games_needed was wrong")
    if not games_needed({"mode": "keep"}) or not games_needed({"mode": "format"}):
        raise SystemExit("a games drive was skipped")
    finish_games("nvme0n1", {"mode": "off"})

    root_end = 269488128
    last = 1000000000
    parts = [
        {"node": "/dev/nvme0n1p1", "start": 2048, "size": 2048},
        {"node": "/dev/nvme0n1p2", "start": 4096, "size": 1048576},
        {"node": "/dev/nvme0n1p3", "start": 1052672, "size": root_end - 1052672},
    ]
    start, size = free_tail(sample_table(last, parts))
    if start != root_end or size != last - root_end + 1:
        raise SystemExit(f"free tail was {start} {size}")
    if size * 512 < MIN_GAMES_GB * (1024 ** 3):
        raise SystemExit("the sample tail is below 32 GB")
    argv, script = split_request("nvme0n1", start, size)
    if argv != ["sfdisk", "--append", "--lock", "/dev/nvme0n1"]:
        raise SystemExit(f"split command was {argv}")
    if script != f"start={start}, size={size}, type=linux, name=games\n":
        raise SystemExit(f"split script was {script}")
    if "--wipe" in argv or "nvme0n1p" in script or "/dev" in script:
        raise SystemExit("the split script named a partition or wiped the disk")
    try:
        split_request("nvme0n1", True, 10)
    except GamesProblem:
        pass
    else:
        raise SystemExit("a split start of true was accepted")
    try:
        split_request("sda1", 2048, 10)
    except GamesProblem:
        pass
    else:
        raise SystemExit("a partition was accepted as the split disk")

    hole_end = 4096 + (40 * (1024 ** 3)) // 512
    align = 2048
    if hole_end % align:
        hole_end += align - (hole_end % align)
    p2_size = 2048
    p2_end = hole_end + p2_size
    hole_parts = [
        {"node": "/dev/nvme0n1p1", "start": 2048, "size": 2048},
        {"node": "/dev/nvme0n1p2", "start": hole_end, "size": p2_size},
    ]
    try:
        free_tail(sample_table(p2_end + align - 1, hole_parts))
    except GamesProblem:
        pass
    else:
        raise SystemExit("a hole was used as the games partition")

    sectorsize = 4096
    fourk_align = (1024 * 1024) // sectorsize
    fourk_end = 1000
    fourk_start = ((fourk_end + fourk_align - 1) // fourk_align) * fourk_align
    fourk_size = (32 * (1024 ** 3)) // sectorsize
    fourk_last = fourk_start + fourk_size - 1
    got_start, got_size = free_tail(
        sample_table(
            fourk_last,
            [{"node": "/dev/nvme0n1p1", "start": 256, "size": fourk_end - 256}],
            sectorsize,
        )
    )
    if got_start != fourk_start or got_size != fourk_size:
        raise SystemExit(f"4k free tail was {got_start} {got_size}")

    rows = [
        {"name": "nvme0n1p1", "fstype": "vfat"},
        {"name": "nvme0n1p3", "fstype": "btrfs"},
    ]
    if only_root(rows) != "nvme0n1p3":
        raise SystemExit("the WASD filesystem was not the only btrfs partition")
    for bad_rows in (rows + [{"name": "nvme0n1p4", "fstype": "btrfs"}], [{"name": "nvme0n1", "fstype": "btrfs"}], []):
        try:
            only_root(bad_rows)
        except GamesProblem:
            pass
        else:
            raise SystemExit(f"a bad filesystem list was accepted: {bad_rows}")

    before = ["nvme0n1p1", "nvme0n1p2", "nvme0n1p3"]
    big = 40 * (1024 ** 3)
    after = [
        {"name": "nvme0n1p1", "fstype": "vfat", "bytes": 10 ** 9},
        {"name": "nvme0n1p2", "fstype": "", "bytes": 10 ** 8},
        {"name": "nvme0n1p3", "fstype": "btrfs", "bytes": 10 ** 11},
        {"name": "nvme0n1p4", "fstype": "", "bytes": big},
    ]
    if new_partition(before, after, "nvme0n1", "nvme0n1p3") != "nvme0n1p4":
        raise SystemExit("the new games partition was not taken from the new table")
    other_disk = list(after)
    other_disk[-1] = {"name": "nvme0n10p1", "fstype": "", "bytes": big}
    two = list(after) + [{"name": "nvme0n1p5", "fstype": "", "bytes": big}]
    typed = list(after)
    typed[-1] = {"name": "nvme0n1p4", "fstype": "btrfs", "bytes": big}
    tiny = list(after)
    tiny[-1] = {"name": "nvme0n1p4", "fstype": "", "bytes": 1024 ** 3}
    for bad in (other_disk, two, typed, tiny):
        try:
            new_partition(before, bad, "nvme0n1", "nvme0n1p3")
        except GamesProblem:
            pass
        else:
            raise SystemExit(f"a bad new partition was accepted: {bad[-1]}")

    wipe, table_argv, format_script, mkfs = format_commands("nvme0n1", "nvme1n1")
    if wipe != ["wipefs", "-a", "/dev/nvme1n1"] or table_argv != ["sfdisk", "--wipe", "always", "--lock", "/dev/nvme1n1"]:
        raise SystemExit(f"format commands were {wipe} {table_argv}")
    if format_script != "label: gpt\ntype=linux, name=games\n":
        raise SystemExit(f"format script was {format_script}")
    if mkfs != ["mkfs.btrfs", "-f", "-L", "games", "/dev/nvme1n1p1"]:
        raise SystemExit(f"mkfs command was {mkfs}")
    if mentions(wipe + table_argv + mkfs, "nvme0n1") or mkfs[-1] in {"/dev/nvme0n1", "/dev/nvme1n1"}:
        raise SystemExit("the format command targeted the WASD disk or a whole disk")
    wide, _, _, wide_mkfs = format_commands("nvme0n1", "nvme0n10")
    if wide_mkfs[-1] != "/dev/nvme0n10p1" or mentions(wide, "nvme0n1"):
        raise SystemExit("nvme0n1 was confused with nvme0n10")
    sd_wipe, _, _, sd_mkfs = format_commands("sda", "sdb")
    if sd_mkfs != ["mkfs.btrfs", "-f", "-L", "games", "/dev/sdb1"] or mentions(sd_wipe + sd_mkfs, "sda"):
        raise SystemExit(f"an sd format was {sd_mkfs}")
    try:
        format_commands("nvme0n1", "nvme0n1")
    except GamesProblem:
        pass
    else:
        raise SystemExit("the WASD disk was formatted as games")
    lone = {
        "partitiontable": {
            "sectorsize": 512,
            "partitions": [{"node": "/dev/sdb1", "start": 2048, "size": 100}],
        }
    }
    if lone_partition(lone, "sdb") != "sdb1":
        raise SystemExit("the formatted drive's only partition was not used")

    kept = fstab_line("01234567-89AB-CDEF-0123-456789ABCDEF", "ntfs3")
    if kept != "UUID=01234567-89ab-cdef-0123-456789abcdef /games ntfs3 defaults,nofail 0 0\n":
        raise SystemExit(f"fstab line was {kept}")
    if "mkfs" in kept or "sfdisk" in kept:
        raise SystemExit("keep would format the drive")
    try:
        fstab_line("01234567-89ab-cdef-0123-456789abcdef", "ntfs")
    except GamesProblem:
        pass
    else:
        raise SystemExit("ntfs was mounted without the ntfs3 driver")

    import inspect

    kept_body = inspect.getsource(add_kept_games)
    if "mkfs" in kept_body or "sfdisk" in kept_body or "wipefs" in kept_body:
        raise SystemExit("keep would erase the games drive")
    split_body = inspect.getsource(add_split_games)
    if "wipefs" in split_body or "--wipe" in split_body:
        raise SystemExit("the split wipes the WASD disk")

    uuid = "01234567-89ab-cdef-0123-456789abcdef"
    with tempfile.TemporaryDirectory(prefix="wasd-games-check-", dir="/tmp") as tmp:
        root = Path(tmp) / "sys"
        root.mkdir()
        etc = root / "etc"
        etc.mkdir()
        fstab = etc / "fstab"
        fstab.write_text("UUID=old / btrfs defaults 0 0\n")
        line = fstab_line(uuid, "btrfs")
        if not append_fstab(fstab, line, root):
            raise SystemExit("fstab was not updated")
        if append_fstab(fstab, line, root):
            raise SystemExit("fstab was updated twice")
        if fstab.read_text().count(" /games ") != 1:
            raise SystemExit("fstab line was doubled")
        outside = Path(tmp) / "out"
        outside.mkdir()
        secret = outside / "fstab"
        secret.write_text("keep\n")
        link = root / "escape"
        link.symlink_to(outside)
        try:
            append_fstab(link / "fstab", line, root)
        except GamesProblem:
            pass
        else:
            raise SystemExit("a filesystem table outside the new system was changed")
        if secret.read_text() != "keep\n":
            raise SystemExit("a filesystem table outside the new system was changed")
        rev = "ab" * 32
        expect = (root / "ostree/deploy/default/deploy" / f"{rev}.0" / "etc/fstab").resolve()
        if deployment_fstab(root, rev) != expect:
            raise SystemExit(f"the deployment fstab path was {deployment_fstab(root, rev)}")
        try:
            deployment_fstab(root, "AB" * 32)
        except GamesProblem:
            pass
        else:
            raise SystemExit("a deployment id was accepted")
        (root / "ostree").symlink_to(outside)
        try:
            deployment_fstab(root, rev)
        except GamesProblem:
            pass
        else:
            raise SystemExit("a deployment path left the new system")
        try:
            path_inside(root, ("..",))
        except GamesProblem:
            pass
        else:
            raise SystemExit("a parent path was accepted")

    source = "containers-storage:example:latest"
    argv = bootc_argv("nvme0n1", {"mode": "off"}, source)

    def quiet_success(command, on_line):
        if command != argv:
            raise SystemExit(f"bootc was started with {command}")
        on_line("Installing bootloader via bootupd\n")
        return 0, "Installing bootloader via bootupd\n"

    def fail_games():
        raise GamesProblem("planner")

    spoken = []
    try:
        run_bootc(argv, "abcd1234efgh5678", quiet_success, spoken, finish=fail_games)
    except Started as exc:
        if str(exc) != GAMES_FAILED or "done" in spoken:
            raise SystemExit(f"a games failure was {exc} after {spoken}") from exc
    else:
        raise SystemExit("a games failure printed the USB line")
    if spoken != ["copy", "boot"]:
        raise SystemExit(f"games failure stages were {spoken}")

    def fail_late():
        raise Refuse("Choose a disk again. Nothing was erased.")

    spoken = []
    try:
        run_bootc(argv, "abcd1234efgh5678", quiet_success, spoken, finish=fail_late)
    except Started as exc:
        if str(exc) != GAMES_FAILED or "Nothing was erased." in str(exc):
            raise SystemExit(f"a late refusal was {exc}") from exc
    else:
        raise SystemExit("a late refusal said the disk was untouched")
    if spoken != ["copy", "boot"]:
        raise SystemExit(f"late refusal stages were {spoken}")

    def fail_os():
        raise OSError("disk")

    spoken = []
    try:
        run_bootc(argv, "abcd1234efgh5678", quiet_success, spoken, finish=fail_os)
    except Started as exc:
        if str(exc) != GAMES_FAILED or "done" in spoken:
            raise SystemExit(f"a games OSError was {exc} after {spoken}") from exc
    else:
        raise SystemExit("a games OSError printed the USB line")
    if spoken != ["copy", "boot"]:
        raise SystemExit(f"games OSError stages were {spoken}")

    seen = {}

    def record():
        seen["boot"] = "boot" in spoken
        seen["done"] = "done" in spoken

    spoken = []
    run_bootc(argv, "abcd1234efgh5678", quiet_success, spoken, finish=record)
    if spoken != ["copy", "boot", "done"] or not seen.get("boot") or seen.get("done"):
        raise SystemExit(f"games ran at the wrong time: {spoken} {seen}")
    if started_line(Started(GAMES_FAILED)) != GAMES_FAILED or started_line(Started("  ")) != WIPED_LINE:
        raise SystemExit("a wiped failure lost its sentence")
    if started_line(Started(WIPED_LINE)) != WIPED_LINE:
        raise SystemExit("a wiped failure changed its sentence")

    guards = (
        (lambda: prepare_games("nvme0n1", {"mode": "split"}), "prepare"),
        (lambda: add_split_games("nvme0n1", {"mode": "split"}), "split"),
        (lambda: add_formatted_games("nvme0n1", {"mode": "format", "device": "nvme1n1"}), "format"),
        (
            lambda: add_kept_games(
                "nvme0n1",
                {
                    "mode": "keep",
                    "device": "nvme1n1",
                    "part": "nvme1n1p1",
                    "uuid": uuid,
                    "fstype": "btrfs",
                },
            ),
            "keep",
        ),
        (lambda: make_btrfs("nvme0n1p4"), "mkfs"),
        (lambda: attach_games("nvme0n1p3", uuid, "btrfs"), "attach"),
        (lambda: mount_library(GAMES_MOUNT), "library"),
        (lambda: read_table("nvme0n1"), "table"),
        (lambda: read_rev(SYSROOT), "rev"),
        (lambda: fs_uuid("nvme0n1p4"), "uuid"),
        (lambda: fs_type("nvme0n1p4"), "type"),
        (lambda: assert_not_live("nvme0n1"), "live"),
        (lambda: quiet_umount(SYSROOT), "umount"),
        (lambda: run_disk(["sfdisk", "--json", "/dev/nvme0n1"]), "sfdisk"),
    )
    for call, label in guards:
        try:
            call()
        except SystemExit as exc:
            if "self-check" not in str(exc):
                raise SystemExit(f"{label} stopped for another reason: {exc}") from exc
        else:
            raise SystemExit(f"{label} ran a disk command during self-check")
    try:
        finish_games("nvme0n1", {"mode": "split", "osGb": 128, "gamesGb": 32})
    except SystemExit as exc:
        if "self-check" not in str(exc):
            raise SystemExit(f"a split finish stopped for another reason: {exc}") from exc
    else:
        raise SystemExit("a split finish ran a disk command during self-check")


def check_account():
    """Check the account plan. This does not run useradd, mount, or bootc."""
    import inspect

    if "Nothing was erased." in ACCOUNT_FAILED or "The games partition" in ACCOUNT_FAILED:
        raise SystemExit("the account failure used the wrong sentence")
    if STAGE_LINES.get("account") != "Setting up your account.":
        raise SystemExit("the account line is missing")
    raw_wifi = (
        "key-mgmt=wpa-psk\n"
        "psk=super-secret\n"
        "password=also-secret\n"
        "WEP-KEY0=abc\n"
        "wep-key-type=1\n"
        "ssid=Home\n"
        "password-flags=0\n"
    )
    cleaned = strip_secrets(raw_wifi)
    if any(secret_line(line) for line in cleaned.splitlines()):
        raise SystemExit(f"a secret stayed in the keyfile: {cleaned}")
    if "super-secret" in cleaned or "also-secret" in cleaned or "psk=" in cleaned:
        raise SystemExit(f"a secret stayed in the keyfile: {cleaned}")
    for kept in ("ssid=Home", "key-mgmt=wpa-psk", "wep-key-type=1", "password-flags=0"):
        if kept not in cleaned:
            raise SystemExit(f"a wifi field was removed: {cleaned}")
    record = passwd_record("alex:x:1000:1000:Alex:/home/alex:/bin/bash\n", "alex")
    if record != {"uid": 1000, "gid": 1000, "home": "/home/alex"}:
        raise SystemExit(f"the account record was {record}")
    for bad_passwd in (
        "alex:x:0:0:Alex:/home/alex:/bin/bash\n",
        "alex:x:1000:1000:Alex:/home/../alex:/bin/bash\n",
        "alex:x:1000:1000:Alex:/root:/bin/bash\n",
        "alex:x:1000:1000:Alex:/home/alex:/bin/bash\nalex:x:1001:1001:Alex:/home/alex:/bin/bash\n",
    ):
        try:
            passwd_record(bad_passwd, "alex")
        except AccountProblem:
            pass
        else:
            raise SystemExit(f"a bad account record was accepted: {bad_passwd!r}")
    for name, func in (
        ("apply_saved_look", apply_saved_look),
        ("copy_wifi", copy_wifi),
        ("write_account", write_account),
        ("place_account", place_account),
        ("prepare_account", prepare_account),
        ("account_commands", account_commands),
    ):
        body = inspect.getsource(func)
        if "nmcli" in body or "rpm-ostree" in body or "rebuild=True" in body:
            raise SystemExit(f"{name} touches the running system")
    install_body = inspect.getsource(install)
    if "prepare_account" not in install_body or "finish_games" not in install_body:
        raise SystemExit("install does not set up the account")
    if "rebuild=True" in install_body or "nmcli" in install_body:
        raise SystemExit("install touches the running system")
    boot_body = inspect.getsource(run_bootc)
    if boot_body.count('announce_stage(status_id, "boot"') != 1:
        raise SystemExit("the bootloader line is spoken from the log")
    host_passwd = Path("/etc/passwd").read_bytes()
    host_name = Path("/etc/hostname").read_bytes() if Path("/etc/hostname").is_file() else None
    rev = "ab" * 32
    with tempfile.TemporaryDirectory(prefix="wasd-account-") as tmp:
        jail = Path(tmp)
        deploy = jail / "ostree/deploy/default/deploy" / f"{rev}.0"
        shared = jail / "ostree/deploy/default/var"
        (shared / "home").mkdir(parents=True)
        deploy.mkdir(parents=True)
        (deploy / "var").symlink_to("../../var")
        (deploy / "home").symlink_to("var/home")
        link_shared_var(deploy, jail)
        if not (deploy / "var").is_symlink() or (deploy / "var").resolve() != shared.resolve():
            raise SystemExit("the shared var symlink was replaced")
        hidden = jail / "ostree/deploy/default/deploy" / f"{'ab' * 32}.hidden"
        hidden.mkdir()
        (hidden / "var").mkdir()
        (hidden / "var" / "marker").write_text("hide")
        (hidden / "home").symlink_to("var/home")
        link_shared_var(hidden, jail)
        if not (hidden / "var").is_symlink() or (hidden / "var").resolve() != shared.resolve():
            raise SystemExit("a real deployment var was left in place")
        if (hidden / "var" / "marker").exists():
            raise SystemExit("the hidden var was kept")
        if not (shared / "home").is_dir():
            raise SystemExit("the shared home was removed")
        (deploy / "etc").mkdir()
        (deploy / "etc/passwd").write_text("alex:x:1000:1000:Alex:/home/alex:/bin/bash\n")
        icons = deploy / "usr/share/wasd/icons"
        icons.mkdir(parents=True)
        (icons / "knight.jpg").write_bytes(b"icon-bytes")
        found = deployment_dir(jail, rev)
        if found.resolve() != deploy.resolve():
            raise SystemExit(f"the deployment path was {found}")
        if deployment_rev(jail) != rev:
            raise SystemExit("the deployment directory was not read")
        (deploy.parent / f"{'cd' * 32}.0").mkdir()
        try:
            deployment_rev(jail)
        except GamesProblem:
            pass
        else:
            raise SystemExit("two deployments were accepted")
        (deploy.parent / f"{'cd' * 32}.0").rmdir()
        link = deploy.parent / f"{'ef' * 32}.0"
        link.symlink_to(deploy.name)
        if deployment_rev(jail) != rev:
            raise SystemExit("a deployment link was followed")
        link.unlink()
        lookup = inspect.getsource(read_rev) + inspect.getsource(deployment_rev)
        if "ostree/0/" in lookup or "ostree/1/" in lookup or "rev-parse" in lookup:
            raise SystemExit("the deployment lookup uses a fixed name")
        try:
            deployment_dir(jail, "AB" * 32)
        except AccountProblem:
            pass
        else:
            raise SystemExit("a deployment id was accepted")
        try:
            walk_inside(jail, jail, ("..",))
        except AccountProblem:
            pass
        else:
            raise SystemExit("a parent path was accepted")
        home = home_inside(deploy, jail, "/home/alex", "alex")
        expect_home = shared / "home/alex"
        if home.resolve() != expect_home.resolve():
            raise SystemExit(f"home followed the wrong link: {home}")
        try:
            home_inside(deploy, jail, "/home/../alex", "alex")
        except AccountProblem:
            pass
        else:
            raise SystemExit("a parent home was accepted")
        bad = jail / "bad-deploy"
        bad.mkdir()
        (bad / "var").symlink_to("/tmp")
        try:
            ensure_tree_links(bad, jail)
        except AccountProblem:
            pass
        else:
            raise SystemExit("a var link left the new system")
        try:
            write_choices(deploy, jail, json.dumps({"password": "secret", "user": "alex"}))
        except AccountProblem:
            pass
        else:
            raise SystemExit("a password string was written")
        leaked = deploy / "etc/wasd/choices.json"
        if leaked.exists() and "secret" in leaked.read_text():
            raise SystemExit("a password string was written")
        try:
            write_choices(
                deploy,
                jail,
                json.dumps({"password": True, "wifi": {"ssid": "Home", "passphrase": "nope"}}),
            )
        except AccountProblem:
            pass
        else:
            raise SystemExit("a wifi passphrase was written")
        prefix = str(deploy.resolve())
        created = account_commands(deploy, "alex", False)
        existing = account_commands(deploy, "alex", True)
        if created[0] != ["useradd", "--prefix", prefix, "--create-home", "--groups", "wheel", "alex"]:
            raise SystemExit(f"useradd was {created[0]}")
        if created[1] != ["passwd", "--prefix", prefix, "--delete", "alex"]:
            raise SystemExit(f"passwd was {created[1]}")
        if existing[0][0] != "usermod" or "--create-home" in existing[0] or "--password" in existing[0]:
            raise SystemExit(f"usermod was {existing[0]}")
        for argv in created + existing:
            checked_account(argv, jail)
            if any(item in {"-p", "--password", "--stdin", "-s", "--root", "-R"} for item in argv):
                raise SystemExit(f"an account command stores a password: {argv}")
        for bad_argv in (
            ["useradd", "--prefix", prefix, "--password", "secret", "alex"],
            ["passwd", "--prefix", prefix, "--stdin", "alex"],
            ["passwd", "--prefix", prefix, "-s", "alex"],
            ["useradd", "--root", prefix, "--create-home", "--groups", "wheel", "alex"],
            ["passwd", "--prefix", "/", "--delete", "alex"],
            ["passwd", "--prefix", "/etc", "--delete", "alex"],
            ["passwd", "--prefix", prefix, "--delete", "root"],
        ):
            try:
                checked_account(bad_argv, jail)
            except AccountProblem:
                pass
            else:
                raise SystemExit(f"an account command was accepted: {bad_argv}")
        choices = {
            "disk": "Disk",
            "device": "nvme0n1",
            "hostname": "wasd",
            "user": "alex",
            "avatar": "knight.jpg",
            "password": True,
            "loading": "stained-glass.jpg",
            "login": "throne.jpg",
            "theme": "We10XOS-dark",
            "wallpaper": "stained-glass.jpg",
            "wifi": {"ssid": "Home", "security": "WPA2", "hidden": False},
            "apps": [],
            "agents": [],
        }
        text = json.dumps(choices, indent=2)
        wifi_dir = jail / "live-wifi"
        wifi_dir.mkdir()
        secret_note = jail / "secret-note"
        secret_note.write_text("psk=do-not-copy\n")
        (wifi_dir / "Home.nmconnection").write_text(raw_wifi)
        (wifi_dir / "link.nmconnection").symlink_to(secret_note)
        passwd_before = (deploy / "etc/passwd").read_bytes()
        place_account(deploy, jail, choices, text, wifi_dir)
        if (deploy / "etc/passwd").read_bytes() != passwd_before:
            raise SystemExit("the deployment account list was rewritten without useradd")
        if not (deploy / "var").is_symlink():
            raise SystemExit("the shared var was replaced")
        if (deploy / "etc/hostname").read_text() != "wasd\n":
            raise SystemExit("the computer name was not written")
        saved = json.loads((deploy / "etc/wasd/choices.json").read_text())
        if saved.get("password") is not True or "passphrase" in json.dumps(saved) or "psk" in json.dumps(saved):
            raise SystemExit("the choice file stored a secret")
        if (deploy / "etc/wasd/choices.json").stat().st_mode & 0o777 != 0o644:
            raise SystemExit("the choice file has the wrong mode")
        login_a = (deploy / "etc/plasmalogin.conf.d/zz-wasd-autologin.conf").read_text()
        login_b = (deploy / "etc/sddm.conf.d/zz-wasd-autologin.conf").read_text()
        if login_a != login_b or "User=alex" not in login_a or "Session=plasma" not in login_a:
            raise SystemExit("automatic sign-in was not written")
        if "password" in login_a.lower():
            raise SystemExit("automatic sign-in stored a password")
        auto = deploy / "home/alex/.config/autostart/wasd-complete.desktop"
        icon = deploy / "home/alex/Desktop/wasd-complete.desktop"
        # Follow the home link. The files have to land in the shared var.
        if auto.resolve() != (shared / "home/alex/.config/autostart/wasd-complete.desktop").resolve():
            raise SystemExit(f"the startup entry missed the shared home: {auto.resolve()}")
        if "Completing the install" not in auto.read_text() or "OnlyShowIn=KDE;" not in auto.read_text():
            raise SystemExit("the startup entry is wrong")
        if icon.stat().st_mode & 0o777 != 0o755 or auto.stat().st_mode & 0o777 != 0o644:
            raise SystemExit("a desktop file has the wrong mode")
        if "Finish setting up this computer" not in icon.read_text() or "wasd-logo" not in icon.read_text():
            raise SystemExit("the desktop icon is wrong")
        face = shared / "home/alex/.face"
        service = shared / "lib/AccountsService/icons/alex"
        if face.read_bytes() != b"icon-bytes" or service.read_bytes() != b"icon-bytes":
            raise SystemExit("the account picture was not copied")
        if face.is_symlink() or service.is_symlink():
            raise SystemExit("the account picture is a link")
        users = (shared / "lib/AccountsService/users/alex").read_text()
        if "Icon=/var/lib/AccountsService/icons/alex" not in users:
            raise SystemExit("the login picture path is wrong")
        copied = deploy / "etc/NetworkManager/system-connections/Home.nmconnection"
        wifi_text = copied.read_text()
        if copied.stat().st_mode & 0o777 != 0o600:
            raise SystemExit("the wifi keyfile has the wrong mode")
        if copied.parent.stat().st_mode & 0o777 != 0o700:
            raise SystemExit("the wifi folder has the wrong mode")
        if "super-secret" in wifi_text or "psk=" in wifi_text or secret_line(wifi_text):
            raise SystemExit("the wifi passphrase was written onto the new system")
        if "ssid=Home" not in wifi_text:
            raise SystemExit("the wifi name was not copied")
        if (copied.parent / "link.nmconnection").exists():
            raise SystemExit("a linked wifi file was copied")
        if secret_note.read_text() != "psk=do-not-copy\n":
            raise SystemExit("a secret note outside the new system was changed")
        src = icons / "knight.jpg"
        src.unlink()
        src.symlink_to("/etc/hostname")
        before_face = face.read_bytes()
        copy_avatar(deploy, jail, "alex", "knight.jpg", face.parent)
        if face.read_bytes() != before_face:
            raise SystemExit("a linked picture was copied")
        if avatar_file(deploy, jail, "") is not None:
            raise SystemExit("an empty picture was installed")
        apply_saved_look(deploy, face.parent, "alex", {"user": "alex", "password": True})
    if Path("/etc/passwd").read_bytes() != host_passwd:
        raise SystemExit("the host account list changed")
    if host_name is not None and Path("/etc/hostname").read_bytes() != host_name:
        raise SystemExit("the host name changed")
    status = "abcd1234efgh5678"
    argv = bootc_argv("nvme0n1", {"mode": "off"}, "containers-storage:example:latest")

    def watch(command, on_line):
        if command != argv:
            raise SystemExit(f"bootc was started with {command}")
        on_line("Installing bootloader via bootupd\n")
        if "boot" in spoken or "account" in spoken or "done" in spoken:
            raise SystemExit(f"a log line moved the window: {spoken}")
        return 0, "Installing bootloader via bootupd\n"

    seen = {}

    def mark():
        if spoken != ["copy"]:
            raise SystemExit(f"the account ran late: {spoken}")
        announce_stage(status, "account", spoken)
        seen["account"] = True

    def games_step():
        if spoken != ["copy", "account", "boot"] or not seen.get("account"):
            raise SystemExit(f"games ran at the wrong time: {spoken}")
        seen["games"] = True

    spoken = []
    run_bootc(argv, status, watch, spoken, account=mark, finish=games_step)
    if spoken != ["copy", "account", "boot", "done"] or not seen.get("games"):
        raise SystemExit(f"account stages were {spoken}")

    def boom():
        announce_stage(status, "account", spoken)
        raise OSError("disk")

    def no_games():
        raise SystemExit("games ran after the account failed")

    spoken = []
    try:
        run_bootc(argv, status, watch, spoken, account=boom, finish=no_games)
    except Started as exc:
        if str(exc) != ACCOUNT_FAILED or "Nothing was erased." in str(exc):
            raise SystemExit(f"an account failure was {exc}") from exc
    except SystemExit as exc:
        raise SystemExit(f"an account failure ran games: {exc}") from exc
    else:
        raise SystemExit("an account failure printed the USB line")
    if spoken != ["copy", "account"] or "boot" in spoken or "done" in spoken:
        raise SystemExit(f"account failure stages were {spoken}")

    def late():
        announce_stage(status, "account", spoken)
        raise Refuse("Choose a disk again. Nothing was erased.")

    spoken = []
    try:
        run_bootc(argv, status, watch, spoken, account=late)
    except Started as exc:
        if (
            str(exc) != ACCOUNT_FAILED
            or "Nothing was erased." in str(exc)
            or "done" in spoken
            or "boot" in spoken
        ):
            raise SystemExit(f"a late account refusal was {exc} after {spoken}") from exc
    else:
        raise SystemExit("a late account refusal said the disk was untouched")

    def fail_after_account():
        if "account" not in spoken or "boot" not in spoken:
            raise SystemExit(f"games failed before the account: {spoken}")
        raise GamesProblem("planner")

    spoken = []
    try:
        run_bootc(argv, status, watch, spoken, account=mark, finish=fail_after_account)
    except Started as exc:
        if str(exc) != GAMES_FAILED or spoken != ["copy", "account", "boot"]:
            raise SystemExit(f"a games failure after the account was {exc} after {spoken}") from exc
    else:
        raise SystemExit("a games failure after the account printed the USB line")

    def explode():
        raise SystemExit("self-check tried to write the account")

    spoken = []
    try:
        run_bootc(argv, status, watch, spoken, account=explode)
    except SystemExit as exc:
        if "self-check" not in str(exc):
            raise SystemExit(f"an account guard was replaced: {exc}") from exc
    else:
        raise SystemExit("an account guard was caught")
    for call, label in (
        (lambda: prepare_account("nvme0n1", {"user": "alex"}, "{}"), "prepare the account"),
        (lambda: write_account("nvme0n1", {"user": "alex"}, "{}"), "write the account"),
        (lambda: run_account(created[0], jail), "run useradd"),
    ):
        try:
            call()
        except SystemExit as exc:
            if "self-check" not in str(exc):
                raise SystemExit(f"{label} stopped for another reason: {exc}") from exc
        else:
            raise SystemExit(f"{label} ran during self-check")


def check_post():
    """Check the app copy, the update source, labeling, and Secure Boot enrollment.

    This does not run rsync, bootc, setfiles, setenforce, mokutil, mount, or chroot.
    """
    import inspect

    if set(STAGE_LINES) != {"prepare", "copy", "account", "boot", "done"}:
        raise SystemExit("a post step added a status line")
    for sentence in (APPS_FAILED, UPDATES_FAILED, LABELS_FAILED):
        if (
            "Nothing was erased." in sentence
            or "Setting up your account." in sentence
            or len(sentence) > 160
            or sentence in STAGE_LINES.values()
        ):
            raise SystemExit("a post failure used the wrong sentence")
    if len({APPS_FAILED, UPDATES_FAILED, LABELS_FAILED, GAMES_FAILED, ACCOUNT_FAILED}) != 5:
        raise SystemExit("the post failures are not distinct")
    if DEFAULT_ZONE != "America/Los_Angeles" or not ZONE_NAME.fullmatch(DEFAULT_ZONE):
        raise SystemExit("the default time zone is not Pacific Time")
    if redact(ENROLLMENT_PASSWORD) != "output omitted" or ENROLLMENT_PASSWORD in redact("fine"):
        raise SystemExit("the enrollment password would be logged")
    image = registry_image("containers-storage:example:latest")
    if image != "example:latest":
        raise SystemExit(f"the registry image was {image}")
    switched = switch_argv(image)
    if switched != [
        "bootc",
        "switch",
        "--mutate-in-place",
        "--transport",
        "registry",
        "example:latest",
    ]:
        raise SystemExit(f"the switch command was {switched}")
    if "--enforce-container-sigpolicy" in switched:
        raise SystemExit("the switch command requires a signature policy this image does not have")
    if "--apply" in switched or "containers-storage" in " ".join(switched):
        raise SystemExit("the switch command would fetch or reboot")
    for bad in (
        "example:latest",
        "containers-storage:../example:latest",
        "containers-storage:example:latest;rm",
        "containers-storage:-example:latest",
        "containers-storage:example",
        "containers-storage:containers-storage:example:latest",
    ):
        try:
            registry_image(bad)
        except PostProblem:
            pass
        else:
            raise SystemExit(f"an update source was accepted: {bad}")
    for facts in (
        (False, True, "ThinkPad"),
        (True, False, "ThinkPad"),
        (True, True, "Jupiter"),
        (True, True, "Galileo"),
        (True, True, " Jupiter "),
    ):
        if mokutil_commands(*facts):
            raise SystemExit(f"enrollment was not skipped for {facts}")
    commands = mokutil_commands(True, True, "21M5")
    if commands != [
        ["mokutil", "--timeout", "-1"],
        ["mokutil", "--import", "/usr/share/ublue-os/sb_pubkey.der"],
    ]:
        raise SystemExit(f"the enrollment commands were {commands}")
    if ENROLLMENT_PASSWORD in " ".join(" ".join(item) for item in commands):
        raise SystemExit("the enrollment password was put on the command")
    if not stdin_ok(commands[1], import_stdin()) or stdin_ok(commands[1], "nope\n"):
        raise SystemExit("the enrollment password was not kept on standard input")
    if stdin_ok([*RSYNC_APPS, "/run/wasd-sysroot/x"], import_stdin()):
        raise SystemExit("a copy command was given the enrollment password")
    try:
        checked_post(["mokutil", "-t", str(SECUREBOOT_KEY)], Path("/tmp"))
    except PostProblem:
        pass
    else:
        raise SystemExit("a secure boot dialog command was accepted")
    rev = "cd" * 32
    with tempfile.TemporaryDirectory(prefix="wasd-post-") as tmp:
        jail = Path(tmp)
        deploy = jail / "ostree/deploy/default/deploy" / f"{rev}.0"
        shared = jail / "ostree/deploy/default/var/lib"
        shared.mkdir(parents=True)
        deploy.mkdir(parents=True)
        (deploy / "var").symlink_to("../../var")
        (deploy / "usr/bin").mkdir(parents=True)
        binary = deploy / "usr/bin/bootc"
        binary.write_text("#!/bin/true\n")
        origin = deploy.parent / f"{rev}.0.origin"
        origin.write_text("original-origin\n")
        before = origin.read_bytes()
        dest = flatpak_dir(deploy, jail)
        if dest != shared.resolve():
            raise SystemExit(f"the apps were aimed at {dest}")
        copied = flatpak_argv(dest, jail)
        if copied != [*RSYNC_APPS, str(FLATPAK_SOURCE), str(dest)]:
            raise SystemExit(f"the app copy was {copied}")
        try:
            checked_post([*RSYNC_APPS, str(dest)], jail)
        except PostProblem:
            pass
        else:
            raise SystemExit("a copy with no source was accepted")
        if ENROLLMENT_PASSWORD in " ".join(copied):
            raise SystemExit("the enrollment password was put on the app copy")
        spec_dir = deploy / "etc/selinux/targeted/contexts/files"
        spec_dir.mkdir(parents=True)
        spec = spec_dir / "file_contexts"
        spec.write_text("# contexts\n")
        flat = shared / "flatpak"
        flat.mkdir()
        home = shared.parent / "home"
        accounts = shared / "AccountsService"
        home.mkdir()
        accounts.mkdir()
        labeled = label_paths(deploy, jail)
        root = shared.parent.parent.resolve()
        expected_labels = [
            ["setfiles", "-r", str(deploy.resolve()), str(spec.resolve()), str((deploy / "etc/selinux").resolve())],
            ["setfiles", "-r", str(root), str(spec.resolve()), str(flat.resolve())],
            ["setfiles", "-r", str(root), str(spec.resolve()), str(home.resolve())],
            ["setfiles", "-r", str(root), str(spec.resolve()), str(accounts.resolve())],
        ]
        if labeled != expected_labels:
            raise SystemExit(f"the label commands were {labeled}")
        if any(ENROLLMENT_PASSWORD in " ".join(item) for item in labeled):
            raise SystemExit("the enrollment password was put on the label command")
        if checked_post(["setenforce", "0"], jail) != ["setenforce", "0"]:
            raise SystemExit("labeling was not allowed to set permissive mode")
        spec.rename(spec_dir / "file_contexts.real")
        spec.symlink_to("/etc/passwd")
        try:
            label_paths(deploy, jail)
        except PostProblem:
            pass
        else:
            raise SystemExit("a linked policy file was accepted")
        spec.unlink()
        (spec_dir / "file_contexts.real").rename(spec)
        rooted = ensure_sysroot_dir(deploy, jail)
        if rooted.name != "sysroot" or not rooted.is_relative_to(jail.resolve()):
            raise SystemExit(f"the system root directory was {rooted}")
        bound = bind_argv(jail, rooted)
        if bound != ["mount", "--bind", str(jail.resolve()), str(rooted)]:
            raise SystemExit(f"the system root mount was {bound}")
        if bootc_present(deploy, jail).resolve() != binary.resolve():
            raise SystemExit("the installed bootc was not found")
        command = chroot_argv(deploy, jail, "containers-storage:example:latest")
        if command[0] != "chroot" or command[2:] != switched or Path(command[1]).resolve() != deploy.resolve():
            raise SystemExit(f"the update command was {command}")
        if ENROLLMENT_PASSWORD in " ".join(command) or "--apply" in command:
            raise SystemExit("the update command would reboot or store a password")
        if origin.read_bytes() != before:
            raise SystemExit("the update source was rewritten during self-check")
        (deploy / "var").unlink()
        (deploy / "var").symlink_to("/var")
        try:
            flatpak_dir(deploy, jail)
        except PostProblem:
            pass
        else:
            raise SystemExit("an app path left the new system")
        if origin.read_bytes() != before:
            raise SystemExit("a refused app path changed the update source")
        (deploy / "sysroot").rmdir()
        (deploy / "sysroot").symlink_to("/")
        try:
            ensure_sysroot_dir(deploy, jail)
        except PostProblem:
            pass
        else:
            raise SystemExit("a linked system root was accepted")
        try:
            checked_post(["chroot", "/", *switched], jail)
        except PostProblem:
            pass
        else:
            raise SystemExit("chroot of this computer was accepted")
        try:
            checked_post(["bootc", *switched[1:]], jail)
        except PostProblem:
            pass
        else:
            raise SystemExit("bootc was allowed to run on this computer")
        try:
            checked_post(["mokutil", "--import", str(SECUREBOOT_KEY), ENROLLMENT_PASSWORD], jail)
        except PostProblem:
            pass
        else:
            raise SystemExit("the enrollment password was put on the command")
        try:
            checked_post(["setfiles", "-r", "/", str(spec), str(deploy / "etc/selinux")], jail)
        except PostProblem:
            pass
        else:
            raise SystemExit("setfiles was aimed at this computer")
        try:
            checked_post(["setenforce", "1"], jail)
        except PostProblem:
            pass
        else:
            raise SystemExit("enforcing mode was changed")
        try:
            checked_post(["restorecon", "-R", "/etc/selinux"], jail)
        except PostProblem:
            pass
        else:
            raise SystemExit("restorecon was allowed on this computer")
        binary.unlink()
        binary.symlink_to("/usr/bin/true")
        try:
            bootc_present(deploy, jail)
        except PostProblem:
            pass
        else:
            raise SystemExit("a linked bootc was accepted")
        if origin.read_bytes() != before:
            raise SystemExit("the update source was rewritten during self-check")
    qml = Path(__file__).with_name("Main.qml").read_text()
    for sentence in (
        "The installed apps were not copied.",
        "Later updates were not pointed at WASD.",
        "The security labels were not restored.",
    ):
        if sentence not in qml:
            raise SystemExit(f"the window ignores {sentence}")
    for name, func in (
        ("switch_argv", switch_argv),
        ("chroot_argv", chroot_argv),
        ("copy_flatpak", copy_flatpak),
        ("point_updates", point_updates),
        ("policy_spec", policy_spec),
        ("label_paths", label_paths),
        ("setfiles_argv", setfiles_argv),
        ("restore_labels", restore_labels),
        ("enroll_secure_boot", enroll_secure_boot),
        ("write_post", write_post),
        ("finish_post", finish_post),
        ("run_post", run_post),
    ):
        body = inspect.getsource(func)
        if any(token in body for token in ("yad", "mokutil -t", "rpm-ostree", "nmcli", "shell=True", "--apply")):
            raise SystemExit(f"{name} touches the running system")
        if name != "run_post" and "subprocess" in body:
            raise SystemExit(f"{name} runs a command itself")
    enroll_body = inspect.getsource(enroll_secure_boot)
    if "print(" in enroll_body or "post_log(ENROLLMENT_PASSWORD" in enroll_body:
        raise SystemExit("the enrollment password would be printed")
    boot_body = inspect.getsource(run_bootc)
    if boot_body.count('announce_stage(status_id, "boot"') != 1 or "if post is not None" not in boot_body:
        raise SystemExit("the post steps moved the bootloader line")
    install_body = inspect.getsource(install)
    if "finish_post" not in install_body or "universalblue" in install_body or "--apply" in install_body:
        raise SystemExit("install does not finish the installed system")
    post_body = inspect.getsource(write_post)
    try:
        between = post_body.split("point_updates(", 1)[1].split("restore_labels(", 1)[0]
    except IndexError as exc:
        raise SystemExit("the update step or the labels are missing") from exc
    if "except PostProblem" not in between:
        raise SystemExit("an update failure skips the security labels")
    if "enroll_secure_boot(" not in post_body.split("restore_labels(", 1)[1]:
        raise SystemExit("enrollment was skipped after the labels")
    status = "abcd1234efgh5678"
    disk_argv = bootc_argv("nvme0n1", {"mode": "off"}, "containers-storage:example:latest")

    def runner(command, on_line):
        if command != disk_argv:
            raise SystemExit(f"bootc was started with {command}")
        return 0, ""

    def mark():
        if spoken != ["copy"]:
            raise SystemExit(f"the account ran late: {spoken}")
        announce_stage(status, "account", spoken)

    seen = {}

    def post_ok():
        if spoken != ["copy", "account", "boot"]:
            raise SystemExit(f"post ran at the wrong time: {spoken}")
        seen["post"] = True

    def games_step():
        if spoken != ["copy", "account", "boot"] or not seen.get("post"):
            raise SystemExit(f"games ran at the wrong time: {spoken}")
        seen["games"] = True

    spoken = []
    run_bootc(disk_argv, status, runner, spoken, account=mark, post=post_ok, finish=games_step)
    if spoken != ["copy", "account", "boot", "done"] or not seen.get("games"):
        raise SystemExit(f"post stages were {spoken}")

    def apps_fail():
        if "boot" not in spoken or "account" not in spoken:
            raise SystemExit(f"the app copy failed too early: {spoken}")
        raise PostProblem(APPS_FAILED)

    def no_games():
        raise SystemExit("games ran after the account failed")

    def games_after(kind):
        def step():
            seen[kind] = True

        return step

    spoken = []
    seen = {}
    try:
        run_bootc(disk_argv, status, runner, spoken, account=mark, post=apps_fail, finish=games_after("apps"))
    except Started as exc:
        if (
            str(exc) != APPS_FAILED
            or "Nothing was erased." in str(exc)
            or spoken != ["copy", "account", "boot"]
            or not seen.get("apps")
        ):
            raise SystemExit(f"an app copy failure was {exc} after {spoken} {seen}") from exc
    else:
        raise SystemExit("an app copy failure printed the USB line")

    def updates_fail():
        raise OSError("disk")

    spoken = []
    seen = {}
    try:
        run_bootc(disk_argv, status, runner, spoken, account=mark, post=updates_fail, finish=games_after("updates"))
    except Started as exc:
        if str(exc) != UPDATES_FAILED or "Nothing was erased." in str(exc) or "done" in spoken or not seen.get("updates"):
            raise SystemExit(f"an update failure was {exc} after {spoken} {seen}") from exc
    else:
        raise SystemExit("an update failure printed the USB line")

    def labels_fail():
        raise PostProblem(LABELS_FAILED)

    spoken = []
    seen = {}
    try:
        run_bootc(disk_argv, status, runner, spoken, account=mark, post=labels_fail, finish=games_after("labels"))
    except Started as exc:
        if str(exc) != LABELS_FAILED or "Nothing was erased." in str(exc) or "done" in spoken or not seen.get("labels"):
            raise SystemExit(f"a label failure was {exc} after {spoken} {seen}") from exc
    else:
        raise SystemExit("a label failure printed the USB line")

    def boom_account():
        announce_stage(status, "account", spoken)
        raise OSError("disk")

    def no_post():
        raise SystemExit("post ran after the account failed")

    spoken = []
    try:
        run_bootc(disk_argv, status, runner, spoken, account=boom_account, post=no_post, finish=no_games)
    except Started as exc:
        if str(exc) != ACCOUNT_FAILED or spoken != ["copy", "account"]:
            raise SystemExit(f"an account failure reached post: {exc} after {spoken}") from exc
    except SystemExit as exc:
        raise SystemExit(f"an account failure continued: {exc}") from exc
    else:
        raise SystemExit("an account failure printed the USB line")

    def explode():
        raise SystemExit("self-check tried to run bootc")

    spoken = []
    try:
        run_bootc(disk_argv, status, runner, spoken, account=mark, post=explode, finish=no_games)
    except SystemExit as exc:
        if str(exc) != "self-check tried to run bootc":
            raise SystemExit(f"a post guard was replaced: {exc}") from exc
    else:
        raise SystemExit("a post guard was caught")
    if "done" in spoken:
        raise SystemExit("a post guard printed the USB line")
    for call, label in (
        (lambda: finish_post("nvme0n1", "containers-storage:example:latest"), "finish the installed system"),
        (lambda: write_post("nvme0n1", "containers-storage:example:latest"), "write the installed system"),
        (lambda: copy_flatpak(deploy, SYSROOT), "copy the installed apps"),
        (
            lambda: point_updates(deploy, SYSROOT, "containers-storage:example:latest"),
            "point later updates",
        ),
        (lambda: restore_labels(deploy, SYSROOT), "restore security labels"),
        (lambda: enroll_secure_boot(), "enroll a key"),
        (lambda: run_post(["bootc", "switch"], SYSROOT), "run a post command"),
        (lambda: umount_bound(deploy / "sysroot"), "unmount the new system root"),
    ):
        try:
            call()
        except SystemExit as exc:
            if "self-check" not in str(exc):
                raise SystemExit(f"{label} stopped for another reason: {exc}") from exc
        else:
            raise SystemExit(f"{label} ran during self-check")


def check_writer():
    """Check the bootc command without running it or touching a disk."""
    os.environ["WASD_SELF_CHECK"] = "1"
    try:
        defaults = (
            "ostreecontainer --url=example:latest --transport=containers-storage "
            "--no-signature-verification\n"
        )
        source = image_ref(defaults)
        if source != "containers-storage:example:latest":
            raise SystemExit(f"image ref was {source}")
        whole = bootc_argv("nvme0n1", {"mode": "off"}, source)
        expected = [
            "bootc",
            "install",
            "to-disk",
            "--wipe",
            "--filesystem",
            "btrfs",
            "--skip-fetch-check",
            "--source-imgref",
            "containers-storage:example:latest",
            "--karg",
            "quiet",
            "--karg",
            "rhgb",
            "/dev/nvme0n1",
        ]
        if whole != expected:
            raise SystemExit(f"whole-disk command was {whole}")
        if "liveinst" in whole or "--root-size" in whole:
            raise SystemExit("the disk writer called the old installer")
        if STAGE_LINES.get("account") != "Setting up your account.":
            raise SystemExit("the account line is missing")
        if "Setting up your account." in whole:
            raise SystemExit("the disk writer put the account in the bootc command")
        split = bootc_argv("nvme0n1", {"mode": "split", "osGb": 128, "gamesGb": 1730}, source)
        if split[:-1] != expected[:-1] + ["--root-size", "128G"] or split[-1] != "/dev/nvme0n1":
            raise SystemExit(f"split command was {split}")
        if any(part in split for part in ("liveinst", "mkfs", "/games", "/dev/nvme1n1")):
            raise SystemExit("the split command touched more than the WASD size")
        keep = bootc_argv(
            "nvme0n1",
            {"mode": "keep", "device": "nvme1n1", "osGb": 128},
            source,
        )
        if keep != expected or "/dev/nvme1n1" in keep:
            raise SystemExit("a games drive was included in the WASD command")
        for bad_source in (
            "ostreecontainer --url=example:latest --transport=registry\n",
            "ostreecontainer --url=example:latest;rm --transport=containers-storage\n",
            "ostreecontainer --url=../example:latest --transport=containers-storage\n",
        ):
            try:
                image_ref(bad_source)
            except Refuse:
                pass
            else:
                raise SystemExit(f"image ref was accepted {bad_source!r}")
        try:
            bootc_argv("sda1", {"mode": "off"}, source)
        except Refuse:
            pass
        else:
            raise SystemExit("a partition was accepted as the install disk")
        try:
            bootc_argv("nvme0n1", {"mode": "split", "osGb": True}, source)
        except Refuse:
            pass
        else:
            raise SystemExit("a split size of true was accepted")
        if install_gate(False, 1000) != "refuse" or install_gate(True, 1000) != "pkexec" or install_gate(True, 0) != "root":
            raise SystemExit("the root gate was wrong")

        def succeed(argv, on_line):
            if argv != expected:
                raise SystemExit(f"bootc was started with {argv}")
            for line in (
                "Installing image: docker://example:latest\n",
                "Wiping /dev/nvme0n1\n",
                "Deploying container image\n",
                "Installing bootloader via bootupd\n",
            ):
                on_line(line)
            return 0, "Deploying container image\nInstalling bootloader via bootupd\n"

        spoken = []
        run_bootc(expected, "abcd1234efgh5678", succeed, spoken)
        if spoken != ["copy", "boot", "done"]:
            raise SystemExit(f"success stages were {spoken}")

        def early(argv, on_line):
            text = "ERROR Installing to disk: Verifying fetch: pinging container registry\n"
            on_line(text)
            return 1, text

        try:
            run_bootc(expected, "abcd1234efgh5678", early, [])
        except Refuse as exc:
            if "Nothing was erased." not in str(exc) or "disk was erased" in str(exc):
                raise SystemExit(f"an early failure was {exc}") from exc
        else:
            raise SystemExit("a failure before the wipe continued")

        def wiped(argv, on_line):
            on_line("Wiping /dev/nvme0n1\n")
            on_line("ERROR Installing to disk: Creating rootfs\n")
            return 1, "Wiping /dev/nvme0n1\n"

        try:
            run_bootc(expected, "abcd1234efgh5678", wiped, [])
        except Started as exc:
            if str(exc) != WIPED_LINE:
                raise SystemExit(f"a wiped failure was {exc}") from exc
        else:
            raise SystemExit("a failure after the wipe said the disk was untouched")

        def missing(argv, on_line):
            return None

        try:
            run_bootc(expected, "abcd1234efgh5678", missing, [])
        except Refuse as exc:
            if str(exc) != NOT_STARTED:
                raise SystemExit(f"a missing writer was {exc}") from exc
        else:
            raise SystemExit("a missing writer continued")
        check_games()
        check_account()
        check_post()
    finally:
        os.environ.pop("WASD_SELF_CHECK", None)


class Started(Exception):
    """bootc wiped the selected disk and then failed."""


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
    if "universalblue" in kick:
        raise SystemExit("kickstart stored the enrollment password")
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
    kick_path = install_kickstart_path()
    if kick_path.name != "wasd-install.ks" or kick_path.parent == Path("/run"):
        raise SystemExit(f"kickstart path {kick_path}")
    check_writer()
    print("erase self-check ok")


def install_kickstart_path():
    """A file the live user can write. --render still prints a kickstart.

    /run itself is not writable by the live user. The disk writer does not
    read this file and does not call liveinst.
    """
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        directory = Path(runtime)
        if directory.is_dir() and os.access(directory, os.W_OK):
            return directory / "wasd-install.ks"
    return Path("/tmp/wasd-install.ks")


def install(payload, defaults_path, status_id):
    """Copy WASD onto the selected disk and set up the account.

    The account runs after the copy and before the bootloader sentence.
    Installed apps, the update source, and Secure Boot enrollment run
    after that sentence. A games choice runs after those. The USB sentence
    is printed only when the copy, the account, and those steps succeed.
    The password is not written.
    """
    if os.environ.get("WASD_SELF_CHECK") == "1":
        raise SystemExit("self-check tried to install")
    spoken = []
    try:
        if not STATUS_ID.fullmatch(status_id or ""):
            raise Refuse(NOT_STARTED)
        announce_stage(status_id, "prepare", spoken)
        data, text = load_choices(payload)
        listing = current_lsblk()
        assert_disk_matches(data, listing)
        assert_games_matches(data, listing)
        assert_wipe_matches(data, listing)
        if shutil.which("bootc") is None:
            raise Refuse(NOT_STARTED)
        source = image_ref(read_defaults(defaults_path))
        plan = games_plan(data, data["device"])
        argv = bootc_argv(data["device"], plan, source)

        def account():
            announce_stage(status_id, "account", spoken)
            prepare_account(data["device"], data, text)

        def post():
            finish_post(data["device"], source)

        def finish():
            finish_games(data["device"], plan)

        run_bootc(
            argv,
            status_id,
            bootc_runner,
            spoken,
            account=account,
            post=post,
            finish=finish,
        )
    except Started as exc:
        line = started_line(exc)
        write_status(status_id, line)
        print(line, file=sys.stderr)
        return 1
    except Refuse as exc:
        write_status(status_id, str(exc))
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description="Install WASD onto the selected disk")
    parser.add_argument("--render", action="store_true", help="Print the kickstart and do not install")
    parser.add_argument("--install", action="store_true", help="Start the install on a live USB")
    parser.add_argument("--self-check", action="store_true", help="Check the kickstart rules without a disk")
    parser.add_argument("--defaults", default="/usr/share/anaconda/interactive-defaults.ks")
    parser.add_argument("--status-id", default="", help="Id the window uses to match status lines")
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
    if os.environ.get("WASD_SELF_CHECK") == "1":
        print("self-check tried to install", file=sys.stderr)
        return 1
    if not is_live():
        print("This is not a live USB. Nothing was erased.", file=sys.stderr)
        return 1
    if os.geteuid() != 0:
        script = str(Path(__file__).resolve())
        try:
            os.execvp("pkexec", ["pkexec", script, *sys.argv[1:]])
        except OSError:
            print(NOT_STARTED, file=sys.stderr)
            return 1
    return install(args.payload or "", args.defaults, args.status_id or "")


if __name__ == "__main__":
    raise SystemExit(main())
