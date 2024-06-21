import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

PLACEHOLDER_VALUE = "# PLACEHOLDER"
LIBVIRT_LOADER_FAIL = "libvirt.loader = '/nonexistent'"
LOG_FILE = "vagrant.log"


def log_subprocess_call(cmdline: list[str], cwd: Path = None, check: bool = True):
    with open(LOG_FILE, "a") as log:
        process = subprocess.Popen(cmdline, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        output = ""
        for line in process.stdout:
            log.write(line)
            output += line
        return_code = process.wait()
        if check and return_code:
            raise subprocess.CalledProcessError(return_code, cmdline, output=output)
        return return_code


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
    cmdline = ["vagrant", "up"]
    if no_destroy:
        cmdline.append("--no-destroy-on-error")
    if no_provision:
        cmdline.append("--no-provision")

    log_subprocess_call(cmdline, cwd=cwd)


def halt(cwd: Path):
    log_subprocess_call(["vagrant", "halt"], cwd=cwd)


def destroy(cwd: Path):
    log_subprocess_call(["vagrant", "destroy", "-f"], cwd=cwd)


def provision(cwd: Path):
    log_subprocess_call(["vagrant", "provision"], cwd=cwd)


def define(cwd: Path):
    """Define the VM in the provider without starting it"""
    with loader_fail_ctxt(cwd):
        try:
            up(cwd, no_destroy=True)
        except subprocess.CalledProcessError as e:
            # check for error "Path '/nonexistent' is not accessible"
            if "Path '/nonexistent' is not accessible" not in e.output:
                raise


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
def ensure_destroyed(cwd: Path):
    try:
        yield
    finally:
        destroy(cwd)
