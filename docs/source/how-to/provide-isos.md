# Provide ISO sources

The image catalogue ships with every `source:` field set to `null`. You supply your own ISOs, either by editing a local `config.yaml` (recommended) or by pointing `source:` at a path or URL.

## Override an image in `config.yaml`

Create `config.yaml` in the project root. Only the fields you set are overridden; everything else is inherited from `default_settings.yaml`:

```yaml
images:
  - name: win10-22h2-19045.2006
    source: /data/isos/Win10_22H2_English_x64.iso

  - name: ubuntu-22.04
    source: https://releases.ubuntu.com/jammy/ubuntu-22.04.4-live-server-amd64.iso
```

A `source:` can be:

- a **local path** — `/data/isos/Win10_22H2.iso`
- an **HTTP(S) URL** — Packer downloads it and caches it

## Verify against the shipped checksum

Each catalogue entry keeps a `checksum:` field even though `source:` is null. This lets you confirm the ISO you obtained matches the build the catalogue was tuned against:

```bash
sha1sum /data/isos/Win10_22H2_English_x64.iso
# compare against the checksum: field for that image in default_settings.yaml
```

If your ISO has a different checksum, the build may still work, but answer-file timing and update behaviour were validated against the original — expect to debug.

## Where to obtain ISOs legally

```{list-table}
:header-rows: 1

* - OS
  - Source
* - Windows 10 / 11
  - [Microsoft software download](https://www.microsoft.com/software-download/) and the [Evaluation Center](https://www.microsoft.com/en-us/evalcenter/)
* - Windows XP / 7 / 8
  - [Internet Archive](https://archive.org) — search for the specific build string
* - Ubuntu (current)
  - <https://ubuntu.com/download/server>
* - Ubuntu (EOL)
  - <https://old-releases.ubuntu.com/releases/>
```

## Legacy Windows boxes

The `win95`, `win98`, `winME`, and `win2000` entries are not ISO-based — they expect a pre-built Vagrant box, because installing these from ISO is impractical to automate. You must build your own box and point `source:` at it. This is an advanced, manual workflow outside the normal pipeline.
