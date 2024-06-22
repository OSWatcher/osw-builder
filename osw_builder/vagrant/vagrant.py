import logging
import re
import subprocess
from contextlib import contextmanager
from enum import Enum, auto
from pathlib import Path
from typing import Generator, Tuple


class MachineStateEnum(Enum):
    NOT_CREATED = auto()
    SHUTOFF = auto()
    RUNNING = auto()


PLACEHOLDER_VALUE = "# PLACEHOLDER"
LIBVIRT_LOADER_FAIL = "libvirt.loader = '/nonexistent'"
LIBVIRT_USER_LOADER_FAIL_ERR = "could not load PC BIOS '/nonexistent'"
LIBVIRT_SYSTEM_LOADER_FAIL_ERR = "Path '/nonexistent' is not accessible"
LOG_FILE = "vagrant.log"


def log_subprocess_call(cmdline: list[str], cwd: Path = None, check: bool = True):
    with open(LOG_FILE, "a") as log:
        process = subprocess.Popen(cmdline, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        output = ""
        for line in process.stdout:
            log.write(line)
            # force flush on every line to see progress live when tail -f vagrant.log
            log.flush()
            output += line
        return_code = process.wait()
        if check and return_code:
            raise subprocess.CalledProcessError(return_code, cmdline, output=output)
        return return_code, output


def box_add(box_path: Path, name: str = None):
    cmdline = ["vagrant", "box", "add"]
    if name:
        cmdline.extend(["--name", name])
    cmdline.append(str(box_path))
    subprocess.check_call(cmdline)


def parse_box_list(output: str) -> Generator[str, None, None]:
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        # sample line
        # generic/debian10   (libvirt, 4.3.12, (amd64))

        # only gather list of names
        yield line.split()[0]


def box_list() -> list[str]:
    cmdline = ["vagrant", "box", "list"]
    output = subprocess.check_output(cmdline).decode()
    return list(parse_box_list(output))


def box_exists(name: str) -> bool:
    return name in box_list()


def up(cwd: Path, no_destroy: bool = False, no_provision: bool = True):
    logging.debug("vagrant up - %s %s", no_destroy, no_provision)
    cmdline = ["vagrant", "up"]
    if no_destroy:
        cmdline.append("--no-destroy-on-error")
    if no_provision:
        cmdline.append("--no-provision")

    log_subprocess_call(cmdline, cwd=cwd)


def halt(cwd: Path):
    logging.debug("vagrant halt")
    log_subprocess_call(["vagrant", "halt"], cwd=cwd)


def destroy(cwd: Path):
    logging.debug("vagrant destroy")
    log_subprocess_call(["vagrant", "destroy", "-f"], cwd=cwd)


def provision(cwd: Path):
    logging.debug("vagrant provision")
    log_subprocess_call(["vagrant", "provision"], cwd=cwd)


def define(cwd: Path):
    """Define the VM in the provider without starting it"""
    with loader_fail_ctxt(cwd):
        try:
            up(cwd, no_destroy=True)
        except subprocess.CalledProcessError as e:
            # check for error "Path '/nonexistent' is not accessible"
            if LIBVIRT_SYSTEM_LOADER_FAIL_ERR not in e.output and LIBVIRT_USER_LOADER_FAIL_ERR not in e.output:
                raise


def snapshot_save(cwd: Path, name: str):
    logging.debug("vagrant snapshot save %s", name)
    cmdline = ["vagrant", "snapshot", "save", name]
    log_subprocess_call(cmdline, cwd=cwd)


def status(cwd: Path):
    logging.debug("vagrant status")
    _, output = log_subprocess_call(["vagrant", "status"], cwd=cwd)
    return parse_status(output)


def snapshot_restore(cwd: Path, name: str):
    logging.debug("vagrant snapshot restore %s", name)
    log_subprocess_call(["vagrant", "snapshot", "restore", name], cwd=cwd)


def parse_status(output: str) -> Tuple[str, MachineStateEnum]:
    """
    Current machine states:

    win10-ts1-1507            not created (libvirt)

    The Libvirt domain is not created. Run `vagrant up` to create it.
    """
    # extract vm and machine state
    # return Tuple[str, MachineStateEnum]
    for line in output.splitlines()[2:]:
        line = line.strip()
        if not line:
            continue
        # sample line
        # win10-ts1-1507            not created (libvirt)
        match = re.match(r"(\S+)\s+([^\(]+)\((\w+)\)", line)
        if not match:
            continue
        vm, state, provider = match.groups()
        state = state.strip()
        try:
            return vm, MachineStateEnum[state.upper()]
        except KeyError:
            if state == "not created":
                return vm, MachineStateEnum.NOT_CREATED
            raise


def snapshot_list(cwd: Path) -> list[str]:
    logging.debug("vagrant snapshot list")
    _, output = log_subprocess_call(["vagrant", "snapshot", "list"], cwd=cwd)
    return list(parse_snapshot_list(output))


def parse_snapshot_list(output: str) -> Generator[str, None, None]:
    for line in output.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        # sample line
        # build
        yield line


@contextmanager
def loader_fail_ctxt(cwd: Path):
    try:
        with open(cwd / "Vagrantfile", "r") as f:
            content = f.read()
            # replace PLACEHOLDER_VALUE
            content = content.replace(PLACEHOLDER_VALUE, LIBVIRT_LOADER_FAIL)
            # write it back
            with open(cwd / "Vagrantfile", "w") as f:
                f.write(content)
            yield
    finally:
        # revert back to original
        with open(cwd / "Vagrantfile", "r") as f:
            content = f.read()
            # replace LIBVIRT_LOADER_FAIL
            content = content.replace(LIBVIRT_LOADER_FAIL, PLACEHOLDER_VALUE)
            # write it back
            with open(cwd / "Vagrantfile", "w") as f:
                f.write(content)


@contextmanager
def up_down_ctxt(cwd: Path):
    try:
        up(cwd)
        yield
    finally:
        halt(cwd)


@contextmanager
def ensure_destroyed(cwd: Path, only_on_error: bool = False):
    try:
        yield
    except BaseException:
        if only_on_error:
            destroy(cwd)
        raise
    finally:
        if not only_on_error:
            destroy(cwd)
