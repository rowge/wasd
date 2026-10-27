#!/usr/bin/env python3
"""Apply the Look step on the installed system.

The loading picture, the login picture, the theme, and the wallpaper are
the ones chosen in Install WASD. The lock screen uses the login picture.
The session splash stays the WASD W. A theme wallpaper is not applied.

--rebuild asks rpm-ostree to include the loading picture. It does that only
when the root is / and this is not a self-check. It does not reboot.
A rebuild that cannot run still leaves the other choices in place.
"""

import argparse
import hashlib
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
from pathlib import Path

FILE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
USER_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
PACKAGE_NAME = re.compile(r"^[A-Za-z0-9._-]+$")
SPLASH = "com.valve.vapor.desktop"
SKIP_FILES = {"kcminputrc"}
# Package id, Kvantum skin, widget style. A missing skin is not guessed.
THEMES = {
    "Sweet KDE": ("Sweet", "Sweet-Ambar-Blue", "kvantum"),
    "Layan": ("com.github.vinceliuice.Layan", "Layan-solid", "kvantum-dark"),
    "We10XOS-dark": ("com.github.yeyushengfan258.We10XOS-dark", "We10XOS-dark", "kvantum"),
    "Ant-Dark": ("Ant-Dark", "Ant-Dark", "kvantum"),
    "Nordic": ("Nordic", "Nordic-Darker-Solid", "kvantum"),
    "ChromeOS": ("com.github.vinceliuice.ChromeOS-dark", "ChromeOS-dark", "kvantum-dark"),
    "Otto": ("Otto", "Otto", "kvantum-dark"),
    "Carl": ("Carl", "Carl", "kvantum-dark"),
    "WhiteSur-Dark": ("com.github.vinceliuice.WhiteSur-dark", "WhiteSurDark", "kvantum-dark"),
    "Edna-Light": ("Edna-Light", "Edna-Light", "kvantum"),
    "Expose": ("org.magpie.expose.desktop", "Expose", "kvantum"),
    "Expose Blue": ("org.magpie.exblue.desktop", None, "Breeze"),
    "Expose Green": ("org.magpie.exgreen.desktop", "ExposeGreen", "kvantum"),
    "Expose Metallic": ("org.magpie.exmetal.desktop", "ExposeMetallic", "kvantum"),
    "Expose Dark": ("org.magpie.exdark.desktop", "ExposeDark", "kvantum"),
    "Expose Air": ("org.magpie.exair.desktop", "ExposeAir", "kvantum"),
    "Expose Air Dark": ("org.magpie.exairdark.desktop", None, "kvantum"),
}
LOOK_MESSAGES = {
    "The desktop was not set.",
    "Choose a picture from the list.",
    "Choose a theme from the list.",
    "That picture is not installed.",
    "The wallpaper did not change.",
    "Could not prepare the loading picture.",
    "Choose the look again.",
}


class LookError(Exception):
    pass


def safe_file(name):
    return (
        isinstance(name, str)
        and name not in {".", ".."}
        and not name.startswith(".")
        and FILE_NAME.fullmatch(name) is not None
    )


def look_from(data):
    """Return the look dict, or None when the installer did not save one."""
    keys = ("loading", "login", "theme", "wallpaper")
    if not any(key in data for key in keys):
        return None
    if not all(key in data for key in keys):
        raise LookError("Choose the look again.")
    loading = data.get("loading")
    login = data.get("login")
    theme = data.get("theme")
    wallpaper = data.get("wallpaper")
    if not safe_file(loading) or not safe_file(login) or not safe_file(wallpaper):
        raise LookError("Choose a picture from the list.")
    if not isinstance(theme, str) or theme not in THEMES:
        raise LookError("Choose a theme from the list.")
    package, skin, widget = THEMES[theme]
    if PACKAGE_NAME.fullmatch(package) is None:
        raise LookError("Choose a theme from the list.")
    if skin is not None and PACKAGE_NAME.fullmatch(skin) is None:
        raise LookError("Choose a theme from the list.")
    return {
        "loading": loading,
        "login": login,
        "theme": theme,
        "package": package,
        "skin": skin,
        "widget": widget,
        "wallpaper": wallpaper,
    }


def look_problem(data):
    if not isinstance(data, dict):
        return "Choose the look again. Nothing was erased."
    try:
        look_from(data)
    except LookError:
        return "Choose the look again. Nothing was erased."
    return ""


def _live(root):
    return root.resolve() == Path("/").resolve() and os.environ.get("WASD_SELF_CHECK") != "1"


def _inside(folder, name):
    folder = folder.resolve()
    candidate = (folder / name).resolve()
    if not candidate.is_file() or folder not in candidate.parents:
        raise LookError("That picture is not installed.")
    return candidate


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
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def set_keys(path, group, updates):
    groups, order = read_config(path)
    rows = [(key, value) for key, value in groups.get(group, []) if key not in updates]
    for key, value in updates.items():
        rows.append((key, value))
    groups[group] = rows
    if group not in order:
        order.append(group)
    write_config(path, groups, order)


def skipped_pair(group, key, value):
    if key in {"cursorTheme", "cursorSize"}:
        return True
    low = key.lower()
    if "wallpaper" in low or "wallpaper" in group.lower():
        return True
    if low in {"image", "previewimage"} and "wallpaper" in value.lower():
        return True
    return False


def own(path, user):
    if os.geteuid() != 0 or not user:
        return
    try:
        record = pwd.getpwnam(user)
    except KeyError:
        return
    try:
        os.chown(path, record.pw_uid, record.pw_gid)
    except OSError:
        return


def own_under(home, path, user):
    if os.geteuid() != 0 or not user:
        return
    home = home.resolve()
    current = path.resolve()
    chain = []
    while current != home and home in current.parents:
        chain.append(current)
        current = current.parent
    for item in reversed(chain):
        own(item, user)


def write_text(path, text, user, home, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    os.chmod(path, mode)
    if home is not None and home in path.parents:
        own_under(home, path, user)


def config_bases(root, home):
    return [root / "etc/xdg", root / "etc/skel/.config", home / ".config"]


def apply_theme_files(root, home, user, look):
    package = root / "usr/share/plasma/look-and-feel" / look["package"]
    if not package.is_dir():
        raise LookError("Choose a theme from the list.")
    defaults = package / "contents/defaults"
    sections = []
    if defaults.is_file():
        sections = parse_defaults(defaults.read_text(encoding="utf-8", errors="replace"))
    for base in config_bases(root, home):
        for file_name, group, pairs in sections:
            if file_name in SKIP_FILES or not safe_file(file_name):
                continue
            updates = {
                key: value
                for key, value in pairs
                if not skipped_pair(group, key, value)
            }
            if updates:
                set_keys(base / file_name, group, updates)
                own_under(home, base / file_name, user)
        set_keys(
            base / "kdeglobals",
            "KDE",
            {"LookAndFeelPackage": look["package"], "widgetStyle": look["widget"]},
        )
        set_keys(
            base / "ksplashrc",
            "KSplash",
            {"Engine": "KSplashQML", "Theme": SPLASH},
        )
        own_under(home, base / "kdeglobals", user)
        own_under(home, base / "ksplashrc", user)
        if look["skin"]:
            kvantum = base / "Kvantum/kvantum.kvconfig"
            set_keys(kvantum, "General", {"theme": look["skin"]})
            own_under(home, kvantum, user)


def set_header(text, header, updates):
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == header:
            start = index
            break
    if start is None:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(header)
        for key, value in updates.items():
            lines.append(f"{key}={value}")
        return "\n".join(lines).rstrip() + "\n"
    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = index
            break
    body = lines[start + 1:end]
    for key, value in updates.items():
        prefix = key + "="
        found = False
        for index, line in enumerate(body):
            if line.startswith(prefix):
                body[index] = prefix + value
                found = True
                break
        if not found:
            body.append(prefix + value)
    return "\n".join(lines[: start + 1] + body + lines[end:]).rstrip() + "\n"


def write_lock(path, url, user, home):
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    text = set_header(text, "[Greeter]", {"WallpaperPlugin": "org.kde.image"})
    text = set_header(
        text,
        "[Greeter][Wallpaper][org.kde.image][General]",
        {"Image": url, "PreviewImage": url},
    )
    write_text(path, text, user, home)


def apply_login(root, home, user, login_name):
    url = f"file:///usr/share/wasd/login/{login_name}"
    for path in (
        root / "etc/xdg/kscreenlockerrc",
        root / "etc/skel/.config/kscreenlockerrc",
        home / ".config/kscreenlockerrc",
    ):
        write_lock(path, url, user, home)
    drop = root / "etc/plasmalogin.conf.d/zz-wasd-login.conf"
    text = (
        "[Greeter]\n"
        "WallpaperPlugin=org.kde.image\n"
        "\n"
        "[Greeter][Wallpaper][org.kde.image][General]\n"
        f"Image={url}\n"
        f"PreviewImage={url}\n"
    )
    write_text(drop, text, user, None)
    main = root / "etc/plasmalogin.conf"
    write_lock(main, url, user, None)


def apply_wallpaper_script(root, home, user, wallpaper_name):
    url = f"file:///usr/share/wallpapers/wasd/{wallpaper_name}"
    body = (
        "var allDesktops = desktops();\n"
        "for (var i = 0; i < allDesktops.length; i++) {\n"
        "    var desktop = allDesktops[i];\n"
        '    desktop.wallpaperPlugin = "org.kde.image";\n'
        '    desktop.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];\n'
        f'    desktop.writeConfig("Image", "{url}");\n'
        "}\n"
    )
    relative = Path(".local/share/plasma/shells/org.kde.plasma.desktop/contents/updates/zzz-wasd-choice.js")
    for base in (home, root / "etc/skel"):
        write_text(base / relative, body, user, home if base == home else None)


def prepare_loading(root, source):
    dest = root / "etc/wasd/loading-background.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() == ".png":
        dest.write_bytes(source.read_bytes())
        os.chmod(dest, 0o644)
        return dest
    converters = []
    if shutil.which("ffmpeg"):
        converters.append(["ffmpeg", "-y", "-loglevel", "error", "-i", str(source), str(dest)])
    if shutil.which("magick"):
        converters.append(["magick", str(source), str(dest)])
    if shutil.which("convert"):
        converters.append(["convert", str(source), str(dest)])
    for command in converters:
        proc = subprocess.run(command, capture_output=True)
        if proc.returncode == 0 and dest.is_file() and dest.stat().st_size > 0:
            os.chmod(dest, 0o644)
            return dest
        dest.unlink(missing_ok=True)
    raise LookError("Could not prepare the loading picture.")


def apply_files(root, home, user, look):
    _inside(root / "usr/share/wasd/loading", look["loading"])
    _inside(root / "usr/share/wasd/login", look["login"])
    _inside(root / "usr/share/wallpapers/wasd", look["wallpaper"])
    apply_theme_files(root, home, user, look)
    apply_login(root, home, user, look["login"])
    apply_wallpaper_script(root, home, user, look["wallpaper"])
    prepare_loading(root, root / "usr/share/wasd/loading" / look["loading"])


def run_session(user, look):
    if USER_NAME.fullmatch(user) is None or user == "root":
        raise LookError("The desktop was not set.")
    subprocess.run(
        ["runuser", "-u", user, "--", "lookandfeeltool", "--apply", look["package"]],
        capture_output=True,
    )
    wall = subprocess.run(
        [
            "runuser",
            "-u",
            user,
            "--",
            "plasma-apply-wallpaperimage",
            f"/usr/share/wallpapers/wasd/{look['wallpaper']}",
        ],
        capture_output=True,
    )
    if wall.returncode != 0:
        raise LookError("The wallpaper did not change.")


def rebuild_initramfs(png):
    """Include the loading picture. Never called from a self-check or a temp root."""
    if not shutil.which("rpm-ostree"):
        return "The loading screen waits for the next system update, then a restart."
    stamp = Path("/etc/wasd/loading-rebuilt")
    digest = hashlib.sha256(png.read_bytes()).hexdigest()
    if stamp.is_file() and stamp.read_text(encoding="utf-8", errors="replace").strip() == digest:
        return ""
    command = [
        "rpm-ostree",
        "initramfs",
        "--enable",
        "--arg=-I",
        "--arg=/etc/wasd/loading-background.png",
    ]
    proc = subprocess.run(command, capture_output=True, text=True)
    output = ((proc.stdout or "") + (proc.stderr or "")).lower()
    if proc.returncode != 0 and "already enabled" in output:
        off = subprocess.run(["rpm-ostree", "initramfs", "--disable"], capture_output=True, text=True)
        proc = subprocess.run(command, capture_output=True, text=True) if off.returncode == 0 else off
    if proc.returncode != 0:
        return "The loading screen waits for the next system update, then a restart."
    stamp.write_text(digest + "\n", encoding="utf-8")
    os.chmod(stamp, 0o644)
    return ""


def apply_look(root, home, user, look, session=False, rebuild=False):
    if USER_NAME.fullmatch(user) is None or user == "root":
        raise LookError("The desktop was not set.")
    root = Path(root)
    home = Path(home)
    home.mkdir(parents=True, exist_ok=True)
    apply_files(root, home, user, look)
    if session and _live(root):
        run_session(user, look)
        # The theme tool can put its own splash and wallpaper back.
        apply_files(root, home, user, look)
    note = ""
    if rebuild and _live(root):
        note = rebuild_initramfs(root / "etc/wasd/loading-background.png")
    return note


def marker_path(root):
    override = os.environ.get("WASD_LOOK_MARK")
    if override:
        return Path(override)
    return Path(root) / "etc/wasd/look-set"


def write_marker(root):
    path = marker_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ok\n", encoding="utf-8")
    os.chmod(path, 0o644)


def home_for(root, user, home):
    if home:
        return Path(home)
    if _live(Path(root)):
        try:
            return Path(pwd.getpwnam(user).pw_dir)
        except KeyError as exc:
            raise LookError("The desktop was not set.") from exc
    return Path(root) / "home" / user


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--choices")
    parser.add_argument("--user")
    parser.add_argument("--home")
    parser.add_argument("--root", default="/")
    parser.add_argument("--session", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--no-mark", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args(argv)
    if args.self_check:
        self_check()
        return 0
    if not args.choices or not args.user:
        print("Choose the look again.", file=sys.stderr)
        return 2
    if os.environ.get("WASD_SELF_CHECK") == "1" and (args.session or args.rebuild) and args.root == "/":
        print("This computer was not changed.", file=sys.stderr)
        return 2
    try:
        data = json.loads(Path(args.choices).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise LookError("Choose the look again.")
        look = look_from(data)
        if look is None:
            return 0
        home = home_for(args.root, args.user, args.home)
        note = apply_look(
            Path(args.root),
            home,
            args.user,
            look,
            session=args.session,
            rebuild=args.rebuild,
        )
    except (OSError, json.JSONDecodeError, LookError) as exc:
        message = str(exc) if str(exc) in LOOK_MESSAGES else "The desktop was not set."
        print(message, file=sys.stderr)
        return 1
    if not args.no_mark:
        write_marker(args.root)
    if note:
        print(note, file=sys.stderr)
    return 0


def _sample_root(root, package, defaults):
    package_dir = root / "usr/share/plasma/look-and-feel" / package
    package_dir.mkdir(parents=True)
    (package_dir / "contents").mkdir()
    (package_dir / "contents/defaults").write_text(defaults, encoding="utf-8")
    for folder, name in (
        ("usr/share/wasd/loading", "stained-glass.png"),
        ("usr/share/wasd/login", "throne.png"),
        ("usr/share/wallpapers/wasd", "camp.png"),
    ):
        path = root / folder
        path.mkdir(parents=True, exist_ok=True)
        (path / name).write_bytes(b"\x89PNG\r\n\x1a\nwasd")


def self_check():
    import tempfile

    os.environ["WASD_SELF_CHECK"] = "1"
    defaults = """[kdeglobals][General]
ColorScheme=Sweet

[kdeglobals][Icons]
Theme=candy-icons

[kdeglobals][KDE]
widgetStyle=kvantum

[kwinrc][org.kde.kdecoration2]
library=org.kde.kwin.aurorae
theme=Sweet-Dark

[plasmarc][Theme]
name=Sweet

[kcminputrc][Mouse]
cursorTheme=breeze_cursors

[plasmarc][Wallpapers]
Image=file:///usr/share/wallpapers/Next/contents/images/Sweet.jpg
"""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _sample_root(root, "Sweet", defaults)
        home = root / "home/alex"
        look = look_from(
            {
                "loading": "stained-glass.png",
                "login": "throne.png",
                "theme": "Sweet KDE",
                "wallpaper": "camp.png",
            }
        )
        note = apply_look(root, home, "alex", look, session=True, rebuild=True)
        if note:
            raise SystemExit(f"a temp root tried to rebuild ({note})")
        kde = (home / ".config/kdeglobals").read_text(encoding="utf-8")
        if "ColorScheme=Sweet" not in kde or "LookAndFeelPackage=Sweet" not in kde:
            raise SystemExit("the theme was not written")
        if "widgetStyle=kvantum" not in kde or "cursorTheme" in kde:
            raise SystemExit("the theme kept a cursor or dropped the widget style")
        if "Sweet.jpg" in kde:
            raise SystemExit("the theme wallpaper was applied")
        splash = (home / ".config/ksplashrc").read_text(encoding="utf-8")
        if f"Theme={SPLASH}" not in splash:
            raise SystemExit("the session splash was replaced")
        skin = (home / ".config/Kvantum/kvantum.kvconfig").read_text(encoding="utf-8")
        if "theme=Sweet-Ambar-Blue" not in skin:
            raise SystemExit("the Kvantum skin was not the one for this theme")
        xdg = (root / "etc/xdg/kdeglobals").read_text(encoding="utf-8")
        if "LookAndFeelPackage=Sweet" not in xdg:
            raise SystemExit("the system theme was not written")
        lock = (home / ".config/kscreenlockerrc").read_text(encoding="utf-8")
        image_lines = [line for line in lock.splitlines() if line.startswith("Image=")]
        if image_lines != ["Image=file:///usr/share/wasd/login/throne.png"]:
            raise SystemExit("the lock screen picture was wrong")
        if "PreviewImage=file:///usr/share/wasd/login/throne.png" not in lock:
            raise SystemExit("the lock screen preview was wrong")
        if "WallpaperPlugin=org.kde.image" not in lock:
            raise SystemExit("the lock screen plugin was wrong")
        script = (
            home / ".local/share/plasma/shells/org.kde.plasma.desktop/contents/updates/zzz-wasd-choice.js"
        ).read_text(encoding="utf-8")
        if "camp.png" not in script or "stained-glass" in script:
            raise SystemExit("the wallpaper script was wrong")
        png = root / "etc/wasd/loading-background.png"
        if png.read_bytes() != b"\x89PNG\r\n\x1a\nwasd":
            raise SystemExit("the loading picture was not copied")
        if (root / "etc/wasd/loading-rebuilt").exists():
            raise SystemExit("a temp root rebuilt the startup picture")
        blue_dir = root / "usr/share/plasma/look-and-feel/org.magpie.exblue.desktop/contents"
        blue_dir.mkdir(parents=True)
        (blue_dir / "defaults").write_text("[kdeglobals][KDE]\nwidgetStyle=Breeze\n", encoding="utf-8")
        blue = look_from(
            {
                "loading": "stained-glass.png",
                "login": "throne.png",
                "theme": "Expose Blue",
                "wallpaper": "camp.png",
            }
        )
        apply_look(root, home, "alex", blue)
        blue_text = (home / ".config/kdeglobals").read_text(encoding="utf-8")
        if "widgetStyle=Breeze" not in blue_text:
            raise SystemExit("Expose Blue was forced onto Kvantum")
        if "LookAndFeelPackage=org.magpie.exblue.desktop" not in blue_text:
            raise SystemExit("Expose Blue was not selected")
        for bad in (
            {"loading": "..", "login": "throne.png", "theme": "Sweet KDE", "wallpaper": "camp.png"},
            {"loading": "stained-glass.png", "login": "throne.png", "theme": "No Such Theme", "wallpaper": "camp.png"},
            {"loading": "stained-glass.png"},
        ):
            try:
                look_from(bad)
            except LookError:
                pass
            else:
                raise SystemExit(f"a bad look was accepted {bad}")
        if look_from({"password": False}) is not None:
            raise SystemExit("a choice file without a look was treated as one")
    print("look self-check ok")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
