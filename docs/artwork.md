# Artwork inventory

Spelling rule: every mark we ship says **WASD**. Not "wasdee". Not an extra E key.

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
| `wasd-wallpapers/keysketch.jpg` | Four keys in a row: W A S D. Pencil ground. Still a loading choice. The default splash is the stained-glass W. |
| `wasd-wallpapers/keysketch2.jpg` | Blank key and W on the top row, A S D below. Not used on a screen. |
| `wasd-wallpapers/keysketchrgb.jpg` | New neon drawing. Cyan W, magenta A, red S, green D. Smooth dark background. |
| `wasd-wallpapers/wasdsketch-800x600.jpg` | Deleted. It was a small copy of the same cluster. |

## Photos in the wallpaper gallery

Every image in `wasd-wallpapers/` is installed for the Plasma wallpaper picker. The default desktop is `stained-glass.jpg`. The camp picture is still the login screen. The moon is only a wallpaper. The default loading splash is the stained-glass W. The USB menu has no picture.

Older copies of this set also sit on the NAS:

- `backup/wasdee-gg/wasdee-wallpapers/`
- `backup/wasd-gg/wasd-wallpapers/`

## Live USB assignments

| Screen | File | Notes |
|---|---|---|
| USB boot menu | none | Black background, white text. No picture. |
| Loading splash | `wasd-loading-screens/stained-glass.jpg` | A loading bar runs along the bottom. Plymouth loads a PNG copy at `system_files/usr/share/plymouth/themes/wasd/background.png`, made from this file. |
| Live desktop | `wasd-wallpapers/stained-glass.jpg` | The room with the stained-glass W. |
| Welcome window logo | `wasd-icons/wasd-logo.png` | Renamed from `wasdee-logo.png`. Checkerboard removed so the background is actually transparent. |
| Login wallpaper (installed system, not the live USB) | `wasd-login-screens/camp.png` | |

## Surfaces we still need art for

- Installer header and sidebar
- ISO volume icon
- Installer `.desktop` icon
- Favicon, once there is a site

When we import, import **specific files into a curated `artwork/` tree** (logo, wordmark, plymouth, login, wallpapers). Do not copy the old project directories. The USB menu stays black and white, with no picture.
