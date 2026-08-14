"""Parse xpad2 status --json into a typed snapshot."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ComponentStatus:
    id: str
    state: str
    detail: str | None = None


@dataclass
class Snapshot:
    product_version: str
    boot_id: str
    selinux: str
    temporary_root: ComponentStatus
    components: list[ComponentStatus]


def _component(obj: dict) -> ComponentStatus:
    return ComponentStatus(id=obj["id"], state=obj["state"], detail=obj.get("detail"))


def parse_status(obj: dict) -> Snapshot:
    tmp = obj.get("temporary_root") or {"id": "temporary-root", "state": "absent"}
    return Snapshot(
        product_version=obj.get("product_version", ""),
        boot_id=obj.get("boot_id", ""),
        selinux=obj.get("selinux", ""),
        temporary_root=_component(tmp),
        components=[_component(c) for c in obj.get("components", [])],
    )
