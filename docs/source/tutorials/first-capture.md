# Your first capture: build and capture Ubuntu

In this tutorial you will take a single Ubuntu ISO and turn it into a queryable snapshot in a Neo4j graph. By the end you will have run the full osw-builder pipeline once, end to end, and seen the captured filesystem in the Neo4j browser.

This is a learning exercise. We deliberately pick a small, modern Ubuntu image because it builds without product keys and downloads quickly.

## What you will need

- A Linux host with virtualisation enabled (KVM)
- About 20 GB of free disk and one to two hours of wall-clock time (most of it unattended)
- The system dependencies installed — if you have not done this yet, follow {doc}`../how-to/install-system-deps` first and come back

## Step 1 — Get the code

```bash
git clone --recurse-submodules https://github.com/OSWatcher/osw-builder.git
cd osw-builder
poetry install
```

The `--recurse-submodules` flag matters: the Packer templates live in a git submodule. If you forgot it, run `git submodule update --init` now.

## Step 2 — Start Neo4j and MinIO

osw-builder writes captured filesystems into Neo4j (the graph) and MinIO (the file contents). The quickest way to get both is the docker-compose stack shipped with [neogit](https://github.com/OSWatcher/neogit). Start it, then confirm you can reach the Neo4j browser at <http://localhost:7474>.

## Step 3 — Tell neogit where the databases are

Create `~/.secrets.toml` so osw-builder can authenticate against Neo4j and MinIO:

```toml
[default]
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "your-password"
MINIO_URL = "http://localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
```

## Step 4 — Point an image at an ISO

The image catalogue in `osw_builder/default_settings.yaml` ships with every `source:` field set to `null` — you supply your own ISO. Create a `config.yaml` in the project root that overrides just the one image we care about:

```yaml
images:
  - name: ubuntu-22.04
    source: https://releases.ubuntu.com/jammy/ubuntu-22.04.4-live-server-amd64.iso
```

```{tip}
You can point `source:` at a local file path instead of a URL if you have already downloaded the ISO — this saves the download on repeated runs.
```

## Step 5 — Run the pipeline

For your first run, skip the update search so the pipeline finishes faster and has fewer moving parts:

```bash
osw-builder capture_os ubuntu-22.04 --search-updates=false -d
```

The `-d` flag turns on debug logging so you can watch each phase. You will see, in order:

1. **Build** — Packer boots the ISO inside a Docker container and produces a `.qcow2` image (this is the slow part)
2. **Box add** — the image is registered as a Vagrant/libvirt box
3. **Capture** — libguestfs reads the offline disk and writes the filesystem tree into Neo4j

## Step 6 — See what you captured

Open the Neo4j browser at <http://localhost:7474> and run:

```cypher
MATCH (b:Branch {name: "ubuntu-22.04"})-[:TRACKS_COMMIT]->(c:Commit)
RETURN b, c
```

You should see a `Branch` node for `ubuntu-22.04` pointing at a `Commit`. That commit owns the entire captured filesystem as a tree of content-addressed nodes. To peek at the root of the filesystem:

```cypher
MATCH (c:Commit)-[:OWNS_FILESYSTEM]->(root:Tree)-[:HAS_CHILD_TREE]->(child)
RETURN root, child
LIMIT 25
```

## What you have learned

You ran the four phases of osw-builder — build, register, capture — and produced a real OS snapshot in a graph database. You also met the two configuration files you will use constantly: `config.yaml` for your local overrides and `default_settings.yaml` for the shared catalogue.

## Where to go next

- To understand the graph structure you just queried, read {doc}`../explanation/architecture`.
- To capture a Windows image (which needs product keys and answer files), the same command works — just provide the ISO. See {doc}`../how-to/provide-isos`.
- To add a brand-new OS version to the catalogue, follow {doc}`../how-to/add-new-image`.
