from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path
from tempfile import TemporaryDirectory

import osw_builder as root_package


def read_vagrantfile_template() -> str:
    vagrantfile_template = files(root_package).joinpath("vagrant", "vagrantfile_template")
    with as_file(vagrantfile_template) as path:
        return Path(path).read_text()


@contextmanager
def prepare_vagrantfile(box_name: str):
    with TemporaryDirectory() as tmp_dir:
        vagrantfile = Path(tmp_dir) / "Vagrantfile"
        with open(vagrantfile, "w") as f:
            f.write(read_vagrantfile_template().format(box_name=box_name))
            f.flush()
            yield Path(tmp_dir)
