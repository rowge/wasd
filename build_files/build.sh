#!/bin/bash

set -ouex pipefail

cp -avf /ctx/system_files/. /

install -d /usr/share/wasd/wallpapers
install -m 0644 /ctx/wasd-wallpapers/moon2.jpg /usr/share/wasd/wallpapers/moon2.jpg
install -m 0644 /ctx/wasd-wallpapers/moon2.png /usr/share/wasd/wallpapers/moon2.png
install -m 0644 /ctx/wasd-wallpapers/keysketch.jpg /usr/share/wasd/wallpapers/keysketch.jpg
install -m 0644 /ctx/wasd-wallpapers/wasdsketch.png /usr/share/wasd/wallpapers/wasdsketch.png
install -m 0644 /ctx/wasd-wallpapers/wasd-camp.png /usr/share/wasd/wallpapers/wasd-camp.png
install -m 0644 /ctx/wasd-icons/wasd-logo.png /usr/share/wasd/wasd-logo.png

# Keep shared libraries. Only the Waydroid packages themselves go.
dnf5 -y remove --setopt=clean_requirements_on_remove=False waydroid waydroid-selinux
if rpm -q waydroid >/dev/null 2>&1 || rpm -q waydroid-selinux >/dev/null 2>&1; then
    echo "waydroid is still installed" >&2
    exit 1
fi

rm -f \
    /usr/bin/waydroid-launcher \
    /etc/default/waydroid-launcher \
    /usr/share/applications/waydroid-container-restart.desktop \
    /usr/libexec/waydroid-fix-controllers \
    /usr/libexec/waydroid-container-stop \
    /usr/libexec/waydroid-container-start \
    /usr/libexec/waydroid-container-restart \
    /usr/share/polkit-1/rules.d/30-waydroid.rules \
    /usr/share/polkit-1/actions/org.bazzite.waydroid.policy \
    /usr/share/ublue-os/just/82-bazzite-waydroid.just
rm -rf /usr/share/applications/Waydroid

# The name on screen is WASD. Leave ID=bazzite so the NVIDIA and desktop
# scripts that match on it keep working. image-info.json stays as shipped
# for the same reason: its image-name still contains "nvidia".
sed -i 's/^NAME=.*/NAME="WASD"/' /usr/lib/os-release
sed -i 's/^PRETTY_NAME=.*/PRETTY_NAME="WASD"/' /usr/lib/os-release
if grep -q '^BOOTLOADER_NAME=' /usr/lib/os-release; then
    sed -i 's/^BOOTLOADER_NAME=.*/BOOTLOADER_NAME="WASD"/' /usr/lib/os-release
fi
if [[ -f /etc/system-release ]]; then
    sed -i 's/^Bazzite/WASD/' /etc/system-release
fi
grep -q '^NAME="WASD"$' /usr/lib/os-release
grep -q '^PRETTY_NAME="WASD"$' /usr/lib/os-release

# Bazzite's flatpak recipe downloads their list from GitHub on each run.
# Point it at the list in this image or Firefox comes back.
python3 /ctx/patch.py

# Theme files are already in place. The base image's initramfs still has
# Bazzite's splash baked in, so the installed system needs a new one.
# The live USB rebuilds its own initramfs later and reads this same theme.
plymouth-set-default-theme wasd
test "$(plymouth-set-default-theme)" = "wasd"

# Bazzite's menu button is these SVGs. A PNG of the same name loses to them.
rm -f \
    /usr/share/icons/hicolor/scalable/places/distributor-logo.svg \
    /usr/share/icons/hicolor/scalable/places/distributor-logo-white.svg \
    /usr/share/icons/hicolor/scalable/places/distributor-logo-steamdeck.svg \
    /usr/share/icons/hicolor/scalable/places/bazzite-logo.svg \
    /usr/share/icons/hicolor/scalable/places/bazzite-logo-white.svg \
    /usr/share/icons/hicolor/scalable/places/bazzite-logo-le.svg
shopt -s nullglob
rm -f /usr/share/icons/hicolor/*/bazzite-logo-icon.png
rm -f /usr/share/icons/hicolor/*/*/bazzite-logo-icon.png
shopt -u nullglob
if command -v gtk-update-icon-cache >/dev/null; then
    gtk-update-icon-cache -f /usr/share/icons/hicolor
elif command -v gtk4-update-icon-cache >/dev/null; then
    gtk4-update-icon-cache -f /usr/share/icons/hicolor
else
    echo "gtk-update-icon-cache is not installed" >&2
    exit 1
fi

mapfile -t kvers < <(find /usr/lib/modules -mindepth 1 -maxdepth 1 -type d -printf '%f\n')
if [[ ${#kvers[@]} -ne 1 ]]; then
    echo "expected one kernel, found: ${kvers[*]}" >&2
    exit 1
fi
kver="${kvers[0]}"
/usr/bin/dracut --no-hostonly --kver "$kver" --reproducible --zstd --add ostree --add fido2 \
    -f "/usr/lib/modules/${kver}/initramfs.img"
chmod 0600 "/usr/lib/modules/${kver}/initramfs.img"
img="/usr/lib/modules/${kver}/initramfs.img"
if ! lsinitrd "$img" | grep -q 'themes/wasd/wasd.script'; then
    echo "WASD plymouth theme missing from the image initramfs" >&2
    exit 1
fi
conf_path=$(lsinitrd "$img" | awk '/plymouthd.conf$/ { print $NF; exit }')
if [[ -z $conf_path ]] || ! lsinitrd -f "$conf_path" "$img" | grep -q '^Theme= *wasd$'; then
    echo "image initramfs is not set to the WASD plymouth theme" >&2
    lsinitrd "$img" | grep -i plymouth >&2 || true
    exit 1
fi

test -s /usr/share/wasd/wallpapers/wasdsketch.png
test -s /usr/share/wasd/wallpapers/wasd-camp.png
test -s /usr/share/wasd/wasd-logo.png
test -s /usr/share/plymouth/themes/wasd/background.png
test -s /usr/share/wasd/wallpapers/moon2.png
test -s /usr/share/icons/hicolor/48x48/apps/wasd-logo.png
test ! -e /usr/share/icons/hicolor/scalable/places/bazzite-logo.svg
grep -q '^app/com.brave.Browser/' /usr/share/wasd/flatpaks
if grep -q 'org.mozilla.firefox' /usr/share/wasd/flatpaks /usr/share/ublue-os/bazzite/flatpak/install; then
    echo "Firefox is still in a flatpak list" >&2
    exit 1
fi
