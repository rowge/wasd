#!/bin/bash

set -ouex pipefail

cp -avf /ctx/system_files/. /

install -d /usr/share/wasd/wallpapers
install -m 0644 /ctx/wasd-wallpapers/moon2.jpg /usr/share/wasd/wallpapers/moon2.jpg
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

# Theme files are already in place. Point Plymouth at them.
# The initramfs already baked into this base image still carries Bazzite's
# splash. The live USB rebuilds the initramfs and picks this theme up then.
ln -sfn wasd/wasd.plymouth /usr/share/plymouth/themes/default.plymouth
install -d /etc/plymouth
if [[ -f /etc/plymouth/plymouthd.conf ]] && grep -q '^Theme=' /etc/plymouth/plymouthd.conf; then
    sed -i 's/^Theme=.*/Theme=wasd/' /etc/plymouth/plymouthd.conf
else
    printf '[Daemon]\nTheme=wasd\n' >>/etc/plymouth/plymouthd.conf
fi

test -s /usr/share/wasd/wallpapers/wasdsketch.png
test -s /usr/share/wasd/wallpapers/wasd-camp.png
test -s /usr/share/wasd/wasd-logo.png
test -s /usr/share/plymouth/themes/wasd/background.png
grep -q '^app/com.brave.Browser/' /usr/share/wasd/flatpaks
if grep -q 'org.mozilla.firefox' /usr/share/wasd/flatpaks /usr/share/ublue-os/bazzite/flatpak/install; then
    echo "Firefox is still in a flatpak list" >&2
    exit 1
fi
