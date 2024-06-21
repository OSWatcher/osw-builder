from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path

from appdirs import AppDirs

import osw_builder as root_package

APPDIRS = AppDirs("osw-builder", "OSWatcher")


def read_vagrantfile_template() -> str:
    vagrantfile_template = files(root_package).joinpath("vagrant", "vagrantfile_template")
    with as_file(vagrantfile_template) as path:
        return Path(path).read_text()


@contextmanager
def prepare_vagrantfile(box_name: str):
    box_dir = Path(APPDIRS.user_data_dir) / box_name
    box_dir.mkdir(parents=True, exist_ok=True)
    vagrantfile = Path(box_dir) / "Vagrantfile"
    with open(vagrantfile, "w") as f:
        f.write(read_vagrantfile_template().format(box_name=box_name))
        f.flush()
        yield Path(box_dir)
