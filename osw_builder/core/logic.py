"""Pure business logic functions for OS Builder"""

from typing import Dict, List, Optional

from .models import MachineState, OSImage, OSImageStatus, UpdatePolicy, VMConfiguration


def lookup_os_image(os_name: str, os_configs: Dict[str, Dict]) -> Optional[OSImage]:
    """Look up OS configuration by name and create OSImage model"""
    config = os_configs.get(os_name)
    if not config:
        return None

    return OSImage(
        name=os_name,
        source=config["source"],
        sha1=config.get("sha1"),
        key=config.get("key"),
        image_name=config.get("image_name"),
        status=OSImageStatus.NOT_BUILT,
    )


def create_update_policy(blacklisted_updates: List[str]) -> UpdatePolicy:
    """Create a Windows update policy with blacklisted updates"""
    return UpdatePolicy(blacklisted_updates=blacklisted_updates)


def should_skip_update(update_id: str, policy: UpdatePolicy) -> bool:
    """Determine if a Windows update should be skipped based on policy"""
    return policy.is_update_blacklisted(update_id)


def is_vm_idle_timeout_reached(idle_seconds: int, timeout_seconds: int) -> bool:
    """Check if VM has exceeded idle timeout threshold"""
    return idle_seconds >= timeout_seconds


def can_proceed_with_capture(vm_config: VMConfiguration) -> bool:
    """Determine if VM is in the correct state for filesystem capture"""
    return vm_config.is_ready_for_capture()


def get_default_idle_timeout() -> int:
    """Get the default idle timeout for VMs in seconds"""
    return 300


def create_vm_configuration(
    box_name: str, machine_state: MachineState, idle_timeout: Optional[int] = None
) -> VMConfiguration:
    """Create VM configuration with optional custom idle timeout"""
    timeout = idle_timeout if idle_timeout is not None else get_default_idle_timeout()
    return VMConfiguration(box_name=box_name, machine_state=machine_state, idle_timeout_seconds=timeout)


def validate_os_name_exists(os_name: str, available_configs: Dict[str, Dict]) -> bool:
    """Validate that the requested OS name exists in available configurations"""
    return os_name in available_configs


def get_packer_extra_args(cpus: Optional[int], memory: Optional[int]) -> List[str]:
    """Generate packer extra arguments for CPU and memory configuration"""
    args = []
    if cpus is not None:
        args.append(f"cpus={cpus}")
    if memory is not None:
        args.append(f"memory={memory}")
    return args
