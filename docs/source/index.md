# osw-builder

**osw-builder** builds VM images from ISOs and captures their filesystems into a Neo4j graph database. It is the data-ingestion engine behind [Grapheos](https://grapheos.cc) — a queryable graph of operating system evolution covering Windows 95 → 11 and Ubuntu 6.10 → 25.04.

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
