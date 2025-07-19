"""Ubuntu preseed.cfg response file handler"""

from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, Optional, TextIO, Union

if TYPE_CHECKING:
    from ..settings import BuildConfig

from .response_files import ResponseFile


class UbuntuPreseed(ResponseFile):
    """Handler for Ubuntu preseed.cfg response files"""

    def __init__(self, preseed_path: Optional[Union[str, Path]]):
        # Skip super().__init__() to avoid file existence check - Ubuntu uses http_content
        self.response_file_path = Path(preseed_path) if preseed_path is not None else None
        self.tmp_dir: Optional[TemporaryDirectory] = None
        self.tmp_preseed: Optional[Path] = None
        self.tmp_preseed_f: Optional[TextIO] = None

    def __enter__(self) -> "UbuntuPreseed":
        self.tmp_dir = TemporaryDirectory()
        self.tmp_preseed = Path(self.tmp_dir.name) / "preseed.cfg"
        self.tmp_preseed_f = open(self.tmp_preseed, "w")
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
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
    def docker_path(self) -> None:
        """Return None - preseed files are served via http_content, no Docker mounting needed"""
        return None

    @property
    def varfile_key(self) -> str:
        """Return the varfile key for preseed files"""
        return "answerfile_path"

    def configure(self, build_config: "BuildConfig"):
        # nothing to do, templating is done by Packer http_content
        pass

    def write(self):
        return super().write()
