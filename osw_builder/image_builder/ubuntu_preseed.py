"""Ubuntu preseed.cfg response file handler"""

from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Optional, Union

from .response_files import ResponseFile


class UbuntuPreseed(ResponseFile):
    """Handler for Ubuntu preseed.cfg response files"""

    def __init__(self, preseed_path: Optional[Union[str, Path]]):
        super().__init__(preseed_path)
        self.tmp_dir: Optional[TemporaryDirectory] = None
        self.tmp_preseed: Optional[Path] = None
        self.tmp_preseed_f = None

    def __enter__(self):
        self.tmp_dir = TemporaryDirectory()
        self.tmp_preseed: Path = Path(self.tmp_dir.name) / "preseed.cfg"
        self.tmp_preseed_f = open(self.tmp_preseed, "w")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.tmp_preseed_f:
            self.tmp_preseed_f.close()
        with suppress(FileNotFoundError):
            if self.tmp_preseed:
                self.tmp_preseed.unlink()
        if self.tmp_dir:
            self.tmp_dir.cleanup()

    @property
    def tmp_path(self) -> Path:
        """Return the temporary preseed file path"""
        if self.tmp_preseed is None:
            raise RuntimeError("Context manager not entered - tmp_preseed is None")
        return self.tmp_preseed

    @property
    def docker_path(self) -> str:
        """Return the Docker container path for preseed file"""
        # must match the relative path in the default_settings.yaml
        return "/packer/answer_files/ubuntu/preseed.cfg"

    @property
    def varfile_key(self) -> str:
        """Return the varfile key for preseed files"""
        return "answerfile_path"

    def update_varfile_data(self, varfile_data: dict) -> None:
        varfile_data["http_directory"] = "./"

    def configure(self, config_entry: dict, extra_commands: Optional[List[str]] = None):
        """Configure the preseed file - just copy original for now"""
        self.write()

    def write(self):
        """Write the preseed file"""
        if self.response_file_path:
            # Copy original preseed file content
            with open(self.response_file_path, "r") as original:
                content = original.read()
            self.tmp_preseed_f.write(content)
        self.tmp_preseed_f.flush()
