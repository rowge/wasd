#!/usr/bin/env python3
"""Add Windows to the WASD boot menu when it is on another drive.

The Windows drive is not mounted except for a read-only look at its EFI
partition. Nothing is written there. The menu file is written on the WASD
drive. A missing Windows install removes that file. This does not run
grub2-mkconfig or os-prober.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, "/usr/libexec")

from disks import DEVICE_NAME, disk_bytes, display_name, live_disk_names  # noqa: E402

PART_NAME = re.compile(
    r"^(nvme[0-9]+n[0-9]+p[0-9]+|sd[a-z]+[0-9]+|vd[a-z]+[0-9]+|mmcblk[0-9]+p[0-9]+|hd[a-z]+[0-9]+)$"
)
FAT_UUID = re.compile(r"^[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}$")
LONG_UUID = re.compile(r"^[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")
EFI_PARTTYPE = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
LOADER = Path("EFI/Microsoft/Boot/bootmgfw.efi")
MAX_ESP = 2 * 1024 ** 3
SOURCE = "if [ -f $prefix/custom.cfg ]; then\n    source $prefix/custom.cfg\nfi\n"
MENU_FILES = (
    Path("boot/grub2/grub.cfg"),
    Path("boot/efi/EFI/fedora/grub.cfg"),
)


def candidates(payload):
    data = json.loads(payload) if isinstance(payload, str) else payload
    rows = []
    for dev in data.get("blockdevices") or []:
        if dev.get("type") != "disk":
            continue
        disk = str(dev.get("name") or "")
        if not DEVICE_NAME.fullmatch(disk):
            continue
        model = display_name(dev.get("model"), disk)
        for node in dev.get("children") or []:
            part = str(node.get("name") or "")
            fstype = str(node.get("fstype") or "").lower()
            if node.get("type") != "part" or fstype != "vfat" or not PART_NAME.fullmatch(part):
                continue
            if not part.startswith(disk):
                continue
            mounts = node.get("mountpoints") or node.get("mountpoint") or []
            if isinstance(mounts, str):
                mounts = [mounts]
            if any(mount and "/boot" in str(mount) for mount in mounts):
                continue
            size = disk_bytes(node.get("size"))
            parttype = str(node.get("parttype") or "").lower()
            if not (parttype == EFI_PARTTYPE or 0 < size <= MAX_ESP):
                continue
            uuid = str(node.get("uuid") or "")
            if not FAT_UUID.fullmatch(uuid) and not LONG_UUID.fullmatch(uuid):
                continue
            rows.append({"disk": disk, "model": model, "part": part, "uuid": uuid})
    return rows


def menu_title(model, several):
    if not several:
        return "Windows"
    clean = re.sub(r"[^A-Za-z0-9 ._-]", "", model)
    clean = " ".join(clean.split())[:40].strip(" ._-")
    if not clean:
        return "Windows"
    return f"Windows on {clean}"


def titled(rows):
    several = len(rows) > 1
    used = set()
    named = []
    for row in rows:
        title = menu_title(row["model"], several)
        if title in used:
            title = f"{title} {row['disk']}"
        used.add(title)
        named.append({**row, "title": title})
    return named


def render(rows):
    lines = ["set timeout_style=menu", "set timeout=5"]
    for row in titled(rows):
        lines.extend(
            [
                f"menuentry '{row['title']}' --class windows --class os {{",
                "    insmod part_gpt",
                "    insmod fat",
                "    insmod chain",
                f"    search --no-floppy --fs-uuid --set=root {row['uuid']}",
                "    chainloader /EFI/Microsoft/Boot/bootmgfw.efi",
                "}",
            ]
        )
    return "\n".join(lines) + "\n"


def mount_has_loader(part):
    if os.environ.get("WASD_SELF_CHECK") == "1":
        raise SystemExit("self-check tried to mount a disk")
    if not PART_NAME.fullmatch(part):
        return False
    mountpoint = Path(tempfile.mkdtemp(prefix="wasd-esp-"))
    mounted = False
    try:
        proc = subprocess.run(
            ["mount", "-o", "ro,nosuid,nodev", f"/dev/{part}", str(mountpoint)],
            capture_output=True,
        )
        if proc.returncode != 0:
            return False
        mounted = True
        return (mountpoint / LOADER).is_file()
    finally:
        if mounted:
            subprocess.run(["umount", str(mountpoint)], capture_output=True)
        mountpoint.rmdir()


def select(payload, skip, probe):
    banned = set(live_disk_names(payload))
    banned.update(skip)
    found = []
    for row in candidates(payload):
        if row["disk"] in banned:
            continue
        if probe(row["part"]):
            found.append(row)
    return found


def ensure_source(root):
    for rel in MENU_FILES:
        path = root / rel
        if not path.is_file():
            continue
        text = path.read_text(errors="replace")
        if "custom.cfg" in text:
            continue
        if "blscfg" not in text and "menuentry" not in text:
            continue
        path.write_text(text.rstrip() + "\n" + SOURCE)


def boot_is_ro():
    try:
        text = Path("/proc/mounts").read_text()
    except OSError:
        return False
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1] == "/boot":
            return "ro" in parts[3].split(",")
    return False


def apply(root, payload, skip, probe):
    root = Path(root)
    custom = root / "boot/grub2/custom.cfg"
    found = select(payload, skip, probe)
    custom.parent.mkdir(parents=True, exist_ok=True)
    if not found:
        if custom.exists():
            custom.unlink()
        return []
    custom.write_text(render(found))
    custom.chmod(0o644)
    ensure_source(root)
    return found


def read_lsblk():
    proc = subprocess.run(
        ["lsblk", "-J", "-b", "-o", "NAME,SIZE,MODEL,TYPE,FSTYPE,LABEL,UUID,PARTTYPE,MOUNTPOINTS"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def windows_post(device, plan, wiped):
    skips = [device]
    if plan.get("mode") == "format" and plan.get("device"):
        skips.append(plan["device"])
    for item in wiped:
        skips.append(item["device"])
    args = " ".join(f"--skip {name}" for name in skips)
    return f"""
%post --nochroot --log=/tmp/anacoda_custom_logs/wasd-windows-boot.log
set -u
if [ -x /usr/libexec/wasd-windows-boot ]; then
    /usr/libexec/wasd-windows-boot --root /mnt/sysimage {args} || true
fi
%end
"""


def self_check():
    os.environ["WASD_SELF_CHECK"] = "1"
    try:
        mount_has_loader("nvme1n1p1")
    except SystemExit as exc:
        if "mount" not in str(exc):
            raise
    else:
        raise SystemExit("self-check mounted a disk")

    payload = {
        "blockdevices": [
            {
                "name": "sda",
                "type": "disk",
                "model": "Live USB",
                "children": [
                    {
                        "name": "sda1",
                        "type": "part",
                        "fstype": "vfat",
                        "size": 100_000_000,
                        "uuid": "AAAA-1111",
                        "parttype": EFI_PARTTYPE,
                        "label": "WASD",
                        "mountpoints": ["/run/initramfs/live"],
                    }
                ],
            },
            {
                "name": "nvme0n1",
                "type": "disk",
                "model": "Samsung SSD 990 PRO",
                "children": [
                    {
                        "name": "nvme0n1p1",
                        "type": "part",
                        "fstype": "vfat",
                        "size": 100_000_000,
                        "uuid": "BBBB-2222",
                        "parttype": EFI_PARTTYPE,
                    }
                ],
            },
            {
                "name": "nvme1n1",
                "type": "disk",
                "model": "WD Black",
                "children": [
                    {
                        "name": "nvme1n1p1",
                        "type": "part",
                        "fstype": "vfat",
                        "size": 100_000_000,
                        "uuid": "ABCD-1234",
                        "parttype": EFI_PARTTYPE,
                    },
                    {
                        "name": "nvme1n1p3",
                        "type": "part",
                        "fstype": "ntfs",
                        "size": 500_000_000_000,
                        "uuid": "CCCC-3333",
                        "label": "Windows",
                    },
                ],
            },
            {
                "name": "nvme2n1",
                "type": "disk",
                "model": "Samsung",
                "children": [
                    {
                        "name": "nvme2n1p1",
                        "type": "part",
                        "fstype": "vfat",
                        "size": 3 * 1024 ** 3,
                        "uuid": "DDDD-4444",
                    }
                ],
            },
        ]
    }
    seen = []

    def probe(part):
        seen.append(part)
        return part == "nvme1n1p1"

    with tempfile.TemporaryDirectory(prefix="wasd-windows-") as tmp:
        root = Path(tmp)
        menu = root / "boot/grub2/grub.cfg"
        menu.parent.mkdir(parents=True)
        menu.write_text("set default=0\ninsmod blscfg\nblscfg\n")
        found = apply(root, payload, {"nvme0n1"}, probe)
        if [row["part"] for row in found] != ["nvme1n1p1"]:
            raise SystemExit(f"windows scan was {found}")
        if "nvme0n1p1" in seen or "sda1" in seen or "nvme2n1p1" in seen or "nvme1n1p3" in seen:
            raise SystemExit(f"windows scan looked at the wrong partition {seen}")
        text = (root / "boot/grub2/custom.cfg").read_text()
        if "set timeout=5" not in text or "ABCD-1234" not in text or "menuentry 'Windows'" not in text:
            raise SystemExit(f"windows menu was {text}")
        if "Windows on" in text or "chainloader /EFI/Microsoft/Boot/bootmgfw.efi" not in text:
            raise SystemExit(f"windows menu was {text}")
        if "custom.cfg" not in menu.read_text():
            raise SystemExit("the boot menu does not read the windows line")
        outside = [path for path in root.parent.glob("custom.cfg")]
        if outside:
            raise SystemExit(f"windows menu wrote outside the install {outside}")

        apply(root, payload, {"nvme0n1", "nvme1n1"}, probe)
        if (root / "boot/grub2/custom.cfg").exists():
            raise SystemExit("the erased windows drive stayed on the menu")

        (root / "boot/grub2/custom.cfg").write_text("stale\n")
        apply(root, payload, {"nvme0n1"}, lambda part: False)
        if (root / "boot/grub2/custom.cfg").exists():
            raise SystemExit("a missing windows loader stayed on the menu")

        both = json.loads(json.dumps(payload))
        extra = {
            "name": "nvme3n1",
            "type": "disk",
            "model": "Samsung",
            "children": [
                {
                    "name": "nvme3n1p1",
                    "type": "part",
                    "fstype": "vfat",
                    "size": 100_000_000,
                    "uuid": "EEEE-5555",
                    "parttype": EFI_PARTTYPE,
                }
            ],
        }
        both["blockdevices"].append(extra)

        def both_probe(part):
            return part in {"nvme1n1p1", "nvme3n1p1"}

        apply(root, both, {"nvme0n1"}, both_probe)
        text = (root / "boot/grub2/custom.cfg").read_text()
        if "Windows on WD Black" not in text or "Windows on Samsung" not in text:
            raise SystemExit(f"two windows lines were {text}")
        if "set timeout=5" not in text or text.count("chainloader") != 2:
            raise SystemExit(f"two windows lines were {text}")
    os.environ.pop("WASD_SELF_CHECK", None)
    print("windows boot self-check ok")


def main():
    parser = argparse.ArgumentParser(description="Keep Windows on the WASD boot menu")
    parser.add_argument("--root", default="/")
    parser.add_argument("--skip", action="append", default=[])
    parser.add_argument("--lsblk")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return 0
    skip = []
    for name in args.skip:
        if not DEVICE_NAME.fullmatch(name):
            print("The Windows menu was not changed.", file=sys.stderr)
            return 0
        skip.append(name)
    remounted = False
    try:
        if Path(args.root).resolve() == Path("/") and boot_is_ro():
            proc = subprocess.run(["mount", "-o", "remount,rw", "/boot"], capture_output=True)
            remounted = proc.returncode == 0
        payload = Path(args.lsblk).read_text() if args.lsblk else read_lsblk()
        if not payload:
            print("The Windows menu was not changed.", file=sys.stderr)
            return 0
        apply(args.root, payload, set(skip), mount_has_loader)
    except Exception as exc:
        print(f"The Windows menu was not changed. {exc}", file=sys.stderr)
        return 0
    finally:
        if remounted:
            subprocess.run(["mount", "-o", "remount,ro", "/boot"], capture_output=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
