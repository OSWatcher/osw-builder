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
            base_config.update(
                {
                    "ansible_connection": "winrm",
                    "ansible_winrm_transport": "basic",
                    "ansible_winrm_server_cert_validation": "ignore",
                    "ansible_password": connection_info.auth_data.get("password", ""),
                }
            )
        case OSType.UBUNTU:
            base_config.update(
                {
                    "ansible_connection": "ssh",
                    "ansible_ssh_private_key_file": connection_info.auth_data.get("identity_file", ""),
                }
            )
        case OSType.UNKNOWN:
            pass

    return {"all": {"hosts": {connection_info.host: base_config}}}


# Task name constants for consistent parsing
WINDOWS_SEARCH_TASK = "search_windows_updates"
UBUNTU_COUNT_TASK = "check_upgradable_packages"
UBUNTU_LIST_TASK = "get_upgradable_packages"


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
            content = [
                {
                    "hosts": "all",
                    "tasks": [
                        {
                            "name": WINDOWS_SEARCH_TASK,
                            "win_updates": {
                                "state": "searched",
                                "category_names": ["CriticalUpdates", "SecurityUpdates", "UpdateRollups"],
                            },
                        }
                    ],
                }
            ]
            return PlaybookConfig(name="windows_search.yml", content=content)

        case OSType.UBUNTU:
            content = [
                {
                    "hosts": "all",
                    "tasks": [
                        {"name": "update_apt_cache", "apt": {"update_cache": True}, "become": True},
                        {
                            "name": UBUNTU_COUNT_TASK,
                            "shell": "apt list --upgradable 2>/dev/null | grep -v '^Listing' | wc -l",
                            "register": "apt_list_upgradable_count",
                        },
                        {
                            "name": UBUNTU_LIST_TASK,
                            "shell": "apt list --upgradable 2>/dev/null | grep -v '^Listing'",
                            "when": "apt_list_upgradable_count.stdout|int > 0",
                        },
                    ],
                }
            ]
            return PlaybookConfig(name="ubuntu_search.yml", content=content)

        case OSType.UNKNOWN:
            raise ValueError("Cannot create search playbook for unknown OS type")
        case _:
            raise ValueError(f"Unsupported OS typUBUNTU_COUNT_TASKe: {os_type}")


def parse_windows_updates(ansible_facts: Dict[str, Any]) -> List[Update]:
    """Parse Windows update results from Ansible win_updates module.

    Args:
        ansible_facts: Results from win_updates Ansible module with structure:
                      {"updates": {"uuid": {"id", "title", "kb", ...}}}

    Returns:
        List of Update objects for each available Windows update
    """
    updates = []

    # Extract updates dict from ansible results
    updates_dict = ansible_facts.get("updates", {})

    for uuid, update_info in updates_dict.items():
        # Get KB list and create identifier
        kb_list = update_info.get("kb", [])
        title = update_info.get("title", "Unknown Update")

        # Create KB identifier
        if kb_list:
            kb_id = f"KB-{kb_list[0]}"  # Use first KB number
        else:
            # Fallback to UUID
            kb_id = f"UPDATE-{uuid[:8]}"

        update = Update(
            id=uuid,  # Use UUID as unique identifier
            name=kb_id,  # Use KB for display name
            description=title,
            os_type=OSType.WINDOWS,
        )
        updates.append(update)

    return updates


def parse_ubuntu_updates(ansible_facts: Dict[str, Any]) -> List[Update]:
    """Parse Ubuntu update results from Ansible apt tasks.

    Args:
        ansible_facts: Results from apt-related Ansible tasks using task names as keys

    Returns:
        List containing single Update object for all available Ubuntu updates
    """
    from datetime import datetime

    # Extract package count and list from ansible facts using task names
    count_result = ansible_facts.get(UBUNTU_COUNT_TASK, {})
    list_result = ansible_facts.get(UBUNTU_LIST_TASK, {})

    upgradable_count = count_result.get("stdout", "0")
    upgradable_packages = list_result.get("stdout", "")

    count = int(upgradable_count) if upgradable_count.isdigit() else 0

    if count == 0:
        return []

    # Create single update for all packages with current date
    date_str = datetime.now().strftime("%Y-%m-%d")
    update_id = f"apt-updates-{date_str}"

    # Create description with package count and some package names
    package_lines = upgradable_packages.strip().split("\n")[:5]  # First 5 packages
    package_names = [line.split("/")[0] for line in package_lines if "/" in line]

    description = f"{count} packages available for update"
    if package_names:
        description += f": {', '.join(package_names)}"
        if len(package_lines) > 5:
            description += "..."

    update = Update(id=update_id, name=update_id, description=description, os_type=OSType.UBUNTU)

    return [update]


def parse_ansible_events(events, os_type: OSType) -> Dict[str, Any]:
    """Parse ansible-runner events to extract task results by task name.

    Args:
        events: Generator of ansible-runner events
        os_type: Operating system type to determine which tasks to look for

    Returns:
        Dictionary containing extracted facts from task results
    """
    facts = {}

    for event in events:
        event_type = event.get("event")

        if event_type == "runner_on_ok":
            event_data = event.get("event_data", {})
            task_name = event_data.get("task", "")

            # Look for OS-specific search tasks by name
            if os_type == OSType.WINDOWS and task_name == WINDOWS_SEARCH_TASK:
                res = event_data.get("res", {})
                if res:
                    facts.update(res)
            elif os_type == OSType.UBUNTU and task_name in (UBUNTU_COUNT_TASK, UBUNTU_LIST_TASK):
                res = event_data.get("res", {})
                if res:
                    # Store result under task name for Ubuntu
                    facts[task_name] = res

    return facts
