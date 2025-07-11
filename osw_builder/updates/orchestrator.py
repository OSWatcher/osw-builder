"""Orchestrator for OS-agnostic update management."""

from pathlib import Path
from typing import List

from .core import (
    OSType,
    Update,
    build_ansible_inventory,
    create_install_playbook,
    create_search_playbook,
    parse_ubuntu_updates,
    parse_windows_updates,
    validate_windows_install_result,
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


def install_update(vagrant_dir: Path, os_type: OSType, update: Update) -> bool:
    """Install a specific system update.

    Args:
        vagrant_dir: Path to Vagrant directory
        os_type: Operating system type
        update: Update object to install

    Returns:
        True if installation succeeded, False otherwise

    Raises:
        ValueError: If OS type is unsupported
        RuntimeError: If Ansible execution fails
    """
    # Get connection information
    connection_info = get_vagrant_connection_info(vagrant_dir, os_type)

    # Build Ansible inventory
    inventory = build_ansible_inventory(connection_info, os_type)

    # Create install playbook
    playbook_config = create_install_playbook(os_type, update)

    # Run Ansible playbook
    result = run_ansible_playbook(inventory, playbook_config.content, os_type)

    # Check if installation was successful
    if result["status"] != "successful":
        return False

    # For Windows, also validate that updates were actually installed
    if os_type == OSType.WINDOWS:
        return validate_windows_install_result(result["facts"])

    # For Ubuntu, assume success if Ansible succeeded
    return True
