# Configuration reference

osw-builder is configured through YAML settings, loaded by [Dynaconf](https://www.dynaconf.com/). Secrets (Neo4j/MinIO credentials) are kept separately.

## Files

`osw_builder/default_settings.yaml`
: The shipped image catalogue and global defaults. Tracked in git. ISO `source:` fields are `null` by design.

`config.yaml`
: Your local overrides, not committed. Any key here overrides the matching key in the defaults.

`~/.secrets.toml`
: neogit credentials (Neo4j, MinIO). Read by neogit, not committed.

Environment variables prefixed with `OSW_BUILDER_` also override settings (Dynaconf convention).

## Top-level keys

```{list-table}
:header-rows: 1
:widths: 25 75

* - Key
  - Meaning
* - `keys`
  - Reusable Windows product keys, referenced by YAML anchors.
* - `image_names`
  - Reusable Windows edition names (e.g. "Windows 10 Pro").
* - `template` / `varfile`
  - Anchors for Packer template and varfile filenames.
* - `extra_firstlogin_cmds`
  - Anchored list of Windows first-login registry commands.
* - `remove_domain`
  - Whether to remove the libvirt domain after running tools. Default `false`.
* - `storage_pool`
  - libvirt storage pool name. Default `"default"`.
* - `skip_neogit`
  - Global default for skipping capture. Default `false`.
* - `logging`
  - Logging configuration (the `format` string).
* - `images`
  - The image catalogue — a flat list of every OS definition.
* - `branches`
  - Groups images into inheritance chains (`windows`, `ubuntu-server`).
```

## Image entry

Each item under `images:` describes one OS:

```yaml
- name: &win10_22h2 "win10-22h2-19045.2006"
  description: "Windows 10 22H2 (March 2022 Update, 19045)"
  source: null            # ISO path/URL — provide in config.yaml
  checksum: "sha1:..."    # verification reference, kept even when source is null
  release_date: "2022-10" # YYYY-MM, used to date the build commit in Neo4j
```

## `build_config`

Controls how the image is built with Packer. Resolved through inheritance (see {doc}`../explanation/image-inheritance`).

```{list-table}
:header-rows: 1
:widths: 30 70

* - Field
  - Meaning
* - `template`
  - Packer template filename (e.g. `windows.pkr.hcl`, `ubuntu.pkr.hcl`).
* - `varfiles`
  - List of HCL varfiles. **Replaces** (does not extend) inherited value.
* - `vars`
  - Dict of Packer variables. **Merged** key-by-key with inherited values.
* - `network`
  - Whether the build needs network access. Default `false`.
* - `extra_firstlogin_cmds`
  - Windows-only list of first-login commands.
* - `key`
  - Windows product key.
* - `image_name`
  - Windows edition name selected from the ISO.
```

## `runtime_config`

Controls what happens after the build.

```{list-table}
:header-rows: 1
:widths: 25 15 60

* - Field
  - Default
  - Meaning
* - `search_updates`
  - `true`
  - Search for OS updates after capture.
* - `idle`
  - `true`
  - Capture an IDLE snapshot (VM left running 10 minutes).
* - `apply_updates`
  - `true`
  - Install the updates that were found.
```

```{note}
A `runtime_config` value of `false` is "sticky": once an image in a branch disables a phase, neither later inheritance nor a CLI flag can re-enable it. See {doc}`cli` → override precedence.
```

## `branches`

A branch is an ordered list that defines an inheritance chain. Entries are processed top to bottom; each one inherits the accumulated configuration of everything above it. An image must appear in exactly one branch. The two shipped branches are `windows` and `ubuntu-server`.
