# Allow build scripts to be referenced without being copied into the final image
FROM scratch AS ctx
COPY build_files /
COPY system_files /system_files
COPY wasd-wallpapers /wasd-wallpapers
COPY wasd-icons /wasd-icons

# NVIDIA open driver. Ada (RTX 4090) uses this image, not the older proprietary one.
# Digest pinned 2026-09-26 from ghcr.io/ublue-os/bazzite-nvidia-open:stable.
FROM ghcr.io/ublue-os/bazzite-nvidia-open:stable@sha256:de1d2b57d34f96d14927bb791f5ee4882c285b4b5957398dc230384c6d823bfe

RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    /ctx/build.sh

RUN bootc container lint
