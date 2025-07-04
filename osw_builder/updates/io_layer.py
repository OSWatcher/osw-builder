"""I/O layer functions for update management."""

import logging
from pathlib import Path
from typing import Any, Dict, List

import ansible_runner

from ..vagrant.vagrant import ssh_config, winrm_config
from .core import ConnectionInfo, OSType, parse_ansible_events


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
                host=config.Host, hostname=config.HostName, user=config.User, port=config.Port, auth_data=auth_data
            )
        case OSType.UBUNTU:
            config = ssh_config(vagrant_dir)
            auth_data = {"password": "vagrant"}  # Use standard vagrant password
            return ConnectionInfo(
                host=config.Host, hostname=config.HostName, user=config.User, port=config.Port, auth_data=auth_data
            )
        case OSType.UNKNOWN:
            raise ValueError("Cannot get connection info for unknown OS type")
        case _:
            raise ValueError(f"Unsupported OS type: {os_type}")


def run_ansible_playbook(
    inventory_dict: Dict[str, Any], playbook_content: List[Dict[str, Any]], os_type: OSType
) -> Dict[str, Any]:
    """Run Ansible playbook using ansible-runner with direct data structures.

    Args:
        inventory_dict: Ansible inventory as dictionary
        playbook_content: Playbook content as list of plays
        os_type: Operating system type for parsing events

    Returns:
        Dictionary containing execution results and facts

    Raises:
        RuntimeError: If playbook execution fails
    """
    result = ansible_runner.run(inventory=inventory_dict, playbook=playbook_content, quiet=True, verbosity=0)

    if result.status != "successful":
        logging.error("Ansible playbook failed with status: %s", result.status)
        logging.error("Return code: %s", result.rc)

        # Log stdout content
        if hasattr(result, "stdout") and result.stdout:
            try:
                stdout_content = result.stdout.read()
                logging.error("Ansible stdout:\n%s", stdout_content)
            except Exception as e:
                logging.error("Could not read stdout: %s", e)

        # Log stderr content if available
        if hasattr(result, "stderr") and result.stderr:
            try:
                stderr_content = result.stderr.read()
                logging.error("Ansible stderr:\n%s", stderr_content)
            except Exception as e:
                logging.error("Could not read stderr: %s", e)

        # Log last few events for context
        if result.events:
            logging.error("Last few events:")
            events_list = list(result.events)
            for event in events_list[-3:]:  # Last 3 events
                event_type = event.get("event", "unknown")
                stdout = event.get("stdout", "")
                logging.error("  %s: %s", event_type, stdout)

        raise RuntimeError(f"Ansible playbook failed with status: {result.status}")

    # Example of event structure containing the registered variable 'windows_updates'
    #  {'uuid': '57bdef9e-98b7-4d34-89f1-d740e72fcf7a',
    #   'counter': 34,
    #   'stdout': '\x1b[0;32mok: [win10-19H1-1903.18362.30] => [truncated]
    #   'start_line': 35,
    #   'end_line': 36,
    #   'runner_ident': '24d279f7-ce34-4164-b1fa-523b18f8fc44',
    #   'event': 'runner_on_ok',
    #   'pid': 736665,
    #   'created': '2025-06-27T19:50:01.755665+00:00',
    #   'parent_uuid': 'bc6ee202-a0e4-dfd3-a6be-000000000004',
    #   'event_data': {'playbook': '/tmp/tmpzyzgll4w/project/main.json',
    #    'playbook_uuid': '160b7df4-bb74-4593-b4ce-ead262aa052f',
    #    'play': 'all',
    #    'play_uuid': 'bc6ee202-a0e4-dfd3-a6be-000000000002',
    #    'play_pattern': 'all',
    #    'task': 'Search for Windows updates',
    #    'task_uuid': 'bc6ee202-a0e4-dfd3-a6be-000000000004',
    #    'task_action': 'win_updates',
    #    'resolved_action': 'ansible.windows.win_updates',
    #    'task_args': '',
    #    'task_path': '',
    #    'host': 'win10-19H1-1903.18362.30',
    #    'remote_addr': 'win10-19H1-1903.18362.30',
    #    'res': {'changed': False,
    #     'reboot_required': False,
    #     'rebooted': False,
    #     'found_update_count': 2,
    #     'failed_update_count': 0,
    #     'installed_update_count': 0,
    #     'updates': {'8f4a16e2-f816-4683-9245-526a14eff6ea': {
    #       'title': '2021-09 Update for Windows 10 Version 1903 for x64-based Systems (KB4023057)',
    #       'kb': ['4023057'],
    #       'categories': ['Critical Updates'],
    #       'id': '8f4a16e2-f816-4683-9245-526a14eff6ea',
    #       'downloaded': False,
    #       'installed': False},
    #      '9024c69d-4de8-4233-86c2-9ee24bc67ec4': {
    #       'title': 'Windows Malicious Software Removal Tool x64 - v5.134 (KB890830)',
    #       'kb': ['890830'],
    #       'categories': ['Update Rollups',
    #        'Windows 10',
    #        'Windows 10 LTSB',
    #        'Windows 10, version 1903 and later',
    #        'Windows 11'],
    #       'id': '9024c69d-4de8-4233-86c2-9ee24bc67ec4',
    #       'downloaded': False,
    #       'installed': False}},
    #     'filtered_updates': {'0319d590-5f10-4d96-8f66-5df04663f962': {
    #       'title': '2020-11 Cumulative Update Preview for [truncated]',
    #       'kb': ['4586878'],
    #       'categories': ['Updates', 'Windows 10, version 1903 and later'],
    #       'id': '0319d590-5f10-4d96-8f66-5df04663f962',
    #       'downloaded': False,
    #       'installed': False,
    #       'filtered_reason': 'category_names',
    #       'filtered_reasons': ['category_names']},
    #      '8dceb489-e9e6-4bb3-9194-f2d11ffe853c': {
    #        'title': 'Security Intelligence Update for Mic[truncated]',
    #       'kb': ['2267602'],
    #       'categories': ['Definition Updates', 'Microsoft Defender Antivirus'],
    #       'id': '8dceb489-e9e6-4bb3-9194-f2d11ffe853c',
    #       'downloaded': False,
    #       'installed': False,
    #       'filtered_reason': 'category_names',
    #       'filtered_reasons': ['category_names']},
    #      'ca228258-2724-4539-a3b4-58f7ef7ff08d': {'title': 'Feature update to Windows 10, version 22H2',
    #       'kb': ['5060533'],
    #       'categories': ['Upgrades'],
    #       'id': 'ca228258-2724-4539-a3b4-58f7ef7ff08d',
    #       'downloaded': False,
    #       'installed': False,
    #       'filtered_reason': 'category_names',
    #       'filtered_reasons': ['category_names']}},
    #     'invocation': {'module_args': {'reject_list': None,
    #       'category_names': ['CriticalUpdates',
    #        'SecurityUpdates',
    #        'UpdateRollups'],
    #       'reboot_timeout': 1200,
    #       'reboot': False,
    #       'server_selection': 'default',
    #       'state': 'searched',
    #       'accept_list': None,
    #       'skip_optional': False,
    #       'log_path': None}},
    #     '_ansible_no_log': False},
    #    'start': '2025-06-27T19:49:29.418243+00:00',
    #    'end': '2025-06-27T19:50:01.755393+00:00',
    #    'duration': 32.33715,
    #    'event_loop': None,
    #    'uuid': '57bdef9e-98b7-4d34-89f1-d740e72fcf7a'}}

    # Use the dedicated parsing function
    facts = parse_ansible_events(result.events, os_type)

    return {"status": result.status, "facts": facts, "stats": result.stats, "rc": result.rc}
