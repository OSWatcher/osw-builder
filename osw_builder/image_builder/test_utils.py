import xml.etree.ElementTree as ET
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import MagicMock, patch

import pytest

from .autounattend import WindowsAutounattend
from .build import build_docker_config, build_packer_cmdline, docker_packer_runner
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


@pytest.mark.parametrize(
    "template,packer_args,expected_vars",
    [
        ("windows.pkr.hcl", [], []),
        ("ubuntu.pkr.hcl", ["cpus=2"], ["-var", "cpus=2"]),
        ("windows.pkr.hcl", ["memory=8192", "cpus=4"], ["-var", "memory=8192", "-var", "cpus=4"]),
    ],
)
def test_build_packer_cmdline_parametrized(template, packer_args, expected_vars):
    """Parametrized test for different packer command line scenarios."""
    result = build_packer_cmdline(template, packer_args)

    # Check base command structure
    assert result[:7] == [
        "build",
        "-only",
        "qemu.vm",
        "-var-file",
        "docker.pkrvars.hcl",
        "-var-file",
        "vars.pkrvars.hcl",
    ]

    # Check variable arguments
    var_section = result[7:-1]  # Everything except the template at the end
    assert var_section == expected_vars

    # Check template is last
    assert result[-1] == template


@patch("osw_builder.image_builder.build.docker.from_env")
@patch("builtins.open")
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

    docker_config = {"image": "test:latest", "command": ["build", "test.pkr.hcl"]}

    # Test successful execution
    with docker_packer_runner(docker_config, network=True):
        pass

    # Verify interactions
    mock_client.images.pull.assert_called_once()
    mock_client.containers.run.assert_called_once_with(**docker_config)
    mock_container.wait.assert_called_once()
    mock_container.remove.assert_called_once_with(force=True)


@patch("osw_builder.image_builder.build.docker.from_env")
@patch("builtins.open")
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


@patch("osw_builder.image_builder.build.docker.from_env")
@patch("builtins.open")
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


@patch("osw_builder.image_builder.build.docker.from_env")
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


@pytest.fixture
def autounattend_files():
    """Get all Autounattend.xml files in the project."""
    packer_templates_dir = Path(__file__).parent / "packer-templates" / "answer_files"
    xml_files = list(packer_templates_dir.glob("**/Autounattend.xml"))
    if not xml_files:
        # If not found in relative path, try from project root
        project_root = Path(__file__).parent.parent
        packer_templates_dir = project_root / "packer-templates" / "answer_files"
        xml_files = list(packer_templates_dir.glob("**/Autounattend.xml"))
    return xml_files


@pytest.mark.parametrize(
    "xml_file",
    list((Path(__file__).parent / "packer-templates" / "answer_files").glob("**/Autounattend.xml"))
    or list((Path(__file__).parent.parent / "packer-templates" / "answer_files").glob("**/Autounattend.xml")),
)
def test_autounattend_xml_is_well_formed(xml_file):
    """Test that all Autounattend.xml files are well-formed XML."""
    try:
        with open(xml_file, "rb") as f:
            content = f.read()
            # This should not raise an exception
            ET.fromstring(content)
    except ET.ParseError as e:
        pytest.fail(f"XML file {xml_file} is not well-formed: {e}")
    except FileNotFoundError:
        pytest.fail(f"XML file {xml_file} not found")


def test_autounattend_xml_parsability_with_windowsautounattend():
    """Test that WindowsAutounattend can parse all XML files without errors."""
    packer_templates_dir = Path(__file__).parent / "packer-templates" / "answer_files"
    xml_files = list(packer_templates_dir.glob("**/Autounattend.xml"))
    if not xml_files:
        # If not found in relative path, try from project root
        project_root = Path(__file__).parent.parent
        packer_templates_dir = project_root / "packer-templates" / "answer_files"
        xml_files = list(packer_templates_dir.glob("**/Autounattend.xml"))

    if not xml_files:
        pytest.skip("No Autounattend.xml files found")

    errors = []
    for xml_file in xml_files:
        try:
            # Test that WindowsAutounattend can parse the file
            autounattend = WindowsAutounattend(xml_file)
            # Test that the tree was created successfully
            assert autounattend.tree is not None, f"Tree is None for {xml_file}"
            # Test that we can access the root element
            root = autounattend.tree.getroot()
            assert root is not None, f"Root element is None for {xml_file}"
        except Exception as e:
            errors.append(f"{xml_file}: {e}")

    if errors:
        pytest.fail("XML parsing errors found:\n" + "\n".join(errors))
