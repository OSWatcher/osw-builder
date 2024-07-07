import logging
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

import guestfs


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
