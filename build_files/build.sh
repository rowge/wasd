#!/bin/bash

set -ouex pipefail

cp -avf /ctx/system_files/. /

# /games is the mount point for a games drive. The directory has to exist
# in the image or the installed system cannot mount over it.
install -d /games

# Pacific Time, including daylight saving. The hardware clock stays UTC.
if [[ ! -f /usr/share/zoneinfo/America/Los_Angeles ]]; then
    echo "Pacific time zone data is missing" >&2
    exit 1
fi
ln -sfn ../usr/share/zoneinfo/America/Los_Angeles /etc/localtime

# The portal is Bazzite's setup window. The live desktop opens Install WASD.
rm -f \
    /etc/skel/.config/autostart/bazzite-portal.desktop \
    /etc/xdg/autostart/bazzite-portal.desktop \
    /etc/xdg/autostart/io.github.ublue_os.yafti_gtk.desktop \
    /etc/skel/Desktop/Welcome.txt \
    /home/player/Desktop/Welcome.txt \
    /var/home/player/Desktop/Welcome.txt

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
for qml in Look.qml LookPage.qml PageFooter.qml ApplyHost.qml Lister.qml AvatarProbe.qml ChosenProbe.qml; do
    install -m 0644 "/ctx/wasd-install/${qml}" "/usr/share/wasd/look/${qml}"
done
chmod 0755 /usr/bin/wasd-look /usr/bin/wasd-launchers /usr/libexec/wasd-apply-look
# Keep every other lock setting. Only the picture is set, to the login picture.
/usr/libexec/wasd-apply-look --sync-lock throne.jpg
install -d /usr/share/wasd/install
for qml in Main.qml DiskPage.qml UserPage.qml LookPage.qml AppsPage.qml SystemPage.qml PageFooter.qml Complete.qml LiveHost.qml InstallStatus.qml; do
    install -m 0644 "/ctx/wasd-install/${qml}" "/usr/share/wasd/install/${qml}"
done
install -m 0644 /ctx/wasd-install/disks.py /usr/libexec/disks.py
install -m 0755 /ctx/wasd-install/liveinfo.py /usr/libexec/wasd-live-info
install -m 0755 /ctx/wasd-install/erase.py /usr/libexec/wasd-erase
install -m 0755 /ctx/wasd-install/awake.py /usr/libexec/wasd-awake
install -m 0755 /ctx/wasd-install/gamepower.py /usr/libexec/wasd-game-power
install -m 0755 /ctx/wasd-install/set_password.py /usr/libexec/wasd-set-password
install -m 0644 /ctx/wasd-install/set_password.py /usr/libexec/set_password.py
install -m 0755 /ctx/wasd-install/wallet.py /usr/libexec/wasd-wallet
install -m 0644 /ctx/wasd-install/wallet.py /usr/libexec/wallet.py
/usr/libexec/wasd-wallet --self-check
install -m 0755 /ctx/wasd-install/network.py /usr/libexec/wasd-network
install -m 0755 /ctx/wasd-install/network.py /usr/libexec/wasd-connect-wifi
install -m 0644 /ctx/wasd-install/network.py /usr/libexec/network.py
install -m 0755 /ctx/wasd-install/apps.py /usr/libexec/wasd-install-apps
install -m 0644 /ctx/wasd-install/apps.py /usr/libexec/apps.py
install -m 0755 /ctx/wasd-install/lookapply.py /usr/libexec/lookapply.py
install -m 0755 /ctx/wasd-install/lookapply.py /usr/libexec/wasd-apply-choices
install -m 0755 /ctx/wasd-install/agents.py /usr/libexec/agents.py
install -m 0755 /ctx/wasd-install/agents.py /usr/libexec/wasd-install-agents
install -m 0755 /ctx/wasd-install/launchers.py /usr/libexec/launchers.py
install -m 0755 /ctx/wasd-install/launchers.py /usr/libexec/wasd-install-launchers
install -d /usr/share/wasd/launchers
install -m 0644 /ctx/wasd-install/Launchers.qml /usr/share/wasd/launchers/Launchers.qml
install -m 0755 /ctx/wasd-install/wasd-webapp /usr/libexec/wasd-webapp
install -m 0755 /ctx/wasd-install/windowsboot.py /usr/libexec/windowsboot.py
install -m 0755 /ctx/wasd-install/windowsboot.py /usr/libexec/wasd-windows-boot
install -m 0755 /ctx/wasd-install/boottitle.py /usr/libexec/wasd-boot-title
install -m 0644 /ctx/wasd-install/boottitle.py /usr/libexec/boottitle.py
install -d /usr/lib/systemd/system/multi-user.target.wants
install -d /usr/lib/systemd/system/ostree-finalize-staged.service.wants
ln -sfn ../wasd-windows-boot.service /usr/lib/systemd/system/multi-user.target.wants/wasd-windows-boot.service
ln -sfn ../wasd-boot-title.service /usr/lib/systemd/system/multi-user.target.wants/wasd-boot-title.service
ln -sfn ../wasd-boot-title-finalize.service /usr/lib/systemd/system/ostree-finalize-staged.service.wants/wasd-boot-title-finalize.service
install -m 0755 /ctx/wasd-install/complete.py /usr/bin/wasd-complete
chmod 0755 /usr/bin/wasd-install

# Plasma ships the Qt 6 libraries. It does not ship the qml command.
# Compile a small opener and the wallet helper, then drop the compiler and the headers.
# The wallet devel package does not ship the backend header. Download the header
# that matches the installed library, because a mismatch crashes on the first wallet.
had_qml_devel=0
had_cxx=0
had_qtbase=0
had_gpg=0
had_kwallet_devel=0
had_ssl=0
had_curl=0
rpm -q qt6-qtdeclarative-devel >/dev/null 2>&1 && had_qml_devel=1
rpm -q gcc-c++ >/dev/null 2>&1 && had_cxx=1
rpm -q qt6-qtbase-devel >/dev/null 2>&1 && had_qtbase=1
rpm -q gpgmepp-devel >/dev/null 2>&1 && had_gpg=1
rpm -q kf6-kwallet-devel >/dev/null 2>&1 && had_kwallet_devel=1
rpm -q openssl-devel >/dev/null 2>&1 && had_ssl=1
rpm -q curl >/dev/null 2>&1 && had_curl=1
dnf5 -y install --setopt=install_weak_deps=False \
    qt6-qtdeclarative-devel qt6-qtbase-devel gcc-c++ pkgconf \
    gpgmepp-devel kf6-kwallet-devel openssl-devel curl
g++ -O2 -std=c++17 -o /usr/bin/wasd-qml /ctx/wasd-qml.cpp \
    $(pkg-config --cflags --libs Qt6Gui Qt6Qml Qt6Quick)
# umu refuses to start as root. Minecraft's games folder is mounted in a
# user namespace whose root is the signed-in account, and this library
# reports that account's id so umu will start.
gcc -O2 -shared -fPIC -o /usr/libexec/wasd-noroot.so /ctx/wasd-noroot.c
test -f /usr/libexec/wasd-noroot.so
kwallet_ver=$(rpm -q --qf '%{VERSION}' kf6-kwallet)
kwallet_hdr=$(mktemp -d)
kwallet_base="https://invent.kde.org/frameworks/kwallet/-/raw/v${kwallet_ver}/src/runtime/kwalletbackend"
for name in kwalletbackend.h kwalletentry.h backendpersisthandler.h; do
    curl -fsSL -o "${kwallet_hdr}/${name}" "${kwallet_base}/${name}"
done
cat > "${kwallet_hdr}/kwalletbackend_export.h" << 'EOF'
#ifndef KWALLETBACKEND_EXPORT_H
#define KWALLETBACKEND_EXPORT_H
#define KWALLETBACKEND_EXPORT
#endif
EOF
# kf6-kwallet-devel ships CMake files, not a KF6Wallet pkg-config file.
# The backend headers include qwindowdefs.h from Qt6Gui.
g++ -O2 -std=c++17 -DHAVE_GPGMEPP -o /usr/libexec/wasd-wallet-file /ctx/wasd-wallet.cpp \
    -I"${kwallet_hdr}" \
    -I/usr/include/KF6/KWallet \
    $(pkg-config --cflags Qt6Core Qt6DBus Qt6Gui gpgmepp) \
    $(pkg-config --libs Qt6Core Qt6DBus gpgmepp) \
    -lKF6WalletBackend -lcrypto
rm -rf "${kwallet_hdr}"
wallet_home=$(mktemp -d)
chmod 700 "${wallet_home}"
env -u XDG_DATA_HOME -u DBUS_SESSION_BUS_ADDRESS -u XDG_RUNTIME_DIR HOME="${wallet_home}" \
    /usr/libexec/wasd-wallet-file self-check
rm -rf "${wallet_home}"
gpg_home=$(mktemp -d)
chmod 700 "${gpg_home}"
cat > "${gpg_home}/batch" << 'EOF'
%no-protection
Key-Type: eddsa
Key-Curve: ed25519
Key-Usage: sign
Subkey-Type: ecdh
Subkey-Curve: cv25519
Subkey-Usage: encrypt
Name-Real: WASD
Name-Comment: wasd-wallet
Expire-Date: 0
%commit
EOF
chmod 600 "${gpg_home}/batch"
gpg --homedir "${gpg_home}" --batch --pinentry-mode loopback --generate-key "${gpg_home}/batch"
wallet_fpr=$(gpg --homedir "${gpg_home}" --batch --with-colons --list-secret-keys | awk -F: '$1=="fpr" {print $10; exit}')
gpg_wallet=$(mktemp -d)
chmod 700 "${gpg_wallet}"
env -u XDG_DATA_HOME -u DBUS_SESSION_BUS_ADDRESS -u XDG_RUNTIME_DIR \
    HOME="${gpg_wallet}" GNUPGHOME="${gpg_home}" \
    /usr/libexec/wasd-wallet-file create-gpg "${wallet_fpr}"
gpg_kind=$(env -u XDG_DATA_HOME -u DBUS_SESSION_BUS_ADDRESS -u XDG_RUNTIME_DIR \
    HOME="${gpg_wallet}" GNUPGHOME="${gpg_home}" \
    /usr/libexec/wasd-wallet-file kind)
case "${gpg_kind}" in
    gpg\ *) ;;
    *)
        echo "the wallet helper did not write a GPG wallet" >&2
        exit 1
        ;;
esac
rm -rf "${gpg_home}" "${gpg_wallet}"
if [[ $had_qml_devel -eq 0 ]] && rpm -q qt6-qtdeclarative-devel >/dev/null 2>&1; then
    dnf5 -y remove --setopt=clean_requirements_on_remove=True qt6-qtdeclarative-devel
fi
if [[ $had_qtbase -eq 0 ]] && rpm -q qt6-qtbase-devel >/dev/null 2>&1; then
    dnf5 -y remove --setopt=clean_requirements_on_remove=True qt6-qtbase-devel
fi
if [[ $had_gpg -eq 0 ]] && rpm -q gpgmepp-devel >/dev/null 2>&1; then
    dnf5 -y remove --setopt=clean_requirements_on_remove=True gpgmepp-devel
fi
if [[ $had_kwallet_devel -eq 0 ]] && rpm -q kf6-kwallet-devel >/dev/null 2>&1; then
    dnf5 -y remove --setopt=clean_requirements_on_remove=True kf6-kwallet-devel
fi
if [[ $had_ssl -eq 0 ]] && rpm -q openssl-devel >/dev/null 2>&1; then
    dnf5 -y remove --setopt=clean_requirements_on_remove=True openssl-devel
fi
if [[ $had_curl -eq 0 ]] && rpm -q curl >/dev/null 2>&1; then
    dnf5 -y remove --setopt=clean_requirements_on_remove=True curl
fi
if [[ $had_cxx -eq 0 ]] && rpm -q gcc-c++ >/dev/null 2>&1; then
    dnf5 -y remove --setopt=clean_requirements_on_remove=True gcc-c++
fi
rpm -q qt6-qtdeclarative
test -x /usr/bin/wasd-qml
# grep -q stops at the first hit. The writer then dies with SIGPIPE, and
# pipefail fails the build. Read the whole listing.
ldd /usr/bin/wasd-qml | grep 'libQt6Qml.so' >/dev/null

# Keep shared libraries. Only the Waydroid packages themselves go.
# The NVIDIA image ships waydroid-nvidia, which provides waydroid.
# Removing the name waydroid leaves that package and its menu entry.
waydroid_pkgs=()
for name in waydroid waydroid-selinux waydroid-nvidia waydroid-nvidia-selinux; do
    if rpm -q "$name" >/dev/null 2>&1; then
        waydroid_pkgs+=("$name")
    fi
done
if ((${#waydroid_pkgs[@]})); then
    dnf5 -y remove --setopt=clean_requirements_on_remove=False "${waydroid_pkgs[@]}"
fi
if rpm -q waydroid >/dev/null 2>&1 \
    || rpm -q waydroid-selinux >/dev/null 2>&1 \
    || rpm -q waydroid-nvidia >/dev/null 2>&1 \
    || rpm -q waydroid-nvidia-selinux >/dev/null 2>&1 \
    || rpm -q --whatprovides waydroid >/dev/null 2>&1 \
    || [[ -e /usr/bin/waydroid || -e /usr/share/applications/Waydroid.desktop ]]; then
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

# The text login runs ublue-motd, which prints this file. PRETTY_NAME does not.
grep -q '^# Welcome to WASD$' /usr/share/ublue-os/motd/template.md
grep -q '^Based on Bazzite\.$' /usr/share/ublue-os/motd/template.md
grep -q '^# Välkommen till WASD$' /usr/share/ublue-os/motd/template.sv.md
grep -q '^Baserat på Bazzite\.$' /usr/share/ublue-os/motd/template.sv.md
if grep -q -e 'Welcome to Bazzite' -e 'Välkommen till Bazzite' \
    /usr/share/ublue-os/motd/template.md /usr/share/ublue-os/motd/template.sv.md; then
    echo "the login banner still welcomes them to Bazzite" >&2
    exit 1
fi

# Bazzite's flatpak recipe downloads their list from GitHub on each run.
# Point it at the list in this image or Firefox comes back.
python3 /ctx/patch.py
if grep -q 'id: "waydroid"' /usr/share/yafti/yafti.yml \
    || grep -q "id: 'waydroid'" /usr/share/yafti/yafti.yml; then
    echo "the portal still offers Waydroid" >&2
    exit 1
fi

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

# Store themes use the Kvantum style. Install them after the splash rewrite
# so their own splash files are not mistaken for Bazzite's. The default is
# We10XOS-dark, and that package's splash is removed so the session keeps the W.
dnf5 -y install --setopt=install_weak_deps=False kvantum
rpm -q kvantum
# Same SIGPIPE rule as the initramfs check below.
rpm -ql kvantum | grep 'kvantum.so' >/dev/null
python3 /ctx/install-themes.py
test -d /usr/share/icons/oxygen

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
test -s /usr/share/wasd/login/throne.jpg
grep -q '^Image=file:///usr/share/wasd/login/throne.jpg$' /etc/xdg/kscreenlockerrc
grep -q '^PreviewImage=file:///usr/share/wasd/login/throne.jpg$' /etc/xdg/kscreenlockerrc
grep -q '^WallpaperPlugin=org.kde.image$' /etc/xdg/kscreenlockerrc
grep -q '^Image=file:///usr/share/wasd/login/throne.jpg$' /etc/skel/.config/kscreenlockerrc
test -d /games
test ! -e /etc/skel/Desktop/Welcome.txt
test ! -e /home/player/Desktop/Welcome.txt
test ! -e /var/home/player/Desktop/Welcome.txt
test ! -e /etc/skel/.config/autostart/bazzite-portal.desktop
test -s /usr/share/wasd/icons/wasd-logo.png
test -s /usr/share/wasd/look/Look.qml
test -s /usr/share/wasd/look/ApplyHost.qml
test -s /usr/share/wasd/look/AvatarProbe.qml
test -s /usr/share/wasd/look/ChosenProbe.qml
test -x /usr/bin/wasd-look
test -x /usr/libexec/wasd-apply-look
test -s /usr/share/applications/wasd-look.desktop
test -s /usr/share/wasd/launchers/Launchers.qml
test -x /usr/bin/wasd-launchers
test -s /usr/share/applications/wasd-launchers.desktop
test -s /usr/libexec/launchers.py
test -s /usr/share/polkit-1/actions/org.wasd.look.policy
test -s /usr/share/wasd/install/Main.qml
test -s /usr/share/wasd/install/Complete.qml
test -s /usr/share/wasd/install/UserPage.qml
test -s /usr/share/wasd/install/LiveHost.qml
test -x /usr/bin/wasd-install
test -x /usr/bin/wasd-qml
test -x /usr/bin/wasd-complete
test -x /usr/libexec/wasd-erase
if grep -F 'ostree/0/1/0' /usr/libexec/wasd-erase >/dev/null; then
    echo "the installer still asks for a fixed deployment name" >&2
    exit 1
fi
test -s /usr/share/polkit-1/actions/org.wasd.erase.policy
grep -F '/usr/libexec/wasd-erase' /usr/share/polkit-1/actions/org.wasd.erase.policy >/dev/null
grep -F '<allow_active>yes</allow_active>' /usr/share/polkit-1/actions/org.wasd.erase.policy >/dev/null
grep -F -- '--install' /usr/share/polkit-1/actions/org.wasd.erase.policy >/dev/null
test -x /usr/libexec/wasd-live-info
test -x /usr/libexec/wasd-set-password
test -s /usr/libexec/set_password.py
test -x /usr/libexec/wasd-network
test -x /usr/libexec/wasd-connect-wifi
test -s /usr/libexec/network.py
test -x /usr/libexec/wasd-install-apps
test -s /usr/libexec/apps.py
test -x /usr/libexec/wasd-apply-choices
test -s /usr/libexec/lookapply.py
test -x /usr/libexec/wasd-install-agents
test -s /usr/libexec/agents.py
test -x /usr/libexec/wasd-webapp
test -x /usr/libexec/wasd-windows-boot
test -s /usr/lib/systemd/system/wasd-windows-boot.service
test -L /usr/lib/systemd/system/multi-user.target.wants/wasd-windows-boot.service
test -x /usr/libexec/wasd-boot-title
test -s /usr/libexec/boottitle.py
test -s /usr/lib/systemd/system/wasd-boot-title.service
test -s /usr/lib/systemd/system/wasd-boot-title-finalize.service
test -L /usr/lib/systemd/system/multi-user.target.wants/wasd-boot-title.service
test -L /usr/lib/systemd/system/ostree-finalize-staged.service.wants/wasd-boot-title-finalize.service
test -s /usr/share/wasd/install/SystemPage.qml
test -s /usr/share/polkit-1/actions/org.wasd.password.policy
test -s /usr/share/polkit-1/actions/org.wasd.wifi.policy
test -s /usr/share/polkit-1/actions/org.wasd.apps.policy
grep -q '/usr/libexec/wasd-install-apps' /usr/share/polkit-1/actions/org.wasd.apps.policy
test -s /usr/share/polkit-1/actions/org.wasd.choices.policy
test -s /usr/share/polkit-1/actions/org.wasd.agents.policy
grep -q '/usr/libexec/wasd-apply-choices' /usr/share/polkit-1/actions/org.wasd.choices.policy
grep -q '/usr/libexec/wasd-install-agents' /usr/share/polkit-1/actions/org.wasd.agents.policy
test ! -e /usr/share/icons/hicolor/scalable/places/bazzite-logo.svg
vapor_splash=/usr/share/plasma/look-and-feel/com.valve.vapor.desktop/contents/splash
grep -q 'images/wasd_logo.png' "${vapor_splash}/Splash.qml"
test -s "${vapor_splash}/images/wasd_logo.png"
if grep -q 'images/bazzite_logo.svgz' /usr/share/plasma/look-and-feel/*/contents/splash/Splash.qml; then
    echo "a Plasma splash still shows the Bazzite logo" >&2
    exit 1
fi
grep -q '^app/com.brave.Browser/x86_64/stable$' /usr/share/wasd/flatpaks
grep -q '^com.brave.Browser$' /usr/share/ublue-os/bazzite/flatpak/install
grep -q '^runtime/org.freedesktop.Platform.VulkanLayer.MangoHud/x86_64/25.08$' /usr/share/wasd/flatpaks
grep -q '^runtime/org.freedesktop.Platform.VulkanLayer.vkBasalt/x86_64/25.08$' /usr/share/wasd/flatpaks
grep -q '^org.freedesktop.Platform.VulkanLayer.MangoHud//25.08$' /usr/share/ublue-os/bazzite/flatpak/install
grep -q '^org.freedesktop.Platform.VulkanLayer.vkBasalt//25.08$' /usr/share/ublue-os/bazzite/flatpak/install
grep -q '^x-scheme-handler/http=com.brave.Browser.desktop$' /etc/xdg/mimeapps.list
grep -q '^x-scheme-handler/https=com.brave.Browser.desktop$' /etc/xdg/mimeapps.list
grep -q '^text/html=com.brave.Browser.desktop$' /etc/xdg/mimeapps.list
grep -q 'https://wasd.run' /etc/brave/policies/recommended/homepage.json
grep -q '"HomepageLocation"' /etc/brave/policies/recommended/homepage.json
grep -q '"RestoreOnStartup"' /etc/brave/policies/recommended/homepage.json
if grep -R -E 'HomepageLocation|RestoreOnStartup' /etc/brave/policies/managed >/dev/null; then
    echo "Brave homepage is locked" >&2
    exit 1
fi
grep -q '"PromotionalTabsEnabled": false' /etc/brave/policies/managed/promotions.json
test ! -e /etc/brave/policies/managed/homepage.json
grep -q -- '--password-store=basic' /etc/skel/.var/app/com.brave.Browser/config/brave-flags.conf
grep -q '^no-allow-external-cache$' /etc/gnupg/gpg-agent.conf
test -x /usr/libexec/wasd-wallet
test -s /usr/libexec/wallet.py
test -x /usr/libexec/wasd-wallet-file
command -v gpg >/dev/null
command -v gpgconf >/dev/null
wallet_ldd=$(ldd /usr/libexec/wasd-wallet-file)
if [[ "$wallet_ldd" != *libKF6WalletBackend.so.6* ]]; then
    echo "the wallet helper is not linked to the wallet library" >&2
    exit 1
fi
grep -q '/var/mnt:ro' /etc/flatpak/overrides/com.brave.Browser
grep -q 'xdg-pictures:ro' /etc/flatpak/overrides/com.brave.Browser
grep -q '^First Use=false$' /etc/xdg/kwalletrc
test ! -e /etc/skel/.ssh/authorized_keys
test ! -e /etc/ssh/sshd_config.d/50-wasd-test.conf
test ! -e /usr/lib/systemd/system/multi-user.target.wants/sshd.service
test "$(readlink /etc/localtime)" = "../usr/share/zoneinfo/America/Los_Angeles"
# Plasma's digital clock follows LC_TIME and has no 12/24 switch.
# C.UTF-8 is 24-hour. en_US is 12-hour. LANG stays C.
grep -q '^LANG="C.UTF-8"$' /etc/locale.conf
grep -q '^LC_TIME="en_US.UTF-8"$' /etc/locale.conf
grep -q '^LC_TIME=en_US.UTF-8$' /etc/xdg/plasma-localerc
grep -q '^LANG=C.UTF-8$' /etc/skel/.config/plasma-localerc
grep -q '^LC_TIME=en_US.UTF-8$' /etc/skel/.config/plasma-localerc
# Plugged in: the screen turns off after 5 minutes and the machine stays awake.
# AutoSuspendAction 0 is PowerDevil's NoAction. Battery profiles are untouched.
grep -q '^TurnOffDisplayWhenIdle=true$' /etc/xdg/powerdevilrc
grep -q '^TurnOffDisplayIdleTimeoutSec=300$' /etc/xdg/powerdevilrc
grep -q '^AutoSuspendAction=0$' /etc/xdg/powerdevilrc
if ! locale -a | grep -Eiq '^en_US\.(utf8|utf-8)$'; then
    echo "en_US.UTF-8 locale is not installed" >&2
    exit 1
fi
python3 - << 'PY'
import locale
locale.setlocale(locale.LC_TIME, "en_US.UTF-8")
fmt = locale.nl_langinfo(locale.T_FMT)
if fmt != "%r":
    raise SystemExit(f"en_US time format is {fmt}, expected %r")
PY
for gone in \
    app/com.discordapp.Discord/ \
    app/im.riot.Riot/ \
    app/com.heroicgameslauncher.hgl/ \
    app/com.usebottles.bottles/ \
    app/com.obsproject.Studio/ \
    app/io.github.benjamimgois.goverlay/ \
    app/com.github.wwmm.easyeffects/ \
    app/org.freedesktop.Piper/ \
    app/org.openrgb.OpenRGB/ \
    app/io.github.ilya_zlobintsev.LACT/ \
    app/org.kde.gwenview/ \
    app/org.kde.okular/ \
    app/org.kde.kcalc/ \
    app/org.kde.haruna/ \
    app/io.github.DenysMb.Kontainer/ \
    app/com.github.tchx84.Flatseal/ \
    app/com.github.Matoking.protontricks/ \
    app/io.github.flattool.Warehouse/ \
    app/com.vysp3r.ProtonPlus/ \
    app/org.gnome.Firmware/ \
    runtime/com.obsproject.Studio.Plugin.OBSVkCapture/ \
    runtime/com.obsproject.Studio.Plugin.Gstreamer/ \
    runtime/com.obsproject.Studio.Plugin.GStreamerVaapi/ \
    runtime/org.freedesktop.Platform.VulkanLayer.OBSVkCapture/
do
    if grep -q "^${gone}" /usr/share/wasd/flatpaks; then
        echo "flatpak list still has ${gone}" >&2
        exit 1
    fi
done
for gone in \
    com.discordapp.Discord \
    im.riot.Riot \
    com.heroicgameslauncher.hgl \
    com.usebottles.bottles \
    com.obsproject.Studio \
    io.github.benjamimgois.goverlay \
    com.github.wwmm.easyeffects \
    org.freedesktop.Piper \
    org.openrgb.OpenRGB \
    io.github.ilya_zlobintsev.LACT \
    org.kde.gwenview \
    org.kde.okular \
    org.kde.kcalc \
    org.kde.haruna \
    io.github.DenysMb.Kontainer \
    com.github.tchx84.Flatseal \
    com.github.Matoking.protontricks \
    io.github.flattool.Warehouse \
    com.vysp3r.ProtonPlus \
    org.gnome.Firmware \
    com.obsproject.Studio.Plugin.OBSVkCapture \
    com.obsproject.Studio.Plugin.Gstreamer \
    com.obsproject.Studio.Plugin.GStreamerVaapi \
    org.freedesktop.Platform.VulkanLayer.OBSVkCapture//25.08
do
    if grep -qx "${gone}" /usr/share/ublue-os/bazzite/flatpak/install; then
        echo "flatpak install list still has ${gone}" >&2
        exit 1
    fi
done
if grep -q 'org.mozilla.firefox' /usr/share/wasd/flatpaks /usr/share/ublue-os/bazzite/flatpak/install; then
    echo "Firefox is still in a flatpak list" >&2
    exit 1
fi
