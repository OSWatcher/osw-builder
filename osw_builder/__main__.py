#!/usr/bin/env python3

"""
Usage: builder.py [options] [<packer_args>...]
       builder.py [options] [(--only-image=<NAME> | --from=<NAME>)] [--only-serie=<SERIE>...]

Options:
    -h --help                       Display this message
    -d --debug                      Enable debug output
    -c --connection=<URI>           Specify a libvirt URI [Default: qemu:///session]
    -o --only-image=<NAME>          Build only image NAME
    -s --only-serie=<SERIE>         Build only serie SERIE
    -f --from=<NAME>                Build images from NAME
    -n --net                        Add network section in domain.xml
"""


import contextlib
import hashlib
import importlib.resources as resources
import logging
import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import List, Optional
from urllib.parse import urlparse

import docker
import hcl2
import libvirt
from docopt import docopt

from osw_builder.autounattend import Autounattend
from osw_builder.settings import settings


# Access the packer-templates directory
def get_packer_templates_dir():
    with resources.path(__package__, "packer-templates") as path:
        return Path(path)


PACKER_TEMPLATES_DIR = get_packer_templates_dir()
OUTPUT_QEMU_DIR = PACKER_TEMPLATES_DIR / "output"
PACKER_DOCKER_AUTOUNATTEND_WIN10_PATH = "/packer/answer_files/10/Autounattend.xml"
PACKER_TEMPLATES_IMAGE = "ghcr.io/oswatcher/packer-templates:latest"
BLOCKSIZE = 65536
DOMAIN_MEMORY = 4096
DEFAULT_REMOVE_DOMAIN_VALUE = True
WINDOWS_TEMPLATE = "windows.json"
DEFAULT_STORAGE_POOL = "default"


def run_packer(varfile, autounattend, packer_args, network_disabled: bool = False) -> Path:
    dk_client = docker.from_env()
    packer_home_cache = Path.home() / ".cache" / "packer"
    # ensure we create packer cache dir
    packer_home_cache.mkdir(parents=True, exist_ok=True)
    volumes = {
        packer_home_cache: {"bind": "/cache", "mode": "rw"},
        PACKER_TEMPLATES_DIR: {"bind": "/output_parent", "mode": "rw"},
        varfile: {"bind": "/packer/win10.pkrvars.hcl", "mode": "ro"},
        autounattend: {"bind": PACKER_DOCKER_AUTOUNATTEND_WIN10_PATH, "mode": "ro"},
    }
    # open log file for packer
    with open("packer-build.log", "a") as packer_log_f:
        container = dk_client.containers.run(
            PACKER_TEMPLATES_IMAGE,
            remove=True,
            volumes=volumes,
            devices=["/dev/kvm"],
            ports={"5900/tcp": 5900},
            user=f"{os.getuid()}:{os.getgid()}",
            group_add=["sudo", "kvm"],
            network_disabled=network_disabled,
            detach=True,
        )
        try:
            for line in container.logs(stream=True):
                packer_log_f.write(line.decode())
                packer_log_f.flush()
            # wait for container to finish
            code = container.wait()
            if code["StatusCode"] != 0:
                raise RuntimeError("Packer failed")
        finally:
            # APIError: removal of container is already in progress
            with contextlib.suppress(docker.errors.NotFound, docker.errors.APIError):
                container.remove(force=True)
    return OUTPUT_QEMU_DIR / os.listdir(OUTPUT_QEMU_DIR)[0]


@contextmanager
def build_image(template, varfile, config_entry, extra_firstlogin_cmds: Optional[List[str]], packer_args: List[str]):

    source_url = config_entry["source"]
    # validate source
    parse_res = urlparse(source_url)
    if parse_res.scheme == "file":
        # file exists ?
        source_path = Path(parse_res.path)
        if not source_path.exists():
            raise RuntimeError("source file does not exists")
        logging.debug("Source: %s", source_url)
        logging.debug("Computing SHA1")
        # compute sha1
        sha1sum = hashlib.sha1()
        with open(source_path, "rb") as source_file:
            buf = source_file.read(BLOCKSIZE)
            while len(buf) > 0:
                sha1sum.update(buf)
                buf = source_file.read(BLOCKSIZE)
        sha1digest = sha1sum.hexdigest()
    else:
        # url, we need the SHA1 to be specified
        try:
            sha1digest = config_entry["sha1"]
        except KeyError:
            raise RuntimeError("Invalid configuration: need to specify a SHA1 for URL sources")
    logging.debug("SHA1: %s", sha1digest)
    # read win10 varfile
    with open(PACKER_TEMPLATES_DIR / varfile) as varfile_f:
        varfile_data = hcl2.load(varfile_f)
    # replace source URL and SHA1
    varfile_data["iso_url"] = source_url
    varfile_data["iso_checksum"] = sha1digest

    auto_path = None
    if template == WINDOWS_TEMPLATE:
        auto_path = PACKER_TEMPLATES_DIR / varfile_data["autounattend"]
    # write a new Autounattend and configure it if needed
    # we also create a temporary directory because the file must be named 'Autounattend.xml'
    with Autounattend(auto_path) as tmp_autounattend:
        if template == WINDOWS_TEMPLATE:
            # replace product key if needed
            product_key = config_entry.get("key")
            if product_key:
                logging.debug("Changing Product Key to %s", product_key)
                tmp_autounattend.product_key = product_key
            # replace image name if needed
            image_name = config_entry.get("image_name")
            if image_name:
                logging.debug("Selecting image %s", image_name)
                tmp_autounattend.image_name = image_name
            if extra_firstlogin_cmds:
                for cmd in reversed(extra_firstlogin_cmds):
                    tmp_autounattend.prepend_cmd(cmd)
            tmp_autounattend.write()
            # dump new Autounattend.xml
            # replace autounattend path in the config
            varfile_data["autounattend"] = PACKER_DOCKER_AUTOUNATTEND_WIN10_PATH
        # write temporary varfile and build
        with NamedTemporaryFile(mode="w", suffix=".pkrvars.hcl") as tmp_f:
            # manual dump
            for key, value in varfile_data.items():
                # check if value is a string
                if isinstance(value, str):
                    tmp_f.write(f'{key} = "{value}"\n')
                else:
                    tmp_f.write(f"{key} = {value}\n")
            # flush
            tmp_f.flush()
            # ensure output-qemu dir is removed
            if OUTPUT_QEMU_DIR.exists():
                logging.warning("Removing previous unfinished build")
                shutil.rmtree(OUTPUT_QEMU_DIR)

            # since we want to have network=none, we need to force cache the ISO first
            # do a first run that will fail and cache the ISO
            with NamedTemporaryFile(mode="w", suffix=".pkrvars.hcl") as tmp_f_fake:
                # manual dump
                for key, value in varfile_data.items():
                    # check if value is a string
                    if key == "cpus":
                        tmp_f_fake.write(f"{key} = 999999\n")
                    elif isinstance(value, str):
                        tmp_f_fake.write(f'{key} = "{value}"\n')
                    else:
                        tmp_f_fake.write(f"{key} = {value}\n")
                tmp_f_fake.flush()
                with contextlib.suppress(RuntimeError):
                    run_packer(
                        tmp_f_fake.name, tmp_autounattend.autounattend_tmp_path, packer_args, network_disabled=False
                    )
            # real run
            image_path = run_packer(
                tmp_f.name, tmp_autounattend.autounattend_tmp_path, packer_args, network_disabled=True
            )
        try:
            yield image_path
        finally:
            logging.info("Build: cleaning up")
            shutil.rmtree(OUTPUT_QEMU_DIR)


class DomXML:
    def __init__(self, xml_desc):
        self.tree = ET.fromstring(xml_desc)

    # helpers
    def findfirst(self, xpath):
        return self.tree.findall(xpath)[0]

    @property
    def name(self):
        return self.findfirst("./name").text

    @name.setter
    def name(self, value):
        self.findfirst("./name").text = value

    @property
    def memory(self):
        return self.findfirst("memory").text

    @memory.setter
    def memory(self, value):
        self.findfirst("./memory").text = value

    @property
    def disk(self):
        return self.findfirst('./devices/disk[@device="disk"]/source').get("file")

    @disk.setter
    def disk(self, value):
        self.findfirst('./devices/disk[@device="disk"]/source').set("file", value)

    def add_network(self):
        devices = self.findfirst("./devices")
        interface = ET.Element("interface", {"type": "network"})
        interface.append(ET.Element("source", {"network": "default"}))
        interface.append(ET.Element("model", {"type": "e1000e"}))
        devices.append(interface)

    def tostring(self):
        """Generate new XML string from tree object"""
        return ET.tostring(self.tree, encoding="unicode")


class LibvirtDom:
    def __init__(
        self,
        con,
        template,
        varfile,
        config_entry,
        remove_domain,
        net_on: bool,
        storage_pool: str,
        extra_firstlogin_cmds: Optional[List[str]],
        packer_args: List[str],
    ):
        self.con = con
        self.template = template
        self.varfile = varfile
        self.dom_name = config_entry["name"]
        self.config_entry = config_entry
        self.remove_domain = remove_domain
        self.extra_firstlogin_cmds = extra_firstlogin_cmds
        self.net_on = net_on
        self.storage_pool = storage_pool
        self.dom = None
        self.image_builder = None
        self.domain_disk = None
        self.packer_args = packer_args

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
            self.image_builder = build_image(
                self.template,
                self.varfile,
                self.config_entry,
                self.extra_firstlogin_cmds,
                self.packer_args,
            )
            image_path = self.image_builder.__enter__()
            # build pool
            pool = self.con.storagePoolLookupByName(self.storage_pool)
            # get pool path from Pool object
            pool_xml = pool.XMLDesc()
            pool_tree = ET.fromstring(pool_xml)
            pool_path = pool_tree.findall("./target/path")[0].text
            logging.debug("path: %s", pool_path)
            # make sure storage is active
            if not pool.isActive():
                pool.create()
            # move image to storage pool
            dst = (Path(pool_path) / self.dom_name).with_suffix(".qcow2")
            logging.debug("Moving image to %s", dst)
            shutil.move(image_path, dst)
            # important: refresh storage pool, otherwise future lookup operation on this qcow will fail
            # ex: Storage volume not found: no storage vol with matching path '..../xxx.qcow2'
            pool.refresh()
            self.domain_disk = dst
            # template default domain XML
            with open("domain.xml") as template_f:
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
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("docker").setLevel(logging.WARNING)
    logging.basicConfig(level=logging_level, format=formatter)


def main(args):
    uri = args["--connection"]
    debug = args["--debug"]
    only_image = args["--only-image"]
    from_image = args["--from"]
    only_series = args["--only-serie"]
    net_on = args["--net"]
    packer_args = args["<packer_args>"]

    init_logger(debug)
    logging.debug(args)

    libvirt_con = libvirt.open(uri)

    remove_domain = settings.get("remove_domain", DEFAULT_REMOVE_DOMAIN_VALUE)
    storage_pool = settings.get("storage_pool", DEFAULT_STORAGE_POOL)
    tool_list = settings.get("tools")

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
            logging.debug(entry)
            logging.info(
                "[%s/%s] Building %s",
                index + 1,
                len(filtered_image_list),
                entry["name"],
            )
            with LibvirtDom(
                libvirt_con,
                template,
                varfile,
                entry,
                remove_domain,
                net_on,
                storage_pool,
                extra_firstlogin_cmds,
                packer_args,
            ) as domain:
                logging.info("New domain: %s", domain.name())
                if tool_list:
                    for tool_cmd in tool_list:
                        # format and replace domain name
                        f_tool_cmd = tool_cmd.format(domain_name=domain.name(), uri=uri)
                        if debug:
                            f_tool_cmd += " --debug"
                        logging.info("Running tool: %s", f_tool_cmd)
                        subprocess.check_call(f_tool_cmd, shell=True)


def entrypoint():
    args = docopt(__doc__)
    main(args)
