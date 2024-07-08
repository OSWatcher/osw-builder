#!/usr/bin/env python3

"""
Usage: builder.py [options] [(--only-image=<NAME> | --from=<NAME>)] [--only-serie=<SERIE>...] [--var <packer_args>...]

Options:
    -h --help                           Display this message
    -d --debug                          Enable debug output
    -c --connection=<URI>               Specify a libvirt URI [Default: qemu:///session]
    -o --only-image=<NAME>              Build only image NAME
    -s --only-serie=<SERIE>             Build only serie SERIE
    -f --from=<NAME>                    Build images from NAME
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


def main(args):
    debug = args["--debug"]
    only_image = args["--only-image"]
    from_image = args["--from"]
    only_series = args["--only-serie"]
    packer_args = args["--var"]
    destroy = args["--destroy"]
    apply_updates = str2bool(args["--updates"])
    search_updates = str2bool(args["--search-updates"])

    init_logger(debug)
    logging.debug(args)

    filtered_serie_list = settings["series"]
    if only_series:
        filtered_serie_list = [serie for serie in settings["series"] if serie["name"] in only_series]
    for serie in filtered_serie_list:
        logging.info("Serie %s", serie["name"])
        # apply filter
        #   get all images
        filtered_image_list = serie["images"]
        if only_image:
            filtered_image_list = [entry for entry in serie["images"] if entry["name"] == only_image]
        elif from_image:
            from_index_list = [index for index, entry in enumerate(serie["images"]) if entry["name"] == from_image]
            if not from_index_list:
                raise RuntimeError("Could not find from image name")
            from_index = from_index_list[0]
            filtered_image_list = serie["images"][from_index:]

        template = serie["template"]
        varfile = serie["varfile"]
        extra_firstlogin_cmds = None
        if serie.get("extra_firstlogin_cmds"):
            extra_firstlogin_cmds = serie["extra_firstlogin_cmds"]
        for index, entry in enumerate(filtered_image_list):
            box_name = entry["name"]
            description = entry.get("description", None)
            logging.debug(entry)
            logging.info(
                "[%s/%s] Processing %s",
                index + 1,
                len(filtered_image_list),
                box_name,
            )
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
                    with vagrant.up_down_ctxt(vagrant_dir):
                        # 10 min
                        logging.info("Waiting for 10 minutes")
                        time.sleep(10 * 60)
                    vagrant.snapshot_save(vagrant_dir, IDLE_SNAPSHOT.to_raw_tag())
                vagrant.snapshot_restore(vagrant_dir, IDLE_SNAPSHOT.to_raw_tag())
                capture_neogit(
                    qcow_path, IDLE_SNAPSHOT.name, branch_name, unique=True, desc=IDLE_SNAPSHOT.description
                )

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


def entrypoint():
    args = docopt(__doc__)
    main(args)
