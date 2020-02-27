#!/usr/bin/env python3

"""
Usage: builder.py [options] <images_config>

Options:
    -h --help                       Display this message
    -d --debug                      Enable debug output
    -c --connection=<URI>           Specify a libvirt URI [Default: qemu:///session]
"""


import sys
import os
import logging
import yaml
import json
import subprocess
import hashlib
import shutil
from contextlib import contextmanager
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse
from pathlib import Path


from docopt import docopt

PACKER_TEMPLATES_DIR = Path(__file__).absolute().parent / 'packer-templates'
OUTPUT_QEMU_DIR = PACKER_TEMPLATES_DIR / 'output-qemu'
BLOCKSIZE = 65536


@contextmanager
def build_image(config_entry):
    source_url = config_entry['source']
    # validate source
    parse_res = urlparse(source_url)
    if not parse_res.scheme == 'file':
        raise NotImplementedError()
    # file exists ?
    source_path = Path(parse_res.path)
    if not source_path.exists():
        raise RuntimeError("source file does not exists")
    logging.debug("Source: %s", source_url)
    logging.debug("Computing SHA1")
    # compute sha1
    sha1sum = hashlib.sha1()
    with open(source_path, 'rb') as source_file:
        buf = source_file.read(BLOCKSIZE)
        while len(buf) > 0:
            sha1sum.update(buf)
            buf = source_file.read(BLOCKSIZE)
    sha1digest = sha1sum.hexdigest()
    logging.debug("SHA1: %s", sha1digest)
    # read win10 varfile
    with open(PACKER_TEMPLATES_DIR / 'win10.json') as win10json_f:
        win10config = json.load(win10json_f)
    # replace source URL and SHA1
    win10config['iso_url'] = source_url
    win10config['iso_checksum'] = sha1digest
    # write temporary file and build
    with NamedTemporaryFile(mode='w') as tmp_f:
        json.dump(win10config, tmp_f)
        # flush
        tmp_f.flush()
        # build with Packer
        cmdline = ['packer', 'build']
        # only qemu
        cmdline.extend(['-only', 'qemu'])
        # varfile
        cmdline.extend(['-var-file', tmp_f.name])
        # template
        cmdline.append(str(PACKER_TEMPLATES_DIR / 'windows.json'))
        logging.debug("cmdline: %s", cmdline)
        # ensure output-qemu dir is removed
        if OUTPUT_QEMU_DIR.exists():
            logging.warning("Removing previous unfinished build")
            shutil.rmtree(OUTPUT_QEMU_DIR)
        # open log file for packer
        with open('packer-build.log', 'a') as packer_log_f:
            subprocess.check_call(cmdline, stdout=packer_log_f, cwd=PACKER_TEMPLATES_DIR)
    # get output file path
    image_path = Path(os.listdir(OUTPUT_QEMU_DIR)[0])
    try:
        yield image_path
    finally:
        logging.info('Build: cleaning up')
        shutil.rmtree(OUTPUT_QEMU_DIR)


def init_logger(debug=False):
    formatter = "%(asctime)s %(levelname)s:%(name)s:%(message)s"
    logging_level = logging.INFO
    if debug:
        logging_level = logging.DEBUG
    logging.basicConfig(level=logging_level, format=formatter)


def main(args):
    # uri = args['--connection']
    debug = args['--debug']
    images_config_path = args['<images_config>']

    init_logger(debug)

    # load yaml config
    with open(images_config_path) as config_f:
        config = yaml.safe_load(config_f)

        for entry in config:
            logging.debug(entry)
            logging.info("Building %s", entry['name'])
            with build_image(entry) as image_path:
                logging.info("Build completed: %s", image_path)


args = docopt(__doc__)
retcode = main(args)
sys.exit(retcode)
