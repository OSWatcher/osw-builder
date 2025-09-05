import logging
import os
import subprocess
from contextlib import ExitStack, closing, contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

import guestfs


class LibguestFSMnt:
    ROOT = "/"

    def __init__(self, qcow_path: Path, local: bool = False, readonly: bool = True):
        self._local = local
        self._readonly = readonly
        self._ex = ExitStack()
        self._logger = logging.getLogger(f"{self.__module__}.{self.__class__.__name__}")
        self.gfs = guestfs.GuestFS(python_return_dict=True)
        self.gfs.add_drive_opts(str(qcow_path), readonly=self._readonly)
        self._local_mnt = None

    @contextmanager
    def _cleanup_on_error(self):
        with ExitStack() as stack:
            stack.push(self)
            yield
            # The validation check passed and didn't raise an exception
            # Accordingly, we want to keep the resource, and pass it
            # back to our caller
            stack.pop_all()

    def __enter__(self):
        with self._cleanup_on_error():
            self._logger.info("Initializing libguestfs mount")
            self._ex.enter_context(closing(self.gfs))

            @contextmanager
            def ctx_launch():
                self.gfs.launch()
                try:
                    yield
                finally:
                    self.gfs.shutdown()

            self._ex.enter_context(ctx_launch())

            @contextmanager
            def ctx_mount(mountable: str, mount_point: str):
                self._logger.info(f"Mounting partition {mountable} to {mount_point}")
                self.gfs.mount(mountable, mount_point)
                try:
                    yield
                finally:
                    self._logger.info(f"Unmounting {mount_point}")
                    self.gfs.umount(mount_point)

            @contextmanager
            def ctx_mount_local(local_mntpnt: str):
                self._logger.info(f"Setting up local mount at {local_mntpnt}")
                self.gfs.mount_local(local_mntpnt, readonly=self._readonly)
                try:
                    yield
                finally:
                    self._logger.info("Unmounting local filesystem")
                    # bug with unmount local guestfs
                    # need to make at least one filesystem requests otherwise fusermount might hang
                    os.scandir(Path(self._local_mntpnt))
                    # bug with umount_local()
                    # need to call fusermount -u manually
                    # self.gfs.umount_local()
                    subprocess.check_call(["fusermount", "-u", self._local_mntpnt])
                    # Join the thread after unmounting since fusermount frees the thread
                    self._thread_mnt_local.join()
                    self._logger.info("Local filesystem unmount completed")

            os_partitions = self.gfs.inspect_os()
            if os_partitions:
                # OS found, use first one
                main_partition = os_partitions[0]
                self._logger.info(f"OS detected, using first partition: {main_partition}")
            else:
                # no OS detected, use first partition
                self._logger.info("No OS detected, using first partition")
                main_partition = self.gfs.list_partitions()[0]
            self._logger.info("Mounting filesystem")
            self._ex.enter_context(ctx_mount(main_partition, self.ROOT))
            if self._local:
                self._local_mntpnt = self._ex.enter_context(TemporaryDirectory())
                self._ex.enter_context(ctx_mount_local(self._local_mntpnt))
                # start processing fs requests
                self._thread_mnt_local = Thread(target=self.gfs.mount_local_run)
                self._thread_mnt_local.start()
            return self._local_mntpnt if self._local else None

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._ex.__exit__(exc_type, exc_val, exc_tb)
