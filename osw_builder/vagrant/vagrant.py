import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


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


def up(cwd: Path):
    subprocess.check_call(["vagrant", "up", "--no-provision"], cwd=cwd)


def halt(cwd: Path):
    subprocess.check_call(["vagrant", "halt"], cwd=cwd)


def destroy(cwd: Path):
    subprocess.check_call(["vagrant", "destroy", "-f"], cwd=cwd)


def provision(cwd: Path):
    subprocess.check_call(["vagrant", "provision"], cwd=cwd)


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
