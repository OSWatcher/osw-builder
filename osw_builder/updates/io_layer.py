"""I/O layer functions for update management."""

from pathlib import Path
from typing import Any, Dict, List

from ansible_runner import Runner

from ..vagrant.vagrant import ssh_config, winrm_config
from .core import ConnectionInfo, OSType


def get_vagrant_connection_info(vagrant_dir: Path, os_type: OSType) -> ConnectionInfo:
    """Get connection info from Vagrant for the specified OS type.
    
    Args:
        vagrant_dir: Path to Vagrant directory
        os_type: Operating system type
        
    Returns:
        ConnectionInfo with connection details
        
    Raises:
        ValueError: If OS type is not supported
    """
    match os_type:
        case OSType.WINDOWS:
            config = winrm_config(vagrant_dir)
            auth_data: Dict[str, str] = {"password": config.Password}
            return ConnectionInfo(
                host=config.Host,
                hostname=config.HostName,
                user=config.User,
                port=config.Port,
                auth_data=auth_data
            )
        case OSType.UBUNTU:
            config = ssh_config(vagrant_dir)
            auth_data = {"identity_file": config.IdentityFile}
            return ConnectionInfo(
                host=config.Host,
                hostname=config.HostName,
                user=config.User,
                port=config.Port,
                auth_data=auth_data
            )
        case OSType.UNKNOWN:
            raise ValueError(f"Cannot get connection info for unknown OS type")
        case _:
            raise ValueError(f"Unsupported OS type: {os_type}")


def run_ansible_playbook(inventory_dict: Dict[str, Any], playbook_content: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Run Ansible playbook using ansible-runner with direct data structures.
    
    Args:
        inventory_dict: Ansible inventory as dictionary
        playbook_content: Playbook content as list of plays
        
    Returns:
        Dictionary containing execution results and facts
        
    Raises:
        RuntimeError: If playbook execution fails
    """
    runner = Runner(
        inventory=inventory_dict,
        playbook=playbook_content,
        quiet=True
    )
    
    result = runner.run()
    
    if result.status != "successful":
        raise RuntimeError(f"Ansible playbook failed with status: {result.status}")
    
    # Extract facts and results from the run
    facts = {}
    if result.get_fact_cache():
        facts.update(result.get_fact_cache())
    
    return {
        "status": result.status,
        "facts": facts,
        "stats": result.stats,
        "rc": result.rc
    }