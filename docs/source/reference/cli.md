# CLI reference

osw-builder exposes a single command through the `osw-builder` entry point.

## `capture_os`

Build (if needed), register, capture, and optionally update an OS image.

```
osw-builder capture_os <os_name> [options] [--var <packer_args>...] [--before=<commit>]
```

### Argument

`<os_name>`
: Name of the OS to capture. Must match a `name:` field in the image catalogue (`default_settings.yaml`, possibly overridden by `config.yaml`).

### Options

```{list-table}
:header-rows: 1
:widths: 30 70

* - Option
  - Description
* - `-h`, `--help`
  - Display the usage message.
* - `-d`, `--debug`
  - Enable debug-level logging, including the resolved configuration block.
* - `-c`, `--connection=<URI>`
  - libvirt connection URI. Default: `qemu:///session`.
* - `--destroy`
  - Destroy the VM after the build completes.
* - `--updates=<ANSWER>`
  - Apply branch updates (`true`/`false`). Overrides the catalogue's `apply_updates`, unless the catalogue explicitly disables it.
* - `--search-updates=<ANSWER>`
  - Search for available updates (`true`/`false`). Overrides the catalogue's `search_updates`, unless explicitly disabled.
* - `--idle=<ANSWER>`
  - Capture the IDLE state (`true`/`false`). Overrides the catalogue's `idle`, unless explicitly disabled.
* - `--network`
  - Enable network access during the build.
* - `--skip-neogit`
  - Skip all neogit capture operations (no Neo4j/MinIO needed).
* - `--branch=<BRANCH_NAME>`
  - neogit branch to commit to.
* - `--before=<commit>`
  - Link the new build commit to an existing commit (used to chain captures).
* - `--var <packer_args>...`
  - Extra Packer variables, repeatable. Example: `--var cpus=4 --var memory=4096`.
```

### Override precedence

The `--updates`, `--search-updates`, and `--idle` flags follow one rule: **the CLI cannot re-enable something the catalogue explicitly disabled.** If an image sets `search_updates: false` in its `runtime_config`, passing `--search-updates=true` has no effect. This protects images that are known not to support a given phase.

### Examples

```bash
# Full pipeline
osw-builder capture_os win10-22h2-19045.2006

# Build and capture, no update search
osw-builder capture_os win10-22h2-19045.2006 --search-updates=false

# Build only, no capture
osw-builder capture_os ubuntu-22.04 --skip-neogit

# Extra Packer resources, debug logging
osw-builder capture_os ubuntu-22.04 --var cpus=4 -d
```
