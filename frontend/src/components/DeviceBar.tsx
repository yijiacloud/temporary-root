import { useEffect, useState } from "react";
import { api, Device } from "../lib/api";

export default function DeviceBar({
  selected,
  onSelect,
}: {
  selected: string | null;
  onSelect: (s: string | null) => void;
}) {
  const [devices, setDevices] = useState<Device[]>([]);
  useEffect(() => {
    api
      .getDevices()
      .then((d) => setDevices(d.devices))
      .catch(() => {});
  }, []);
  return (
    <div className="flex items-center gap-3">
      <label className="text-sm text-neutral-400">设备</label>
      <select
        className="rounded-lg bg-neutral-800 px-3 py-2 text-sm ring-1 ring-neutral-700"
        value={selected ?? ""}
        onChange={async (e) => {
          const v = e.target.value || null;
          onSelect(v);
          await api.selectDevice(v);
        }}
      >
        <option value="">（未选择）</option>
        {devices.map((d) => (
          <option key={d.serial} value={d.serial}>
            {d.serial} · {d.model ?? d.state}
          </option>
        ))}
      </select>
    </div>
  );
}
