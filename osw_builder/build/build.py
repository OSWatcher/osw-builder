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

from .autounattend import Autounattend
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
                tmp_f.write(f'{key} = {str(value).lower()}\n')
            elif isinstance(value, int):
                tmp_f.write(f'{key} = {value}\n')
            elif isinstance(value, list):
                s = json.dumps(value)
                tmp_f.write(f'{key} = {s}\n')
        tmp_f.flush()
        yield tmp_f.name


def configure_autounattend(
    tmp_autounattend: Autounattend, config_entry: dict, extra_firstlogin_cmds: Optional[list[str]]
) -> None:
    """configure the autounattend file with the product key and image name from the config entry"""
    if "key" in config_entry:
        logging.debug("Changing Product Key to %s", config_entry["key"])
        tmp_autounattend.product_key = config_entry["key"]
    if "image_name" in config_entry:
        logging.debug("Selecting image %s", config_entry["image_name"])
        tmp_autounattend.image_name = config_entry["image_name"]
    if extra_firstlogin_cmds:
        for cmd in reversed(extra_firstlogin_cmds):
            tmp_autounattend.prepend_cmd(cmd)
    tmp_autounattend.write()


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

    auto_path = None
    if template == WINDOWS_TEMPLATE:
        auto_path = PACKER_TEMPLATES_DIR / varfile_data["autounattend"]

    with ExitStack() as ex:
        autounattend_tmp_path = None
        autounattend_docker_path = None
        if auto_path.suffix == '.xml':
            tmp_autounattend = ex.enter_context(Autounattend(auto_path))
            configure_autounattend(tmp_autounattend, config_entry, extra_firstlogin_cmds)
            varfile_data["autounattend"] = PACKER_DOCKER_AUTOUNATTEND_PATH
            autounattend_tmp_path = tmp_autounattend.autounattend_tmp_path
            autounattend_docker_path = PACKER_DOCKER_AUTOUNATTEND_PATH
        else:
            # winxp
            autounattend_tmp_path = auto_path
            varfile_data["autounattend"] = PACKER_DOCKER_AUTOUNATTEND_PATH_XP
            autounattend_docker_path = PACKER_DOCKER_AUTOUNATTEND_PATH_XP
        # /tmp/tmp0v1z7z1v.pkrvars.hcl
        tmp_varfile_path = ex.enter_context(write_temp_varfile(varfile_data))
        # force packer cache, need network for that
        fake_run_packer(tmp_varfile_path, autounattend_tmp_path, autounattend_docker_path, network=True)
        # enforce no network for now
        yield run_packer(tmp_varfile_path, autounattend_tmp_path, autounattend_docker_path, packer_args, network=network)


def fake_run_packer(varfile_path: str, autounattend_path: str, autounattend_docker_path: str, network: bool = True):
    logging.info("Fake Packer run (Force image download)")
    with NamedTemporaryFile(mode="w", suffix=".pkrvars.hcl", delete=False) as tmp_f_fake:
        with open(varfile_path) as original_varfile:
            for line in original_varfile:
                tmp_f_fake.write("cpus = 999999\n" if line.startswith("cpus =") else line)
        tmp_f_fake.flush()
        with suppress(RuntimeError):
            # empty packer args, we don't want any cpu override here
            run_packer(tmp_f_fake.name, autounattend_path, autounattend_docker_path, packer_args=[], network=network)


def run_packer(varfile: str, autounattend_host_path: str, autounattend_docker_path: str, packer_args: list[str], network: bool) -> Path:
    with ensure_cleanup_output():
        dk_client = docker.from_env()
        dk_client.login(username="oswatcher", password=os.environ["GHCR_TOKEN"], registry="ghcr.io")

        # Pull the latest image
        if network:
            logging.info(f"Pulling the latest {PACKER_TEMPLATES_IMAGE} image")
            dk_client.images.pull(PACKER_TEMPLATES_IMAGE)

        packer_home_cache = Path.home() / ".cache" / "packer"
        packer_home_cache.mkdir(parents=True, exist_ok=True)
        volumes = {
            packer_home_cache: {"bind": "/cache", "mode": "rw"},
            PACKER_TEMPLATES_DIR: {"bind": "/output_parent", "mode": "rw"},
            varfile: {"bind": "/packer/vars.pkrvars.hcl", "mode": "ro"},
            autounattend_host_path: {"bind": autounattend_docker_path, "mode": "ro"},
        }
        # Get the group IDs for 'kvm' and 'sudo'
        kvm_group_id = grp.getgrnam("kvm").gr_gid
        sudo_group_id = grp.getgrnam("sudo").gr_gid
        logging.debug("Volumes: %s", volumes)
        cmdline = [
            "build",
            "-only",
            "qemu.windows",
            "-var-file",
            "docker.pkrvars.hcl",
            "-var-file",
            "vars.pkrvars.hcl",
        ]

        var_packer_args = []
        for arg in packer_args:
            var_packer_args.extend(["-var", arg])

        cmdline.extend(var_packer_args)

        cmdline.append(WINDOWS_TEMPLATE)

        logging.debug("Running packer with command line: %s", cmdline)
        with open("packer-build.log", "a") as packer_log_f:
            logging.info("Running Packer")
            container = dk_client.containers.run(
                PACKER_TEMPLATES_IMAGE,
                remove=True,
                volumes=volumes,
                devices=["/dev/kvm"],
                ports={"5900/tcp": 5900},
                user=f"{os.getuid()}:{os.getgid()}",
                group_add=[sudo_group_id, kvm_group_id],
                network_disabled=not network,
                detach=True,
                command=cmdline,
            )
            try:
                for line in container.logs(stream=True):
                    packer_log_f.write(line.decode())
                    packer_log_f.flush()
                code = container.wait()
                if code["StatusCode"] != 0:
                    raise RuntimeError("Packer failed")
            finally:
                with suppress(docker.errors.NotFound, docker.errors.APIError):
                    container.remove(force=True)
        # return the fist file ending with .box in the output directory
        return OUTPUT_QEMU_DIR / [f for f in os.listdir(OUTPUT_QEMU_DIR) if f.endswith(".box")][0]
