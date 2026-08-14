import { useState } from "react";
import DeviceBar from "./components/DeviceBar";
import StatusBoard from "./components/StatusBoard";
import CommandPanel from "./components/CommandPanel";

type Page = "dashboard" | "control" | "root" | "update" | "logs";

const NAV: { id: Page; label: string }[] = [
  { id: "dashboard", label: "仪表盘" },
  { id: "control", label: "命令" },
  { id: "root", label: "Root" },
  { id: "update", label: "更新" },
  { id: "logs", label: "日志" },
];

export default function App() {
  const [serial, setSerial] = useState<string | null>(null);
  const [page, setPage] = useState<Page>("dashboard");
  return (
    <div className="flex min-h-screen">
      <aside className="w-52 border-r border-neutral-800 p-4">
        <h1 className="mb-6 text-lg font-bold">xpad2 Console</h1>
        <nav className="flex flex-col gap-1">
          {NAV.map((n) => (
            <button
              key={n.id}
              onClick={() => setPage(n.id)}
              className={`rounded-lg px-3 py-2 text-left text-sm ${
                page === n.id
                  ? "bg-neutral-800 text-white"
                  : "text-neutral-400 hover:bg-neutral-900"
              }`}
            >
              {n.label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="flex-1 p-6">
        <DeviceBar selected={serial} onSelect={setSerial} />
        <div className="mt-6">
          {page === "dashboard" && <StatusBoard />}
          {page === "control" && <CommandPanel />}
          {page === "root" && <CommandPanel />}
          {page === "update" && <CommandPanel />}
          {page === "logs" && <CommandPanel />}
        </div>
      </main>
    </div>
  );
}
