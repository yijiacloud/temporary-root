from app import snapshot


STATUS = {
    "product_version": "0.7.4",
    "boot_id": "mock-boot-1",
    "selinux": "Enforcing",
    "temporary_root": {"id": "temporary-root", "state": "absent"},
    "components": [
        {"id": "ota", "state": "active", "detail": "frozen"},
        {"id": "ksu", "state": "active", "detail": "version=32547"},
    ],
}


def test_parse_status_extracts_top_fields():
    snap = snapshot.parse_status(STATUS)
    assert snap.product_version == "0.7.4"
    assert snap.selinux == "Enforcing"
    assert snap.temporary_root.state == "absent"


def test_parse_status_components():
    snap = snapshot.parse_status(STATUS)
    assert [c.id for c in snap.components] == ["ota", "ksu"]
    assert snap.components[0].state == "active"
