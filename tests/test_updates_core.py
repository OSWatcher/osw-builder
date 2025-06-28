"""Tests for updates core module."""

import pytest

from osw_builder.updates.core import OSType, ConnectionInfo, detect_os_type, build_ansible_inventory


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