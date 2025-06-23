#!/usr/bin/env python3

"""
Usage:
    builder.py capture_os <os_name> [options] [--var <packer_args>...] [--before=<commit>]
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
    --idle=<IDLE_ANSWER>                Capture IDLE state [Default: yes]
    --var <packer_args>...              Extra packer arguments
"""


import logging
import shutil
import time
from contextlib import ExitStack, suppress
from pathlib import Path

from docopt import docopt
from winupdate.winupdate import UpdateNotInstalledError, WinUpdate

from osw_builder import vagrant
from osw_builder.build import build_image
from osw_builder.capture import capture_neogit, create_branch
from osw_builder.services.capture_service import CaptureService
from osw_builder.settings import settings

from .snapshot import Snapshot

BUILD_SNAPSHOT = Snapshot("BUILD", "Build state")
IDLE_SNAPSHOT = Snapshot("IDLE", "Idle state (10 min)")
LIBVIRT_URI = "qemu:///session"


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
    idle = str2bool(args["--idle"])
    before = args.get("--before")
    # Treat empty string as None
    before = before if before else None

    # Create service from settings
    capture_service = CaptureService.from_settings(settings)

    # Validate OS configuration
    os_configs = {entry["name"]: entry for entry in settings["images"]}
    capture_service.validate_os_configuration(os_name, os_configs)  # Validates OS exists
    entry = os_configs[os_name]  # Keep for backward compatibility with existing code

    template = entry.get("template")
    varfile = entry.get("varfile")
    description = entry["description"]
    extra_firstlogin_cmds = entry.get("extra_firstlogin_cmds")
    search_updates = entry.get("search_updates", search_updates)
    idle = entry.get("idle", idle)

    with ExitStack() as ex:
        if not vagrant.box_exists(box_name):
            # TODO: win11 hack
            network = entry.get("network", False)
            if entry["source"].endswith(".box"):
                image = entry["source"]
            else:
                image = ex.enter_context(
                    build_image(template, varfile, entry, extra_firstlogin_cmds, packer_args, network=network)
                )
            vagrant.box_add(image, name=box_name)

        # prepare vagrant env
        vagrant_dir = ex.enter_context(vagrant.prepare_vagrantfile(box_name))
        logging.info("Vagrant dir: %s", vagrant_dir)
        if destroy:
            ex.enter_context(vagrant.ensure_destroyed(vagrant_dir))
        # ensure we refresh the libvirt pool, just in case it has been manually modified
        # and isn't up to date
        vagrant.pool_refresh(uri=LIBVIRT_URI)
        vm, state = vagrant.status(vagrant_dir)
        logging.info("VM state: %s", state)
        if state == vagrant.MachineStateEnum.NOT_CREATED:
            # define the VM
            # ensure atomicity
            with vagrant.ensure_destroyed(vagrant_dir, only_on_error=True):
                logging.info("Defining VM")
                vagrant.define(vagrant_dir)
                # get the qcow path
                qcow_path = vagrant.get_qcow_path(box_name, uri=LIBVIRT_URI)
                # WORKAROUND: if source is box, we must copy the box qcow origninal source
                # and redefine all the internal snapshots in libvirt metadata
                if entry["source"].endswith(".box"):
                    logging.info("Copying box qcow to %s", qcow_path)
                    source_qcow = Path.home() / ".vagrant.d" / "boxes" / box_name / "0" / "libvirt" / "box_0.img"
                    shutil.copy(source_qcow, qcow_path)
                    # redefine all the internal snapshots in libvirt metadata
                    previous = None
                    for snap in vagrant.snapshot_list(vagrant_dir, qcow_path):
                        logging.info("Redefining snapshot %s in libvirt", snap.Tag)
                        vagrant.snapshot_libvirt_define(box_name, snap.Tag, parent=previous)
                        previous = snap.Tag
                # ensure build snapshot existence
                if not any(
                    [
                        snap
                        for snap in vagrant.snapshot_list(vagrant_dir, qcow_path)
                        if snap.Tag == BUILD_SNAPSHOT.to_raw_tag()
                    ]
                ):
                    vagrant.snapshot_save(vagrant_dir, BUILD_SNAPSHOT.to_raw_tag())
        # TODO: hack win11: add EFI loader
        if "win11" in box_name:
            vagrant.set_loader_efi(vagrant_dir)
        # get the qcow path
        qcow_path = vagrant.get_qcow_path(box_name, uri=LIBVIRT_URI)
        logging.debug("Qcow path: %s", qcow_path)

        snap_list = vagrant.snapshot_list(vagrant_dir, qcow_path)
        assert snap_list[0].Tag == BUILD_SNAPSHOT.to_raw_tag()
        # process build snapshot
        vagrant.snapshot_restore(vagrant_dir, BUILD_SNAPSHOT.to_raw_tag())
        # use description from default_settings.yaml just for build snapshot
        build_commit = capture_neogit(qcow_path, box_name, unique=True, desc=description, before=before)
        # pop it
        snap_list.pop(0)

        # ensure create OS branch
        branch_name = box_name
        with suppress(ValueError):
            create_branch(
                branch_name,
                build_commit,
            )

        apply_updates = entry.get("apply_updates", apply_updates)
        if not apply_updates:
            return

        # should we capture IDLE state ?
        if idle:
            if not snap_list:
                logging.info("No IDLE snapshot found. Vagrant up VM")
                # Create VM configuration for idle timeout
                timeout_seconds, timeout_msg = capture_service.create_idle_vm_configuration(box_name)
                with vagrant.up_down_ctxt(vagrant_dir):
                    logging.info(timeout_msg)
                    time.sleep(timeout_seconds)
                vagrant.snapshot_save(vagrant_dir, IDLE_SNAPSHOT.to_raw_tag())
            vagrant.snapshot_restore(vagrant_dir, IDLE_SNAPSHOT.to_raw_tag())
            capture_neogit(qcow_path, IDLE_SNAPSHOT.name, branch_name, unique=True, desc=IDLE_SNAPSHOT.description)

        # iterate after 'build' and 'IDLE' snapshot
        for raw_snap in snap_list:
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
                if capture_service.should_skip_windows_update(update.kb[0]):
                    logging.warning("Blacklisted update %s found, skipping", update.kb[0])
                    continue
                kb_name = f"KB-{update.kb[0]}"
                # update somehow already exists in snapshot list ?
                if any(Snapshot.from_raw_tag(snap.Tag).name == kb_name for snap in snap_list):
                    logging.warning("Found existing snapshot for candidate update %s. Skipping", kb_name)
                    continue
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
