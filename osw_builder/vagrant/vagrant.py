import logging
import re
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Generator, Optional, Tuple

from attrs import define

from ..settings import settings


@define(auto_attribs=True)
class WinRMConfig:
    Host: str
    HostName: str
    User: str
    Password: str
    Port: int
    RDPHostName: str
    RDPPort: int
    RDPUser: str
    RDPPassword: str


@define(auto_attribs=True)
class SSHConfig:
    Host: str
    HostName: str
    User: str
    Port: int


@define(auto_attribs=True)
class QEMUSnapshot:
    ID: int
    Tag: str


class MachineStateEnum(Enum):
    NOT_CREATED = auto()
    SHUTOFF = auto()
    RUNNING = auto()


PLACEHOLDER_VALUE = "# PLACEHOLDER"
LIBVIRT_LOADER_FAIL = "libvirt.loader = '/nonexistent'"
LIBVIRT_USER_LOADER_FAIL_ERR = "could not load PC BIOS '/nonexistent'"
LIBVIRT_SYSTEM_LOADER_FAIL_ERR = "Path '/nonexistent' is not accessible"
LIBVIRT_LOADER_EFI = "libvirt.loader = '/usr/share/OVMF/OVMF_CODE.fd'"
LOG_FILE = "vagrant.log"


def setup_vagrant_logging() -> logging.Logger:
    """Configure dedicated Vagrant logging with console and file output."""
    vagrant_logger = logging.getLogger("osw_builder.vagrant")

    # Only setup if not already configured
    if not vagrant_logger.handlers:
        vagrant_logger.setLevel(logging.INFO)
        # Prevent propagation to root logger to avoid duplicate console output
        vagrant_logger.propagate = False

        # Use same format as main logger from settings
        formatter = logging.Formatter(settings.logging.format)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        vagrant_logger.addHandler(console_handler)

        # File handler - log to vagrant.log (truncate on each run)
        log_file = Path(LOG_FILE)
        file_handler = logging.FileHandler(log_file, mode="w")  # 'w' mode truncates file
        file_handler.setFormatter(formatter)
        vagrant_logger.addHandler(file_handler)

    return vagrant_logger


def log_subprocess_call(cmdline: list[str], cwd: Optional[Path] = None, check: bool = True):
    # Setup and use dedicated vagrant logger
    vagrant_logger = setup_vagrant_logging()

    # Log the command being executed
    cmd_str = " ".join(cmdline)
    vagrant_logger.info(f"Executing: {cmd_str}")

    # Run subprocess with PIPE to capture output
    process = subprocess.Popen(cmdline, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    output = ""
    # Read output line by line and log in real-time
    if process.stdout:
        for line in process.stdout:
            # Log to vagrant logger in real-time at debug level
            clean_line = line.rstrip("\n\r")
            if clean_line:  # Only log non-empty lines
                vagrant_logger.debug(clean_line)
            output += line

    return_code = process.wait()

    if return_code == 0:
        vagrant_logger.info("Command completed successfully")
    else:
        vagrant_logger.error(f"Command failed with exit code: {return_code}")

    if check and return_code:
        raise subprocess.CalledProcessError(return_code, cmdline, output=output)

    return return_code, output


def box_add(box_path: Path, name: Optional[str] = None):
    cmdline = ["vagrant", "box", "add"]
    if name:
        cmdline.extend(["--name", name])
    cmdline.append(str(box_path))
    log_subprocess_call(cmdline)


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
    _, output = log_subprocess_call(cmdline)
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


def define_vm(cwd: Path):
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
    # If no valid status line found
    raise ValueError(f"Could not parse vagrant status output: {output}")


def snapshot_list(cwd: Path, qcow_path: Path) -> list[QEMUSnapshot]:
    # use qemu-img
    cmdline = ["qemu-img", "snapshot", "-l", str(qcow_path)]
    _, output = log_subprocess_call(cmdline)
    return list(parse_qemu_img_snapshot_list(output))


def snapshot_push(cwd: Path):
    logging.debug("vagrant snapshot push")
    cmdline = ["vagrant", "snapshot", "push"]
    log_subprocess_call(cmdline, cwd=cwd)


def snapshot_pop(cwd: Path):
    logging.debug("vagrant snapshot pop")
    cmdline = ["vagrant", "snapshot", "pop"]
    log_subprocess_call(cmdline, cwd=cwd)


def vagrant_snapshot_list(cwd: Path) -> list[QEMUSnapshot]:
    logging.debug("vagrant snapshot list")
    _, output = log_subprocess_call(["vagrant", "snapshot", "list"], cwd=cwd)
    return list(parse_vagrant_snapshot_list(output))


def snapshot_libvirt_define(domain: str, snapshot: str, parent: Optional[str] = None):
    """From an QEMU internal snapshot name, define it in libvirt metadata"""
    # Get the full domain XML definition
    _, domain_xml = log_subprocess_call(["virsh", "dumpxml", domain])

    # define the XML
    # Note: we use vda as the disk name as this is enforced in our packer-templates/vagrantfile.pkrtpl.hcl
    xml = f"""
    <domainsnapshot>
        <name>{snapshot}</name>
{domain_xml}
        <state>shutoff</state>
        <creationTime>{int(datetime.now().timestamp())}</creationTime>
        <memory snapshot='no'/>
        <disks>
            <disk name='vda' snapshot='internal'/>
        </disks>
    """
    # set parent if any
    if parent:
        xml += f"    <parent><name>{parent}</name></parent>\n"

    xml += "</domainsnapshot>"

    # Create temporary file and write XML
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xml", delete=True) as tmp:
        tmp.write(xml)
        tmp.flush()

        # Use virsh to create the snapshot from XML
        cmdline = ["virsh", "snapshot-create", domain, tmp.name, "--redefine"]
        log_subprocess_call(cmdline)


def parse_qemu_img_snapshot_list(output: str) -> Generator[QEMUSnapshot, None, None]:
    """
        Snapshot list:
    ID        TAG               VM SIZE                DATE     VM CLOCK     ICOUNT
    1         build                 0 B 2024-06-23 01:57:19 00:00:00.000          0
    2         2267602          3.05 GiB 2024-06-23 16:31:11 00:05:17.849
    3         3125217          2.35 GiB 2024-06-23 16:35:46 00:02:59.605
    4         4056254          2.05 GiB 2024-06-23 16:39:09 00:01:39.459
    5         890830           2.92 GiB 2024-06-23 16:43:45 00:03:26.232
    6         3161102          1.93 GiB 2024-06-23 16:47:33 00:02:12.826
    7         4033631          1.96 GiB 2024-06-23 16:52:11 00:03:40.142
    8         4480730           1.9 GiB 2024-06-23 16:54:46 00:01:34.657
    9         4023057          1.93 GiB 2024-06-23 16:57:34 00:01:49.845
    10        4019474          3.56 GiB 2024-06-23 17:31:24 00:32:51.087
    """
    for line in output.splitlines()[2:]:
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"\s{2,}", line)
        if len(parts) < 2:
            continue

        yield QEMUSnapshot(
            ID=int(parts[0]),
            Tag=parts[1],
        )


def parse_vagrant_snapshot_list(output: str) -> Generator[QEMUSnapshot, None, None]:
    for i, line in enumerate(output.splitlines()[1:], 1):
        line = line.strip()
        if not line:
            continue
        # sample line
        # build
        yield QEMUSnapshot(ID=i, Tag=line)


def winrm_config(cwd: Path) -> WinRMConfig:
    logging.debug("vagrant winrm-config")
    _, output = log_subprocess_call(["vagrant", "winrm-config"], cwd=cwd)
    return parse_winrm_config(output)


def ssh_config(cwd: Path) -> SSHConfig:
    logging.debug("vagrant ssh-config")
    _, output = log_subprocess_call(["vagrant", "ssh-config"], cwd=cwd)
    return parse_ssh_config(output)


def parse_winrm_config(output: str) -> WinRMConfig:
    """sample output:
    Host win10-ts1-1507
        HostName 192.168.122.173
        User vagrant
        Password vagrant
        Port 5985
        RDPHostName 192.168.122.173
        RDPPort 3389
        RDPUser vagrant
        RDPPassword vagrant
    """
    config = {}
    lines = output.strip().split("\n")

    for line in lines:
        if line.strip():
            key, value = line.strip().split(None, 1)
            config[key] = value

    # Ensure required fields are present
    required_fields = [
        "Host",
        "HostName",
        "User",
        "Password",
        "Port",
        "RDPHostName",
        "RDPPort",
        "RDPUser",
        "RDPPassword",
    ]
    for field in required_fields:
        if field not in config:
            raise ValueError(f"Missing required WinRM config field: {field}")

    return WinRMConfig(
        Host=config["Host"],
        HostName=config["HostName"],
        User=config["User"],
        Password=config["Password"],
        Port=int(config["Port"]),
        RDPHostName=config["RDPHostName"],
        RDPPort=int(config["RDPPort"]),
        RDPUser=config["RDPUser"],
        RDPPassword=config["RDPPassword"],
    )


def parse_ssh_config(output: str) -> SSHConfig:
    """sample output:
    Host ubuntu-17.10
    HostName 192.168.122.92
    User vagrant
    Port 22
    UserKnownHostsFile /dev/null
    StrictHostKeyChecking no
    PasswordAuthentication no
    IdentitiesOnly yes
    LogLevel FATAL
    PubkeyAcceptedKeyTypes +ssh-rsa
    HostKeyAlgorithms +ssh-rsa

    """
    config = {}
    lines = output.strip().split("\n")

    for line in lines:
        if line.strip():
            key, value = line.strip().split(None, 1)
            config[key] = value

    # Ensure required fields are present
    required_fields = ["Host", "HostName", "User", "Port"]
    for field in required_fields:
        if field not in config:
            raise ValueError(f"Missing required SSH config field: {field}")

    return SSHConfig(
        Host=config["Host"],
        HostName=config["HostName"],
        User=config["User"],
        Port=int(config["Port"]),
    )


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


def set_loader_efi(cwd: Path):
    # revert back to original
    with open(cwd / "Vagrantfile", "r") as f:
        content = f.read()
        # replace LIBVIRT_LOADER_FAIL
        print("Setting loader to EFI !")
        content = content.replace(PLACEHOLDER_VALUE, LIBVIRT_LOADER_EFI)
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
    except BaseException as e:
        if only_on_error:
            logging.debug("Error: %s. Destroying VM", e)
            destroy(cwd)
        raise
    finally:
        if not only_on_error:
            logging.debug("Destroying VM")
            destroy(cwd)
