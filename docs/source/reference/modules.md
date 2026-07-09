# Module reference

osw-builder is organised into focused packages under `osw_builder/`.

## `image_builder`

Packer + Docker orchestration. Builds a `.qcow2` image from an ISO by running Packer inside the `ghcr.io/oswatcher/packer-templates` container.

Designed around pure functions plus context managers for testability:

- `build_packer_cmdline(template, packer_args)` — assemble Packer CLI arguments
- `build_docker_volumes(...)` — compute the container volume mounts
- `build_docker_config(volumes, cmdline, network)` — assemble the container config
- `docker_packer_runner(docker_config, network)` — context manager owning the container lifecycle with guaranteed cleanup
- `build_image_with_inheritance(os_name, entry, config, packer_args)` — high-level entry used by the CLI

## `capture`

libguestfs-based capture into Neo4j via neogit. Reads the offline disk image (no booting required) and writes the filesystem and registry as content-addressed Merkle trees.

- `capture_neogit(qcow_path, name, ...)` — capture one snapshot as a neogit commit
- `create_branch(name, commit)` — create the neogit branch for an OS

## `updates`

OS-agnostic update search and installation. Dispatches on OS type detected from the Packer template.

- `detect_os_type(template)` → `OSType.WINDOWS` | `OSType.UBUNTU`
- `search_updates(vagrant_dir, os_type)` — enumerate available updates (Windows Update API / `apt`)
- `install_update(vagrant_dir, os_type, update)` — install one update inside the booted VM

## `vagrant`

VM lifecycle over libvirt: define, boot, snapshot, restore, destroy. Wraps Vagrant and `virsh`.

Key helpers: `box_exists`, `box_add`, `prepare_vagrantfile`, `define_vm`, `snapshot_save`/`snapshot_restore`/`snapshot_list`, `up_down_ctxt`, `ensure_destroyed`, `pool_refresh`.

## `services`

Service detection within captured images.

## `settings`

Dynaconf-backed configuration loading and the inheritance resolver:

- `settings` — the loaded configuration object
- `resolve_image_config(os_name)` → `ResolvedConfig` — apply chronological inheritance
- `BuildConfig`, `RuntimeConfig`, `ResolvedConfig` — the strongly-typed resolved structures

## Entry point

`osw_builder/__main__.py` parses the CLI with docopt and dispatches to `capture_os`. The console script is registered in `pyproject.toml` as `osw-builder`.
