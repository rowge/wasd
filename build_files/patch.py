#!/usr/bin/python3
"""Point Bazzite's flatpak installer at WASD's list. Leave the Bazzite Portal as Bazzite."""

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
    if "WASD" in portal:
        sys.exit("Portal config says WASD. The portal stays Bazzite's.")
    if "Bazzite" not in portal:
        sys.exit("Portal config no longer says Bazzite. Refusing to guess.")
    YAFTI.write_text(portal)
    require_bazzite_portal()


if __name__ == "__main__":
    main()
