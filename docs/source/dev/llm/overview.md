# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

osw-builder is a tool for building and capturing Windows and Ubuntu OS images for OSWatcher. It automates the creation of virtual machine images with various Windows versions (from Windows 95 to Windows 11) and captures their filesystem states using neogit for analysis.

## Architecture

The project is structured into several key modules:

- **osw_builder/__main__.py**: Main entry point with CLI interface using docopt
- **osw_builder/build/**: Image building functionality using Packer and Docker
- **osw_builder/capture/**: Filesystem capture using libguestfs and neogit
- **osw_builder/vagrant/**: Vagrant VM management and libvirt integration
- **osw_builder/settings.py**: Configuration management using Dynaconf
- **osw_builder/packer-templates/**: Packer templates and configuration files

### Key Components

- **Image Building**: Uses Packer running in Docker containers to build Windows/Ubuntu images from ISO sources
- **VM Management**: Leverages Vagrant with libvirt provider for VM lifecycle management
- **Filesystem Capture**: Uses libguestfs to mount and analyze VM disk images, with neogit for version control
- **Configuration**: YAML-based configuration in `default_settings.yaml` with extensive Windows version definitions

## Development Commands

### Environment Setup
```bash
# Install dependencies
poetry install

# Initialize git submodules
git submodule update --init
```

### Code Quality
```bash
# Format code
poetry run poe fmt

# Check formatting
poetry run poe fmt-check

# Run linting
poetry run poe lint

# Type checking
poetry run poe typecheck

# Combined code checks
poetry run poe ccode

# Run tests
poetry run poe unit_test

# Build documentation
poetry run poe docs
```

### Main Operations
```bash
# Build and capture an OS image
osw-builder capture_os <os_name> [options]

# Example: Capture Windows 10 image
osw-builder capture_os win10-ts1-1507 --debug

# Use capture tool directly
osw-capture-tool [options]
```

## Configuration

- **osw_builder/default_settings.yaml**: Central configuration file defining all supported OS images, their sources, SHA1 checksums, and build parameters
- **Environment Variables**: Can be prefixed with `OSW_BUILDER_` to override settings
- **Packer Templates**: Located in `osw_builder/packer-templates/` with HCL2 configuration files

## Important Notes

- Requires libvirt, KVM, and Docker for image building
- Uses ghcr.io/oswatcher/packer-templates Docker image for Packer builds
- Expects GHCR_TOKEN environment variable for Docker registry access
- Images are built with specific Windows product keys defined in configuration
- Supports automated Windows Update installation and snapshot creation
- Integrates with neogit for filesystem state versioning

## Test Framework

Uses pytest for unit testing. Run tests with `poetry run poe unit_test`.