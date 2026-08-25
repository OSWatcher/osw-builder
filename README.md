# osw-builder

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python versions](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![CI](https://github.com/OSWatcher/osw-builder/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/OSWatcher/osw-builder/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-GitHub%20Pages-blue.svg)](https://oswatcher.github.io/osw-builder/)

> Turn an OS ISO into a queryable graph snapshot. osw-builder builds a VM image from an installer ISO, then captures its filesystem and registry into a Neo4j graph — fully unattended — so you can diff and query operating systems the way you query a git history.

It feeds a queryable graph of operating system evolution covering Windows 95 → 11 and Ubuntu 6.10 → 25.04.

**What it does, end to end:**

1. Build a VM image from an ISO using Packer (runs inside Docker, no local Packer install needed)
2. Register the image with Vagrant/libvirt
3. Capture the filesystem and registry into Neo4j via [neogit](https://github.com/OSWatcher/neogit) as content-addressed Merkle trees
4. Optionally search for and install OS updates, snapshotting and capturing after each one

```
ISO ─▶ image_builder ─▶ vagrant ─▶ capture ─▶ updates ─▶ Neo4j graph
       (Packer/Docker)  (libvirt)  (libguestfs)  (apt /
                                                  Windows Update)
```

📖 **Full documentation:** <https://oswatcher.github.io/osw-builder/> — tutorials, how-to guides, configuration reference, and architecture explanations.

---

## Prerequisites

**System packages**

| Tool | Purpose |
|------|---------|
| QEMU/KVM + libvirt | VM hypervisor |
| `vagrant` + `vagrant-libvirt` plugin | VM lifecycle management |
| Docker | Runs the Packer build container |
| `libguestfs-tools` | Offline filesystem inspection (capture) |
| `sshpass` | SSH into VMs during update installation |
| Python 3.11+ | Runtime |
| Poetry | Dependency management |

**Infrastructure** (only needed for capture — see [neogit](https://github.com/OSWatcher/neogit) for setup)

- Neo4j 5.x — graph database where OS snapshots are stored
- Object storage for file contents — neogit defaults to the **local filesystem**, so MinIO (or any S3-compatible store) is optional and only needed for a distributed/production setup like [oswatcher-deploy](https://github.com/OSWatcher/oswatcher-deploy)

---

## Two ways in

**🎓 I just want to try it.** Follow the [first-capture tutorial](https://oswatcher.github.io/osw-builder/tutorials/first-capture.html): it walks you from zero to a captured Ubuntu image with a single Neo4j container and no product keys. Budget one to two hours, mostly unattended.

**🏗️ I want to run this for real.** Read the rest of this README, then the [how-to guides](https://oswatcher.github.io/osw-builder/how-to/index.html) for providing ISOs, adding images, and building without capture. For the full OSWatcher infrastructure (Neo4j + MinIO + API + frontend), see [oswatcher-deploy](https://github.com/OSWatcher/oswatcher-deploy).

---

## Installation

```bash
git clone --recurse-submodules https://github.com/OSWatcher/osw-builder.git
cd osw-builder
poetry install
```

`--recurse-submodules` matters: the Packer templates live in a git submodule. If you forgot it, run `git submodule update --init`.

System dependencies (QEMU, libvirt, Vagrant, Docker, libguestfs) are not Python packages — install them first. See [Install system dependencies](https://oswatcher.github.io/osw-builder/how-to/install-system-deps.html).

---

## Configuration

### `config.yaml` — your local config (not committed)

Override any value from `default_settings.yaml`. At minimum, provide ISO paths:

```yaml
images:
  - name: win10-22h2-19045.2006
    source: /path/to/Win10_22H2.iso

  - name: ubuntu-22.04
    source: https://releases.ubuntu.com/jammy/ubuntu-22.04.4-live-server-amd64.iso
```

You can also override the libvirt connection URI, storage pool, or any build/runtime config:

```yaml
storage_pool: default
images:
  - name: ubuntu-22.04
    source: /data/isos/ubuntu-22.04.4-live-server-amd64.iso
    runtime_config:
      search_updates: true
```

### `osw_builder/default_settings.yaml` — image catalogue

Defines all supported images with their build configuration (Packer template, answer files, product keys) and runtime configuration (whether to search for updates, capture idle state, etc.). ISO `source:` fields are intentionally left `null` — fill them in your local `config.yaml`.

### neogit credentials

osw-builder uses neogit to write the graph to Neo4j and the file contents to object storage. Create `~/.secrets.toml` with at least the Neo4j connection:

```toml
[default]
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "your-password"
# Object storage. neogit defaults to local filesystem storage, so MinIO is
# optional. Add these only if you point neogit at a MinIO/S3 backend.
MINIO_URL = "http://localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
```

---

## Usage

```bash
# Full pipeline: build image, capture to Neo4j, search and install updates
osw-builder capture_os win10-22h2-19045.2006

# Build and capture only — skip update search
osw-builder capture_os win10-22h2-19045.2006 --search-updates=false

# Build only — no Neo4j capture at all
osw-builder capture_os ubuntu-22.04 --skip-neogit

# Pass extra Packer variables
osw-builder capture_os ubuntu-22.04 --var cpus=4 --var memory=4096

# Debug logging
osw-builder capture_os win10-22h2-19045.2006 -d
```

If the Vagrant box for the OS already exists, the build step is skipped and the pipeline goes straight to capture/updates.

---

## Architecture

```
ISO
 │
 ▼
image_builder        Packer runs inside a Docker container (ghcr.io/oswatcher/packer-templates)
 │                   and produces a .qcow2 image via QEMU.
 ▼
vagrant              The image is registered as a Vagrant/libvirt box and booted as a VM.
 │
 ▼
capture              libguestfs inspects the offline disk image and feeds filesystem/registry
 │                   trees into Neo4j via neogit (content-addressed Merkle trees).
 ▼
updates              The VM is booted, updates are searched (Windows Update API / apt),
 │                   each update is installed, the VM is snapshotted, and the snapshot
 ▼                   is captured to Neo4j.
Neo4j graph
```

### Modules

| Module | Role |
|--------|------|
| `image_builder` | Packer + Docker orchestration — builds VM images from ISOs |
| `capture` | libguestfs-based filesystem/registry capture into Neo4j |
| `updates` | OS update search and installation (Windows + Ubuntu) |
| `vagrant` | VM lifecycle: define, boot, snapshot, restore, destroy |
| `services` | Service detection within captured images |

---

## Development

```bash
# Format, lint, typecheck, and run tests in one shot
poetry run poe ccode

# Individual steps
poetry run poe fmt          # black
poetry run poe lint         # flake8 + isort
poetry run poe typecheck    # mypy
poetry run poe unit_test    # pytest with coverage
```

---

## Supported images

See `osw_builder/default_settings.yaml` for the full catalogue. Highlights:

- **Windows**: XP SP3, 7, 8, 10 (1507 → 22H2), 11 (21H2 → 25H2)
- **Ubuntu**: 6.10 (Edgy Eft) → 25.04 (Quirky Quokka)

Legacy Windows 95/98/ME/2000 entries require pre-built Vagrant boxes (build your own).

---

## Documentation

The full documentation is organised with the [Divio system](https://docs.divio.com/documentation-system/) and published at <https://oswatcher.github.io/osw-builder/>:

| Section | What it covers |
|---------|----------------|
| [Tutorials](https://oswatcher.github.io/osw-builder/tutorials/index.html) | Hands-on: your first Ubuntu capture, end to end |
| [How-to guides](https://oswatcher.github.io/osw-builder/how-to/index.html) | Install system deps, provide ISOs, add a new image, build without capture |
| [Reference](https://oswatcher.github.io/osw-builder/reference/index.html) | CLI options, configuration schema, module API |
| [Explanation](https://oswatcher.github.io/osw-builder/explanation/index.html) | Pipeline design, image inheritance, response files |

## Related projects

- [neogit](https://github.com/OSWatcher/neogit) — the content-addressed Merkle-tree library that backs capture
- [packer-templates](https://github.com/OSWatcher/packer-templates) — the Packer build templates (a submodule of this repo)
- [oswatcher-deploy](https://github.com/OSWatcher/oswatcher-deploy) — full production stack (Neo4j, MinIO, API, frontend)
- [pywinupdate](https://github.com/OSWatcher/pywinupdate) — standalone WinRM/Ansible Windows Update CLI; independent from the OS-agnostic update orchestration in `osw_builder/updates/`, but scratches a similar itch

## License

Licensed under the Apache License 2.0.
