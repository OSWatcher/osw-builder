# LLM Specs Overview

This document summarizes the architecture and main features of **osw-builder**. It serves as reference material for LLMs and developers when translating natural language feature requests into concrete changes.

## Project Purpose

* Automate the creation and capture of Windows virtual machine images.
* Provide a command line interface for building images, managing Vagrant boxes, and capturing filesystem snapshots.
* Maintain a versioned collection of images using a Git-like repository (Neogit).

## Command Line Interface

The entry point is `osw-builder` (`osw_builder.__main__`). The primary subcommand is:

```
osw-builder capture_os <os_name> [options] [--var <packer_args>...] [--before=<commit>]
```

Key options:

* `--destroy` – remove the VM after capture.
* `--updates` – whether to apply branch updates.
* `--search-updates` – perform Windows Update searches.
* `--idle` – capture an *IDLE* snapshot before updates.
* `--var` – extra arguments passed to Packer.

## Build Process

Module: `osw_builder.build.build`.

1. Validate the image source and SHA‑1 checksum (`validate_source_and_compute_sha1`).
2. Update the Packer varfile with the ISO URL and checksum (`update_varfile`).
3. Configure Autounattend files through the `Autounattend` helper (product keys, image names, first‑login commands).
4. Run Packer inside a Docker container (`run_packer`). The container image is `ghcr.io/oswatcher/packer-templates:latest`.
5. Produce a `.box` file under `packer-templates/output`.

## Capture Process

Module: `osw_builder.capture.capture`.

1. Use `LibguestFSMnt` to mount qcow2 images locally with libguestfs.
2. Commit files into Neogit using `capture_neogit`.
3. Create branches per OS with `create_branch` and store snapshots with unique descriptions.
4. Optionally search for Windows Updates and take additional snapshots for each installed update.

## Vagrant and Libvirt Integration

Module: `osw_builder.vagrant.vagrant`.

* Wrapper functions for `vagrant` commands: `box_add`, `status`, `snapshot_save`, `snapshot_restore`, etc.
* Parsing utilities for `qemu-img snapshot -l`, `vagrant snapshot list`, and `vagrant winrm-config`.
* Helpers to define domains, set EFI loaders, and manage snapshot metadata in libvirt (`snapshot_libvirt_define`).
* `ctxt.prepare_vagrantfile` creates temporary Vagrant environments under the user data directory.

## Configuration

Settings are defined in `osw_builder/default_settings.yaml` and loaded via Dynaconf (`settings.py`). The YAML lists dozens of Windows versions with:

* `name` and `description`.
* Download `source` URLs and `sha1` checksums.
* Optional product keys, image names, extra first‑login commands, and template references.
* `branches` section defines the capture order for each branch (e.g. the `master` branch captures all Windows versions from Windows 95 to Windows 11).

## Snapshot Representation

Snapshots are represented by the `Snapshot` dataclass (`snapshot.py`). The snapshot name and description are encoded into a QEMU tag using base64 so they can be stored as internal snapshots.

## Automation and Testing

* Dockerfile and GitHub workflows build the project and automate captures.
* Development tasks (`poetry run poe <task>`) include formatting (`black`), linting (`flake8`/`isort`), type checking (`mypy`), unit testing (`pytest`), and documentation build (`sphinx-build`).
* Tests cover utility helpers such as SHA‑1 computation and snapshot parsing.

## Adding Features

1. Describe the desired behaviour in natural language.
2. Locate the relevant modules (build, capture, vagrant, or settings).
3. Update `default_settings.yaml` when new images or branches are needed.
4. Write unit tests under `osw_builder/*/test_*.py` for new logic.
5. Document the new functionality here so future agents can understand it.

This overview enables LLMs and AI agents to derive specifications and code changes consistently across the project.
