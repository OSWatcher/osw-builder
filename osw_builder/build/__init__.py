from importlib.resources import as_file, files
from pathlib import Path

import osw_builder as root_package


# Access the packer-templates directory
def get_packer_templates_dir():
    packer_templates = files(root_package).joinpath("packer-templates")
    with as_file(packer_templates) as path:
        return Path(path)


PACKER_TEMPLATES_DIR = get_packer_templates_dir()
OUTPUT_QEMU_DIR = PACKER_TEMPLATES_DIR / "output"
PACKER_DOCKER_AUTOUNATTEND_WIN10_PATH = "/packer/answer_files/10/Autounattend.xml"
PACKER_TEMPLATES_IMAGE = "ghcr.io/oswatcher/packer-templates:latest"

DOMAIN_MEMORY = 4096
WINDOWS_TEMPLATE = "windows.pkr.hcl"
