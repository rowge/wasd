#!/usr/bin/env python3
"""Install the WASD Plasma theme pack into the image.

The KDE Store global theme is only the look-and-feel package. Applying it
also needs the color scheme, window border, Kvantum theme, Plasma theme,
and icon theme that package names. Those files are pinned in theme-pack.tsv.
The download link expires, so the build asks the store for a fresh link and
checks the pinned checksum.

We10XOS-dark is the default global theme. The desktop wallpaper stays the
WASD stained-glass picture, and the session splash stays the WASD W.
"""

import argparse
import hashlib
import os
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "theme-pack.tsv"
USER_AGENT = "wasd-theme-pack"
DEFAULT_LOOK = "com.github.yeyushengfan258.We10XOS-dark"
SPLASH_THEME = "com.valve.vapor.desktop"
KVANTUM_THEME = "We10XOS-dark"

LOOK_AND_FEEL = (
    "Sweet",
    "com.github.vinceliuice.Layan",
    DEFAULT_LOOK,
    "Ant-Dark",
    "Nordic",
    "com.github.vinceliuice.ChromeOS-dark",
    "Otto",
    "Carl",
    "com.github.vinceliuice.WhiteSur-dark",
    "Edna-Light",
    "org.magpie.expose.desktop",
    "org.magpie.exblue.desktop",
    "org.magpie.exgreen.desktop",
    "org.magpie.exmetal.desktop",
    "org.magpie.exdark.desktop",
    "org.magpie.exair.desktop",
    "org.magpie.exairdark.desktop",
)


def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


def read_manifest(path):
    rows = []
    seen = set()
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        content_id, md5 = line.split()
        if not content_id.isdigit() or len(md5) != 32:
            fail(f"bad theme pin: {line}")
        if content_id in seen:
            fail(f"theme {content_id} is pinned twice")
        seen.add(content_id)
        rows.append((content_id, md5.lower()))
    if len(rows) < 17:
        fail("the theme pack pin is missing packages")
    return rows


class MissingFile(Exception):
    """This store item has no file in that slot."""


def fetch_slot(content_id, slot):
    meta = urllib.request.Request(
        f"https://api.pling.com/ocs/v1/content/download/{content_id}/{slot}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(meta, timeout=60) as response:
        root = ET.fromstring(response.read())
    status = root.find("./meta/statuscode")
    link = root.find(".//downloadlink")
    if status is None or status.text != "100" or link is None or not link.text:
        raise MissingFile()
    name = link.text.rsplit("/", 1)[-1]
    req = urllib.request.Request(link.text, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=180) as response:
        return response.read(), name


def download(content_id, md5, cache):
    cached = sorted(cache.glob(f"{content_id}--*")) if cache else []
    for path in cached:
        digest = hashlib.md5(path.read_bytes()).hexdigest()
        if digest == md5:
            return path.read_bytes(), path.name.split("--", 1)[1]
    # The pinned file is not always the first one. WhiteSur's solid Kvantum
    # archive answers HTTP 500, and the translucent archive is the next file.
    last = None
    for slot in range(1, 6):
        for attempt in range(3):
            try:
                blob, name = fetch_slot(content_id, slot)
                digest = hashlib.md5(blob).hexdigest()
                if digest != md5:
                    break
                if cache:
                    cache.mkdir(parents=True, exist_ok=True)
                    (cache / f"{content_id}--{name}").write_bytes(blob)
                return blob, name
            except MissingFile:
                fail(f"theme {content_id} checksum was not in the published files")
            except SystemExit:
                raise
            except Exception as exc:
                last = exc
                print(
                    f"theme {content_id} file {slot} retry {attempt + 1}: {exc}",
                    file=sys.stderr,
                )
                time.sleep(2 + attempt)
        else:
            continue
    fail(f"theme {content_id} did not download: {last}")


def safe_name(name):
    if not name or name in {".", ".."} or "/" in name or name.startswith("."):
        return ""
    return name


def read_json_text(path):
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def is_look_and_feel(directory):
    text = read_json_text(directory / "metadata.json")
    return "Plasma/LookAndFeel" in text


def is_icon_theme(directory):
    index = directory / "index.theme"
    if not index.is_file():
        return False
    return "[Icon Theme]" in index.read_text(encoding="utf-8", errors="replace")


def is_kvantum(directory):
    return any(directory.glob("*.kvconfig"))


def is_aurorae(directory):
    if (directory / "widgets").is_dir() or (directory / "dialogs").is_dir():
        return False
    has_meta = (directory / "metadata.desktop").is_file() or (directory / "metadata.json").is_file()
    return has_meta and (directory / "decoration.svg").is_file()


def is_desktop_theme(directory):
    if is_look_and_feel(directory) or is_icon_theme(directory) or is_kvantum(directory):
        return False
    if (directory / "widgets").is_dir() or (directory / "dialogs").is_dir():
        return True
    text = read_json_text(directory / "metadata.json") + read_json_text(directory / "metadata.desktop")
    return "Plasma/Theme" in text or "Plasma Theme" in text


def place(directory, root):
    name = safe_name(directory.name)
    if not name:
        return ""
    if is_look_and_feel(directory):
        dest = root / "usr/share/plasma/look-and-feel" / name
    elif is_icon_theme(directory):
        dest = root / "usr/share/icons" / name
    elif is_kvantum(directory):
        dest = root / "usr/share/Kvantum" / name
    elif is_aurorae(directory):
        dest = root / "usr/share/aurorae/themes" / name
    elif is_desktop_theme(directory):
        dest = root / "usr/share/plasma/desktoptheme" / name
    else:
        return ""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(directory, dest, symlinks=True)
    return str(dest.relative_to(root))


def split_kvantum(directory, root):
    # Kvantum loads Theme/Theme.kvconfig. Some archives keep a dark theme
    # beside the light one in a single folder, so give that theme its own folder.
    if not is_kvantum(directory):
        return []
    placed = []
    for config in sorted(directory.glob("*.kvconfig")):
        theme = safe_name(config.stem)
        if not theme or theme == directory.name:
            continue
        dest = root / "usr/share/Kvantum" / theme
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        shutil.copy2(config, dest / config.name)
        svg = directory / f"{theme}.svg"
        if svg.is_file():
            shutil.copy2(svg, dest / svg.name)
        placed.append(str(dest.relative_to(root)))
    return placed


def install_tree(extracted, root):
    placed = []

    def take(path):
        if path.is_file() and path.name.endswith(".colors"):
            dest = root / "usr/share/color-schemes" / path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            placed.append(str(dest.relative_to(root)))
            return
        if not path.is_dir():
            return
        target = place(path, root)
        if target:
            placed.append(target)
            placed.extend(split_kvantum(path, root))

    tops = [path for path in extracted.iterdir() if path.name != "__MACOSX"]
    for path in tops:
        take(path)
    if not placed:
        for path in tops:
            if path.is_dir():
                for child in path.iterdir():
                    take(child)
    return placed


def theme_tar_filter(member, dest_path):
    # One icon archive links a size folder at the packager's home directory.
    # Drop links that leave the archive. Keep the real files.
    if (member.issym() or member.islnk()) and member.linkname.startswith("/"):
        return None
    return tarfile.data_filter(member, dest_path)


def install_blob(blob, name, root):
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        source = folder / "pack"
        source.write_bytes(blob)
        extracted = folder / "out"
        extracted.mkdir()
        if zipfile.is_zipfile(source):
            with zipfile.ZipFile(source) as archive:
                for info in archive.infolist():
                    member = info.filename
                    if member.startswith("/") or ".." in Path(member).parts:
                        fail(f"{name} has an unsafe path")
                archive.extractall(extracted)
        elif tarfile.is_tarfile(source):
            with tarfile.open(source) as archive:
                archive.extractall(extracted, filter=theme_tar_filter)
        elif name.endswith(".colors") or b"[Colors]" in blob[:400] or b"[Color" in blob[:400]:
            dest = root / "usr/share/color-schemes" / Path(name).name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(blob)
            return [str(dest.relative_to(root))]
        else:
            fail(f"{name} is not a theme archive")
        placed = install_tree(extracted, root)
        if not placed:
            names = [path.name for path in extracted.rglob("*") if path.is_file()][:12]
            fail(f"{name} did not contain a theme package: {names}")
        return placed


def parse_defaults(text):
    sections = []
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]") and "][" in line:
            file_name, group = line[1:-1].split("][", 1)
            current = [file_name, group, []]
            sections.append(current)
            continue
        if current and line and not line.startswith(("#", ";")) and "=" in line:
            key, value = line.split("=", 1)
            current[2].append((key.strip(), value.strip()))
    return sections


def read_config(path):
    groups = {}
    order = []
    current = None
    if path.is_file():
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if line.startswith("[") and line.endswith("]") and "][" not in line:
                current = line[1:-1]
                if current not in groups:
                    groups[current] = []
                    order.append(current)
                continue
            if current and line and not line.startswith(("#", ";")) and "=" in line:
                key, value = line.split("=", 1)
                groups[current].append((key.strip(), value))
    return groups, order


def write_config(path, groups, order):
    lines = []
    seen = set()
    for group in order + [name for name in groups if name not in order]:
        if group in seen:
            continue
        seen.add(group)
        if lines:
            lines.append("")
        lines.append(f"[{group}]")
        for key, value in groups.get(group, []):
            lines.append(f"{key}={value}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def set_keys(path, group, updates):
    groups, order = read_config(path)
    rows = [(key, value) for key, value in groups.get(group, []) if key not in updates]
    for key, value in updates.items():
        rows.append((key, value))
    groups[group] = rows
    if group not in order:
        order.append(group)
    write_config(path, groups, order)


def apply_default(root):
    package = root / "usr/share/plasma/look-and-feel" / DEFAULT_LOOK
    defaults = package / "contents/defaults"
    if not defaults.is_file():
        fail("We10XOS-dark has no defaults file")
    splash = package / "contents/splash"
    if splash.exists():
        shutil.rmtree(splash)
    icons = root / "usr/share/icons"
    # The published icon file is named We10X-black. The global theme asks for We10X.
    alias_icon(icons, "We10X", "We10X-black")
    # Nordic asks for candy-Nordic-green. The store file is the green folder set.
    alias_icon(icons, "candy-Nordic-green", "Nordic-green")
    for relative in ("etc/xdg", "etc/skel/.config"):
        base = root / relative
        for file_name, group, pairs in parse_defaults(defaults.read_text(encoding="utf-8")):
            if file_name == "kcminputrc":
                continue
            updates = {key: value for key, value in pairs if key != "cursorTheme"}
            if not updates:
                continue
            set_keys(base / file_name, group, updates)
        set_keys(
            base / "kdeglobals",
            "KDE",
            {"LookAndFeelPackage": DEFAULT_LOOK, "widgetStyle": "kvantum"},
        )
        set_keys(base / "ksplashrc", "KSplash", {"Engine": "KSplashQML", "Theme": SPLASH_THEME})
        kvantum = base / "Kvantum/kvantum.kvconfig"
        set_keys(kvantum, "General", {"theme": KVANTUM_THEME})


def alias_icon(icons, wanted, target):
    link = icons / wanted
    if link.exists() or link.is_symlink():
        return
    if (icons / target).is_dir():
        link.symlink_to(target)


def require(path):
    if not path.exists():
        fail(f"missing {path}")


def check(root):
    for name in LOOK_AND_FEEL:
        require(root / "usr/share/plasma/look-and-feel" / name / "metadata.json")
    require(root / "usr/share/color-schemes/We10XOSDark.colors")
    require(root / "usr/share/aurorae/themes/We10XOS-dark/metadata.desktop")
    require(root / "usr/share/plasma/desktoptheme/We10XOS-dark")
    require(root / "usr/share/Kvantum/We10XOS-dark/We10XOS-dark.kvconfig")
    require(root / "usr/share/Kvantum/WhiteSurDark/WhiteSurDark.kvconfig")
    for icon in (
        "Tela",
        "Tela-dark",
        "candy-icons",
        "We10X",
        "We10X-black",
        "kora",
        "McMojave-circle-dark",
        "Ant-Dark",
        "candy-Nordic-green",
        "WhiteSur-dark",
        "Fluent",
        "Eleven",
        "ExposeAir",
        "ExposeAirDark",
        "Reactionary",
    ):
        require(root / "usr/share/icons" / icon / "index.theme")
    kdeglobals = (root / "etc/xdg/kdeglobals").read_text(encoding="utf-8")
    if f"LookAndFeelPackage={DEFAULT_LOOK}" not in kdeglobals:
        fail("the default global theme was not set")
    if "ColorScheme=We10XOSDark" not in kdeglobals:
        fail("the default color scheme was not set")
    ksplash = (root / "etc/xdg/ksplashrc").read_text(encoding="utf-8")
    if f"Theme={SPLASH_THEME}" not in ksplash:
        fail("the session splash was not left on the WASD mark")
    kvantum = (root / "etc/skel/.config/Kvantum/kvantum.kvconfig").read_text(encoding="utf-8")
    if f"theme={KVANTUM_THEME}" not in kvantum:
        fail("the default Kvantum theme was not set")
    splash = root / "usr/share/plasma/look-and-feel" / DEFAULT_LOOK / "contents/splash"
    if splash.exists():
        fail("We10XOS-dark still ships its own session splash")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="/")
    parser.add_argument("--manifest", default=str(MANIFEST))
    parser.add_argument("--cache", default=os.environ.get("WASD_THEME_CACHE", ""))
    args = parser.parse_args()
    root = Path(args.root)
    cache = Path(args.cache) if args.cache else None
    rows = read_manifest(Path(args.manifest))
    for content_id, md5 in rows:
        blob, name = download(content_id, md5, cache)
        placed = install_blob(blob, name, root)
        print(f"{content_id} {name}: {', '.join(placed)}")
    apply_default(root)
    check(root)
    print(f"theme pack installed, default {DEFAULT_LOOK}")


if __name__ == "__main__":
    main()
