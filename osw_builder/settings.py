from pathlib import Path
from typing import Any, Dict, List, Optional

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

    template: Optional[str] = None
    varfiles: List[str] = []
    vars: Dict[str, Any] = {}
    network: bool = False
    extra_firstlogin_cmds: Optional[List[str]] = None
    key: Optional[str] = None
    image_name: Optional[str] = None

    def to_packer_cmdline(self, iso_url: str, checksum: str, packer_args: List[str]) -> List[str]:
        """Export BuildConfig as Packer command line arguments."""
        assert self.template is not None, "template is required for Packer builds"

        cmdline = ["build", "-only", "qemu.vm"]

        # Add docker varfile first (essential for Docker environment)
        cmdline.extend(["-var-file", "docker.pkrvars.hcl"])

        # Add varfiles from BuildConfig
        for varfile in self.varfiles:
            cmdline.extend(["-var-file", varfile])

        # Add runtime variables (iso_url, sha1)
        cmdline.extend(["-var", f"iso_url={iso_url}"])
        cmdline.extend(["-var", f"iso_checksum={checksum}"])
        cmdline.extend(["-var", f"vm_name={self.template.replace('.pkr.hcl', '')}"])

        # Add BuildConfig variables
        for key, value in self.vars.items():
            # Convert Python boolean to lowercase string for Packer
            if isinstance(value, bool):
                value = str(value).lower()
            if isinstance(value, list):
                import json

                value = json.dumps(value)
            cmdline.extend(["-var", f"{key}={value}"])

        # Add additional packer arguments
        for arg in packer_args:
            cmdline.extend(["-var", arg])

        # Add template
        cmdline.append(self.template)

        return cmdline

    def to_docker_volumes(
        self, response_file, packer_home_cache: Path, packer_templates_dir: Path
    ) -> Dict[str, Dict[str, str]]:
        """Export BuildConfig as Docker volume configuration."""
        volumes = {
            str(packer_home_cache): {"bind": "/cache", "mode": "rw"},
            str(packer_templates_dir): {"bind": "/packer", "mode": "rw"},
        }

        # Mount response file only if docker_path indicates mounting is needed
        docker_path = response_file.docker_path
        if docker_path:
            volumes[str(response_file.tmp_path)] = {"bind": docker_path, "mode": "ro"}

        # Add varfiles from BuildConfig
        for varfile in self.varfiles:
            varfile_path = packer_templates_dir / varfile
            volumes[str(varfile_path)] = {"bind": f"/packer/{varfile}", "mode": "ro"}

        return volumes


@define
class RuntimeConfig:
    """Runtime behavior configuration resolved through inheritance."""

    search_updates: Optional[bool] = None
    idle: Optional[bool] = None
    apply_updates: Optional[bool] = None


@define
class ResolvedConfig:
    """Complete resolved configuration containing both build and runtime config."""

    build_config: BuildConfig
    runtime_config: RuntimeConfig


def _image_in_branch(branch_items: List, target_image: str) -> bool:
    """Check if target image exists in branch items."""
    for item in branch_items:
        if isinstance(item, dict) and item.get("name") == target_image:
            return True
        elif isinstance(item, str) and item == target_image:
            return True
    return False


def resolve_image_config(target_image: str) -> ResolvedConfig:
    """
    Resolve both build and runtime configuration using chronological inheritance.

    Args:
        target_image: Name of the target image to resolve config for

    Returns:
        ResolvedConfig: Complete resolved configuration with build_config and runtime_config

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
    return _resolve_full_inheritance(branch_items, target_image, branch_name)


def _resolve_full_inheritance(branch_items: List, target_image: str, branch_name: str) -> ResolvedConfig:
    """Apply chronological inheritance to resolve complete configuration."""
    template = None
    varfiles = []
    vars_dict = {}
    build_config_dict = {}
    runtime_config_dict = {}

    for item in branch_items:
        # Check if this item has build_config
        if isinstance(item, dict) and "build_config" in item:
            build_config = item["build_config"]

            # Apply build_config (replace strategy for template/varfiles, merge for vars)
            if "template" in build_config:
                template = build_config["template"]

            if "varfiles" in build_config:
                varfiles = build_config["varfiles"].copy()  # Replace, don't extend

            if "vars" in build_config:
                vars_dict.update(build_config["vars"])  # Merge individual keys

            # Dict update for other build_config fields (network, extra_firstlogin_cmds)
            for key, value in build_config.items():
                if key not in ["template", "varfiles", "vars"]:
                    build_config_dict[key] = value

        # Handle runtime_config with simple dict update
        if isinstance(item, dict) and "runtime_config" in item:
            runtime_config_dict.update(item["runtime_config"])

        # Stop if this is our target image
        if isinstance(item, dict) and item.get("name") == target_image:
            break
        elif isinstance(item, str) and item == target_image:
            break

    return ResolvedConfig(
        build_config=BuildConfig(template=template, varfiles=varfiles, vars=vars_dict, **build_config_dict),
        runtime_config=RuntimeConfig(**runtime_config_dict),
    )
