#!/usr/bin/env python3

"""
Usage: builder.py [options] [(--only-image=<NAME> | --from=<NAME>)] [--only-serie=<SERIE>...] [--var <packer_args>...]

Options:
    -h --help                       Display this message
    -d --debug                      Enable debug output
    -c --connection=<URI>           Specify a libvirt URI [Default: qemu:///session]
    -o --only-image=<NAME>          Build only image NAME
    -s --only-serie=<SERIE>         Build only serie SERIE
    -f --from=<NAME>                Build images from NAME
    --destroy                       Destroy the VM after build
    --var <packer_args>...          Extra packer arguments
"""


import logging
from contextlib import ExitStack, suppress

from docopt import docopt
from winupdate.winupdate import UpdateNotInstalledError, WinUpdate

from osw_builder import vagrant
from osw_builder.build import build_image
from osw_builder.capture import capture_neogit, create_branch
from osw_builder.settings import settings

BUILD_SNAPSHOT_NAME = "build"
LIBVIRT_URI = "qemu:///session"


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
                        vagrant.snapshot_save(vagrant_dir, BUILD_SNAPSHOT_NAME)

                # get the qcow path
                qcow_path = vagrant.get_qcow_path(box_name, uri=LIBVIRT_URI)
                logging.debug("Qcow path: %s", qcow_path)

                # restore build snapshot
                vagrant.snapshot_restore(vagrant_dir, BUILD_SNAPSHOT_NAME)
                build_commit = capture_neogit(qcow_path, box_name, unique=True)

                # create branch
                branch_name = box_name
                with suppress(ValueError):
                    create_branch(
                        branch_name,
                        build_commit,
                    )

                # TODO idle state

                # loop through the snapshot list, and assert that the first one is the build snapshot
                snap_list = vagrant.snapshot_list(vagrant_dir, qcow_path)
                assert snap_list[0].Tag == BUILD_SNAPSHOT_NAME

                # iterate after 'build' snapshot
                for snap in snap_list[1:]:
                    vagrant.snapshot_restore(vagrant_dir, snap.Tag)
                    capture_neogit(qcow_path, snap.Tag, branch_name, unique=True)

                # take last snapshot
                previous_snap = snap_list[-1].Tag
                # apply latest winupdates
                with vagrant.up_down_ctxt(vagrant_dir):
                    logging.info("Searching for Windows Updates")
                    winrm_config = vagrant.winrm_config(vagrant_dir)
                    win_update = WinUpdate(winrm_config.HostName, debug_lvl=0)
                    for index, update in enumerate(win_update.search()):
                        kb_name = f"KB-{update.kb[0]}"
                        logging.info("[%s][%s] %s", index + 1, kb_name, update.title)
                        try:
                            with vagrant.up_down_ctxt(vagrant_dir):
                                win_update.apply_update(update.id, update.kb[0])
                        except UpdateNotInstalledError:
                            logging.warning("Update not installed")
                            # restore previous snapshot
                            vagrant.snapshot_restore(vagrant_dir, previous_snap)
                        else:
                            # SUCCESS !
                            # take snapshot
                            vagrant.snapshot_save(vagrant_dir, kb_name)
                            # update previous
                            previous_snap = kb_name
                            capture_neogit(qcow_path, kb_name, branch_name, unique=True)


def entrypoint():
    args = docopt(__doc__)
    main(args)
