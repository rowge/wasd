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
        for node in walk(dev):
            fs = (node.get("fstype") or "").lower()
            label = node.get("label") or ""
            if fs == "bitlocker" or (fs == "ntfs" and re.search(r"windows|microsoft", label, re.I)):
                windows = True
                occupied = True
            elif fs in OS_FS:
                occupied = True
        if windows:
            kind = "Windows. This drive stays"
        elif occupied:
            kind = "Another system. This drive stays"
        else:
            kind = ""
        disks.append(
            {
                "name": name,
                "device": device,
                "kind": kind,
                "size": dev.get("size") or "",
                "windows": windows,
                "occupied": occupied,
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
        ["lsblk", "-J", "-o", "NAME,SIZE,MODEL,TYPE,FSTYPE,LABEL"],
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
