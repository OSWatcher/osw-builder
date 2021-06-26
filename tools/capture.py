#!/usr/bin/env python3

"""
Usage:
    capture.py oswatcher [options] <vm_name> <plugins_configuration>
    capture.py neogit [options] <vm_name>

Options:
    -h --help                       Display this message
    -d --debug                      Enable debug output
    -u --updates                    Install Windows Updates
    -c --connection=<URI>           Specify a libvirt URI [Default: qemu:///session]
"""


import sys

import libvirt
import time
import logging
import socket
import guestfs
import subprocess
from pathlib import Path
from threading import Thread
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as tree
from functools import partial
from docopt import docopt
import os
from contextlib import closing

from oswatcher.capture import capture_vm
from winupdate.winupdate import WinUpdate, WinUpdateModData, WinUpdateInfo

from neogit.service import Neogit

SNAPSHOT_XML = """
<domainsnapshot>
    <name>{snapshot_name}</name>
    <description>{description}</description>
</domainsnapshot>
"""


class LibguestFSMnt:
    def __init__(self, qcow_path: Path, local: bool = False, readonly: bool = True):
        self._local = local
        self._readonly = readonly
        self.gfs = guestfs.GuestFS(python_return_dict=True)
        self.gfs.add_drive_opts(str(qcow_path), readonly=self._readonly)
        self._thread_mnt_local = Thread(target=self.run_mount_local)
        self._local_mnt = None

    def __enter__(self):
        self.gfs.launch()
        os_partitions = self.gfs.inspect_os()
        if len(os_partitions) == 0:
            main_partition = self.gfs.list_partitions()[0]
            logging.info(f"No OS detected, using first partition: {main_partition}")
        else:
            # capture first detected OS
            main_partition = os_partitions[0]
        logging.info("Mounting filesystem")
        self.gfs.mount(main_partition, "/")
        if self._local:
            self._local_mntpnt = TemporaryDirectory()
            self.gfs.mount_local(self._local_mntpnt.name, readonly=self._readonly)
            # start processing fs requests
            self._thread_mnt_local.start()
        return self._local_mntpnt.name

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._local:
            # bug with unmount local guestfs filesystem
            # need to make at least one filesystem requests otherwise fusermount might hang
            os.scandir(Path(self._local_mntpnt.name))
            # bug with umount_local()
            # need to call fusermount manually

            # bug: fusermount -u might fail when mounting / umounting too
            # quickly (pending fs requests ?)
            # this time sleep seems to solve the issue for now
            import time

            time.sleep(2)
            logging.debug("fusermount %s", self._local_mntpnt.name)
            subprocess.check_call(["fusermount", "-u", self._local_mntpnt.name])
            self._local_mntpnt.cleanup()
        try:
            self.gfs.umount_all()
            self.gfs.shutdown()
        except RuntimeError:
            # not launched
            pass

    def run_mount_local(self):
        logging.debug("Start processing requests on local mountpoint")
        self.gfs.mount_local_run()
        logging.debug("Done processing request on local mountpoint")


def wait_socket(port, ip_addr, opened=True, sleep=1):
    logging.info(
        "Waiting for the monitored service on port %d to %s", port, "become available" if opened else "shutdown"
    )
    while True:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            state = sock.connect_ex((ip_addr, port))
            logging.debug("Monitor state: %s", os.strerror(state))
            if state == 0 and opened:
                logging.info("Monitored service on port %d became available", port)
                break
            elif state != 0 and not opened:
                logging.info("Monitored service on port %d went down", port)
                break
            time.sleep(sleep)


wait_winrm = partial(wait_socket, 5985)


def wait_for_ip(domain, network_name="default"):
    # find MAC address
    dom_elem = tree.fromstring(domain.XMLDesc())
    mac_addr = dom_elem.find("./devices/interface[@type='network']/mac").get("address")
    logging.debug("MAC address: {}".format(mac_addr))
    while True:
        net = domain.connect().networkLookupByName(network_name)
        leases = net.DHCPLeases()
        found = [l for l in leases if l["mac"] == mac_addr]
        if found:
            return found[0]["ipaddr"]
        time.sleep(1)


def shutdown(domain):
    logging.info("shutting down")
    domain.shutdown()
    while domain.state()[0] != libvirt.VIR_DOMAIN_SHUTOFF:
        time.sleep(2)


def oswatcher(args):
    debug = args["--debug"]
    vm_name = args["<vm_name>"]
    plugins_path = args["<plugins_configuration>"]
    uri = args["--connection"]
    # run first capture
    # retcode = capture_vm(vm_name, plugins_path, connection=uri, base_branch=None, tag=vm_name, debug=debug)
    # start vm
    con = libvirt.open(uri)
    domain = con.lookupByName(vm_name)

    # take snapshot
    snap_xml = SNAPSHOT_XML.format(snapshot_name="ready", description="")
    try:
        domain.snapshotLookupByName("ready")
    except libvirt.libvirtError:
        # create it
        domain.snapshotCreateXML(snap_xml)
    # revert to snapshot
    # domain.revertToSnapshot("ready")
    logging.info("Start domain %s", vm_name)
    domain.create()
    # wait for ip
    logging.info("Wait for IP address")
    ip_addr = wait_for_ip(domain)
    logging.info("IP: %s", ip_addr)
    # wait WinRM
    logging.info("Wait for WinRM service")
    wait_winrm(ip_addr)
    logging.info("Searching for Windows Updates")
    # search for updates
    win_log_level = 0
    if debug:
        win_log_level = 1
    win_update = WinUpdate(ip_addr, debug_lvl=win_log_level)

    if args["--updates"]:
        for update in win_update.search():
            logging.info("[%s] %s", update.kb[0], update.title)
            # shutdown VM
            shutdown(domain)
            # take snapshot
            snap_name = update.kb[0]
            snap_xml = SNAPSHOT_XML.format(snapshot_name=snap_name, description=update.title)
            try:
                domain.snapshotLookupByName(snap_name)
            except libvirt.libvirtError:
                # create it
                domain.snapshotCreateXML(snap_xml)
            # recapture image, on a specific branch
            # capture_vm(vm_name, plugins_path, connection=uri, base_branch=vm_name, debug=debug)

            logging.info("Start domain %s", vm_name)
            domain.create()
            # wait for ip
            logging.info("Wait for IP address")
            ip_addr = wait_for_ip(domain)
            logging.info("IP: %s", ip_addr)
            # wait WinRM
            logging.info("Wait for WinRM service")
            wait_winrm(ip_addr)

    # while has_updates
    # install update
    # capture
    retcode = 0
    sys.exit(retcode)


def neogit(args):
    vm_name = args["<vm_name>"]
    uri = args["--connection"]
    # get qcow path
    con = libvirt.open(uri)
    domain = con.lookupByName(vm_name)
    dom_xml = domain.XMLDesc()
    root = tree.fromstring(dom_xml)
    qcow_path = root.findall('./devices/disk[@device="disk"]/source')[0].get("file")
    logging.info("Qcow path: %s", qcow_path)

    with LibguestFSMnt(qcow_path, local=True, readonly=True) as local_mnt:
        logging.info("Local mountpoint: %s", local_mnt)
        # ensure init
        cmdline = ["neogit", "init"]
        subprocess.check_call(cmdline)
        cmdline = ["neogit", "commit", vm_name, "-r", local_mnt]
        logging.info("Running Neogit ...")
        subprocess.check_call(cmdline)


def main():
    args = docopt(__doc__)
    debug = args["--debug"]
    # setup logging
    log_lvl = logging.INFO
    if debug:
        log_lvl = logging.DEBUG
    logging.basicConfig(level=log_lvl)
    # switch subcommands
    if args["neogit"]:
        return neogit(args)
    if args["oswatcher"]:
        return oswatcher(args)


if __name__ == "__main__":
    main()
