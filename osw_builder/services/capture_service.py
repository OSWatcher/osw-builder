"""Application service for OS capture orchestration"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from osw_builder.core.logic import (
    create_update_policy,
    create_vm_configuration,
    get_default_idle_timeout,
    should_skip_update,
    validate_os_name_exists,
)
from osw_builder.core.models import MachineState, UpdatePolicy


@dataclass(frozen=True)
class CaptureConfiguration:
    """Configuration for OS capture operation"""

    os_name: str
    box_name: str
    apply_updates: bool
    search_updates: bool
    idle: bool
    destroy: bool
    packer_args: List[str]
    before: Optional[str] = None


@dataclass(frozen=True)
class OSImageConfiguration:
    """OS image configuration from settings"""

    name: str
    template: Optional[str]
    varfile: Optional[str]
    description: str
    source: str
    extra_firstlogin_cmds: Optional[List[str]]
    network: bool = False


class CaptureService:
    """Service for orchestrating OS capture business logic"""

    def __init__(self, update_policy: UpdatePolicy):
        """Initialize with update policy from configuration"""
        self.update_policy = update_policy

    @classmethod
    def from_settings(cls, settings: Dict) -> "CaptureService":
        """Create service from settings configuration"""
        blacklisted_updates = settings.get("blacklisted_updates", [])
        update_policy = create_update_policy(blacklisted_updates)
        return cls(update_policy)

    def validate_os_configuration(self, os_name: str, os_configs: Dict[str, Dict]) -> OSImageConfiguration:
        """Validate OS name exists and return configuration"""
        if not validate_os_name_exists(os_name, os_configs):
            raise RuntimeError(f"Could not find OS name: {os_name}")

        entry = os_configs[os_name]
        return OSImageConfiguration(
            name=os_name,
            template=entry.get("template"),
            varfile=entry.get("varfile"),
            description=entry["description"],
            source=entry["source"],
            extra_firstlogin_cmds=entry.get("extra_firstlogin_cmds"),
            network=entry.get("network", False),
        )

    def should_skip_windows_update(self, update_kb: str) -> bool:
        """Determine if a Windows update should be skipped based on policy"""
        return should_skip_update(update_kb, self.update_policy)

    def create_idle_vm_configuration(self, box_name: str) -> tuple[int, str]:
        """Create VM configuration for idle state capture and return timeout info"""
        idle_timeout = get_default_idle_timeout() * 2  # 10 minutes (300s * 2)
        vm_config = create_vm_configuration(box_name, MachineState.RUNNING, idle_timeout)
        return vm_config.idle_timeout_seconds, f"Waiting for {vm_config.idle_timeout_seconds} seconds"

    def should_apply_updates(self, config: CaptureConfiguration, os_config: OSImageConfiguration) -> bool:
        """Determine if updates should be applied based on configuration"""
        # Check if updates are enabled in capture config or OS config
        apply_updates = getattr(os_config, "apply_updates", config.apply_updates)
        return apply_updates

    def should_search_updates(self, config: CaptureConfiguration, os_config: OSImageConfiguration) -> bool:
        """Determine if update search should be performed"""
        # OS config can override the capture config
        search_updates = getattr(os_config, "search_updates", config.search_updates)
        return search_updates

    def should_capture_idle(self, config: CaptureConfiguration, os_config: OSImageConfiguration) -> bool:
        """Determine if idle state should be captured"""
        # OS config can override the capture config
        idle = getattr(os_config, "idle", config.idle)
        return idle
