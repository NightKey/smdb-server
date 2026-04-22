from dataclasses import dataclass
from typing import Dict


@dataclass
class UrlData:
    query: Dict[str, str]
    fragment: str
    data: bytes
    sender: str
    headers: Dict[str, str]

    def __str__(self) -> str:
        return f"UrlData({self.sender})[ path params: {self.query}, fragment: {self.fragment}, data: {self.data} ]"