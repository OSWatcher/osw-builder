# osw-builder

A pipeline tool that builds VM images from ISOs and captures their filesystems into a Neo4j graph database. It is the data-ingestion engine behind [Grapheos](https://grapheos.cc) — a queryable graph of operating system evolution covering Windows 95 → 11 and Ubuntu 6.10 → 25.04.

**What it does, end to end:**

1. Build a VM image from an ISO using Packer (runs inside Docker, no local Packer install needed)
2. Register the image with Vagrant/libvirt
3. Capture the filesystem and registry into Neo4j via [neogit](https://github.com/OSWatcher/neogit)
4. Optionally search for and install OS updates, snapshotting and capturing after each one

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

**Infrastructure** (see [neogit](https://github.com/OSWatcher/neogit) for setup)

- Neo4j 5.x — graph database where OS snapshots are stored
- MinIO (or any S3-compatible store) — object storage for blob data

---

## Installation

```bash
git clone --recurse-submodules https://github.com/OSWatcher/osw-builder.git
cd osw-builder
poetry install
```

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

osw-builder uses neogit to write to Neo4j and MinIO. Create `~/.secrets.toml` with:

```toml
[default]
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "your-password"
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
