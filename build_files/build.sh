#!/bin/bash

set -ouex pipefail

cp -avf /ctx/system_files/. /

# Plasma's wallpaper gallery scans /usr/share/wallpapers, including folders
# under it. Symlinks are ignored, so these are real copies. Every image in
# wasd-wallpapers/ shows up as a choice. The default desktop is set elsewhere.
install -d /usr/share/wallpapers/wasd
shopt -s nullglob
wallpaper_count=0
for src in /ctx/wasd-wallpapers/*; do
    [[ -f $src ]] || continue
    case ${src##*.} in
        jpg | jpeg | png | webp | JPG | JPEG | PNG | WEBP) ;;
        *)
            echo "skipping non-image in wasd-wallpapers: ${src##*/}" >&2
            continue
            ;;
    esac
    install -m 0644 "$src" "/usr/share/wallpapers/wasd/${src##*/}"
    wallpaper_count=$((wallpaper_count + 1))
done
shopt -u nullglob
if [[ $wallpaper_count -lt 1 ]]; then
    echo "no wallpapers installed from wasd-wallpapers" >&2
    exit 1
fi
install -m 0644 /ctx/wasd-icons/wasd-logo.png /usr/share/wasd/wasd-logo.png

# WASD Look reads these folders after install. Plasma ignores wallpaper
# symlinks, so the copies are real files, same as the gallery above.
copy_wasd_images() {
    local src_dir=$1 dest=$2 label=$3
    local src count=0
    install -d "$dest"
    shopt -s nullglob
    for src in "$src_dir"/*; do
        [[ -f $src ]] || continue
        case ${src##*.} in
            jpg | jpeg | png | webp | JPG | JPEG | PNG | WEBP) ;;
            *)
                echo "skipping non-image in ${label}: ${src##*/}" >&2
                continue
                ;;
        esac
        install -m 0644 "$src" "${dest}/${src##*/}"
        count=$((count + 1))
    done
    shopt -u nullglob
    if [[ $count -lt 1 ]]; then
        echo "no images installed from ${label}" >&2
        exit 1
    fi
}
copy_wasd_images /ctx/wasd-loading-screens /usr/share/wasd/loading wasd-loading-screens
copy_wasd_images /ctx/wasd-login-screens /usr/share/wasd/login wasd-login-screens
copy_wasd_images /ctx/wasd-icons /usr/share/wasd/icons wasd-icons
install -d /usr/share/wasd/look
for qml in Look.qml LookPage.qml PageFooter.qml ApplyHost.qml Lister.qml; do
    install -m 0644 "/ctx/wasd-install/${qml}" "/usr/share/wasd/look/${qml}"
done
chmod 0755 /usr/bin/wasd-look /usr/libexec/wasd-apply-look

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

# The name on screen is WASD. Leave ID=bazzite so Bazzite's own scripts keep
# matching. image-info.json stays as the base image shipped it, so the NVIDIA
# build still says nvidia and the AMD build does not.
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
# Bazzite ships the spinner plugin only. The key-sketch splash is a script theme.
dnf5 -y install --setopt=install_weak_deps=False plymouth-plugin-script
test -e /usr/lib64/plymouth/script.so
plymouth-set-default-theme wasd
test "$(plymouth-set-default-theme)" = "wasd"

# Plymouth quits when the bar hits the end. Plasma then paints its own
# splash, a black screen with Bazzite's logo in the middle, while the
# session starts. The live desktop and the installed one both use it.
shopt -s nullglob
splash_qmls=(/usr/share/plasma/look-and-feel/*/contents/splash/Splash.qml)
shopt -u nullglob
replaced=0
for qml in "${splash_qmls[@]}"; do
    if ! grep -q 'images/bazzite_logo.svgz' "$qml"; then
        continue
    fi
    images="${qml%/Splash.qml}/images"
    install -d "$images"
    install -m 0644 /ctx/wasd-icons/wasd-logo.png "${images}/wasd_logo.png"
    sed -i 's|images/bazzite_logo.svgz|images/wasd_logo.png|' "$qml"
    # Bazzite's glyph is drawn at gridUnit * 8. The slab W needs more
    # pixels than that or the stacks blur into a blob.
    if grep -q 'gridUnit \* 8' "$qml"; then
        sed -i 's|gridUnit \* 8|gridUnit * 16|' "$qml"
    fi
    if grep -q 'images/bazzite_logo.svgz' "$qml"; then
        echo "Bazzite logo still referenced in $qml" >&2
        exit 1
    fi
    grep -q 'images/wasd_logo.png' "$qml"
    test -s "${images}/wasd_logo.png"
    replaced=$((replaced + 1))
done
if [[ $replaced -lt 1 ]]; then
    echo "did not find the Plasma splash that shows the Bazzite logo" >&2
    exit 1
fi

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
if ! lsinitrd -f usr/share/plymouth/themes/wasd/wasd.script "$img" >/dev/null \
    && ! lsinitrd -f /usr/share/plymouth/themes/wasd/wasd.script "$img" >/dev/null; then
    echo "WASD plymouth theme missing from the image initramfs" >&2
    lsinitrd "$img" | grep -i plymouth >&2 || true
    exit 1
fi
# awk must read the whole listing. Exiting early closes the pipe and
# lsinitrd dies with SIGPIPE, which fails the build under pipefail.
conf_path=$(lsinitrd "$img" | awk '/plymouthd.conf$/ { path = $NF } END { print path }')
theme_line=$(lsinitrd -f "$conf_path" "$img" | awk '/^Theme=/ { line = $0 } END { print line }')
if [[ -z $conf_path || $theme_line != Theme=wasd && $theme_line != "Theme= wasd" ]]; then
    echo "image initramfs is not set to the WASD plymouth theme" >&2
    lsinitrd "$img" | grep -i plymouth >&2 || true
    exit 1
fi

test -s /usr/share/wallpapers/wasd/stained-glass.jpg
test -s /usr/share/wallpapers/wasd/wasdsketch.png
test -s /usr/share/wallpapers/wasd/camp.png
test -s /usr/share/wallpapers/wasd/keysketch.jpg
test -s /usr/share/wasd/wasd-logo.png
test -s /usr/share/plymouth/themes/wasd/background.png
test -s /usr/share/icons/hicolor/48x48/apps/wasd-logo.png
test -s /usr/share/wasd/loading/stained-glass.jpg
test -s /usr/share/wasd/loading/keysketch.jpg
test -s /usr/share/wasd/login/camp.png
test -s /usr/share/wasd/login/camp.png
test -s /usr/share/wasd/icons/wasd-logo.png
test -s /usr/share/wasd/look/Look.qml
test -s /usr/share/wasd/look/ApplyHost.qml
test -x /usr/bin/wasd-look
test -x /usr/libexec/wasd-apply-look
test -s /usr/share/applications/wasd-look.desktop
test -s /usr/share/polkit-1/actions/org.wasd.look.policy
test ! -e /usr/share/icons/hicolor/scalable/places/bazzite-logo.svg
vapor_splash=/usr/share/plasma/look-and-feel/com.valve.vapor.desktop/contents/splash
grep -q 'images/wasd_logo.png' "${vapor_splash}/Splash.qml"
test -s "${vapor_splash}/images/wasd_logo.png"
if grep -q 'images/bazzite_logo.svgz' /usr/share/plasma/look-and-feel/*/contents/splash/Splash.qml; then
    echo "a Plasma splash still shows the Bazzite logo" >&2
    exit 1
fi
grep -q '^app/com.brave.Browser/' /usr/share/wasd/flatpaks
for app in \
    app/com.discordapp.Discord/ \
    app/im.riot.Riot/ \
    app/com.heroicgameslauncher.hgl/ \
    app/com.usebottles.bottles/ \
    app/com.obsproject.Studio/ \
    app/io.github.benjamimgois.goverlay/ \
    app/com.github.wwmm.easyeffects/ \
    app/org.freedesktop.Piper/ \
    app/org.openrgb.OpenRGB/ \
    app/io.github.ilya_zlobintsev.LACT/
do
    grep -q "^${app}" /usr/share/wasd/flatpaks
    grep -q "^${app}" /usr/share/ublue-os/bazzite/flatpak/install || {
        # The install list uses the short id, app/id/arch/branch.
        short=${app#app/}
        short=${short%/}
        grep -q "^${short}$" /usr/share/ublue-os/bazzite/flatpak/install
    }
done
if grep -q 'org.mozilla.firefox' /usr/share/wasd/flatpaks /usr/share/ublue-os/bazzite/flatpak/install; then
    echo "Firefox is still in a flatpak list" >&2
    exit 1
fi
