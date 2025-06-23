"""Business models for OS Builder"""

import base64
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class OSImageStatus(Enum):
    """Status of an OS image throughout its lifecycle"""

    NOT_BUILT = "not_built"
    BUILDING = "building"
    BUILT = "built"
    CAPTURED = "captured"
    FAILED = "failed"


class MachineState(Enum):
    """State of a virtual machine"""

    NOT_CREATED = "not_created"
    SHUTOFF = "shutoff"
    RUNNING = "running"


@dataclass(frozen=True)
class OSImage:
    """Represents an OS image configuration and metadata"""

    name: str
    source: str
    sha1: Optional[str]
    key: Optional[str]
    image_name: Optional[str]
    status: OSImageStatus = OSImageStatus.NOT_BUILT


@dataclass(frozen=True)
class UpdatePolicy:
    """Policy for managing Windows updates during image building"""

    blacklisted_updates: List[str]

    def is_update_blacklisted(self, update_id: str) -> bool:
        """Check if a Windows update is blacklisted"""
        return update_id in self.blacklisted_updates


@dataclass(frozen=True)
class SnapshotMetadata:
    """Metadata for VM snapshots with encoded descriptions"""

    name: str
    encoded_description: str

    @classmethod
    def create(cls, name: str, description: str) -> "SnapshotMetadata":
        """Create snapshot metadata with base64 encoded description"""
        encoded_desc = base64.b64encode(description.encode()).decode()
        return cls(name=name, encoded_description=encoded_desc)

    def get_description(self) -> str:
        """Decode and return the original description"""
        return base64.b64decode(self.encoded_description).decode()


@dataclass(frozen=True)
class VMConfiguration:
    """Configuration for a virtual machine"""

    box_name: str
    machine_state: MachineState = MachineState.NOT_CREATED
    idle_timeout_seconds: int = 300

    def is_ready_for_capture(self) -> bool:
        """Check if VM is ready for filesystem capture"""
        return self.machine_state == MachineState.RUNNING
