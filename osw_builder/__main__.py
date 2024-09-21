#!/usr/bin/env python3

"""
Usage:
    builder.py capture_os <os_name> [options] [--var <packer_args>...]
    builder.py (-h | --help)

Arguments:
    <os_name>                           Name of the OS to capture (optional)

Options:
    -h --help                           Display this message
    -d --debug                          Enable debug output
    -c --connection=<URI>               Specify a libvirt URI [Default: qemu:///session]
    --destroy                           Destroy the VM after build
    --updates=<UP_ANSWER>               Apply branch updates [Default: yes]
    --search-updates=<SEARCH_ANSWER>    Search for updates [Default: yes]
    --var <packer_args>...              Extra packer arguments
"""


import logging
import time
from contextlib import ExitStack, suppress

from docopt import docopt
from winupdate.winupdate import UpdateNotInstalledError, WinUpdate

from osw_builder import vagrant
from osw_builder.build import build_image
from osw_builder.capture import capture_neogit, create_branch
from osw_builder.settings import settings

from .snapshot import Snapshot

BUILD_SNAPSHOT = Snapshot("BUILD", "Build state")
IDLE_SNAPSHOT = Snapshot("IDLE", "Idle state (10 min)")
LIBVIRT_URI = "qemu:///session"
BLACKLISTED_UPDATES = ["4462939", "2267602"]
# win10-rs2-1703.15063.0: 4462939
# 2267602 causes issues but still returns as installed, so can be installed twice or more


def str2bool(v):
    return v.lower() in ("yes", "true", "t", "1")


def init_logger(debug=False):
    formatter = "%(asctime)s %(levelname)s:%(name)s:%(message)s"
    logging_level = logging.INFO
    if debug:
        logging_level = logging.DEBUG
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("docker").setLevel(logging.WARNING)
    logging.basicConfig(level=logging_level, format=formatter)


def capture_os(os_name, args):
    logging.info("Capturing OS %s", os_name)
    box_name = os_name

    packer_args = args["--var"]
    destroy = args["--destroy"]
    apply_updates = str2bool(args["--updates"])
    search_updates = str2bool(args["--search-updates"])

    try:
        entry = next((entry for entry in settings["images"] if entry["name"] == os_name))
    except StopIteration:
        raise RuntimeError("Could not find OS name")

    template = entry["template"]
    varfile = entry["varfile"]
    description = entry["description"]
    extra_firstlogin_cmds = entry["extra_firstlogin_cmds"]

    with ExitStack() as ex:
        if not vagrant.box_exists(box_name):
            image = ex.enter_context(build_image(template, varfile, entry, extra_firstlogin_cmds, packer_args))
            vagrant.box_add(image, name=box_name)

        # prepare vagrant env
        vagrant_dir = ex.enter_context(vagrant.prepare_vagrantfile(box_name))
        logging.info("Vagrant dir: %s", vagrant_dir)
        if destroy:
            ex.enter_context(vagrant.ensure_destroyed(vagrant_dir))
        vm, state = vagrant.status(vagrant_dir)
        logging.info("VM state: %s", state)
        if state == vagrant.MachineStateEnum.NOT_CREATED:
            # define the VM
            # ensure atomicity
            with vagrant.ensure_destroyed(vagrant_dir, only_on_error=True):
                logging.info("Defining VM")
                vagrant.define(vagrant_dir)
                vagrant.snapshot_save(vagrant_dir, BUILD_SNAPSHOT.to_raw_tag())

        # get the qcow path
        qcow_path = vagrant.get_qcow_path(box_name, uri=LIBVIRT_URI)
        logging.debug("Qcow path: %s", qcow_path)

        # restore build snapshot
        vagrant.snapshot_restore(vagrant_dir, BUILD_SNAPSHOT.to_raw_tag())
        # use description from default_settings.yaml just for build snapshot
        build_commit = capture_neogit(qcow_path, box_name, unique=True, desc=description)

        # create branch
        branch_name = box_name
        with suppress(ValueError):
            create_branch(
                branch_name,
                build_commit,
            )

        if not apply_updates:
            return

        # loop through the snapshot list, and assert that the first one is the build snapshot
        snap_list = vagrant.snapshot_list(vagrant_dir, qcow_path)
        assert snap_list[0].Tag == BUILD_SNAPSHOT.to_raw_tag()

        # check and capture IDLE state
        if len(snap_list) < 2:
            logging.info("No IDLE snapshot found. Vagrant up VM")
            with vagrant.up_down_ctxt(vagrant_dir):
                # 10 min
                logging.info("Waiting for 10 minutes")
                time.sleep(10 * 60)
            vagrant.snapshot_save(vagrant_dir, IDLE_SNAPSHOT.to_raw_tag())
        vagrant.snapshot_restore(vagrant_dir, IDLE_SNAPSHOT.to_raw_tag())
        capture_neogit(qcow_path, IDLE_SNAPSHOT.name, branch_name, unique=True, desc=IDLE_SNAPSHOT.description)

        # iterate after 'build' and 'IDLE' snapshot
        for raw_snap in snap_list[2:]:
            vagrant.snapshot_restore(vagrant_dir, raw_snap.Tag)
            snap = Snapshot.from_raw_tag(raw_snap.Tag)
            capture_neogit(qcow_path, snap.name, branch_name, unique=True, desc=snap.description)

        if not search_updates:
            return
        # take last snapshot
        previous_raw_snap = snap_list[-1].Tag
        # apply latest winupdates
        with vagrant.up_down_ctxt(vagrant_dir):
            logging.info("Searching for Windows Updates")
            winrm_config = vagrant.winrm_config(vagrant_dir)
            win_update = WinUpdate(winrm_config.HostName, debug_lvl=1)
            for index, update in enumerate(win_update.search()):
                if update.kb[0] in BLACKLISTED_UPDATES:
                    logging.warning("Blacklisted update found, skipping")
                    continue
                kb_name = f"KB-{update.kb[0]}"
                logging.info("[%s][%s] %s", index + 1, kb_name, update.title)
                try:
                    with vagrant.up_down_ctxt(vagrant_dir):
                        win_update.apply_update(update.id, update.kb[0])
                except UpdateNotInstalledError:
                    logging.warning("Update not installed")
                    # restore previous snapshot
                    vagrant.snapshot_restore(vagrant_dir, previous_raw_snap)
                else:
                    # SUCCESS !
                    snap = Snapshot(kb_name, update.title)
                    raw_tag = snap.to_raw_tag()
                    # take snapshot
                    vagrant.snapshot_save(vagrant_dir, raw_tag)
                    # update previous
                    previous_raw_snap = raw_tag
                    capture_neogit(qcow_path, kb_name, branch_name, unique=True, desc=update.title)


def main(args):
    debug = args["--debug"]

    init_logger(debug)
    logging.debug(args)

    if args["capture_os"]:
        capture_os(args["<os_name>"], args)
        return


def entrypoint():
    args = docopt(__doc__)
    main(args)
