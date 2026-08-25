# osw-builder

**osw-builder** turns an OS installer ISO into a queryable graph snapshot. It builds a VM image with Packer, captures the resulting filesystem and registry into a Neo4j graph as content-addressed Merkle trees, and — optionally — installs OS updates one by one, capturing the state after each. The whole pipeline runs unattended.

It feeds a queryable graph of operating system evolution covering Windows 95 → 11 and Ubuntu 6.10 → 25.04. Because every snapshot lives in the same graph, you can ask questions an ordinary disk image never answers — *which files changed between two Windows builds, which registry keys a given update touched, on which OS versions a symbol first appeared.*

```
ISO ─▶ image_builder ─▶ vagrant ─▶ capture ─▶ updates ─▶ Neo4j graph
       (Packer/Docker)  (libvirt)  (libguestfs)  (apt /
                                                  Windows Update)
```

**New here?** Jump straight to the {doc}`first-capture tutorial <tutorials/first-capture>` — it takes you from an empty machine to a captured Ubuntu image with one Neo4j container and no product keys.

This documentation is organised according to the [Divio documentation system](https://docs.divio.com/documentation-system/) — four distinct kinds of documentation that serve different needs:

::::{grid} 2
:gutter: 3

:::{grid-item-card} 🎓 Tutorials
:link: tutorials/index
:link-type: doc

**Learning-oriented.** Start here if you are new. A hands-on lesson that takes you from nothing to your first captured OS.
:::

:::{grid-item-card} 🔧 How-to guides
:link: how-to/index
:link-type: doc

**Problem-oriented.** Recipes for specific tasks: installing dependencies, providing ISOs, adding a new image to the catalogue.
:::

:::{grid-item-card} 📖 Reference
:link: reference/index
:link-type: doc

**Information-oriented.** Dry, complete descriptions of the CLI, configuration schema, and modules.
:::

:::{grid-item-card} 💡 Explanation
:link: explanation/index
:link-type: doc

**Understanding-oriented.** Discussion of how the pipeline works and why it is designed the way it is.
:::

::::

```{toctree}
:hidden:
:caption: Documentation

tutorials/index
how-to/index
reference/index
explanation/index
```

```{toctree}
:hidden:
:caption: Project

contributing
```
