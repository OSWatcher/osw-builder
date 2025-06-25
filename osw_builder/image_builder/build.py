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
    packer_args: list[str] = None,
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
        yield run_packer(template, varfile_data, response_file, packer_args, network=network)


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
    
    try:
        # Login to registry
        dk_client.login(username="oswatcher", password=os.environ["GHCR_TOKEN"], registry="ghcr.io")
        
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
        packer_home_cache = Path.home() / ".cache" / "packer"
        packer_home_cache.mkdir(parents=True, exist_ok=True)

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
