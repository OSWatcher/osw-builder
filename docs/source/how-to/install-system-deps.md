# Install system dependencies

osw-builder orchestrates several external tools. They are not Python packages, so Poetry cannot install them — you install them through your OS package manager.

## What you need and why

| Dependency | Why osw-builder needs it |
|------------|--------------------------|
| QEMU/KVM + libvirt | The hypervisor that runs the VMs |
| Vagrant + `vagrant-libvirt` | Manages VM lifecycle (define, boot, snapshot, destroy) |
| Docker | Runs the Packer build container (`ghcr.io/oswatcher/packer-templates`) |
| `libguestfs-tools` | Reads the offline disk image during capture |
| `sshpass` | Non-interactive SSH into VMs when installing updates |
| Python 3.11+ and Poetry | Runtime and dependency management |

## On Debian / Ubuntu

```bash
sudo apt update
sudo apt install -y \
    qemu-kvm libvirt-daemon-system libvirt-clients \
    vagrant libguestfs-tools sshpass \
    docker.io python3 python3-pip \
    libguestfs-dev libvirt-dev python3-dev pkg-config gcc

# Vagrant libvirt provider
vagrant plugin install vagrant-libvirt
```

```{note}
The last line installs build headers, not runtime tools. `guestfs` and
`libvirt-python` are C extensions that Poetry compiles from source, so without
`libguestfs-dev` and `libvirt-dev` the install fails at
`fatal error: guestfs.h: No such file or directory` long before you reach a
capture.
```

## Post-install checks

Add yourself to the `libvirt`, `kvm`, and `docker` groups so you do not need `sudo`:

```bash
sudo usermod -aG libvirt,kvm,docker "$USER"
# log out and back in for group changes to take effect
```

Verify each tool works:

```bash
kvm-ok                      # "KVM acceleration can be used"
virsh --connect qemu:///session list   # connects without error
vagrant --version
docker run --rm hello-world
sudo libguestfs-test-tool   # ends with "libguestfs-test-tool: PASS"
```

```{warning}
`libguestfs` is the dependency most likely to fail silently. If capture errors out with a guestfs mount failure, run `libguestfs-test-tool` first — it almost always reveals a missing kernel-read permission or a broken appliance.
```

## Infrastructure (separate from system packages)

Capturing to a graph requires a reachable Neo4j instance; object storage defaults to the local filesystem, so MinIO is optional. The quickest way to get Neo4j is a single container — `docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/your-password neo4j:5.26` (see [neogit](https://github.com/OSWatcher/neogit) for details, or [oswatcher-deploy](https://github.com/OSWatcher/oswatcher-deploy) for the full stack with MinIO). If you only want to *build* images and not capture, you can skip this entirely; see {doc}`build-without-capture`.
