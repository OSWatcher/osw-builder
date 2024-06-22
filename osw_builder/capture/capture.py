import logging
from pathlib import Path

from neogit.service import Neogit

from .guest_filesystem import LibguestFSMnt


def capture_neogit(qcow_path: Path, vm_name: str, debug: bool = False):
    with LibguestFSMnt(qcow_path, local=True, readonly=True) as local_mnt:
        logging.debug("Local mountpoint: %s", local_mnt)
        # ensure init
        neo = Neogit(debug=debug)
        neo.init()
        logging.info("Running Neogit capture on %s", vm_name)
        neo.commit(vm_name, Path(local_mnt))
