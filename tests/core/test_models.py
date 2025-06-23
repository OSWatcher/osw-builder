"""Tests for business models"""

from osw_builder.core.models import (
    MachineState,
    OSImage,
    OSImageStatus,
    SnapshotMetadata,
    UpdatePolicy,
    VMConfiguration,
)


class TestOSImage:
    def test_create_os_image(self):
        """Test creating an OS image with all fields"""
        image = OSImage(
            name="win10",
            source="file:///path/to/iso",
            sha1="abc123",
            key="XXXXX-XXXXX-XXXXX-XXXXX-XXXXX",
            image_name="Windows 10 Pro",
        )

        assert image.name == "win10"
        assert image.source == "file:///path/to/iso"
        assert image.sha1 == "abc123"
        assert image.key == "XXXXX-XXXXX-XXXXX-XXXXX-XXXXX"
        assert image.image_name == "Windows 10 Pro"
        assert image.status == OSImageStatus.NOT_BUILT

    def test_create_os_image_minimal(self):
        """Test creating an OS image with minimal fields"""
        image = OSImage(
            name="ubuntu20",
            source="https://releases.ubuntu.com/20.04/ubuntu-20.04.6-desktop-amd64.iso",
            sha1=None,
            key=None,
            image_name=None,
        )

        assert image.name == "ubuntu20"
        assert image.sha1 is None
        assert image.key is None
        assert image.image_name is None


class TestUpdatePolicy:
    def test_update_policy_empty(self):
        """Test update policy with no blacklisted updates"""
        policy = UpdatePolicy(blacklisted_updates=[])

        assert not policy.is_update_blacklisted("123456")

    def test_update_policy_with_blacklist(self):
        """Test update policy with blacklisted updates"""
        policy = UpdatePolicy(blacklisted_updates=["4462939", "2267602"])

        assert policy.is_update_blacklisted("4462939")
        assert policy.is_update_blacklisted("2267602")
        assert not policy.is_update_blacklisted("1111111")


class TestSnapshotMetadata:
    def test_create_snapshot_metadata(self):
        """Test creating snapshot metadata with encoding"""
        metadata = SnapshotMetadata.create("test-snapshot", "Test description")

        assert metadata.name == "test-snapshot"
        assert metadata.get_description() == "Test description"

    def test_snapshot_metadata_encoding(self):
        """Test that description is properly encoded"""
        description = "Special chars: éñ中文"
        metadata = SnapshotMetadata.create("test", description)

        assert metadata.get_description() == description
        assert metadata.encoded_description != description


class TestVMConfiguration:
    def test_create_vm_config(self):
        """Test creating VM configuration"""
        config = VMConfiguration(box_name="test-vm", machine_state=MachineState.RUNNING, idle_timeout_seconds=600)

        assert config.box_name == "test-vm"
        assert config.machine_state == MachineState.RUNNING
        assert config.idle_timeout_seconds == 600

    def test_vm_ready_for_capture(self):
        """Test VM readiness for capture"""
        running_config = VMConfiguration(box_name="test-vm", machine_state=MachineState.RUNNING)
        shutoff_config = VMConfiguration(box_name="test-vm", machine_state=MachineState.SHUTOFF)

        assert running_config.is_ready_for_capture()
        assert not shutoff_config.is_ready_for_capture()

    def test_vm_config_defaults(self):
        """Test VM configuration default values"""
        config = VMConfiguration(box_name="test-vm")

        assert config.machine_state == MachineState.NOT_CREATED
        assert config.idle_timeout_seconds == 300
