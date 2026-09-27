# WASD — project sketch

Working notes. Locked so far: the name, the live account, and that artwork never spells "wasdee".

## What this is

A Linux distribution that boots, looks, and plays like **WASD** — not like Fedora, not like SteamOS, not like Bazzite with a sticker on it.

Target machine: a desktop or tower. Someone who built their own PC, or bought a pre-built, and wants to game. They do not want to be on SteamOS. They do not necessarily want to be on Bazzite either. They want an OS that is obviously *for gaming*, especially FPS, with everything included.

The first real product is an ISO:

1. Boot it.
2. Land in a live desktop that is already WASD (hostname, user, prompt, wallpaper, login, installer).
3. Use it like a normal machine.
4. Install it, and the installed system is the same OS, not a different skin that falls off after setup.

## Who it is for

- Desktop / tower PCs (DIY or pre-built)
- People whose main job for this machine is **playing games**
- FPS first: low latency, high refresh, HDR/VRR, good NVIDIA *and* AMD paths
- People who want "it just works" more than they want to assemble Proton, MangoHud, GameMode, and launchers by hand

Not the primary audience (for now): handhelds, Steam Deck clones, living-room Steam Gaming Mode boxes. Those are SteamOS / Bazzite-deck territory. WASD is the keyboard-and-mouse PC.

## Positioning

| Distro | What it is | Why WASD is not that |
|---|---|---|
| SteamOS | Valve's OS. Deck / Steam Machine. Console-like. | Desktop PC users, NVIDIA, full desktop, our branding, our package choices |
| Bazzite | Fedora Atomic gaming image. Excellent, popular, already "the" Linux gaming rec in 2026 | We may *stand on* it. Users should not feel like they installed Bazzite |
| CachyOS | Fast Arch, rolling, power-user | Rolling Arch is not the "everything included, don't break my FPS weekend" pitch |
| Pop!_OS / Mint / etc. | General desktops you then game on | Gaming is the product, not an afterthought |

If we derive from Bazzite, the relationship is: Bazzite is the engine. WASD is the car.

## Locked defaults

| | |
|---|---|
| Written name | WASD |
| Spoken name | wazdee, long E |
| Live username | `player` |
| Live hostname | `wasd` |
| Live prompt (implied) | `player@wasd` |
| Artwork spelling | **wasd only** — no "wasdee", no extra E on the wordmark, no extra E keys |

The live session is `player` on host `wasd`. The person who installs gets to pick *their* user. Installed hostname default is still open.

## Brand

- **Written:** WASD (four letters). Never "wasdee" on screen, in `os-release`, in the installer, or in art.
- **Spoken:** wazdee, long E. That's pronunciation only.

There is already a visual language from earlier art (see [`artwork.md`](artwork.md)):

- Pencil WASD key cluster — usable only in forms that are just W A S D, no trailing E
- Retro stacked wordmark on teal — old file says **WASDee**; that mark does not ship. Needs a four-letter WASD redraw
- A colorful stacked-slab **W** that can work as a mark
- Teal showed up as an accent (Papirus folders were even set to teal last time)

None of that is sacred yet except the spelling rule. It is a starting palette, not a style guide.

## The branded journey

Every surface a user sees from USB insert to first match should say WASD. This is the list we will actually implement against.

### Boot media

- ISO volume label
- UEFI boot entry / GRUB menu title, background, fonts, timeout
- BIOS/legacy isolinux only if we still ship it (most modern PCs never see it — this is why the last splash never changed)
- Plymouth splash from kernel start until the login screen
- Kernel / boot messages hidden behind that splash (`quiet splash`)

### Live session

- Hostname: `wasd`
- Live user: `player` (prompt lands as `player@wasd`)
- `os-release`: `NAME=WASD`, pretty name, home URL
- Fastfetch / neofetch / MOTD
- Terminal prompt, colors, maybe a small logo
- Login manager (SDDM if we stay on Plasma)
- Wallpaper, lock screen, splash, cursor, icons
- Installer app name, icon, and Anaconda/Titanoboa chrome ("Install WASD", not "Install Fedora" / "Install Bazzite")
- About this system / System Settings vendor strings
- Default browser start page / bookmarks only if we actually want them

### Installed system

Same as live, plus:

- First-boot user the *person* chooses (live user is ours; installed user is theirs)
- Hostname they set in the installer, with a WASD-flavored default
- Updates that keep *our* image, not a surprise rebase onto upstream Bazzite
- Our artwork remaining the default, not replaced by Fedora/Bazzite assets on first update

## Technical direction (lean, not locked)

**Likely base:** Bazzite, which is Fedora Atomic / `bootc`, built by Universal Blue.

Why that is a better starting point than last time:

- Gaming stack is already there (Steam, Proton, HDR/VRR, schedulers, drivers)
- Image-based updates with rollback (an FPS box that can undo a bad NVIDIA bump matters)
- Official, supported way to derive a custom image instead of remastering someone else's ISO
- NVIDIA and AMD are first-class (SteamOS historically is not)

**How custom images are actually built in this world:**

1. **`ublue-os/image-template`** — Containerfile + GitHub Actions. You `FROM ghcr.io/ublue-os/bazzite:stable` (or the NVIDIA variant), put branding and packages in `build_files/` and `system_files/`, CI publishes a signed image to GHCR.
2. **BlueBuild** — same idea, YAML recipes instead of a raw Containerfile. Easier modules; one more layer of tooling.
3. **Forking Bazzite itself** — only if we need to rip out large parts of their image. Higher maintenance. Not the first move.

Recommendation when we start building: image-template, `FROM` Bazzite, keep our delta small and explicit.

**How the ISO actually gets made:**

- `bootc-image-builder` (what the ublue template ships) produces installer / disk images. Useful. Not automatically a *try-before-install live desktop*.
- **Titanoboa** (`ublue-os/titanoboa`) is how Universal Blue builds a LiveCD from a bootc image: boot it, use it, then install. That matches the product we described.

So the pipeline we want looks like:

```
our Containerfile  →  WASD bootc image (GHCR)
                   →  Titanoboa  →  branded live+install ISO
```

Branding belongs **in the image**, not patched onto an already-built ISO. That is the single biggest lesson from the last attempt.

## Package changes

The image starts from Bazzite's NVIDIA desktop and keeps that package set, with three edits.

- `waydroid` and `waydroid-selinux` are removed in the build. They are an Android container, and they are not part of this desktop.
- Firefox is not installed. It is only a first-boot Flatpak in Bazzite's KDE list, so it comes off that list.
- Brave is installed from Flathub (`com.brave.Browser`) and set as the default browser.

`mozilla-openh264` stays. It is a video codec package, not the Firefox browser.

## First image

The recipe is in this repo. It builds from `ghcr.io/ublue-os/bazzite-nvidia-open:stable` (digest pinned in the Containerfile).

- `waydroid` and `waydroid-selinux` are removed, along with the launcher, policy, and the Waydroid entry in the welcome screen.
- Brave replaces Firefox. Bazzite's install command downloads their Flatpak list from GitHub, so the build points that command at `/usr/share/wasd/flatpaks` in the image. The list is Bazzite's current KDE installer list with Brave in Firefox's place.
- The desktop wallpaper is `wasdsketch.png`. The login screen wallpaper is `wasd-camp.png`. The logo is installed for the welcome window. The Plymouth theme uses `keysketch.jpg` (as a PNG) with a bar along the bottom, and the USB menu background `moon2.jpg` is in the image for the ISO build.
- The kernel and initramfs are still Bazzite's. The sketch splash shows once the live USB rebuilds the initramfs. The boot menu picture is part of that ISO, not this container.
- Steam, Lutris, Proton tools, GameMode, MangoHud, the NVIDIA driver, and Plasma stay.
- The on-screen name is WASD. The internal id stays `bazzite` so the NVIDIA scripts keep matching.

## Agent

Locked. Stubs only.

WASD does not include an agent of its own, and it does not include a local model. Updates, installs, and crashes are ordinary system behavior. The image ships tiny launchers for the subscription agents people already pay for (Claude, Codex, Grok, and the others Omarchy wires). Nothing downloads until that launcher is run, and the sign-in is to their account. The model stays on that company's servers.

## What we are not doing

The earlier projects (`wasdee-gg`, `wasd-gg`) remastered **LMDE 7** (Linux Mint Debian Edition): dump a machine's package list, chroot, copy wallpapers, hope isolinux/GRUB/Plymouth/SDDM all pick it up.

That is why the boot splash never became ours:

- Isolinux is the legacy BIOS menu. UEFI machines boot GRUB (or systemd-boot). Editing `live.cfg` does nothing on a modern board.
- Plymouth (the actual kernel splash) was never shipped — the script only copied a theme if `wasdee-plymouth/` existed. It didn't.
- SDDM still pointed at Debian logos.
- `dpkg --set-selections` of a personal box is not a distro (the list included things like BibleTime and leftover Cinnamon bits).
- Mint/Debian live tooling regenerates boot assets from the original ISO. Overlaying files after the fact is a fight you lose.

Those trees stay on the NAS. We may lift **artwork** later. We will not lift the remaster scripts.

## Defaults we still have to pick

See [`open-questions.md`](open-questions.md). The ones that still block a first ISO:

- Desktop (Plasma is the Bazzite desktop default and what the last attempt used)
- GPU images: AMD/Intel only, NVIDIA only, or both ISOs
- Update channel: follow Bazzite stable, a slower pin, or our own cadence
- A WASD wordmark (four letters) to replace the old WASDee art

## Where the ISO lives

`main/wasd` on the NAS (`smb://angelwatch.local/main/wasd`) is the only published copy of the ISO. When `wasd.click` exists, the site points at that share for the download. The domain waits until an image has actually booted.

Icons and wallpapers stay in this git repo (`wasd-icons/`, `wasd-wallpapers/`). The image build copies those folders into the system, so an update to the art is in the next image without a separate upload. GitHub's builder cannot see the NAS, which is why the pictures live here and the finished ISO file lives there. No ISOs in git.

## Repo hygiene

This directory stays the source of truth for the recipe. Keep it small.

- Notes, the Containerfile, system files, and the curated icons and wallpapers
- No dump of the old projects
- No ISOs in git
