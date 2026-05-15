import xml.etree.ElementTree as ET
from typing import Any


def _local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def parse_wechat_xml(xml_body: str) -> dict[str, Any]:
    """Parse WeChat webhook XML into a plain dict (CDATA text values)."""
    root = ET.fromstring(xml_body)
    out: dict[str, Any] = {}
    for child in root:
        key = _local_tag(child.tag)
        out[key] = (child.text or "").strip()
    return out
