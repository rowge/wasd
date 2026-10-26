# For Ben

These are the steps for the two jobs you do by hand: add pictures and ship them, and point WASD at a newer Bazzite. The repo on this machine is `/home/rowge/grok/wasd`. GitHub is https://github.com/rowge/wasd. The branch is `main`.

A push that starts a build runs on Hammerite. AMD/Intel is built first. That is the laptop image, and its ISO name has no extra word in it. NVIDIA starts after the AMD job finishes. That is the image for Elemental, and its ISO name contains `nvidia`.

One build runs at a time. A second push waits in line behind the one already running.

## Add pictures

There is no separate art folder for the installer. Install WASD and WASD Look both read the four folders below. A new file in the right folder becomes a choice on the next image. It does not become the default. The default section is further down.

| What you are adding | Folder | Push starts a build |
|---|---|---|
| Character icon | `wasd-icons/` | Yes |
| Wallpaper | `wasd-wallpapers/` | Yes |
| Loading screen | `wasd-loading-screens/` | No. Start the run by hand after the push. |
| Login screen | `wasd-login-screens/` | No. Start the run by hand after the push. |

The logo file is `wasd-icons/wasd-logo.png`. Leave that file there. It is the W on the boot splash and in the windows. It is not one of the character choices.

### Shape of the picture

Use `.jpg`, `.jpeg`, `.png`, or `.webp`. The file name uses letters, numbers, dots, hyphens, and underscores. `stained-glass.jpg` is a good name. `my picture.jpg` is a bad name. A file with any other extension is skipped. If a folder ends up with no images at all, the build stops.

Loading screens are 16:9. `1792×1008` and `1920×1080` are the sizes that fit. Put one W in the upper part of the picture. Leave the bottom fifth empty and dark. Plymouth draws the loading bar there. Do not paint a bar, and do not paint the word LOADING.

Login screens are 16:9. Put the subject on one side and leave the other side quiet. That quiet side is where the sign-in box sits. No words.

Wallpapers are 16:9. `1920×1080` is the target, and `1792×1008` is fine. The picture can fill the whole frame. Plasma scales other sizes, and a taller picture loses its top and bottom on a 16:9 screen.

Character icons are square. A big face and shoulders still read when the picture is cropped to a circle. No words.

`wasd-login-screens/throne.jpg` is the login picture. `wasd-login-screens/camp.png` stays a login choice. `wasd-wallpapers/camp.png` is a wallpaper. The two camp files are different files.

These files are named in the build checks. Leave them in place unless you also change `build_files/build.sh`:

- `wasd-wallpapers/stained-glass.jpg`
- `wasd-wallpapers/wasdsketch.png`
- `wasd-wallpapers/camp.png`
- `wasd-wallpapers/keysketch.jpg`
- `wasd-loading-screens/stained-glass.jpg`
- `wasd-loading-screens/keysketch.jpg`
- `wasd-login-screens/camp.png`
- `wasd-login-screens/throne.jpg`
- `wasd-icons/wasd-logo.png`

### Steps

1. Copy the file into the folder in the table.
2. From `/home/rowge/grok/wasd`, look at what will be committed:

```bash
cd /home/rowge/grok/wasd
git status
```

3. Add that file. This example is one wallpaper. Use the real folder and file name.

```bash
git add wasd-wallpapers/my-picture.jpg
git commit -m "Add the my-picture wallpaper."
git push origin main
```

Add a whole folder the same way, for example `git add wasd-loading-screens`. Commit only the pictures you mean to ship. Do not commit an ISO. ISO files are already ignored.

4. Open https://github.com/rowge/wasd/actions. A run named **Build WASD** appears for icons and wallpapers, because those folders are on the list that starts a build.

5. A commit that only changes loading screens or login screens does not appear there. Start it yourself:

- Open https://github.com/rowge/wasd/actions/workflows/build.yml
- Click **Run workflow**
- Branch: `main`
- Squashfs compression: `fast`
- Click the green **Run workflow** button

`fast` is the right choice while you are still changing pictures. `release` spends much longer compressing the ISO. Use it when you are making a stick you plan to keep.

6. The AMD file shows up on the NAS about an hour after the run starts, in the share `main/wasd` (`smb://angelwatch.local/main/wasd`). The name uses the UTC date, so an evening push in California is often the next calendar day:

```text
WASD-YYYYMMDD-SHORTSHA.iso
WASD-latest.iso
```

`WASD-latest.iso` is a link to that file. A `.sha256` file sits next to it. NVIDIA is the same pattern with `WASD-nvidia-` in the name, and it starts after AMD finishes, about another hour. The success email arrives after NVIDIA finishes. A failure email arrives when the failing job stops. The AMD file can already be on the NAS before that final email.

When the job finishes, Hammerite also replaces `https://downloads.wasd.run/WASD.iso` and `https://downloads.wasd.run/WASD-nvidia.iso`. The NAS keeps the dated files. The public names are only the latest pair.

## Change the default picture

Adding a file gives you a new choice. The picture that comes up first is set in a few files. Change the quoted file name in each place, in one commit.

Loading splash:

- `wasd-install/Main.qml`, the line `loadingChoice`
- `wasd-install/Look.qml`, the line `loadingChoice`
- `wasd-install/Lister.qml`, the loading name inside `prefer`
- `wasd-install/run.py`, the first name in `LOADING_ORDER`, and the `stained-glass.jpg` check near the bottom
- The baked splash, which is a PNG of the JPEG:

```bash
ffmpeg -y -loglevel error \
  -i wasd-loading-screens/THE-FILE.jpg \
  system_files/usr/share/plymouth/themes/wasd/background.png
```

Desktop wallpaper:

- `system_files/usr/share/plasma/shells/org.kde.plasma.desktop/contents/updates/zz-wasd-wallpaper.js`
- `wasd-install/Main.qml` and `wasd-install/Look.qml`, the line `wallpaperChoice`
- `wasd-install/Lister.qml`, the wallpaper name inside `prefer`
- `wasd-install/run.py`, `WALL_ORDER` and the wallpaper check

Login screen:

- `system_files/usr/lib/plasmalogin/defaults.conf`, both `Image` and `PreviewImage`
- `wasd-install/Main.qml` and `wasd-install/Look.qml`, the line `loginChoice`
- `wasd-install/Lister.qml` and `wasd-install/LiveHost.qml`, the login name inside `prefer`
- `wasd-install/run.py`, the `throne.jpg` check

Then commit and push. A commit that includes `system_files/` starts the build. A commit that only changes `wasd-install/` does not. In that case use **Run workflow**, the same clicks as in the previous section.

The current defaults are the stained-glass W for the loading splash, `wasd-wallpapers/stained-glass.jpg` for the desktop, and `wasd-login-screens/throne.jpg` for login. `camp.png` stays a login choice.

## Take a newer Bazzite

WASD is built on top of two exact Bazzite snapshots written in `images.env`. A push that leaves those lines alone rebuilds WASD on the same Bazzite. The build does not follow the moving `stable` tag by itself.

Bazzite's own guide says the `stable` images update every fortnight, every other week. Their testing images update almost every day. WASD stays on `stable`. Checked against that guide on 2026-10-25: https://docs.bazzite.gg/Installing_and_Managing_Software/Updates_Rollbacks_and_Rebasing/rebase_guide/

Recent stable builds landed on 2026-10-12 and 2026-10-23, about eleven days apart. Plan on doing this about every two weeks while you are actively making WASD, and again before you write a USB you are going to test or hand to someone. Do it sooner when a Bazzite release has a graphics driver, kernel, or boot fix you need. Skip it when the digest command below prints the same values already in `images.env`.

Do both images on the same day so the laptop ISO and Elemental's ISO come from the same Bazzite. On the evening of 2026-10-25 the AMD line still matched `stable`, and the NVIDIA line was behind it. Run the command again before you edit. Those sentences go stale.

A machine that is already running WASD does not track Bazzite. It tracks `ghcr.io/rowge/wasd` (the laptop) or `ghcr.io/rowge/wasd-nvidia` (Elemental). It receives the newer Bazzite only after this build is published, and the update applies on the next reboot.

### Read the current stable digests

From `/home/rowge/grok/wasd`:

```bash
digest_of() {
  local repo=$1 tag=$2
  local token
  token=$(curl -fsS "https://ghcr.io/token?service=ghcr.io&scope=repository:${repo}:pull" | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])')
  curl -fsSI \
    -H "Authorization: Bearer ${token}" \
    -H "Accept: application/vnd.oci.image.manifest.v1+json" \
    "https://ghcr.io/v2/${repo}/manifests/${tag}" \
    | awk 'tolower($1)=="docker-content-digest:" {print $2}' \
    | tr -d '\r'
}

digest_of ublue-os/bazzite stable
digest_of ublue-os/bazzite-nvidia-open stable
```

Each line prints `sha256:` and 64 hex characters. If a printed value is already the value in `images.env`, that image has no newer stable. Leave its line alone.

### Write them into images.env

Open `images.env`. The two lines that matter look like this:

```text
nvidia_base=ghcr.io/ublue-os/bazzite-nvidia-open:stable@sha256:PASTE_THE_NVIDIA_DIGEST_HERE
amd_base=ghcr.io/ublue-os/bazzite:stable@sha256:PASTE_THE_AMD_DIGEST_HERE
```

Paste the digest after `@`. Keep the `sha256:` that the command printed. Update the date comments above those lines. Save the file.

The build rejects a line that is only `:stable` with no digest. Both lines have to stay in that exact `@sha256:` form.

### Push it

`images.env` is on the list that starts a build, so this push is the build. You do not need any other change.

```bash
cd /home/rowge/grok/wasd
git diff images.env
git add images.env
git commit -m "Point both images at the current Bazzite stable."
git push origin main
```

If a build is already running, this one waits. Cancel the older run first when you do not want to wait for it. The cancel steps are in the next section.

Then open https://github.com/rowge/wasd/actions and confirm the new run is for this commit. The AMD ISO name will be `WASD-` plus the UTC date plus the new short commit id.

## See a run, and cancel a bad one

The run list is https://github.com/rowge/wasd/actions. Click the run. The AMD job is **Image and live ISO (amd)**. The NVIDIA job is **Image and live ISO (nvidia)**. A healthy image build takes most of an hour before the AMD ISO is copied. A job that dies in the first few minutes at **Build the image** stopped inside the recipe. Open that job and read the log on the page. The link in the GitHub email opens the same run.

To cancel:

1. Open the run from the Actions list, or from the email.
2. At the top of the run, click **Cancel workflow**.
3. A queued run has the same button. Cancel that one too when you do not want it to start after the current one.

Cancelling stops the job and lets the next waiting run start. An ISO that was already copied to the NAS stays there. Cancelling during NVIDIA leaves the AMD ISO in place.

Leave Hammerite running. Stopping the builder from the server is the wrong cancel. GitHub then records a failed job and the next run can sit stuck behind it.

If NVIDIA fails in a few seconds with `403` while pulling `bazzite-nvidia-open`, the AMD job logged in to push its image and that login was still there. GitHub then refuses the public Bazzite pull. On that run, open **Re-run jobs** and choose **Re-run failed jobs**. That builds NVIDIA only. **Re-run all jobs** builds AMD again too. The builder has to be logged out of ghcr.io before that re-run, or the same 403 comes back.

## A few other things

- Bigger changes that are still waiting, such as the theme pack, the smaller ISO, and the install button that really erases a disk, are listed in `docs/next-build.md`. Dropping a picture does not go on that list.
- This file lives in `docs/`. A commit that only changes `docs/` does not start a build.
- Changes to the installer program in `wasd-install/` also do not start a build. Push them, then use **Run workflow**.
- `docs/artwork.md` is the inventory of pictures. `docs/sketch.md` describes what the image contains.
- The public download page is https://wasd.run. The files it links are the two names on `downloads.wasd.run`, replaced whenever a job publishes.
