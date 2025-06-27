"""Pure functions for OS-agnostic update management."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, NamedTuple, Optional


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