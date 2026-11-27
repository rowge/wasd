"""Disk list for WASD Install.

The preview feeds this a sample. The live USB reads lsblk. Nothing here
partitions, formats, or erases a disk.
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

OS_FS = {"ext4", "btrfs", "xfs", "ntfs", "bitlocker", "crypto_luks"}
DEVICE_NAME = re.compile(r"^(nvme[0-9]+n[0-9]+|sd[a-z]+|vd[a-z]+|mmcblk[0-9]+|hd[a-z]+)$")
PART_NAME = re.compile(
    r"^(nvme[0-9]+n[0-9]+p[0-9]+|sd[a-z]+[0-9]+|vd[a-z]+[0-9]+|mmcblk[0-9]+p[0-9]+|hd[a-z]+[0-9]+)$"
)
GIB = 1024 ** 3
LIBRARY_ROOTS = (
    "Program Files (x86)/Steam",
    "Program Files/Steam",
    "SteamLibrary",
)


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


def _library_list(value):
    if isinstance(value, str):
        value = value.split("\n")
    if not isinstance(value, list):
        return []
    found = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text and text not in found:
            found.append(text)
    return found


def _ntfs_row(node, size):
    return {
        "part": str(node.get("name") or ""),
        "fs": (node.get("fstype") or "").lower(),
        "uuid": str(node.get("uuid") or ""),
        "size": size,
        "free": disk_bytes(node.get("fsavail")),
        "hibernated": bool(node.get("hibernated")),
        "libraries": _library_list(node.get("libraries")),
    }


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
        games_free = 0
        data_part = ""
        data_fs = ""
        data_uuid = ""
        data_bytes = -1
        ntfs_info = None
        library_info = None
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
            mounted_libraries = []
            for mount in _mounts(node):
                root = Path(mount)
                try:
                    if (root / "SteamLibrary" / "steamapps").is_dir():
                        mounted_libraries = ["SteamLibrary"]
                        break
                    if (root / "steamapps").is_dir():
                        mounted_libraries = ["."]
                        break
                except OSError:
                    continue
            steam = bool(mounted_libraries)
            size = disk_bytes(node.get("size"))
            if fs == "ntfs" and node.get("uuid"):
                info = _ntfs_row(node, size)
                if mounted_libraries and not info["libraries"]:
                    info["libraries"] = mounted_libraries
                if ntfs_info is None or size >= ntfs_info["size"]:
                    ntfs_info = info
                if info["libraries"] and (library_info is None or size >= library_info["size"]):
                    library_info = info
            if (marked or steam) and size >= games_bytes:
                games = True
                games_part = str(node.get("name") or "")
                games_fs = fs
                games_uuid = str(node.get("uuid") or "")
                games_bytes = size
                games_free = disk_bytes(node.get("fsavail"))
            elif fs in {"btrfs", "ext4", "xfs", "ntfs", "exfat"} and size > data_bytes:
                data_part = str(node.get("name") or "")
                data_fs = fs
                data_uuid = str(node.get("uuid") or "")
                data_bytes = size
        libraries = []
        free = 0
        hibernated = False
        if windows:
            kind = "Windows is on this drive."
            games = False
            chosen = library_info or ntfs_info
            if chosen:
                part = chosen["part"]
                fstype = chosen["fs"]
                uuid = chosen["uuid"]
                libraries = chosen["libraries"]
                free = chosen["free"]
                hibernated = chosen["hibernated"]
            else:
                part = ""
                fstype = ""
                uuid = ""
        else:
            if library_info and (not games or library_info["size"] >= games_bytes):
                games = True
                part = library_info["part"]
                fstype = library_info["fs"]
                uuid = library_info["uuid"]
                libraries = library_info["libraries"]
                free = library_info["free"]
                hibernated = library_info["hibernated"]
            else:
                part = games_part or data_part
                fstype = games_fs if games else data_fs
                uuid = games_uuid if games else data_uuid
                free = games_free
            kind = "Another system is on this drive." if occupied else ""
        rota = dev.get("rota")
        rotational = bool(rota) if "rota" in dev and rota is not None else False
        usb = str(dev.get("tran") or "").lower() == "usb"
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
                "part": part,
                "fstype": fstype,
                "uuid": uuid,
                "free": free,
                "hibernated": hibernated,
                "libraries": libraries,
                "steam": bool(libraries),
                "rotational": rotational,
                "usb": usb,
                "solid": not rotational and not usb,
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
        fstype = (node.get("fstype") or "").lower()
        hit = label.casefold() == "wasd" or fstype == "iso9660"
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


def parent_disk(name):
    if name.startswith(("nvme", "mmcblk")):
        return re.sub(r"p\d+$", "", name)
    return re.sub(r"\d+$", "", name)


def live_usb_from_os():
    """The disk behind /dev/disk/by-label/WASD, when this is the live system."""
    found = set()
    try:
        link = Path("/dev/disk/by-label/WASD")
        if link.exists():
            parent = parent_disk(link.resolve().name)
            if parent:
                found.add(parent)
    except OSError:
        return found
    return found


def _solid(disk):
    if "solid" in disk:
        return bool(disk["solid"])
    return not disk.get("rotational") and not disk.get("usb")


def _keepable(disk):
    fstype = str(disk.get("fstype") or "").lower()
    return bool(disk.get("part")) and bool(disk.get("uuid")) and fstype != "bitlocker"


def windows_library(disk):
    """A Windows drive that can be mounted at /games without formatting it."""
    if not disk.get("windows") or disk.get("hibernated") or not _keepable(disk):
        return False
    if disk.get("steam") or disk.get("libraries"):
        return True
    return int(disk.get("free") or 0) >= 64 * GIB


def _usable_gb(disk):
    return max(0, int(disk.get("bytes") or 0) // GIB - 4)


def choose_layout(disks):
    """The install the page starts with.

    system and games are indexes. games is -1 when the system drive is split
    or when there is no /games. mode is split, format, keep, or off.
    """
    blanks = [
        index
        for index, disk in enumerate(disks)
        if not disk.get("occupied") and not disk.get("windows")
    ]
    solid = [index for index in blanks if _solid(disks[index])]
    pool = solid or blanks
    if len(pool) >= 2:
        games = max(pool, key=lambda index: (int(disks[index].get("bytes") or 0), index))
        rest = [index for index in pool if index != games]
        system = max(rest, key=lambda index: (int(disks[index].get("bytes") or 0), -index))
        return {"system": system, "games": games, "mode": "format"}
    if len(pool) == 1:
        system = pool[0]
        for index, disk in enumerate(disks):
            if index != system and disk.get("games") and not disk.get("windows") and _keepable(disk):
                return {"system": system, "games": index, "mode": "keep"}
        for index, disk in enumerate(disks):
            if index != system and windows_library(disk):
                return {"system": system, "games": index, "mode": "keep"}
        if _usable_gb(disks[system]) >= 96:
            return {"system": system, "games": -1, "mode": "split"}
        return {"system": system, "games": -1, "mode": "off"}
    if len(disks) == 1:
        mode = "split" if _usable_gb(disks[0]) >= 96 else "off"
        return {"system": 0, "games": -1, "mode": mode}
    return {"system": -1, "games": -1, "mode": "off"}


def _add_library(found, relative):
    if relative and relative not in found:
        found.append(relative)


def libraries_in_vdf(root, vdf):
    try:
        text = vdf.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found = []
    root_real = root.resolve()
    for raw in re.findall(r'"path"\s+"([^"]*)"', text):
        relative = raw.replace("\\", "/").strip()
        if len(relative) >= 2 and relative[1] == ":":
            relative = relative[2:]
        parts = [part for part in relative.split("/") if part not in {"", "."}]
        if not parts or any(part == ".." for part in parts):
            continue
        relative = "/".join(parts)
        folder = root_real.joinpath(*parts)
        try:
            folder.relative_to(root_real)
        except ValueError:
            continue
        apps = folder / "steamapps"
        try:
            if apps.is_dir() and not apps.is_symlink():
                _add_library(found, relative)
        except OSError:
            continue
    return found


def libraries_at(root):
    """Steam libraries at the known Windows paths. This does not walk the disk."""
    found = []
    try:
        apps = root / "steamapps"
        if apps.is_dir() and not apps.is_symlink():
            _add_library(found, ".")
    except OSError:
        pass
    for relative in LIBRARY_ROOTS:
        folder = root.joinpath(*relative.split("/"))
        try:
            apps = folder / "steamapps"
            if apps.is_dir() and not apps.is_symlink():
                _add_library(found, relative)
        except OSError:
            continue
    for relative in LIBRARY_ROOTS[:2]:
        vdf = root.joinpath(*relative.split("/")) / "steamapps" / "libraryfolders.vdf"
        for extra in libraries_in_vdf(root, vdf):
            _add_library(found, extra)
    return found


def probe_ntfs(name):
    """Read free space, Fast Startup, and Steam libraries. Nothing is written."""
    device = Path("/dev") / name
    try:
        if not device.exists():
            return None
    except OSError:
        return None
    mountpoint = Path(tempfile.mkdtemp(prefix="wasd-ntfs-"))
    try:
        result = subprocess.run(
            ["mount", "-t", "ntfs3", "-o", "ro", str(device), str(mountpoint)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            text = f"{result.stderr}\n{result.stdout}".lower()
            return {"hibernated": "hibernat" in text, "libraries": [], "free": 0}
        free = 0
        try:
            usage = os.statvfs(mountpoint)
            free = usage.f_bavail * usage.f_frsize
        except OSError:
            free = 0
        return {"hibernated": False, "libraries": libraries_at(mountpoint), "free": free}
    except OSError:
        return None
    finally:
        subprocess.run(["umount", str(mountpoint)], capture_output=True)
        try:
            mountpoint.rmdir()
        except OSError:
            pass


def annotate_ntfs(data):
    if os.environ.get("WASD_DISK_PROBE") == "0":
        return
    for dev in data.get("blockdevices") or []:
        for node in walk(dev):
            if node is dev:
                continue
            name = str(node.get("name") or "")
            if (node.get("fstype") or "").lower() != "ntfs" or not PART_NAME.fullmatch(name):
                continue
            if node.get("libraries") or node.get("hibernated"):
                continue
            found = probe_ntfs(name)
            if not found:
                continue
            node["hibernated"] = found["hibernated"]
            node["libraries"] = found["libraries"]
            if found["free"]:
                node["fsavail"] = found["free"]


def shown_disks(payload, extra_banned=()):
    """Disks a person can install onto. The live USB and zram stay off the list."""
    banned = set(live_disk_names(payload)) | set(extra_banned)
    shown = []
    for disk in parse_disks(payload):
        device = disk["device"]
        if not DEVICE_NAME.fullmatch(device) or device in banned:
            continue
        shown.append(disk)
    return shown


def live_disks():
    result = subprocess.run(
        [
            "lsblk", "-J", "-b", "-o",
            "NAME,SIZE,MODEL,TYPE,FSTYPE,LABEL,UUID,MOUNTPOINTS,ROTA,TRAN,FSAVAIL",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    annotate_ntfs(payload)
    return shown_disks(payload, live_usb_from_os())


def live_payload():
    disks = live_disks()
    warnings = []
    if any(disk["windows"] for disk in disks):
        warnings.append("Turn off BitLocker and fast startup in Windows before you install.")
    legacy = not Path("/sys/firmware/efi").is_dir()
    if legacy:
        warnings.append("Set the firmware to UEFI in the BIOS. The motherboard manual explains how.")
    if secure_boot_on():
        warnings.append(
            "Secure Boot is on. The next boot is a blue screen. "
            "The steps are at wasd.run/mok. The password is universalblue."
        )
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
    if marked[1]["games"] or not marked[1]["windows"]:
        raise SystemExit(f"windows disk became a games drive {marked[1]}")
    if marked[1]["part"] != "nvme1n1p2" or marked[1]["fstype"] != "ntfs" or not marked[1]["uuid"]:
        raise SystemExit(f"windows disk hid its ntfs partition {marked[1]}")
    hidden = {
        "blockdevices": [
            payload["blockdevices"][0],
            payload["blockdevices"][1],
            {"name": "zram0", "type": "disk", "size": 16_000_000_000, "model": ""},
            {
                "name": "sdb",
                "type": "disk",
                "size": 32_000_000_000,
                "model": "Cruzer Fit",
                "children": [{"name": "sdb1", "type": "part", "fstype": "iso9660"}],
            },
        ]
    }
    visible = [disk["device"] for disk in shown_disks(hidden)]
    if visible != ["nvme0n1"]:
        raise SystemExit(f"live usb or zram stayed on the list {visible}")
    if parent_disk("nvme0n1p1") != "nvme0n1" or parent_disk("sda1") != "sda":
        raise SystemExit("parent disk names were wrong")
    windows_games = parse_disks({
        "blockdevices": [
            {
                "name": "nvme0n1",
                "type": "disk",
                "size": 1_000_000_000_000,
                "rota": False,
                "tran": "nvme",
                "children": [],
            },
            {
                "name": "nvme1n1",
                "type": "disk",
                "size": 2_000_000_000_000,
                "rota": False,
                "tran": "nvme",
                "children": [{
                    "name": "nvme1n1p3",
                    "type": "part",
                    "fstype": "ntfs",
                    "label": "Windows",
                    "uuid": "abcdefab-1234-1234-1234-123456789abc",
                    "size": 1_900_000_000_000,
                    "fsavail": 400 * GIB,
                    "libraries": ["Program Files (x86)/Steam"],
                }],
            },
        ]
    })
    if windows_games[1]["games"] or not windows_games[1]["steam"]:
        raise SystemExit(f"windows library was misread {windows_games[1]}")
    if windows_games[1]["libraries"] != ["Program Files (x86)/Steam"] or windows_games[1]["free"] != 400 * GIB:
        raise SystemExit(f"windows library details {windows_games[1]}")
    slow = {
        "occupied": False,
        "windows": False,
        "bytes": 4_000_000_000_000,
        "rotational": True,
        "solid": False,
    }
    fast = {
        "occupied": False,
        "windows": False,
        "bytes": 1_000_000_000_000,
        "solid": True,
    }
    picked = choose_layout([slow, fast])
    if picked != {"system": 1, "games": -1, "mode": "split"}:
        raise SystemExit(f"a spinning disk was chosen for games {picked}")
    big = {"occupied": False, "windows": False, "bytes": 4_000_000_000_000, "solid": True}
    small = {"occupied": False, "windows": False, "bytes": 1_000_000_000_000, "solid": True}
    sized = choose_layout([small, big])
    if sized != {"system": 0, "games": 1, "mode": "format"}:
        raise SystemExit(f"the larger blank disk was not /games {sized}")
    library = {
        "occupied": True,
        "windows": True,
        "bytes": 2_000_000_000_000,
        "part": "nvme1n1p3",
        "fstype": "ntfs",
        "uuid": "abcdefab-1234-1234-1234-123456789abc",
        "steam": True,
        "free": 20 * GIB,
        "hibernated": False,
    }
    blank = {"occupied": False, "windows": False, "bytes": 1_000_000_000_000, "solid": True}
    kept = choose_layout([blank, library])
    if kept != {"system": 0, "games": 1, "mode": "keep"}:
        raise SystemExit(f"a Windows Steam library was skipped {kept}")
    asleep = dict(library)
    asleep["hibernated"] = True
    if choose_layout([blank, asleep])["games"] != -1:
        raise SystemExit("a hibernated Windows drive was mounted")
    crowded = dict(library)
    crowded["steam"] = False
    crowded["libraries"] = []
    crowded["free"] = 10 * GIB
    if choose_layout([blank, crowded])["mode"] != "split":
        raise SystemExit("a full Windows drive without Steam was used")
    same = {"occupied": False, "windows": False, "bytes": 2_000_000_000_000, "solid": True}
    tied = choose_layout([dict(same), dict(same)])
    if tied != {"system": 0, "games": 1, "mode": "format"}:
        raise SystemExit(f"equal disks broke the tie wrong {tied}")
    both = choose_layout([
        {"occupied": False, "windows": False, "bytes": 1_000_000_000_000, "solid": True},
        {"occupied": False, "windows": False, "bytes": 2_000_000_000_000, "solid": True},
        library,
    ])
    if both != {"system": 0, "games": 1, "mode": "format"}:
        raise SystemExit(f"Windows was used beside two blank drives {both}")
    usb = choose_layout([
        {"occupied": False, "windows": False, "bytes": 4_000_000_000_000, "usb": True, "solid": False},
        {"occupied": False, "windows": False, "bytes": 500_000_000_000, "solid": True},
    ])
    if usb != {"system": 1, "games": -1, "mode": "split"}:
        raise SystemExit(f"a USB disk was chosen over an internal drive {usb}")
    with tempfile.TemporaryDirectory(prefix="wasd-libraries-") as raw:
        root = Path(raw)
        steam = root / "Program Files (x86)" / "Steam" / "steamapps"
        steam.mkdir(parents=True)
        (steam / "libraryfolders.vdf").write_text(
            '"libraryfolders"\n{\n'
            '\t"0"\n\t{\n\t\t"path"\t\t"C:\\\\Program Files (x86)\\\\Steam"\n\t}\n'
            '\t"1"\n\t{\n\t\t"path"\t\t"D:\\\\SteamLibrary"\n\t}\n'
            '\t"2"\n\t{\n\t\t"path"\t\t"C:\\\\..\\\\etc"\n\t}\n'
            '\t"3"\n\t{\n\t\t"path"\t\t"C:\\\\MissingLibrary"\n\t}\n'
            "}\n",
            encoding="utf-8",
        )
        (root / "SteamLibrary" / "steamapps").mkdir(parents=True)
        found = libraries_at(root)
        if found != ["Program Files (x86)/Steam", "SteamLibrary"]:
            raise SystemExit(f"known libraries were missed {found}")
        outside = root / "outside"
        outside.mkdir()
        escaped = libraries_in_vdf(root, steam / "libraryfolders.vdf")
        if any(item.startswith("/") or ".." in item.split("/") for item in escaped):
            raise SystemExit(f"a library escaped the drive {escaped}")
        if "MissingLibrary" in escaped:
            raise SystemExit("a missing library was recorded")
    with tempfile.TemporaryDirectory(prefix="wasd-root-library-") as raw:
        root = Path(raw)
        (root / "steamapps").mkdir()
        if libraries_at(root) != ["."]:
            raise SystemExit(f"a library at the root was missed {libraries_at(root)}")
