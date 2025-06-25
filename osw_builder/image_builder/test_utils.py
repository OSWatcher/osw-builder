from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import Mock, patch, MagicMock
import pytest
import docker

from .build import build_docker_config, build_docker_volumes, build_packer_cmdline, docker_packer_runner
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


def test_build_docker_config_no_network():
    """Test Docker config with network disabled."""
    volumes = {}
    cmdline = ["build"]
    network = False

    result = build_docker_config(volumes, cmdline, network)

    assert result["network_disabled"] is True


@pytest.mark.parametrize("template,packer_args,expected_vars", [
    ("windows.pkr.hcl", [], []),
    ("ubuntu.pkr.hcl", ["cpus=2"], ["-var", "cpus=2"]),
    ("windows.pkr.hcl", ["memory=8192", "cpus=4"], ["-var", "memory=8192", "-var", "cpus=4"]),
])
def test_build_packer_cmdline_parametrized(template, packer_args, expected_vars):
    """Parametrized test for different packer command line scenarios."""
    result = build_packer_cmdline(template, packer_args)
    
    # Check base command structure
    assert result[:7] == ["build", "-only", "qemu.vm", "-var-file", "docker.pkrvars.hcl", "-var-file", "vars.pkrvars.hcl"]
    
    # Check variable arguments
    var_section = result[7:-1]  # Everything except the template at the end
    assert var_section == expected_vars
    
    # Check template is last
    assert result[-1] == template


@patch.dict('os.environ', {'GHCR_TOKEN': 'test_token'})
@patch('osw_builder.image_builder.build.docker.from_env')
@patch('builtins.open')
def test_docker_packer_runner_success(mock_open, mock_docker_from_env):
    """Test successful Docker container execution."""
    # Setup mocks
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_docker_from_env.return_value = mock_client
    mock_client.containers.run.return_value = mock_container
    mock_container.logs.return_value = [b"Packer log line 1\n", b"Packer log line 2\n"]
    mock_container.wait.return_value = {"StatusCode": 0}
    
    mock_file = MagicMock()
    mock_open.return_value.__enter__.return_value = mock_file
    
    docker_config = {
        "image": "test:latest",
        "command": ["build", "test.pkr.hcl"]
    }
    
    # Test successful execution
    with docker_packer_runner(docker_config, network=True):
        pass
    
    # Verify interactions
    mock_client.login.assert_called_once_with(username="oswatcher", password="test_token", registry="ghcr.io")
    mock_client.images.pull.assert_called_once()
    mock_client.containers.run.assert_called_once_with(**docker_config)
    mock_container.wait.assert_called_once()
    mock_container.remove.assert_called_once_with(force=True)


@patch.dict('os.environ', {'GHCR_TOKEN': 'test_token'})
@patch('osw_builder.image_builder.build.docker.from_env')
@patch('builtins.open')
def test_docker_packer_runner_failure(mock_open, mock_docker_from_env):
    """Test Docker container execution failure."""
    # Setup mocks
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_docker_from_env.return_value = mock_client
    mock_client.containers.run.return_value = mock_container
    mock_container.logs.return_value = [b"Packer failed\n"]
    mock_container.wait.return_value = {"StatusCode": 1}  # Non-zero exit code
    
    mock_file = MagicMock()
    mock_open.return_value.__enter__.return_value = mock_file
    
    docker_config = {"image": "test:latest", "command": ["build", "test.pkr.hcl"]}
    
    # Test failure scenario
    with pytest.raises(RuntimeError, match="Packer failed"):
        with docker_packer_runner(docker_config, network=False):
            pass
    
    # Verify cleanup still happens
    mock_container.remove.assert_called_once_with(force=True)


@patch.dict('os.environ', {'GHCR_TOKEN': 'test_token'})
@patch('osw_builder.image_builder.build.docker.from_env')
@patch('builtins.open')
def test_docker_packer_runner_no_network(mock_open, mock_docker_from_env):
    """Test Docker runner with network disabled."""
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_docker_from_env.return_value = mock_client
    mock_client.containers.run.return_value = mock_container
    mock_container.logs.return_value = [b"Success\n"]
    mock_container.wait.return_value = {"StatusCode": 0}
    
    mock_file = MagicMock()
    mock_open.return_value.__enter__.return_value = mock_file
    
    docker_config = {"image": "test:latest"}
    
    with docker_packer_runner(docker_config, network=False):
        pass
    
    # Verify no image pull when network is disabled
    mock_client.images.pull.assert_not_called()
    mock_client.login.assert_called_once()


@patch.dict('os.environ', {'GHCR_TOKEN': 'test_token'})
@patch('osw_builder.image_builder.build.docker.from_env')
def test_docker_packer_runner_cleanup_on_exception(mock_docker_from_env):
    """Test that container cleanup happens even when exceptions occur."""
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_docker_from_env.return_value = mock_client
    mock_client.containers.run.return_value = mock_container
    mock_container.logs.side_effect = Exception("Network error")
    
    docker_config = {"image": "test:latest"}
    
    # Test that exceptions are propagated but cleanup still happens
    with pytest.raises(Exception, match="Network error"):
        with docker_packer_runner(docker_config, network=True):
            pass
    
    # Verify cleanup still happens
    mock_container.remove.assert_called_once_with(force=True)


def test_build_docker_volumes_multiple_response_files():
    """Test Docker volumes with different response file types."""
    # Test Windows response file
    mock_response_file = Mock()
    mock_response_file.tmp_path = Path("/tmp/autounattend.xml")
    mock_response_file.docker_path = "/packer/Autounattend.xml"
    
    result = build_docker_volumes(mock_response_file, "/tmp/vars.hcl", Path("/cache"))
    
    assert str(mock_response_file.tmp_path) in result
    assert result[str(mock_response_file.tmp_path)]["bind"] == "/packer/Autounattend.xml"
    
    # Test Ubuntu response file
    mock_response_file.docker_path = "/packer/preseed.cfg"
    result = build_docker_volumes(mock_response_file, "/tmp/vars.hcl", Path("/cache"))
    
    assert result[str(mock_response_file.tmp_path)]["bind"] == "/packer/preseed.cfg"


@patch('osw_builder.image_builder.build.docker.from_env')
def test_docker_packer_runner_missing_token(mock_docker_from_env):
    """Test that missing GHCR_TOKEN raises helpful error."""
    mock_client = MagicMock()
    mock_docker_from_env.return_value = mock_client
    
    docker_config = {"image": "test:latest"}
    
    # Test without GHCR_TOKEN in environment
    with patch.dict('os.environ', {}, clear=True):
        with pytest.raises(RuntimeError, match="GHCR_TOKEN environment variable is required"):
            with docker_packer_runner(docker_config, network=True):
                pass
    
    # Verify no Docker operations were attempted
    mock_client.login.assert_not_called()
    mock_client.containers.run.assert_not_called()
