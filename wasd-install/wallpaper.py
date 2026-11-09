#!/usr/bin/env python3
"""Set the desktop wallpaper on every screen.

plasma-apply-wallpaperimage asks Plasma for desktops(). On Plasma 6.8 that
list is empty when a desktop has no activity id, which is what an update
leaves behind. The tool then exits 0 and the picture stays whatever Plasma
fell back to. desktopForScreen still finds each screen. This uses that.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

WALL = Path("/usr/share/wallpapers/wasd")
SAFE = re.compile(r"^[A-Za-z0-9._-]+$")
SENTENCE = "The wallpaper did not change."


class WallpaperError(Exception):
    pass


def picture_file(arg, root=WALL):
    if not isinstance(arg, str) or arg == "" or "\n" in arg or "\0" in arg:
        raise WallpaperError(SENTENCE)
    candidate = Path(arg)
    if not candidate.is_absolute():
        candidate = root / arg
    if candidate.parent != root or not SAFE.fullmatch(candidate.name):
        raise WallpaperError(SENTENCE)
    if candidate.is_symlink() or not candidate.is_file():
        raise WallpaperError(SENTENCE)
    resolved_root = root.resolve()
    resolved = candidate.resolve()
    if resolved.parent != resolved_root or not resolved.is_file():
        raise WallpaperError(SENTENCE)
    return resolved


def plasma_script(url):
    if not url.startswith("file:///usr/share/wallpapers/wasd/"):
        raise WallpaperError(SENTENCE)
    name = url.removeprefix("file:///usr/share/wallpapers/wasd/")
    if not SAFE.fullmatch(name):
        raise WallpaperError(SENTENCE)
    return (
        'var url = "file:///usr/share/wallpapers/wasd/' + name + '";\n'
        "var wrote = 0;\n"
        "for (var i = 0; i < screenCount; i++) {\n"
        "    var desktop = desktopForScreen(i);\n"
        "    if (!desktop)\n"
        "        continue;\n"
        '    desktop.wallpaperPlugin = "org.kde.image";\n'
        '    desktop.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];\n'
        '    desktop.writeConfig("Image", url);\n'
        "    desktop.reloadConfig();\n"
        "    wrote = wrote + 1;\n"
        "}\n"
        'print("WASD_WALLPAPER_WROTE=" + wrote);\n'
    )


def _qdbus(*args):
    return subprocess.run(
        ["qdbus-qt6", "org.kde.plasmashell", "/PlasmaShell", *args],
        capture_output=True,
        text=True,
    )


def apply_picture(path):
    url = "file:///usr/share/wallpapers/wasd/" + path.name
    script = plasma_script(url)
    if "desktops()" in script:
        raise WallpaperError(SENTENCE)
    ran = _qdbus("org.kde.PlasmaShell.evaluateScript", script)
    if ran.returncode != 0:
        raise WallpaperError(SENTENCE)
    marker = "WASD_WALLPAPER_WROTE="
    wrote = 0
    for line in (ran.stdout or "").splitlines():
        if line.startswith(marker):
            try:
                wrote = int(line[len(marker):])
            except ValueError:
                wrote = 0
    if wrote < 1:
        raise WallpaperError(SENTENCE)
    for screen in range(wrote):
        reply = _qdbus("org.kde.PlasmaShell.wallpaper", str(screen))
        if reply.returncode != 0 or url not in (reply.stdout or ""):
            raise WallpaperError(SENTENCE)
    home = Path.home()
    rc = home / ".config" / "wasd-wallpaperrc"
    try:
        rc.parent.mkdir(parents=True, exist_ok=True)
        rc.write_text(f"[Wallpaper]\nImage={url}\n", encoding="utf-8")
        os.chmod(rc, 0o644)
    except OSError:
        pass
    return wrote


def self_check():
    script = plasma_script("file:///usr/share/wallpapers/wasd/camp.png")
    if "desktopForScreen" not in script or "desktops()" in script:
        raise SystemExit("the wallpaper script still walks the empty desktop list")
    if 'print("WASD_WALLPAPER_WROTE=" + wrote);' not in script:
        raise SystemExit("the wallpaper script does not report how many screens changed")
    try:
        plasma_script("file:///tmp/camp.png")
    except WallpaperError:
        pass
    else:
        raise SystemExit("a picture outside the wallpaper folder was accepted")
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        picture = root / "camp.png"
        picture.write_bytes(b"picture")
        if picture_file("camp.png", root) != picture:
            raise SystemExit("a wallpaper in the folder was refused")
        if picture_file(str(picture), root) != picture:
            raise SystemExit("a full wallpaper path was refused")
        link = root / "link.png"
        link.symlink_to(picture)
        outside = root / "nested"
        outside.mkdir()
        (outside / "nope.png").write_bytes(b"nope")
        for bad in ("../camp.png", str(outside / "nope.png"), str(link), "camp.png/../camp.png", ""):
            try:
                picture_file(bad, root)
            except WallpaperError:
                continue
            raise SystemExit(f"a bad wallpaper path was accepted: {bad}")
    print("wallpaper self-check ok")


def main(argv):
    if argv == ["--self-check"]:
        self_check()
        return 0
    if len(argv) != 1 or argv[0] in {"-h", "--help"}:
        print(f"Usage: wasd-apply-wallpaper {WALL}/picture.jpg", file=sys.stderr)
        return 2 if argv != ["--help"] and argv != ["-h"] else 0
    try:
        apply_picture(picture_file(argv[0]))
    except WallpaperError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
