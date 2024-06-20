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
    --var <packer_args>...          Extra packer arguments
"""


import logging
from contextlib import ExitStack

import libvirt
from docopt import docopt

from osw_builder import vagrant
from osw_builder.build import build_image
from osw_builder.settings import settings


def init_logger(debug=False):
    formatter = "%(asctime)s %(levelname)s:%(name)s:%(message)s"
    logging_level = logging.INFO
    if debug:
        logging_level = logging.DEBUG
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("docker").setLevel(logging.WARNING)
    logging.basicConfig(level=logging_level, format=formatter)


def main(args):
    uri = args["--connection"]
    debug = args["--debug"]
    only_image = args["--only-image"]
    from_image = args["--from"]
    only_series = args["--only-serie"]
    packer_args = args["--var"]

    init_logger(debug)
    logging.debug(args)

    libvirt_con = libvirt.open(uri)

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
                    image = ex.enter_context(
                        build_image(libvirt_con, template, varfile, entry, extra_firstlogin_cmds, packer_args)
                    )
                    vagrant.box_add(image, name=box_name)

                # prepare vagrant env
                vagrant_dir = ex.enter_context(vagrant.prepare_vagrantfile(box_name))
                ex.enter_context(vagrant.ensure_destroyed(vagrant_dir))
                ex.enter_context(vagrant.up_down_ctxt(vagrant_dir))
                vagrant.provision(vagrant_dir)


def entrypoint():
    args = docopt(__doc__)
    main(args)
