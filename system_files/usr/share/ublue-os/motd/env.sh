#!/usr/bin/env sh
# KEEP THIS SMALL
# This will run on every shell that a user starts up.
# The image line is the image this computer is running. image-info.json is
# the Bazzite image the build started from, and it stays that way.

clean_ref() {
    ref=$1
    case $ref in
        ostree-image-signed:docker://*) ref=${ref#ostree-image-signed:docker://} ;;
        ostree-unverified-image:docker://*) ref=${ref#ostree-unverified-image:docker://} ;;
        ostree-unverified-registry:*) ref=${ref#ostree-unverified-registry:} ;;
        ostree-image-signed:*) ref=${ref#ostree-image-signed:} ;;
        docker://*) ref=${ref#docker://} ;;
    esac
    printf '%s' "$ref"
}

booted=""
if command -v rpm-ostree >/dev/null 2>&1 && command -v jq >/dev/null 2>&1; then
    booted=$(rpm-ostree status --json 2>/dev/null | jq -r '
        .deployments[] | select(.booted == true) | ."container-image-reference" // empty
    ' 2>/dev/null | head -n 1 || true)
    booted=$(clean_ref "$booted")
fi
if [ -z "$booted" ] || [ "$booted" = "null" ]; then
    info="${MOTD_IMAGE_INFO_FILE:-/usr/share/ublue-os/image-info.json}"
    booted=$(clean_ref "$(jq -rc '."image-ref" // empty' "$info" 2>/dev/null || true)")
    branch=$(jq -rc '."image-branch" // empty' "$info" 2>/dev/null || true)
    case $booted in
        *:*|*@*) ;;
        "") ;;
        *)
            if [ -n "$branch" ] && [ "$branch" != "null" ]; then
                booted="${booted}:${branch}"
            fi
            ;;
    esac
fi
export MOTD_IMAGE_NAME="$booted"
export MOTD_IMAGE_BRANCH="$(jq -rc '."image-branch"' "${MOTD_IMAGE_INFO_FILE:-/usr/share/ublue-os/image-info.json}" 2>/dev/null || true)"
export MOTD_IMAGE_TAG="$(jq -rc '."image-tag"' "${MOTD_IMAGE_INFO_FILE:-/usr/share/ublue-os/image-info.json}" 2>/dev/null || true)"
case "${LC_MESSAGES:-${LANG:-C}}" in
  sv*)
    export MOTD_TEMPLATE_FILE="${MOTD_TEMPLATE_FILE:-/usr/share/ublue-os/motd/template.sv.md}"
    export MOTD_TIP_DIRECTORY="${MOTD_TIP_DIRECTORY:-/usr/share/ublue-os/motd/tips/sv}"
    ;;
esac
export MOTD_TIP="${MOTD_TIP:-"$(/usr/bin/cat "${MOTD_TIP_DIRECTORY:-/usr/share/ublue-os/motd/tips}"/*.md 2>/dev/null | shuf -n 1)"}"
GREENBOOT=""
if [ -f /etc/motd.d/boot-status ]; then
	if grep -q "status is GREEN" /etc/motd.d/boot-status; then
		GREENBOOT='Boot Status: Healthy 󰄳'
	else
		GREENBOOT=$(cat /etc/motd.d/boot-status)
	fi
fi
export MOTD_GREENBOOT="$GREENBOOT"
