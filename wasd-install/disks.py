"""Disk list for Install WASD.

The preview feeds this a sample. The live USB reads lsblk. Nothing here
partitions, formats, or erases a disk.
"""

import json
import re
import subprocess
from pathlib import Path

OS_FS = {"ext4", "btrfs", "xfs", "ntfs", "bitlocker", "crypto_luks"}
DEVICE_NAME = re.compile(r"^(nvme[0-9]+n[0-9]+|sd[a-z]+|vd[a-z]+|mmcblk[0-9]+|hd[a-z]+)$")


def walk(node):
    yield node
    for child in node.get("children") or []:
        yield from walk(child)


def display_name(model, fallback):
    raw = model or fallback or "Disk"
    return " ".join(str(raw).replace("_", " ").split())


def disk_bytes(value):
    if isinstance(value, int):
        return value if value > 0 else 0
    text = str(value or "").strip()
    if text.isdigit():
        return int(text)
    return 0


def human_size(value):
    number = disk_bytes(value)
    if number <= 0:
        return str(value or "")
    units = ((1_000_000_000_000, "TB"), (1_000_000_000, "GB"))
    for scale, label in units:
        if number >= scale:
            shown = number / scale
            text = f"{shown:.1f}".rstrip("0").rstrip(".")
            return f"{text} {label}"
    return f"{number // 1_000_000} MB"


def parse_disks(payload):
    data = json.loads(payload) if isinstance(payload, str) else payload
    disks = []
    for dev in data.get("blockdevices") or []:
        if dev.get("type") != "disk":
            continue
        device = str(dev.get("name") or "")
        name = display_name(dev.get("model"), device)
        windows = False
        occupied = False
        games = False
        games_part = ""
        games_fs = ""
        games_uuid = ""
        games_bytes = -1
        data_part = ""
        data_fs = ""
        data_uuid = ""
        data_bytes = -1
        for node in walk(dev):
            if node is dev:
                continue
            fs = (node.get("fstype") or "").lower()
            label = str(node.get("label") or "")
            if fs == "bitlocker" or (fs == "ntfs" and re.search(r"windows|microsoft", label, re.I)):
                windows = True
                occupied = True
            elif fs in OS_FS or fs == "exfat":
                occupied = True
            marked = label.casefold() == "games"
            steam = False
            for mount in _mounts(node):
                root = Path(mount)
                try:
                    steam = (root / "SteamLibrary" / "steamapps").is_dir() or (root / "steamapps").is_dir()
                except OSError:
                    steam = False
                if steam:
                    break
            size = disk_bytes(node.get("size"))
            if (marked or steam) and size >= games_bytes:
                games = True
                games_part = str(node.get("name") or "")
                games_fs = fs
                games_uuid = str(node.get("uuid") or "")
                games_bytes = size
            elif fs in {"btrfs", "ext4", "xfs", "ntfs", "exfat"} and size > data_bytes:
                data_part = str(node.get("name") or "")
                data_fs = fs
                data_uuid = str(node.get("uuid") or "")
                data_bytes = size
        if windows:
            kind = "Windows. This drive stays"
            games = False
            part = ""
            fstype = ""
            uuid = ""
        else:
            part = games_part or data_part
            fstype = games_fs if games else data_fs
            uuid = games_uuid if games else data_uuid
            kind = "Another system. This drive stays" if occupied else ""
        raw_size = dev.get("size")
        disks.append(
            {
                "name": name,
                "device": device,
                "kind": kind,
                "size": human_size(raw_size) if disk_bytes(raw_size) else (raw_size or ""),
                "bytes": disk_bytes(raw_size),
                "windows": windows,
                "occupied": occupied,
                "games": games,
                "part": "" if windows else part,
                "fstype": "" if windows else fstype,
                "uuid": "" if windows else uuid,
            }
        )
    return disks


def default_disk(disks):
    for index, disk in enumerate(disks):
        if not disk["occupied"]:
            return index
    return -1


def is_live():
    try:
        command = Path("/proc/cmdline").read_text()
    except OSError:
        return False
    if re.search(r"(^|\s)rd\.live\.image(\s|$)", command):
        return True
    live = Path("/run/initramfs/live")
    try:
        if live.is_dir() and any(live.iterdir()):
            return True
    except OSError:
        return False
    return False


def _mounts(node):
    mounts = node.get("mountpoints")
    if mounts is None:
        mounts = node.get("mountpoint") or []
    if isinstance(mounts, str):
        mounts = [mounts]
    return [mount for mount in mounts if mount]


def live_disk_names(payload):
    """Whole disks that hold the running live system."""
    data = json.loads(payload) if isinstance(payload, str) else payload
    parents = {}

    def remember(node, parent_disk):
        name = str(node.get("name") or "")
        disk = name if node.get("type") == "disk" else parent_disk
        if name:
            parents[name] = disk
        for child in node.get("children") or []:
            remember(child, disk)

    banned = set()

    def consider(node):
        name = str(node.get("name") or "")
        label = str(node.get("label") or "")
        hit = label == "WASD"
        for mount in _mounts(node):
            if mount == "/run/initramfs/live" or mount.startswith("/run/initramfs/"):
                hit = True
        if hit:
            disk = parents.get(name) or ""
            if disk:
                banned.add(disk)
        for child in node.get("children") or []:
            consider(child)

    for dev in data.get("blockdevices") or []:
        remember(dev, "")
    for dev in data.get("blockdevices") or []:
        consider(dev)
    return banned


def secure_boot_on():
    efi = Path("/sys/firmware/efi/efivars")
    if not efi.is_dir():
        return False
    for path in efi.glob("SecureBoot-*"):
        try:
            blob = path.read_bytes()
        except OSError:
            continue
        if len(blob) >= 5 and blob[4] == 1:
            return True
    return False


def memory_kb():
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return 0
    return 0


def live_disks():
    result = subprocess.run(
        ["lsblk", "-J", "-b", "-o", "NAME,SIZE,MODEL,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS"],
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_disks(result.stdout)


def live_payload():
    disks = live_disks()
    warnings = []
    if any(disk["windows"] for disk in disks):
        warnings.append("Turn off BitLocker and fast startup in Windows before you install.")
    legacy = not Path("/sys/firmware/efi").is_dir()
    if legacy:
        warnings.append("Set the firmware to UEFI in the BIOS. The motherboard manual explains how.")
    if secure_boot_on():
        warnings.append("Secure Boot is on. On the next boot, choose Enroll MOK and enter universalblue.")
    if 0 < memory_kb() < 5_000_000:
        warnings.append("This computer has very little memory. The install may fail.")
    if not disks:
        warnings.append("No disks were found.")
    return {"warnings": warnings, "blocked": legacy or not disks, "disks": disks}


def self_check():
    payload = {
        "blockdevices": [
            {
                "name": "sda",
                "type": "disk",
                "size": "16G",
                "model": "Live USB",
                "children": [
                    {
                        "name": "sda1",
                        "type": "part",
                        "label": "WASD",
                        "mountpoints": ["/run/initramfs/live"],
                    }
                ],
            },
            {
                "name": "nvme0n1",
                "type": "disk",
                "size": "1.8T",
                "model": "Samsung SSD 990 PRO",
                "children": [],
            },
        ]
    }
    banned = live_disk_names(payload)
    if banned != {"sda"}:
        raise SystemExit(f"live disk detection {banned}")
    disks = parse_disks(payload)
    if disks[0]["device"] != "sda" or disks[1]["device"] != "nvme0n1":
        raise SystemExit(f"device names {disks}")
    if not DEVICE_NAME.fullmatch("nvme0n1") or DEVICE_NAME.fullmatch("../nvme0n1"):
        raise SystemExit("device name check failed")
    if human_size(2_000_000_000_000) != "2 TB":
        raise SystemExit(f"size text {human_size(2_000_000_000_000)}")
    if human_size("1.8T") != "1.8T":
        raise SystemExit("a labeled size was rewritten")
    marked = parse_disks({
        "blockdevices": [
            {
                "name": "nvme0n1",
                "type": "disk",
                "size": 2_000_000_000_000,
                "model": "Samsung SSD 990 PRO",
                "children": [{
                    "name": "nvme0n1p1",
                    "type": "part",
                    "fstype": "ntfs",
                    "label": "Games",
                    "size": 1_500_000_000_000,
                    "uuid": "12345678-1234-1234-1234-123456789abc",
                }],
            },
            {
                "name": "nvme1n1",
                "type": "disk",
                "size": 1_000_000_000_000,
                "model": "Windows Disk",
                "children": [
                    {"name": "nvme1n1p1", "type": "part", "fstype": "BitLocker"},
                    {"name": "nvme1n1p2", "type": "part", "fstype": "ntfs", "label": "games", "uuid": "abcdefab-1234-1234-1234-123456789abc"},
                ],
            },
        ]
    })
    if not marked[0]["games"] or marked[0]["part"] != "nvme0n1p1" or marked[0]["fstype"] != "ntfs":
        raise SystemExit(f"games label was missed {marked[0]}")
    if marked[1]["games"] or marked[1]["part"] or marked[1]["uuid"] or not marked[1]["windows"]:
        raise SystemExit(f"windows disk became a games drive {marked[1]}")
