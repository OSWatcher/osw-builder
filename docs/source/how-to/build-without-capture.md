# Build an image without capturing

Sometimes you want the VM image but not the Neo4j capture — for example when testing a Packer template change, or when you do not have Neo4j and MinIO running. Use `--skip-neogit`.

## Skip the capture step

```bash
osw-builder capture_os ubuntu-22.04 --skip-neogit
```

This runs the build and registers the Vagrant box, but performs no neogit operations. You do not need `~/.secrets.toml` or a running Neo4j/MinIO for this.

## Combine with other flags

Skip capture but still exercise the update search and install logic:

```bash
osw-builder capture_os ubuntu-22.04 --skip-neogit --search-updates=true
```

Skip capture and pass extra Packer variables (for example, more CPUs for a faster build):

```bash
osw-builder capture_os ubuntu-22.04 --skip-neogit --var cpus=4 --var memory=4096
```

## When the box already exists

If a Vagrant box for the OS is already registered, the build phase is skipped entirely and osw-builder proceeds to the later phases. To force a rebuild, remove the existing box first:

```bash
vagrant box remove ubuntu-22.04 --provider libvirt
```

```{seealso}
The flag is named `--skip-neogit` for historical reasons. See the configuration reference for the full flag list: {doc}`../reference/cli`.
```
