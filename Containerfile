# Allow build scripts to be referenced without being copied into the final image
ARG BASE_IMAGE
FROM scratch AS ctx
COPY build_files /
COPY system_files /system_files
COPY wasd-wallpapers /wasd-wallpapers
COPY wasd-icons /wasd-icons
COPY wasd-loading-screens /wasd-loading-screens
COPY wasd-login-screens /wasd-login-screens
COPY wasd-install /wasd-install

# Which Bazzite desktop to start from. `just build` passes the pin in images.env.
# The NVIDIA open pin is the default. The AMD/Intel pin is the other line.
FROM ${BASE_IMAGE}

RUN --mount=type=bind,from=ctx,source=/,target=/ctx \
    --mount=type=cache,dst=/var/cache \
    --mount=type=cache,dst=/var/log \
    --mount=type=tmpfs,dst=/tmp \
    /ctx/build.sh

RUN bootc container lint
