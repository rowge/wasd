#!/usr/bin/python3
"""Point Bazzite's flatpak installer at WASD's list. Leave the Bazzite Portal as Bazzite."""

from pathlib import Path
import re
import sys

JUSTFILE = Path("/usr/share/ublue-os/just/80-bazzite.just")
YAFTI = Path("/usr/share/yafti/yafti.yml")
DESKTOP_ROOTS = (
    Path("/usr/share/applications"),
    Path("/etc/xdg/autostart"),
    Path("/etc/skel/.config/autostart"),
)

CURL_LINE = (
    'FLATPAK_LIST="$(curl https://raw.githubusercontent.com/ublue-os/bazzite/main/installer/${FLATPAKS} '
    "| tr '\\n' ' ')\""
)
LOCAL_LINE = "FLATPAK_LIST=\"$(tr '\\n' ' ' < /usr/share/wasd/flatpaks)\""

WAYDROID_ID = re.compile(r"""^- id: ["']waydroid["']\s*$""")


def find_yafti_program() -> Path:
    for candidate in (
        Path("/usr/bin/yafti_gtk.py"),
        Path("/usr/libexec/yafti_gtk.py"),
        Path("/usr/share/yafti/yafti_gtk.py"),
    ):
        if candidate.is_file():
            return candidate
    sys.exit("yafti_gtk.py is not installed.")


def require_bazzite_portal() -> None:
    # This window is Bazzite's. Its title, its docs, and its Discord stay theirs.
    program = find_yafti_program()
    text = program.read_text()
    if "APP_TITLE = 'Bazzite Portal'" not in text:
        sys.exit(f"{program} is not titled Bazzite Portal.")
    if "WASD" in text:
        sys.exit(f"{program} says WASD. The portal stays Bazzite's.")
    found = 0
    for root in DESKTOP_ROOTS:
        if not root.is_dir():
            continue
        for desktop in root.rglob("*.desktop"):
            body = desktop.read_text()
            if "yafti_gtk.py" not in body and "Bazzite Portal" not in body and "WASD Portal" not in body:
                continue
            if "WASD" in body:
                sys.exit(f"{desktop} says WASD. The portal stays Bazzite's.")
            if "Bazzite Portal" not in body:
                sys.exit(f"{desktop} is a portal entry without the Bazzite Portal name.")
            found += 1
    if found < 1:
        sys.exit("No Bazzite Portal desktop file was found.")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def remove_waydroid_entry(text: str) -> str:
    """Drop the portal list item whose id is waydroid.

    The description text changes between images, so the id is the marker.
    A missing entry is left alone. Two entries stop the build.
    """
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if WAYDROID_ID.match(line.strip())]
    if len(starts) > 1:
        sys.exit("Waydroid portal entry matched more than once.")
    if not starts:
        print("Waydroid portal entry not found. Packages are still removed.", file=sys.stderr)
        return text
    start = starts[0]
    item_indent = _indent(lines[start])
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() == "":
            look = end + 1
            while look < len(lines) and lines[look].strip() == "":
                look += 1
            if look == len(lines) or _indent(lines[look]) <= item_indent:
                break
            end = look
            continue
        if _indent(line) <= item_indent:
            break
        end += 1
    del lines[start:end]
    result = "".join(lines)
    if any(WAYDROID_ID.match(line.strip()) for line in result.splitlines()):
        sys.exit("Waydroid portal entry is still present.")
    return result


def main() -> None:
    text = JUSTFILE.read_text()
    if CURL_LINE not in text:
        sys.exit("Bazzite flatpak recipe no longer curls GitHub. Refusing to guess.")
    if text.count(CURL_LINE) != 1:
        sys.exit("Bazzite flatpak curl line matched more than once.")
    JUSTFILE.write_text(text.replace(CURL_LINE, LOCAL_LINE, 1))

    portal = remove_waydroid_entry(YAFTI.read_text())
    if "WASD" in portal:
        sys.exit("Portal config says WASD. The portal stays Bazzite's.")
    if "Bazzite" not in portal:
        sys.exit("Portal config no longer says Bazzite. Refusing to guess.")
    YAFTI.write_text(portal)
    require_bazzite_portal()


if __name__ == "__main__":
    main()
