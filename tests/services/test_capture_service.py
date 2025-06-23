"""Tests for CaptureService"""

import pytest

from osw_builder.core.models import UpdatePolicy
from osw_builder.services.capture_service import CaptureConfiguration, CaptureService, OSImageConfiguration


class TestCaptureService:
    def test_from_settings_with_blacklisted_updates(self):
        """Test creating service from settings with blacklisted updates"""
        settings = {"blacklisted_updates": ["4462939", "2267602"]}
        service = CaptureService.from_settings(settings)

        assert service.should_skip_windows_update("4462939")
        assert service.should_skip_windows_update("2267602")
        assert not service.should_skip_windows_update("1111111")

    def test_from_settings_without_blacklisted_updates(self):
        """Test creating service from settings without blacklisted updates"""
        settings = {}
        service = CaptureService.from_settings(settings)

        assert not service.should_skip_windows_update("4462939")
        assert not service.should_skip_windows_update("any_update")

    def test_validate_os_configuration_success(self):
        """Test successful OS configuration validation"""
        service = CaptureService(UpdatePolicy([]))
        os_configs = {
            "win10": {
                "template": "windows.pkr.hcl",
                "varfile": "win10.pkrvars.hcl",
                "description": "Windows 10",
                "source": "test.iso",
                "extra_firstlogin_cmds": ["cmd1"],
                "network": True,
            }
        }

        config = service.validate_os_configuration("win10", os_configs)

        assert config.name == "win10"
        assert config.template == "windows.pkr.hcl"
        assert config.varfile == "win10.pkrvars.hcl"
        assert config.description == "Windows 10"
        assert config.source == "test.iso"
        assert config.extra_firstlogin_cmds == ["cmd1"]
        assert config.network is True

    def test_validate_os_configuration_minimal(self):
        """Test OS configuration validation with minimal fields"""
        service = CaptureService(UpdatePolicy([]))
        os_configs = {"ubuntu20": {"description": "Ubuntu 20", "source": "ubuntu.iso"}}

        config = service.validate_os_configuration("ubuntu20", os_configs)

        assert config.name == "ubuntu20"
        assert config.template is None
        assert config.varfile is None
        assert config.description == "Ubuntu 20"
        assert config.source == "ubuntu.iso"
        assert config.extra_firstlogin_cmds is None
        assert config.network is False

    def test_validate_os_configuration_not_found(self):
        """Test OS configuration validation with non-existent OS"""
        service = CaptureService(UpdatePolicy([]))
        os_configs = {"win10": {"description": "Windows 10", "source": "test.iso"}}

        with pytest.raises(RuntimeError, match="Could not find OS name: win11"):
            service.validate_os_configuration("win11", os_configs)

    def test_should_skip_windows_update(self):
        """Test Windows update skipping logic"""
        update_policy = UpdatePolicy(["4462939", "2267602"])
        service = CaptureService(update_policy)

        assert service.should_skip_windows_update("4462939")
        assert service.should_skip_windows_update("2267602")
        assert not service.should_skip_windows_update("1111111")

    def test_create_idle_vm_configuration(self):
        """Test idle VM configuration creation"""
        service = CaptureService(UpdatePolicy([]))

        timeout_seconds, timeout_msg = service.create_idle_vm_configuration("test-vm")

        assert timeout_seconds == 600  # 300 * 2
        assert "Waiting for 600 seconds" in timeout_msg

    def test_should_apply_updates_from_config(self):
        """Test update application logic from capture config"""
        service = CaptureService(UpdatePolicy([]))
        capture_config = CaptureConfiguration(
            os_name="win10",
            box_name="win10",
            apply_updates=True,
            search_updates=True,
            idle=True,
            destroy=False,
            packer_args=[],
        )
        os_config = OSImageConfiguration(
            name="win10",
            template=None,
            varfile=None,
            description="Windows 10",
            source="test.iso",
            extra_firstlogin_cmds=None,
        )

        assert service.should_apply_updates(capture_config, os_config)

    def test_should_search_updates_from_config(self):
        """Test update search logic from capture config"""
        service = CaptureService(UpdatePolicy([]))
        capture_config = CaptureConfiguration(
            os_name="win10",
            box_name="win10",
            apply_updates=True,
            search_updates=True,
            idle=True,
            destroy=False,
            packer_args=[],
        )
        os_config = OSImageConfiguration(
            name="win10",
            template=None,
            varfile=None,
            description="Windows 10",
            source="test.iso",
            extra_firstlogin_cmds=None,
        )

        assert service.should_search_updates(capture_config, os_config)

    def test_should_capture_idle_from_config(self):
        """Test idle capture logic from capture config"""
        service = CaptureService(UpdatePolicy([]))
        capture_config = CaptureConfiguration(
            os_name="win10",
            box_name="win10",
            apply_updates=True,
            search_updates=True,
            idle=True,
            destroy=False,
            packer_args=[],
        )
        os_config = OSImageConfiguration(
            name="win10",
            template=None,
            varfile=None,
            description="Windows 10",
            source="test.iso",
            extra_firstlogin_cmds=None,
        )

        assert service.should_capture_idle(capture_config, os_config)
