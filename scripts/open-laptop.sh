#!/bin/bash
# Open SSH on a WASD laptop. This is not installed into the image.
# From the laptop, on the home network:
#   curl -fsSL http://192.168.50.8/wasd/open-laptop.sh -o /tmp/w && sudo bash /tmp/w
# On the live USB the password is empty: press Enter at the sudo prompt.
# A USB copy still runs with: bash open-laptop.sh
set -euo pipefail

KEY='ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGaPeYlyGGADP7+Jv45QdCEWauVcWChM4VfNXN+NIrBX rowge@soulforge'

if [[ ${EUID} -ne 0 ]]; then
    # A pipe into bash has no file for sudo to re-run, and sudo would
    # read the script itself as the password. Save the file, then sudo.
    if [[ -f $0 && $0 != /dev/fd/* && $0 != /proc/* ]]; then
        script=$(readlink -f "$0")
        exec sudo -- bash "$script" "$@"
    fi
    echo "Save the script, then run it with sudo. On the live USB, press Enter." >&2
    echo "curl -fsSL http://192.168.50.8/wasd/open-laptop.sh -o /tmp/w && sudo bash /tmp/w" >&2
    exit 1
fi

if ! systemctl cat sshd.service >/dev/null 2>&1; then
    echo "sshd is not installed on this computer." >&2
    exit 1
fi

install -d -m 0755 /etc/ssh/sshd_config.d
cat >/etc/ssh/sshd_config.d/50-wasd-open.conf <<'EOF'
PermitEmptyPasswords no
EOF
chmod 0644 /etc/ssh/sshd_config.d/50-wasd-open.conf

add_key() {
    local user="$1" home group file
    home=$(getent passwd "$user" | cut -d: -f6)
    [[ -n $home && -d $home ]] || return 0
    group=$(id -gn "$user")
    install -d -m 0700 -o "$user" -g "$group" "$home/.ssh"
    file="$home/.ssh/authorized_keys"
    if [[ ! -f $file ]]; then
        touch "$file"
    fi
    chown "$user:$group" "$file"
    chmod 0600 "$file"
    if ! grep -qxF "$KEY" "$file"; then
        printf '%s\n' "$KEY" >>"$file"
        chown "$user:$group" "$file"
        chmod 0600 "$file"
    fi
    if command -v restorecon >/dev/null 2>&1; then
        restorecon -R "$home/.ssh" || true
    fi
}

opened=()
while IFS=: read -r name _ uid _ _ home shell; do
    [[ $uid =~ ^[0-9]+$ ]] || continue
    ((uid >= 1000 && uid < 60000)) || continue
    [[ -d $home ]] || continue
    case $shell in
        */nologin | */false) continue ;;
    esac
    add_key "$name"
    opened+=("$name")
done </etc/passwd

if [[ ${#opened[@]} -eq 0 ]]; then
    echo "No account was available for the key." >&2
    exit 1
fi

if systemctl is-active --quiet firewalld; then
    firewall-cmd --add-service=ssh >/dev/null || true
    firewall-cmd --permanent --add-service=ssh >/dev/null || true
fi

systemctl enable sshd
systemctl restart sshd

echo "SSH is on for: ${opened[*]}"
echo "Addresses: $(hostname -I 2>/dev/null || true)"
