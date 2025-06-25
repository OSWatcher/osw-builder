from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import Mock

import pytest

from .build import build_docker_config, build_docker_volumes, build_packer_cmdline
from .utils import compute_sha1sum


@pytest.fixture
def test_file():
    with NamedTemporaryFile() as temp_file:
        temp_file.write(b"This is a test file.")
        temp_file.flush()
        yield Path(temp_file.name)


def test_compute_sha1sum(test_file):
    # Compute the SHA1 sum for the test file
    result = compute_sha1sum(test_file)
    # Compare it to the expected SHA1 sum
    expected_sha1sum = "26d82f1931cbdbd83c2a6871b2cecd5cbcc8c26b"
    assert result == expected_sha1sum


def test_build_packer_cmdline():
    """Test pure function for building Packer command line."""
    template = "ubuntu.pkr.hcl"
    packer_args = ["cpus=4", "memory=4096"]

    result = build_packer_cmdline(template, packer_args)

    expected = [
        "build",
        "-only",
        "qemu.vm",
        "-var-file",
        "docker.pkrvars.hcl",
        "-var-file",
        "vars.pkrvars.hcl",
        "-var",
        "cpus=4",
        "-var",
        "memory=4096",
        "ubuntu.pkr.hcl",
    ]
    assert result == expected


def test_build_docker_volumes():
    """Test pure function for building Docker volumes."""
    # Create mock response file
    mock_response_file = Mock()
    mock_response_file.tmp_path = Path("/tmp/test_response")
    mock_response_file.docker_path = "/packer/preseed.cfg"

    tmp_varfile_path = "/tmp/test.pkrvars.hcl"
    packer_cache = Path("/home/user/.cache/packer")

    result = build_docker_volumes(mock_response_file, tmp_varfile_path, packer_cache)

    assert "/tmp/test_response" in result
    assert result["/tmp/test_response"]["bind"] == "/packer/preseed.cfg"
    assert tmp_varfile_path in result
    assert str(packer_cache) in result


def test_build_docker_config():
    """Test pure function for building Docker configuration."""
    volumes = {"/host/path": {"bind": "/container/path", "mode": "ro"}}
    cmdline = ["build", "template.pkr.hcl"]
    network = True

    result = build_docker_config(volumes, cmdline, network)

    assert result["volumes"] == volumes
    assert result["command"] == cmdline
    assert result["network_disabled"] is False  # network=True means network_disabled=False
    assert result["detach"] is True
    assert "/dev/kvm" in result["devices"]
