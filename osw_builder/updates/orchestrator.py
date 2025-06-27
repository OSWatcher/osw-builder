"""Orchestrator for OS-agnostic update management."""

from pathlib import Path
from typing import List

from .core import (
    OSType,
    Update,
    build_ansible_inventory,
    create_search_playbook,
    parse_ubuntu_updates,
    parse_windows_updates,
)
from .io_layer import get_vagrant_connection_info, run_ansible_playbook


def search_updates(vagrant_dir: Path, os_type: OSType) -> List[Update]:
    """Search for available system updates.

    Args:
        vagrant_dir: Path to Vagrant directory
        os_type: Operating system type (already detected by caller)

    Returns:
        List of Update objects for available updates

    Raises:
        ValueError: If OS type is unsupported
        RuntimeError: If Ansible execution fails
    """
    # Get connection information
    connection_info = get_vagrant_connection_info(vagrant_dir, os_type)

    # Build Ansible inventory
    inventory = build_ansible_inventory(connection_info, os_type)

    # Create search playbook
    playbook_config = create_search_playbook(os_type)

    # Run Ansible playbook
    result = run_ansible_playbook(inventory, playbook_config.content, os_type)

    # Parse results based on OS type
    match os_type:
        case OSType.WINDOWS:
            return parse_windows_updates(result["facts"])
        case OSType.UBUNTU:
            return parse_ubuntu_updates(result["facts"])
        case _:
            raise ValueError(f"Unsupported OS type for parsing: {os_type}")
