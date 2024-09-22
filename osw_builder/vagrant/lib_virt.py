from contextlib import contextmanager
from pathlib import Path
from typing import Generator

import libvirt

from .domxml import DomXML


@contextmanager
def virt_con_ctxt(uri) -> Generator[libvirt.virConnect, None, None]:
    con = libvirt.open(uri)
    try:
        yield con
    finally:
        con.close()


def get_qcow_path(domaine_name: str, uri: str = "qemu:///system") -> Path:
    with virt_con_ctxt(uri) as con:
        domain = con.lookupByName(domaine_name)
        dom_xml = DomXML(domain.XMLDesc())
        return Path(dom_xml.disk)


def pool_refresh(uri: str = "qemu:///system", pool_name: str = "default"):
    with virt_con_ctxt(uri) as con:
        pool = con.storagePoolLookupByName(pool_name)
        pool.refresh()
