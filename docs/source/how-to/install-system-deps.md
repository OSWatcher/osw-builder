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
    docker.io python3 python3-pip

# Vagrant libvirt provider
vagrant plugin install vagrant-libvirt
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

Capturing to a graph requires Neo4j and MinIO running somewhere reachable. These are not installed here — use the docker-compose stack from [neogit](https://github.com/OSWatcher/neogit). If you only want to *build* images and not capture, you can skip this; see {doc}`build-without-capture`.
