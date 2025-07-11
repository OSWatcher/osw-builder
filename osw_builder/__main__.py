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

from osw_builder import vagrant
from osw_builder.capture import capture_neogit, create_branch
from osw_builder.image_builder import build_image
from osw_builder.settings import settings
from osw_builder.updates.core import OSType, detect_os_type
from osw_builder.updates.orchestrator import install_update, search_updates

from .snapshot import Snapshot

BUILD_SNAPSHOT = Snapshot("BUILD", "Build state")
IDLE_SNAPSHOT = Snapshot("IDLE", "Idle state (10 min)")
LIBVIRT_URI = "qemu:///session"
BLACKLISTED_UPDATES = ["4462939", "2267602", "5042099", "5012170"]
# win10-rs2-1703.15063.0: 4462939
# win11-22h2: "An update loop was detected, this could be caused by an update being rolled back during
# a reboot or the Windows Update API incorrectly reporting a failed update as being successful.
# Check the Windows Updates logs on the host to gather more information"
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
    search_updates_flag = str2bool(args["--search-updates"])
    idle = str2bool(args["--idle"])
    before = args.get("--before")
    # Treat empty string as None
    before = before if before else None
    try:
        entry = next((entry for entry in settings["images"] if entry["name"] == os_name))
    except StopIteration:
        raise RuntimeError("Could not find OS name")

    template = entry.get("template")
    varfile = entry.get("varfile")
    description = entry["description"]
    extra_firstlogin_cmds = entry.get("extra_firstlogin_cmds")
    search_updates_flag = entry.get("search_updates", search_updates_flag)
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
                vagrant.define_vm(vagrant_dir)
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
        snap_list.pop(0)  # remove build snapshot from the list

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
                logging.info("No IDLE snapshot found. Creating one...")
                with vagrant.up_down_ctxt(vagrant_dir):
                    # 10 min
                    logging.info("Waiting for 10 minutes")
                    time.sleep(10 * 60)
                vagrant.snapshot_save(vagrant_dir, IDLE_SNAPSHOT.to_raw_tag())

            vagrant.snapshot_restore(vagrant_dir, IDLE_SNAPSHOT.to_raw_tag())
            capture_neogit(qcow_path, IDLE_SNAPSHOT.name, branch_name, unique=True, desc=IDLE_SNAPSHOT.description)

        for raw_snap in snap_list:
            vagrant.snapshot_restore(vagrant_dir, raw_snap.Tag)
            snap = Snapshot.from_raw_tag(raw_snap.Tag)
            capture_neogit(qcow_path, snap.name, branch_name, unique=True, desc=snap.description)

        if not search_updates_flag:
            return

        # OS-agnostic update management
        os_type = detect_os_type(template)
        logging.info("Starting OS-agnostic update search and installation")

        # Take the most recent snapshot before updates
        if snap_list:
            previous_raw_snap = snap_list[-1].Tag
        elif idle:
            previous_raw_snap = IDLE_SNAPSHOT.to_raw_tag()
        else:
            previous_raw_snap = BUILD_SNAPSHOT.to_raw_tag()

        # First, search for available updates
        with vagrant.up_down_ctxt(vagrant_dir):
            try:
                available_updates = search_updates(vagrant_dir, os_type)
                logging.info("Found %d available updates:", len(available_updates))
                for i, update in enumerate(available_updates):
                    logging.info("  [%d] %s: %s", i + 1, update.name, update.description)

                if not available_updates:
                    logging.info("No updates available")
                    return
            except Exception as e:
                logging.error("Failed to search for updates: %s", e, exc_info=True)
                return

        # Install each update with full vagrant cycle
        for index, update in enumerate(available_updates):
            # Check blacklist for Windows updates
            if os_type == OSType.WINDOWS:
                kb_match = None
                if update.name.startswith("KB-"):
                    kb_match = update.name[3:]  # Remove "KB-" prefix
                if kb_match and kb_match in BLACKLISTED_UPDATES:
                    logging.warning("Blacklisted update found, skipping: %s", update.name)
                    continue

            # For Ubuntu, use date-based naming; for Windows, use update name
            if os_type == OSType.UBUNTU:
                from datetime import datetime

                date_str = datetime.now().strftime("%Y-%m-%d")
                snapshot_name = f"ubuntu-updates-{date_str}"
            else:
                snapshot_name = update.name

            logging.info("[%d/%d] Installing update: %s", index + 1, len(available_updates), update.name)

            try:
                # Full vagrant cycle: up -> install -> halt -> snapshot
                with vagrant.up_down_ctxt(vagrant_dir):
                    success = install_update(vagrant_dir, os_type, update)
                    if success:
                        logging.info("✅ Update %s installed successfully", update.name)
                    else:
                        logging.warning("❌ Update %s installation failed", update.name)
                        continue

                # Create snapshot after successful installation and halt
                snap = Snapshot(snapshot_name, update.description)
                vagrant.snapshot_save(vagrant_dir, snap.to_raw_tag())
                logging.info("📸 Snapshot created: %s", snapshot_name)

                # Capture git commit
                capture_neogit(qcow_path, snapshot_name, branch_name, unique=True, desc=update.description)

                # Update previous snapshot reference for next iteration
                previous_raw_snap = snap.to_raw_tag()

            except Exception as e:
                logging.error("Failed to install update %s: %s", update.name, e, exc_info=True)
                # Restore previous snapshot on error
                vagrant.snapshot_restore(vagrant_dir, previous_raw_snap)

        logging.info("All updates installation complete")
        return


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
