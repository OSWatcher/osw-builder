"""Tests for branch-based cascade inheritance system."""

from unittest.mock import patch

import pytest

from osw_builder.settings import BuildConfig, resolve_image_config


class TestBasicInheritance:
    """Test basic chronological inheritance functionality."""

    @patch("osw_builder.settings.settings")
    def test_simple_inheritance(self, mock_settings):
        """Test basic chronological inheritance from single override point."""
        mock_settings.branches = {
            "ubuntu-server": [
                {
                    "name": "ubuntu-6.10",
                    "build_config": {
                        "template": "ubuntu.pkr.hcl",
                        "vars": {"boot_dir": "/install", "boot_command": "<F6>"},
                    },
                },
                "ubuntu-7.04",  # Should inherit from 6.10
                "ubuntu-8.04",  # Should inherit from 6.10
            ]
        }

        result = resolve_image_config("ubuntu-7.04").build_config

        assert isinstance(result, BuildConfig)
        assert result.template == "ubuntu.pkr.hcl"
        assert result.vars["boot_dir"] == "/install"
        assert result.vars["boot_command"] == "<F6>"
        assert result.varfiles == []

    @patch("osw_builder.settings.settings")
    def test_first_item_must_define_template(self, mock_settings):
        """Test that first item in branch must define template to be useful."""
        mock_settings.branches = {
            "ubuntu-server": [
                {
                    "name": "ubuntu-6.10",
                    "build_config": {"template": "ubuntu.pkr.hcl", "vars": {"boot_dir": "/install"}},
                },
                "ubuntu-7.04",
            ]
        }

        # First item should work
        result_first = resolve_image_config("ubuntu-6.10").build_config
        assert result_first.template == "ubuntu.pkr.hcl"
        assert result_first.vars["boot_dir"] == "/install"

        # Second item should inherit template
        result_second = resolve_image_config("ubuntu-7.04").build_config
        assert result_second.template == "ubuntu.pkr.hcl"
        assert result_second.vars["boot_dir"] == "/install"

    @patch("osw_builder.settings.settings")
    def test_first_item_without_template_succeeds(self, mock_settings):
        """Test that branch starting without template works (for box images)."""
        mock_settings.branches = {
            "box-branch": [
                {"name": "ubuntu-6.10", "build_config": {"vars": {"boot_dir": "/install"}}},  # No template!
                "ubuntu-7.04",
            ]
        }

        result = resolve_image_config("ubuntu-7.04").build_config
        assert result.template is None  # Box images don't need templates
        assert result.vars["boot_dir"] == "/install"

    @patch("osw_builder.settings.settings")
    def test_target_not_found(self, mock_settings):
        """Test error handling when target image not found in any branch."""
        mock_settings.branches = {
            "ubuntu-server": [{"name": "ubuntu-6.10", "build_config": {"template": "ubuntu.pkr.hcl"}}]
        }

        with pytest.raises(ValueError, match="Image 'ubuntu-99.99' not found in any branch"):
            resolve_image_config("ubuntu-99.99")

    @patch("osw_builder.settings.settings")
    def test_no_branches_defined(self, mock_settings):
        """Test error handling when no branches defined."""
        mock_settings.branches = {}

        with pytest.raises(ValueError, match="No branches defined in configuration"):
            resolve_image_config("any-image")

    @patch("osw_builder.settings.settings")
    def test_image_in_multiple_branches_fails(self, mock_settings):
        """Test error handling when image found in multiple branches."""
        mock_settings.branches = {"branch1": ["duplicate-image"], "branch2": ["duplicate-image"]}

        with pytest.raises(
            ValueError, match="Image 'duplicate-image' found in multiple branches: \\['branch1', 'branch2'\\]"
        ):
            resolve_image_config("duplicate-image")


class TestOverrideInheritance:
    """Test override points in inheritance chain."""

    @patch("osw_builder.settings.settings")
    def test_override_inheritance(self, mock_settings):
        """Test override points in inheritance chain."""
        mock_settings.branches = {
            "ubuntu-server": [
                {
                    "name": "ubuntu-6.10",
                    "build_config": {
                        "template": "ubuntu.pkr.hcl",
                        "varfiles": ["preseed.pkrvars.hcl"],
                        "vars": {"boot_dir": "/install", "boot_command": "<F6>"},
                    },
                },
                "ubuntu-15.10",  # Inherits from 6.10
                {
                    "name": "ubuntu-16.04",
                    "build_config": {
                        "varfiles": ["modern.pkrvars.hcl"],  # REPLACES varfiles
                        "vars": {"boot_dir": "/casper"},  # OVERRIDES vars
                    },
                },
                "ubuntu-18.04",  # Inherits 6.10 + 16.04 overrides
            ]
        }

        result = resolve_image_config("ubuntu-18.04").build_config

        assert result.template == "ubuntu.pkr.hcl"  # From 6.10
        assert result.varfiles == ["modern.pkrvars.hcl"]  # From 16.04 (replaced)
        assert result.vars["boot_dir"] == "/casper"  # From 16.04 (overridden)
        assert result.vars["boot_command"] == "<F6>"  # From 6.10 (preserved)

    @patch("osw_builder.settings.settings")
    def test_varfiles_replace_not_extend(self, mock_settings):
        """Test that varfiles are replaced, not extended."""
        mock_settings.branches = {
            "ubuntu-server": [
                {
                    "name": "ubuntu-6.10",
                    "build_config": {
                        "template": "ubuntu.pkr.hcl",
                        "varfiles": ["base.pkrvars.hcl", "preseed.pkrvars.hcl"],
                    },
                },
                {
                    "name": "ubuntu-16.04",
                    "build_config": {"varfiles": ["modern.pkrvars.hcl"]},  # Should REPLACE, not extend
                },
                "ubuntu-18.04",
            ]
        }

        result = resolve_image_config("ubuntu-18.04").build_config

        # Should only have varfiles from 16.04, not 6.10 + 16.04
        assert result.varfiles == ["modern.pkrvars.hcl"]

    @patch("osw_builder.settings.settings")
    def test_vars_merge_behavior(self, mock_settings):
        """Test that vars are merged, individual keys override."""
        mock_settings.branches = {
            "ubuntu-server": [
                {
                    "name": "ubuntu-6.10",
                    "build_config": {
                        "template": "ubuntu.pkr.hcl",
                        "vars": {"boot_dir": "/install", "boot_command": "<F6>", "initrd": "initrd.gz"},
                    },
                },
                {
                    "name": "ubuntu-16.04",
                    "build_config": {
                        "vars": {
                            "boot_dir": "/casper",  # Override
                            "boot_command": "<ESC><F6>",  # Override
                            # initrd should be preserved
                        }
                    },
                },
                "ubuntu-18.04",
            ]
        }

        result = resolve_image_config("ubuntu-18.04").build_config

        assert result.vars["boot_dir"] == "/casper"  # Overridden
        assert result.vars["boot_command"] == "<ESC><F6>"  # Overridden
        assert result.vars["initrd"] == "initrd.gz"  # Preserved from 6.10

    @patch("osw_builder.settings.settings")
    def test_multiple_override_points(self, mock_settings):
        """Test multiple override points in succession."""
        mock_settings.branches = {
            "ubuntu-server": [
                {
                    "name": "ubuntu-6.10",
                    "build_config": {"template": "ubuntu.pkr.hcl", "vars": {"era": "legacy", "boot_dir": "/install"}},
                },
                "ubuntu-15.10",
                {"name": "ubuntu-16.04", "build_config": {"vars": {"era": "modern", "boot_dir": "/casper"}}},
                "ubuntu-19.10",
                {"name": "ubuntu-20.04", "build_config": {"vars": {"era": "autoinstall", "installer": "cloud-init"}}},
                "ubuntu-22.04",
            ]
        }

        result = resolve_image_config("ubuntu-22.04").build_config

        assert result.template == "ubuntu.pkr.hcl"  # From 6.10
        assert result.vars["era"] == "autoinstall"  # From 20.04 (last override)
        assert result.vars["boot_dir"] == "/casper"  # From 16.04 (not overridden)
        assert result.vars["installer"] == "cloud-init"  # From 20.04


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @patch("osw_builder.settings.settings")
    def test_string_only_branch(self, mock_settings):
        """Test branch with only string entries (no build_config) works for box images."""
        mock_settings.branches = {"string-only": ["image-1", "image-2", "image-3"]}

        result = resolve_image_config("image-2").build_config
        assert result.template is None  # No template for box images
        assert result.varfiles == []
        assert result.vars == {}

    @patch("osw_builder.settings.settings")
    def test_mixed_string_and_object_branch(self, mock_settings):
        """Test branch with mix of strings and objects."""
        mock_settings.branches = {
            "mixed": [
                {"name": "base", "build_config": {"template": "test.pkr.hcl"}},
                "inherit-1",
                "inherit-2",
                {"name": "override", "build_config": {"vars": {"key": "value"}}},
                "inherit-3",
            ]
        }

        result = resolve_image_config("inherit-3").build_config

        assert result.template == "test.pkr.hcl"  # From base
        assert result.vars["key"] == "value"  # From override

    @patch("osw_builder.settings.settings")
    def test_target_is_override_point(self, mock_settings):
        """Test when target image is itself an override point."""
        mock_settings.branches = {
            "test": [
                {"name": "base", "build_config": {"template": "base.pkr.hcl"}},
                {"name": "target", "build_config": {"vars": {"new": "value"}}},
            ]
        }

        result = resolve_image_config("target").build_config

        assert result.template == "base.pkr.hcl"
        assert result.vars["new"] == "value"


class TestWindowsCompatibility:
    """Test that Windows builds work with inheritance system."""

    @patch("osw_builder.settings.settings")
    def test_windows_inheritance(self, mock_settings):
        """Test Windows branch inheritance."""
        mock_settings.branches = {
            "master": [
                {
                    "name": "win95",
                    "build_config": {
                        "template": "windows.pkr.hcl",
                        "varfiles": ["windows.pkrvars.hcl"],
                        "vars": {"answerfile_path": "./answer_files/windows/Autounattend.xml"},
                    },
                },
                "win98",
                "winME",
                {"name": "win10-1507", "build_config": {"vars": {"key": "VK7JG-NPHTM-C97JM-9MPGT-3V66T"}}},
                "win10-1511",
            ]
        }

        result = resolve_image_config("win10-1511").build_config

        assert result.template == "windows.pkr.hcl"
        assert result.varfiles == ["windows.pkrvars.hcl"]
        assert result.vars["answerfile_path"] == "./answer_files/windows/Autounattend.xml"
        assert result.vars["key"] == "VK7JG-NPHTM-C97JM-9MPGT-3V66T"
