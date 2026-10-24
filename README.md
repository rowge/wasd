# WASD

**WASD** is a gaming Linux distribution for desktop PCs.

This repo is the clean start. Notes live in [`docs/`](docs/). Artwork from earlier attempts stays on the NAS and is inventoried in [`docs/artwork.md`](docs/artwork.md) — it is not copied in here.

| | |
|---|---|
| Written name | WASD |
| Live user | `player` |
| Live hostname | `wasd` |
| Audience | People who built or bought a gaming PC and want to play, especially FPS |
| Base | [Bazzite](https://bazzite.gg/) AMD/Intel desktop, and the NVIDIA open desktop. Pins are in `images.env`. |
| Agent | Stubs only, for the subscription agents people already pay for. No WASD agent. No local model. |
| Deliverable | A branded live ISO you can use, then install |

The recipe is the container in this repo (`Containerfile`, `build_files/`). GitHub Actions builds both variants and publishes `ghcr.io/rowge/wasd` (AMD/Intel, the default) and `ghcr.io/rowge/wasd-nvidia` (NVIDIA). Each one gets a live ISO.

Start here: [`docs/sketch.md`](docs/sketch.md).
