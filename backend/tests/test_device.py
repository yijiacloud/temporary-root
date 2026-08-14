from app import device


SAMPLE = """List of devices attached
abc123               device product:ls12 model:XPad2 device:ls12_mt8797_wifi_64
offline              unauthorized transport_id:2
"""


def test_parse_devices_parses_serial_state_attrs():
    devices = device.parse_devices(SAMPLE)
    assert len(devices) == 2
    assert devices[0].serial == "abc123"
    assert devices[0].state == "device"
    assert devices[0].attrs["model"] == "XPad2"
    assert devices[1].state == "unauthorized"


def test_device_memory_roundtrip(tmp_path):
    path = tmp_path / "memory.json"
    mem = device.DeviceMemory(selected_serial="abc123")
    device.save(mem, path)
    loaded = device.load(path)
    assert loaded.selected_serial == "abc123"


def test_device_memory_missing_file_defaults(tmp_path):
    loaded = device.load(tmp_path / "nope.json")
    assert loaded.selected_serial is None
