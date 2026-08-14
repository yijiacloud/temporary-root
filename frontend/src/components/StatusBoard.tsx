import { useEffect, useState } from "react";
import { api, ComponentStatus } from "../lib/api";
import { statusMeta } from "../lib/status";

function Chip({ c }: { c: ComponentStatus }) {
  const m = statusMeta(c.state);
  return (
    <div className="flex items-center justify-between rounded-lg bg-neutral-900 p-3 ring-1 ring-neutral-800">
      <span className="font-mono text-sm">{c.id}</span>
      <span className={`rounded-full px-2 py-0.5 text-xs ring-1 ${m.color}`}>
        {m.label}
      </span>
    </div>
  );
}

export default function StatusBoard() {
  const [data, setData] = useState<{
    temporary_root: ComponentStatus;
    components: ComponentStatus[];
    selinux: string;
    boot_id: string;
  } | null>(null);
  useEffect(() => {
    api.getStatus().then(setData).catch(() => {});
  }, []);
  if (!data) return <div className="text-neutral-500">加载中…</div>;
  return (
    <div className="space-y-4">
      <div className="flex gap-6 text-sm text-neutral-400">
        <span>
          SELinux: <b className="text-neutral-100">{data.selinux}</b>
        </span>
        <span>
          Boot: <b className="text-neutral-100">{data.boot_id}</b>
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        <Chip c={data.temporary_root} />
        {data.components.map((c) => (
          <Chip key={c.id} c={c} />
        ))}
      </div>
    </div>
  );
}
