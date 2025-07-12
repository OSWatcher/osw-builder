from pathlib import Path
from typing import Dict, List

from attrs import define
from dynaconf import Dynaconf

CUR_DIR = Path(__file__).parent

settings = Dynaconf(
    envvar_prefix="OSW_BUILDER",
    environments=False,
    load_dotenv=True,
    # use absolute paths to import the conf from parent modules
    # from neogit.config import settings
    settings_files=[
        str(CUR_DIR / "default_settings.yaml"),
    ],
)


@define
class BuildConfig:
    """Strongly-typed build configuration resolved through inheritance."""

    template: str
    varfiles: List[str] = []
    vars: Dict[str, str] = {}

    def to_packer_cmdline(self, iso_url: str, sha1: str, packer_args: List[str]) -> List[str]:
        """Export BuildConfig as Packer command line arguments."""
        cmdline = ["build", "-only", "qemu.vm"]

        # Add docker varfile first (essential for Docker environment)
        cmdline.extend(["-var-file", "docker.pkrvars.hcl"])

        # Add varfiles from BuildConfig
        for varfile in self.varfiles:
            cmdline.extend(["-var-file", varfile])

        # Add runtime variables (iso_url, sha1)
        cmdline.extend(["-var", f"iso_url={iso_url}"])
        cmdline.extend(["-var", f"iso_checksum={sha1}"])
        cmdline.extend(["-var", f"iso_checksum_type=sha1"])
        cmdline.extend(["-var", f"vm_name={self.template.replace('.pkr.hcl', '')}"])

        # Add BuildConfig variables
        for key, value in self.vars.items():
            cmdline.extend(["-var", f"{key}={value}"])

        # Add additional packer arguments
        for arg in packer_args:
            cmdline.extend(["-var", arg])

        # Add template
        cmdline.append(self.template)

        return cmdline

    def to_docker_volumes(self, response_file, packer_home_cache, packer_templates_dir) -> Dict[str, Dict[str, str]]:
        """Export BuildConfig as Docker volume configuration."""
        volumes = {
            str(packer_home_cache): {"bind": "/cache", "mode": "rw"},
            str(packer_templates_dir): {"bind": "/output_parent", "mode": "rw"},
            str(response_file.tmp_path): {"bind": response_file.docker_path, "mode": "ro"},
        }

        # Add varfiles from BuildConfig
        for varfile in self.varfiles:
            varfile_path = packer_templates_dir / varfile
            volumes[str(varfile_path)] = {"bind": f"/packer/{varfile}", "mode": "ro"}

        return volumes


def resolve_build_config(target_image: str) -> BuildConfig:
    """
    Resolve build configuration using chronological inheritance.

    Walks through all branches to find the target image, then applies
    chronological inheritance to resolve the complete build configuration.

    Args:
        target_image: Name of the target image to resolve config for

    Returns:
        BuildConfig: Resolved configuration with template, varfiles, vars

    Raises:
        ValueError: If image not found, found in multiple branches,
                   or first build_config lacks template
    """
    # Find which branch(es) contain the target image
    found_branches = []

    if not hasattr(settings, "branches") or not settings.branches:
        raise ValueError("No branches defined in configuration")

    for branch_name, branch_items in settings.branches.items():
        if _image_in_branch(branch_items, target_image):
            found_branches.append(branch_name)

    # Ensure image is found in exactly one branch
    if not found_branches:
        raise ValueError(f"Image '{target_image}' not found in any branch")

    if len(found_branches) > 1:
        raise ValueError(f"Image '{target_image}' found in multiple branches: {found_branches}")

    branch_name = found_branches[0]
    branch_items = settings.branches[branch_name]

    # Apply chronological inheritance
    return _resolve_inheritance(branch_items, target_image, branch_name)


def _image_in_branch(branch_items: List, target_image: str) -> bool:
    """Check if target image exists in branch items."""
    for item in branch_items:
        if isinstance(item, dict) and item.get("name") == target_image:
            return True
        elif isinstance(item, str) and item == target_image:
            return True
    return False


def _resolve_inheritance(branch_items: List, target_image: str, branch_name: str) -> BuildConfig:
    """Apply chronological inheritance to resolve build configuration."""
    template = None
    varfiles = []
    vars_dict = {}
    first_build_config_seen = False

    for item in branch_items:
        # Check if this item has build_config
        if isinstance(item, dict) and "build_config" in item:
            build_config = item["build_config"]

            # Validate first build_config has template
            if not first_build_config_seen:
                if "template" not in build_config:
                    raise ValueError(f"First build_config in branch '{branch_name}' must define template")
                first_build_config_seen = True

            # Apply configuration (replace strategy for template/varfiles, merge for vars)
            if "template" in build_config:
                template = build_config["template"]

            if "varfiles" in build_config:
                varfiles = build_config["varfiles"].copy()  # Replace, don't extend

            if "vars" in build_config:
                vars_dict.update(build_config["vars"])  # Merge individual keys

            # Stop if this is our target image
            if item.get("name") == target_image:
                break

        # Check if we've reached our target (string form)
        elif isinstance(item, str) and item == target_image:
            break

    # Validate we found at least one build_config
    if template is None:
        raise ValueError(f"No build_config found in branch '{branch_name}'")

    return BuildConfig(template=template, varfiles=varfiles, vars=vars_dict)
