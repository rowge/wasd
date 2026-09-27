#!/usr/bin/python3
"""Point Bazzite's flatpak installer at WASD's list, and drop the Waydroid portal entry."""

from pathlib import Path
import sys

JUSTFILE = Path("/usr/share/ublue-os/just/80-bazzite.just")
YAFTI = Path("/usr/share/yafti/yafti.yml")

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
        return
    if portal.count(WAYDROID_BLOCK) != 1:
        sys.exit("Waydroid portal entry matched more than once.")
    YAFTI.write_text(portal.replace(WAYDROID_BLOCK, "", 1))


if __name__ == "__main__":
    main()
