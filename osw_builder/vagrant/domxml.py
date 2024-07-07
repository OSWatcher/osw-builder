import xml.etree.ElementTree as ET


class DomXML:
    def __init__(self, xml_desc):
        self.tree = ET.fromstring(xml_desc)

    # helpers
    def findfirst(self, xpath):
        return self.tree.findall(xpath)[0]

    @property
    def name(self):
        return self.findfirst("./name").text

    @name.setter
    def name(self, value):
        self.findfirst("./name").text = value

    @property
    def memory(self):
        return self.findfirst("memory").text

    @memory.setter
    def memory(self, value):
        self.findfirst("./memory").text = value

    @property
    def disk(self):
        return self.findfirst('./devices/disk[@device="disk"]/source').get("file")

    @disk.setter
    def disk(self, value):
        self.findfirst('./devices/disk[@device="disk"]/source').set("file", value)

    def add_network(self):
        devices = self.findfirst("./devices")
        interface = ET.Element("interface", {"type": "network"})
        interface.append(ET.Element("source", {"network": "default"}))
        interface.append(ET.Element("model", {"type": "e1000e"}))
        devices.append(interface)

    def tostring(self):
        """Generate new XML string from tree object"""
        return ET.tostring(self.tree, encoding="unicode")
