"""Ubuntu autoinstall response file handler"""

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from ..settings import BuildConfig

from .response_files import ResponseFile


class UbuntuAutoinstall(ResponseFile):
    """Handler for Ubuntu autoinstall directory with user-data and meta-data files"""

    def __init__(self, autoinstall_dir_path: Optional[Union[str, Path]]):
        # Skip super().__init__() to avoid file existence check - Ubuntu uses http_content
        self.response_file_path = Path(autoinstall_dir_path) if autoinstall_dir_path is not None else None
        self.tmp_dir: Optional[TemporaryDirectory] = None
        self.tmp_autoinstall_dir: Optional[Path] = None

    def __enter__(self):
        self.tmp_dir = TemporaryDirectory()
        self.tmp_autoinstall_dir = Path(self.tmp_dir.name)

        # Copy original autoinstall files to temporary directory
        if self.response_file_path and self.response_file_path.exists():
            # Copy all files from source directory to temp directory
            for file_path in self.response_file_path.iterdir():
                if file_path.is_file():
                    shutil.copy2(file_path, self.tmp_autoinstall_dir)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.tmp_dir:
            self.tmp_dir.cleanup()

    @property
    def tmp_path(self) -> Path:
        """Return the temporary autoinstall directory path"""
        if self.tmp_autoinstall_dir is None:
            raise RuntimeError("Context manager not entered - tmp_autoinstall_dir is None")
        return self.tmp_autoinstall_dir

    @property
    def docker_path(self) -> None:
        """Return None - autoinstall files are served via http_content, no Docker mounting needed"""
        return None

    @property
    def varfile_key(self) -> str:
        """Return the varfile key for autoinstall files"""
        return "answerfile_path"

    def configure(self, build_config: "BuildConfig"):
        """Configure the autoinstall files - customize user-data with config values"""
        # nothing to do, templating is done by Packer http_content
        pass

    def write(self):
        return super().write()
