# How the pipeline works

osw-builder turns an ISO into a queryable graph snapshot. This page explains the journey of an OS through the pipeline and the role each stage plays.

## The pipeline at a glance

```
ISO
 │
 ▼  image_builder — Packer runs inside a Docker container and produces a .qcow2
 ▼  vagrant       — the image becomes a Vagrant/libvirt box and is booted as a VM
 ▼  capture       — libguestfs reads the offline disk; neogit writes it to Neo4j
 ▼  updates       — the VM is booted, updates installed, each one captured
Neo4j graph
```

Each stage is a distinct module, and each stage is *resumable* in the sense that if its output already exists (a box, a snapshot, a commit), the pipeline reuses it instead of redoing the work.

## Why build inside Docker

Packer, its plugins, and the QEMU toolchain are pinned inside the `ghcr.io/oswatcher/packer-templates` image. Running Packer in a container means contributors do not install Packer locally, and every build uses the same template versions. The container produces a `.qcow2` disk image, which is the only artefact that leaves the build stage.

## Why capture offline with libguestfs

The capture stage does **not** boot the VM to read its filesystem. It uses libguestfs to mount the `.qcow2` disk image offline. This is faster, deterministic, and avoids a running OS mutating its own state while being read. The exception is the *updates* stage, which must boot the VM because installing updates is inherently an online operation.

## What lands in Neo4j

The captured filesystem is stored as a **content-addressed Merkle tree**, the same idea git uses for its object store. The shape is:

```cypher
(Branch)-[:TRACKS_COMMIT]->(Commit)
(Commit)-[:OWNS_FILESYSTEM]->(Tree)
(Tree)-[:HAS_CHILD_TREE|HAS_CHILD_BLOB]->(Tree|Blob)
```

- A **Branch** is one OS line (e.g. `ubuntu-22.04`).
- A **Commit** is one snapshot in time — the build, an idle state, or a post-update state.
- A **Tree** is a directory; a **Blob** is a file's content.

Because nodes are content-addressed, two snapshots that share an identical subtree point at the *same* nodes. This is what makes diffing two OS versions cheap: unchanged subtrees are literally the same graph nodes, so a diff only has to walk where the hashes differ. The actual file bytes live in MinIO, keyed by content hash; Neo4j holds the structure.

## Why snapshots and updates are chained

A single `capture_os` run can produce several commits: the build, an idle capture, and one commit per installed update. They are chained with the `--before` relationship so the graph records the *order* in which states occurred. This turns the database into a timeline you can query — "what changed when update X was installed" becomes a graph traversal.

## Where to go deeper

- The configuration model that decides *how* each image is built: {doc}`image-inheritance`
- How unattended installs are driven per-OS: {doc}`response-files`
- The downstream graph and queries: the [neogit](https://github.com/OSWatcher/neogit) project.
