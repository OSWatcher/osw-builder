"""Tests for business logic functions"""

from osw_builder.core.logic import (
    can_proceed_with_capture,
    create_update_policy,
    create_vm_configuration,
    get_default_idle_timeout,
    get_packer_extra_args,
    is_vm_idle_timeout_reached,
    lookup_os_image,
    should_skip_update,
    validate_os_name_exists,
)
from osw_builder.core.models import MachineState, OSImageStatus


class TestOSImageLookup:
    def test_lookup_existing_os_image(self):
        """Test looking up an existing OS configuration"""
        configs = {
            "win10": {
                "source": "file:///path/to/win10.iso",
                "sha1": "abc123",
                "key": "WIN10-KEY",
                "image_name": "Windows 10 Pro",
            }
        }

        image = lookup_os_image("win10", configs)

        assert image is not None
        assert image.name == "win10"
        assert image.source == "file:///path/to/win10.iso"
        assert image.sha1 == "abc123"
        assert image.key == "WIN10-KEY"
        assert image.image_name == "Windows 10 Pro"
        assert image.status == OSImageStatus.NOT_BUILT

    def test_lookup_nonexistent_os_image(self):
        """Test looking up a non-existent OS configuration"""
        configs = {"win10": {"source": "file:///path/to/win10.iso"}}

        image = lookup_os_image("win11", configs)

        assert image is None

    def test_lookup_os_image_minimal_config(self):
        """Test looking up OS with minimal configuration"""
        configs = {"ubuntu20": {"source": "https://ubuntu.com/ubuntu.iso"}}

        image = lookup_os_image("ubuntu20", configs)

        assert image is not None
        assert image.name == "ubuntu20"
        assert image.source == "https://ubuntu.com/ubuntu.iso"
        assert image.sha1 is None
        assert image.key is None
        assert image.image_name is None


class TestUpdatePolicy:
    def test_create_update_policy(self):
        """Test creating an update policy"""
        blacklisted = ["4462939", "2267602"]
        policy = create_update_policy(blacklisted)

        assert policy.blacklisted_updates == blacklisted

    def test_should_skip_blacklisted_update(self):
        """Test skipping blacklisted updates"""
        policy = create_update_policy(["4462939", "2267602"])

        assert should_skip_update("4462939", policy)
        assert should_skip_update("2267602", policy)

    def test_should_not_skip_allowed_update(self):
        """Test not skipping allowed updates"""
        policy = create_update_policy(["4462939"])

        assert not should_skip_update("1111111", policy)


class TestVMOperations:
    def test_vm_idle_timeout_not_reached(self):
        """Test VM idle timeout not reached"""
        assert not is_vm_idle_timeout_reached(250, 300)

    def test_vm_idle_timeout_reached(self):
        """Test VM idle timeout reached"""
        assert is_vm_idle_timeout_reached(350, 300)

    def test_vm_idle_timeout_exactly_reached(self):
        """Test VM idle timeout exactly reached"""
        assert is_vm_idle_timeout_reached(300, 300)

    def test_can_proceed_with_capture_running_vm(self):
        """Test can proceed with capture when VM is running"""
        config = create_vm_configuration("test-vm", MachineState.RUNNING)

        assert can_proceed_with_capture(config)

    def test_cannot_proceed_with_capture_shutoff_vm(self):
        """Test cannot proceed with capture when VM is shut off"""
        config = create_vm_configuration("test-vm", MachineState.SHUTOFF)

        assert not can_proceed_with_capture(config)

    def test_get_default_idle_timeout(self):
        """Test getting default idle timeout"""
        assert get_default_idle_timeout() == 300

    def test_create_vm_configuration_with_custom_timeout(self):
        """Test creating VM configuration with custom timeout"""
        config = create_vm_configuration("test-vm", MachineState.RUNNING, 600)

        assert config.box_name == "test-vm"
        assert config.machine_state == MachineState.RUNNING
        assert config.idle_timeout_seconds == 600

    def test_create_vm_configuration_with_default_timeout(self):
        """Test creating VM configuration with default timeout"""
        config = create_vm_configuration("test-vm", MachineState.RUNNING)

        assert config.idle_timeout_seconds == 300


class TestValidation:
    def test_validate_existing_os_name(self):
        """Test validating existing OS name"""
        configs = {"win10": {}, "ubuntu20": {}}

        assert validate_os_name_exists("win10", configs)
        assert validate_os_name_exists("ubuntu20", configs)

    def test_validate_nonexistent_os_name(self):
        """Test validating non-existent OS name"""
        configs = {"win10": {}}

        assert not validate_os_name_exists("win11", configs)


class TestPackerArgs:
    def test_get_packer_extra_args_none(self):
        """Test getting packer args with no custom values"""
        args = get_packer_extra_args(None, None)

        assert args == []

    def test_get_packer_extra_args_cpus_only(self):
        """Test getting packer args with CPU override only"""
        args = get_packer_extra_args(8, None)

        assert args == ["cpus=8"]

    def test_get_packer_extra_args_memory_only(self):
        """Test getting packer args with memory override only"""
        args = get_packer_extra_args(None, 4096)

        assert args == ["memory=4096"]

    def test_get_packer_extra_args_both(self):
        """Test getting packer args with both CPU and memory overrides"""
        args = get_packer_extra_args(8, 4096)

        assert args == ["cpus=8", "memory=4096"]
