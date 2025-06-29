"""Pure functions for OS-agnostic update management."""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional


class OSType(Enum):
    """Supported operating system types."""
    WINDOWS = auto()
    UBUNTU = auto()
    UNKNOWN = auto()


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