# WASD

**WASD** (pronounced *wazdee*, long E) is a gaming Linux distribution for desktop PCs.

This repo is the clean start. Notes live in [`docs/`](docs/). Artwork from earlier attempts stays on the NAS and is inventoried in [`docs/artwork.md`](docs/artwork.md) — it is not copied in here.

| | |
|---|---|
| Written name | WASD (never "wasdee") |
| Spoken name | wazdee |
| Live user | `player` |
| Live hostname | `wasd` |
| Audience | People who built or bought a gaming PC and want to play, especially FPS |
| Base | [Bazzite](https://bazzite.gg/) NVIDIA desktop, `ghcr.io/ublue-os/bazzite-nvidia-open:stable` |
| Agent | Stubs only, for the subscription agents people already pay for. No WASD agent. No local model. |
| Deliverable | A branded live ISO you can use, then install |

The first image is the container recipe in this repo (`Containerfile`, `build_files/`). GitHub Actions publishes it to `ghcr.io/rowge/wasd`. The live ISO is the step after that image has been built.

Start here: [`docs/sketch.md`](docs/sketch.md).
