"""Tests for build system integration with inheritance."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from osw_builder.image_builder.build import build_image_with_inheritance, create_response_file_from_answerfile_path
from osw_builder.settings import BuildConfig


class TestCommandGeneration:
    """Test Packer command line generation from BuildConfig."""

    def test_build_packer_cmdline_ubuntu_basic(self):
        """Test basic Ubuntu command generation."""
        build_config = BuildConfig(
            template="ubuntu.pkr.hcl",
            varfiles=["ubuntu.pkrvars.hcl", "ubuntu.pkrvars/preseed.pkrvars.hcl"],
            vars={"answerfile_path": "./answer_files/ubuntu/preseed.cfg", "boot_dir": "/install"},
        )

        result = build_config.to_packer_cmdline(
            iso_url="http://example.com/ubuntu.iso", sha1="abc123", packer_args=["cpus=2"]
        )

        expected = [
            "build",
            "-only",
            "qemu.vm",
            "-var-file",
            "ubuntu.pkrvars.hcl",
            "-var-file",
            "ubuntu.pkrvars/preseed.pkrvars.hcl",
            "-var",
            "iso_url=http://example.com/ubuntu.iso",
            "-var",
            "iso_checksum=abc123",
            "-var",
            "answerfile_path=./answer_files/ubuntu/preseed.cfg",
            "-var",
            "boot_dir=/install",
            "-var",
            "cpus=2",
            "ubuntu.pkr.hcl",
        ]

        assert result == expected

    def test_build_packer_cmdline_windows_basic(self):
        """Test basic Windows command generation."""
        build_config = BuildConfig(
            template="windows.pkr.hcl",
            varfiles=["windows.pkrvars.hcl"],
            vars={"answerfile_path": "./answer_files/windows/Autounattend.xml", "key": "VK7JG-NPHTM-C97JM-9MPGT-3V66T"},
        )

        result = build_config.to_packer_cmdline(iso_url="http://example.com/win10.iso", sha1="def456", packer_args=[])

        expected = [
            "build",
            "-only",
            "qemu.vm",
            "-var-file",
            "windows.pkrvars.hcl",
            "-var",
            "iso_url=http://example.com/win10.iso",
            "-var",
            "iso_checksum=def456",
            "-var",
            "answerfile_path=./answer_files/windows/Autounattend.xml",
            "-var",
            "key=VK7JG-NPHTM-C97JM-9MPGT-3V66T",
            "windows.pkr.hcl",
        ]

        assert result == expected

    def test_build_packer_cmdline_no_varfiles(self):
        """Test command generation with no varfiles (pure command-line vars)."""
        build_config = BuildConfig(template="custom.pkr.hcl", varfiles=[], vars={"custom_var": "value"})

        result = build_config.to_packer_cmdline(
            iso_url="http://example.com/custom.iso", sha1="xyz789", packer_args=["memory=4096"]
        )

        expected = [
            "build",
            "-only",
            "qemu.vm",
            "-var",
            "iso_url=http://example.com/custom.iso",
            "-var",
            "iso_checksum=xyz789",
            "-var",
            "custom_var=value",
            "-var",
            "memory=4096",
            "custom.pkr.hcl",
        ]

        assert result == expected

    def test_build_packer_cmdline_multiple_varfiles(self):
        """Test command generation with multiple varfiles."""
        build_config = BuildConfig(
            template="ubuntu.pkr.hcl",
            varfiles=[
                "ubuntu.pkrvars.hcl",
                "ubuntu.pkrvars/modern.pkrvars.hcl",
                "ubuntu.pkrvars/autoinstall.pkrvars.hcl",
            ],
            vars={"answerfile_path": "./answer_files/ubuntu/user-data"},
        )

        result = build_config.to_packer_cmdline(
            iso_url="http://example.com/ubuntu-20.04.iso", sha1="hash123", packer_args=[]
        )

        expected = [
            "build",
            "-only",
            "qemu.vm",
            "-var-file",
            "ubuntu.pkrvars.hcl",
            "-var-file",
            "ubuntu.pkrvars/modern.pkrvars.hcl",
            "-var-file",
            "ubuntu.pkrvars/autoinstall.pkrvars.hcl",
            "-var",
            "iso_url=http://example.com/ubuntu-20.04.iso",
            "-var",
            "iso_checksum=hash123",
            "-var",
            "answerfile_path=./answer_files/ubuntu/user-data",
            "ubuntu.pkr.hcl",
        ]

        assert result == expected


class TestDockerVolumeGeneration:
    """Test Docker volume generation from BuildConfig."""

    def test_build_docker_volumes_ubuntu(self):
        """Test Docker volume generation for Ubuntu with multiple varfiles."""
        build_config = BuildConfig(
            template="ubuntu.pkr.hcl",
            varfiles=["ubuntu.pkrvars.hcl", "ubuntu.pkrvars/preseed.pkrvars.hcl"],
            vars={"answerfile_path": "./answer_files/ubuntu/preseed.cfg"},
        )

        mock_response_file = MagicMock()
        mock_response_file.tmp_path = Path("/tmp/preseed.cfg")
        mock_response_file.docker_path = "/packer/preseed.cfg"

        packer_cache = Path("/cache")
        templates_dir = Path("/packer/templates")

        result = build_config.to_docker_volumes(
            response_file=mock_response_file, packer_home_cache=packer_cache, packer_templates_dir=templates_dir
        )

        expected = {
            "/cache": {"bind": "/cache", "mode": "rw"},
            "/packer/templates": {"bind": "/output_parent", "mode": "rw"},
            "/tmp/preseed.cfg": {"bind": "/packer/preseed.cfg", "mode": "ro"},
            "/packer/templates/ubuntu.pkrvars.hcl": {"bind": "/packer/ubuntu.pkrvars.hcl", "mode": "ro"},
            "/packer/templates/ubuntu.pkrvars/preseed.pkrvars.hcl": {
                "bind": "/packer/ubuntu.pkrvars/preseed.pkrvars.hcl",
                "mode": "ro",
            },
        }

        assert result == expected

    def test_build_docker_volumes_windows(self):
        """Test Docker volume generation for Windows with single varfile."""
        build_config = BuildConfig(
            template="windows.pkr.hcl",
            varfiles=["windows.pkrvars.hcl"],
            vars={"answerfile_path": "./answer_files/windows/Autounattend.xml"},
        )

        mock_response_file = MagicMock()
        mock_response_file.tmp_path = Path("/tmp/Autounattend.xml")
        mock_response_file.docker_path = "/packer/Autounattend.xml"

        packer_cache = Path("/cache")
        templates_dir = Path("/packer/templates")

        result = build_config.to_docker_volumes(
            response_file=mock_response_file, packer_home_cache=packer_cache, packer_templates_dir=templates_dir
        )

        expected = {
            "/cache": {"bind": "/cache", "mode": "rw"},
            "/packer/templates": {"bind": "/output_parent", "mode": "rw"},
            "/tmp/Autounattend.xml": {"bind": "/packer/Autounattend.xml", "mode": "ro"},
            "/packer/templates/windows.pkrvars.hcl": {"bind": "/packer/windows.pkrvars.hcl", "mode": "ro"},
        }

        assert result == expected

    def test_build_docker_volumes_no_varfiles(self):
        """Test Docker volume generation with no varfiles."""
        build_config = BuildConfig(
            template="custom.pkr.hcl", varfiles=[], vars={"answerfile_path": "./answer_files/custom/config.cfg"}
        )

        mock_response_file = MagicMock()
        mock_response_file.tmp_path = Path("/tmp/config.cfg")
        mock_response_file.docker_path = "/packer/config.cfg"

        packer_cache = Path("/cache")
        templates_dir = Path("/packer/templates")

        result = build_config.to_docker_volumes(
            response_file=mock_response_file, packer_home_cache=packer_cache, packer_templates_dir=templates_dir
        )

        expected = {
            "/cache": {"bind": "/cache", "mode": "rw"},
            "/packer/templates": {"bind": "/output_parent", "mode": "rw"},
            "/tmp/config.cfg": {"bind": "/packer/config.cfg", "mode": "ro"},
        }

        assert result == expected


class TestResponseFileCreation:
    """Test response file creation from answerfile_path."""

    def test_create_response_file_ubuntu_preseed(self):
        """Test Ubuntu preseed response file creation."""
        templates_dir = Path("/packer/templates")
        answerfile_path = "./answer_files/ubuntu/preseed.cfg"

        with patch("osw_builder.image_builder.ubuntu_preseed.UbuntuPreseed") as mock_preseed:
            mock_instance = MagicMock()
            mock_preseed.return_value = mock_instance

            result = create_response_file_from_answerfile_path(answerfile_path, templates_dir)

            mock_preseed.assert_called_once_with(templates_dir / "answer_files/ubuntu/preseed.cfg")
            assert result == mock_instance

    def test_create_response_file_ubuntu_autoinstall(self):
        """Test Ubuntu autoinstall response file creation."""
        templates_dir = Path("/packer/templates")
        answerfile_path = "./answer_files/ubuntu/user-data"

        with patch("osw_builder.image_builder.ubuntu_preseed.UbuntuPreseed") as mock_preseed:
            mock_instance = MagicMock()
            mock_preseed.return_value = mock_instance

            result = create_response_file_from_answerfile_path(answerfile_path, templates_dir)

            mock_preseed.assert_called_once_with(templates_dir / "answer_files/ubuntu/user-data")
            assert result == mock_instance

    def test_create_response_file_windows_autounattend(self):
        """Test Windows Autounattend.xml response file creation."""
        templates_dir = Path("/packer/templates")
        answerfile_path = "./answer_files/windows/Autounattend.xml"

        with patch("osw_builder.image_builder.autounattend.WindowsAutounattend") as mock_autounattend:
            mock_instance = MagicMock()
            mock_autounattend.return_value = mock_instance

            result = create_response_file_from_answerfile_path(answerfile_path, templates_dir)

            mock_autounattend.assert_called_once_with(templates_dir / "answer_files/windows/Autounattend.xml")
            assert result == mock_instance

    def test_create_response_file_windows_xp_sif(self):
        """Test Windows XP SIF response file creation."""
        templates_dir = Path("/packer/templates")
        answerfile_path = "./answer_files/windows/WINNT.SIF"

        with patch("osw_builder.image_builder.winxp_sif.WindowsXPSif") as mock_sif:
            mock_instance = MagicMock()
            mock_sif.return_value = mock_instance

            result = create_response_file_from_answerfile_path(answerfile_path, templates_dir)

            mock_sif.assert_called_once_with(templates_dir / "answer_files/windows/WINNT.SIF")
            assert result == mock_instance

    def test_create_response_file_unsupported_extension(self):
        """Test error handling for unsupported file extensions."""
        templates_dir = Path("/packer/templates")
        answerfile_path = "./answer_files/unknown/config.txt"

        with pytest.raises(ValueError, match="Unsupported response file type for: config.txt"):
            create_response_file_from_answerfile_path(answerfile_path, templates_dir)


class TestBuildImageIntegration:
    """Test the new build_image_with_inheritance function."""

    @patch("osw_builder.image_builder.build.resolve_build_config")
    @patch("osw_builder.image_builder.build.validate_source_and_compute_sha1")
    @patch("osw_builder.image_builder.build.create_response_file_from_answerfile_path")
    @patch("osw_builder.image_builder.build.run_packer_with_inheritance")
    @patch("osw_builder.image_builder.build.fake_run_packer_with_inheritance")
    def test_build_image_with_inheritance_ubuntu(
        self, mock_fake_run_packer, mock_run_packer, mock_create_response, mock_validate, mock_resolve
    ):
        """Test complete Ubuntu build with inheritance."""
        # Setup mocks
        mock_resolve.return_value = BuildConfig(
            template="ubuntu.pkr.hcl",
            varfiles=["ubuntu.pkrvars.hcl", "ubuntu.pkrvars/preseed.pkrvars.hcl"],
            vars={"answerfile_path": "./answer_files/ubuntu/preseed.cfg", "boot_dir": "/install"},
        )
        mock_validate.return_value = "abc123"
        mock_response_file = MagicMock()
        mock_response_file.__enter__ = MagicMock(return_value=mock_response_file)
        mock_response_file.__exit__ = MagicMock(return_value=None)
        mock_create_response.return_value = mock_response_file
        mock_run_packer.return_value = Path("/output/ubuntu.qcow2")

        config_entry = {"name": "ubuntu-18.04", "source": "http://example.com/ubuntu.iso", "key": "test-key"}

        # Test the function
        with build_image_with_inheritance("ubuntu-18.04", config_entry) as result:
            assert result == Path("/output/ubuntu.qcow2")

        # Verify calls
        mock_resolve.assert_called_once_with("ubuntu-18.04")
        mock_validate.assert_called_once_with(config_entry)
        mock_create_response.assert_called_once()
        mock_response_file.configure.assert_called_once_with(config_entry, None)
        mock_run_packer.assert_called_once()

    @patch("osw_builder.image_builder.build.resolve_build_config")
    @patch("osw_builder.image_builder.build.validate_source_and_compute_sha1")
    @patch("osw_builder.image_builder.build.create_response_file_from_answerfile_path")
    @patch("osw_builder.image_builder.build.run_packer_with_inheritance")
    @patch("osw_builder.image_builder.build.fake_run_packer_with_inheritance")
    def test_build_image_with_inheritance_windows(
        self, mock_fake_run_packer, mock_run_packer, mock_create_response, mock_validate, mock_resolve
    ):
        """Test complete Windows build with inheritance."""
        # Setup mocks
        mock_resolve.return_value = BuildConfig(
            template="windows.pkr.hcl",
            varfiles=["windows.pkrvars.hcl"],
            vars={"answerfile_path": "./answer_files/windows/Autounattend.xml"},
        )
        mock_validate.return_value = "def456"
        mock_response_file = MagicMock()
        mock_response_file.__enter__ = MagicMock(return_value=mock_response_file)
        mock_response_file.__exit__ = MagicMock(return_value=None)
        mock_create_response.return_value = mock_response_file
        mock_run_packer.return_value = Path("/output/windows.qcow2")

        config_entry = {
            "name": "win10-1507",
            "source": "http://example.com/win10.iso",
            "key": "VK7JG-NPHTM-C97JM-9MPGT-3V66T",
        }
        extra_cmds = ["reg.exe add HKLM\\SOFTWARE\\Test"]

        # Test the function
        with build_image_with_inheritance("win10-1507", config_entry, extra_cmds) as result:
            assert result == Path("/output/windows.qcow2")

        # Verify calls
        mock_resolve.assert_called_once_with("win10-1507")
        mock_validate.assert_called_once_with(config_entry)
        mock_create_response.assert_called_once()
        mock_response_file.configure.assert_called_once_with(config_entry, extra_cmds)
        mock_run_packer.assert_called_once()

    @patch("osw_builder.image_builder.build.resolve_build_config")
    def test_build_image_with_inheritance_image_not_found(self, mock_resolve):
        """Test error handling when image not found."""
        mock_resolve.side_effect = ValueError("Image 'nonexistent' not found in any branch")

        config_entry = {"name": "nonexistent", "source": "http://example.com/fake.iso"}

        with pytest.raises(ValueError, match="Image 'nonexistent' not found in any branch"):
            with build_image_with_inheritance("nonexistent", config_entry):
                pass
