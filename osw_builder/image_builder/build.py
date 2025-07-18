import grp
import json
import logging
import os
import shutil
from contextlib import ExitStack, contextmanager, suppress
from importlib.resources import as_file, files
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Generator, Optional
from urllib.parse import urlparse

import docker
import hcl2

import osw_builder as root_package

from ..settings import BuildConfig
from .response_files import ResponseFile, create_response_file
from .utils import compute_sha1sum


# Access the packer-templates directory
def get_packer_templates_dir():
    packer_templates = files(root_package).joinpath("packer-templates")
    with as_file(packer_templates) as path:
        return Path(path)


PACKER_TEMPLATES_DIR = get_packer_templates_dir()
OUTPUT_QEMU_DIR = PACKER_TEMPLATES_DIR / "output"
PACKER_DOCKER_AUTOUNATTEND_PATH = "/packer/Autounattend.xml"
PACKER_DOCKER_AUTOUNATTEND_PATH_XP = "/packer/WINNT.SIF"
PACKER_TEMPLATES_IMAGE = "ghcr.io/oswatcher/packer-templates:latest"
WINDOWS_TEMPLATE = "windows.pkr.hcl"


def validate_source_and_compute_sha1(config_entry: dict) -> str:
    """validate the source URL and compute the SHA1 digest if needed"""
    source_url = config_entry["source"]
    parse_res = urlparse(source_url)
    if parse_res.scheme == "file":
        source_path = Path(parse_res.path)
        if not source_path.exists():
            raise FileNotFoundError("source file does not exist")
        logging.debug("Source: %s", source_url)
        logging.debug("Computing SHA1")
        sha1digest = compute_sha1sum(source_path)
    else:
        sha1digest = config_entry.get("sha1", None)
        if not sha1digest:
            raise RuntimeError("Invalid configuration: need to specify a SHA1 for URL sources")
    logging.debug("SHA1: %s", sha1digest)
    return sha1digest


def update_varfile(varfile_path: Path, source_url: str, sha1digest: str) -> dict:
    """update the varfile with the source URL and SHA1 digest"""
    with open(varfile_path) as varfile_f:
        varfile_data = hcl2.load(varfile_f)
    varfile_data["iso_url"] = source_url
    varfile_data["iso_checksum"] = sha1digest
    return varfile_data


@contextmanager
def write_temp_varfile(varfile_data: dict) -> Generator[str, None, None]:
    """write the varfile data to a temporary file in HCL2 like format and return the path"""
    with NamedTemporaryFile(mode="w", suffix=".pkrvars.hcl", delete=False) as tmp_f:
        for key, value in varfile_data.items():
            if isinstance(value, str):
                tmp_f.write(f'{key} = "{value}"\n')
            # Boolean are Integers in Python
            # check this first
            elif isinstance(value, bool):
                tmp_f.write(f"{key} = {str(value).lower()}\n")
            elif isinstance(value, int):
                tmp_f.write(f"{key} = {value}\n")
            elif isinstance(value, list):
                s = json.dumps(value)
                tmp_f.write(f"{key} = {s}\n")
        tmp_f.flush()
        yield tmp_f.name


@contextmanager
def ensure_cleanup_output():
    try:
        logging.info("Build: pre cleaning up")
        with suppress(FileNotFoundError):
            shutil.rmtree(OUTPUT_QEMU_DIR)
        yield
    except BaseException:
        logging.info("Build: error cleaning up")
        with suppress(FileNotFoundError):
            shutil.rmtree(OUTPUT_QEMU_DIR)
        raise


@contextmanager
def build_image(
    template: str,
    varfile: str,
    config_entry: dict,
    extra_firstlogin_cmds: Optional[list[str]],
    packer_args: Optional[list[str]] = None,
    network: bool = False,
) -> Generator[Path, None, None]:
    logging.info("Building image")
    sha1digest = validate_source_and_compute_sha1(config_entry)
    varfile_data = update_varfile(PACKER_TEMPLATES_DIR / varfile, config_entry["source"], sha1digest)

    with ExitStack() as ex:
        # Create appropriate response file handler based on template and varfile
        # Examples:
        # - template="windows.pkr.hcl", varfile="win10.pkrvars.hcl" -> WindowsAutounattend
        # - template="windows.pkr.hcl", varfile="winxp.pkrvars.hcl" -> WindowsXPSif
        # - template="ubuntu.pkr.hcl", varfile="ubuntu.pkrvars.hcl" -> UbuntuPreseed
        response_file = ex.enter_context(create_response_file(template, varfile, varfile_data, PACKER_TEMPLATES_DIR))

        # Configure response file with product keys, hostnames, etc.
        response_file.configure(config_entry, extra_firstlogin_cmds)

        # force packer cache, need network for that
        fake_run_packer(template, varfile_data, response_file, network=True)
        # enforce no network for now
        yield run_packer(template, varfile_data, response_file, packer_args or [], network=network)


def build_packer_cmdline(template: str, packer_args: list[str]) -> list[str]:
    """Build Packer command line arguments - pure function."""
    cmdline = [
        "build",
        "-only",
        "qemu.vm",
        "-var-file",
        "docker.pkrvars.hcl",
        "-var-file",
        "vars.pkrvars.hcl",
    ]

    # Add packer variable arguments
    for arg in packer_args:
        cmdline.extend(["-var", arg])

    # Add template
    cmdline.append(template)

    return cmdline


def build_docker_volumes(response_file: ResponseFile, tmp_varfile_path: str, packer_home_cache: Path) -> dict:
    """Build Docker volume configuration - pure function."""
    volumes = {
        str(packer_home_cache): {"bind": "/cache", "mode": "rw"},
        str(PACKER_TEMPLATES_DIR): {"bind": "/output_parent", "mode": "rw"},
        tmp_varfile_path: {"bind": "/packer/vars.pkrvars.hcl", "mode": "ro"},
    }

    # Add response file volume
    volumes[str(response_file.tmp_path)] = {"bind": response_file.docker_path, "mode": "ro"}

    return volumes


def build_docker_config(volumes: dict, cmdline: list[str], network: bool) -> dict:
    """Build Docker container run configuration - pure function."""
    # Get the group IDs for 'kvm' and 'sudo'
    kvm_group_id = grp.getgrnam("kvm").gr_gid
    sudo_group_id = grp.getgrnam("sudo").gr_gid

    return {
        "image": PACKER_TEMPLATES_IMAGE,
        "remove": True,
        "volumes": volumes,
        "devices": ["/dev/kvm"],
        "ports": {"5900/tcp": 5900},
        "user": f"{os.getuid()}:{os.getgid()}",
        "group_add": [sudo_group_id, kvm_group_id],
        "network_disabled": not network,
        "detach": True,
        "command": cmdline,
    }


@contextmanager
def docker_packer_runner(docker_config: dict, network: bool) -> Generator[None, None, None]:
    """Context manager for Docker container lifecycle management."""
    dk_client = docker.from_env()
    container = None

    # Check for required environment variable
    ghcr_token = os.environ.get("GHCR_TOKEN")
    if not ghcr_token:
        raise RuntimeError(
            "GHCR_TOKEN environment variable is required for Docker registry authentication. "
            "Please set GHCR_TOKEN to your GitHub Container Registry token."
        )

    try:
        # Login to registry
        dk_client.login(username="oswatcher", password=ghcr_token, registry="ghcr.io")

        # Pull the latest image if network is enabled
        if network:
            logging.info(f"Pulling the latest {PACKER_TEMPLATES_IMAGE} image")
            dk_client.images.pull(PACKER_TEMPLATES_IMAGE)

        # Create and start container
        logging.info("Running Packer")
        container = dk_client.containers.run(**docker_config)

        # Stream logs to file
        with open("packer-build.log", "a") as packer_log_f:
            for line in container.logs(stream=True):
                packer_log_f.write(line.decode())
                packer_log_f.flush()

        # Wait for completion and check exit code
        code = container.wait()
        if code["StatusCode"] != 0:
            raise RuntimeError("Packer failed")

        yield

    finally:
        # Guaranteed cleanup
        if container:
            with suppress(docker.errors.NotFound, docker.errors.APIError):
                container.remove(force=True)


def fake_run_packer(template: str, varfile_data: dict, response_file: ResponseFile, network: bool = True):
    logging.info("Fake Packer run (Force image download)")
    # Create fake varfile with impossible CPU count to force download failure
    fake_varfile_data = varfile_data.copy()
    fake_varfile_data["cpus"] = 999999

    with suppress(RuntimeError):
        # empty packer args, we don't want any cpu override here
        run_packer(template, fake_varfile_data, response_file, packer_args=[], network=network)


def run_packer(
    template: str, varfile_data: dict, response_file: ResponseFile, packer_args: list[str], network: bool
) -> Path:
    with ensure_cleanup_output():
        packer_home_cache = get_packer_home_cache()

        # Update varfile_data with response file Docker path
        response_file.update_varfile_data(varfile_data)

        # Create temporary varfile
        with write_temp_varfile(varfile_data) as tmp_varfile_path:
            # Build configuration using pure functions
            cmdline = build_packer_cmdline(template, packer_args)
            volumes = build_docker_volumes(response_file, tmp_varfile_path, packer_home_cache)
            docker_config = build_docker_config(volumes, cmdline, network)

            logging.debug("Volumes: %s", volumes)
            logging.debug("Running packer with command line: %s", cmdline)

            # Use Docker context manager for container lifecycle
            with docker_packer_runner(docker_config, network):
                # return the first file ending with .box in the output directory
                return OUTPUT_QEMU_DIR / [f for f in os.listdir(OUTPUT_QEMU_DIR) if f.endswith(".box")][0]


# New inheritance-based build functions


def get_packer_home_cache() -> Path:
    """Get Packer home cache directory, creating it if needed."""
    packer_home_cache = Path.home() / ".cache" / "packer"
    packer_home_cache.mkdir(parents=True, exist_ok=True)
    return packer_home_cache


# Note: build_packer_cmdline_from_build_config and build_docker_volumes_from_build_config
# functions have been replaced by BuildConfig.to_packer_cmdline() and BuildConfig.to_docker_volumes() methods


def create_response_file_from_answerfile_path(answerfile_path: str, packer_templates_dir: Path) -> ResponseFile:
    """Create response file from explicit answerfile_path."""
    from .autounattend import WindowsAutounattend
    from .ubuntu_autoinstall import UbuntuAutoinstall
    from .ubuntu_preseed import UbuntuPreseed
    from .winxp_sif import WindowsXPSif

    # Convert relative path to absolute
    if answerfile_path.startswith("./"):
        response_file_path = packer_templates_dir / answerfile_path[2:]
    else:
        response_file_path = packer_templates_dir / answerfile_path

    # Check if path is a directory (autoinstall) or file (preseed/autounattend/winxp)
    if response_file_path.is_dir():
        # Directory indicates Ubuntu autoinstall with user-data/meta-data files
        return UbuntuAutoinstall(response_file_path)

    # Determine response file type based on file extension
    file_extension = response_file_path.suffix.lower()
    filename = response_file_path.name.lower()

    if file_extension == ".cfg" or filename in ["preseed.cfg", "user-data"]:
        return UbuntuPreseed(response_file_path)
    elif file_extension == ".xml" or filename == "autounattend.xml":
        return WindowsAutounattend(response_file_path)
    elif file_extension == ".sif" or filename == "winnt.sif":
        return WindowsXPSif(response_file_path)
    else:
        raise ValueError(f"Unsupported response file type for: {response_file_path.name}")


@contextmanager
def build_image_with_inheritance(
    image_name: str,
    config_entry: dict,
    resolved_config,
    packer_args: Optional[list[str]] = None,
) -> Generator[Path, None, None]:
    """Build image using inheritance system - no template/varfile needed."""
    logging.info("Building image with inheritance: %s", image_name)

    # Use the resolved configuration passed from main
    build_config = resolved_config.build_config

    # Validate source and compute SHA1
    sha1digest = validate_source_and_compute_sha1(config_entry)

    with ExitStack() as ex:
        # Create response file from answerfile_path in BuildConfig
        answerfile_path = build_config.vars.get("answerfile_path")
        if not answerfile_path:
            raise ValueError(f"No answerfile_path defined in build configuration for {image_name}")

        response_file = ex.enter_context(
            create_response_file_from_answerfile_path(answerfile_path, PACKER_TEMPLATES_DIR)
        )

        # Configure response file with product keys, hostnames, etc.
        response_file.configure(build_config)

        # Build Packer command and Docker configuration using BuildConfig methods
        cmdline = build_config.to_packer_cmdline(
            iso_url=config_entry["source"], sha1=sha1digest, packer_args=packer_args or []
        )

        volumes = build_config.to_docker_volumes(
            response_file=response_file,
            packer_home_cache=get_packer_home_cache(),
            packer_templates_dir=PACKER_TEMPLATES_DIR,
        )

        logging.debug("Volumes: %s", volumes)
        logging.debug("Running packer with command line: %s", cmdline)

        # force packer cache, need network for that
        fake_run_packer_with_inheritance(build_config, response_file, config_entry["source"], sha1digest, network=True)
        # Use network setting from build_config
        yield run_packer_with_inheritance(
            build_config,
            response_file,
            config_entry["source"],
            sha1digest,
            packer_args or [],
            network=build_config.network,
        )


def fake_run_packer_with_inheritance(
    build_config: BuildConfig, response_file: ResponseFile, iso_url: str, sha1: str, network: bool
):
    """Fake run packer to force cache - inheritance version."""
    logging.info("Fake Packer run (Force image download)")

    with suppress(RuntimeError):
        # Use real ISO URL and SHA1 but with impossible CPU count to force build failure after download
        run_packer_with_inheritance(
            build_config=build_config,
            response_file=response_file,
            iso_url=iso_url,
            sha1=sha1,
            packer_args=["cpus=999999"],  # Impossible CPU count to force build failure
            network=network,
        )


def run_packer_with_inheritance(
    build_config: BuildConfig,
    response_file: ResponseFile,
    iso_url: str,
    sha1: str,
    packer_args: list[str],
    network: bool,
) -> Path:
    """Run packer using inheritance configuration."""
    with ensure_cleanup_output():
        packer_home_cache = get_packer_home_cache()

        # Build Packer command using BuildConfig with real values
        cmdline = build_config.to_packer_cmdline(iso_url=iso_url, sha1=sha1, packer_args=packer_args)

        # Build Docker volumes using BuildConfig
        volumes = build_config.to_docker_volumes(
            response_file=response_file, packer_home_cache=packer_home_cache, packer_templates_dir=PACKER_TEMPLATES_DIR
        )

        docker_config = build_docker_config(volumes, cmdline, network)

        logging.debug("Volumes: %s", volumes)
        logging.debug("Running packer with command line: %s", cmdline)

        # Use Docker context manager for container lifecycle
        with docker_packer_runner(docker_config, network):
            # return the first file ending with .box in the output directory
            return OUTPUT_QEMU_DIR / [f for f in os.listdir(OUTPUT_QEMU_DIR) if f.endswith(".box")][0]
