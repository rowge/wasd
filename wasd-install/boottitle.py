#!/usr/bin/env python3
"""Name every ostree boot entry WASD.

ostree titles the menu "WASD (ostree:0)". The entry should say WASD
after install and after a later update. A Windows menu entry is not a
boot loader snippet, so it is left alone.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ENTRY_DIRS = (
    "boot/loader/entries",
    "boot/efi/loader/entries",
    "loader/entries",
)
EFI_TYPE = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
ESP_MOUNT = Path("/run/wasd-esp")
DEVICE_NAME = re.compile(r"^(nvme[0-9]+n[0-9]+|sd[a-z]+|vd[a-z]+|mmcblk[0-9]+|hd[a-z]+)$")
PART_NAME = re.compile(
    r"^(nvme[0-9]+n[0-9]+p[0-9]+|sd[a-z]+[0-9]+|vd[a-z]+[0-9]+|mmcblk[0-9]+p[0-9]+|hd[a-z]+[0-9]+)$"
)


def entry_directories(root):
    """Boot-entry folders under this root. A link that leaves the root is skipped."""
    base = Path(root).resolve()
    found = []
    if base == Path("/") and os.environ.get("WASD_SELF_CHECK") == "1":
        return found
    for rel in ENTRY_DIRS:
        directory = Path(root) / rel
        if directory.is_symlink():
            target = directory.resolve()
            if not target.is_dir() or not target.is_relative_to(base):
                continue
            directory = target
        elif not directory.is_dir():
            continue
        resolved = directory.resolve()
        if not resolved.is_relative_to(base):
            continue
        found.append(resolved)
    return found


def ostree_entry(text):
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("options ") and "ostree=" in stripped:
            return True
        if stripped.startswith(("linux ", "initrd ")) and "/ostree/" in stripped:
            return True
    return False


def retitle(text):
    """Return the entry with its title set to WASD, and whether it changed."""
    if not ostree_entry(text):
        return text, False
    newline = text.endswith("\n")
    changed = False
    lines = []
    for line in text.splitlines():
        if line.startswith("title ") or line.startswith("title\t"):
            if line.strip() != "title WASD":
                changed = True
                line = "title WASD"
        lines.append(line)
    rendered = "\n".join(lines)
    if newline or not rendered:
        rendered += "\n"
    return rendered, changed


def rewrite(root):
    """Set the title of each ostree entry under root. Returns how many changed."""
    changed = 0
    for directory in entry_directories(root):
        for path in sorted(directory.glob("*.conf")):
            if not path.is_file() or path.is_symlink():
                continue
            if not path.resolve().is_relative_to(directory):
                continue
            updated, did = retitle(path.read_text(errors="replace"))
            if did:
                path.write_text(updated)
                changed += 1
    return changed


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


def esp_name(device, listing):
    """The install disk's EFI partition, when it is not already mounted."""
    if not DEVICE_NAME.fullmatch(device or ""):
        return ""
    import json

    try:
        blob = json.loads(listing)
    except json.JSONDecodeError:
        return ""
    for dev in blob.get("blockdevices") or []:
        if dev.get("type") != "disk" or dev.get("name") != device:
            continue
        for node in dev.get("children") or []:
            name = str(node.get("name") or "")
            if node.get("type") != "part" or not PART_NAME.fullmatch(name) or not name.startswith(device):
                continue
            if str(node.get("fstype") or "").lower() != "vfat":
                continue
            label = str(node.get("label") or "")
            parttype = str(node.get("parttype") or "").lower()
            if label != "EFI-SYSTEM" and parttype != EFI_TYPE:
                continue
            mounts = node.get("mountpoints") or node.get("mountpoint") or []
            if isinstance(mounts, str):
                mounts = [mounts]
            if any(mounts):
                continue
            return name
    return ""


def read_block_list():
    proc = subprocess.run(
        ["lsblk", "-J", "-b", "-o", "NAME,TYPE,FSTYPE,LABEL,PARTTYPE,MOUNTPOINTS"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout


def name_installed(sysroot, device):
    """Rename entries on the new system. A miss does not fail the install.

    The root holds /boot when that directory is on the WASD filesystem.
    The EFI partition is mounted on its own when it is not already mounted.
    """
    if os.environ.get("WASD_SELF_CHECK") == "1":
        raise SystemExit("self-check tried to name the boot menu")
    root = Path(sysroot)
    if not root.is_dir() or root.is_symlink() or root.resolve() == Path("/").resolve():
        return 0
    changed = rewrite(root)
    part = esp_name(device, read_block_list())
    if not part:
        return changed
    if ESP_MOUNT.is_symlink() or os.path.ismount(ESP_MOUNT):
        return changed
    ESP_MOUNT.mkdir(parents=True, exist_ok=True)
    if any(ESP_MOUNT.iterdir()):
        return changed
    mounted = subprocess.run(
        ["mount", "-o", "rw", f"/dev/{part}", str(ESP_MOUNT)],
        capture_output=True,
        text=True,
    )
    if mounted.returncode != 0 or not os.path.ismount(ESP_MOUNT):
        return changed
    try:
        changed += rewrite(ESP_MOUNT)
    finally:
        subprocess.run(["umount", str(ESP_MOUNT)], capture_output=True)
    return changed


def self_check():
    import tempfile

    sample = (
        "title WASD (ostree:0)\n"
        "version 1\n"
        "options ostree=/ostree/boot.1/default/hash/0 quiet\n"
        "linux /ostree/default/hash/0/vmlinuz\n"
    )
    updated, changed = retitle(sample)
    if not changed or "title WASD\n" not in updated or "(ostree:" in updated:
        raise SystemExit(f"the boot title stayed {updated!r}")
    again, twice = retitle(updated)
    if twice or again != updated:
        raise SystemExit("the boot title was renamed twice")
    windows = "title Windows\noptions root=UUID=abc\n"
    kept, touched = retitle(windows)
    if touched or kept != windows:
        raise SystemExit("a windows entry was renamed")
    plain = "title WASD (ostree:1)\nlinux /boot/vmlinuz\n"
    skipped, used = retitle(plain)
    if used or skipped != plain:
        raise SystemExit("a normal entry was renamed")
    with tempfile.TemporaryDirectory(prefix="wasd-boot-title-") as tmp:
        root = Path(tmp)
        folder = root / "boot/loader/entries"
        folder.mkdir(parents=True)
        (folder / "ostree-1.conf").write_text(sample)
        (folder / "other.conf").write_text(windows)
        outside = root.parent / "ostree-1.conf"
        if rewrite(root) != 1:
            raise SystemExit("the boot title was not written")
        text = (folder / "ostree-1.conf").read_text()
        if text.startswith("title WASD\n") and "(ostree:" not in text and (folder / "other.conf").read_text() == windows:
            pass
        else:
            raise SystemExit(f"the boot entry was {text!r}")
        if outside.exists():
            raise SystemExit("the boot title wrote outside the install")
        linked = root / "loader"
        linked.mkdir()
        link = root / "boot/efi"
        link.symlink_to(root.parent)
        if rewrite(root) != 0:
            raise SystemExit("a boot entry link left the install")
    listing = """
    {"blockdevices":[{"name":"nvme0n1","type":"disk","children":[
      {"name":"nvme0n1p2","type":"part","fstype":"vfat","label":"EFI-SYSTEM","parttype":"%s","mountpoints":[null]},
      {"name":"sda1","type":"part","fstype":"vfat","label":"EFI-SYSTEM","parttype":"%s","mountpoints":["/run/initramfs/live"]}
    ]}]}
    """ % (EFI_TYPE, EFI_TYPE)
    if esp_name("nvme0n1", listing) != "nvme0n1p2":
        raise SystemExit("the install EFI partition was missed")
    mounted = listing.replace("[null]", '["/boot/efi"]')
    if esp_name("nvme0n1", mounted):
        raise SystemExit("a mounted EFI partition was selected")
    if esp_name("sda", listing):
        raise SystemExit("the live disk was selected")
    print("boot title self-check ok")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Name the WASD boot menu")
    parser.add_argument("--root", default="/")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return 0
    remounted = False
    try:
        if Path(args.root).resolve() == Path("/") and boot_is_ro():
            proc = subprocess.run(["mount", "-o", "remount,rw", "/boot"], capture_output=True)
            remounted = proc.returncode == 0
        rewrite(args.root)
    except OSError as exc:
        print(f"The boot menu was not renamed. {exc}", file=sys.stderr)
        return 0
    finally:
        if remounted:
            subprocess.run(["mount", "-o", "remount,ro", "/boot"], capture_output=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
