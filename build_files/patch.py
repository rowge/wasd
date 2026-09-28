#!/usr/bin/python3
"""Point Bazzite's flatpak installer at WASD's list, and put WASD on the portal."""

from pathlib import Path
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

WAYDROID_BLOCK = """      - id: "waydroid"
        title: "Waydroid"
        description: "Android system in a container, for app compatibility on Linux. Incompatible with NVIDIA drivers."
        default: false
        options:
          - id: "init"
            label: "Initialize"
            script: "ujust configure-waydroid init"
          - id: "configure"
            label: "Configure"
            script: "ujust configure-waydroid configure"
          - id: "gpu"
            label: "Select GPU"
            script: "ujust configure-waydroid gpu"
          - id: "reset"
            label: "Reset"
            script: "ujust configure-waydroid reset"
          - id: "helper"
            label: "Install Helper"
            script: "ujust configure-waydroid helper"
"""


def replace_once(text: str, old: str, new: str, label: str) -> str:
    found = text.count(old)
    if found != 1:
        sys.exit(f"{label} matched {old!r} {found} times. Refusing to guess.")
    return text.replace(old, new, 1)


def find_yafti_program() -> Path:
    for candidate in (
        Path("/usr/bin/yafti_gtk.py"),
        Path("/usr/libexec/yafti_gtk.py"),
        Path("/usr/share/yafti/yafti_gtk.py"),
    ):
        if candidate.is_file():
            return candidate
    sys.exit("yafti_gtk.py is not installed. The portal title cannot be changed.")


def rebrand_portal_program(path: Path) -> None:
    # The window title is a constant in the program. The yml title is not what GTK shows.
    text = path.read_text()
    text = replace_once(text, "APP_TITLE = 'Bazzite Portal'", "APP_TITLE = 'WASD Portal'", path.name)
    text = replace_once(text, "Name=Bazzite Portal", "Name=WASD Portal", path.name)
    text = replace_once(text, "Comment=Helps you setup Bazzite", "Comment=Helps you set up WASD", path.name)
    text = replace_once(text, 'description="Bazzite Portal"', 'description="WASD Portal"', path.name)
    path.write_text(text)


def rebrand_portal_config(text: str) -> str:
    # Visible copy uses "Bazzite". Commands and URLs stay lowercase, so they still run.
    found = text.count("Bazzite")
    if found < 1:
        sys.exit("Portal config no longer says Bazzite. Refusing to guess.")
    return text.replace("Bazzite", "WASD")


def rebrand_desktop_files() -> int:
    changed = 0
    for root in DESKTOP_ROOTS:
        if not root.is_dir():
            continue
        for desktop in root.rglob("*.desktop"):
            text = desktop.read_text()
            if "yafti_gtk.py" not in text and "Bazzite Portal" not in text:
                continue
            new = text.replace("Bazzite Portal", "WASD Portal").replace(
                "Helps you setup Bazzite", "Helps you set up WASD"
            )
            if new != text:
                desktop.write_text(new)
                changed += 1
    return changed


def main() -> None:
    text = JUSTFILE.read_text()
    if CURL_LINE not in text:
        sys.exit("Bazzite flatpak recipe no longer curls GitHub. Refusing to guess.")
    if text.count(CURL_LINE) != 1:
        sys.exit("Bazzite flatpak curl line matched more than once.")
    JUSTFILE.write_text(text.replace(CURL_LINE, LOCAL_LINE, 1))

    portal = YAFTI.read_text()
    if WAYDROID_BLOCK not in portal:
        print("Waydroid portal entry not found. Packages are still removed.", file=sys.stderr)
    elif portal.count(WAYDROID_BLOCK) != 1:
        sys.exit("Waydroid portal entry matched more than once.")
    else:
        portal = portal.replace(WAYDROID_BLOCK, "", 1)
    portal = rebrand_portal_config(portal)
    if "Bazzite" in portal:
        sys.exit("Portal config still says Bazzite.")
    YAFTI.write_text(portal)

    rebrand_portal_program(find_yafti_program())
    if rebrand_desktop_files() < 1:
        sys.exit("No portal desktop file was renamed.")


if __name__ == "__main__":
    main()
