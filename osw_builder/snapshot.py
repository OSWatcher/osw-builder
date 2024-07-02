import base64
from typing import Optional

from attrs import define


@define(auto_attribs=True)
class Snapshot:
    name: str
    description: Optional[str]

    @classmethod
    def from_raw_tag(self, tag: str) -> "Snapshot":
        # format: name:description
        # description is a base64 encoded string
        name, bdescription = tag.split(":")
        description = base64.b64decode(bdescription, validate=True).decode("utf-8")
        return Snapshot(name, description)

    def to_raw_tag(self) -> str:
        bdescription = base64.b64encode(self.description.encode("utf-8")).decode("utf-8")
        return f"{self.name}:{bdescription}"
