#!/usr/bin/env python3

"""
Usage: builder.py [options] <images_config>
       builder.py [options] [(--only-image=<NAME> | --from=<NAME>)] [--only-serie=<SERIE>...] <images_config>

Options:
    -h --help                       Display this message
    -d --debug                      Enable debug output
    -c --connection=<URI>           Specify a libvirt URI [Default: qemu:///session]
    -o --only-image=<NAME>          Build only image NAME
    -s --only-serie=<SERIE>         Build only serie SERIE
    -f --from=<NAME>                Build images from NAME
    -n --net                        Add network section in domain.xml
"""


import sys
import os
import logging
import yaml
import json
import subprocess
import hashlib
import shutil
import libvirt
from contextlib import contextmanager
from tempfile import NamedTemporaryFile, TemporaryDirectory
from urllib.parse import urlparse
from pathlib import Path
import xml.etree.ElementTree as ET


from docopt import docopt

PACKER_TEMPLATES_DIR = Path(__file__).absolute().parent / 'packer-templates'
OUTPUT_QEMU_DIR = PACKER_TEMPLATES_DIR / 'output-qemu'
BLOCKSIZE = 65536
DOMAIN_MEMORY = 4096
DEFAULT_REMOVE_DOMAIN_VALUE = True
WINDOWS_TEMPLATE = 'windows.json'


@contextmanager
def build_image(template, varfile, config_entry):
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
    with open(PACKER_TEMPLATES_DIR / varfile) as varfile_f:
        varfile_data = json.load(varfile_f)
    # replace source URL and SHA1
    varfile_data['iso_url'] = source_url
    varfile_data['iso_checksum'] = sha1digest

    # read autounattend only if Windows
    if template == WINDOWS_TEMPLATE:
        # read autounattend
        with open(PACKER_TEMPLATES_DIR / varfile_data['autounattend']) as autounattend_f:
            autounattend = autounattend_f.read()

    # write a new Autounattend and configure it if needed
    # we also create a temporary directory because the file must be named 'Autounattend.xml'
    with TemporaryDirectory() as tmp_dir_autounattend:
        # parse XML only if Windows
        if template == WINDOWS_TEMPLATE:
            # register Autounattend XML prefixes
            ET.register_namespace('', 'urn:schemas-microsoft-com:unattend')
            ET.register_namespace('wcm', 'http://schemas.microsoft.com/WMIConfig/2002/State')
            ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')
            ET.register_namespace('cpi', 'urn:schemas-microsoft-com:cpi')
            tree = ET.ElementTree(ET.fromstring(autounattend))
            namespaces = {'ns': 'urn:schemas-microsoft-com:unattend'}

            # replace product key if needed
            product_key = config_entry.get('key')
            if product_key:
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

            # replace image name if needed
            image_name = config_entry.get('image_name')
            if image_name:
                logging.debug("Selecting image %s", image_name)
                image_value_el = tree.findall('./ns:settings[@pass="windowsPE"]/ns:component/ns:ImageInstall/ns:OSImage/ns:InstallFrom/ns:MetaData/ns:Value',
                                      namespaces=namespaces)[0]
                image_value_el.text = image_name
            # dump new Autounattend.xml
            autounattend_path = Path(tmp_dir_autounattend) / 'Autounattend.xml'
            tree.write(str(autounattend_path), xml_declaration=True, encoding='utf-8')
            # replace autounattend path in the config
            varfile_data['autounattend'] = str(autounattend_path)
        # write temporary varfile and build
        with NamedTemporaryFile(mode='w') as tmp_f:
            json.dump(varfile_data, tmp_f)
            # flush
            tmp_f.flush()
            # build with Packer
            cmdline = ['packer', 'build']
            # only qemu
            cmdline.extend(['-only', 'qemu'])
            # varfile
            cmdline.extend(['-var-file', tmp_f.name])
            # template
            cmdline.append(str(PACKER_TEMPLATES_DIR / template))
            logging.debug("cmdline: %s", cmdline)
            # ensure output-qemu dir is removed
            if OUTPUT_QEMU_DIR.exists():
                logging.warning("Removing previous unfinished build")
                shutil.rmtree(OUTPUT_QEMU_DIR)
            # open log file for packer
            with open('packer-build.log', 'a') as packer_log_f:
                try:
                    subprocess.check_call(cmdline, stdout=packer_log_f, cwd=PACKER_TEMPLATES_DIR)
                except subprocess.CalledProcessError as e:
                    raise RuntimeError('Packer build failed ! Check packer-buikd.log')
        # get output file path
        image_path = OUTPUT_QEMU_DIR / os.listdir(OUTPUT_QEMU_DIR)[0]
        try:
            yield image_path
        finally:
            logging.info('Build: cleaning up')
            shutil.rmtree(OUTPUT_QEMU_DIR)


class DomXML:

    def __init__(self, xml_desc):
        self.tree = ET.fromstring(xml_desc)

    # helpers
    def findfirst(self, xpath):
        return self.tree.findall(xpath)[0]

    @property
    def name(self):
        return self.findfirst('./name').text

    @name.setter
    def name(self, value):
        self.findfirst('./name').text = value

    @property
    def memory(self):
        return self.findfirst('memory').text

    @memory.setter
    def memory(self, value):
        self.findfirst('./memory').text = value

    @property
    def disk(self):
        return self.findfirst('./devices/disk[@device="disk"]/source').get('file')

    @disk.setter
    def disk(self, value):
        self.findfirst('./devices/disk[@device="disk"]/source').set('file', value)

    def add_network(self):
        devices = self.findfirst('./devices')
        interface = ET.Element('interface', {'type': 'network'})
        interface.append(ET.Element('source', {'network': 'default'}))
        devices.append(interface)

    def tostring(self):
        """Generate new XML string from tree object"""
        return ET.tostring(self.tree, encoding='unicode')


class LibvirtDom:

    def __init__(self, con, template, varfile, config_entry, remove_domain, net_on: bool):
        self.con = con
        self.template = template
        self.varfile = varfile
        self.dom_name = config_entry['name']
        self.config_entry = config_entry
        self.remove_domain = remove_domain
        self.net_on = net_on
        self.dom = None
        self.image_builder = None
        self.domain_disk = None

    def __enter__(self):
        """Build a Libvirt domain and returns it"""
        # check whether the domain already exists
        try:
            logging.info("Checking for domain %s", self.dom_name)
            self.dom = self.con.lookupByName(self.dom_name)
            logging.debug("Domain exists")
        except libvirt.libvirtError:
            logging.info("Building domain")
            # build and define domain
            self.image_builder = build_image(self.template, self.varfile, self.config_entry)
            image_path = self.image_builder.__enter__()
            # build pool
            pool = self.con.storagePoolLookupByName('default')
            # get pool path from Pool object
            pool_xml = pool.XMLDesc()
            pool_tree = ET.fromstring(pool_xml)
            pool_path = pool_tree.findall('./target/path')[0].text
            logging.debug('path: %s', pool_path)
            # make sure storage is active
            if not pool.isActive():
                pool.create()
            # move image to storage pool
            dst = (Path(pool_path) / self.dom_name).with_suffix('.qcow2')
            logging.debug('Moving image to %s', dst)
            shutil.move(image_path, dst)
            # important: refresh storage pool, otherwise future lookup operation on this qcow will fail
            # ex: Storage volume not found: no storage vol with matching path '..../xxx.qcow2'
            pool.refresh()
            self.domain_disk = dst
            # template default domain XML
            with open('domain.xml') as template_f:
                template_xml = template_f.read()
                template = DomXML(template_xml)
                template.name = self.dom_name
                template.memory = str(DOMAIN_MEMORY)
                template.disk = str(dst)
                if self.net_on:
                    template.add_network()
                domain_xml = template.tostring()
                # define domain
                logging.info("Defining domain")
                self.con.defineXML(domain_xml)
                self.dom = self.con.lookupByName(self.dom_name)
        return self.dom

    def __exit__(self, type, value, traceback):
        # cleanup domain and image
        if self.remove_domain:
            logging.info("Undefining domain")
            self.dom.undefine()
            logging.info("Removing disk")
            if self.domain_disk:
                self.domain_disk.unlink()
            if self.image_builder:
                self.image_builder.__exit__(type, value, traceback)


def init_logger(debug=False):
    formatter = "%(asctime)s %(levelname)s:%(name)s:%(message)s"
    logging_level = logging.INFO
    if debug:
        logging_level = logging.DEBUG
    logging.basicConfig(level=logging_level, format=formatter)


def main(args):
    uri = args['--connection']
    debug = args['--debug']
    images_config_path = args['<images_config>']
    only_image = args['--only-image']
    from_image = args['--from']
    only_series = args['--only-serie']
    net_on = args['--net']

    init_logger(debug)
    logging.debug(args)

    libvirt_con = libvirt.open(uri)

    # load yaml config
    with open(images_config_path) as config_f:
        config = yaml.safe_load(config_f)

        remove_domain = config.get('remove_domain', DEFAULT_REMOVE_DOMAIN_VALUE)
        tool_list = config.get('tools')

        filtered_serie_list = config['series']
        if only_series:
            filtered_serie_list = [serie for serie in config['series'] if serie['name'] in only_series]
        for serie in filtered_serie_list:
            logging.info('Serie %s', serie['name'])
            # apply filter
            #   get all images
            filtered_image_list = serie['images']
            if only_image:
                filtered_image_list = [entry for entry in serie['images'] if entry['name'] == only_image]
            elif from_image:
                from_index_list = [index for index, entry in enumerate(serie['images']) if entry['name'] == from_image]
                if not from_index_list:
                    raise RuntimeError("Could not find from image name")
                from_index = from_index_list[0]
                filtered_image_list = serie['images'][from_index:]

            template = serie['template']
            varfile = serie['varfile']
            for index, entry in enumerate(filtered_image_list):
                logging.debug(entry)
                logging.info("[%s/%s] Building %s", index+1, len(filtered_image_list), entry['name'])
                with LibvirtDom(libvirt_con, template, varfile, entry, remove_domain, net_on) as domain:
                    logging.info("New domain: %s", domain.name())
                    if tool_list:
                        for tool_cmd in tool_list:
                            # format and replace domain name
                            f_tool_cmd = tool_cmd.format(domain_name=domain.name(), uri=uri)
                            logging.info("Running tool: %s", f_tool_cmd)
                            subprocess.check_call(f_tool_cmd, shell=True)


args = docopt(__doc__)
retcode = main(args)
sys.exit(retcode)
