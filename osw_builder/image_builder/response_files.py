"""Response file abstraction for different operating systems"""

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from pathlib import Path
from typing import List, Optional, Union


class ResponseFile(AbstractContextManager, ABC):
    """Abstract base class for OS response files (autounattend.xml, preseed.cfg, etc.)"""

    def __init__(self, response_file_path: Optional[Union[str, Path]]):
        self.response_file_path = None
        if response_file_path is not None:
            if isinstance(response_file_path, str):
                response_file_path = Path(response_file_path)
            if not response_file_path.exists():
                raise ValueError(f"File {response_file_path} does not exist")
            self.response_file_path = response_file_path

    @abstractmethod
    def __enter__(self):
        """Context manager entry"""
        pass

    @abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        pass

    @property
    @abstractmethod
    def tmp_path(self) -> Path:
        """Return the path to the temporary response file"""
        pass

    @property
    @abstractmethod
    def docker_path(self) -> str:
        """Return the Docker container path for this response file"""
        pass

    @property
    @abstractmethod
    def varfile_key(self) -> str:
        """Return the varfile key for this response file type"""
        pass

    def update_varfile_data(self, varfile_data: dict) -> None:
        """Update the varfile data with the Docker path"""
        varfile_data[self.varfile_key] = self.docker_path

    @abstractmethod
    def configure(self, config_entry: dict, extra_commands: Optional[List[str]] = None):
        """Configure the response file with the given configuration"""
        pass

    @abstractmethod
    def write(self):
        """Write the configured response file"""
        pass


def create_response_file(template: str, varfile: str, varfile_data: dict, packer_templates_dir: Path) -> ResponseFile:
    """Factory function to create the appropriate ResponseFile instance based on template and varfile"""
    from .autounattend import WindowsAutounattend
    from .ubuntu_preseed import UbuntuPreseed
    from .winxp_sif import WindowsXPSif

    # Auto-detect response file type based on template and varfile
    if template == "ubuntu.pkr.hcl":
        response_file_path = packer_templates_dir / varfile_data["answerfile_path"]
        return UbuntuPreseed(response_file_path)

    elif template == "windows.pkr.hcl":
        response_file_path = packer_templates_dir / varfile_data["answerfile_path"]

        # Only Windows XP uses SIF files, all other Windows versions use XML
        if "winxp" in varfile.lower():
            return WindowsXPSif(response_file_path)
        else:
            return WindowsAutounattend(response_file_path)

    else:
        raise ValueError(f"Unsupported template: {template}")
