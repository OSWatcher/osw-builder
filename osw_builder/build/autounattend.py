"""A module to manipulate Windows Autounattend.xml configuration files"""

import xml.etree.ElementTree as ET
from contextlib import suppress
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Optional, Union

from .response_files import ResponseFile


class ElementNotFoundError(Exception):
    pass


class WindowsAutounattend(ResponseFile):
    def __init__(self, autounattend_path: Union[None, str, Path]):
        super().__init__(autounattend_path)
        if autounattend_path is None:
            self.tree = None
            self.nsmap = None
            self.tmp_dir = None
            self.tmp_autounattend = None
            return

        # avoid 'ns0' prefixes in the final XML
        # Windows installer will crash
        ET.register_namespace("", "urn:schemas-microsoft-com:unattend")
        ET.register_namespace("wcm", "http://schemas.microsoft.com/WMIConfig/2002/State")
        ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
        ET.register_namespace("cpi", "urn:schemas-microsoft-com:cpi")
        # load XML
        with open(self.response_file_path, "rb") as f:
            self.tree = ET.ElementTree(ET.fromstring(f.read()))
        self.nsmap: Dict[str, str] = {"ns": "urn:schemas-microsoft-com:unattend"}
        self.tmp_dir: Optional[TemporaryDirectory] = None
        self.tmp_autounattend: Optional[Any] = None

    def __enter__(self):
        self.tmp_dir = TemporaryDirectory()
        self.tmp_autounattend: Path = Path(self.tmp_dir.name) / "Autounattend.xml"
        self.tmp_autounattend_f = open(self.tmp_autounattend, "wb")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.tmp_autounattend_f.close()
        with suppress(FileNotFoundError):
            self.tmp_autounattend.unlink()
        self.tmp_dir.cleanup()

    @property
    def tmp_path(self) -> Path:
        """Return the new Autounattend.xml path"""
        return self.tmp_autounattend
    
    @property
    def autounattend_tmp_path(self) -> Path:
        """Return the new Autounattend.xml path (backward compatibility)"""
        return self.tmp_autounattend
    
    @property 
    def docker_path(self) -> str:
        """Return the Docker container path for autounattend file"""
        return "/packer/Autounattend.xml"
    
    @property
    def varfile_key(self) -> str:
        """Return the varfile key for autounattend files"""
        return "autounattend"

    @property
    def product_key(self):
        """Retrieves the ProductKey"""
        product_key = self.tree.find(".//ns:ProductKey", namespaces=self.nsmap)
        if product_key is None:
            raise ElementNotFoundError("Cannot find ProductKey element")
        key = product_key.find("./ns:Key", namespaces=self.nsmap)
        if key is None:
            raise ElementNotFoundError("Cannot find Key element")
        return key.text

    @product_key.setter
    def product_key(self, value):
        """Sets the ProductKey value"""
        product_key = self.tree.find(".//ns:ProductKey", namespaces=self.nsmap)
        if product_key is None:
            raise ElementNotFoundError("Cannot find ProductKey element")
        key = product_key.find("./ns:Key", namespaces=self.nsmap)
        if key is None:
            # insert
            key = ET.Element("Key")
            product_key.append(key)
        key.text = value

    @property
    def image_name(self) -> ET.Element:
        """Retrieves the Metadata/Value"""
        image_name = self.tree.find(".//ns:MetaData/ns:Value", namespaces=self.nsmap)
        if image_name is None:
            raise ElementNotFoundError("Cannot find Value element")
        return image_name

    @image_name.setter
    def image_name(self, value=None):
        """Sets the Metadata/Value value"""
        if value is None:
            # no need to insert anything
            return
        try:
            image_name = self.image_name
        except ElementNotFoundError:
            # search for OSImage
            # and insert this under OSImage
            # <InstallFrom>
            #     <MetaData wcm:action="add">
            #         <Key>/IMAGE/NAME</Key>
            #         <Value>Windows 11 Pro</Value>
            #     </MetaData>
            # </InstallFrom>

            # search for OSImage
            os_image = self.tree.find(".//ns:OSImage", namespaces=self.nsmap)
            if os_image is None:
                raise ElementNotFoundError("Cannot find OSImage element")

            # create and insert InstallFrom element
            install_from = ET.SubElement(os_image, "InstallFrom")

            # create and insert MetaData element
            metadata = ET.SubElement(install_from, "MetaData")
            metadata.set("wcm:action", "add")

            # create and insert Key element
            key = ET.SubElement(metadata, "Key")
            key.text = "/IMAGE/NAME"

            # create and insert Value element
            value_elem = ET.SubElement(metadata, "Value")
            value_elem.text = value

            # set image_name to the newly created Value element
            image_name = value_elem
            return
        image_name.text = value

    def tostring(self, pretty_print=True):
        """Returns a string representation of the XML tree"""
        return ET.tostring(self.tree.getroot(), encoding="utf-8", xml_declaration=True)

    def write(self):
        """Writes the new Autounattend.xml"""
        self.tree.write(self.tmp_autounattend_f, encoding="utf-8", xml_declaration=True)
    
    def configure(self, config_entry: dict, extra_commands: Optional[List[str]] = None):
        """Configure the autounattend file with the product key and image name from the config entry"""
        if "key" in config_entry:
            self.product_key = config_entry["key"]
        if "image_name" in config_entry:
            self.image_name = config_entry["image_name"]
        if extra_commands:
            for cmd in reversed(extra_commands):
                self.prepend_cmd(cmd)
        self.write()

    def prepend_cmd(self, cmd: str):
        first_logon_commands = self.tree.find(".//ns:FirstLogonCommands", namespaces=self.nsmap)
        if first_logon_commands is None:
            raise ElementNotFoundError("Cannot find FirstLogonCommands element")
        # since we don't know how to create an Element with a namespace
        # deepcopy the first one
        # create SynchronousCommand element
        orig_sync_cmd = first_logon_commands.find("./ns:SynchronousCommand", namespaces=self.nsmap)
        if orig_sync_cmd is None:
            raise ElementNotFoundError("Cannot find SynchronousCommand element")
        sync_cmd = deepcopy(orig_sync_cmd)
        cmd_line = sync_cmd.find("./ns:CommandLine", self.nsmap)
        if cmd_line is None:
            raise ElementNotFoundError("Cannot find CommandLine element")
        cmd_line.text = cmd
        desc = sync_cmd.find("./ns:Description", self.nsmap)
        if desc is None:
            raise ElementNotFoundError("Cannot find Description element")
        desc.text = "Command added by osw-builder config"
        requires_user_input = sync_cmd.find("./ns:RequiresUserInput", namespaces=self.nsmap)
        if requires_user_input is None:
            raise ElementNotFoundError("Cannot find RequiresUserInput element")
        requires_user_input.text = "true"
        # insert element in first position
        first_logon_commands.insert(0, sync_cmd)
        # update order
        for index, child in enumerate(first_logon_commands):
            order = child.find("./ns:Order", self.nsmap)
            order.text = str(index + 1)


# Backward compatibility alias
Autounattend = WindowsAutounattend
