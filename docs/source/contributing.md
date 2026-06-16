# Contributing

This page covers the developer workflow for osw-builder itself. For using the tool, see the {doc}`tutorials <tutorials/index>` and {doc}`how-to guides <how-to/index>`.

## Setup

```bash
git clone --recurse-submodules https://github.com/OSWatcher/osw-builder.git
cd osw-builder
poetry install
```

## Code quality gate

Run the full quality suite before every commit. CI runs the same checks:

```bash
poetry run poe ccode
```

This is a meta-task that runs, in order:

```bash
poetry run poe fmt          # black (line length 120)
poetry run poe lint         # flake8 + isort
poetry run poe typecheck    # mypy
poetry run poe unit_test    # pytest with coverage
```

Do not commit code that fails any of these.

## Testing approach

The codebase favours **pure functions plus context managers** so that business logic can be unit-tested without Docker, libvirt, or a network:

- **Pure functions** (e.g. `build_packer_cmdline`) are tested directly, no mocking.
- **Context managers** (e.g. `docker_packer_runner`) are tested with `unittest.mock` standing in for the Docker client.
- **Parametrised tests** cover the different OS configurations.

When adding a feature, extract the logic into a pure function first, keep the orchestration thin, and add the unit test immediately.

## Building the documentation

```bash
poetry install --with docs
poetry run poe docs          # builds docs/source -> docs/build
```

Open `docs/build/index.html` in a browser. The documentation follows the [Divio system](https://docs.divio.com/documentation-system/) — when adding a page, decide first whether it is a tutorial, how-to, reference, or explanation, and place it accordingly.

## Documentation deployment

The docs are built and published to GitHub Pages automatically on every push to `master` by the `.github/workflows/docs.yml` workflow.
