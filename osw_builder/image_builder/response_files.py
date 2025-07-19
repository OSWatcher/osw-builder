"""Response file abstraction for different operating systems"""

from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from ..settings import BuildConfig


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
    def docker_path(self) -> Optional[str]:
        """Return the Docker container path if mounting is needed, None otherwise"""
        pass

    @abstractmethod
    def configure(self, build_config: "BuildConfig"):
        """Configure the response file with the given build configuration"""
        pass

    @abstractmethod
    def write(self):
        """Write the configured response file"""
        pass
