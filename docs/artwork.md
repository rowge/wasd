# Artwork inventory

Spelling rule: every mark we ship says **WASD**. Not "wasdee". Not an extra E key as a pronunciation gag. Spoken name can still be wazdee; it never appears in the art.

Nothing from the old projects is copied into this repo. These are pointers so we can pull specific files later.

NAS root: `smb://angelwatch.local/main/`
Mounted here as: `/run/user/1000/gvfs/smb-share:server=angelwatch.local,share=main/`

The published ISO goes in `smb://angelwatch.local/main/wasd`.

## Usable as-is

| File | Size | Notes |
|---|---|---|
| `backup/wasdee-logo.png` | 960×960 PNG | Stacked colorful slabs forming a **W**. No letters. Strong mark. |
| `backup/wasd-gg/wasd-icons/wasdee-logo.png` | | Copy of the W mark. |
| `backup/wasd-gg/wasd-icons/splash.png` | | Pixel-art mountain landscape. Nice, but not branded WASD. Maybe a wallpaper, not a logo. |

## Edited in `wasd-wallpapers/`

The E keys and the extra "ee" in the wordmark were removed in place. Blank keys that were already blank were left alone.

| File | Result |
|---|---|
| `wasd-wallpapers/wasdee-login-bg.png` | Deleted. The wordmark cut left a blunt D. |
| `wasd-wallpapers/wasdsketch.png` | Pencil cluster. Trailing E key removed. Blank key beside W stays. |
| `wasd-wallpapers/keysketch.jpg` | Top row is W A S D. The two E keys underneath are removed. |
| `wasd-wallpapers/keysketch2.jpg` | Blank, W, A, S, D. The two light E keys on the right are removed. A faint patch remains in that spot. |
| `wasd-wallpapers/keysketchrgb.jpg` | New neon drawing. Cyan W, magenta A, red S, green D. Smooth dark background. |
| `wasd-wallpapers/wasdsketch-800x600.jpg` | Same cluster as `wasdsketch.png`, E key removed. |

## Personal / off-brand photos that were used as wallpapers

These were in the wallpaper folders. They are personal photos (aquarium light, camera, moon, kydex, tubes). Fine as *your* desktop. Wrong as the default distro wallpaper pack unless we decide they are part of the identity.

- `kydex.jpg`, `tubes.jpg`, `legocamera.jpg`, `kessil.jpg`
- `moon1.jpg`, `moon2.jpg`

Same set exists in both:

- `backup/wasdee-gg/wasdee-wallpapers/`
- `backup/wasd-gg/wasd-wallpapers/`

## Live USB assignments

| Screen | File | Notes |
|---|---|---|
| USB boot menu | `wasd-wallpapers/moon2.jpg` | Menu text sits on the black, left of the moon. |
| Loading splash | `wasd-wallpapers/keysketch.jpg` | Keys stay up top. A loading bar runs along the bottom. The theme ships a PNG copy at `system_files/usr/share/plymouth/themes/wasd/background.png`, made from this file. |
| Live desktop | `wasd-wallpapers/wasdsketch.png` | |
| Welcome window logo | `wasd-icons/wasd-logo.png` | Renamed from `wasdee-logo.png`. Checkerboard removed so the background is actually transparent. |
| Login wallpaper (installed system, not the live USB) | `wasd-wallpapers/wasd-camp.png` | |

## Surfaces we still need art for

- Installer header and sidebar
- ISO volume icon
- Installer `.desktop` icon
- Favicon, once there is a site

When we import, import **specific files into a curated `artwork/` tree** (logo, wordmark, plymouth, grub, sddm, wallpapers). Do not copy the old project directories.
