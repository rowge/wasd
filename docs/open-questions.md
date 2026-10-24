# Open questions

Decide these as we go. Bold items block a first bootable ISO.

## Locked

- Written name: **WASD** (never "wasdee" in UI or art)
- Live username: `player`
- Live hostname: `wasd`
- Live prompt lands as `player@wasd`
- No WASD agent and no local model. The image does not run an agent, ship a model, or hand crashes to one.
- Stubs ship for the common subscription agents (Claude, Codex, Grok, and the others Omarchy wires). Nothing downloads until the first launch of that agent. The person signs into their own account.
- Remove `waydroid` and `waydroid-selinux` from the image.
- Do not install Firefox. Brave (`com.brave.Browser`) is the browser, and it is the default.

## Identity still open

- **Installed-system default hostname** suggested by the installer (could stay `wasd`).
- Prompt *theme* (plain bash `player@wasd`, starship, etc.). The user/host are locked; the look of the prompt is not.
- Domain / home URL. Old `os-release` pointed at an X account. Do we want `wasd.gg` or similar?
- Color: commit to teal, or rebuild the palette around the W-slab mark?

## Product

- **Desktop environment.** Plasma is the default lean (Bazzite desktop + last attempt). Steam Gaming Mode as a session, or desktop-only?
- **GPU variants.** Two images, one workflow. AMD/Intel is the default, `ghcr.io/rowge/wasd`, from `bazzite`. NVIDIA open is `ghcr.io/rowge/wasd-nvidia`, from `bazzite-nvidia-open`. Pins are in `images.env`. The plain ISO is AMD/Intel. The NVIDIA ISO is named `WASD-nvidia`.
- Handheld / deck images: no for v1?
- Dual-boot with Windows as a first-class installer path?
- Secure Boot: ship and sign, or document a manual enroll like Bazzite?

## Stack

- **Confirm Bazzite as the base**, vs Fedora Atomic from scratch, vs something else.
- image-template (Containerfile) vs BlueBuild (YAML recipes). Lean: image-template.
- Update cadence: track Bazzite `stable`, pin and batch, or our own slower "don't break ranked on a Thursday" channel?
- Which Bazzite tag: `stable` vs `testing` vs a Fedora version pin.
- NVIDIA: proprietary vs `nvidia-open`.

## Live ISO

- Titanoboa (real live desktop + install) vs bootc-image-builder installer-only ISO. Lean: Titanoboa, because "use the live environment normally" is a product requirement.
- Live user (`player`) password: none / well-known (`wasd` or `player`) / random-and-printed-on-the-screen?
- Default apps on the live session vs on the installed image (they can differ).

## Software set

What is "everything included" for an FPS PC?

- Steam: yes, from the Bazzite base
- Lutris: yes, from the Bazzite base
- Heroic and Bottles: yes, Flatpaks
- Discord and Element: yes, Flatpaks, next to each other
- OBS Studio, GOverlay, EasyEffects, Piper, OpenRGB, and LACT: yes, Flatpaks
- Browser: Brave
- Proton-GE and GameMode: not added yet
- GPU overlay / reflex / frame-gen helpers: GOverlay is the settings window. The rest of this line is still open.
- Kernel / scheduler: inherit Bazzite, or pick (BORE, etc.)
- What we refuse to ship (the last package dump had a lot of unrelated desktop cruft)

## Art

- Which of the existing pieces become *the* logo?
- Do personal photos (moon, aquarium, kydex) belong in the distro at all?
- New four-letter WASD wordmark (the old WASDee mark does not ship, even as a placeholder)

## Out of scope for v1 (unless we change our minds)

- Own package repo / COPR
- The public site is `site/`. The front page links AMD and Intel, then NVIDIA, at the GitHub release files `WASD.iso` and `WASD-nvidia.iso`. Those files are uploaded only when asked. ISOs are not attached to GitHub on every build.
- Official support forum
- ARM / handheld images
- Shipping games themselves
