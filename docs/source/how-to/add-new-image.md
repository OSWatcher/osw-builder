# Add a new image to the catalogue

When a new OS version is released, you add it to `default_settings.yaml`. Because the catalogue uses chronological inheritance, a new entry usually needs only a name and the fields that *differ* from the previous one.

If you have not met the inheritance model yet, read {doc}`../explanation/image-inheritance` first — it explains why the steps below work.

## Step 1 — Add the image definition

Under the top-level `images:` list, add an entry with a YAML anchor so it can be referenced in a branch:

```yaml
  - name: &ubuntu_25_10 "ubuntu-25.10"
    description: "Ubuntu 25.10 (Questing Quokka)"
    source: null  # provide your own ISO path in config.yaml
    checksum: "sha256:..."
    release_date: "2025-10"
```

The `release_date` (format `YYYY-MM`) is used to date the build commit in Neo4j, so the graph reflects when the OS actually shipped.

## Step 2 — Place it in a branch

Add a reference to the anchor in the appropriate branch under `branches:`. If the new version behaves identically to the previous one, a bare alias is enough — it inherits everything before it:

```yaml
branches:
  ubuntu-server:
    # ... earlier versions ...
    - *ubuntu_25_04
    - *ubuntu_25_10        # inherits all build/runtime config from above
```

## Step 3 — Override only what changed

If the new version needs a different setting — say update searching should be off, or a mirror flag changed — use the expanded form with just the delta:

```yaml
    - name: *ubuntu_25_10
      build_config:
        vars:
          old_release_mirrors: false
      runtime_config:
        search_updates: true
```

Everything you do *not* specify is inherited from earlier entries in the same branch.

## Step 4 — Test the resolution

Before running a full build, confirm the configuration resolves the way you expect. The cheapest check is a build without capture:

```bash
osw-builder capture_os ubuntu-25.10 --skip-neogit -d
```

Watch the debug output for the resolved config block — it prints the final `build_config` and `runtime_config` after inheritance.

```{important}
An image must appear in exactly one branch. If you accidentally reference the same anchor in two branches, config resolution raises an error.
```
