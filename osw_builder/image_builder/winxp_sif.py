"""Windows XP WINNT.SIF response file handler"""

from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Optional, Union

from .response_files import ResponseFile


class WindowsXPSif(ResponseFile):
    """Handler for Windows XP WINNT.SIF response files"""

    def __init__(self, sif_path: Optional[Union[str, Path]]):
        super().__init__(sif_path)
        self.tmp_dir: Optional[TemporaryDirectory] = None
        self.tmp_sif: Optional[Path] = None
        self.tmp_sif_f = None

    def __enter__(self):
        self.tmp_dir = TemporaryDirectory()
        self.tmp_sif: Path = Path(self.tmp_dir.name) / "WINNT.SIF"
        self.tmp_sif_f = open(self.tmp_sif, "w")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.tmp_sif_f:
            self.tmp_sif_f.close()
        with suppress(FileNotFoundError):
            if self.tmp_sif:
                self.tmp_sif.unlink()
        if self.tmp_dir:
            self.tmp_dir.cleanup()

    @property
    def tmp_path(self) -> Path:
        """Return the temporary SIF file path"""
        if self.tmp_sif is None:
            raise RuntimeError("Context manager not entered - tmp_sif is None")
        return self.tmp_sif

    @property
    def docker_path(self) -> str:
        """Return the Docker container path for SIF file"""
        return "/packer/WINNT.SIF"

    @property
    def varfile_key(self) -> str:
        """Return the varfile key for SIF files"""
        return "answerfile_path"

    def configure(self, config_entry: dict, extra_commands: Optional[List[str]] = None):
        """Configure the SIF file - Windows XP doesn't support much customization"""
        # For Windows XP, we mostly just copy the original file
        # Limited configuration options compared to modern Windows autounattend
        self.write()

    def write(self):
        """Write the SIF file"""
        if self.response_file_path:
            # Copy original SIF file content
            with open(self.response_file_path, "r") as original:
                content = original.read()
            self.tmp_sif_f.write(content)
            self.tmp_sif_f.flush()
        else:
            # Create minimal SIF if none provided
            self.tmp_sif_f.write("[Data]\n")
            self.tmp_sif_f.write("AutoPartition=1\n")
            self.tmp_sif_f.write('MsDosInitiated="0"\n')
            self.tmp_sif_f.write('UnattendedInstall="Yes"\n')
            self.tmp_sif_f.flush()
