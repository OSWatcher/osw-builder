"""Tests for updates core module."""

import pytest

from osw_builder.updates.core import OSType, ConnectionInfo, PlaybookConfig, Update, detect_os_type, build_ansible_inventory, create_search_playbook, parse_windows_updates, parse_ubuntu_updates


def test_detect_os_type_ubuntu():
    """Test detection of Ubuntu OS type."""
    assert detect_os_type("ubuntu.pkr.hcl") == OSType.UBUNTU
    assert detect_os_type("Ubuntu.pkr.hcl") == OSType.UBUNTU
    assert detect_os_type("UBUNTU.pkr.hcl") == OSType.UBUNTU


def test_detect_os_type_windows():
    """Test detection of Windows OS type."""
    assert detect_os_type("windows.pkr.hcl") == OSType.WINDOWS
    assert detect_os_type("Windows.pkr.hcl") == OSType.WINDOWS
    assert detect_os_type("WINDOWS.pkr.hcl") == OSType.WINDOWS
    assert detect_os_type("win10.pkr.hcl") == OSType.WINDOWS
    assert detect_os_type("win11.pkr.hcl") == OSType.WINDOWS


def test_detect_os_type_unknown():
    """Test detection of unknown OS type."""
    assert detect_os_type("macos.pkr.hcl") == OSType.UNKNOWN
    assert detect_os_type("fedora.pkr.hcl") == OSType.UNKNOWN
    assert detect_os_type("random.pkr.hcl") == OSType.UNKNOWN
    assert detect_os_type("") == OSType.UNKNOWN


def test_build_ansible_inventory_windows():
    """Test building Ansible inventory for Windows."""
    conn_info = ConnectionInfo(
        host="win10-vm",
        hostname="192.168.1.100", 
        user="vagrant",
        port=5985,
        auth_data={"password": "vagrant"}
    )
    
    inventory = build_ansible_inventory(conn_info, OSType.WINDOWS)
    
    expected = {
        "all": {
            "hosts": {
                "win10-vm": {
                    "ansible_host": "192.168.1.100",
                    "ansible_user": "vagrant",
                    "ansible_port": 5985,
                    "ansible_connection": "winrm",
                    "ansible_winrm_transport": "basic",
                    "ansible_winrm_server_cert_validation": "ignore",
                    "ansible_password": "vagrant"
                }
            }
        }
    }
    
    assert inventory == expected


def test_build_ansible_inventory_ubuntu():
    """Test building Ansible inventory for Ubuntu."""
    conn_info = ConnectionInfo(
        host="ubuntu-vm",
        hostname="192.168.1.101",
        user="vagrant", 
        port=22,
        auth_data={"identity_file": "/path/to/key"}
    )
    
    inventory = build_ansible_inventory(conn_info, OSType.UBUNTU)
    
    expected = {
        "all": {
            "hosts": {
                "ubuntu-vm": {
                    "ansible_host": "192.168.1.101",
                    "ansible_user": "vagrant",
                    "ansible_port": 22,
                    "ansible_connection": "ssh",
                    "ansible_ssh_private_key_file": "/path/to/key"
                }
            }
        }
    }
    
    assert inventory == expected


def test_build_ansible_inventory_unknown():
    """Test building Ansible inventory for unknown OS type."""
    conn_info = ConnectionInfo(
        host="unknown-vm",
        hostname="192.168.1.102",
        user="user",
        port=22,
        auth_data={}
    )
    
    inventory = build_ansible_inventory(conn_info, OSType.UNKNOWN)
    
    expected = {
        "all": {
            "hosts": {
                "unknown-vm": {
                    "ansible_host": "192.168.1.102",
                    "ansible_user": "user",
                    "ansible_port": 22
                }
            }
        }
    }
    
    assert inventory == expected


def test_create_search_playbook_windows():
    """Test Windows search playbook generation."""
    playbook = create_search_playbook(OSType.WINDOWS)
    
    assert playbook.name == "windows_search.yml"
    assert len(playbook.content) == 1
    
    play = playbook.content[0]
    assert play["hosts"] == "all"
    assert len(play["tasks"]) == 1
    
    task = play["tasks"][0]
    assert task["name"] == "Search for Windows updates"
    assert task["register"] == "windows_updates"
    assert task["win_updates"]["state"] == "searched"
    assert "CriticalUpdates" in task["win_updates"]["category_names"]
    assert "SecurityUpdates" in task["win_updates"]["category_names"]


def test_create_search_playbook_ubuntu():
    """Test Ubuntu search playbook generation."""
    playbook = create_search_playbook(OSType.UBUNTU)
    
    assert playbook.name == "ubuntu_search.yml"
    assert len(playbook.content) == 1
    
    play = playbook.content[0]
    assert play["hosts"] == "all"
    assert len(play["tasks"]) == 3
    
    # Check update cache task
    cache_task = play["tasks"][0]
    assert cache_task["name"] == "Update apt cache"
    assert cache_task["apt"]["update_cache"] is True
    assert cache_task["become"] is True
    
    # Check count task
    count_task = play["tasks"][1]
    assert count_task["name"] == "Check for upgradable packages"
    assert "wc -l" in count_task["shell"]
    assert count_task["register"] == "upgradable_count"
    
    # Check list task
    list_task = play["tasks"][2]
    assert list_task["name"] == "Get upgradable package list"
    assert list_task["register"] == "upgradable_packages"
    assert list_task["when"] == "upgradable_count.stdout|int > 0"


def test_create_search_playbook_unknown():
    """Test that unknown OS type raises ValueError."""
    with pytest.raises(ValueError, match="Cannot create search playbook for unknown OS type"):
        create_search_playbook(OSType.UNKNOWN)


def test_parse_windows_updates():
    """Test parsing Windows update results from Ansible facts."""
    ansible_facts = {
        "updates": {
            "uuid-1234-5678": {
                "id": "uuid-1234-5678",
                "title": "Security Update for Windows (KB4534273)",
                "kb": ["4534273"],
                "categories": ["SecurityUpdates"]
            },
            "uuid-abcd-efgh": {
                "id": "uuid-abcd-efgh", 
                "title": "Critical Update for Windows",
                "kb": [],
                "categories": ["CriticalUpdates"]
            }
        }
    }
    
    updates = parse_windows_updates(ansible_facts)
    
    assert len(updates) == 2
    
    # First update with KB
    update1 = updates[0]
    assert update1.id == "uuid-1234-5678"
    assert update1.name == "KB-4534273"
    assert update1.description == "Security Update for Windows (KB4534273)"
    assert update1.os_type == OSType.WINDOWS
    
    # Second update without KB
    update2 = updates[1]
    assert update2.id == "uuid-abcd-efgh"
    assert update2.name == "UPDATE-uuid-abc"  # Truncated UUID fallback
    assert update2.description == "Critical Update for Windows"
    assert update2.os_type == OSType.WINDOWS


def test_parse_windows_updates_empty():
    """Test parsing empty Windows update results."""
    ansible_facts = {"updates": {}}
    updates = parse_windows_updates(ansible_facts)
    assert updates == []


def test_parse_ubuntu_updates():
    """Test parsing Ubuntu update results from Ansible facts."""
    ansible_facts = {
        "upgradable_count": {"stdout": "15"},
        "upgradable_packages": {
            "stdout": "apt/focal-updates 2.0.9 amd64 [upgradable from: 2.0.6]\nvim/focal-updates 8.2.0716-3ubuntu0.1 amd64 [upgradable from: 8.2.0716-3ubuntu0.0]\ncurl/focal-updates 7.68.0-1ubuntu2.18 amd64 [upgradable from: 7.68.0-1ubuntu2.16]"
        }
    }
    
    updates = parse_ubuntu_updates(ansible_facts)
    
    assert len(updates) == 1
    
    update = updates[0]
    assert update.id.startswith("apt-updates-")
    assert update.name.startswith("apt-updates-")
    assert "15 packages available for update" in update.description
    assert "apt, vim, curl" in update.description
    assert update.os_type == OSType.UBUNTU


def test_parse_ubuntu_updates_no_updates():
    """Test parsing Ubuntu results when no updates available."""
    ansible_facts = {
        "upgradable_count": {"stdout": "0"},
        "upgradable_packages": {"stdout": ""}
    }
    
    updates = parse_ubuntu_updates(ansible_facts)
    assert updates == []


def test_parse_ubuntu_updates_malformed():
    """Test parsing Ubuntu results with malformed data."""
    ansible_facts = {
        "upgradable_count": {"stdout": "invalid"},
        "upgradable_packages": {"stdout": ""}
    }
    
    updates = parse_ubuntu_updates(ansible_facts)
    assert updates == []