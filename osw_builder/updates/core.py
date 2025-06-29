"""Pure functions for OS-agnostic update management."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, List, NamedTuple, Optional


class OSType(Enum):
    """Supported operating system types."""
    WINDOWS = auto()
    UBUNTU = auto()
    UNKNOWN = auto()


class ConnectionInfo(NamedTuple):
    """Connection information for remote systems."""
    host: str
    hostname: str
    user: str
    port: int
    auth_data: Dict[str, str]


@dataclass(frozen=True)
class PlaybookConfig:
    """Configuration for an Ansible playbook."""
    name: str
    content: List[Dict[str, Any]]
    

@dataclass(frozen=True)
class Update:
    """Represents an OS update."""
    id: str
    name: str
    description: str
    os_type: OSType
    severity: Optional[str] = None


def detect_os_type(template: str) -> OSType:
    """Detect OS type from template file name.
    
    Args:
        template: Template file name (e.g., "ubuntu.pkr.hcl", "windows.pkr.hcl")
        
    Returns:
        OSType enum value
    """
    template_lower = template.lower()
    
    match template_lower:
        case template_lower if "ubuntu" in template_lower:
            return OSType.UBUNTU
        case template_lower if "windows" in template_lower or "win" in template_lower:
            return OSType.WINDOWS
        case _:
            return OSType.UNKNOWN


def build_ansible_inventory(connection_info: ConnectionInfo, os_type: OSType) -> Dict[str, Any]:
    """Build Ansible inventory configuration.
    
    Args:
        connection_info: Connection details for the target system
        os_type: Operating system type
        
    Returns:
        Dictionary containing Ansible inventory configuration
    """
    base_config: Dict[str, Any] = {
        "ansible_host": connection_info.hostname,
        "ansible_user": connection_info.user,
        "ansible_port": connection_info.port,
    }
    
    match os_type:
        case OSType.WINDOWS:
            base_config.update({
                "ansible_connection": "winrm",
                "ansible_winrm_transport": "basic",
                "ansible_winrm_server_cert_validation": "ignore",
                "ansible_password": connection_info.auth_data.get("password", ""),
            })
        case OSType.UBUNTU:
            base_config.update({
                "ansible_connection": "ssh",
                "ansible_ssh_private_key_file": connection_info.auth_data.get("identity_file", ""),
            })
        case OSType.UNKNOWN:
            pass
    
    return {
        "all": {
            "hosts": {
                connection_info.host: base_config
            }
        }
    }


def create_search_playbook(os_type: OSType) -> PlaybookConfig:
    """Create Ansible playbook for searching system updates.
    
    Args:
        os_type: Operating system type
        
    Returns:
        PlaybookConfig with OS-specific update search playbook
        
    Raises:
        ValueError: If OS type is not supported
    """
    match os_type:
        case OSType.WINDOWS:
            content = [{
                "hosts": "all",
                "tasks": [{
                    "name": "Search for Windows updates",
                    "win_updates": {
                        "state": "searched",
                        "category_names": [
                            "CriticalUpdates",
                            "SecurityUpdates", 
                            "UpdateRollups"
                        ]
                    },
                    "register": "windows_updates"
                }]
            }]
            return PlaybookConfig(name="windows_search.yml", content=content)
            
        case OSType.UBUNTU:
            content = [{
                "hosts": "all",
                "tasks": [
                    {
                        "name": "Update apt cache",
                        "apt": {"update_cache": True},
                        "become": True
                    },
                    {
                        "name": "Check for upgradable packages", 
                        "shell": "apt list --upgradable 2>/dev/null | grep -v '^Listing' | wc -l",
                        "register": "upgradable_count"
                    },
                    {
                        "name": "Get upgradable package list",
                        "shell": "apt list --upgradable 2>/dev/null | grep -v '^Listing'",
                        "register": "upgradable_packages",
                        "when": "upgradable_count.stdout|int > 0"
                    }
                ]
            }]
            return PlaybookConfig(name="ubuntu_search.yml", content=content)
            
        case OSType.UNKNOWN:
            raise ValueError("Cannot create search playbook for unknown OS type")
        case _:
            raise ValueError(f"Unsupported OS type: {os_type}")