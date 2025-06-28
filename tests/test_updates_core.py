"""Tests for updates core module."""

import pytest

from osw_builder.updates.core import OSType, detect_os_type


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