# Ubuntu Support Implementation Plan

## Overview

This document outlines the architectural changes required to add Ubuntu image support to osw-builder. Currently, the system is heavily focused on Windows builds, requiring significant refactoring to support multiple operating systems.

## Current Windows-Specific Issues

### 1. Build Module (`osw_builder/build/build.py`)

**Lines 128-150: Template and Answer File Processing**
- Hardcoded `WINDOWS_TEMPLATE = "windows.pkr.hcl"`
- Windows-specific Autounattend.xml processing logic
- Conditional logic assumes Windows answer files (`.xml` vs `.SIF`)

**Lines 177-182: Docker Volume Mounts**
- Autounattend.xml mounted to `/packer/Autounattend.xml`
- WINNT.SIF for WinXP mounted to `/packer/WINNT.SIF`
- No support for Ubuntu preseed files

**Lines 190-203: Packer Configuration**
- Hardcoded `-only qemu.windows` builder selection
- Template selection limited to `WINDOWS_TEMPLATE`

### 2. Main Orchestration (`osw_builder/__main__.py`)

**Lines 185-219: Windows Update Processing**
- WinRM-specific configuration and connection logic
- Windows Update API integration (`winupdate` library)
- Blacklisted update handling specific to Windows KB articles

### 3. Answer File Processing (`osw_builder/build/autounattend.py`)

**Entire Module: Windows-Only**
- Complete module dedicated to Windows Autounattend.xml manipulation
- XML namespace handling for Microsoft schemas
- Product key and image name configuration specific to Windows installation

## Proposed Architecture Changes

### Phase 1: Abstract OS-Specific Build Logic

#### Create OS Builder Abstraction

**New File: `osw_builder/build/os_builders.py`**

```python
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Optional, Tuple

class OSBuilder(ABC):
    """Abstract base class for OS-specific build logic"""
    
    @abstractmethod
    def get_template(self) -> str:
        """Return the Packer template filename"""
        pass
    
    @abstractmethod 
    def get_packer_builder_name(self) -> str:
        """Return the Packer builder name (e.g., 'qemu.windows')"""
        pass
    
    @abstractmethod
    def prepare_answer_file(self, config_entry: dict, extra_commands: Optional[List[str]] = None) -> Dict[str, str]:
        """
        Prepare OS-specific answer/configuration files
        Returns dict of {host_path: container_path} for Docker volume mounts
        """
        pass
    
    @abstractmethod
    def get_docker_volumes(self, base_volumes: Dict, answer_files: Dict[str, str]) -> Dict:
        """Return complete Docker volume configuration"""
        pass
    
    @abstractmethod
    def supports_updates(self) -> bool:
        """Return True if OS supports automated update processing"""
        pass

class WindowsBuilder(OSBuilder):
    """Windows-specific build logic"""
    
    def get_template(self) -> str:
        return "windows.pkr.hcl"
    
    def get_packer_builder_name(self) -> str:
        return "qemu.windows"
    
    def prepare_answer_file(self, config_entry: dict, extra_commands: Optional[List[str]] = None) -> Dict[str, str]:
        """Handle Autounattend.xml and WINNT.SIF preparation"""
        varfile_path = PACKER_TEMPLATES_DIR / config_entry.get("varfile")
        with open(varfile_path) as f:
            varfile_data = hcl2.load(f)
        
        auto_path = PACKER_TEMPLATES_DIR / varfile_data["autounattend"]
        
        if auto_path.suffix == '.xml':
            # Autounattend.xml processing (existing logic)
            tmp_autounattend = Autounattend(auto_path)
            configure_autounattend(tmp_autounattend, config_entry, extra_commands)
            return {
                str(tmp_autounattend.autounattend_tmp_path): PACKER_DOCKER_AUTOUNATTEND_PATH
            }
        else:
            # WINNT.SIF for Windows XP
            return {
                str(auto_path): PACKER_DOCKER_AUTOUNATTEND_PATH_XP
            }
    
    def get_docker_volumes(self, base_volumes: Dict, answer_files: Dict[str, str]) -> Dict:
        volumes = base_volumes.copy()
        volumes.update({
            host_path: {"bind": container_path, "mode": "ro"} 
            for host_path, container_path in answer_files.items()
        })
        return volumes
    
    def supports_updates(self) -> bool:
        return True

class UbuntuBuilder(OSBuilder):
    """Ubuntu-specific build logic"""
    
    def get_template(self) -> str:
        return "ubuntu.pkr.hcl"
    
    def get_packer_builder_name(self) -> str:
        return "qemu.ubuntu"
    
    def prepare_answer_file(self, config_entry: dict, extra_commands: Optional[List[str]] = None) -> Dict[str, str]:
        """Handle preseed.cfg preparation"""
        preseed_file = config_entry.get("preseed", "preseed.cfg")
        preseed_path = PACKER_TEMPLATES_DIR / "http" / preseed_file
        
        if not preseed_path.exists():
            raise FileNotFoundError(f"Preseed file not found: {preseed_path}")
        
        # TODO: Implement preseed customization if needed (similar to Autounattend)
        # For now, use the file as-is
        return {
            str(preseed_path): "/packer/preseed.cfg"
        }
    
    def get_docker_volumes(self, base_volumes: Dict, answer_files: Dict[str, str]) -> Dict:
        volumes = base_volumes.copy()
        volumes.update({
            host_path: {"bind": container_path, "mode": "ro"} 
            for host_path, container_path in answer_files.items()
        })
        return volumes
    
    def supports_updates(self) -> bool:
        return True  # Ubuntu supports apt updates

def get_os_builder(os_type: str) -> OSBuilder:
    """Factory function to get appropriate OS builder"""
    builders = {
        "windows": WindowsBuilder,
        "ubuntu": UbuntuBuilder,
    }
    
    if os_type not in builders:
        raise ValueError(f"Unsupported OS type: {os_type}")
    
    return builders[os_type]()
```

#### Update Build Function

**Modified: `osw_builder/build/build.py`**

```python
@contextmanager
def build_image(
    template: str,
    varfile: str, 
    config_entry: dict,
    extra_firstlogin_cmds: Optional[list[str]],
    packer_args: list[str] = None,
    network: bool = False,
) -> Generator[Path, None, None]:
    logging.info("Building image")
    
    # Determine OS type and get appropriate builder
    os_type = config_entry.get("os_type", "windows")  # Default to windows for backward compatibility
    builder = get_os_builder(os_type)
    
    sha1digest = validate_source_and_compute_sha1(config_entry)
    varfile_data = update_varfile(PACKER_TEMPLATES_DIR / varfile, config_entry["source"], sha1digest)
    
    with ExitStack() as ex:
        # Prepare OS-specific answer files
        answer_files = builder.prepare_answer_file(config_entry, extra_firstlogin_cmds)
        
        # Prepare varfile
        tmp_varfile_path = ex.enter_context(write_temp_varfile(varfile_data))
        
        # Force packer cache download
        fake_run_packer(builder, tmp_varfile_path, answer_files, network=True)
        
        # Run actual build
        yield run_packer(builder, tmp_varfile_path, answer_files, packer_args, network=network)

def run_packer(
    builder: OSBuilder, 
    varfile: str, 
    answer_files: Dict[str, str], 
    packer_args: list[str], 
    network: bool
) -> Path:
    with ensure_cleanup_output():
        dk_client = docker.from_env()
        dk_client.login(username="oswatcher", password=os.environ["GHCR_TOKEN"], registry="ghcr.io")

        if network:
            logging.info(f"Pulling the latest {PACKER_TEMPLATES_IMAGE} image")
            dk_client.images.pull(PACKER_TEMPLATES_IMAGE)

        # Base volumes
        packer_home_cache = Path.home() / ".cache" / "packer"
        packer_home_cache.mkdir(parents=True, exist_ok=True)
        base_volumes = {
            packer_home_cache: {"bind": "/cache", "mode": "rw"},
            PACKER_TEMPLATES_DIR: {"bind": "/output_parent", "mode": "rw"},
            varfile: {"bind": "/packer/vars.pkrvars.hcl", "mode": "ro"},
        }
        
        # Get complete volumes from OS builder
        volumes = builder.get_docker_volumes(base_volumes, answer_files)
        
        # Build command line
        cmdline = [
            "build",
            "-only",
            builder.get_packer_builder_name(),  # OS-specific builder
            "-var-file",
            "docker.pkrvars.hcl",
            "-var-file", 
            "vars.pkrvars.hcl",
        ]

        # Add packer arguments
        var_packer_args = []
        for arg in packer_args:
            var_packer_args.extend(["-var", arg])
        cmdline.extend(var_packer_args)
        
        # Add template
        cmdline.append(builder.get_template())  # OS-specific template

        # Run Docker container (existing logic)
        # ... rest of Docker execution logic remains the same
```

### Phase 2: Enhance Configuration Schema

#### Update Configuration Format

**Modified: `osw_builder/default_settings.yaml`**

```yaml
images:
  # Existing Windows images (add os_type field)
  - name: "win10-ts1-1507"
    os_type: "windows"  # New field (default for backward compatibility)
    description: "Windows 10 Threshold 1 (1507)"
    source: "https://storage.grapheos.app/images/win10/Win10_1507_English_x64.iso"
    sha1: "60cce9e9c6557335b4f7b18d02cfe2b438a8b3e2"
    key: *key_pro
    image_name: *win10_pro
    template: *win10_template
    varfile: *win10_varfile
    extra_firstlogin_cmds: *win10_extra_firstlogin_cmds

  # New Ubuntu images
  - name: "ubuntu-16.04-server"
    os_type: "ubuntu"
    description: "Ubuntu 16.04 LTS Server"
    source: "http://old-releases.ubuntu.com/releases/xenial/ubuntu-16.04-server-amd64.iso"
    sha1: "70db69379816b91eb01559212ae474a36ecec9ef"
    template: "ubuntu.pkr.hcl"
    varfile: "ubuntu.pkrvars.hcl"
    preseed: "preseed.cfg"
    ssh_username: "vagrant"
    ssh_password: "vagrant"
    search_updates: true   # Enable apt updates
    apply_updates: true
    idle: false           # Skip idle snapshot for Ubuntu

  - name: "ubuntu-18.04-server"
    os_type: "ubuntu"
    description: "Ubuntu 18.04 LTS Server"
    source: "http://old-releases.ubuntu.com/releases/bionic/ubuntu-18.04-server-amd64.iso"
    sha1: "73ae6579ef7c51d944a0be5c4c48f748bfd689df"
    template: "ubuntu.pkr.hcl"
    varfile: "ubuntu.pkrvars.hcl"
    preseed: "preseed.cfg"
    ssh_username: "vagrant"
    ssh_password: "vagrant"
    search_updates: true
    apply_updates: true
    idle: false

# Add Ubuntu branch
branches:
  master:
    - *win95
    # ... existing Windows images ...
    
  ubuntu:
    - "ubuntu-16.04-server"
    - "ubuntu-18.04-server"
```

### Phase 3: Update Main Orchestration

#### Modify Main Function

**Modified: `osw_builder/__main__.py`**

```python
def capture_os(os_name, args):
    logging.info("Capturing OS %s", os_name)
    box_name = os_name

    # ... existing setup code ...

    try:
        entry = next((entry for entry in settings["images"] if entry["name"] == os_name))
    except StopIteration:
        raise RuntimeError("Could not find OS name")

    # Get OS type from configuration
    os_type = entry.get("os_type", "windows")  # Default to windows for backward compatibility
    
    # ... existing VM setup code ...

    # OS-specific update processing
    if search_updates and apply_updates:
        if os_type == "windows":
            # Existing Windows Update logic (lines 185-219)
            handle_windows_updates(vagrant_dir, qcow_path, snap_list, branch_name, previous_raw_snap)
        elif os_type == "ubuntu":
            # New Ubuntu update logic
            handle_ubuntu_updates(vagrant_dir, qcow_path, snap_list, branch_name, previous_raw_snap)
        else:
            logging.warning("Updates not supported for OS type: %s", os_type)

def handle_windows_updates(vagrant_dir: Path, qcow_path: Path, snap_list: list, branch_name: str, previous_raw_snap: str):
    """Extract existing Windows Update logic"""
    # Move lines 185-219 from capture_os into this function
    with vagrant.up_down_ctxt(vagrant_dir):
        logging.info("Searching for Windows Updates")
        winrm_config = vagrant.winrm_config(vagrant_dir)
        win_update = WinUpdate(winrm_config.HostName, debug_lvl=1)
        # ... existing Windows Update logic ...

def handle_ubuntu_updates(vagrant_dir: Path, qcow_path: Path, snap_list: list, branch_name: str, previous_raw_snap: str):
    """Handle Ubuntu package updates"""
    with vagrant.up_down_ctxt(vagrant_dir):
        logging.info("Searching for Ubuntu package updates")
        ssh_config = vagrant.ssh_config(vagrant_dir)  # Need to implement
        
        # Get available package updates
        updates = get_ubuntu_updates(ssh_config)
        
        for index, update in enumerate(updates):
            pkg_name = f"pkg-{update.name}"
            
            # Check if update already processed
            if any(Snapshot.from_raw_tag(snap.Tag).name == pkg_name for snap in snap_list):
                logging.warning("Found existing snapshot for package %s. Skipping", pkg_name)
                continue
                
            logging.info("[%s][%s] %s", index + 1, pkg_name, update.description)
            
            try:
                with vagrant.up_down_ctxt(vagrant_dir):
                    apply_ubuntu_update(ssh_config, update)
            except UpdateFailedError:
                logging.warning("Package update failed")
                vagrant.snapshot_restore(vagrant_dir, previous_raw_snap)
            else:
                # Success - create snapshot
                snap = Snapshot(pkg_name, update.description)
                raw_tag = snap.to_raw_tag()
                vagrant.snapshot_save(vagrant_dir, raw_tag)
                previous_raw_snap = raw_tag
                capture_neogit(qcow_path, pkg_name, branch_name, unique=True, desc=update.description)
```

### Phase 4: Implement Ubuntu Update Handling

#### Create Ubuntu Update Module

**New File: `osw_builder/ubuntu_updates.py`**

```python
import logging
import subprocess
from dataclasses import dataclass
from typing import List
import paramiko


@dataclass
class UbuntuUpdate:
    name: str
    version: str
    description: str


class UpdateFailedError(Exception):
    pass


def get_ubuntu_updates(ssh_config) -> List[UbuntuUpdate]:
    """Get list of available package updates via SSH"""
    with paramiko.SSHClient() as ssh:
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=ssh_config.hostname,
            username=ssh_config.username,
            password=ssh_config.password,
            port=ssh_config.port
        )
        
        # Update package list
        stdin, stdout, stderr = ssh.exec_command("sudo apt update")
        if stdout.channel.recv_exit_status() != 0:
            raise UpdateFailedError("Failed to update package list")
        
        # Get upgradeable packages
        stdin, stdout, stderr = ssh.exec_command("apt list --upgradable")
        output = stdout.read().decode()
        
        updates = []
        for line in output.splitlines()[1:]:  # Skip header
            if '/' in line:
                parts = line.split()
                if len(parts) >= 2:
                    name = parts[0].split('/')[0]
                    version = parts[1]
                    description = f"Upgrade {name} to {version}"
                    updates.append(UbuntuUpdate(name, version, description))
        
        return updates


def apply_ubuntu_update(ssh_config, update: UbuntuUpdate):
    """Apply a specific package update"""
    with paramiko.SSHClient() as ssh:
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=ssh_config.hostname,
            username=ssh_config.username,
            password=ssh_config.password,
            port=ssh_config.port
        )
        
        # Install specific package
        cmd = f"sudo DEBIAN_FRONTEND=noninteractive apt-get install -y {update.name}"
        stdin, stdout, stderr = ssh.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()
        
        if exit_status != 0:
            error_output = stderr.read().decode()
            raise UpdateFailedError(f"Failed to install {update.name}: {error_output}")
        
        logging.info("Successfully installed %s", update.name)
```

#### Add SSH Configuration Support

**Modified: `osw_builder/vagrant/vagrant.py`**

```python
@dataclass
class SSHConfig:
    hostname: str
    username: str
    password: str
    port: int


def ssh_config(cwd: Path) -> SSHConfig:
    """Get SSH configuration for Ubuntu VMs"""
    logging.debug("vagrant ssh-config")
    _, output = log_subprocess_call(["vagrant", "ssh-config"], cwd=cwd)
    return parse_ssh_config(output)


def parse_ssh_config(output: str) -> SSHConfig:
    """Parse vagrant ssh-config output"""
    config = {}
    lines = output.strip().split("\n")
    
    for line in lines:
        line = line.strip()
        if line and not line.startswith("Host "):
            key, value = line.split(None, 1)
            config[key] = value
    
    return SSHConfig(
        hostname=config.get("HostName", "localhost"),
        username=config.get("User", "vagrant"),
        password="vagrant",  # Default Vagrant password
        port=int(config.get("Port", "22"))
    )
```

### Phase 5: Update Dependencies and Configuration

#### Add Required Dependencies

**Modified: `pyproject.toml`**

```toml
[tool.poetry.dependencies]
# ... existing dependencies ...
paramiko = "^3.4.0"  # For SSH connections to Ubuntu VMs
```

#### Create Ubuntu-Specific Packer Variables

**New File: `osw_builder/packer-templates/ubuntu-16.04.pkrvars.hcl`**

```hcl
vm_name = "ubuntu-16.04-server"
cpus = "2"
memory = "2048"
disk_size = "20480"
iso_checksum_type = "sha1"
iso_checksum = "70db69379816b91eb01559212ae474a36ecec9ef"
iso_url = "http://old-releases.ubuntu.com/releases/xenial/ubuntu-16.04-server-amd64.iso"
preseed = "preseed.cfg"
ssh_username = "vagrant"
ssh_password = "vagrant"
ssh_fullname = "vagrant"
hostname = "ubuntu-vagrant"
```

## Implementation Timeline

### Phase 1: Foundation (Week 1-2)
- Create OS builder abstraction
- Implement Windows and Ubuntu builders
- Add unit tests for builders

### Phase 2: Build System Integration (Week 3-4)
- Refactor `build_image` function
- Update Docker volume mounting
- Test Windows builds still work

### Phase 3: Main Orchestration (Week 5-6)
- Add OS-type branching in `capture_os`
- Implement Ubuntu update handling
- Add SSH configuration support

### Phase 4: Configuration and Testing (Week 7-8)
- Add Ubuntu image definitions
- Create integration tests
- Document Ubuntu image creation process

### Phase 5: Polish and Documentation (Week 9-10)
- Performance optimization
- Error handling improvements
- Complete documentation

## Benefits

### Architectural Improvements
- **Clean Separation**: OS-specific logic isolated in dedicated builders
- **Extensibility**: Easy to add support for other OS types (CentOS, Debian, etc.)
- **Testability**: Each OS builder can be unit tested independently
- **Maintainability**: Reduced coupling between OS-specific concerns

### Functional Benefits
- **Multi-OS Support**: Unified workflow for Windows and Ubuntu images
- **Consistent Interface**: Same CLI commands work for all OS types
- **Update Management**: Automated package updates for Ubuntu similar to Windows Updates
- **Snapshot Management**: Consistent snapshot naming and organization

### Risk Mitigation
- **Backward Compatibility**: Existing Windows configurations continue to work
- **Incremental Deployment**: Can be implemented and tested phase by phase
- **Rollback Safety**: Each phase can be independently rolled back if needed

## Success Metrics

- **Functional**: Successfully build and capture Ubuntu 16.04 and 18.04 images
- **Quality**: All existing Windows functionality continues to work
- **Performance**: Build times comparable to current Windows-only implementation
- **Maintainability**: Code complexity reduced through better separation of concerns
- **Documentation**: Complete documentation for Ubuntu image creation workflow