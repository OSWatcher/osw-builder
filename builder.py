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
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.parse import urlparse
from pathlib import Path
import xml.etree.ElementTree as ET


from docopt import docopt

PACKER_TEMPLATES_DIR = Path(__file__).absolute().parent / 'packer-templates'
OUTPUT_QEMU_DIR = PACKER_TEMPLATES_DIR / 'output-qemu'
BLOCKSIZE = 65536


@contextmanager
def build_image(config_entry):
    source_url = config_entry['source']
    # validate source
    parse_res = urlparse(source_url)
    if parse_res.scheme == 'file':
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
    else:
        # url, we need the SHA1 to be specified
        try:
            sha1digest = config_entry['sha1']
        except KeyError:
            raise RuntimeError('Invalid configuration: need to specify a SHA1 for URL sources')
    logging.debug("SHA1: %s", sha1digest)
    # read win10 varfile
    with open(PACKER_TEMPLATES_DIR / 'win10.json') as win10json_f:
        win10config = json.load(win10json_f)
    # replace source URL and SHA1
    win10config['iso_url'] = source_url
    win10config['iso_checksum'] = sha1digest

    # read autounattend
    with open(PACKER_TEMPLATES_DIR / win10config['autounattend']) as autounattend_f:
        autounattend = autounattend_f.read()
    # write a new Autounattend and configure it if needed
    # we also create a temporary directory because the file must be named 'Autounattend.xml'
    with TemporaryDirectory() as tmp_dir_autounattend:
        # register Autounattend XML prefixes
        ET.register_namespace('', 'urn:schemas-microsoft-com:unattend')
        ET.register_namespace('wcm', 'http://schemas.microsoft.com/WMIConfig/2002/State')
        ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')
        ET.register_namespace('cpi', 'urn:schemas-microsoft-com:cpi')
        tree = ET.ElementTree(ET.fromstring(autounattend))
        namespaces = {'ns': 'urn:schemas-microsoft-com:unattend'}
        try:
            product_key = config_entry['key']
        except KeyError:
            pass
        else:
            logging.debug("Changing Product Key to %s", product_key)
            try:
                key_el = tree.findall('./ns:settings[@pass="windowsPE"]/ns:component/ns:UserData/ns:ProductKey/ns:Key',
                                  namespaces=namespaces)[0]
            except IndexError:
                # Key not present, insert it
                product_key_el = tree.findall('./ns:settings[@pass="windowsPE"]/ns:component/ns:UserData/ns:ProductKey',
                                  namespaces=namespaces)[0]
                key_el = ET.Element('Key')
                product_key_el.append(key_el)
            key_el.text = product_key
        # dump new Autounattend.xml
        autounattend_path = Path(tmp_dir_autounattend) / 'Autounattend.xml'
        tree.write(str(autounattend_path), xml_declaration=True, encoding='utf-8')
        # replace autounattend path in the config
        win10config['autounattend'] = str(autounattend_path)
        # write temporary varfile and build
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

        for entry in config['images']:
            logging.debug(entry)
            logging.info("Building %s", entry['name'])
            with build_image(entry) as image_path:
                logging.info("Build completed: %s", image_path)


args = docopt(__doc__)
retcode = main(args)
sys.exit(retcode)
