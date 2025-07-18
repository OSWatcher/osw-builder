import logging
from pathlib import Path
from typing import Optional

from neogit.service import Neogit

from ..settings import settings
from .guest_filesystem import LibguestFSMnt


def capture_neogit(
    qcow_path: Path,
    vm_name: str,
    branch_name: Optional[str] = None,
    unique: bool = False,
    debug: bool = False,
    desc: Optional[str] = None,
    before: Optional[str] = None,
):
    if settings.skip_neogit:
        logging.info("Skipping Neogit capture on %s (skip_neogit flag is enabled)", vm_name)
        return None

    with LibguestFSMnt(qcow_path, local=True, readonly=True) as local_mnt:
        logging.debug("Local mountpoint: %s", local_mnt)
        # ensure init
        neo = Neogit(debug=debug)
        neo.init()
        logging.info("Running Neogit capture on %s", vm_name)
        return neo.commit(vm_name, Path(local_mnt), branch_name=branch_name, unique=unique, desc=desc, before=before)


def create_branch(branch_name: str, commit_hash: str):
    if settings.skip_neogit:
        logging.info("Skipping branch creation for %s (skip_neogit flag is enabled)", branch_name)
        return
    neo = Neogit()
    neo.create_branch(branch_name, commit_hash)
