import logging
import os
import subprocess
from contextlib import ExitStack, closing, contextmanager, redirect_stderr
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from typing import Optional

import guestfs


@contextmanager
def capture_stderr():
    """
    Capture stderr during libguestfs operations and report summary.

    libguestfs emits many non-fatal diagnostic messages (especially for
    unsupported NTFS reparse points) that pollute logs. This captures
    all stderr and logs a summary count instead.

    Yields:
        StringIO buffer containing captured stderr
    """
    stderr_buffer = StringIO()
    with redirect_stderr(stderr_buffer):
        yield stderr_buffer


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
    def ctx_mount(self, mountable: str, mount_point: str):
        """Context manager for mounting/unmounting partitions."""
        self._logger.info(f"Mounting partition {mountable} to {mount_point}")
        try:
            self.gfs.mount(mountable, mount_point)
            yield
        except Exception as e:
            self._logger.debug(f"Failed to mount {mountable}: {e}")
            raise
        finally:
            try:
                self._logger.info(f"Unmounting {mount_point}")
                self.gfs.umount(mount_point)
            except Exception as e:
                self._logger.warning(f"Failed to unmount {mount_point}: {e}")

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
            # Capture stderr from libguestfs operations
            with capture_stderr() as stderr_buf:
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

                # Try standard libguestfs OS detection first
                os_partitions = self.gfs.inspect_os()
                if os_partitions:
                    # OS found, use first one
                    main_partition = os_partitions[0]
                    self._logger.info(f"OS detected, using first partition: {main_partition}")
                else:
                    # Fallback to custom OS detection when inspect_os fails
                    self._logger.info("No OS detected by inspect_os, trying custom detection")
                    main_partition = self._detect_main_partition()
                    if not main_partition:
                        # Exit with error instead of guessing
                        raise RuntimeError(
                            "Unable to detect main OS partition - both inspect_os and custom detection failed"
                        )
                self._logger.info("Mounting filesystem")
                self._ex.enter_context(self.ctx_mount(main_partition, self.ROOT))
                if self._local:
                    self._local_mntpnt = self._ex.enter_context(TemporaryDirectory())
                    self._ex.enter_context(ctx_mount_local(self._local_mntpnt))
                    # start processing fs requests
                    self._thread_mnt_local = Thread(target=self.gfs.mount_local_run)
                    self._thread_mnt_local.start()

            # Report how many messages were suppressed
            stderr_content = stderr_buf.getvalue()
            if stderr_content:
                num_lines = len(stderr_content.strip().split("\n"))
                self._logger.info(f"Suppressed {num_lines} libguestfs diagnostic messages")

            return self._local_mntpnt if self._local else None

    def _detect_main_partition(self) -> Optional[str]:
        """
        Custom OS partition detection when libguestfs inspect_os fails.
        Iterates through filesystems, skips EFI (vfat), and returns first mountable partition.
        """
        filesystems = self.gfs.list_filesystems()
        self._logger.info(f"Available filesystems: {filesystems}")

        for partition, fs_type in filesystems.items():
            # Handle vfat partitions - could be EFI or legacy Windows
            if fs_type == "vfat":
                if self._is_efi_system_partition(partition):
                    self._logger.debug(f"Skipping {partition}: EFI System Partition")
                    continue
                else:
                    self._logger.info(f"Found vfat partition {partition}, appears to be legacy Windows OS")

            # Try to mount the partition
            try:
                self._logger.info(f"Testing partition {partition} ({fs_type})")
                with self.ctx_mount(partition, self.ROOT):
                    # If we got here, mounting succeeded
                    self._logger.info(f"Found mountable partition: {partition}")
                    return partition

            except Exception as e:
                self._logger.debug(f"Cannot mount {partition}: {e}")
                continue

        self._logger.warning("No mountable partition found")
        return None

    def _is_efi_system_partition(self, partition: str) -> bool:
        """
        Determine if a vfat partition is an EFI System Partition by checking for EFI directory.
        """
        try:
            with self.ctx_mount(partition, self.ROOT):
                files = self.gfs.ls(self.ROOT)
                self._logger.debug(f"Contents of {partition}: {files}")

                has_efi_dir = "EFI" in files

                if has_efi_dir:
                    self._logger.debug(f"{partition} appears to be EFI System Partition")

                return has_efi_dir

        except Exception as e:
            self._logger.warning(f"Error inspecting vfat partition {partition}: {e}")
            # If we can't inspect, assume it's not EFI (safer for legacy systems)
            return False

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._ex.__exit__(exc_type, exc_val, exc_tb)
