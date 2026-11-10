#!/bin/bash
# Plymouth's generic (--no-hostonly) initramfs keeps its own spinner and
# does not pick up a theme added later. Copy the WASD splash in afterwards.

check() {
    return 0
}

depends() {
    echo plymouth
}

# Plymouth's module runs first and copies the stock stained-glass picture
# into the initramfs. dracut's inst leaves a file that is already there, so
# inst of the chosen picture does not replace it. Copy over that file.
install_loading_picture() {
    local source=${1:-/etc/wasd/loading-background.png}
    local stock=${2:-/usr/share/plymouth/themes/wasd/background.png}
    local theme_dir dest

    theme_dir="${initdir}/usr/share/plymouth/themes/wasd"
    dest="${theme_dir}/background.png"
    mkdir -p "$theme_dir"
    if [[ -s $source ]]; then
        rm -f "$dest"
        cp -f "$source" "$dest"
        chmod 0644 "$dest"
        return 0
    fi
    if [[ -s $stock ]]; then
        if [[ ! -s $dest ]]; then
            inst "$stock" /usr/share/plymouth/themes/wasd/background.png
        fi
        return 0
    fi
    dfatal "WASD splash is missing background.png"
    return 1
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
        /usr/share/plymouth/themes/wasd/progress_fill.png \
        /usr/share/plymouth/themes/wasd/progress_track.png
    do
        if [[ ! -f $file ]]; then
            dfatal "WASD splash is missing $file"
            return 1
        fi
        inst "$file"
    done

    install_loading_picture

    mkdir -p "${initdir}/usr/share/plymouth/themes" "${initdir}/etc/plymouth"
    ln -sfn wasd/wasd.plymouth "${initdir}/usr/share/plymouth/themes/default.plymouth"
    printf '[Daemon]\nTheme=wasd\n' > "${initdir}/etc/plymouth/plymouthd.conf"
    if [[ -f ${initdir}/usr/share/plymouth/plymouthd.defaults ]] \
        && grep -q '^Theme=' "${initdir}/usr/share/plymouth/plymouthd.defaults"; then
        sed -i 's/^Theme=.*/Theme=wasd/' "${initdir}/usr/share/plymouth/plymouthd.defaults"
    fi
}

# dracut sources this file. The check runs only when the file itself is executed.
self_check() {
    local tmp initdir chosen stock dest skipped
    tmp=$(mktemp -d)
    initdir=$tmp/initramfs
    chosen=$tmp/chosen.png
    stock=$tmp/stock.png
    dest=$initdir/usr/share/plymouth/themes/wasd/background.png
    printf 'basement' > "$chosen"
    printf 'stained-glass' > "$stock"
    mkdir -p "$(dirname "$dest")"
    printf 'stained-glass' > "$dest"

    # The real inst returns without writing when the destination exists.
    inst() {
        local target=${2:-$1}
        target=${target#/}
        if [[ -e ${initdir}/${target} ]]; then
            skipped=1
            return 0
        fi
        mkdir -p "${initdir}/$(dirname "$target")"
        cp -f "$1" "${initdir}/${target}"
    }
    dfatal() {
        echo "$*" >&2
        return 1
    }

    skipped=0
    install_loading_picture "$chosen" "$stock"
    if [[ $(cat "$dest") != basement ]]; then
        echo "chosen loading picture did not replace the stained glass" >&2
        rm -rf "$tmp"
        return 1
    fi
    if [[ $skipped -ne 0 ]]; then
        echo "chosen loading picture went through inst" >&2
        rm -rf "$tmp"
        return 1
    fi

    rm -f "$dest"
    skipped=0
    install_loading_picture "$tmp/missing.png" "$stock"
    if [[ $(cat "$dest") != stained-glass || $skipped -ne 0 ]]; then
        echo "stock loading picture was not the fallback" >&2
        rm -rf "$tmp"
        return 1
    fi

    if install_loading_picture "$tmp/missing.png" "$tmp/missing-stock.png" 2>/dev/null; then
        echo "a missing loading picture was accepted" >&2
        rm -rf "$tmp"
        return 1
    fi

    rm -rf "$tmp"
    echo "plymouth loading picture self-check ok"
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
    case ${1-} in
        --self-check)
            self_check
            ;;
        *)
            echo "This is a dracut module." >&2
            exit 2
            ;;
    esac
fi
