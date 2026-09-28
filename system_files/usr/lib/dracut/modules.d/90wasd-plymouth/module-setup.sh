#!/bin/bash
# Plymouth's generic (--no-hostonly) initramfs keeps its own spinner and
# does not pick up a theme added later. Copy the WASD splash in afterwards.

check() {
    return 0
}

depends() {
    echo plymouth
}

install() {
    local script_so file

    script_so=/usr/lib64/plymouth/script.so
    if [[ ! -e $script_so ]]; then
        script_so=/usr/lib/plymouth/script.so
    fi
    if [[ ! -e $script_so ]]; then
        dfatal "WASD splash needs plymouth script.so"
        return 1
    fi
    inst "$script_so"

    for file in \
        /usr/share/plymouth/themes/wasd/wasd.plymouth \
        /usr/share/plymouth/themes/wasd/wasd.script \
        /usr/share/plymouth/themes/wasd/background.png \
        /usr/share/plymouth/themes/wasd/progress_fill.png \
        /usr/share/plymouth/themes/wasd/progress_track.png
    do
        if [[ ! -f $file ]]; then
            dfatal "WASD splash is missing $file"
            return 1
        fi
        inst "$file"
    done

    mkdir -p "${initdir}/usr/share/plymouth/themes" "${initdir}/etc/plymouth"
    ln -sfn wasd/wasd.plymouth "${initdir}/usr/share/plymouth/themes/default.plymouth"
    printf '[Daemon]\nTheme=wasd\n' > "${initdir}/etc/plymouth/plymouthd.conf"
    if [[ -f ${initdir}/usr/share/plymouth/plymouthd.defaults ]] \
        && grep -q '^Theme=' "${initdir}/usr/share/plymouth/plymouthd.defaults"; then
        sed -i 's/^Theme=.*/Theme=wasd/' "${initdir}/usr/share/plymouth/plymouthd.defaults"
    fi
}
